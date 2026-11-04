#!/usr/bin/env python3
"""Post-process improvement of a finals JSON (2026-10-16; a post-process that lifts a pipeline finals file toward the
best known proofs). Input and output are the pipeline's finals
format {problem: {proof, score, ...}}; every row ends at its best verified proof, never lower than its input, with the stage that found it.
Stages, in the order given by --stages (default free,rules,oracle: $0 computation only; polish and replan are opt-in model stages;
pool is reference-only and needs --allow-pool):
  free    the existing $0 chain (harness/autobrief.free_passes: normalize -> hb_rewrite -> preorder -> hb_polish -> lint_delete -> hb_tool),
          repeated to a fixpoint (--free-rounds); every pass is compile-gated on every toolchain by itself.
  rules   token-structural families (harness/gap_rules.py: bullet merge / hoist, tail closers,
          have inlining, by-exact, eta, rwa / simpa, obtain -> projections, witness / argument underscores, refine-constructor, apply-exact,
          ih-into-simp) searched greedily: each candidate compiled on the primary toolchain, adopted only when the whole proof scores more
          than --min-gain higher, then re-checked on every listed toolchain with Z unchanged (--max-compiles per row, --deadline-s).
          Measured (B26, 2026-10-20, probe/b26/readout.json): warm-up pipeline finals 90.89 -> 90.91 (1/15 rows), 42 held-out dev finals
          +0.12 (4/42). The hb_tool_token families that took the warm-up finals to 91.48 were literal templates of warm-up proofs and added
          nothing on held-out rows; they were removed.
  polish  model review rounds (harness/review.run_rounds: a reviewer names exact edits, each compiled, winners stacked) with
          --polish-model / --polish-rounds / --polish-k / --polish-budget; the result is re-verified on every toolchain here. Measured
          (docs/review_rounds_ab.md): Argon medium, 3 rounds x 5 edits, +2.12 summed on the 15 finals for $1.14 (about $0.08 per row).
  replan  one bounded harness/agent.py session from the current best (its own work root seeded with the current proof as the stored
          best, --no-bank-sync, --budget-usd = --replan-budget, --replan-turns turns, --replan-model preset, --replan-args extras); the
          session's best is read back and re-verified here. This is the lever behind the union's large rows (docs/retro_union_92.md:
          seeded re-plans with facts beat the union on 4/5; cold fresh starts all failed), bounded by the per-problem cap.
  certify search tactics -> the explicit certificate Lean reports for them (harness/certify.py: simp?, simp_all?, simpa?, grind?,
          aesop?; per-goal suggestions merged; grind anchors skipped; gen / maxDischargeDepth config variants); heartbeats drop,
          tokens may rise - priced by the score gate, pre-pruned by the row's token budget (probe/ceiling/floors.json). Opt-in.
  oracle  Lean's own library search as a $0 candidate generator (harness/oracle_rules.py): every proof suffix and nested `by` block is
          probed with `exact?` (--oracle-probes compiles per row); a "Try this: exact <term>" answer becomes a candidate through the
          same gate. The union's library wins (one Mathlib characterization or projection lemma per row) are of
          this kind. The rules stage also runs a one-step lookahead (--lookahead): a neutral edit that enables a gaining one is kept as a pair.
  pool    every proof of the same theorem stored anywhere in the repository (--pool-sources), the top --pool-top re-verified and the best
          adopted: retrieval, not computation. The organizer rules make every final row start from its seed proof, so this stage is for
          measuring the ceiling only (--allow-pool), never for a pipeline.
  verify  nothing beyond the input measurement: --stages verify re-measures a finals file on every toolchain (package hygiene).
Spend: a row's `spend` (input inference spend, item.spend, plus polish and replan) is tracked against --cap-usd (default $3, the
organizer's per-problem cap); a model stage whose budget would cross it is skipped and the row says so.
Honest framing: the pool stage creates no new proof; it retrieves the best stored one (union by retrieval). New points can only come from
free / rules / polish / replan. Adopted rows carry a provenance chain (input -> stage, source file, the record's own provenance).
The input row is measured once on every toolchain first (the stored score can be stale or from another meter). Every stage's result
is compared with its input measured on the SAME meter in this run (the evaluator: the direct lean path), never with the stored score:
2026-10-21 (docs/scaffold_panel.md "Rung 0 results") the free chain's result (lake meter) was compared with max(direct re-measure,
stored score), so the bar was 0.05 plus the meter offset; on the held-out finals 5 rows lost +0.06-0.07 each above the bar. Results
measured elsewhere (the free chain's passes, the review, a re-plan session) are re-measured here on every toolchain before the gate;
the bar stays 0.05 (scorer/accept.SIGNAL_GAIN). A row that no stage improves keeps its input proof and stored score, so it never ends
below its input. A row whose input does not compile is passed through unchanged (score as stored, flagged).
--no-compile (no Lean on this machine): only the pool stage runs, adopting stored measurements re-tokenized here, every adopted row
flagged verified=false -- a prediction of what the compiled run will confirm, not a result.
    python3 harness/postpass.py --input probe/distill/pipeline_finals_hb.json --output probe/postpass/finals_post.json
        [--report probe/postpass/finals_post.report.jsonl] [--stages free,rules,polish,replan] [--jobs 3] [--max-compiles 60]
        [--replan-model gpt-6.1-sol --replan-budget 0.4 --replan-turns 12 --replan-args "--auto-brief DIR"] [--cap-usd 3.0]
        [--allow-pool --stages pool --pool-top 3]
        [--min-gain 0.05] [--deadline-s 1800] [--free-rounds 3] [--polish-model gemini-4-argon --polish-rounds 2 --polish-k 5
        --polish-budget 1.0 --polish-effort high] [--rows data/abpool/abpool.jsonl --heartbeats data/abpool/heartbeats.jsonl]
        [--problems NAME ...] [--no-compile] [--anon]
Resumable: rows already in --report are skipped and their output rows kept. Compiles go through the scorer's memory gate (at most 3 at
once): run it in a memory-capped unit, never from an interactive shell."""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(1, str(ROOT / "harness"))
from harness import leantools as LT  # noqa: E402
from harness.hb_tool import _metrics, _valid, _finite  # noqa: E402
from harness.normalize import apply  # noqa: E402
from scorer.tokenize import split_declaration, count_tokens  # noqa: E402
from scorer.forbidden import check_forbidden  # noqa: E402
from scorer.score import len_pct, hb_pct_local, compat_pct, problem_score  # noqa: E402
from probe.verify_candidates import newest_first  # noqa: E402
from scorer.accept import SIGNAL_GAIN  # noqa: E402

MIN_GAIN = SIGNAL_GAIN     # noise margin of a re-measured proof (lint_delete.MIN_GAIN); the checkpoint signal bar, 0.05
STAGES = ("verify", "pool", "free", "rules", "certify", "oracle", "polish", "replan")
DEFAULT_STAGES = ("free", "rules", "oracle")   # computation only; `pool` (retrieval of stored proofs) needs --allow-pool: reference, never a pipeline step
POLISH_PRESETS_NOTE = "a harness/agent.py MODEL_PRESETS name (OpenRouter list price counts toward the per-problem cap)"
POOL_SOURCES = ("bank/*/*.json", "probe/runs/*/verified.jsonl", "probe/review/*.json", "probe/review/*/*.json", "probe/distill/*.json",
                "probe/distill/*.jsonl", "probe/bounty/results.jsonl", "probe/hbtool/*.jsonl", "probe/hbtool/*.json", "probe/gap91/*.json")
OUT_KEYS = ("tokens", "heartbeats", "L", "H", "Z", "score", "compat")


def parse_rules_exclude(spec) -> tuple[str, ...]:
    """B26: kind labels dropped from the rules stage. `spec`: None / "" (nothing), an iterable of labels, a comma list, or "@FILE"
    (one label per line, `#` comments). Labels must be gap_rules.KINDS (exact, no globs); an unknown label is an error, so a typo can
    never silently exclude nothing."""
    if not spec:
        return ()
    if isinstance(spec, str):
        if spec.startswith("@"):
            spec = [l.split("#", 1)[0] for l in Path(spec[1:]).read_text().splitlines()]
        else:
            spec = spec.split(",")
    labels = tuple(dict.fromkeys(x.strip() for x in spec if x and x.strip()))
    from harness.gap_rules import KINDS as GAP_KINDS
    bad = [x for x in labels if x not in set(GAP_KINDS)]
    if bad:
        raise ValueError(f"--rules-exclude: unknown kind label(s) {bad}; known: gap_rules.KINDS {list(GAP_KINDS)}")
    return labels


def rules_candidate_fn(source: str = "gap", exclude=()):
    """Candidate generators for the rules stage: harness.gap_rules (17 general syntactic kinds), deduped by (kind, edit spans).
    B26 (2026-10-20): the "token" source (harness/hb_tool_token.py, 2026-10-16) was removed: 23 of its 27 kinds templated single
    warm-up proofs and the module added nothing on the 42 held-out dev finals. `exclude` (--rules-exclude): kind labels never offered
    (lookahead included)."""
    if source != "gap":
        raise ValueError(f"rules source {source!r} was removed in B26 (2026-10-20); only 'gap' remains")
    excl = frozenset(parse_rules_exclude(exclude))
    from harness.gap_rules import candidates as gap_c
    fns = [lambda b: gap_c(b)]

    def fn(body):
        seen, out = set(), []
        for f in fns:
            for site in f(body):
                if site.kind in excl:
                    continue
                key = (site.kind, tuple(sorted(site.edits)))
                if key not in seen:
                    seen.add(key)
                    out.append(site)
        return out
    return fn


def _norm(proof: str) -> str:
    return re.sub(r"[ \t]+\n", "\n", proof.strip()) + "\n"


def _score_of(d: dict):
    for k in ("score", "final", "union_score"):
        v = d.get(k)
        if _finite(v):
            return float(v)
    for k in ("after", "stacked", "final", "verified"):
        v = d.get(k)
        if isinstance(v, dict) and _finite(v.get("score")):
            return float(v["score"])
    return None


def _stored_metrics(d: dict) -> dict:
    """The measurement stored with a record (its own keys, or those of its after / stacked / final dict)."""
    src = d
    for k in ("after", "stacked", "final"):
        v = d.get(k)
        if isinstance(v, dict) and _finite(v.get("score")):
            src = v
            break
    return {k: src[k] for k in OUT_KEYS if k in src}


# ------------------------------------------------------------------------------------------------------------------------------- pool
def _ws(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def identify(proof: str, stmts) -> tuple[str | None, str]:
    """(problem, proof) for a stored proof: the problem whose exact statement it starts with; else the one whose statement it starts
    with up to whitespace (a re-printed statement: review fix 3), in which case the proof body is spliced onto the exact statement so
    the scorer accepts it. `stmts`: [(statement, name)], longest first."""
    for st, n in stmts:
        if proof.startswith(st) and re.match(r"\s*:=", proof[len(st):]):
            return n, proof
    flat = _ws(proof)
    for st, n in stmts:
        fst = _ws(st)
        if flat.startswith(fst) and re.match(r"\s*:=", flat[len(fst):]):
            m = re.match(r"\s*:=", flat[len(fst):])
            # the body: everything after the statement's last token in the original text, found by walking its tokens
            toks, pos = st.split(), 0
            for t in toks:
                pos = proof.find(t, pos) + len(t)
            rest = proof[pos:]
            mm = re.match(r"\s*:=", rest)
            if mm:
                return n, st + " :=" + rest[mm.end():]
    return None, proof


def harvest(patterns, rows: dict, root: Path = ROOT, log=None) -> dict[str, list[dict]]:
    """Every proof found under the glob patterns, keyed by the problem whose exact statement it starts with, deduplicated (the highest
    stored score per text). Records: {proof, score (or None), src, metrics (stored keys)}."""
    stmts = sorted(((r["statement"], n) for n, r in rows.items()), key=lambda t: -len(t[0]))
    found: dict[str, dict[str, dict]] = {n: {} for n in rows}

    def emit(proof, score, src, rec):
        n, proof = identify(proof, stmts)
        if n is None:
            return
        key = _norm(proof)
        prev = found[n].get(key)
        metrics = {k: v for k, v in _stored_metrics(rec).items() if v is not None}
        prov = rec.get("provenance") if isinstance(rec.get("provenance"), (dict, str)) else None
        if prev is None:
            found[n][key] = {"proof": proof.strip(), "score": score, "src": src, "metrics": metrics, "provenance": prov}
        else:   # the same text from several sources: the highest stored score, the union of the stored measurements
            if score is not None and (prev["score"] is None or score > prev["score"]):
                prev.update(score=score, src=src)
                prev["provenance"] = prov or prev["provenance"]
            prev["metrics"] = {**metrics, **prev["metrics"]} if (prev["score"] == score or score is None) else {**prev["metrics"], **metrics}
            prev["provenance"] = prev["provenance"] or prov

    def walk(obj, src, depth=0):
        if depth > 12:
            return
        if isinstance(obj, dict):
            if isinstance(obj.get("proof"), str):
                emit(obj["proof"], _score_of(obj), src, obj)
            for k in ("union_proof", "pipeline_proof"):
                if isinstance(obj.get(k), str):
                    emit(obj[k], obj.get(k.replace("proof", "score")) if _finite(obj.get(k.replace("proof", "score"))) else None, src, {})
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    walk(v, src, depth + 1)
        elif isinstance(obj, list):
            for v in obj:
                if isinstance(v, (dict, list)):
                    walk(v, src, depth + 1)

    files = sorted({p for pat in patterns for p in glob.glob(str(root / pat), recursive=True)})
    for f in files:
        p = Path(f)
        try:
            if p.suffix == ".jsonl":
                with p.open() as fh:
                    for line in fh:
                        line = line.strip()
                        if line.startswith("{"):
                            try:
                                walk(json.loads(line), str(p.relative_to(root)))
                            except json.JSONDecodeError:
                                continue
            else:
                walk(json.loads(p.read_text()), str(p.relative_to(root)))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            if log:
                log(f"pool: skipped {p.name}: {type(e).__name__}")
    return {n: sorted(v.values(), key=lambda r: -(r["score"] if r["score"] is not None else -1e9)) for n, v in found.items()}


def predicted(name: str, proof: str, metrics: dict, rows: dict, hbs: dict) -> dict | None:
    """A stored measurement re-derived here without Lean: tokens re-counted (L recomputed), H from the stored heartbeats (or H), Z from the
    stored compat (or Z). None when the record carries no heartbeat and no compatibility information."""
    row = rows[name]
    body = split_declaration(proof, row["statement"])
    if body is None or check_forbidden(body):
        return None
    tokens = count_tokens(body)
    L = len_pct(row["proof_length"], tokens)
    if _finite(metrics.get("heartbeats")):
        H = hb_pct_local(name, int(metrics["heartbeats"]), hbs.get(name))
    elif _finite(metrics.get("H")):
        H = float(metrics["H"])
    else:
        return None
    compat = metrics.get("compat")
    if isinstance(compat, dict) and compat:
        Z = compat_pct(compat)
    elif _finite(metrics.get("Z")):
        Z = float(metrics["Z"])
    else:
        return None
    return {"ok": True, "tokens": tokens, "heartbeats": metrics.get("heartbeats"), "L": round(L, 2), "H": round(H, 2), "Z": Z,
            "compat": compat if isinstance(compat, dict) else {}, "score": problem_score(True, L, H, Z)}


# ------------------------------------------------------------------------------------------------------------------ rule search
def rule_search(name: str, proof: str, *, statement: str, versions: list, evaluate_fn, candidate_fn=None, max_compiles: int = 60,
                min_gain: float = MIN_GAIN, deadline=None, clock=time.monotonic, base: dict | None = None, log=None, caps=None,
                lookahead: int = 0) -> dict:
    """Greedy compile-gated search over harness.gap_rules candidates (hb_tool.improve's loop with a score-only gate: a token-structural edit
    may cost heartbeats as long as the score rises by more than `min_gain`; Z must stay unchanged on every listed toolchain).
    `evaluate_fn(decl, full)` returns scorer metrics (+ `compat` on full evaluations, optionally `compiles`) and may expose `cost(full)`;
    `base`: a fresh full measurement of `proof` to start from (saves the initial compiles); else the input is measured first.
    `lookahead` (2026-10-17): when a round finds no gain, the `lookahead` best-ranked NEUTRAL candidates (compiled, score within the noise
    margin of the best, no longer) are each expanded one step: a gaining follow-up edit on top of one is adopted as a pair (an edit that
    pays only after an enabling one: `unhygienic` before auto-named closers, a bullet merge before a tail closer)."""
    if candidate_fn is None:
        from harness.gap_rules import candidates as _cands
        candidate_fn = lambda b: _cands(b, caps)  # noqa: E731
    versions = list(versions)
    report = {"problem": name, "status": "no gain", "proof": proof, "before": {}, "after": {}, "compiles": 0, "max_compiles": max_compiles,
              "applied": {}, "attempts": [], "versions": versions}
    body = split_declaration(proof, statement)
    if body is None:
        report["status"] = "statement differs"
        return report
    bad = check_forbidden(body)
    if bad:
        report.update(status="forbidden input", error=bad)
        return report
    head = proof[:len(proof) - len(body)]

    def cost(full):
        m = getattr(evaluate_fn, "cost", None)
        return int(m(full)) if m else (len(versions) if full else 1)

    def evaluate(decl, full):
        bound = cost(full)
        if report["compiles"] + bound > max_compiles:
            raise RuntimeError("compile reservation exceeded")
        try:
            r = dict(evaluate_fn(decl, full))
        except Exception as exc:  # noqa: BLE001
            r = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "compiles": bound}
        actual = r.get("compiles", bound)
        if not isinstance(actual, int) or actual < 0:
            actual = bound
        if actual > bound:   # the evaluator spent more than its estimate: charge it and note it (never abort the row)
            report["overspent"] = report.get("overspent", 0) + (actual - bound)
        report["compiles"] += actual
        return r

    started = clock()
    if base and _valid(base, versions, True):
        initial = dict(base)
    else:
        if cost(True) > max_compiles:
            report.update(status="budget too small", stopped="max-compiles")
            return report
        initial = evaluate(proof, True)
    report["before"] = report["after"] = _metrics(initial)
    if not _valid(initial, versions, True):
        report.update(status="input does not compile" if not initial.get("ok") else "incomplete baseline", error=initial.get("error"))
        return report
    best = initial
    seen = {proof}
    failed: set = set()
    neutral: list = []

    def try_candidate(cbody, site, incumbent, tag_prefix=""):
        """Primary compile, provisional gate, full check: the verified result or None (attempt recorded)."""
        candidate = head + apply(cbody, [site])
        if candidate in seen:
            return None, None
        seen.add(candidate)
        nbody = split_declaration(candidate, statement)
        tag = (site.kind, site.note)
        if nbody is None or check_forbidden(nbody):
            failed.add(tag)
            return None, None
        trial = evaluate(candidate, False)
        attempt = {"kind": tag_prefix + site.kind, "note": site.note, "primary": _metrics(trial), "accepted": False}
        report["attempts"].append(attempt)
        if not _valid(trial, versions, False):
            attempt.update(reason="compile failed", error=(trial.get("error") or "")[:200])
            failed.add(tag)
            return None, None
        provisional = round((trial["L"] + trial["H"] + incumbent["Z"]) / 3, 2)
        if provisional - incumbent["score"] <= min_gain + 1e-9:
            attempt["reason"] = f"no gain ({provisional} vs {incumbent['score']})"
            if not tag_prefix and provisional >= incumbent["score"] - min_gain - 1e-9 and trial["tokens"] <= incumbent["tokens"]:
                neutral.append((site.priority, candidate, nbody, trial))
            failed.add(tag)
            return None, None
        checked = evaluate(candidate, True)
        attempt["verified"] = _metrics(checked)
        if not _valid(checked, versions, True):
            attempt.update(reason="full verification failed", error=(checked.get("error") or "")[:200])
            failed.add(tag)
            return None, None
        if checked["compat"] != initial["compat"] or checked["Z"] != initial["Z"]:
            attempt["reason"] = "toolchain compatibility changed"
            failed.add(tag)
            return None, None
        if checked["score"] - incumbent["score"] <= min_gain + 1e-9:
            attempt["reason"] = "confirmed score margin"
            failed.add(tag)
            return None, None
        attempt["accepted"] = True
        return candidate, checked

    def out_of_budget(full=True):
        return report["compiles"] + cost(False) + (cost(True) if full else 0) > max_compiles

    while True:
        changed = False
        neutral.clear()
        for site in list(candidate_fn(body)):
            if deadline is not None and clock() >= deadline:
                report["stopped"] = "deadline"
                break
            if out_of_budget():
                report["stopped"] = "max-compiles"
                break
            if (site.kind, site.note) in failed:
                continue
            got, checked = try_candidate(body, site, best)
            if got:
                report["applied"][site.kind] = report["applied"].get(site.kind, 0) + 1
                report.update(status="improved", proof=got, after=_metrics(checked))
                if log:
                    log(f"  rules: {site.kind} accepted ({best['score']} -> {checked['score']}): {site.note[:70]}")
                body, best, changed = split_declaration(got, statement), checked, True
                break
        if not changed and lookahead and not report.get("stopped"):
            # one-step lookahead: expand the best neutral candidates; a gaining follow-up adopts the pair
            for _, cand, cbody, trial in sorted(neutral, key=lambda t: -t[0])[:lookahead]:
                if changed or report.get("stopped"):
                    break
                for site2 in list(candidate_fn(cbody)):
                    if deadline is not None and clock() >= deadline:
                        report["stopped"] = "deadline"
                        break
                    if out_of_budget():
                        report["stopped"] = "max-compiles"
                        break
                    if (site2.kind, site2.note) in failed:
                        continue
                    got, checked = try_candidate(cbody, site2, best, tag_prefix="lookahead:")
                    if got:
                        report["applied"]["lookahead"] = report["applied"].get("lookahead", 0) + 1
                        report["applied"][site2.kind] = report["applied"].get(site2.kind, 0) + 1
                        report.update(status="improved", proof=got, after=_metrics(checked))
                        if log:
                            log(f"  rules: lookahead pair accepted ({best['score']} -> {checked['score']}): {site2.note[:60]}")
                        body, best, changed = split_declaration(got, statement), checked, True
                        break
        if not changed or report.get("stopped"):
            break
    report["seconds"] = round(clock() - started, 1)
    report["gain"] = round(best["score"] - initial["score"], 2)
    return report


# ------------------------------------------------------------------------------------------------------------------ the row driver
def _free_stage(name, proof, rounds, log, only=None):
    from harness.autobrief import free_passes
    decl, steps = free_passes(name, proof, log=log, rounds=rounds, only=only)
    last = None
    for st in steps:
        if st.get("status") == "improved" and (st.get("after") or {}).get("score") is not None:
            last = st["after"]
    return decl, last, [{k: st.get(k) for k in ("round", "pass", "status", "applied", "gain", "compiles", "seconds")} for st in steps]


def _polish_stage(name, proof, cfg, log):
    from harness.review import run_rounds
    rep_n, stk = int(getattr(cfg, "polish_repair", 0) or 0), bool(getattr(cfg, "polish_stack", False))   # b72 R6 (off: the call as before)
    r6kw = {"repair": rep_n, "stack": stk, "stack_eps": float(getattr(cfg, "polish_stack_eps", 0.02))} if (rep_n or stk) else {}
    r = run_rounds(name, proof, cfg.polish_model, cfg.polish_k, cfg.polish_effort, rounds=cfg.polish_rounds,
                   budget_usd=cfg.polish_budget, log=log, max_tokens=int(getattr(cfg, "polish_max_tokens", 32000) or 32000),
                   cap_price=getattr(cfg, "polish_cap_price", None) or "announced",
                   fallback_model=getattr(cfg, "polish_fallback_model", None), **r6kw)   # b66 (A3): the stand-in after a confirmed pin (router)
    # review_cap_spend (b64 L0): the same calls at the cap prices the budget is in (= review_spend when they are the list table)
    return r.get("proof") or proof, r.get("final"), {k: r.get(k) for k in ("status", "review_spend", "review_cap_spend", "base", "final", "pin_unservable",
                                                                          "review_fallback", "r6", "stack_proofs", "r6_rounds")
                                                     if k not in ("pin_unservable", "review_fallback", "r6", "stack_proofs", "r6_rounds") or r.get(k)}
    # b65-final: a confirmed max_price pin (review skipped, $0); b66 (A3): the review went on on its fallback model after one; b72 R6: its
    # counts and the verified stacks (only with R6 on)


def check_stages(stages, allow_pool: bool) -> str | None:
    """None when the stage list is runnable, else the reason: an unknown stage, or `pool` without --allow-pool (the organizer rules:
    every final row starts from its seed proof; stored proofs are reference only)."""
    bad = [s for s in stages if s not in STAGES]
    if bad:
        return f"unknown stage(s) {bad}; choose from {STAGES}"
    if "pool" in stages and not allow_pool:
        return ("the pool stage retrieves proofs stored by earlier runs: reference only, not computation (the final must start from the seed "
                "proof). Pass --allow-pool to run it deliberately, e.g. to measure the ceiling.")
    return None


def seed_workspace(root: Path, name: str, proof: str, metrics: dict) -> Path:
    """A fresh agent work root for one problem whose stored best is the current proof: harness/agent.py resumes from it (candidate.lean =
    best, the digest says so) and its --budget-usd counts from zero here (api_spend)."""
    import re as _re
    d = root / _re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    d.mkdir(parents=True, exist_ok=True)
    best = {"score": float(metrics.get("score") or 33.33), "proof": proof.rstrip() + "\n"}
    best.update({k: metrics.get(k) for k in ("tokens", "heartbeats", "L", "H", "Z", "compat") if metrics.get(k) is not None})
    (d / "state.json").write_text(json.dumps({"problem": name, "best": best, "attempts": [], "runs": [], "api_spend": 0.0}, ensure_ascii=False, indent=1))
    (d / "best.lean").write_text(best["proof"]); (d / "candidate.lean").write_text(best["proof"])
    if not (d / "notes.md").exists():   # 2026-10-19: agent.py's digest reads notes.md of an existing workspace (first live replan exited 1 without it)
        (d / "notes.md").write_text("# Notes (yours to keep; persisted across runs)\n")
    return d


def _replan_stage(name, proof, metrics, cfg, log, runner=None):
    """Model re-plan from the current best: one bounded harness/agent.py session (its own work root, seeded with the current proof as the
    stored best; --no-bank-sync; --budget-usd = --replan-budget; turns = --replan-turns), then the session's best is read back. The
    agent's full verification is repeated by the caller (final check). `runner(cmd, workdir)` is injectable (tests)."""
    import shlex, subprocess
    run_id = f"postpass-replan-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() // 1_000_000 % 1000:03d}"   # unique when a row re-plans twice in a second
    root = Path(cfg.replan_root)
    root = root if root.is_absolute() else ROOT / root
    d = seed_workspace(root, name, proof, metrics)
    cmd = [sys.executable, str(ROOT / "harness/agent.py"), "--problems", name, "--work-root", str(root.relative_to(ROOT) if root.is_relative_to(ROOT) else root),
           "--model-preset", cfg.replan_model, "--budget-usd", str(cfg.replan_budget), "--turns", str(cfg.replan_turns), "--no-adaptive-turns",
           "--run-id", run_id, "--workers", "1", "--no-bank-sync"] + shlex.split(getattr(cfg, "replan_args", "") or "")
    t0 = time.time()
    try:
        if runner is None:
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=getattr(cfg, "replan_timeout", 3600))
            tail = (r.stdout or "")[-1500:]; rc = r.returncode
        else:
            rc, tail = runner(cmd, d)
    except Exception as e:  # noqa: BLE001  (2026-10-18: a timed-out or failed session has still spent; its ledger below counts it)
        rc, tail = -1, f"session failed: {type(e).__name__}: {str(e)[:300]}"
    st = json.loads((d / "state.json").read_text()) if (d / "state.json").exists() else {}
    best = st.get("best") or {}
    info = {"run_id": run_id, "work_dir": str(d), "returncode": rc, "spend": float(st.get("api_spend") or 0), "attempts": len(st.get("attempts") or []),
            "best_score": best.get("score"), "seconds": round(time.time() - t0, 1), "tail": tail[-600:]}
    log(f"replan: {cfg.replan_model} {cfg.replan_turns} turns, ${info['spend']:.3f}, agent best {best.get('score')} (from {metrics.get('score')})")
    return (best.get("proof") or proof), {k: best.get(k) for k in ("score", "tokens", "heartbeats", "L", "H", "Z", "compat") if best.get(k) is not None}, info


def improve_row(name: str, item: dict, cfg, evaluator, pool: dict, log=print, rows=None, hbs=None) -> dict:
    """One row: measure the input, run the stages in order, re-measure on the evaluator what a stage measured elsewhere, gate every stage
    on that one meter (2026-10-21), never return less than the input there (an unimproved row keeps its input proof and stored score)."""
    rows, hbs = rows or LT.ROWS, hbs or LT.HBS
    row = rows[name]
    versions = newest_first(row["version_info"])
    proof0 = item["proof"].strip()
    stored = float(item["score"]) if _finite(item.get("score")) else None
    t0 = time.time()
    rep = {"problem": name, "input_score": stored, "stages": {}, "versions": versions}
    if callable(evaluator) and not hasattr(evaluator, "bound"):
        evaluator = evaluator()   # a factory: one evaluator per row (its compile counter is per instance, never shared across rows)
    ev = evaluator.bound(name, versions) if evaluator is not None else None
    body0 = split_declaration(proof0, row["statement"])
    if body0 is None or check_forbidden(body0):
        rep.update(status="input rejected", error="statement differs" if body0 is None else "forbidden")
        return rep | {"out": dict(item, verified=False, stage="input")}
    if ev is not None:
        base = ev(proof0, True)
        if not _valid(base, versions, True):
            rep.update(status="input does not compile", error=base.get("error"))
            return rep | {"out": dict(item, verified=False, stage="input")}
    else:
        base = predicted(name, proof0, {k: item[k] for k in OUT_KEYS if k in item} | ({"Z": item.get("Z", 100.0)} if "H" in item else {}), rows, hbs) or {
            "ok": True, "tokens": count_tokens(body0), "L": round(len_pct(row["proof_length"], count_tokens(body0)), 2), "score": stored or 0.0,
            "H": None, "Z": item.get("Z", 100.0), "compat": {}}
    # 2026-10-21 meter mix: cur["metrics"] is always a measurement on ev from this run (the input's, or an adopted result's), so every gate
    # below compares one meter; the stored score is no floor (was max(stored, measured): the bar became 0.05 plus the meter offset)
    cur = {"proof": proof0, "metrics": base, "stage": "input", "src": None, "full": ev is not None, "verified": ev is not None,
           "provenance": [{"stage": "input", "score": stored, "provenance": item.get("provenance")}]}
    rep["measured_input"] = _metrics(base)
    spend = {"input": float(item["spend"]) if _finite(item.get("spend")) else None}   # per-problem inference spend, USD (the cap counts it)
    cap = float(getattr(cfg, "cap_usd", 0) or 0)

    def spent() -> float:
        return sum(v for v in spend.values() if v)

    def room(budget: float) -> bool:
        return not cap or spent() + float(budget or 0) <= cap + 1e-9

    def adopt(proof, metrics, stage, src=None, full=False, verified=True, provenance=None, stored_score=None):
        nonlocal cur
        if proof.strip() != cur["proof"] and _finite(metrics.get("score")) and metrics["score"] - cur["metrics"]["score"] > cfg.min_gain + 1e-9:
            chain = cur["provenance"] + [{"stage": stage, "src": src, "stored_score": stored_score, "score": metrics["score"], "provenance": provenance}]
            cur = {"proof": proof.strip(), "metrics": metrics, "stage": stage, "src": src, "full": full, "verified": verified, "provenance": chain}
            log(f"{name[:40]}: {stage} -> {metrics['score']}" + (f" ({src})" if src else ""))
            return True
        return False

    def remeasured(proof, stage, info) -> bool:
        """A result measured on another meter (the free chain's lake passes, the review, the agent session): measured here on ev, every
        toolchain, then gated against cur on that same meter (2026-10-21 meter mix). Was: adopted on the stage's own numbers against
        max(cur, stored), with one deferred final check of the last such stage."""
        m = ev(proof, True)
        info["measured"] = _metrics(m)
        if stage in ("polish", "replan"):
            rep["final_check"] = info["measured"]
        if _valid(m, versions, True):
            return adopt(proof, m, stage, full=True)
        log(f"{name[:40]}: {stage} result fails the full check ({(m.get('error') or m.get('score'))}); {cur['stage']} kept")
        return False

    for stage in cfg.stages:
        try:
            if stage == "verify":   # measure only (the input measurement above); final-package hygiene
                rep["stages"]["verify"] = _metrics(base)
            elif stage == "pool":
                cands = [c for c in pool.get(name, []) if _norm(c["proof"]) != _norm(cur["proof"])   # stored scores: a pre-filter only
                         and (c["score"] is not None and c["score"] - cur["metrics"]["score"] > cfg.min_gain)]
                tried = []
                for c in cands:
                    if len(tried) >= cfg.pool_top:
                        break
                    if ev is None:
                        m = predicted(name, c["proof"], c["metrics"], rows, hbs)
                        ok = m is not None
                        if not ok:
                            continue   # a stored score without a measurement cannot be predicted; it does not use up a slot
                    else:
                        m = ev(c["proof"], True)
                        ok = _valid(m, versions, True)
                    tried.append({"src": c["src"], "stored": c["score"], "ok": ok, "measured": _metrics(m) if m else None,
                                  "error": (m or {}).get("error")})
                    if ok:
                        adopt(c["proof"], m, "pool", c["src"], full=True, verified=ev is not None, provenance=c.get("provenance"), stored_score=c["score"])
                rep["stages"]["pool"] = {"candidates": len(cands), "tried": tried}
            elif stage == "free":
                if ev is None:
                    rep["stages"]["free"] = {"status": "skipped (no compile)"}
                    continue
                fp = getattr(cfg, "free_passes", None)
                decl, after, steps = _free_stage(name, cur["proof"], cfg.free_rounds, lambda m: log(f"{name[:40]}: {m}"),
                                                 only=[x.strip() for x in fp.split(",") if x.strip()] if isinstance(fp, str) and fp else (fp or None))
                rep["stages"]["free"] = {"steps": steps, "after": after}
                if after and decl.strip() != cur["proof"]:   # `after` is the last improving pass's own meter (lake, or direct for hb_tool)
                    remeasured(decl, "free", rep["stages"]["free"])
            elif stage == "rules":
                if ev is None:
                    rep["stages"]["rules"] = {"status": "skipped (no compile)"}
                    continue
                base_for = cur["metrics"] if cur["full"] else None
                r = rule_search(name, cur["proof"], statement=row["statement"], versions=versions, evaluate_fn=ev, max_compiles=cfg.max_compiles, candidate_fn=rules_candidate_fn(getattr(cfg, "rules_source", "gap"), getattr(cfg, "rules_exclude", None)),
                                lookahead=int(getattr(cfg, "lookahead", 0) or 0),
                                min_gain=cfg.min_gain, deadline=None if not cfg.deadline_s else time.monotonic() + cfg.deadline_s,
                                base=base_for, log=lambda m: log(f"{name[:40]}: {m}"))
                rep["stages"]["rules"] = {k: r.get(k) for k in ("status", "before", "after", "applied", "compiles", "gain", "stopped", "seconds", "error")}
                rep["stages"]["rules"]["source"] = getattr(cfg, "rules_source", "gap")
                rep["stages"]["rules"]["exclude"] = list(parse_rules_exclude(getattr(cfg, "rules_exclude", None)))
                rep["stages"]["rules"]["attempts"] = [{k: a.get(k) for k in ("kind", "note", "accepted", "reason", "verified")} for a in r.get("attempts", [])]
                if r.get("status") == "improved":
                    adopt(r["proof"], r["after"], "rules", full=True)
                elif r.get("before") and cur["stage"] == "input" and not cur["full"]:
                    cur["metrics"], cur["full"] = r["before"], True
            elif stage == "certify":
                if ev is None:
                    rep["stages"]["certify"] = {"status": "skipped (no compile)"}
                    continue
                from harness.certify import certify_candidates, token_budget_for
                fl = getattr(cfg, "_floors", None)
                if fl is None:
                    fp = ROOT / "probe/ceiling/floors.json"
                    fl = cfg._floors = json.loads(fp.read_text()) if fp.exists() else {}
                if fl.get(name) is not None:
                    fl[name]["hb_now"] = cur["metrics"].get("heartbeats")
                cands = certify_candidates(ev, row["statement"], max_probes=int(getattr(cfg, "certify_probes", 12) or 0),
                                           token_budget=token_budget_for(name, fl), log=lambda m: log(f"{name[:40]}: {m}"))
                base_for = cur["metrics"] if cur["full"] else None
                r = rule_search(name, cur["proof"], statement=row["statement"], versions=versions, evaluate_fn=ev, candidate_fn=cands,
                                max_compiles=cfg.max_compiles, min_gain=cfg.min_gain, base=base_for,
                                deadline=None if not cfg.deadline_s else time.monotonic() + cfg.deadline_s, log=lambda m: log(f"{name[:40]}: {m}"))
                rep["stages"]["certify"] = {k: r.get(k) for k in ("status", "before", "after", "applied", "compiles", "gain", "stopped", "seconds", "error")}
                rep["stages"]["certify"]["probes"] = cands.state["probes"]
                rep["stages"]["certify"]["attempts"] = [{k: a.get(k) for k in ("kind", "note", "accepted", "reason")} for a in r.get("attempts", [])]
                if r.get("status") == "improved":
                    adopt(r["proof"], r["after"], "certify", full=True)
                elif r.get("before") and cur["stage"] == "input" and not cur["full"]:
                    cur["metrics"], cur["full"] = r["before"], True
            elif stage == "oracle":
                if ev is None:
                    rep["stages"]["oracle"] = {"status": "skipped (no compile)"}
                    continue
                from harness.oracle_rules import oracle_candidates
                cands = oracle_candidates(ev, max_probes=int(getattr(cfg, "oracle_probes", 12) or 0), log=lambda m: log(f"{name[:40]}: {m}"),
                                          statement=row["statement"])
                base_for = cur["metrics"] if cur["full"] else None
                r = rule_search(name, cur["proof"], statement=row["statement"], versions=versions, evaluate_fn=ev, candidate_fn=cands,
                                max_compiles=cfg.max_compiles, min_gain=cfg.min_gain, base=base_for,
                                deadline=None if not cfg.deadline_s else time.monotonic() + cfg.deadline_s, log=lambda m: log(f"{name[:40]}: {m}"))
                rep["stages"]["oracle"] = {k: r.get(k) for k in ("status", "before", "after", "applied", "compiles", "gain", "stopped", "seconds", "error")}
                rep["stages"]["oracle"]["probes"] = cands.state["probes"]
                rep["stages"]["oracle"]["attempts"] = [{k: a.get(k) for k in ("kind", "note", "accepted", "reason")} for a in r.get("attempts", [])]
                if r.get("status") == "improved":
                    adopt(r["proof"], r["after"], "oracle", full=True)
                elif r.get("before") and cur["stage"] == "input" and not cur["full"]:
                    cur["metrics"], cur["full"] = r["before"], True
            elif stage == "polish":
                if ev is None or not cfg.polish_model:
                    rep["stages"]["polish"] = {"status": "skipped (no compile or no --polish-model)"}
                    continue
                if not room(cfg.polish_budget):
                    rep["stages"]["polish"] = {"status": f"skipped: spend ${spent():.2f} + budget ${cfg.polish_budget:.2f} would exceed the cap ${cfg.cap_usd:.2f}"}
                    continue
                try:
                    decl, final, info = _polish_stage(name, cur["proof"], cfg, lambda m: log(f"{name[:40]}: {m}"))
                except Exception as e:  # noqa: BLE001  (2026-10-18: a failed review may have spent; count its whole budget)
                    decl, final = cur["proof"], None
                    if getattr(e, "pin_confirmed", False):   # b65-final: a confirmed max_price pin refused it before any data: its real charge
                        info = {"status": "pin_unservable (review skipped, $0)", "review_spend": float(getattr(e, "charged", 0) or 0),
                                "review_cap_spend": float(getattr(e, "charged_cap", 0) or 0), "pin_unservable": str(getattr(e, "body", "") or e)[:300]}
                    elif getattr(e, "connect_exhausted", False):   # b66 (A4): never sent ($0): its real charge, not the budget
                        info = {"status": "connect failure (review stopped; never sent, $0)", "review_spend": float(getattr(e, "charged", 0) or 0),
                                "review_cap_spend": float(getattr(e, "charged_cap", 0) or 0)}
                    else:
                        info = {"status": f"error {type(e).__name__}: {str(e)[:160]} (spend assumed = budget)", "review_spend": float(cfg.polish_budget or 0),
                                "review_cap_spend": float(cfg.polish_budget or 0)}
                rep["stages"]["polish"] = info
                spend["polish"] = round((spend.get("polish") or 0) + float(info.get("review_spend") or 0), 4)   # accumulate: a stage may run more than once (router passes)
                if final and decl.strip() != cur["proof"] and _finite(final.get("score")):
                    remeasured(decl, "polish", info)
            elif stage == "replan":
                if ev is None or not getattr(cfg, "replan_model", None):
                    rep["stages"]["replan"] = {"status": "skipped (no compile or no --replan-model)"}
                    continue
                if not room(cfg.replan_budget):
                    rep["stages"]["replan"] = {"status": f"skipped: spend ${spent():.2f} + budget ${cfg.replan_budget:.2f} would exceed the cap ${cfg.cap_usd:.2f}"}
                    continue
                decl, m, info = _replan_stage(name, cur["proof"], cur["metrics"], cfg, lambda m_: log(f"{name[:40]}: {m_}"), runner=getattr(cfg, "replan_runner", None))
                rep["stages"]["replan"] = info
                spend["replan"] = round((spend.get("replan") or 0) + float(info.get("spend") or 0), 4)   # accumulate: a stage may run more than once (router passes)
                if decl.strip() != cur["proof"] and _finite(m.get("score")):
                    remeasured(decl, "replan", info)   # the agent's own check is not trusted here: re-verified on every toolchain
        except Exception as e:  # noqa: BLE001  (one stage failing never loses the row)
            rep["stages"][stage] = {"status": f"error {type(e).__name__}: {str(e)[:160]}"}
            log(f"{name[:40]}: stage {stage} failed: {type(e).__name__}: {str(e)[:120]}")
    out = {"proof": cur["proof"], **{k: cur["metrics"].get(k) for k in OUT_KEYS if cur["metrics"].get(k) is not None},
           "stage": cur["stage"], "verified": bool(cur["verified"]), "input_score": stored}
    if cur["src"]:
        out["src"] = cur["src"]
    if cur["stage"] != "input":
        out["provenance"] = cur["provenance"]   # the chain input -> stage(s) that produced this proof, with the pool record's own provenance
    spend["total"] = round(spent(), 4)
    out["spend"] = spend
    if cur["stage"] == "input":
        out["score"] = stored if stored is not None else cur["metrics"].get("score")
        out["gain"] = round((out.get("score") or 0) - (stored or 0), 2)
    else:   # the gain on the meter the stages were gated on (the stored score may be another meter's reading)
        out["measured_input"] = base["score"]
        out["gain"] = round(out["score"] - base["score"], 2)
        if stored is not None and _finite(base.get("score")):
            # review 2026-10-21: the score leaves on the STORED scale (stored + the same-meter gain), so the router's
            # write-back, fold and gate keep comparing one meter's numbers (the ladder's); the reading itself stays in measured_score
            out["measured_score"] = out["score"]
            out["score"] = round(float(stored) + (float(cur["metrics"]["score"]) - float(base["score"])), 2)
    rep.update(status="improved" if cur["stage"] != "input" else "no gain", stage=cur["stage"], score=out.get("score"),
               gain=out["gain"], seconds=round(time.time() - t0, 1), out=out)
    return rep


# --------------------------------------------------------------------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    """The CLI; harness/router.py builds its per-step configurations from these defaults (one source of truth)."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="finals JSON {problem: {proof, score, ...}}")
    ap.add_argument("--output", required=True, help="improved finals JSON (same shape, plus stage / verified / src / gain)")
    ap.add_argument("--report", help="per-row JSONL report (default: <output>.report.jsonl); rows present are skipped (resume)")
    ap.add_argument("--stages", default=",".join(DEFAULT_STAGES), help="comma list in execution order, from " + ", ".join(STAGES))
    ap.add_argument("--pool-sources", default=",".join(POOL_SOURCES), help="comma list of glob patterns (relative to the repo root)")
    ap.add_argument("--pool-top", type=int, default=3, help="stored candidates re-verified per row, best stored score first")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--max-compiles", type=int, default=60, help="rules stage: compile budget per row")
    ap.add_argument("--rules-source", default="gap", choices=["gap"], help="rules stage candidate generators: gap_rules (the hb_tool_token "
                    "source was removed in B26, 2026-10-20)")
    ap.add_argument("--rules-exclude", default="", help="rules stage: kind labels never offered (comma list or @FILE, one per line); "
                    "exact gap_rules labels only")
    ap.add_argument("--min-gain", type=float, default=MIN_GAIN)
    ap.add_argument("--deadline-s", type=float, default=1800.0, help="rules stage: seconds per row (0 = none)")
    ap.add_argument("--free-rounds", type=int, default=3)
    ap.add_argument("--free-passes", default=None, help="comma list: run only these free passes (normalize, hb_rewrite, hb_preorder, "
                    "hb_polish, lint_delete, hb_tool); default all")
    ap.add_argument("--polish-model", default=None, help="harness/agent.py MODEL_PRESETS name for the polish stage")
    ap.add_argument("--polish-rounds", type=int, default=2)
    ap.add_argument("--polish-k", type=int, default=5)
    ap.add_argument("--polish-budget", type=float, default=1.0, help="review spend cap per row in USD")
    ap.add_argument("--polish-effort", default="high")
    ap.add_argument("--polish-max-tokens", type=int, default=32000, help="review output cap per call; its worst case (cap x output price) must fit "
                    "the review budget or the review is skipped")
    ap.add_argument("--polish-cap-price", choices=["announced", "list"], default="announced", help="b64 L0: the price table the polish "
                    "budget gates every review call at (agent.cap_prices): announced = a preset's announced price (Gemini 4 Argon $4 / $20), "
                    "list = its metered table (the pre-L0 gate); the reported spend is metered at the list table either way")
    ap.add_argument("--polish-repair", type=int, default=0, help="b72 R6: repair turns per review round for edits that failed to compile "
                    "(the review's own model, metered as the review; 0 = off)")
    ap.add_argument("--polish-stack", action="store_true", help="b72 R6: after each round, every compiling edit within --polish-stack-eps "
                    "of the base stacked in one full compile (greedy fallback); verified stacks are returned for the row's bank")
    ap.add_argument("--polish-stack-eps", type=float, default=0.02, help="b72 R6: --polish-stack's admission margin under the round base")
    ap.add_argument("--certify-probes", type=int, default=12, help="certify stage: `?`-query probe compiles per row (simp?/simp_all?/simpa?/grind?/aesop?)")
    ap.add_argument("--oracle-probes", type=int, default=12, help="oracle stage: `exact?` probe compiles per row (suffixes and by-blocks)")
    ap.add_argument("--lookahead", type=int, default=2, help="rules stage: neutral candidates expanded one step when a round finds no gain (0 = off)")
    ap.add_argument("--replan-model", default=None, help="harness/agent.py MODEL_PRESETS name: one bounded agent session from the current best")
    ap.add_argument("--replan-budget", type=float, default=0.4, help="replan: --budget-usd of the session (USD per row, list price)")
    ap.add_argument("--replan-turns", type=int, default=12)
    ap.add_argument("--replan-timeout", type=int, default=3600, help="replan: seconds per row before the session is killed")
    ap.add_argument("--replan-args", default="", help="replan: extra harness/agent.py arguments, quoted (e.g. '--auto-brief DIR --pattern-cards')")
    ap.add_argument("--replan-root", default="probe/postpass/replan", help="replan: work root for the seeded sessions")
    ap.add_argument("--cap-usd", type=float, default=3.0, help="per-problem inference cap: input spend (item.spend) + polish + replan budgets must fit; 0 = no cap")
    ap.add_argument("--allow-pool", action="store_true", help="run the pool stage (retrieval of stored proofs: reference only)")
    ap.add_argument("--rows", help="extra rows JSONL (held-out problems) registered before running")
    ap.add_argument("--heartbeats", help="their reference heartbeats JSONL")
    ap.add_argument("--problems", nargs="*", help="restrict to these rows")
    ap.add_argument("--no-compile", action="store_true", help="no Lean: pool stage only, stored measurements, verified=false")
    ap.add_argument("--anon", action="store_true", help="log rows as row#k instead of names")
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    stages = [s.strip() for s in a.stages.split(",") if s.strip()]
    err = check_stages(stages, a.allow_pool)
    if err:
        ap.error(err)
    a.stages = stages
    try:
        a.rules_exclude = parse_rules_exclude(a.rules_exclude)
    except (ValueError, OSError) as e:
        ap.error(str(e))
    if a.rows:
        LT.ROWS.update({json.loads(l)["name"]: json.loads(l) for l in open(ROOT / a.rows) if l.strip()})
        if a.heartbeats:
            LT.HBS.update({json.loads(l)["name"]: json.loads(l)["heartbeat"] for l in open(ROOT / a.heartbeats) if l.strip()})
    inp = Path(a.input); outp = Path(a.output)
    repp = Path(a.report) if a.report else outp.with_suffix(".report.jsonl")
    if outp.resolve() == inp.resolve():
        ap.error("--output must differ from --input")
    finals = json.loads(inp.read_text())
    names = [n for n in finals if n in LT.ROWS and (not a.problems or n in a.problems)]
    missing = [n for n in finals if n not in LT.ROWS]
    if missing:
        print(f"{len(missing)} input rows are not registered problems (pass --rows): {missing[:3]}", file=sys.stderr)
    done: dict[str, dict] = {}
    if repp.exists():
        for line in repp.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("out"):
                    done[r["problem"]] = r["out"]
    todo = [n for n in names if n not in done]
    idx = {n: i for i, n in enumerate(names)}
    tag = (lambda n: f"row#{idx[n]:02d}") if a.anon else (lambda n: n[:40])
    import threading
    plock = threading.Lock()

    def log(m):
        with plock:
            print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
    pool = harvest([p.strip() for p in a.pool_sources.split(",") if p.strip()], {n: LT.ROWS[n] for n in names}, log=log) if "pool" in stages else {}
    if "pool" in stages:
        log(f"pool: {sum(len(v) for v in pool.values())} stored proofs over {len(names)} rows")
    evaluator = None
    if not a.no_compile:
        from harness.hb_tool_eval import Evaluator
        rows_all, hbs_all = dict(LT.ROWS), dict(LT.HBS)
        evaluator = lambda: Evaluator(rows_all, hbs_all, max_compiles=1 << 30)   # noqa: E731  one per row: the slot gate is shared, the counter is not
    outp.parent.mkdir(parents=True, exist_ok=True); repp.parent.mkdir(parents=True, exist_ok=True)

    def one(n):
        try:
            r = improve_row(n, finals[n], a, evaluator, pool, log=lambda m: log(m.replace(n[:40], tag(n), 1)))
        except Exception as e:  # noqa: BLE001
            r = {"problem": n, "status": f"error {type(e).__name__}: {str(e)[:160]}", "out": dict(finals[n], verified=False, stage="input")}
        with open(repp, "a") as fh:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        log(f"{tag(n)}: {r.get('status')} {r.get('input_score')} -> {(r.get('out') or {}).get('score')} ({(r.get('out') or {}).get('stage')}, {r.get('seconds', '?')}s)")
        return n, r["out"]
    with ThreadPoolExecutor(max(1, a.jobs)) as ex:
        for n, out in ex.map(one, todo):
            done[n] = out
    result = {n: done.get(n, finals[n]) for n in finals}
    outp.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    scored = [n for n in names if n in done]
    before = sum(float(finals[n].get("score") or 0) for n in scored) / max(1, len(scored))
    after = sum(float(done[n].get("score") or 0) for n in scored) / max(1, len(scored))
    unverified = sum(1 for n in scored if not done[n].get("verified", True) and done[n].get("stage") != "input")
    print(json.dumps({"rows": len(scored), "improved": sum(1 for n in scored if done[n].get("stage") not in (None, "input")),
                      "mean_before": round(before, 2), "mean_after": round(after, 2), "unverified_rows": unverified,
                      "rules_source": a.rules_source, "rules_exclude": list(a.rules_exclude),
                      "stages": {s: sum(1 for n in scored if done[n].get("stage") == s) for s in stages}}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
