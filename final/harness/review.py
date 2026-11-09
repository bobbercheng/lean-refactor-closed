#!/usr/bin/env python3
"""Compressed review loop (2026-10-14; with a cheap-model simp executor; the reviewer always comes from another provider
than the agent's model; docs/distillation_plan.md). The union's biggest lever (docs/retro_union_92.md: a reviewer names EXACT
text-level edits on a near-final proof, then a budgeted batch compile stacks the winners, +11.8 and +10.5 summed points) compressed into
one row's budget, with no knowledge from other lines:
  1. reviewer   one call (default GPT-6.1 Sol via OpenRouter): it sees the row's current best, its tokens / heartbeats / score, the
                heartbeat hot spots (harness/profile.py) and the general technique cards, and writes K exact edits as find/replace pairs
                (find = an exact substring of the proof) via the tool submit_edits
  2. batch      every edit applied alone, compiled and scored at $0 (primary toolchain); the winners stacked greedily (largest single gain
                first, each kept only if the stack still scores higher than the noise margin); the stack checked on every toolchain: a ladder
  3. handoff    the stacked best and every edit's outcome (kept / no gain / does not apply / compile error with its first error) as a notes
                text, for an executor session of a model from a DIFFERENT provider (default DeepSeek V4.1 Flash), which repairs the failing
                edits and polishes (probe/review/run_review_loop.sh)
    python3 harness/review.py --problem NAME --proof-file P --out OUT.json [--model openai/gpt-6.1-sol] [--k 8] [--effort high]
Compiles go through the scorer (memgate): run in a memory-capped unit, never from an interactive shell.
"""
from __future__ import annotations

import argparse, json, os, pathlib, re, sys, threading, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(1, str(ROOT / "harness"))
from harness.leantools import ROWS, HBS  # noqa: E402
from harness.architect import check, TECHNIQUES, _reasoning, ROUTING, KEY  # noqa: E402
from harness.pattern_cards import pattern_cards_for  # noqa: E402
from scorer.tokenize import split_declaration, count_tokens  # noqa: E402
from probe.verify_candidates import newest_first  # noqa: E402
from llm.openai_compat import create  # noqa: E402

MIN_GAIN = 0.05
_LEDGER_LOCK = threading.Lock()
REVIEW_SYSTEM = "You are an expert Lean 4 proof reviewer."
# 2026-10-22 (cap safety at router --target-frac 1.0, where the review reserve is the only headroom under the cap): every paid review call is
# priced at its WORST CASE before it is sent, its input included (was: output cap x output price only; b34a/b34b: 4 of 72 calls used the
# whole 16k cap and cost $0.164-0.166 against a $0.160 output-only estimate). Input bound: a token covers at least one UTF-8 byte of the text
# it encodes (byte-level BPE, SentencePiece with byte fallback), so the bytes of the JSON-serialized system prompt, messages and tool schema
# (which also counts escapes, quotes and keys) plus INPUT_SLACK_TOKENS for the chat template bound the provider's input count (measured
# review prompts: 2.5k tokens median, 4.2k max). A call whose full output cap does not fit is sent with a smaller cap (what the budget can
# pay for; agent.fit_output_cap), or not sent below REVIEW_MIN_TOKENS (b34a/b34b review outputs: median 2.5k, p75 4.6k tokens).
INPUT_SLACK_TOKENS = 2000
REVIEW_MIN_TOKENS = 4000


def _unknown_bill(mm) -> bool:
    from harness.agent import unknown_bill
    return unknown_bill(mm)


def input_bound(system: str, msgs: list, tools: list | None) -> int:
    """An upper bound on a call's input tokens (see INPUT_SLACK_TOKENS above)."""
    return len(json.dumps([system, msgs, tools or []], ensure_ascii=False, default=str).encode("utf-8")) + INPUT_SLACK_TOKENS


def ledger(rec: dict) -> None:
    """2026-10-20 price-trace audit: one JSON line per review call and per failed attempt, appended at once to $LRA_REVIEW_LEDGER (the router
    sets <run-dir>/review_calls.jsonl), so every paid call is traceable with its tokens and dollars even when the row's review later fails."""
    path = os.environ.get("LRA_REVIEW_LEDGER")
    if not path:
        return
    try:
        with _LEDGER_LOCK, open(path, "a") as f:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **rec}, ensure_ascii=False) + "\n")
    except OSError:
        pass   # the trace never fails a review
SUBMIT = [{"name": "submit_edits", "description": "Submit exact text edits of the current proof.",
           "input_schema": {"type": "object", "properties": {"edits": {"type": "array", "items": {"type": "object", "properties": {
               "label": {"type": "string"},
               "find": {"type": "string", "description": "an EXACT substring of the current proof (copy it verbatim, whitespace included)"},
               "replace": {"type": "string", "description": "its replacement"},
               "why": {"type": "string", "description": "one line: why it should cut tokens or heartbeats"}},
               "required": ["label", "find", "replace"]}}}, "required": ["edits"]}}]


# ---------------------------------------------------------------------------------------------------------- b72 R6 (docs/b72_r6.md)
# Behind run(repair=, stack=) / run_rounds(...) (router --review-repair N / --review-stack; postpass --polish-repair / --polish-stack); both
# off by default, where run() and run_rounds() take exactly the pre-R6 path. Generic: no row text, no tables.
#   REPAIR  one turn per edit that failed to compile (at most `repair` per round, in the reviewer's order): the review's own model gets ONLY
#           the edit (find / replace), the compile error and the local goal (repair_prompt), returns a corrected edit (submit_repair), which
#           is compiled once like a single. Each call is priced, gated, retried, ledgered and metered exactly as the review's calls
#           (PricedCaller, kind "repair"; worst case at the cap prices before it is sent, within what the round's budget has left) and booked
#           once into the round's review cost (cost_exact / cap_cost_exact). A repair that fails, is skipped or raises leaves the round's
#           edits, singles and accounting as they were (its failed attempts' charged worst cases included).
#   STACK   after the round's singles (and repairs) and the paying-edit ladder: every compiling edit whose single score is >= the round
#           base - stack_eps (below the 0.05 bar included) applied together (largest single first, an overlapping edit skipped), checked in
#           ONE full compile on every pin; when it fails or does not beat the base, a greedy fallback (each edit kept when the stack still
#           compiles on the primary pin and scores higher; at most STACK_GREEDY_MAX compiles) then one full check. A stack verified on every
#           pin (Z = 100, statement prefix identical, check_forbidden clean) and above the base is (a) the round's output when it beats the
#           ladder's full reading and (b) returned for the row's bank (run_rounds: stack_proofs), where the end stage reads it back to back
#           with its incumbent (scorer.accept.decide, bar 0.005): no other acceptance. A stack that fails or raises keeps the ladder's result.
STACK_EPS = 0.02
STACK_GREEDY_MAX = 6
REPAIR_MAX_TOKENS = 8000
REPAIR_SYSTEM = REVIEW_SYSTEM
REPAIR_TOOL = [{"name": "submit_repair", "description": "Submit the corrected edit (or give up).",
                "input_schema": {"type": "object", "properties": {
                    "find": {"type": "string", "description": "optional: an exact substring of the ORIGINAL find text to replace instead "
                                                              "(default: the original find text)"},
                    "replace": {"type": "string", "description": "the corrected replacement text"},
                    "give_up": {"type": "boolean", "description": "true when no corrected edit keeps the intended saving"}},
                    "required": ["replace"]}}]
_GOAL = re.compile(r"⊢ (.*?)(?= ‖ | case \S+ |$)")


def local_goal(errors: list) -> str:
    """The goal(s) the compile error shows (harness/leantools.digest_error keeps every `⊢ goal` in full), one per line; a stand-in line when
    the error shows none (an unknown name, a parse error)."""
    goals = []
    for e in errors or []:
        for g in _GOAL.findall(re.sub(r"\s+", " ", str(e))):
            g = g.strip()
            if g and ("⊢ " + g) not in goals:
                goals.append("⊢ " + g)
    return "\n".join(goals[:4]) if goals else "(the error shows no goal)"


def repair_prompt(find: str, replace: str, errors: list) -> str:
    """The R6 repair turn's whole prompt: the edit, its compile error and the local goal. Nothing else (no row name, statement, proof,
    numbers or cards): test_b72_r6 checks it."""
    err = "\n".join(str(e) for e in (errors or ["?"]))[:1400]
    return (
        "A reviewer proposed the exact text edit below on a Lean 4 proof, to make it shorter (fewer Lean tokens) or cheaper to elaborate "
        "(fewer heartbeats). Applied alone, it does not compile. Repair it: give a corrected replacement that keeps the intended saving and "
        "compiles.\n\n"
        f"EDIT (`find` is an exact substring of the proof; `replace` is its proposed new text):\nfind:\n```lean\n{find}\n```\nreplace:\n"
        f"```lean\n{replace}\n```\n\n"
        f"COMPILE ERROR with the edit applied (line:column positions are in the compiled file):\n{err}\n\n"
        f"LOCAL GOAL at the error:\n{local_goal(errors)}\n\n"
        "TASK: call submit_repair ONCE: `replace` = the corrected replacement for the same `find` text (you may narrow `find` to an exact "
        "substring of it). Keep the edit's intent; do not restore the original text. If no corrected edit keeps the saving, set give_up.")


def parse_repair(mm, find0: str) -> tuple:
    """(find, replace) of a submit_repair answer, or (None, why). find defaults to the original find; a find outside it, a give-up, a
    missing or empty replace, or a no-op edit is no repair."""
    cs = [b for b in (getattr(mm, "content", None) or []) if getattr(b, "type", None) == "tool_use" and getattr(b, "name", None) == "submit_repair"]
    if not cs:
        return None, "no submit_repair call"
    a = cs[0].input if isinstance(cs[0].input, dict) else {}
    if a.get("give_up") is True:
        return None, "the reviewer gave up"
    r = a.get("replace")
    if not isinstance(r, str):
        return None, "no replace text"
    f = a.get("find") if isinstance(a.get("find"), str) and a.get("find") else find0
    if f not in find0:
        return None, "find is not part of the original find text"
    if r == f:
        return None, "a no-op edit"
    return (f, r), None


def guard(name: str, text: str) -> str | None:
    """R6 candidates (a repaired edit, a stack) are compiled and banked only with the row's statement prefix intact and a clean body
    (scorer.forbidden.check_forbidden), as the end stage's acceptance requires; the reason otherwise."""
    from scorer.forbidden import check_forbidden
    body = split_declaration(text.strip(), ROWS[name]["statement"])
    if body is None:
        return "statement differs"
    bad = check_forbidden(body)
    return f"forbidden: {bad}" if bad else None


def _all_pins(c: dict) -> bool:
    return bool(c.get("ok")) and c.get("score") is not None and float(c.get("Z") or 0) >= 100.0 - 1e-9


def stack_edits(name: str, proof: str, base_score: float, cands: list, versions: list, log=print, eps: float = STACK_EPS,
                greedy_max: int = STACK_GREEDY_MAX, known: tuple | None = None) -> dict:
    """R6 STACK (module notes above). cands: (single score, find, replace, record) of the round's compiling edits on `proof`. known: (text,
    full reading) already measured (the ladder's output), reused instead of a second compile. Returns {"status": "stacked" | "no candidate" |
    "no gain", "mode": "all" | "greedy", "proof", "metrics", "edits", "candidates", "compiles", ...}; never changes `proof`."""
    pool = sorted([c for c in cands if c[0] is not None and float(c[0]) >= float(base_score) - eps - 1e-9], key=lambda x: -float(x[0]))
    out = {"candidates": len(pool), "compiles": 0, "eps": eps}
    if not pool:
        out["status"] = "no candidate"; return out

    def full(text):
        g = guard(name, text)
        if g:
            return {"ok": False, "error": g}
        if known and known[0] is not None and text.strip() == str(known[0]).strip() and known[1]:
            return dict(known[1])
        out["compiles"] += 1
        return check(name, text, versions, full=True)

    def done(text, c, mode, used):
        out.update(status="stacked", mode=mode, proof=text, edits=used,
                   metrics={x: c.get(x) for x in ("ok", "tokens", "heartbeats", "L", "H", "Z", "compat", "score")})
        log(f"   R6 stack ({mode}, {len(used)} edits): {base_score} -> {c.get('score')}")
        return out
    cur, used = proof, []
    for s, f, r, rec in pool:
        if f and cur.count(f) == 1:
            cur = cur.replace(f, r, 1); used.append(str(rec.get("label"))[:60])
    out["all_edits"] = list(used)
    if used and cur != proof:
        c = full(cur)
        out["all"] = {x: c.get(x) for x in ("ok", "tokens", "heartbeats", "Z", "score", "error")} | (
            {"error": " | ".join(c.get("errors") or [])[:300]} if not c.get("ok") and c.get("errors") else {})
        if _all_pins(c) and float(c["score"]) > float(base_score):
            return done(cur, c, "all", used)
    if len(used) <= 1:   # one edit: the greedy fallback would try the same text again
        out["status"] = "no gain"; return out
    g, gs, kept, n = proof, float(base_score), [], 0
    for s, f, r, rec in pool:
        if n >= greedy_max:
            break
        if not f or g.count(f) != 1:
            continue
        cand = g.replace(f, r, 1)
        if guard(name, cand):
            continue
        if not kept:   # the first edit alone is the single the round already measured on the same base (primary pin)
            ok, sc = True, float(s)
        else:
            n += 1; out["compiles"] += 1
            c = check(name, cand, versions); ok, sc = bool(c.get("ok")), float(c.get("score") or 0)
        if ok and sc > gs:
            g, gs = cand, sc; kept.append(str(rec.get("label"))[:60])
    if kept and g != proof:
        c = full(g)
        if _all_pins(c) and float(c["score"]) > float(base_score):
            return done(g, c, "greedy", kept)
    out["status"] = "no gain"; return out


class PricedCaller:
    """The paid-call machinery of run() (2026-10-25, b63 item 16: shared by harness/repair.py so the REPAIR route is priced, retried and
    ledgered exactly as the review): every call priced at its worst case before it is sent (input bound + output cap), the output cap shrunk
    to what the budget can pay (agent.fit_output_cap) or the call not sent below REVIEW_MIN_TOKENS, a stalled stream / 5xx retried at most
    3 times with the failed attempts' worst cases charged as spent when they may have been billed, one ledger line per call and per failed
    attempt ($LRA_REVIEW_LEDGER), metered dollars as agent.py's spend meter prices a turn.
    b64 L0 (cap safety): two price tables. The GATE (plan, the charged worst cases, the budget the caller hands in) uses the preset's cap
    prices (agent.cap_prices, `cap_price` mode: "announced" = e.g. Argon at $4 / $20, "list" = the pre-L0 gate); the METER (metered(), the
    reported spend, the ledger's metered_usd) keeps the list table. cap_metered() is a call at the cap prices: what the caller adds to the
    spend it budgets with, so the sum over every call of a row never passes the budget at either price."""

    def __init__(self, name: str, model: str, effort: str, max_tokens: int, budget_usd: float | None, log=print, *, system: str = REVIEW_SYSTEM,
                 tools: list | None = None, kind: str = "call", cap_price: str = "announced"):
        from harness.agent import MODEL_PRESETS, cap_prices
        self.name, self.model, self.effort, self.max_tokens, self.budget_usd, self.log = name, model, effort, max_tokens, budget_usd, log
        self.system, self.tools, self.kind = system, tools if tools is not None else SUBMIT, kind
        self.preset = MODEL_PRESETS.get(model) or {}
        self.prices = self.preset.get("prices")
        self.cap_prices = cap_prices(self.preset, cap_price) if self.prices else None
        self.cap_diff = bool(self.prices) and tuple(self.cap_prices) != tuple(self.prices)
        self.gated = budget_usd is not None and bool(self.prices)
        self.per_call: list = []; self.failed: list = []
        self.charged = [0.0]   # worst cases charged for failed attempts that may have been billed (2026-10-22): counted as spent (list table)
        self.charged_cap = [0.0]   # b64 L0: the same attempts' worst cases at the cap prices (what the gate counts)
        # b65 (2): the worst case (list table, cap prices) planned for the call in flight; an OpenRouter call whose bill stays unknown (an
        # estimated usage, no cost: agent.unknown_bill) is metered at least at it, not at the estimate
        self.last_worst: tuple | None = None
        self.or_billed = "openrouter.ai" in (self.preset.get("base_url") or "")

    def metered(self, mm) -> float:
        # 2026-10-20 price-trace audit (Argon on Vertex priced as on OpenRouter): priced exactly as agent.py's spend
        # meter prices a turn: a list_price preset from its table on the call's tokens, cached input at the cache-read price (was: every input
        # token at the full price on Vertex, and the billed cost, 0.99 x list, on OpenRouter); otherwise the provider's cost, else the table
        if self.or_billed and self.last_worst and _unknown_bill(mm):   # b65 (2)
            return max(self._metered(mm), self.last_worst[0])
        return self._metered(mm)

    def _metered(self, mm) -> float:
        u = mm.usage; prices, preset = self.prices, self.preset
        if preset.get("meter_billed") and u.cost is not None:   # b65 (3): agent.metered_usd's rule: the billed cost, never below the
            from harness.agent import metered_usd               # call at its list table (2026-10-27); the table only without one
            return metered_usd(preset, u)
        if prices and (preset.get("list_price") or u.cost is None):
            if u.cost is None:   # b65-final: at the cap prices when the pin admits endpoints above the table (agent.meter_table)
                from harness.agent import meter_table
                prices = meter_table(preset)
            pi, po, pr, pw = prices
            cr, cw = int(getattr(u, "cache_read", 0) or 0), int(getattr(u, "cache_write", 0) or 0)
            tab = (max(0, u.input_tokens - cr - cw) * pi + u.output_tokens * po + cr * pr + cw * pw) / 1e6
            return max(tab, float(u.cost)) if u.cost is not None else tab   # never below a reported cost (a stale table must not under-count)
        return float(u.cost or 0)

    def cap_metered(self, mm) -> float:
        """b64 L0: the call at the cap prices, never below a reported cost (= metered() when the cap prices are the list table)."""
        if not self.cap_diff:
            return self.metered(mm)
        from harness.agent import table_cost
        u = mm.usage; tab = table_cost(u, self.cap_prices)
        c = max(tab, float(u.cost)) if u.cost is not None else tab
        return max(c, self.last_worst[1]) if (self.or_billed and self.last_worst and _unknown_bill(mm)) else c   # b65 (2)

    def trace(self, mm, meta) -> None:   # one record per completed call (with the failed attempts before it), in per_call and in the ledger
        u = mm.usage
        rec = {"problem": self.name, "model": self.model, "effort": self.effort, "max_tokens": (meta or {}).get("max_tokens", self.max_tokens),
               "input": u.input_tokens, "output": u.output_tokens,
               "cached": getattr(u, "cache_read", None), "cache_write": getattr(u, "cache_write", None), "reasoning": getattr(u, "reasoning", None),
               "cost_reported": u.cost, "metered_usd": round(self.metered(mm), 6), "stop": mm.stop_reason, "seconds": (meta or {}).get("seconds"),
               "failed_attempts": list(self.failed)}
        if self.cap_diff:   # b64 L0: what the gate counted for this call (the cap prices); the list-price lines are unchanged
            rec["cap_usd"] = round(self.cap_metered(mm), 6)
        self.per_call.append(rec); self.failed.clear(); ledger(dict(rec, type=self.kind))

    def plan(self, mm, spent_now: float) -> tuple:
        """(max_tokens for the next call, its worst case $) or (None, worst case at the full cap) when it does not fit the budget. Priced at the
        cap prices; spent_now is the caller's spend at the cap prices (b64 L0)."""
        from harness.agent import fit_output_cap
        prices, max_tokens = self.cap_prices, self.max_tokens
        if not self.gated:
            return max_tokens, max_tokens * (prices[1] if prices else 0) / 1e6
        fixed = input_bound(self.system, mm, self.tools) * max(prices[0], prices[3]) / 1e6
        n, r = fit_output_cap(float(self.budget_usd), spent_now + self.charged_cap[0], fixed, prices[1], max_tokens, min(REVIEW_MIN_TOKENS, max_tokens))
        return (n, r) if n is not None else (None, fixed + max_tokens * prices[1] / 1e6)

    def _pin_exc(self, cls, status, msg):
        """b65-final: the PinUnservable a confirmed pin raises, carrying what this call's failed attempts were charged (run_rounds adds it
        to the review's spend instead of assuming the budget)."""
        e = cls(status, msg, before_data=True)
        e.charged, e.charged_cap, e.pin_confirmed = self.charged[0], self.charged_cap[0], True
        return e

    def list_worst(self, mm, max_tokens: int) -> float:
        """b64 L0: a call's worst case at the list table (what a possibly billed failed attempt is reported as). b65-final: at the cap prices
        when the preset's max_price pin is above its table (agent.meter_table)."""
        from harness.agent import meter_table
        p = meter_table(self.preset)
        return input_bound(self.system, mm, self.tools) * max(p[0], p[3]) / 1e6 + max_tokens * p[1] / 1e6

    def call_retry(self, mm, spent_now: float = 0.0):   # 2026-10-15: a stalled stream (silence limit) or a 5xx is retried, at most 3 tries per call
        from harness.architect import call as _call
        from harness.agent import PINS, maybe_billed, pin_unservable
        from harness import pinwatch as PW
        from llm.openai_compat import PinUnservable, with_connect_retry, with_rate_limit_retry
        name, model, effort, log, budget_usd = self.name, self.model, self.effort, self.log, self.budget_usd
        rl: dict = {}   # 2026-10-20: a 429 (Vertex capacity, Azure quota) waits on its own budget, shared by the 3 tries of this call
        cn: dict = {}   # b66 (A4): the connect-failure budget of this call (llm/openai_compat.with_connect_retry)
        last = None
        attempt = -1   # b65-final: a while loop, so a pin error ($0, retried after PW.PIN_BACKOFF_S) does not use up one of the 3 tries
        while attempt < 2:
            attempt += 1
            if PINS.dead(model):   # b65-final: a CONFIRMED pin (harness/pinwatch.py; fresh for PIN_WINDOW_S): no request is sent, $0
                PINS.skip(model, name)
                raise self._pin_exc(PinUnservable, 404, PINS.dead(model))
            mt, wc = self.plan(mm, spent_now)   # 2026-10-22: every attempt is priced before it is sent (a retry included)
            self.last_worst = (self.list_worst(mm, mt) if self.cap_diff else wc, wc) if (mt is not None and self.gated) else None
            if mt is None:
                if attempt == 0:
                    return None, None, {"skipped": f"worst case ${wc:.3f} exceeds the ${float(budget_usd) - spent_now - self.charged_cap[0]:.3f} left"}
                raise last   # the failed call cannot be retried under the budget
            t1 = time.time()
            try:
                if model.startswith("codex:"):   # 2026-10-16: a Codex session answers the same prompt (llm/codex_review.py; $0 on the plan)
                    from llm.codex_review import review_call
                    return review_call(model.split(":", 1)[1], mm[0]["content"], effort, name), None, {}
                # b66 (A4): a connect failure (never sent, $0) waits for the network on its own budget, not one of the 3 tries
                out = with_rate_limit_retry(lambda: with_connect_retry(lambda: _call(model, mm, effort, mt, tools=self.tools, system=self.system),
                                                                       state=cn, log=lambda s_: log(f"{name[:30]} review call: {s_}")),
                                            state=rl, log=lambda s_: log(f"{name[:30]} review call: {s_}"))
                out[2]["max_tokens"] = mt
                if PINS.pending(model, name) and PINS.answered(model, name):   # b65-final: answered after this row's pin errors: the pin
                    log(f"{name[:30]} review call: answered after pin error(s): the pin serves")   # serves (every row's earlier errors lifted)
                return out
            except Exception as e:  # noqa: BLE001
                # a 429 is not billed; a stall or a broken stream may have been (the meter cannot see it): traced; when the call is budgeted
                # (2026-10-22) its worst case is charged as spent, so the retry and the rounds after it stay under the budget
                last = e
                fa = {"attempt": attempt, "status": getattr(e, "status_code", None), "error": f"{type(e).__name__}: {str(e)[:200]}",
                      "seconds": round(time.time() - t1, 1), "max_tokens": mt}
                if self.gated and maybe_billed(e):
                    wl = self.list_worst(mm, mt) if self.cap_diff else wc   # reported at the list table, gated at the cap prices (b64 L0)
                    self.charged[0] += wl; self.charged_cap[0] += wc; fa["assumed_usd"] = round(wl, 6)
                    if self.cap_diff:
                        fa["assumed_cap_usd"] = round(wc, 6)
                self.failed.append(fa); ledger(dict(fa, type="failed_attempt", problem=name, model=model, effort=effort))
                pin = pin_unservable(e, model)
                if pin:   # b65-final: a pin error, refused before any data ($0: maybe_billed is False above): retried after a backoff
                    conf = PINS.observe(model, name, pin, status=getattr(e, "status_code", None))   # (not one of the 3 tries) until answered
                    # or CONFIRMED (harness/pinwatch.py; review 2026-10-27: a 503 confirms only by this row's streak, never on 2 rows)
                    if conf:   # a confirmed pin skips this row's review at $0 (run_rounds records the review's real spend, not its budget)
                        log(f"{name[:30]} review call: FATAL (max_price pin of {model}): {conf}; this row's review is skipped ($0)")
                        PINS.skip(model, name)
                        raise self._pin_exc(PinUnservable, getattr(e, "status_code", 404), conf) from e
                    log(f"{name[:30]} review call: pin error (not confirmed; retry in {PW.PIN_BACKOFF_S:.0f} s, $0): {pin[:160]}")
                    if PW.wait_backoff(PW.PIN_BACKOFF_S, lambda: PINS.dead(model)):   # another row's call confirmed it meanwhile
                        PINS.skip(model, name)
                        raise self._pin_exc(PinUnservable, getattr(e, "status_code", 404), PINS.dead(model) or pin) from e
                    attempt -= 1; continue
                log(f"{name[:30]} review call failed ({type(e).__name__}: {str(e)[:120]}); try {attempt + 1} of 3")
                if getattr(e, "connect_exhausted", False):   # b66 (A4): never sent ($0); what this call's earlier attempts were charged
                    e.charged, e.charged_cap = self.charged[0], self.charged_cap[0]
                    raise
                if attempt == 2 or getattr(e, "rate_limit_exhausted", False):
                    raise
                time.sleep(30 * (attempt + 1))


def prompt(name: str, proof: str, numbers: dict, hot: list, k: int, prior: str = "") -> str:
    row = ROWS[name]
    hs = "\n".join(f"  lines {b['lines']}: {b['heartbeats']} hb  `{b['text'][:90]}`" for b in hot[:8] if b.get("heartbeats")) or "  (not measured)"
    return (
        "You are reviewing a Lean 4 proof that has already been polished for a long time. Your job is NOT to rewrite it: name the exact "
        "text-level edits that make it shorter (fewer Lean tokens) or cheaper (fewer elaboration heartbeats) while it still compiles.\n\n"
        "SCORE = mean of token reduction, heartbeat reduction and compatibility versus the reference proof; "
        f"reference {row['proof_length']} tokens, {HBS.get(name, '?')} heartbeats"
        + (f" (so one token is worth about {HBS[name] / row['proof_length']:.0f} heartbeats in the score).\n\n" if HBS.get(name) else ".\n\n") +
        f"CURRENT BEST ({numbers.get('tokens')} tokens, {numbers.get('heartbeats')} heartbeats, score {numbers.get('score')}):\n"
        f"```lean\n{proof.rstrip()}\n```\n\n"
        f"HEARTBEAT HOT SPOTS (cost of each top-level step):\n{hs}\n\n"
        f"{TECHNIQUES}\n\n{pattern_cards_for(row['statement'], proof, k=3)}\n\n"
        + (f"EARLIER REVIEW ROUNDS ON THIS PROOF (their outcomes were measured; do not propose them again; the proof above already holds "
           f"every edit that paid):\n{prior}\n\n" if prior else "") +
        f"TASK: call submit_edits ONCE with up to {k} independent edits, most promising first. Each edit is an exact find/replace on the "
        "current proof: `find` must be copied verbatim from it (an exact substring, whitespace included), `replace` is its new text. Prefer "
        "edits aimed at the hot spots and at removable tokens; each edit is compiled and scored on its own, and the winners are combined.")


def run(name: str, proof: str, model: str, k: int, effort: str, max_tokens: int = 32000, log=print, continue_on_length: int = 0,
        budget_usd: float | None = None, prior: str = "", cap_price: str = "announced", repair: int = 0, stack: bool = False,
        stack_eps: float = STACK_EPS) -> dict:
    """continue_on_length (2026-10-15, Kimi K3 at max effort; the IMO-setup length guard): a review cut at max_tokens before it
    submitted continues from its own output (Azure's Kimi returns cut reasoning as text, so the continuation sees it), at most that many
    times. budget_usd: the review's dollar cap (the row's $3 minus the ladder spend and an executor reserve); a call whose worst case (its
    full output cap) would cross it is not made. b64 L0: the budget is in CAP-price dollars (agent.cap_prices, `cap_price` mode); the
    review's cost is reported at the list table (cost, cost_exact) and at the cap prices (cap_cost_exact, what run_rounds budgets with).
    b72 R6 (off by default): repair = repair turns per round for edits that failed to compile; stack = the one-compile stack of every
    compiling edit within stack_eps of the base (module notes at STACK_EPS)."""
    row = ROWS[name]; versions = newest_first(row["version_info"])
    from harness.profile import profile
    base = check(name, proof, versions)
    res = {"problem": name, "model": model, "base": {x: base.get(x) for x in ("ok", "tokens", "heartbeats", "score")}, "edits": []}
    if not base.get("ok"):
        res["status"] = "base does not compile"; return res
    try:
        pr = profile(name, proof); hot = pr.get("blocks") or []
    except Exception as e:  # noqa: BLE001
        hot = []; res["profile_error"] = f"{type(e).__name__}"
    t0 = time.time()
    pc = PricedCaller(name, model, effort, max_tokens, budget_usd, log, system=REVIEW_SYSTEM, tools=SUBMIT, cap_price=cap_price)
    metered, trace, call_retry, charged, per_call, plan = pc.metered, pc.trace, pc.call_retry, pc.charged, pc.per_call, pc.plan
    msgs = [{"role": "user", "content": prompt(name, proof, base, hot, k, prior)}]
    gated = pc.gated
    mt0, worst = plan(msgs, 0.0)
    if mt0 is None:
        res["status"] = f"review skipped: one call's worst case ${worst:.2f} (input included) exceeds the review budget ${budget_usd:.2f}"; return res
    m, _sub, _meta = call_retry(msgs)   # a call that fails for good raises: run_rounds then counts the rest of the budget as spent
    if m is None:
        res["status"] = f"review skipped: {_meta.get('skipped')}"; return res
    trace(m, _meta)
    spent, n_in, n_out, rounds = metered(m), m.usage.input_tokens, m.usage.output_tokens, 1
    spent_cap = pc.cap_metered(m)   # b64 L0: what the gate counts (the cap prices)

    def submitted(mm) -> list:
        cs = [b for b in mm.content if b.type == "tool_use" and b.name == "submit_edits"]
        return ((cs[0].input or {}).get("edits") or []) if cs else []
    edits = submitted(m)
    while not edits and m.stop_reason in ("max_tokens", "end_turn") and rounds <= continue_on_length:
        # max_tokens: cut mid-reasoning, continue; end_turn without the tool call (2026-10-15: one model on a dev row): ask for the submission
        nudge = ("Your output was cut by the length limit. Continue from where your reasoning stopped, then call submit_edits ONCE with your "
                 "edits." if m.stop_reason == "max_tokens" else
                 "You ended without calling submit_edits. Call submit_edits ONCE now with your best exact edits of the current proof.")
        nxt = msgs + [{"role": "assistant", "content": [b.model_dump() for b in m.content] or [{"type": "text", "text": "(no output)"}]},
                      {"role": "user", "content": nudge}]
        if gated and plan(nxt, spent_cap)[0] is None:   # the continuation's worst case (its longer input included) must fit too
            break
        msgs = nxt
        try:
            m2, _sub, _meta = call_retry(msgs, spent_cap)
        except Exception as e:  # noqa: BLE001
            if getattr(e, "connect_exhausted", False):   # b66 (A4): never sent ($0): the answer so far is kept; no further call
                break
            if not getattr(e, "pin_confirmed", False):
                raise
            res["pin_unservable"] = str(getattr(e, "body", "") or e)[:300]   # b65-final: the answer so far is kept; no further call ($0)
            break
        if m2 is None:
            break
        m = m2; trace(m, _meta)
        spent += metered(m); spent_cap += pc.cap_metered(m); n_in += m.usage.input_tokens; n_out += m.usage.output_tokens; rounds += 1
        edits = submitted(m)
        log(f"{name[:30]} review continued after the length cut ({rounds} calls, ${spent:.2f}): {len(edits)} edits")
    spent += charged[0]; spent_cap += pc.charged_cap[0]
    res["review"] = {"seconds": round(time.time() - t0, 1), "input": n_in, "output": n_out, "cost": round(spent, 4), "stop": m.stop_reason,
                     "n_edits": len(edits), "calls": rounds, "effort": effort, **({"assumed": round(charged[0], 6)} if charged[0] else {})}
    log(f"{name[:30]} review: {len(edits)} edits, {res['review']}")
    res["review"]["per_call"] = per_call   # after the log line: the router log keeps its one-line format
    res["review"]["cost_exact"] = spent    # the reported (list-table) cost, unrounded
    res["review"]["cap_cost_exact"] = spent_cap   # b64 L0: run_rounds budgets the next round from this (the cap prices), not from a rounded cost
    # 2. batch: each edit alone
    singles = []
    failed, compiled = [], []   # b72 R6: the compile failures (repair) and the compiling edits (stack); unused with R6 off
    for e in edits[:k]:
        f, r = str(e.get("find") or ""), str(e.get("replace") or "")
        rec = {"label": str(e.get("label"))[:60], "find": f[:300], "replace": r[:300], "why": str(e.get("why") or "")[:200]}
        if not f or f not in proof:
            rec["outcome"] = "does not apply (find text not in the proof)"
        elif proof.count(f) > 1:
            rec["outcome"] = "ambiguous (find text occurs more than once)"
        else:
            c = check(name, proof.replace(f, r, 1), versions)
            rec.update(ok=c.get("ok"), tokens=c.get("tokens"), heartbeats=c.get("heartbeats"), score=c.get("score"))
            if not c.get("ok"):
                rec["outcome"] = "compile error: " + " | ".join(c.get("errors") or [c.get("error") or "?"])[:400]
                failed.append((f, r, rec, list(c.get("errors") or [c.get("error") or "?"])))
            elif (c.get("score") or 0) > (base.get("score") or 0) + MIN_GAIN:
                rec["outcome"] = f"pays alone: {base.get('score')} -> {c.get('score')}"; singles.append((c["score"], f, r, rec))
            else:
                rec["outcome"] = f"no gain ({c.get('score')} vs {base.get('score')})"
            if c.get("ok") and c.get("score") is not None:
                compiled.append((c["score"], f, r, rec))
        res["edits"].append(rec)
        log(f"   {rec['label'][:28]:28s} {rec['outcome'][:110]}")
    if repair > 0 and failed:   # b72 R6 REPAIR: before the ladder, so a repaired edit that pays alone is stacked like any other
        try:
            _repairs(name, proof, base, failed[:int(repair)], versions, model, effort, max_tokens, budget_usd, cap_price, log, res, singles,
                     compiled, spent_cap)
        except Exception as e:  # noqa: BLE001  (no harm: the round goes on with its own edits; what the repairs spent is booked)
            res["review"].setdefault("repair", {})["error"] = f"{type(e).__name__}: {str(e)[:160]}"
            log(f"{name[:30]} R6 repair failed ({type(e).__name__}); the round goes on without it")
    # ladder: stack the paying edits, largest single gain first
    cur, cur_s = proof, base.get("score") or 0
    for s, f, r, rec in sorted(singles, key=lambda x: -x[0]):
        if f not in cur:
            rec["stacked"] = "skipped (overlaps an edit already stacked)"; continue
        cand = cur.replace(f, r, 1); c = check(name, cand, versions)
        if c.get("ok") and (c.get("score") or 0) > cur_s + MIN_GAIN:
            cur, cur_s = cand, c["score"]; rec["stacked"] = f"kept ({cur_s})"
        else:
            rec["stacked"] = "dropped in the stack"
    full = check(name, cur, versions, full=True)
    res["stacked"] = {x: full.get(x) for x in ("ok", "tokens", "heartbeats", "L", "H", "Z", "score")}; res["proof"] = cur
    if stack:   # b72 R6 STACK: after the round's singles, repairs and ladder; a stack that fails or raises keeps the ladder's result
        try:
            st = stack_edits(name, proof, float(base.get("score") or 0), compiled, versions, log, stack_eps, known=(cur, full))
        except Exception as e:  # noqa: BLE001
            st = {"status": f"error {type(e).__name__}: {str(e)[:160]}"}
            log(f"{name[:30]} R6 stack failed ({type(e).__name__}); the ladder's result stays")
        sm = st.get("metrics") if st.get("status") == "stacked" else None
        st["bank"] = sm is not None   # verified on every pin and above the base: an end-stage candidate (run_rounds: stack_proofs)
        if sm is not None and (not full.get("ok") or float(sm.get("score") or 0) > float(full.get("score") or 0)) and st["proof"] != cur:
            cur, full = st["proof"], dict(sm); st["picked"] = True
            res["stacked"] = {x: full.get(x) for x in ("ok", "tokens", "heartbeats", "L", "H", "Z", "score")}; res["proof"] = cur
        res["stack"] = st
    res["status"] = "improved" if full.get("ok") and (full.get("score") or 0) > (base.get("score") or 0) + MIN_GAIN else "no gain"
    res["notes"] = handoff(res)
    return res


def _book(rv: dict, usd: float, cap: float) -> None:
    """b72 R6: a repair call's (or charged attempt's) dollars into the round's review cost, the one place run_rounds books it from."""
    rv["cost_exact"] = float(rv.get("cost_exact") or 0) + float(usd)
    rv["cap_cost_exact"] = float(rv.get("cap_cost_exact") or 0) + float(cap)
    rv["cost"] = round(rv["cost_exact"], 4)


def _repairs(name, proof, base, failed, versions, model, effort, max_tokens, budget_usd, cap_price, log, res, singles, compiled,
             spent_cap0) -> None:
    """b72 R6 REPAIR (module notes at STACK_EPS): one turn per failed edit, in order, each priced at its worst case within what the round's
    budget has left (spent_cap0 = the review calls' cap-price spend so far), compiled once; every completed call is booked into
    res["review"] at once and the charged worst cases of possibly billed failed attempts once at the end (finally), so an exception
    anywhere leaves the accounting complete. Repaired edits go into res["edits"] (the handoff and the next round's context), `compiled`
    (the stack) and, when they pay alone, `singles` (the ladder)."""
    rv = res["review"]
    rc = PricedCaller(name, model, effort, min(int(max_tokens), REPAIR_MAX_TOKENS), budget_usd, log, system=REPAIR_SYSTEM, tools=REPAIR_TOOL,
                      kind="repair", cap_price=cap_price)
    st = rv.setdefault("repair", {})
    st.update(failed=len(failed), sent=0, compiled=0, pays=0, no_repair=0, cost=0.0, cap_cost=0.0)
    cap_now = float(spent_cap0)
    try:
        for f, r, rec, errs in failed:
            msgs = [{"role": "user", "content": repair_prompt(f, r, errs)}]
            try:
                m, _sub, meta = rc.call_retry(msgs, cap_now)
            except Exception as e:  # noqa: BLE001  (a failed call ends the repairs; its charged attempts are booked below)
                st["stopped"] = f"{type(e).__name__}: {str(e)[:160]}"
                log(f"{name[:30]} R6 repair call failed ({type(e).__name__}); repairs stop here")
                break
            if m is None:
                st["stopped"] = f"skipped: {(meta or {}).get('skipped')}"
                break
            # b75 review: an answered (billed) call is booked BEFORE anything that can raise. run() catches an exception from here and the
            # round goes on, so a raise between the answer and the booking (the ledger trace, the meter) would leave a billed call out of the
            # review's spend, the row's ledger and every later gate. A meter that cannot price the answer books the call's planned worst
            # case (rc.last_worst, at the list table and the cap prices), else the rest of the budget. Same result on the normal path.
            try:
                usd, cap = rc.metered(m), rc.cap_metered(m)
            except Exception:  # noqa: BLE001
                w = rc.last_worst or ((max(0.0, float(budget_usd) - cap_now - rc.charged_cap[0]),) * 2 if budget_usd is not None else (0.0, 0.0))
                usd, cap = float(w[0]), float(w[1]); st["meter_error"] = True
            _book(rv, usd, cap); cap_now += cap; st["sent"] += 1
            st["cost"] = round(st["cost"] + usd, 6); st["cap_cost"] = round(st["cap_cost"] + cap, 6)
            try:
                rc.trace(m, meta)
            except Exception:  # noqa: BLE001  (the ledger line is a record; the booking above is what the gates read)
                st["trace_error"] = True
            fr, why = parse_repair(m, f)
            rr = {"label": f"{str(rec.get('label'))[:50]} (repair)", "repair_of": str(rec.get("label"))[:60],
                  "find": (fr[0] if fr else f)[:300], "replace": (fr[1] if fr else "")[:300], "why": "R6 repair of an edit that did not compile"}
            if fr is None:
                rr["outcome"] = f"repair: {why}"; st["no_repair"] += 1
            else:
                f2, r2 = fr
                if proof.count(f2) != 1:
                    rr["outcome"] = "repair: " + ("ambiguous (find text occurs more than once)" if proof.count(f2) > 1 else "does not apply")
                elif guard(name, proof.replace(f2, r2, 1)):
                    rr["outcome"] = "repair: " + str(guard(name, proof.replace(f2, r2, 1)))
                else:
                    c = check(name, proof.replace(f2, r2, 1), versions)
                    rr.update(ok=c.get("ok"), tokens=c.get("tokens"), heartbeats=c.get("heartbeats"), score=c.get("score"))
                    if not c.get("ok"):
                        rr["outcome"] = "repair: compile error: " + " | ".join(c.get("errors") or [c.get("error") or "?"])[:400]
                    else:
                        st["compiled"] += 1
                        if c.get("score") is not None:
                            compiled.append((c["score"], f2, r2, rr))
                        if (c.get("score") or 0) > (base.get("score") or 0) + MIN_GAIN:
                            rr["outcome"] = f"repair pays alone: {base.get('score')} -> {c.get('score')}"; singles.append((c["score"], f2, r2, rr))
                            st["pays"] += 1
                        else:
                            rr["outcome"] = f"repair: no gain ({c.get('score')} vs {base.get('score')})"
            res["edits"].append(rr)
            log(f"   {rr['label'][:28]:28s} {rr['outcome'][:110]}")
    finally:
        if rc.charged[0] or rc.charged_cap[0]:
            _book(rv, rc.charged[0], rc.charged_cap[0]); st["assumed"] = round(rc.charged[0], 6)
        rv["per_call"] = list(rv.get("per_call") or []) + list(rc.per_call)


def run_rounds(name: str, proof: str, model: str, k: int, effort: str, rounds: int = 3, max_tokens: int = 32000, log=print,
               continue_on_length: int = 0, budget_usd: float | None = None, patience: int = 2, cap_price: str = "announced",
               fallback_model: str | None = None, repair: int = 0, stack: bool = False, stack_eps: float = STACK_EPS) -> dict:
    """Multi-round review (2026-10-15, docs/astra_crossrow_proposal.md direction 3): short profile-directed
    rounds, each on the current stacked proof with a fresh heartbeat profile and the earlier rounds' measured edits as do-not-repeat
    context; the next round rebases on the winner. Stops after `rounds`, after `patience` rounds in a row without a gain, or when the
    rounds' review spend reaches budget_usd (a started round always finishes). b64 L0: budget_usd is in cap-price dollars (`cap_price`);
    review_spend is the reported (list-table) spend, review_cap_spend the same calls at the cap prices (<= budget_usd).
    b66 (retro A3, docs/b66_robust.md): with `fallback_model`, a CONFIRMED max_price pin of `model` does not end the review: that round and
    the rest run on fallback_model (once; its PricedCaller gates every call at ITS cap price, within what is left of budget_usd), recorded
    as `review_fallback` {"from", "to", "round", "message"}; without one (or when the fallback is pinned too) the review stops at $0 as before.
    b72 R6 (repair > 0 / stack; off by default: then no key below is added and run() is called exactly as before): every round's repairs
    and stack (run()); `stack_proofs` = each round's stack verified on every pin above its base (for the row's bank), `r6` the counts."""
    cur = proof; hist: list[str] = []; per: list[dict] = []; spent = 0.0; dry = 0
    r6kw = ({"repair": int(repair), "stack": bool(stack), "stack_eps": float(stack_eps)} if (repair or stack) else {})   # b72 R6
    stacks: list[dict] = []
    spent_cap = 0.0   # b64 L0: the gate's spend (cap prices); spent stays the reported spend
    first = None
    model0, fb = model, {}   # b66 (A3): the configured model and the fallback taken
    for r in range(rounds):
        if budget_usd is not None and spent_cap >= budget_usd:
            break
        res, stop = None, False
        while res is None:
            try:
                res = run(name, cur, model, k, effort, max_tokens, log, continue_on_length, None if budget_usd is None else budget_usd - spent_cap,
                          prior="\n".join(hist[-24:]), cap_price=cap_price, **r6kw)
            except Exception as e:  # noqa: BLE001  2026-10-20: a failed call (429 budget used, stall) after a paying round keeps that round's
                if getattr(e, "pin_confirmed", False):   # verified proof; the rest of the review budget counts as spent (its usage is unknown).
                    # b65-final (audit C3): a CONFIRMED max_price pin (review.PricedCaller) refused this round's first call before any data: $0.
                    # The review stops here at its REAL spend (earlier rounds + what this call's failed attempts were charged), never the
                    # budget, and the row keeps the best so far (its pre-review proof when this was round 1)
                    spent += float(getattr(e, "charged", 0) or 0); spent_cap += float(getattr(e, "charged_cap", 0) or 0)
                    pin_msg = str(getattr(e, "body", "") or e)[:300]
                    if fallback_model and not fb and fallback_model != model and (budget_usd is None or spent_cap < budget_usd):
                        # b66 (A3): this round again on the fallback model, gated at its cap price within what is left
                        per.append({"round": r, "status": f"pin_unservable: {pin_msg[:160]} (the review goes on on {fallback_model}, $0)",
                                    "fallback": True})
                        log(f"{name[:30]} round {r + 1}: confirmed max_price pin of {model} ($0); the review goes on on {fallback_model}")
                        fb = {"from": model, "to": fallback_model, "round": r + 1, "message": pin_msg}
                        model = fallback_model
                        continue
                    per.append({"round": r, "status": f"pin_unservable: {pin_msg[:160]} (review skipped, $0)"})
                    log(f"{name[:30]} round {r + 1}: review skipped on a confirmed max_price pin ($0); review spend ${spent:.3f}")
                    stop = True; break
                if getattr(e, "connect_exhausted", False):   # b66 (A4): the network stayed down past the connect budget; never sent ($0):
                    # the review stops at its REAL spend (earlier rounds + this call's charged attempts), never the budget
                    spent += float(getattr(e, "charged", 0) or 0); spent_cap += float(getattr(e, "charged_cap", 0) or 0)
                    per.append({"round": r, "status": f"connect failure: {type(e).__name__}: {str(e)[:120]} (review stopped; never sent, $0)"})
                    log(f"{name[:30]} round {r + 1}: review stopped: connect failures past the connect budget (never sent, $0); review spend ${spent:.3f}")
                    stop = True; break
                if first is None or budget_usd is None:   # With no budget the failed round's paid calls cannot be bounded: fail as before
                    raise
                assumed = max(0.0, (budget_usd - spent) if budget_usd is not None else 0.0)
                spent += assumed; spent_cap = max(spent_cap, float(budget_usd))   # b64 L0: the whole budget, on both meters
                per.append({"round": r, "status": f"error {type(e).__name__}: {str(e)[:160]} (spend assumed ${assumed:.3f})"})
                log(f"{name[:30]} round {r + 1}: review call failed ({type(e).__name__}); earlier rounds kept, ${assumed:.3f} assumed spent")
                stop = True; break
        if stop:
            break
        first = first or res.get("base")
        rv = res.get("review") or {}
        spent += float(rv.get("cost_exact", rv.get("cost")) or 0)
        spent_cap += float(rv.get("cap_cost_exact", rv.get("cost_exact", rv.get("cost"))) or 0)
        per.append({"round": r, "status": res.get("status"), "base": res.get("base"), "stacked": res.get("stacked"), "review": rv,
                    "edits": res.get("edits")} | ({"pin_unservable": res["pin_unservable"]} if res.get("pin_unservable") else {})
                   | ({"model": model} if fb else {})
                   | ({"stack": {x: v for x, v in res["stack"].items() if x != "proof"}} if res.get("stack") else {}))   # b72 R6
        st = res.get("stack") or {}
        if st.get("bank") and st.get("proof"):   # b72 R6: verified on every pin above its round's base: a candidate for the row's bank
            stacks.append({"proof": st["proof"], "round": r, "mode": st.get("mode"), "n_edits": len(st.get("edits") or []),
                           **{x: (st.get("metrics") or {}).get(x) for x in ("tokens", "heartbeats", "L", "H", "Z", "compat", "score")}})
        for e in res.get("edits") or []:
            hist.append(f"- round {r + 1}: {e['label']}: {e.get('outcome', '')[:160]}; find {e['find'][:100]!r} -> {e['replace'][:100]!r}")
        if res.get("status") == "improved" and res.get("proof"):
            cur = res["proof"]; dry = 0
        else:
            dry += 1
            if dry >= patience or res.get("status") in ("base does not compile",) or str(res.get("status", "")).startswith("review skipped"):
                break
        log(f"{name[:30]} round {r + 1}: {res.get('status')} -> {(res.get('stacked') or {}).get('score')} (review spend so far ${spent:.3f})")
    out = {"problem": name, "model": model0, "rounds": per, "base": first, "proof": cur, "review_spend": round(spent, 4),
           "review_cap_spend": round(spent_cap, 4)}
    pins = [x["status"] for x in per if str(x.get("status") or "").startswith("pin_unservable") and not x.get("fallback")] + \
        [x["pin_unservable"] for x in per if x.get("pin_unservable")]
    if pins:   # b65-final: flagged up to the router's summary.json (postpass keeps it in the polish stage's report)
        out["pin_unservable"] = pins[0][:300]
    if fb:   # b66 (A3)
        out["review_fallback"] = fb
    if r6kw:   # b72 R6: counts over the rounds; the verified stacks (the router banks them as review_stack)
        rp = [((x.get("review") or {}).get("repair") or {}) for x in per]
        out["r6"] = {"repair": int(repair), "stack": bool(stack), "stack_eps": float(stack_eps),
                     "repairs_sent": sum(int(x.get("sent") or 0) for x in rp), "repairs_compiled": sum(int(x.get("compiled") or 0) for x in rp),
                     "repairs_pay": sum(int(x.get("pays") or 0) for x in rp),
                     "repair_cost": round(sum(float(x.get("cost") or 0) for x in rp), 6),
                     "repair_cap_cost": round(sum(float(x.get("cap_cost") or 0) for x in rp), 6),
                     "stacks_verified": len(stacks), "stacks_picked": sum(1 for x in per if (x.get("stack") or {}).get("picked"))}
        if stacks:
            out["stack_proofs"] = stacks
        # every round's edits with their texts (cut at 300 characters, as recorded) and outcomes: the router keeps them in the review
        # step's report, so a later replay has the texts (finb's records kept only labels and outcomes)
        out["r6_rounds"] = [{"round": x["round"], "status": x.get("status"), "stack": x.get("stack"),
                             "edits": [{k: e.get(k) for k in ("label", "find", "replace", "outcome", "repair_of", "stacked") if e.get(k) is not None}
                                       for e in x.get("edits") or []]} for x in per]
    last = next((x["stacked"] for x in reversed(per) if x.get("status") == "improved"), None)
    out["final"] = last or first
    out["status"] = "improved" if last and (last.get("score") or 0) > ((first or {}).get("score") or 0) + MIN_GAIN else "no gain"
    return out


def handoff(res: dict) -> str:
    """The notes text for the executor session: the stacked result and every edit's outcome (its own measurements, no other lines)."""
    lines = ["# notes", "", f"A review of this proof proposed {len(res['edits'])} exact edits; each was compiled and scored alone, the winners stacked.",
             f"Start {res['base'].get('score')} ({res['base'].get('tokens')} tokens, {res['base'].get('heartbeats')} hb) -> stacked "
             f"{(res.get('stacked') or {}).get('score')}. candidate.lean is the stacked result.", "",
             "Edit outcomes (fix the ones that failed to compile if they still look promising; the 'no gain' ones were measured):"]
    for e in res["edits"]:
        lines.append(f"- {e['label']}: {e.get('outcome')}" + (f"; {e['stacked']}" if e.get("stacked") else ""))
        lines.append(f"    find: {e['find'][:160]!r}  ->  replace: {e['replace'][:160]!r}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--problem", required=True); ap.add_argument("--proof-file", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="openai/gpt-6.1-sol"); ap.add_argument("--k", type=int, default=8); ap.add_argument("--effort", default="high")
    a = ap.parse_args()
    r = run(a.problem, pathlib.Path(a.proof_file).read_text(), a.model, a.k, a.effort)
    out = pathlib.Path(a.out); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(r, ensure_ascii=False, indent=1))
    print(json.dumps({x: r.get(x) for x in ("problem", "status", "base", "stacked", "review")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
