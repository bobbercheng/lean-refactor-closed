#!/usr/bin/env python3
"""CLI wrapper over harness/mine.py mine (opencode line, cycle 92): try one automation closer (grind, simp_all, aesop,
omega, fun_prop, norm_num, linarith, positivity, tauto, exact?) in place of every block of the proof and report which
blocks each closer closes — the biggest single-block wins first.
Usage (from the workspace): lean_mine.py PROBLEM [FILE] [--jobs N]        (FILE default candidate.lean)"""
from __future__ import annotations
import os as _os, sys as _sys
if _os.environ.get("LRA_CHECK_V2") == "1":   # Claude Code driver v2 (docs/cc_driver_v2.md §4): `lean_mine.py [FILE]`, banks mined.lean
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); import _lra_v2; _sys.exit(_lra_v2.main("lean_mine"))

import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
from mine import mine  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("problem")
ap.add_argument("file", nargs="?", default="candidate.lean")
ap.add_argument("--jobs", type=int, default=6)
a = ap.parse_args()
print(json.dumps(mine(a.problem, Path(a.file).read_text(), jobs=a.jobs, log=lambda *m: None), ensure_ascii=False))
