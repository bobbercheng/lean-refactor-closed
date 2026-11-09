#!/usr/bin/env python3
"""Independently re-verify a submission-format snapshot before upload.
Each row goes through harness.leantools.lean_check against a FRESH state (best = the 33.33 reference): byte-identical statement,
forbidden-construct filter, primary compile, compile on every listed toolchain, local score. verified_path=None: nothing is
recorded anywhere (closed-model proofs never enter the bank). Prints per-row results and the mean; compares with scores.json.
Compiles: run inside a memory-capped unit.   python3 probe/heldout/verify_snapshot.py <snapshot dir>
"""
import json, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from harness.leantools import lean_check  # noqa: E402

d = Path(sys.argv[1])
rows = [json.loads(l) for l in (d / "submission.jsonl").open() if l.strip()]
claimed = json.loads((d / "scores.json").read_text())["problems"]
bench = [json.loads(l)["name"] for l in (ROOT / "data/benchmark_warmup.jsonl").open() if l.strip()]
assert [r["name"] for r in rows] == bench and all(set(r) == {"name", "proof"} for r in rows), "format"
out, scores = [], []
for r in rows:
    st = {"best": {"score": 33.33, "proof": None}, "attempts": []}
    t = lean_check(r["name"], r["proof"], st, {"kind": "verify-only"}, None)
    b = st["best"]; sc = b["score"] if b.get("proof") else 33.33
    c = b.get("compat") or {}
    scores.append(sc); out.append({"name": r["name"], "ok": t.get("ok"), "errors": (t.get("errors") or [])[:2], "score": sc,
                                   "claimed": claimed[r["name"]]["score"], "tokens": b.get("tokens"), "heartbeats": b.get("heartbeats"),
                                   "compat": f"{sum(c.values())}/{len(c)}"})
    o = out[-1]
    print(f"{r['name'][:44]:44s} ok={o['ok']} compat {o['compat']} score {sc} (snapshot {o['claimed']}) {o['errors'] or ''}", flush=True)
print(f"\nre-verified mean {statistics.mean(scores):.2f} (snapshot {statistics.mean(v['score'] for v in claimed.values()):.2f}); "
      f"all compile everywhere: {all(o['ok'] and o['compat'].split('/')[0] == o['compat'].split('/')[1] for o in out)}")
(d / "verify.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
