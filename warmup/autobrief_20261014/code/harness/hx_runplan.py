#!/usr/bin/env python3
"""Resumable pass runner for the hosted-model arms (2026-10-11, after the second OOM). Runs a named plan's passes in order;
for each pass it skips problems that already have a `DONE best` line in that pass's log (probe/<run-id>.log), appends to
the same log, and logs progress to probe/hx-<plan>.log. Problem names in agent logs are truncated to 18 chars, so DONE lines
are matched by that prefix.     python3 harness/hx_runplan.py <plan>      plans: sol15, ds10, hr10, termcard
"""
from __future__ import annotations

import pathlib, re, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
REST10 = (ROOT / "probe/oline-knowledge/REST10.txt").read_text().split()
PILOT5 = ["CallElimCorrect.extractedOldExprInVars", "Cslib.CCS.bisimilarity_congr_choice",
          "FieldSpecification.WickAlgebra.ι_timeOrderF_superCommuteF_eq_time",
          "Binius.BinaryBasefold.fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius", "putnam_1964_b2"]
COMMON = ["--turns", "40", "--no-adaptive-turns", "--max-tokens", "4000", "--budget-usd", "2.85"]   # 2026-10-11: cap $2.85/problem (hard bound in agent.py)
BRIEFS = ["--brief-dir", "probe/oline-knowledge"]
FRESH = ["--from-reference", "--brief", "restructure"]
# (run_id, preset, effort, work_root, workers, extra, problems)
PLANS = {
    "sol15": [("hx-solknow-x10a", "gpt-6.1-sol", "medium", "solknow", 2, BRIEFS, REST10),
              ("hx-solknow-x10b", "gpt-6.1-sol", "medium", "solknow", 2, BRIEFS, REST10),
              ("hx-solknow-x10c", "gpt-6.1-sol", "medium", "solknow", 2, BRIEFS, REST10)],
    "ds10": [("hx-dsknow-x10a", "deepseek-v4.1-flash", "medium", "dsknow", 2, BRIEFS, REST10),
             ("hx-dsknow-x10b", "deepseek-v4.1-flash", "medium", "dsknow", 2, BRIEFS + FRESH, REST10),
             ("hx-dsknow-x10c", "deepseek-v4.1-flash", "medium", "dsknow", 2, BRIEFS, REST10),
             ("hx-ds-c2", "deepseek-v4.1-flash", "medium", "ds", 1, [], ["CallElimCorrect.extractedOldExprInVars"])],
    "hr10": [("hx-haiku-x10a", "haiku-5.5", "medium", "haiku", 1, [], REST10),
             ("hx-haiku-x10b", "haiku-5.5", "medium", "haiku", 1, [], REST10),
             ("hx-haiku-x10c", "haiku-5.5", "medium", "haiku", 1, [], REST10),
             ("hx-router-x10a", "haiku-5.5", "medium", "router", 1, [], REST10),
             ("hx-router-x10b", "sonnet-5.5", "high", "router", 1, FRESH, REST10),
             ("hx-router-x10c", "haiku-5.5", "medium", "router", 1, [], REST10)],
    "termcard": [("hx-tcab-base", "gpt-6.1-sol", "medium", "tc-base", 2, BRIEFS, PILOT5),
                 ("hx-tcab-card", "gpt-6.1-sol", "medium", "tc-card", 2, BRIEFS + ["--term-card"], PILOT5)],
}


def done_in(log: pathlib.Path) -> set[str]:
    if not log.exists():
        return set()
    return {m.group(1).strip() for m in re.finditer(r"^(.{18}) DONE best", log.read_text(), re.M)}


def main() -> int:
    plan = sys.argv[1]
    plog = ROOT / f"probe/hx-{plan}.log"
    def say(msg: str) -> None:
        line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime())}] {msg}"
        print(line, flush=True); plog.open("a").write(line + "\n")
    say(f"plan {plan}: resume")
    for run_id, preset, eff, root, workers, extra, probs in PLANS[plan]:
        log = ROOT / f"probe/{run_id}.log"
        done = done_in(log)
        todo = [p for p in probs if p[:18] not in done]
        if not todo:
            say(f"{run_id}: all {len(probs)} done"); continue
        say(f"{run_id}: {len(todo)} to run ({len(probs) - len(todo)} done)")
        cmd = ["python3", "harness/agent.py", "--model-preset", preset, "--reasoning-effort", eff, *COMMON, "--workers", str(workers),
               "--work-root", f"harness/hwork/{root}", "--run-id", run_id, *extra, "--problems", *todo]
        with log.open("a") as f:
            subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
        say(f"{run_id}: pass done ({len(done_in(log))} of {len(probs)} problems done)")
    say(f"PLAN {plan} DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
