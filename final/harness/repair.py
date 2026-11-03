#!/usr/bin/env python3
"""REPAIR route (b63 item 16; docs/adaptive_plan_93.md §1.1 P, §1.4): a paid edit loop fed ONLY compiled artifacts.

Input (harness/artifacts.py, from the C1 pass / the sessions): a compiled skeleton with <= REPAIR_MAX_HOLES `sorry` holes and their goal
states, or >= 2 near-misses (a full candidate + its first error + <= 3 open goals), plus the row's current best (compiling, measured).
The model (Argon medium through the review client: harness/review.PricedCaller = the same pricing, retries and ledger as the review step)
sees the best, the artifact and every earlier step's measured outcomes, and submits up to k edits per step, each either
  {find, replace} on a named target ("best", "artifact", "near_miss:<k>"; find = an exact substring, copied verbatim) or
  {hole_id, fill}   (the artifact's hole_id-th `sorry`, in text order, replaced by `fill`).
Each edit is applied alone and read on the row's evaluator (a skeleton that still has holes elaborates through goals.skeleton_check and
counts as progress when it loses a hole without a real error; a full candidate compiles on the primary pin), the paying ones are stacked
greedily (largest gain first, each kept only while the stack still pays), a full candidate that beats the incumbent passes scorer/accept.decide
on the primary reading, then an all-pin confirmation with a paired incumbent re-read, then accept.decide again, and enters bank.jsonl with
source "repair:<step>" (harness/bank.py). <= max_steps steps, stop after dry_stop steps in a row without a bank or a hole filled, <= budget_usd
(each call priced at its worst case before it is sent). Logs (contract §2): shown.json (what was shown per step, the adoption counter =
edits on the shown artifact that were kept) and the per-step records the router writes to decisions.jsonl as kind REPAIR.
Compiles go through the evaluator (scorer memgate): run in a memory-capped unit, never from an interactive shell. No model call is made
without a budget; the fake model of the tests injects harness.architect.call.
"""
from __future__ import annotations

import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(1, str(ROOT / "harness"))
from harness import artifacts as AR  # noqa: E402
from harness import bank as BK  # noqa: E402
from harness import leantools as LT  # noqa: E402
from scorer.accept import decide as accept, exact_score  # noqa: E402
from scorer.score import len_pct, hb_pct_local  # noqa: E402
from scorer.tokenize import split_declaration, count_tokens  # noqa: E402

MAX_STEPS = 10
DRY_STOP = 2
STEP_BUDGET_MIN = 0.02      # a step whose cheapest call (REVIEW_MIN_TOKENS) cannot be paid is not started
MAX_TOKENS = 16000          # one call's output cap (as the review's REVIEW_MAX_TOKENS: ~$0.16 worst case on Argon)
K = 6                       # edits per step
MIN_GAIN = 0.05             # a full candidate pays alone above this (the review's bar); banks pass accept.decide (paired, exact)
REPAIR_SYSTEM = "You are an expert Lean 4 proof engineer repairing a compiled proof skeleton with exact text edits."
SUBMIT = [{"name": "submit_edits", "description": "Submit exact edits: hole fills of the artifact and/or find/replace edits of a named target.",
           "input_schema": {"type": "object", "properties": {"edits": {"type": "array", "items": {"type": "object", "properties": {
               "label": {"type": "string"},
               "target": {"type": "string", "description": "`best` (the current best proof), `artifact` (the skeleton) or `near_miss:<k>`; default `artifact` for a hole fill, `best` for find/replace"},
               "hole_id": {"type": "integer", "description": "the artifact's hole to fill (1-based, in text order)"},
               "fill": {"type": "string", "description": "the text that replaces that `sorry` (a tactic block or a term, as the hole's position needs)"},
               "find": {"type": "string", "description": "an EXACT substring of the target (copy it verbatim, whitespace included)"},
               "replace": {"type": "string", "description": "its replacement"},
               "why": {"type": "string", "description": "one line"}},
               "required": ["label"]}}}, "required": ["edits"]}}]


def _ref(name: str) -> tuple[int, int | None]:
    row = LT.ROWS[name]
    hb = LT.HBS.get(name) if isinstance(LT.HBS, dict) else None
    return int(row["proof_length"]), hb


def reading_score(name: str, m: dict, Z: float) -> float:
    rl, rh = _ref(name)
    return exact_score(len_pct(rl, int(m["tokens"])), hb_pct_local(name, int(m["heartbeats"]), rh), float(Z))


def render_artifact(art: dict | None, near: list[dict], limit: int = 9000) -> str:
    """The artifact block: the skeleton with its holes' goals, or the near-misses with their first error and open goals. Text only."""
    lines = []
    if art:
        lines.append(f"ARTIFACT (a skeleton of this proof that elaborates with {len(art.get('holes') or [])} `sorry` hole(s); kind {art.get('kind')}; "
                     f"compiled by the harness, not a hint):\n```lean\n{art['text'].rstrip()}\n```")
        for h in art.get("holes") or []:
            lines.append(f"  hole {h['hole_id']} (line {h.get('line')}): ⊢ {h.get('goal') or '(goal not recorded)'}")
    for i, n in enumerate(near, 1):
        lines.append(f"NEAR-MISS {i} (a full candidate that does NOT compile; first error and open goals measured):\n```lean\n{n['text'].rstrip()}\n```\n"
                     f"  first error: {n.get('first_error') or '?'}" + ("".join(f"\n  open goal: {g}" for g in n.get("open_goals") or []) if n.get("open_goals") else ""))
    txt = "\n".join(lines)
    return txt if len(txt) <= limit else txt[:limit - 1].rsplit("\n", 1)[0] + "\n(cut)"


def prompt(name: str, best: dict, art: dict | None, near: list[dict], k: int, prior: list[str]) -> str:
    rl, rh = _ref(name)
    return (
        "You are repairing a Lean 4 proof. The harness holds a CURRENT BEST that compiles and a compiled ARTIFACT of the same theorem "
        "(a skeleton whose unfinished parts are `sorry` holes with their goals, or near-miss candidates with their measured first error). "
        "Your job: make the artifact compile with the fewest edits, or make an exact edit of the best; never rewrite from scratch.\n\n"
        "SCORE = mean of token reduction, heartbeat reduction and compatibility versus the reference proof; "
        f"reference {rl} tokens, {rh if rh else '?'} heartbeats" + (f" (one token ≈ {rh / rl:.0f} heartbeats in the score)" if rh else "") + ".\n\n"
        f"CURRENT BEST ({best.get('tokens')} tokens, {best.get('heartbeats')} heartbeats, score {best.get('score')}):\n```lean\n{(best.get('proof') or '').rstrip()}\n```\n\n"
        + render_artifact(art, near) + "\n\n"
        + ("EARLIER STEPS (measured; the artifact and best above already hold every edit that paid; do not resend these):\n" + "\n".join(prior[-30:]) + "\n\n" if prior else "")
        + f"TASK: call submit_edits ONCE with up to {k} independent edits, most promising first. A hole fill is {{hole_id, fill}} (the fill replaces "
        "that `sorry`; a tactic block or a term as the position needs; the goal shown is exactly what it must close). A find/replace edit is "
        "{target, find, replace} with `find` copied verbatim from the target. Each edit is applied alone, elaborated or compiled, and the winners "
        "are combined; a skeleton that loses a hole without an error is kept as the new artifact.")


def _apply(target_text: str, e: dict) -> tuple[str | None, str | None]:
    """(new text, error) for one edit on its target text."""
    if e.get("hole_id") is not None and e.get("fill") is not None:
        t = AR.fill_hole(target_text, int(e["hole_id"]), str(e["fill"]))
        return (t, None) if t is not None else (None, f"no hole {e['hole_id']} in the artifact")
    f, r = str(e.get("find") or ""), str(e.get("replace") or "")
    if not f:
        return None, "no find text and no hole fill"
    if f not in target_text:
        return None, "does not apply (find text not in the target)"
    if target_text.count(f) > 1:
        return None, "ambiguous (find text occurs more than once)"
    return target_text.replace(f, r, 1), None


def run_repair(name: str, best: dict, route: dict, model: str, effort: str, budget_usd: float, evaluator, log=print, *, max_steps: int = MAX_STEPS,
               dry_stop: int = DRY_STOP, max_tokens: int = MAX_TOKENS, k: int = K, state_path=None, run_id: str = "repair", skeleton_fn=None,
               shown_path=None, trajectory_path=None, cap_price: str = "announced") -> dict:
    """The loop. `best` = {proof, score, tokens, heartbeats, Z, compat}; `route` = artifacts.route_for() output (kind repair); `evaluator` =
    the router's evaluator (factory or bound: callable(text, full) -> reading). Returns {status, proof, item (the new best or None), steps,
    spend, shown, banked: n, holes_filled: n}. skeleton_fn(text) -> goals.skeleton_check-shaped dict (injectable). trajectory_path: one JSON
    line per call (the full prompt, the model's reply blocks, usage, metered $; rule: full per-message trajectories of every run).
    b64 L0: budget_usd is in cap-price dollars (agent.cap_prices, `cap_price` mode; review.PricedCaller): every step is gated on the slice's
    spend at the cap prices (cap_spend in the result), while `spend` stays the metered (list-table) spend."""
    from harness.review import PricedCaller
    row = LT.ROWS[name]; statement = row["statement"]; versions = LT.newest_first(row["version_info"])
    ev = (evaluator() if callable(evaluator) and not hasattr(evaluator, "bound") else evaluator)
    ev = ev.bound(name, versions) if hasattr(ev, "bound") else ev
    if skeleton_fn is None:
        from harness import goals as _goals
        skeleton_fn = lambda t: _goals.skeleton_check(name, t)   # noqa: E731
    art = dict(route.get("artifact")) if route.get("artifact") else None
    near = [dict(n) for n in route.get("near_misses") or []]
    cur = dict(best); cur_text = (cur.get("proof") or "").rstrip()
    Zc = float(cur.get("Z") if cur.get("Z") is not None else 100.0)
    out = {"problem": name, "model": model, "route": route.get("reason"), "steps": [], "spend": 0.0, "banked": 0, "holes_filled": 0, "item": None,
           "shown": [], "status": "no gain", "start": {k_: best.get(k_) for k_ in ("score", "tokens", "heartbeats", "Z")}}
    if not cur_text or cur.get("score") is None:
        out["status"] = "no measured best"; return out
    if art is None and len(near) < 1:
        out["status"] = "no artifact"; return out
    from harness.agent import MODEL_PRESETS
    if not str(model).startswith("codex:") and not (MODEL_PRESETS.get(model) or {}).get("prices"):
        # review 2026-10-25: PricedCaller gates a call only when the preset has a price table; an unpriced model's calls could not be
        # bounded by the slice (worst case = steps x 3 tries x the full output cap), so the paid route refuses it before any call
        out["status"] = f"refused: model {model} has no price table (the slice could not bound its calls)"; return out
    b0 = ev(cur_text, False)
    if not b0.get("ok") or b0.get("heartbeats") is None:
        out["status"] = "the best does not read on the evaluator"; return out
    inc = {"score": reading_score(name, b0, Zc), "tokens": int(b0["tokens"]), "heartbeats": int(b0["heartbeats"]), "Z": Zc}
    # one score scale (review 2026-10-25; postpass.improve_row's 2026-10-21 meter-mix rule): every gate compares readings of THIS run's
    # evaluator (inc = the last adopted reading, paired = its re-read); the result leaves on the caller's STORED scale = the stored score +
    # the same-meter gain (the router's fold / write-back and the G8 readout compare it with postpass outputs, which use that scale)
    stored0, inc0 = float(cur["score"]), inc["score"]
    shown_shas = {art["sha"]} if art else set()
    shown_shas |= {n["sha"] for n in near}
    adopted = 0
    prior: list[str] = []
    dry = 0; spent = 0.0; t0 = time.time()
    spent_cap = 0.0   # b64 L0: the gate's spend (cap prices); spent stays the reported spend
    for step in range(1, max_steps + 1):
        left = round(budget_usd - spent_cap, 4)
        if left < STEP_BUDGET_MIN:
            out["steps"].append({"step": step, "status": f"stopped: ${left:.3f} left"}); break
        pc = PricedCaller(name, model, effort, max_tokens, left, log, system=REPAIR_SYSTEM, tools=SUBMIT, kind="repair_call", cap_price=cap_price)
        msgs = [{"role": "user", "content": prompt(name, cur, art, near, k, prior)}]
        shown_rec = {"step": step, "artifact": art["sha"] if art else None, "holes": len(art["holes"]) if art else 0,
                     "near_misses": [n["sha"] for n in near], "best": BK.sha(cur_text), "at": AR.now()}
        out["shown"].append(shown_rec)
        rec = {"step": step, "edits": [], "banked": False, "holes_filled": 0, "spend": 0.0}
        try:
            m, _s, meta = pc.call_retry(msgs, 0.0)
        except Exception as e:  # noqa: BLE001  a call that failed for good after being billed: its charged worst case counts, the loop ends
            spent += pc.charged[0]; spent_cap += pc.charged_cap[0]
            rec.update(status=f"call failed: {type(e).__name__}: {str(e)[:120]}", spend=round(pc.charged[0], 4)); out["steps"].append(rec)
            log(f"{name[:30]} repair step {step}: call failed ({type(e).__name__}); ${pc.charged[0]:.3f} assumed"); break
        if m is None:
            rec.update(status=f"skipped: {(meta or {}).get('skipped')}"); out["steps"].append(rec); break
        pc.trace(m, meta)
        cost = pc.metered(m) + pc.charged[0]; spent += cost; rec["spend"] = round(cost, 4); rec["calls"] = pc.per_call
        spent_cap += pc.cap_metered(m) + pc.charged_cap[0]
        if trajectory_path:
            try:
                tp = Path(trajectory_path); tp.parent.mkdir(parents=True, exist_ok=True)
                with tp.open("a") as f_:
                    f_.write(json.dumps({"t": AR.now(), "run_id": run_id, "step": step, "system": REPAIR_SYSTEM, "prompt": msgs[0]["content"],
                                         "reply": [b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else str(b) for b in m.content],
                                         "stop": getattr(m, "stop_reason", None), "usage": (pc.per_call[-1] if pc.per_call else None),
                                         "metered_usd": round(cost, 6)}, ensure_ascii=False, default=str) + "\n")
            except OSError:
                pass   # a trace never fails the loop
        cs = [b for b in m.content if b.type == "tool_use" and b.name == "submit_edits"]
        edits = (((cs[0].input or {}).get("edits") or []) if cs else [])[:k]
        # ---- each edit alone
        singles = []       # (score, text, erec) full candidates that pay alone vs the incumbent
        fills = []         # (holes left, text, holes, erec) skeleton edits that still elaborate with fewer holes
        for e in edits:
            tgt = str(e.get("target") or ("artifact" if e.get("hole_id") is not None else "best"))
            erec = {"label": str(e.get("label") or "")[:60], "target": tgt, "hole_id": e.get("hole_id"), "find": str(e.get("find") or "")[:200],
                    "replace": str(e.get("replace") or "")[:200], "fill": str(e.get("fill") or "")[:300], "why": str(e.get("why") or "")[:160]}
            rec["edits"].append(erec)
            if tgt == "best":
                base_text = cur_text
            elif tgt == "artifact":
                base_text = art["text"] if art else None
            elif tgt.startswith("near_miss:"):
                try:
                    base_text = near[int(tgt.split(":", 1)[1]) - 1]["text"]
                except (ValueError, IndexError):
                    base_text = None
            else:
                base_text = None
            if base_text is None:
                erec["outcome"] = f"no such target {tgt}"; continue
            text, err = _apply(base_text, e)
            if text is None:
                erec["outcome"] = err; continue
            text = text.rstrip()
            if split_declaration(text, statement) is None:
                erec["outcome"] = "statement differs (the statement must stay byte-identical)"; continue
            if AR.holes_of(text):
                if tgt == "best":
                    erec["outcome"] = "a `sorry` in an edit of the best is not a candidate"; continue
                try:
                    sk = skeleton_fn(text)
                except Exception as ex:  # noqa: BLE001
                    erec["outcome"] = f"skeleton check failed: {type(ex).__name__}"; continue
                n_before = len(art["holes"]) if (art and tgt == "artifact") else len(AR.holes_of(base_text))
                hs = sk.get("holes") or AR.holes_of(text)
                if sk.get("errors"):
                    erec["outcome"] = "elaboration error: " + " | ".join(sk["errors"])[:300]; continue
                if len(hs) >= n_before:
                    erec["outcome"] = f"elaborates but no hole closed ({len(hs)} left)"; continue
                erec["outcome"] = f"elaborates with {len(hs)} hole(s) left (was {n_before})"
                fills.append((len(hs), text, hs, erec)); continue
            r = ev(text, False)
            if not r.get("ok") or r.get("heartbeats") is None:
                erec["outcome"] = "compile error: " + str(r.get("error") or " | ".join(r.get("errors") or []) or "?")[:300]
                if tgt != "best":   # a failed full fill is a new near-miss (shown next step in place of the oldest)
                    nm = AR.near_miss(text, erec["outcome"][15:], f"repair:{step}", technique=erec["label"] or None, parent=art["sha"] if art else None)
                    if all(nm["sha"] != x["sha"] for x in near):
                        near = (near + [nm])[-4:]
                continue
            sc = reading_score(name, r, Zc)
            cand = {"score": sc, "tokens": int(r["tokens"]), "heartbeats": int(r["heartbeats"]), "Z": Zc}
            erec.update(ok=True, tokens=cand["tokens"], heartbeats=cand["heartbeats"], score=round(sc, 4))
            if state_path:
                BK.add(Path(state_path).parent, BK.entry(text, f"repair:{step}", tokens=cand["tokens"], heartbeats=cand["heartbeats"], score=sc,
                                                            parent=BK.sha(base_text), run_id=run_id, statement=statement))
            ok, why = accept(inc, cand)
            if ok and sc > inc["score"] + MIN_GAIN:
                erec["outcome"] = f"pays alone: {inc['score']:.4f} -> {sc:.4f}"; singles.append((sc, text, erec))
            else:
                erec["outcome"] = f"compiles, no gain ({why})"
        # ---- greedy stack of the paying full candidates (largest gain first; each kept only while the stack still pays)
        stack_text, stack_sc = None, inc["score"]
        for sc, text, erec in sorted(singles, key=lambda x: -x[0]):
            if stack_text is None:
                stack_text, stack_sc = text, sc; erec["stacked"] = f"first ({sc:.4f})"; continue
            # re-apply this edit's find/replace on the stacked text where it still applies; a hole fill or near-miss repair is a whole text
            e = next((x for x in edits if str(x.get("label") or "")[:60] == erec["label"]), {})
            if e.get("find") and str(e["find"]) in stack_text and stack_text.count(str(e["find"])) == 1:
                t2 = stack_text.replace(str(e["find"]), str(e.get("replace") or ""), 1).rstrip()
                r2 = ev(t2, False)
                if r2.get("ok") and r2.get("heartbeats") is not None and reading_score(name, r2, Zc) > stack_sc + MIN_GAIN:
                    stack_text, stack_sc = t2, reading_score(name, r2, Zc); erec["stacked"] = f"kept ({stack_sc:.4f})"
                else:
                    erec["stacked"] = "dropped in the stack"
            else:
                erec["stacked"] = "skipped (a whole-text candidate; the best single is kept)"
        banked = False
        if stack_text is not None:
            full = ev(stack_text, True)
            if full.get("ok") and full.get("Z") is not None and full.get("heartbeats") is not None:
                Zf = float(full["Z"])
                cand = {"score": reading_score(name, full, Zf), "tokens": int(full["tokens"]), "heartbeats": int(full["heartbeats"]), "Z": Zf}
                i1 = ev(cur_text, False)   # paired incumbent re-read right after the confirmation
                paired = inc if not (i1.get("ok") and i1.get("heartbeats") is not None) else \
                    {"score": reading_score(name, i1, Zc), "tokens": int(i1["tokens"]), "heartbeats": int(i1["heartbeats"]), "Z": Zc}
                ok, why = accept(paired, cand)
                if ok and cand["score"] > max(inc["score"], paired["score"]) + MIN_GAIN:   # same meter only (was: max(stored score, paired))
                    gain = round(cand["score"] - paired["score"], 4)
                    cur = dict(cur, proof=stack_text + "\n", score=round(stored0 + (cand["score"] - inc0), 2), measured_score=cand["score"], tokens=cand["tokens"],
                               heartbeats=cand["heartbeats"], Z=Zf, compat=full.get("compat"), L=full.get("L"), H=full.get("H"), verified=True, stage="repair")
                    cur_text = stack_text; inc, Zc = cand, Zf
                    if state_path:
                        BK.add(Path(state_path).parent, BK.entry(stack_text, f"repair:{step}", tokens=cand["tokens"], heartbeats=cand["heartbeats"], Z=Zf,
                                                                    compat=full.get("compat"), score=cand["score"], parent=BK.sha(best.get("proof") or ""),
                                                                    run_id=run_id, statement=statement))
                    banked = True; out["banked"] += 1; out["item"] = cur
                    rec.update(banked=True, gain=gain, why=why)
                    if art and any(x[2].get("target") == "artifact" or x[2].get("hole_id") is not None for x in singles):
                        adopted += 1
                        rec["artifact"] = {"sha": art["sha"], "holes": 0, "consumed": True}; art = None   # the artifact is the best now
                else:
                    rec["confirm"] = f"all-pin confirmation did not pass: {why}"
            else:
                rec["confirm"] = "all-pin confirmation failed: " + str(full.get("error") or "?")[:160]
        # ---- hole fills: the fill that leaves the fewest holes becomes the artifact (stacked fills of different holes when they combine)
        if fills and art is not None:
            fills.sort(key=lambda x: x[0])
            n_left, text, hs, erec = fills[0]
            for n2, t2, hs2, erec2 in fills[1:]:
                e2 = next((x for x in edits if str(x.get("label") or "")[:60] == erec2["label"]), {})
                if e2.get("hole_id") is None or e2.get("fill") is None:
                    continue
                # the hole is re-located in the stacked skeleton by its goal text (hole numbers shift after a fill); no goal -> not stacked
                g2 = next((h.get("goal") for h in art["holes"] if h["hole_id"] == int(e2["hole_id"])), None)
                tgt_h = next((h for h in hs if g2 and h.get("goal") == g2), None)
                if tgt_h is None:
                    erec2["stacked"] = "not stacked (hole not re-located)"; continue
                t3 = AR.fill_hole(text, int(tgt_h["hole_id"]), str(e2["fill"]))
                if t3 is None:
                    continue
                try:
                    sk3 = skeleton_fn(t3)
                except Exception:  # noqa: BLE001
                    continue
                if not sk3.get("errors") and len(sk3.get("holes") or AR.holes_of(t3)) < len(hs):
                    text, hs = t3.rstrip(), sk3.get("holes") or AR.holes_of(t3); erec2["stacked"] = f"kept ({len(hs)} holes left)"
                else:
                    erec2["stacked"] = "dropped in the stack"
            filled = len(art["holes"]) - len(hs)
            art = AR.skeleton(text, hs, f"repair:{step}", kind=art.get("kind"), parent=art["sha"], tokens_est=count_tokens(split_declaration(text, statement) or ""),
                              structural=art.get("structural"))
            rec["holes_filled"] = filled; out["holes_filled"] += filled; adopted += 1
            rec["artifact"] = {"sha": art["sha"], "holes": len(hs)}
            shown_shas.add(art["sha"])
        for erec in rec["edits"]:
            prior.append(f"- step {step}: {erec['label']}: {erec.get('outcome', '')[:160]}" + (f"; {erec['stacked']}" if erec.get("stacked") else ""))
        progressed = banked or rec["holes_filled"] > 0
        dry = 0 if progressed else dry + 1
        rec["status"] = "banked" if banked else ("hole progress" if rec["holes_filled"] else "dry")
        out["steps"].append(rec)
        log(f"{name[:30]} repair step {step}: {len(edits)} edit(s), {rec['status']}, ${cost:.3f} (total ${spent:.3f}); best {cur.get('score')}"
            + (f", artifact {len(art['holes'])} hole(s)" if art else ""))
        if dry >= dry_stop:
            out["stop"] = f"{dry_stop} dry steps"; break
    out.update(spend=round(spent, 4), cap_spend=round(spent_cap, 4), proof=cur.get("proof") or best.get("proof"), seconds=round(time.time() - t0, 1), adopted=adopted,
               final={k_: cur.get(k_) for k_ in ("score", "tokens", "heartbeats", "Z")},
               artifact_final={"sha": art["sha"], "holes": len(art["holes"])} if art else None)
    out["status"] = "improved" if out["banked"] else ("hole progress" if out["holes_filled"] else "no gain")
    if shown_path:
        try:
            p = Path(shown_path); sj = json.loads(p.read_text()) if p.exists() else {"sessions": []}
            sj["sessions"].append({"run_id": run_id, "kind": "repair", "at": AR.now(), "shown": out["shown"], "adopted": adopted,
                                   "adopted_shas": sorted(shown_shas) if adopted else []})
            p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(sj, ensure_ascii=False, indent=1))
        except OSError:
            pass
    return out
