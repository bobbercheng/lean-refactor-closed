#!/usr/bin/env python3
"""b85 style_rw (docs/b85_style_rw.md; design docs/b80_style_rewrite.md section 3.4, adopted 2026-10-29 after its validation
replay): an ACCEPT-ONLY paid step at the END of the router's end stage, on every row.

What it does (one row, after the end step wrote the row's final):
  units    the incumbent (the row's final) first, then up to STYLE_RW_UNITS - 1 other verified proofs of the row (the best candidate of each
           basin the end stage collected whose text is unlike the incumbent, token-set Jaccard < UNIT_JACCARD, within UNIT_MARGIN points),
           best first, one unit at a time: the next unit starts only when money and wall time are left.
  rounds   per unit: r1 (ONE call: rewrite the proof into the scoring dialect, K_CANDS complete declarations), one repair call per failing
           candidate (at most MAX_REPAIRS per round, with the exact compiler error on the primary pin), r2 (ONE call seeded with r1's best and
           every result), repairs again. The prompt (b80 rewrite.py's T1 prompt, frozen here) carries the scoring rule with the row's exchange
           rate, agent.py's TOKEN_RULES, the dialect guide, the statement, the proof with its reading, its depth-2 goal map (harness/goals)
           and the exemplar pairs of harness/style_rw_exemplars.json (frozen by sha: --style-rw-exemplars; a pair of the prompted row is
           never shown). The row's heartbeat reference is asserted present: a row without one is skipped at $0.
  model    --style-rw-preset (the closed final: gpt-6.1-sol-main, Sol medium on OpenRouter, pinned at list, metered at max(billed, list)),
           --style-rw-effort, through harness.review.PricedCaller (the review's own paid-call machinery): every call priced at its worst case
           at the cap prices BEFORE it is sent (input bound uncached + output cap), the output cap shrunk to what the budget has left
           (agent.fit_output_cap), the call not sent below the floor; a 429 / connect failure waits inside the attempt ($0); a 5xx, a
           timeout or a broken stream is charged its worst case once; a 4xx books nothing; a CONFIRMED pin ends the step at $0.
  budget   min(--style-rw-usd, cap - the row's metered spend at the cap price - SPEND_MARGIN), rounded down to 1e-4 (router.tail_room):
           the step can never push a row past the cap. Booked once: step `style_rw_started` (the budget) before the first call, step
           `style_rw` (the spend) after; a resume of a row that crashed inside the step books the whole budget as spent (as an interrupted
           review) and keeps the incumbent.
  scoring  every candidate on ALL pins with the row's end-stage meter (endstage.Meter: the run-start self-test, statement check,
           check_forbidden; LRA_FORCE_WARN_SORRY=1 is set for the compiles when the environment lacks it). A re-typed statement is spliced
           onto the exact one. The best verified candidate (Z 100) then gets the final writer's axiom audit (router_audit_fn: clean or
           skipped-no-sorry) and, when within POLISH_MARGIN of the incumbent, the run's own $0 end stage (the frozen --end-config, r10) as
           a one-candidate polish.
  accept   only if the polished candidate beats the incumbent by >= MIN_GAIN (0.05) on a single confirm read (incumbent and candidate back
           to back on the same meter, every pin, no Z regression); otherwise the incumbent stays BYTE-IDENTICAL. An accepted proof becomes
           step `style_rw` (stage "style_rw", the incumbent's stored score plus the same-meter delta, as the end step) and is banked.
  no harm  the incumbent is checkpointed (step `style_rw_started` carries its sha) before the step; any exception, refusal, junk answer,
           timeout or cap stop leaves the final as it was, except for the booked worst case of a possibly billed call.
  wall     HARD cap per row (2026-10-30, b80 3.4's "added wall <= 15 min per row"): the whole step (calls, compiles, audit, the
           polish, the confirm read) gets cap_s = min(--style-rw-wall-s (900 s), the row's end-stage clock left) from its start
           (router.style_rw_end_clock). Inside, every part works to the deadline: a new call only with CALL_MIN_LEFT_S left, candidate
           compiles and repair errors clipped to it, the polish stopped at deadline - the audit and confirm reserve (endstage stop_at,
           cooperative: the end stage's own budget stop), the confirm read only when it fits. The router runs the step in a worker thread
           and waits at most cap_s: what is still running then is ABANDONED (the gate refuses every later call; the incumbent stays
           byte-identical; the spend booked is the calls' metered spend, or the whole budget when a call was in flight).
Frozen into config.json "style_rw" (router.style_rw_config; a resume that changes it is refused). Off by default: a run without --style-rw
on has no key and runs no code of this module. Tests: harness/test_b85_stylerw.py (fake model, fake meter, no Lean)."""
from __future__ import annotations

import hashlib, json, math, os, re, threading, time, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXEMPLARS_PATH = ROOT / "harness" / "style_rw_exemplars.json"
STYLE_RW_STEP, STYLE_RW_START = "style_rw", "style_rw_started"
STYLE_RW_USD, STYLE_RW_PRESET, STYLE_RW_EFFORT = 0.30, "gpt-6.1-sol-main", "medium"
STYLE_RW_UNITS = 3          # the incumbent + up to 2 other basins' bests (b80 section 3.4 B "inputs")
UNIT_JACCARD = 0.6          # another unit's token set must be this unlike the incumbent's
UNIT_MARGIN = 2.5           # and within this many points of it
K_CANDS, MAX_REPAIRS = 4, 4
MAX_TOKENS = {"round": 24000, "repair": 12000}
FLOOR_TOKENS = {"round": 6000, "repair": 3000}
POLISH_MARGIN = 2.5         # the $0 polish runs on the best candidate when it is within this of the incumbent
MIN_GAIN = 0.05             # accept bar on the confirm read (postpass.MIN_GAIN)
BACKSTOP_S = 1500.0         # wall backstop per row: no new call after this many seconds since the step started
STYLE_RW_WALL_S = 900.0     # the step's hard wall cap per row (--style-rw-wall-s, frozen), min'd with the row's end-stage clock left
CALL_MIN_LEFT_S = 300.0     # a new call (round or repair) starts only with this much of the cap left: the call, its candidates, audit, confirm
POLISH_MIN_S = 60.0         # the polish runs only when it gets at least this much wall before its own deadline
POST_READS = 4.0            # after the polish: the audit (~1 full read) and the confirm read (2) of the incumbent's read time, reserved
POST_MIN_S = 60.0           # ... and at least this many seconds
MEASURE_MIN_S = 20.0        # a candidate is compiled only when this much is left before that reserve (else "not measured")
TAG = "style_rw"
_LOCK = threading.Lock()
_LEAN_SEM = threading.Semaphore(2)   # repair-error recompiles and goal maps (harness/mine.lean_run): at most 2 at once beside the meters


# ------------------------------------------------------------------------------------------------------------------------------ exemplars
def exemplars_sha(path: Path = EXEMPLARS_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def load_exemplars(sha: str | None, path: Path = EXEMPLARS_PATH) -> list[dict]:
    """The exemplar pairs; raises when the file's sha is not `sha` (the frozen flag) or a pair is not usable."""
    path = Path(path)
    have = exemplars_sha(path)
    if sha and have != sha:
        raise RuntimeError(f"{path.name}: sha {have} differs from the frozen --style-rw-exemplars {sha}")
    d = json.loads(path.read_text())
    pairs = d["pairs"] if isinstance(d, dict) else d
    out = []
    for x in pairs:
        m = x.get("measured") or {}
        b, a = m.get("before") or {}, m.get("after") or {}
        if not (x.get("before", "").strip() and x.get("after", "").strip() and b.get("Z") == 100.0 and a.get("Z") == 100.0
                and float(a.get("score_exact", -1)) >= float(b.get("score_exact", 0))):
            raise RuntimeError(f"{path.name}: pair {x.get('id')} is not a usable exemplar")
        out.append(x)
    return out


def exemplars_for(name: str, pairs: list[dict]) -> list[dict]:
    """The pairs shown on row `name`: every pair whose row is not `name` (a pair of the prompted row would hand the model a proof of it)."""
    return [x for x in pairs if x.get("name") != name]


# -------------------------------------------------------------------------------------------------------------------------------- prompts
SYSTEM_RW = ("You are an expert Lean 4 proof golfer. You rewrite verified proofs into the shortest and cheapest form the scorer rewards, "
             "keeping their mathematical approach. You answer by calling submit_proofs once.")

DIALECT = """THE SCORING DIALECT (the moves below are what the shortest verified proofs of hard rows share; each appears in a compiled exemplar below):
1. `unhygienic`: `:= by unhygienic` (or `unhygienic` at the head of ONE tactic block) makes Lean's auto-generated names accessible, so names
   need not be written: bare `intro` / `intros` / `repeat' intro`, `cases h` and `induction h` with no `with` arms, `rcases h` with no pattern.
   The new hypotheses are then named as Lean prints them without the dagger: `a✝` is `a`, `a✝¹` is `a_1`, `h✝` is `h`, induction hypotheses
   `a_ih` / `ih` (the goal map below shows the daggered names). `‹_›` or `‹T›` uses an anonymous hypothesis.
   Caution: a top-level `unhygienic` breaks every `rename_i` of the proof ("too many variable names provided"): drop those `rename_i`
   (use the auto names) or scope `unhygienic` to the one block that needs it.
2. Positional case handling: `rotate_left k` / `rotate_right`, `case'`, `next =>`, or one combinator over all goals, instead of named
   `case foo x y =>` arms and bullets.
3. Uniform closers: one `all_goals` / `any_goals` / `<;>` block for cases that look alike; `repeat' constructor` to split conjunctions,
   existentials and inductive goals, then `assumption'` / `all_goals assumption` / one `exact`; `first | A | B` inside a combinator.
4. Pre-shaping instead of destructuring: a `.imp` call with a lambda on the hypothesis (`Exists.imp`, `And.imp`), `.1` / `.2`
   projections instead of `obtain ⟨..⟩ := h`, `choose` or `choose_spec.1`.
5. `exists` with the witnesses instead of `use` / `refine ⟨.., ?_⟩` (it tries `trivial` on what remains); `rewrite` instead of `rw` when
   no `rfl` is needed; `apply_rfl`.
6. Fewer tokens is the main lever on these rows; a dialect move that costs heartbeats (for example a combinator that tries a closer on
   many goals) pays only when its token saving is worth more (see the exchange rate).
7. Elaboration cost: `simp only [..]` over `simp`, `exact` over `apply` when the term is known, `(h : T)` ascriptions only where
   unification is slow; a heartbeat lever is worth taking when it does not add tokens."""


def versions_of(row: dict) -> list[str]:
    from probe.verify_candidates import newest_first
    return list(newest_first(row["version_info"]))


def reference_heartbeats(name: str, hbs: dict) -> int | None:
    from scorer.score import local_reference_heartbeats
    return local_reference_heartbeats(name) or hbs.get(name)


def scoring_text(row: dict, hbs: dict) -> str:
    ref_t = int(row["proof_length"])
    ref_h = reference_heartbeats(row["name"], hbs)
    pins = versions_of(row)
    p_tok = 100.0 / (3 * ref_t)
    p_100hb = 100.0 * 100 / (3 * ref_h) if ref_h else None
    return (f"SCORING (one row): score = (L + H + Z) / 3 with L = 100 x (1 - tokens / {ref_t}) (Lean lexer tokens of the proof body after "
            f"`:=`), H = 100 x (1 - heartbeats / {ref_h}) (elaboration heartbeats of the declaration), Z = 100 x (share of the toolchains "
            f"{', '.join(pins)} on which it compiles; it must compile on all of them). Exchange rate: one token = {p_tok:.3f} points"
            + (f", 100 heartbeats = {p_100hb:.3f} points, so one token is worth {ref_h / ref_t:.1f} heartbeats" if p_100hb else "") + ".\n"
            + ("Toolchain note: `assumption'` is an unknown tactic on v4.26.0 (use `all_goals assumption` on this row).\n"
               if "v4.26.0" in pins else ""))


def exemplar_text(exs: list[dict]) -> str:
    out = ["EXEMPLARS (other theorems, not this one; each pair compiled and measured on every toolchain; the AFTER side is the dialect):"]
    for x in exs:
        m = x["measured"]; b, a = m["before"], m["after"]
        out.append(f"\n[{x['id']}] moves: {'; '.join(x['moves'])}\nBEFORE ({b['tokens']} tokens, {b['heartbeats']} heartbeats, score "
                   f"{b['score_exact']:.2f}):\n```lean\n{x['before'].strip()}\n```\nAFTER ({a['tokens']} tokens, {a['heartbeats']} heartbeats, "
                   f"score {a['score_exact']:.2f}):\n```lean\n{x['after'].strip()}\n```")
    return "\n".join(out) + "\n"


def goal_text(gm: dict | None) -> str:
    if not gm or not gm.get("steps"):
        return "GOAL MAP: (not available for this proof)\n"
    lines = ["GOAL MAP of the CURRENT PROOF (Lean's goal state before each step, keyed by the proof's line numbers, line 1 = the first "
             "line of the declaration; depth 2: also inside bullets / `=>` arms / `by` blocks):"]
    for s in gm["steps"]:
        lines.append(f"- line {s['line']} `{s['tactic'][:80]}` ({s.get('n_goals')} goal(s)):\n{s['goals']}")
    if gm.get("note"):
        lines.append(f"(note: {gm['note']})")
    return "\n".join(lines) + "\n"


def fmt(r: dict | None) -> str:
    if not r or not r.get("ok"):
        return "fails"
    return f"{r['tokens']} tokens, {r['heartbeats']} heartbeats, score {r['score_exact']:.2f}" + ("" if r.get("Z") == 100.0 else f" (Z {r.get('Z')})")


def token_rules() -> str:
    from harness.agent import TOKEN_RULES
    return TOKEN_RULES.strip()


def round_prompt(row: dict, hbs: dict, proof: str, reading: dict, gm: dict | None, exs: list[dict], rnd: int, results: list[dict] | None = None,
                 best: dict | None = None) -> str:
    parts = ["TASK: rewrite a verified Lean 4 proof into the scoring dialect, keeping its approach.\n\n" + scoring_text(row, hbs) + "\n"
             + token_rules() + "\n\n" + DIALECT + "\n\n",
             f"STATEMENT (copy it exactly):\n```lean\n{row['statement'].rstrip()}\n```\n\n"
             f"CURRENT PROOF ({fmt(reading)}; it compiles on every toolchain):\n```lean\n", proof.strip(), "\n```\n\n" + goal_text(gm) + "\n",
             exemplar_text(exs) + "\n"]
    if rnd == 1:
        parts.append(f"YOUR TASK: rewrite the CURRENT PROOF into the dialect. Keep its approach: the same key lemmas and the same "
                     f"induction / case structure (you may merge or reorder cases and replace closers). Write {K_CANDS} complete "
                     "declarations (the exact statement, `:=`, the proof), from conservative (a few safe dialect moves) to "
                     "aggressive (every move that may apply), each aimed at fewer tokens than the CURRENT PROOF without losing "
                     "on heartbeats more than the tokens are worth. No sorry, admit, native_decide, axioms, auxiliary "
                     "declarations, `set_option` or `open` outside the proof. Call submit_proofs ONCE with the "
                     f"{K_CANDS} declarations.\n")
        return "".join(parts)
    res = ["ROUND 1 RESULTS (every candidate measured on every toolchain):"]
    for r in results or []:
        m = r.get("reading") or {}
        res.append(f"- {r['label']} ({r['origin']}): " + (fmt(m) if m.get("ok") and m.get("Z") == 100.0
                                                         else f"fails: {(r.get('error_short') or m.get('error') or '?')[:240]}"))
    parts.append("\n".join(res) + "\n\n")
    if best and best.get("decl") and best["decl"].strip() != proof.strip():
        parts += [f"BEST SO FAR ({fmt(best['reading'])}):\n```lean\n", best["decl"].strip(), "\n```\n\n"]
    else:
        parts.append("BEST SO FAR: the CURRENT PROOF (no round-1 candidate beat it).\n\n")
    parts.append(f"YOUR TASK (round 2): write {K_CANDS} NEW complete declarations that score higher than BEST SO FAR. Push the "
                 "moves that worked further, combine them, and avoid what failed. Same approach, same rules (no sorry, admit, "
                 "native_decide, axioms, auxiliary declarations). Call submit_proofs ONCE.\n")
    return "".join(parts)


def repair_prompt(row: dict, proof: str, cand: dict) -> str:
    return ("A rewrite of a verified Lean 4 proof into a shorter dialect failed to compile. Fix it with the smallest change: keep "
            "its dialect moves where they can work and undo only the move that breaks. Return ONE complete declaration (the exact "
            "statement, `:=`, the proof) by calling submit_proofs once. No sorry, admit, native_decide or axioms.\n\n" + DIALECT + "\n\n"
            f"STATEMENT (copy it exactly):\n```lean\n{row['statement'].rstrip()}\n```\n\nORIGINAL VERIFIED PROOF (the same approach; "
            "it compiles):\n```lean\n" + proof.strip() + "\n```\n\nFAILING REWRITE:\n```lean\n" + cand["decl"].strip()
            + f"\n```\n\nCOMPILER ERROR ({cand.get('error_pin') or 'primary toolchain'}):\n{cand.get('error_full') or cand.get('error_short') or '?'}\n")


# ----------------------------------------------------------------------------------------------------------------------------- candidates
def sha16(p: str) -> str:
    return hashlib.sha256(p.strip().encode()).hexdigest()[:16]


def normalize(decl: str, statement: str) -> tuple[str | None, str | None]:
    """(declaration on the exact statement, None) or (None, why). A re-typed statement is replaced by the exact one."""
    from scorer.tokenize import split_declaration
    d = (decl or "").strip()
    d = re.sub(r"^```(?:lean4?)?\s*\n|\n```\s*$", "", d).strip()
    if not d:
        return None, "empty declaration"
    if split_declaration(d, statement) is not None:
        return d, None
    k = statement.count(":=")   # the proof after the (k+1)-th `:=`, k = the `:=` inside the statement itself
    pos = -2
    for _ in range(k + 1):
        pos = d.find(":=", pos + 2)
        if pos < 0:
            return None, "no `:=` after the statement in the declaration"
    body = d[pos + 2:].lstrip(" ")
    nd = statement.rstrip() + " :=" + ("" if body.startswith("\n") else " ") + body
    return (nd, None) if split_declaration(nd, statement) is not None else (None, "statement differs")


def features(decl: str) -> list[str]:
    f = []
    for k, rx in (("unhygienic", r"\bunhygienic\b"), ("rotate", r"\brotate_(left|right)\b"), ("repeat'", r"\brepeat'"),
                  ("assumption'", r"\bassumption'"), ("any_goals", r"\bany_goals\b"), ("all_goals", r"\ball_goals\b"),
                  ("imp", r"\.imp\b|Exists\.imp|And\.imp"), ("exists", r"(^|\s)exists\s")):
        if re.search(rx, decl, re.M):
            f.append(k)
    return f


def jaccard(a: str, b: str) -> float:
    from scorer.tokenize import tokens as lex
    try:
        sa, sb = set(lex(a)), set(lex(b))
    except Exception:  # noqa: BLE001
        sa, sb = set(a.split()), set(b.split())
    return len(sa & sb) / max(1, len(sa | sb))


def is_verified(rd: dict | None) -> bool:
    return bool(rd and rd.get("ok") and rd.get("heartbeats") is not None and rd.get("Z") == 100.0 and isinstance(rd.get("score_exact"), (int, float))
                and math.isfinite(float(rd["score_exact"])))


def measure_full(meter, decl: str, timeout: float | None = None) -> tuple[dict, dict]:
    """(reading as endstage.Meter.measure gives it, {"pin", "errors"} of the first failing pin or {}). The same compiles as
    meter.measure(full=True); a meter without the internals (tests) is asked through measure()."""
    decl = decl.strip()
    if not all(hasattr(meter, a) for a in ("freeze", "_check", "_one", "_reading", "versions")):
        rd = meter.measure(decl, full=True, timeout=timeout)
        fail = {} if is_verified(rd) else {"pin": None, "errors": [rd.get("error") or "?"]}
        return rd, fail
    path = meter.freeze()
    bad = meter._check(decl)
    if bad:
        return {"ok": False, "error": bad, "compiles": 0, "meter": path}, {"pin": None, "errors": [bad]}
    n0 = meter.compiles
    meter._cand_timeout = timeout
    fail: dict = {}
    try:
        prim, _ = meter._one(decl, meter.versions[0], True, path)
        compat = None
        if not (prim.ok and prim.heartbeats is not None):
            fail = {"pin": meter.versions[0], "errors": list(prim.errors or [])}
        else:
            compat = {meter.versions[0]: True}
            for v in meter.versions[1:]:
                r, _ = meter._one(decl, v, False, path)
                compat[v] = bool(r.ok)
                if not r.ok and not fail:
                    fail = {"pin": v, "errors": list(r.errors or [])}
    finally:
        meter._cand_timeout = None
    return meter._reading(decl, prim, compat, None, path, meter.compiles - n0), fail


def repair_error(name: str, decl: str, fail: dict, primary: str, timeout: float = 900):
    """(text, fault): the exact compiler error for the repair prompt: on the primary pin, the declaration recompiled through
    harness/mine.lean_run (lines relative to the declaration, every message in full, at most `timeout` s); on another pin, that pin's
    errors as the meter returned them. fault: why the recompile was not used (an exception's type and text, e.g. a missing module), so
    the step records it instead of hiding it; None when it was used or not needed."""
    lines = decl.split("\n")
    if fail.get("pin") is None:   # statement / forbidden: no compile
        return "\n".join(fail.get("errors") or []) or "(no error message)", None
    if fail.get("pin") == primary:
        try:
            from harness.mine import lean_run
            with _LEAN_SEM:
                msgs = lean_run(name, decl, timeout=int(max(30, min(900, timeout))))
            out = []
            for x in [x for x in msgs if x.get("severity") == "error"][:3]:
                ln = int(x.get("line") or 0)
                src = lines[ln - 1].strip() if 1 <= ln <= len(lines) else ""
                out.append(f"line {ln}" + (f" (`{src[:120]}`)" if src else "") + f": {str(x.get('data'))[:1800]}")
            if out:
                return "\n\n".join(out), None
            fault = None   # no error message from the recompile (a timeout, a heartbeat limit): the meter's own text
        except Exception as e:  # noqa: BLE001  (the meter's own message then; the fault is recorded, a missing module named)
            fault = f"{type(e).__name__}: {str(e)[:200]}"
    else:
        fault = None
    return "\n\n".join(str(e)[:1800] for e in (fail.get("errors") or [])[:3]) or "(no error message)", fault


def goal_map(name: str, decl: str, total: int = 8000) -> dict:
    """The depth-2 goal map of a proof (harness/goals), depth 1 when Lean asks for it; {} on any failure ($0, informational)."""
    try:
        from harness import goals as GO
        with _LEAN_SEM:
            gm = GO.goal_map(name, decl, depth=2, total=total)
            if not gm.get("steps") and gm.get("ok") is False and "Retry with depth 1" in (gm.get("note") or ""):
                gm = GO.goal_map(name, decl, depth=1, total=total)
        return gm if isinstance(gm, dict) else {}
    except Exception as e:  # noqa: BLE001  (informational, $0: the step records and logs the fault, the prompt says "not available")
        return {"ok": False, "note": f"goal map unavailable ({type(e).__name__}: {str(e)[:160]})"}


# ----------------------------------------------------------------------------------------------------------------------------- the model
def _block(b):
    """A reply content block as JSON (llm/openai_compat blocks are dataclasses; other clients' may be pydantic)."""
    import dataclasses
    if dataclasses.is_dataclass(b):
        return {k: v for k, v in dataclasses.asdict(b).items() if v is not None}
    return b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else str(b)


class WallCap(Exception):
    """The step's wall cap: the router abandoned the step (its gate is closed), so no new call is sent."""


class CallGate:
    """The router's handle on the step's calls (made before the worker starts): enter() before a call is sent (refused once closed),
    leave() after it is booked; close() refuses every later call and says whether one is in flight (its cost then unknown)."""

    def __init__(self):
        self.lk = threading.Lock()
        self.closed = False
        self.inflight = 0

    def enter(self) -> None:
        with self.lk:
            if self.closed:
                raise WallCap("the step's wall cap was reached: no new call")
            self.inflight += 1

    def leave(self) -> None:
        with self.lk:
            self.inflight -= 1

    def close(self) -> bool:
        with self.lk:
            self.closed = True
            return self.inflight > 0


class Caller:
    """The step's paid calls through harness.review.PricedCaller (kind "style_rw"): one budget for the row, every call gated at its worst
    case at the cap prices, failed attempts charged once. spent_cap() / spent_list() are what the row is booked."""

    def __init__(self, name: str, preset: str, effort: str, budget_usd: float, cap_price: str, log, caller_cls=None,
                 gate: CallGate | None = None, trajectory: Path | str | None = None):
        from harness.review import PricedCaller
        from harness.architect import SUBMIT
        cls = caller_cls or PricedCaller
        self.pc = cls(name, preset, effort, MAX_TOKENS["round"], budget_usd, log, system=SYSTEM_RW, tools=SUBMIT, kind=TAG, cap_price=cap_price)
        self.name, self.log, self.budget = name, log, float(budget_usd)
        self.preset, self.effort = preset, effort
        self.gate = gate or CallGate()
        self.trajectory = Path(trajectory) if trajectory else None   # the full per-call trajectory: prompt, reply, usage
        self.calls: list[dict] = []
        self._cap = 0.0; self._list = 0.0
        self.stopped: str | None = None

    def _trace(self, rec: dict) -> None:
        if self.trajectory is None:
            return
        try:   # a trace never fails the step
            self.trajectory.parent.mkdir(parents=True, exist_ok=True)
            with _LOCK, self.trajectory.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass

    def spent_cap(self) -> float:
        return self._cap + float(self.pc.charged_cap[0])

    def spent_list(self) -> float:
        return self._list + float(self.pc.charged[0])

    def call(self, kind: str, prompt: str) -> list[dict]:
        """The submitted proofs of one call ([] on a skip, a refusal, a junk answer). Raises on a confirmed pin / exhausted retries (the
        charged worst cases are kept by the PricedCaller)."""
        self.gate.enter()   # raises WallCap once the router abandoned the step: no call is sent after the wall cap
        try:
            return self._call(kind, prompt)
        finally:
            self.gate.leave()   # after the call's spend is booked in this object (the router reads it only when nothing is in flight)

    def _call(self, kind: str, prompt: str) -> list[dict]:
        self.pc.max_tokens = MAX_TOKENS["round" if kind != "repair" else "repair"]
        msgs = [{"role": "user", "content": prompt}]
        rec = {"kind": kind, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "chars": len(prompt)}
        tr = {"t": rec["at"], "row": self.name, "kind": kind, "model": self.preset, "effort": self.effort, "system": SYSTEM_RW, "prompt": prompt}
        t0 = time.time()
        try:
            out = self.pc.call_retry(msgs, self.spent_cap())
        except Exception as e:  # noqa: BLE001
            rec.update(error=f"{type(e).__name__}: {str(e)[:300]}", seconds=round(time.time() - t0, 1), charged_cap=round(self.spent_cap(), 6))
            self.calls.append(rec)
            self._trace(dict(tr, error=rec["error"], seconds=rec["seconds"], charged_usd=round(self.spent_list(), 6)))
            raise
        m, sub, meta = out
        if m is None:
            rec.update(skipped=(meta or {}).get("skipped"), seconds=round(time.time() - t0, 1))
            self.calls.append(rec)
            self.stopped = "budget"
            self._trace(dict(tr, skipped=rec["skipped"]))
            return []
        c_list, c_cap = self.pc.metered(m), self.pc.cap_metered(m)
        self._list += c_list; self._cap += c_cap
        self.pc.trace(m, meta)
        u = m.usage
        rec.update(usd=round(c_list, 6), usd_cap=round(c_cap, 6), input=u.input_tokens, output=u.output_tokens, cached=getattr(u, "cache_read", None),
                   cost_reported=u.cost, stop=m.stop_reason, max_tokens=(meta or {}).get("max_tokens"), n_proofs=len(sub or []),
                   seconds=round(time.time() - t0, 1))
        self.calls.append(rec)
        self._trace(dict(tr, reply=[_block(b) for b in (m.content or [])],
                         stop=m.stop_reason, usage={k: rec.get(k) for k in ("input", "output", "cached", "cost_reported", "max_tokens")},
                         metered_usd=rec["usd"], cap_usd=rec["usd_cap"], seconds=rec["seconds"], n_proofs=rec["n_proofs"]))
        self.log(f"{TAG} {kind}: {len(sub or [])} proof(s), ${c_cap:.4f} (row ${self.spent_cap():.4f} of ${self.budget:.4f})"
                 + (f", stop {m.stop_reason}" if m.stop_reason not in ("tool_use", "stop", "end_turn") else ""))
        return list(sub or [])


# ------------------------------------------------------------------------------------------------------------------------------ the step
def budget_for(cap: float, cap_spend: float, usd: float, margin: float) -> float:
    """min(--style-rw-usd, cap - the row's spend at the cap price - margin), rounded DOWN to 1e-4, never below 0."""
    room = max(0.0, math.floor((float(cap) - float(cap_spend) - float(margin)) * 1e4) / 1e4)
    return max(0.0, math.floor(min(float(usd), room) * 1e4) / 1e4)


def other_units(name: str, incumbent: str, cands: list[dict], k: int) -> list[dict]:
    """Up to k other verified candidates (collect() entries with a stored score), unlike the incumbent (token Jaccard < UNIT_JACCARD) and
    within UNIT_MARGIN of the best stored score among them, best first, distinct from each other by the same rule."""
    out: list[dict] = []
    inc_s = None
    pool = []
    for c in cands or []:
        p = (c.get("proof") or "").strip()
        s = c.get("score")
        if not p or not isinstance(s, (int, float)) or not math.isfinite(float(s)):
            continue
        if p == incumbent.strip():
            inc_s = max(inc_s or -1e9, float(s)); continue
        pool.append((float(s), p, c))
    pool.sort(key=lambda t: -t[0])
    top = inc_s if inc_s is not None else (pool[0][0] if pool else None)
    for s, p, c in pool:
        if len(out) >= k:
            break
        if top is not None and s < top - UNIT_MARGIN:
            break
        if jaccard(p, incumbent) >= UNIT_JACCARD or any(jaccard(p, o["proof"]) >= UNIT_JACCARD for o in out):
            continue
        out.append({"proof": p, "score": s, "origins": list(c.get("origins") or [])[:4]})
    return out


class Step:
    """One row's style_rw step. Everything Lean or model is reachable through attributes so tests replace them: `caller` (a Caller), `meter`
    (an endstage.Meter-like object), `audit(name, proof) -> (status, why)`, `polish(proof_item, stop_at) -> result dict` (the $0 end stage,
    stopped at the absolute time stop_at). `deadline` (absolute, `clock` time; None: no wall cap): the step's hard wall cap (module
    docstring, "wall"); every part works to it."""

    def __init__(self, name: str, row: dict, hbs: dict, incumbent: dict, exs: list[dict], caller: Caller, meter, audit, polish, log,
                 units: list[dict] | None = None, clock=time.time, deadline: float | None = None):
        self.name, self.row, self.hbs, self.cur, self.exs = name, row, hbs, incumbent, exs
        self.caller, self.meter, self.audit, self.polish, self.log, self.clock = caller, meter, audit, polish, log, clock
        self.units = [{"proof": incumbent["proof"].strip(), "role": "incumbent"}] + [dict(u, role="other") for u in (units or [])]
        self.primary = versions_of(row)[0]
        self.cands: list[dict] = []
        self.cache: dict = {}
        self.t0 = clock()
        self.deadline = deadline
        self.read_s = 0.0   # the incumbent's full read on this meter (seconds): what the audit and the confirm read are reserved by
        self.rep: dict = {"units": [], "calls": 0, "cands": 0, "compiled": 0, "stopped": None}

    def rlog(self, m: str) -> None:
        self.log(f"{self.name[:40]}: {TAG}: {m}")

    def left(self) -> float:
        """Seconds to the step's wall cap (inf without one)."""
        return math.inf if self.deadline is None else self.deadline - self.clock()

    def post_reserve(self) -> float:
        """What the audit and the confirm read after the polish are reserved (POST_READS full reads of the incumbent, >= POST_MIN_S)."""
        return max(POST_MIN_S, POST_READS * float(self.read_s or 0.0))

    def time_left(self) -> bool:
        """A new call may start: the backstop since the step's start and CALL_MIN_LEFT_S before the wall cap."""
        if self.left() < CALL_MIN_LEFT_S:
            self.rep["wall_stop"] = f"no new call: {max(0.0, self.left()):.0f} s left before the wall cap (a call needs {CALL_MIN_LEFT_S:g} s)"
            return False
        return (self.clock() - self.t0) < BACKSTOP_S

    def _stop(self, urec: dict) -> None:
        why = "wall" if self.left() < CALL_MIN_LEFT_S else "backstop"
        urec["status"] = why; self.rep["stopped"] = why

    def measure_cands(self, sub: list, origin: str, timeout: float) -> list[dict]:
        out = []
        for i, s in enumerate(sub[:K_CANDS]):
            d0 = s.get("declaration") if isinstance(s, dict) else None
            decl, why = normalize(d0 or "", self.row["statement"])
            c = {"label": (s.get("label") if isinstance(s, dict) else None) or f"c{i}", "origin": origin, "raw_chars": len(d0 or ""),
                 "unit": getattr(self, "unit_sha", None)}
            if decl is None:
                c.update(decl=None, reading={"ok": False, "error": why}, error_short=why, error_full=why)
                out.append(c); continue
            k = sha16(decl)
            hit = self.cache.get(k)
            room = self.left() - self.post_reserve()   # a compile never eats the audit's and the confirm read's time
            if hit is None and room < MEASURE_MIN_S:
                why = f"not measured: {max(0.0, room):.0f} s left before the wall cap's reserve"
                c.update(decl=decl, sha=k, reading={"ok": False, "error": why}, error_short=why, error_full=why, features=features(decl))
                self.rep["wall_stop"] = why
                out.append(c); continue
            if hit is None:
                rd, fail = measure_full(self.meter, decl, timeout=min(timeout, room))
                rd = {kk: rd.get(kk) for kk in ("ok", "tokens", "heartbeats", "Z", "L", "H", "score_exact", "compat", "error", "timed_out", "meter", "compiles")}
                hit = {"reading": rd, "fail": fail}
                self.cache[k] = hit
            c.update(decl=decl, sha=k, reading=hit["reading"], features=features(decl))
            if not is_verified(hit["reading"]):
                f = hit["fail"] or {"pin": None, "errors": [hit["reading"].get("error") or "?"]}
                if "error_full" not in hit:
                    r = repair_error(self.name, decl, f, self.primary, timeout=max(30.0, min(900.0, self.left() - self.post_reserve())))
                    hit["error_full"], fault = r if isinstance(r, tuple) else (r, None)
                    if fault:   # recorded and logged, never hidden (the repair prompt then carries the meter's own error text)
                        self.rep.setdefault("helper_faults", []).append(f"repair error: {fault}")
                        self.rlog(f"repair error recompile not used ({fault})")
                c.update(error_pin=f.get("pin"), error_full=hit["error_full"], error_short=(hit["error_full"] or "")[:300])
            else:
                self.rep["compiled"] += 1
            out.append(c)
            self.rlog(f"{origin} {c['label']}: {fmt(c['reading'])} {c.get('features')}")
        self.rep["cands"] += len(out)
        return out

    def best_of(self, cands: list[dict]) -> dict | None:
        ok = [c for c in cands if c.get("decl") and is_verified(c["reading"])]
        return max(ok, key=lambda c: c["reading"]["score_exact"]) if ok else None

    def run_unit(self, u: dict, reading: dict) -> dict:
        """r1, repairs, r2, repairs on one unit; returns its record. Stops (without raising) when the budget or the clock is out."""
        urec = {"role": u["role"], "sha": sha16(u["proof"]), "reading": reading, "calls": 0, "status": "running"}
        self.unit_sha = urec["sha"]
        gm = goal_map(self.name, u["proof"])
        urec["goal_steps"] = len(gm.get("steps") or [])
        if not gm.get("steps") and gm.get("note"):
            urec["goal_note"] = str(gm["note"])[:200]
            if "unavailable" in str(gm["note"]):   # a helper fault (e.g. a missing module) is recorded and logged, never hidden
                self.rep.setdefault("helper_faults", []).append(f"goal map: {gm['note']}")
                self.rlog(f"goal map not available ({gm['note']})")
        timeout = max(180.0, 8.0 * float(reading.get("seconds") or 30.0))
        results: list = []; best = None
        for rnd in (1, 2):
            if not self.time_left():
                self._stop(urec); break
            prompt = round_prompt(self.row, self.hbs, u["proof"], reading, gm, self.exs, rnd, results=results, best=best)
            sub = self.caller.call(f"r{rnd}", prompt); urec["calls"] += 1; self.rep["calls"] += 1
            if self.caller.stopped:
                urec["status"] = "budget"; self.rep["stopped"] = "budget"; break
            cs = self.measure_cands(sub, f"r{rnd}", timeout)
            self.cands += cs
            fails = [c for c in cs if c.get("decl") and not is_verified(c["reading"]) and not str(c["reading"].get("error") or "").startswith("not measured")]
            for c in fails[:MAX_REPAIRS]:
                if not self.time_left():
                    self._stop(urec); break
                rsub = self.caller.call("repair", repair_prompt(self.row, u["proof"], c)); urec["calls"] += 1; self.rep["calls"] += 1
                if self.caller.stopped:
                    urec["status"] = "budget"; self.rep["stopped"] = "budget"; break
                self.cands += self.measure_cands(rsub[:1], f"r{rnd}-repair-{c['label']}", timeout)
            if self.rep["stopped"]:
                break
            results = [c for c in self.cands if c["origin"].startswith(f"r{rnd}") and c.get("unit") == urec["sha"]]
            b = self.best_of(self.cands)
            if b and b["reading"]["score_exact"] > float(reading.get("score_exact") or -1e9):
                best = b
        else:
            urec["status"] = "done"
        return urec

    def run(self) -> dict:
        """Returns the step's report with "candidate" (the best verified candidate after the polish, or None); never raises on a model
        error (recorded in "error"; what was charged stays in the caller)."""
        rep = self.rep
        try:
            for i, u in enumerate(self.units):
                if i > 0 and (self.caller.stopped or not self.time_left()):
                    break
                t_read = self.clock()
                rd, _fail = measure_full(self.meter, u["proof"])   # the incumbent too: its exact reading on this meter heads the prompt
                if u["role"] == "incumbent":
                    self.read_s = max(0.0, self.clock() - t_read)
                    rep["incumbent_read_s"] = round(self.read_s, 1)
                if not is_verified(rd):
                    rep["units"].append({"role": u["role"], "sha": sha16(u["proof"]), "status": "unit does not read on the meter", "reading": rd})
                    if u["role"] == "incumbent":
                        rep["status"] = "the incumbent does not read on the meter: no call"
                        return rep
                    continue
                if u["role"] == "incumbent":
                    rep["incumbent_reading"] = {k: rd.get(k) for k in ("tokens", "heartbeats", "score_exact", "Z", "meter")}
                rep["units"].append(self.run_unit(u, rd))
        except Exception as e:  # noqa: BLE001  (a model error after its retries, a confirmed pin, the wall cap's closed gate): the candidates so far are kept
            rep["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            rep["stopped"] = "wall" if isinstance(e, WallCap) else "error"
            if getattr(e, "pin_confirmed", False):
                rep["pin_unservable"] = str(e)[:300]
            self.rlog(f"stopped on {rep['error']}")
        rep["calls"] = sum(1 for c in self.caller.calls if "skipped" not in c)   # calls sent (a skip at the gate is not a call)
        if rep["calls"] == 0 and self.caller.stopped == "budget" and not rep.get("status"):
            rep["status"] = f"skipped at the gate: no call fits the ${self.caller.budget:.4f} budget ($0)"
        rep["spent"] = round(self.caller.spent_list(), 6); rep["spent_cap"] = round(self.caller.spent_cap(), 6)
        rep["call_records"] = list(self.caller.calls)
        rep["candidates"] = [{k: c.get(k) for k in ("label", "origin", "sha", "features", "error_short")} | {"reading": c.get("reading")} for c in self.cands]
        rep["candidate"] = self.select()
        return rep

    def select(self) -> dict | None:
        """The best verified candidate: the axiom audit, then the $0 polish when within POLISH_MARGIN of the incumbent (stopped at the wall
        cap minus the audit and confirm reserve; skipped when less than POLISH_MIN_S would be left); None when nothing verified beats the
        audit, when nothing differs from the incumbent, or when the wall cap leaves no time for the audit and the confirm read."""
        rep = self.rep
        inc = (self.rep.get("incumbent_reading") or {}).get("score_exact")
        ok = [c for c in self.cands if c.get("decl") and is_verified(c["reading"]) and c["decl"].strip() != self.cur["proof"].strip()]
        ok.sort(key=lambda c: -c["reading"]["score_exact"])
        for c in ok[:3]:   # the best candidate whose audit is clean (a sorry-dependent one is skipped, the next tried)
            if self.left() < self.post_reserve():
                rep["wall_stop"] = (f"no candidate taken: {max(0.0, self.left()):.0f} s left, the audit and the confirm read need "
                                    f"{self.post_reserve():.0f} s before the wall cap")
                self.rlog(rep["wall_stop"])
                return None
            try:
                st, why = self.audit(self.name, c["decl"])
            except Exception as e:  # noqa: BLE001
                st, why = "unknown", f"audit raised {type(e).__name__}: {str(e)[:120]}"
            c["audit"] = {"status": st, "why": why}
            if st not in ("clean", "skipped"):
                self.rlog(f"candidate {c['label']} rejected by the axiom audit: {st}: {why[:160]}"); continue
            best = {"proof": c["decl"], "reading": c["reading"], "label": c["label"], "origin": c["origin"], "audit": c["audit"], "polished": False}
            if inc is not None and c["reading"]["score_exact"] < float(inc) - POLISH_MARGIN:
                rep["polish"] = {"status": f"skipped: best raw {c['reading']['score_exact']:.3f} is more than {POLISH_MARGIN} below the incumbent"}
                return best
            stop_at = None if self.deadline is None else self.deadline - self.post_reserve()
            if stop_at is not None and stop_at - self.clock() < POLISH_MIN_S:
                rep["polish"] = {"status": f"skipped: {max(0.0, stop_at - self.clock()):.0f} s before the wall cap's reserve (< {POLISH_MIN_S:g} s)"}
                return best
            try:
                pr = self.polish({"proof": c["decl"], **{k: c["reading"].get(k) for k in ("tokens", "heartbeats", "Z", "L", "H", "compat")},
                                  "score": c["reading"]["score_exact"], "score_exact": c["reading"]["score_exact"], "stage": TAG, "verified": True},
                                 stop_at)
            except Exception as e:  # noqa: BLE001
                pr = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            rep["polish"] = {k: pr.get(k) for k in ("stage", "compiles", "error", "meter")}
            if stop_at is not None:
                rep["polish"]["stop_at_s"] = round(stop_at - self.t0, 1)
            m = pr.get("metrics") if isinstance(pr.get("metrics"), dict) else pr
            pp = (pr.get("proof") or "").strip()
            verified = bool(pr["verified"]) if "verified" in pr else pr.get("stage") not in (None, "unmeasured")
            # endstage.end_stage's metrics carry score_exact / tokens / heartbeats / Z / compat / meter and no "ok": a verified result is
            # one the end stage measured (its stage is not "unmeasured") with every pin passing (Z 100)
            m = dict(m, ok=bool(m.get("ok", verified)))
            rep["polish"]["score_exact"] = m.get("score_exact")
            if pp and verified and is_verified(m) and pp != self.cur["proof"].strip() and float(m["score_exact"]) >= float(c["reading"]["score_exact"]):
                nd, why = normalize(pp, self.row["statement"])
                if nd is not None:
                    try:
                        st2, why2 = self.audit(self.name, nd)
                    except Exception as e:  # noqa: BLE001
                        st2, why2 = "unknown", f"audit raised {type(e).__name__}"
                    if st2 in ("clean", "skipped"):
                        best = {"proof": nd, "reading": {k: m.get(k) for k in ("ok", "tokens", "heartbeats", "Z", "L", "H", "score_exact", "compat", "meter")},
                                "label": c["label"], "origin": c["origin"] + "+polish", "audit": {"status": st2, "why": why2}, "polished": True,
                                "polish_stage": pr.get("stage")}
                        rep["polish"]["gain"] = round(float(m["score_exact"]) - float(c["reading"]["score_exact"]), 4)
                    else:
                        rep["polish"]["rejected"] = f"audit {st2}: {why2[:120]}"
                else:
                    rep["polish"]["rejected"] = "the polished text does not splice onto the statement"
            elif pp == self.cur["proof"].strip():
                rep["polish"]["rejected"] = "the polish returned the incumbent's text"
            elif not (pp and verified and is_verified(m)):
                rep["polish"]["rejected"] = "the polish result is not verified on every pin"
            elif float(m["score_exact"]) < float(c["reading"]["score_exact"]):
                rep["polish"]["rejected"] = "the polish result reads below the raw candidate"
            return best
        return None


def confirm(meter, incumbent: str, candidate: str, log=None) -> dict:
    """The single confirm read: the incumbent and the candidate back to back on the meter, every pin. ok = the candidate reads (Z 100, no
    lower Z than the incumbent) and its exact score is >= the incumbent's + MIN_GAIN; when the incumbent does not read, ok is False (the
    final stays byte-identical: a step whose meter cannot read the incumbent accepts nothing)."""
    a = meter.measure(incumbent.strip(), full=True)
    b = meter.measure(candidate.strip(), full=True)
    rd = lambda m: {k: m.get(k) for k in ("ok", "tokens", "heartbeats", "Z", "L", "H", "score_exact", "compat", "meter", "error")}  # noqa: E731
    out = {"incumbent": rd(a), "candidate": rd(b), "compiles": int(a.get("compiles") or 0) + int(b.get("compiles") or 0), "bar": MIN_GAIN}
    if not is_verified(b):
        out.update(ok=False, why="the candidate does not read on the confirm read (every pin)", delta=None)
    elif not is_verified(a):
        out.update(ok=False, why="the incumbent does not read on the confirm read: nothing is accepted", delta=None)
    else:
        d = float(b["score_exact"]) - float(a["score_exact"])
        out.update(ok=float(b["Z"]) >= float(a["Z"]) - 1e-9 and d >= MIN_GAIN - 1e-9, delta=round(d, 6),
                   why=f"confirm read: candidate {float(b['score_exact']):.4f} vs incumbent {float(a['score_exact']):.4f} (bar +{MIN_GAIN:g})")
    return out


PREFLIGHT_MODULES = ("harness.review", "harness.architect", "harness.agent", "harness.endstage", "harness.final_writer", "harness.goals",
                     "harness.mine", "harness.workbench", "harness.batch_screen", "probe.verify_candidates", "scorer.score", "scorer.tokenize",
                     "scorer.forbidden", "llm.openai_compat")
PREFLIGHT_TOP = ("mine",)   # harness/goals.py imports `from mine import ...` (harness/ on sys.path, as the router puts it)


def preflight() -> str | None:
    """Before any spend (router.style_rw_args_check): every module the step imports lazily resolves in this checkout (a package missing a
    file fails here, at the start, not as a silently degraded step in the middle of the final), and the exemplar file is present. Returns
    the refusal text, else None."""
    import importlib.util
    missing = []
    for m in PREFLIGHT_MODULES + PREFLIGHT_TOP:
        try:
            if importlib.util.find_spec(m) is None:
                missing.append(m)
        except (ImportError, ValueError) as e:
            missing.append(f"{m} ({type(e).__name__})")
    if not EXEMPLARS_PATH.is_file():
        missing.append(str(EXEMPLARS_PATH.relative_to(ROOT)))
    return f"--style-rw on: missing in this checkout: {', '.join(missing)}" if missing else None


def force_warn_sorry() -> bool:
    """The sorry guard for every compile of the step (b71 R1): set in this process when the environment lacks it. Returns whether it was
    already on."""
    on = os.environ.get("LRA_FORCE_WARN_SORRY") == "1"
    if not on:
        os.environ["LRA_FORCE_WARN_SORRY"] = "1"
    return on
