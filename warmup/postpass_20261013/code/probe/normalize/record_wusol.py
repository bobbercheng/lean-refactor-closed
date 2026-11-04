#!/usr/bin/env python3
"""Record the lexer normalizer's improved bests of the held closed warm-up entry (the agent.py + Sol ladder, wu-hx-sol; 2026-10-13:
$0 passes, docs/warmup_from_set3_review.md). Like probe/normalize/record_a100.py: reads probe/normalize/wu-sol<tag>.jsonl
(harness/normalize.py --bests wu-sol), re-checks every improved proof with harness.leantools.lean_check (byte-identical statement, forbidden
constructs, primary compile, toolchain compatibility, strictly better than the line's best) under the line's own provenance, marked
`normalized`. Unlike record_a100.py it updates the line's state files (the lineage continues from the normalized best: the transfer sweep
that follows mines and banks into the same root); each state is rewritten only after a strict gain. Records go to
~/source/lra-ab/wu-hx/probe/runs/wu-hx-sol-normalize1/verified.jsonl (leaderboard/problem_scores.py counts them toward wu-sol). Closed-model
results: never banked. API spend $0 (CPU only), so the rows stay within their capped lineage.
Compiles: run inside a memory-capped unit.   python3 probe/normalize/record_wusol.py [--tag T]
"""
import argparse, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from harness.leantools import lean_check  # noqa: E402

WR = Path.home() / "source/lra-ab/wu-hx/harness/hwork/wu-sol"
OUT = Path.home() / "source/lra-ab/wu-hx/probe/runs/wu-hx-sol-normalize1"
ap = argparse.ArgumentParser(); ap.add_argument("--tag", default=""); a = ap.parse_args()
res = [json.loads(l) for l in (ROOT / f"probe/normalize/wu-sol{a.tag}.jsonl").open() if l.strip()]
paths = {}
for p in WR.glob("*/state.json"):
    paths[json.loads(p.read_text())["problem"]] = p
OUT.mkdir(parents=True, exist_ok=True)
sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
gain = 0.0
for r in res:
    if r.get("status") != "improved":
        continue
    sp = paths[r["problem"]]; st = json.loads(sp.read_text()); before = (st.get("best") or {}).get("score")
    prov = {"kind": "closed-dev-only", "model": "gpt-6.1-sol@openrouter", "run_id": "wu-hx-sol-normalize1", "mode": "agent",
            "normalized": r.get("applied"), "normalizer": f"harness/normalize.py@{sha}"}
    t = lean_check(r["problem"], r["proof"], st, prov, OUT / "verified.jsonl")
    after = (st.get("best") or {}).get("score")
    better = bool(after and before and after > before)
    if better:
        sp.write_text(json.dumps(st, ensure_ascii=False, indent=1))
        (sp.parent / "best.lean").write_text(st["best"]["proof"].rstrip() + "\n")
        gain += after - before
    print(f"{r['problem'][:44]:44s} ok={t.get('ok')} tok {t.get('tokens')} hb {t.get('heartbeats')} Z {t.get('Z')} score {before} -> {after}"
          f"{'  RECORDED' if better else '  (not better: not recorded)'}", flush=True)
print(f"wu-sol normalize: summed gain {gain:+.2f} = {gain / 15:+.3f} on the 15-row line")
