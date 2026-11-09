#!/usr/bin/env python3
"""CLI: python3 lean_check.py [candidate.lean]  (run from a problem workspace; env LRA_PROBLEM, LRA_RUN_ID, LRA_MODEL set by the driver)"""
import json, os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from harness.leantools import lean_check, ROOT
_f = pathlib.Path.cwd() / ".lra_env.json"   # drivers whose sandbox filters the environment (Codex) write the settings here
_cfg = json.loads(_f.read_text()) if _f.exists() else {}
def _get(k, d=None): return os.environ.get(k) or _cfg.get(k) or d
ws = pathlib.Path(_get("LRA_WORKSPACE", os.getcwd()))
name = _get("LRA_PROBLEM"); run_id = _get("LRA_RUN_ID", "cc-adhoc"); model = _get("LRA_MODEL", "claude")
path = ws / pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "candidate.lean").name
decl = path.read_text()
sp = ws / "state.json"; state = json.loads(sp.read_text()) if sp.exists() else {"problem": name, "best": {"score": 33.33, "proof": None}, "attempts": [], "runs": []}
res = lean_check(name, decl, state, {"kind": "closed-dev-only", "model": model + "@" + _get("LRA_AGENT_TAG", "claude-code"), "run_id": run_id, "mode": _get("LRA_MODE", "agent-cc")},
                 ROOT / "probe/runs" / run_id / "verified.jsonl")
sp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
if state["best"].get("proof"):
    (ws / "best.lean").write_text(state["best"]["proof"].rstrip() + "\n")
print(json.dumps(res, ensure_ascii=False, indent=1))
