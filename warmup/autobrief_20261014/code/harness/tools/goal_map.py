#!/usr/bin/env python3
"""CLI wrapper over harness/goals.py goal_map (opencode line M0, cycle 89): insert a trace_state before every top-level step
and print each step's goal, so an external agent can see the goal map without the in-process tool.
Usage (from the workspace): goal_map.py PROBLEM [FILE] [--depth N]      (FILE default candidate.lean)"""
from __future__ import annotations
import os as _os, sys as _sys
if _os.environ.get("LRA_CHECK_V2") == "1":   # Claude Code driver v2 (docs/cc_driver_v2.md §4): `goal_map.py [FILE] [--depth N]`
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); import _lra_v2; _sys.exit(_lra_v2.main("goal_map"))

import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
from goals import goal_map  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("problem")
ap.add_argument("file", nargs="?", default="candidate.lean")
ap.add_argument("--depth", type=int, default=1)
a = ap.parse_args()
decl = Path(a.file).read_text()
print(json.dumps(goal_map(a.problem, decl, depth=a.depth), ensure_ascii=False))
