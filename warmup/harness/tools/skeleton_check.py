#!/usr/bin/env python3
"""CLI wrapper over harness/goals.py skeleton_check (opencode line M0, cycle 89): check a draft whose unfinished parts are
`sorry` holes and print each hole's goal (scratch compile only; a draft with holes can never be banked).
Usage (from the workspace): skeleton_check.py PROBLEM [FILE]            (FILE default candidate.lean)"""
from __future__ import annotations

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
