#!/usr/bin/env python3
"""CLI: python3 lean_run.py <snippet.lean>   (snippet appended after the problem's imports/context; sorry allowed)"""
import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import json
from harness.leantools import lean_run
_f = pathlib.Path.cwd() / ".lra_env.json"   # see lean_check.py
_cfg = json.loads(_f.read_text()) if _f.exists() else {}
def _get(k, d=None): return os.environ.get(k) or _cfg.get(k) or d
ws = pathlib.Path(_get("LRA_WORKSPACE", os.getcwd()))
code = (ws / pathlib.Path(sys.argv[1]).name).read_text() if len(sys.argv) > 1 else sys.stdin.read()
print(lean_run(_get("LRA_PROBLEM"), code))
