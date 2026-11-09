#!/usr/bin/env python3
"""Token count of a proof file with the arena's exact lexer, without compiling (opencode line, cycle 92).
Usage (from the workspace): tok_count.py [FILE ...]      (default: candidate.lean best.lean)"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scorer.tokenize import count_tokens  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="*", default=["candidate.lean", "best.lean"])
a = ap.parse_args()
out = {}
for f in a.files:
    p = Path(f)
    if p.exists():
        out[f] = count_tokens(p.read_text())
print(json.dumps(out))
