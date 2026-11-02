#!/usr/bin/env python3
"""Bounded, model-free heartbeat search; opt-in, with a full-pin gate per edit.

    python3 -m harness.hb_tool --input finals.json --output results.jsonl

For a different dataset pass --dataset and --heartbeats. Existing pipeline
defaults are untouched. See docs/hb_tool_report.md for measurements and usage.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scorer.forbidden import check_forbidden
from scorer.tokenize import split_declaration

METRICS = ("ok", "tokens", "heartbeats", "L", "H", "Z", "score", "compat")


def _metrics(result):
    return {key: result[key] for key in METRICS if key in result}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _valid(result, versions, full):
    """Fail closed for incomplete measurements, including a missing counter."""
    if not result.get("ok") or not all(_finite(result.get(k)) for k in ("tokens", "heartbeats", "L", "H", "Z", "score")):
        return False
    if result["heartbeats"] < 0 or result["tokens"] < 0:
        return False
    if full:
        compat = result.get("compat", {})
        if set(compat) != set(versions) or not all(isinstance(v, bool) for v in compat.values()):
            return False
        expected_z = 100 * sum(compat.values()) / len(versions)
        return compat[versions[0]] and abs(result["Z"] - expected_z) < 1e-8
    return True


def _gain(candidate, incumbent, floor, margin):
    return (candidate["score"] - max(incumbent["score"], floor) > margin + 1e-9
            and candidate["H"] >= incumbent["H"]
            and candidate["heartbeats"] <= incumbent["heartbeats"])


def improve(name, proof, *, base=None, statement=None, versions=None,
            evaluate_fn=None, candidate_fn=None, max_compiles=60, min_gain=0.05,
            deadline=None, clock=time.monotonic, rows=None, heartbeats=None):
    """Return the unchanged or fully verified improved declaration and audit log.

    ``evaluate_fn(decl, full)`` is injectable for tests. It returns scorer metrics,
    a per-version ``compat`` map on full evaluations, and optionally actual
    ``compiles``. Its optional ``cost(full)`` bounds physical compiler launches.
    ``deadline`` is an absolute monotonic time; it stops new trials, never skips
    verification of an edit already in flight. ``base`` is a stored input score,
    not a substitute for measuring the input on every supported toolchain.
    """
    if not isinstance(max_compiles, int) or isinstance(max_compiles, bool) or max_compiles < 0:
        raise ValueError("max_compiles must be a nonnegative integer")
    if not _finite(min_gain) or min_gain < 0.05:
        raise ValueError("min_gain must be at least 0.05")
    if statement is None or versions is None or evaluate_fn is None:
        from harness.hb_tool_eval import Evaluator, load_dataset
        if rows is None:
            rows, default_hbs = load_dataset(ROOT / "data/benchmark_warmup.jsonl", ROOT / "data/benchmark_heartbeats.jsonl")
            if heartbeats is None:
                heartbeats = default_hbs
        row = rows[name]
        statement = row["statement"] if statement is None else statement
        evaluator = Evaluator(rows, heartbeats or {}, max_compiles=max_compiles)
        versions = evaluator.versions(name) if versions is None else versions
        if evaluate_fn is None:
            evaluate_fn = evaluator.bound(name, versions)
    versions = list(versions)
    if not versions or len(set(versions)) != len(versions):
        raise ValueError("versions must contain unique supported toolchains")
    if candidate_fn is None:
        from harness.hb_tool_candidates import candidates
        candidate_fn = candidates
    report = {"problem": name, "status": "no gain", "proof": proof, "before": {}, "after": {},
              "compiles": 0, "max_compiles": max_compiles, "min_gain": min_gain,
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
        method = getattr(evaluate_fn, "cost", None)
        return int(method(full)) if method else (len(versions) if full else 1)

    def evaluate(decl, full):
        bound = cost(full)
        if report["compiles"] + bound > max_compiles:
            raise RuntimeError("compile reservation exceeded")
        try:
            result = dict(evaluate_fn(decl, full))
        except Exception as exc:
            # Failed evaluations can have launched compilers. Charge the entire
            # reservation, preserve the latest verified proof, and report it.
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "compiles": bound}
        actual = result.get("compiles", bound)
        if not isinstance(actual, int) or actual < 0 or actual > bound:
            raise ValueError("evaluator violated its compiler reservation")
        report["compiles"] += actual
        return result

    if cost(True) > max_compiles:
        report.update(status="budget too small", stopped="max-compiles")
        return report
    initial = evaluate(proof, True)
    report["before"] = report["after"] = _metrics(initial)
    if not _valid(initial, versions, True):
        report.update(status="input does not compile" if not initial.get("ok") else "incomplete baseline",
                      error=initial.get("error"))
        return report
    best = initial
    floor = max(initial["score"], base["score"]) if base and _finite(base.get("score")) else initial["score"]
    seen = {proof}
    started = clock()
    while True:
        changed = False
        sites = list(candidate_fn(body))
        for site in sites:
            if deadline is not None and clock() >= deadline:
                report["stopped"] = "deadline"
                break
            # Reserve confirmation before launching a primary trial. This
            # counts physical compiles, including scorer validity guards.
            if report["compiles"] + cost(False) + cost(True) > max_compiles:
                report["stopped"] = "max-compiles"
                break
            from harness.normalize import apply
            candidate = head + apply(body, [site])
            if candidate in seen:
                continue
            seen.add(candidate)
            candidate_body = split_declaration(candidate, statement)
            if candidate_body is None or check_forbidden(candidate_body):
                continue
            trial = evaluate(candidate, False)
            attempt = {"kind": site.kind, "note": site.note,
                       "sha256": hashlib.sha256(candidate.encode()).hexdigest(),
                       "primary": _metrics(trial), "accepted": False}
            report["attempts"].append(attempt)
            if not _valid(trial, versions, False):
                attempt.update(reason="compile failed or incomplete measurement", error=trial.get("error"))
                continue
            # A partial evaluation assumes all pins pass; compare it using the
            # incumbent's actual Z when the original is partially compatible.
            provisional = dict(trial)
            provisional["score"] = round((trial["L"] + trial["H"] + best["Z"]) / 3, 2)
            if not _gain(provisional, best, floor, min_gain):
                attempt["reason"] = "score margin or heartbeat gate"
                continue
            checked = evaluate(candidate, True)
            attempt["verified"] = _metrics(checked)
            if not _valid(checked, versions, True):
                attempt.update(reason="full verification failed", error=checked.get("error"))
                continue
            if checked["compat"] != initial["compat"] or checked["Z"] != initial["Z"]:
                attempt["reason"] = "toolchain compatibility changed"
                continue
            if not _gain(checked, best, floor, min_gain):
                attempt["reason"] = "confirmed score margin or heartbeat gate"
                continue
            attempt["accepted"] = True
            report["applied"][site.kind] = report["applied"].get(site.kind, 0) + 1
            report.update(status="improved", proof=candidate, after=_metrics(checked))
            body = split_declaration(candidate, statement)
            best = checked
            changed = True
            break  # Recompute offsets and eligibility after every accepted edit.
        if not changed:
            break
    report["seconds"] = round(clock() - started, 3)
    report["gain"] = round(best["score"] - initial["score"], 2)
    return report


def run_batch(finals, *, rows, heartbeats, jobs=3, max_compiles=60,
              min_gain=0.05, deadline_s=None):
    """Yield (input key, report); no model calls or writes to pipeline state."""
    if jobs not in (1, 2, 3):
        raise ValueError("jobs must be between 1 and 3")

    def run(key, item):
        name = item.get("problem", key)
        started = time.monotonic()
        try:
            result = improve(name, item["proof"], base=item, rows=rows, heartbeats=heartbeats,
                             max_compiles=max_compiles, min_gain=min_gain,
                             deadline=None if deadline_s is None else started + deadline_s)
        except Exception as exc:
            result = {"problem": name, "status": "error", "error": f"{type(exc).__name__}: {exc}",
                      "proof": item.get("proof"), "before": {}, "after": {}}
        result.update(input_key=key, stored={k: item[k] for k in ("score", "L", "H", "Z", "raw_L", "raw_H") if k in item},
                      seconds=round(time.monotonic() - started, 3))
        if "arm" in item:
            result["arm"] = item["arm"]
        return key, result

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run, key, item) for key, item in finals.items()]
        for future in as_completed(futures):
            yield future.result()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/benchmark_warmup.jsonl")
    parser.add_argument("--heartbeats", type=Path, default=ROOT / "data/benchmark_heartbeats.jsonl")
    parser.add_argument("--jobs", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--max-compiles", type=int, default=60)
    parser.add_argument("--min-gain", type=float, default=0.05)
    parser.add_argument("--deadline-s", type=float)
    args = parser.parse_args(argv)
    if args.output.resolve() in {args.input.resolve(), args.dataset.resolve(), args.heartbeats.resolve()}:
        parser.error("--output must differ from the input and reference datasets")
    from harness.hb_tool_eval import load_dataset
    rows, hbs = load_dataset(args.dataset, args.heartbeats)
    finals = json.loads(args.input.read_text())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    reports = []
    with args.output.open("w") as out:
        for _, report in run_batch(finals, rows=rows, heartbeats=hbs, jobs=args.jobs,
                                   max_compiles=args.max_compiles, min_gain=args.min_gain, deadline_s=args.deadline_s):
            reports.append(report)
            out.write(json.dumps(report, ensure_ascii=False) + "\n")
            out.flush()
            print(f"row {len(reports)}/{len(finals)}: {report['status']}, "
                  f"compiles={report.get('compiles', '?')}, gain={report.get('gain', 0):+.2f}", flush=True)
    complete = all(r["status"] in ("improved", "no gain") for r in reports)
    summary = {"rows": len(reports), "verified": sum(r["status"] in ("improved", "no gain") for r in reports),
               "improved": sum(r["status"] == "improved" for r in reports),
               "compiles": sum(r.get("compiles", 0) for r in reports)}
    if complete and reports:
        for metric in ("H", "L", "score"):
            summary[metric] = {phase: round(sum(r[phase][metric] for r in reports) / len(reports), 4)
                               for phase in ("before", "after")}
    print(json.dumps(summary, sort_keys=True))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
