#!/usr/bin/env python3
"""CLI wrapper over harness/goals.py skeleton_check (opencode line M0, cycle 89): check a draft whose unfinished parts are
`sorry` holes and print each hole's goal (scratch compile only; a draft with holes can never be banked).
Usage (from the workspace): skeleton_check.py PROBLEM [FILE]            (FILE default candidate.lean)"""
from __future__ import annotations
import os as _os, sys as _sys
if _os.environ.get("LRA_CHECK_V2") == "1":   # Claude Code driver v2 (docs/cc_driver_v2.md §4): `skeleton_check.py [FILE]`
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); import _lra_v2; _sys.exit(_lra_v2.main("skeleton_check"))

import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
from goals import skeleton_check  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("problem")
ap.add_argument("file", nargs="?", default="candidate.lean")
a = ap.parse_args()
print(json.dumps(skeleton_check(a.problem, Path(a.file).read_text()), ensure_ascii=False))
