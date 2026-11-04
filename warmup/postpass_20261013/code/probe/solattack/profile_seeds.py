"""Heartbeat profiles of the champions a Sol attack starts from (docs/opus_sol_attack_plan.md step 2, 2026-10-13): harness/profile.py on each
problem's best.lean in a source work root, saved to OUT (JSON {problem: profile}). Lean compiles: run it in a memory-capped systemd unit,
never from the session shell. Problems already in OUT are kept (resumable).
    python3 probe/solattack/profile_seeds.py SRC_ROOT OUT.json PROBLEM ... [--max-cuts 10]"""
import argparse, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "harness")]
from profile import profile  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src_root"); ap.add_argument("out"); ap.add_argument("problems", nargs="+")
ap.add_argument("--max-cuts", type=int, default=10)
a = ap.parse_args()
out = Path(a.out); res = json.loads(out.read_text()) if out.exists() else {}
by_name = {}
for f in Path(a.src_root).glob("*/state.json"):
    by_name[json.loads(f.read_text())["problem"]] = f.parent
for n in a.problems:
    if n in res:
        continue
    d = by_name.get(n)
    if not d or not (d / "best.lean").exists():
        print(f"{n}: no best.lean in {a.src_root}", flush=True); continue
    t = time.time()
    try:
        res[n] = profile(n, (d / "best.lean").read_text(), max_cuts=a.max_cuts)
    except Exception as e:  # noqa: BLE001
        res[n] = {"ok": False, "note": f"{type(e).__name__}: {e}"[:300]}
    out.write_text(json.dumps(res, indent=1))
    p = res[n]
    print(f"{n}: ok {p.get('ok')} total {p.get('total')} floor {p.get('floor')} H-left {p.get('points_left_heartbeats')} "
          f"blocks {len(p.get('blocks') or [])} ({time.time() - t:.0f} s)", flush=True)
