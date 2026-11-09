#!/usr/bin/env python3
"""CLI wrapper over harness/profile.py profile (opencode line M0, cycle 89): measure heartbeats per block of the proof
(compile-free cuts), so an external agent can aim at the costliest block.
Usage (from the workspace): heartbeat_profile.py PROBLEM [FILE] [--max-cuts N]   (FILE default best.lean)"""
from __future__ import annotations
import os as _os, sys as _sys
if _os.environ.get("LRA_CHECK_V2") == "1":   # Claude Code driver v2 (docs/cc_driver_v2.md §4): `heartbeat_profile.py [FILE]`, candidate.lean default
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); import _lra_v2; _sys.exit(_lra_v2.main("heartbeat_profile"))

import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
from profile import profile  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("problem")
ap.add_argument("file", nargs="?", default="best.lean")
ap.add_argument("--max-cuts", type=int, default=12)
a = ap.parse_args()
print(json.dumps(profile(a.problem, Path(a.file).read_text(), max_cuts=a.max_cuts), ensure_ascii=False))
