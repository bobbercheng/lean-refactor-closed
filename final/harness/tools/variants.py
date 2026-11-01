#!/usr/bin/env python3
"""Variant files for one lean_check_variants batch (Claude Code driver v2, 2026-10-12 G0b smoke: shell loops writing files are refused under
dontAsk, and one `cp` per variant costs a turn each). Copies SRC (default candidate.lean) to v1.lean .. vN.lean in the workspace (N <= 6),
overwriting earlier variants, and prints their names; then Read and Edit each one.
Usage (from the workspace): variants.py N [SRC]"""
from __future__ import annotations
import json, shutil, sys
from pathlib import Path

args = sys.argv[1:]
if not args or not args[0].isdigit() or not 1 <= int(args[0]) <= 6 or len(args) > 2:
    sys.exit("usage: variants.py N [SRC]   (1 <= N <= 6; SRC a workspace file, default candidate.lean)")
src = Path(args[1] if len(args) > 1 else "candidate.lean")
if src.name != str(src) or not src.is_file():   # workspace basenames only
    sys.exit(f"variants.py: {src} is not a file in the workspace")
made = []
for i in range(1, int(args[0]) + 1):
    shutil.copyfile(src, f"v{i}.lean"); made.append(f"v{i}.lean")
print(json.dumps({"copied_from": src.name, "variants": made, "next": "Read each vK.lean, Edit it, then ONE lean_check_variants.py call"}))
