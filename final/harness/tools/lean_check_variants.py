#!/usr/bin/env python3
"""CLI: python3 lean_check_variants.py a.lean b.lean ...  (run from a problem workspace, like lean_check.py)
Batch compile for the closed-model drivers (docs/break_90_panel.md: the Opus line compiled one file at a time): each file is checked
exactly as lean_check.py checks candidate.lean (scored, recorded in state.json, a verified record when it beats the best), then one
compact table is printed, best first. Files are checked one after another, so the state never races."""
import os as _os, sys as _sys
if _os.environ.get("LRA_CHECK_V2") == "1":   # Claude Code driver v2 (docs/cc_driver_v2.md §4): <= 6 files, the winner copied to candidate.lean
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); import _lra_v2; _sys.exit(_lra_v2.main("lean_check_variants"))
import json, os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from harness.leantools import lean_check, ROOT
_f = pathlib.Path.cwd() / ".lra_env.json"
_cfg = json.loads(_f.read_text()) if _f.exists() else {}
def _get(k, d=None): return os.environ.get(k) or _cfg.get(k) or d
ws = pathlib.Path(_get("LRA_WORKSPACE", os.getcwd()))
name = _get("LRA_PROBLEM"); run_id = _get("LRA_RUN_ID", "cc-adhoc"); model = _get("LRA_MODEL", "claude")
files = sys.argv[1:]
if not files:
    print("usage: lean_check_variants.py a.lean b.lean ...  (up to 8 files)"); sys.exit(2)
if len(files) > 8:
    print(f"WARNING: {len(files)} files given; only the first 8 run (tool cap) — split the rest into a second call")
sp = ws / "state.json"
rows = []
for fn in files[:8]:
    path = ws / pathlib.Path(fn).name
    if not path.exists():
        rows.append({"file": fn, "ok": False, "error": "no such file in the workspace"}); continue
    state = json.loads(sp.read_text()) if sp.exists() else {"problem": name, "best": {"score": 33.33, "proof": None}, "attempts": [], "runs": []}
    res = lean_check(name, path.read_text(), state, {"kind": "closed-dev-only", "model": model + "@" + _get("LRA_AGENT_TAG", "claude-code"), "run_id": run_id,
                                                     "mode": _get("LRA_MODE", "agent-cc")}, ROOT / "probe/runs" / run_id / "verified.jsonl")
    sp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    if state["best"].get("proof"):
        (ws / "best.lean").write_text(state["best"]["proof"].rstrip() + "\n")
    rows.append({"file": fn, "ok": res.get("ok"), "tokens": res.get("tokens"), "heartbeats": res.get("heartbeats"),
                 "predicted": res.get("predicted_score_if_compatible"), "score": res.get("score"), "new_best": bool(res.get("new_best")),
                 "error": (res.get("errors") or [None])[0], "auto_fixed": res.get("auto_fixed")})
rows.sort(key=lambda r: (not r.get("ok"), -(r.get("score") or r.get("predicted") or 0)))
best = json.loads(sp.read_text())["best"] if sp.exists() else {}
print(json.dumps({"variants": rows, "best_after": {k: best.get(k) for k in ("score", "tokens", "heartbeats")}}, ensure_ascii=False, indent=1))
