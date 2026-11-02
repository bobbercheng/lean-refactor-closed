#!/usr/bin/env python3
"""Pre-upload check for the known lakefile-options gap (2026-10-11 panel finding): `lake env lean` on a scratch file ignores a
project's lakefile leanOptions, so a proof could pass locally and fail on a worker that applies them. Compiles the Strata rows with
-DwarningAsError=true and the ArkLib rows with -DautoImplicit=false on every listed toolchain, for the snapshot proof and, as a
control, the reference proof. Nothing is recorded. Run inside a memory-capped unit.
  python3 probe/heldout/optcheck_snapshot.py <snapshot dir>
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from scorer.compile import compile_project  # noqa: E402
from harness.leantools import newest_first  # noqa: E402

FLAGS = {"strata": ("-DwarningAsError=true",), "arklib": ("-DautoImplicit=false",)}
rows = {json.loads(l)["name"]: json.loads(l) for l in (ROOT / "data/benchmark_warmup.jsonl").open() if l.strip()}
sub = [json.loads(l) for l in (Path(sys.argv[1]) / "submission.jsonl").open() if l.strip()]
bad = 0
for s in sub:
    row = rows[s["name"]]
    if row["source"] not in FLAGS:
        continue
    for v in newest_first(row["version_info"]):
        for tag, decl in (("snapshot", s["proof"]), ("reference", row["src"])):
            r = compile_project(row, decl, v, count=False, lean_args=FLAGS[row["source"]])
            bad += (tag == "snapshot" and not r.ok)
            print(f"{s['name'][:40]:40s} {v:12s} {FLAGS[row['source']][0]:22s} {tag:9s} ok={r.ok} {(r.errors or [])[:1]}", flush=True)
print(f"\nsnapshot rows failing under the lakefile options: {bad}")
