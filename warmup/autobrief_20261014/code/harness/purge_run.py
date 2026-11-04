#!/usr/bin/env python3
"""Remove a dead run (no work done: network outage, failed launch) from a work root so it cannot skew adaptive budgets.

  python3 harness/purge_run.py <work_root> <run_id> [<run_id> ...]   [--dry-run]

Removes the run's entries from every <work_root>/*/state.json `runs` list (a dead run still appends one entry per problem,
and its `mode` tags — fresh / structural — feed the fresh-start cap and plateau logic). Refuses to purge a run that has any
recorded attempt (that run did real work). A backup of each touched state.json is written next to it as state.json.bak-<ts>.
"""
import json, pathlib, sys, time

args = [a for a in sys.argv[1:] if not a.startswith("--")]
dry = "--dry-run" in sys.argv
root, runs = pathlib.Path(args[0]), set(args[1:])
assert root.is_dir() and runs, __doc__
files = sorted(root.glob("*/state.json"))
for f in files:  # safety first: no attempts from these runs anywhere
    bad = [a for a in json.loads(f.read_text()).get("attempts", []) if a.get("run_id") in runs]
    if bad:
        sys.exit(f"refusing: {f.parent.name} has {len(bad)} attempts from {sorted({a['run_id'] for a in bad})} (not a dead run)")
ts = time.strftime("%Y%m%dT%H%M%S")
n = 0
for f in files:
    st = json.loads(f.read_text())
    keep = [r for r in st.get("runs", []) if r.get("run_id") not in runs]
    k = len(st.get("runs", [])) - len(keep)
    if k and not dry:
        f.with_name(f"state.json.bak-{ts}").write_text(f.read_text())
        st["runs"] = keep; f.write_text(json.dumps(st, indent=1, ensure_ascii=False))
    n += k
print(f"{'would remove' if dry else 'removed'} {n} run entries for {sorted(runs)} across {len(files)} problems")
