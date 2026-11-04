#!/usr/bin/env python3
"""CLI (Claude Code driver v2 only, round 2 2026-10-12; docs/cc_driver_v2.md §7/§9): python3 normalize_check.py [FILE] [--no-polish]
The lexer normalizer (harness/normalize.py) and the heartbeat polish (harness/hb_polish.py: `?`-certificates -> `only` lists, unused `only`
lemmas pruned) on a COMPILING workspace file (default candidate.lean), each kept only where strictly better with Z unchanged; a changed proof is
written to normalized.lean, checked and banked through the v2 lean_check path, and copied to candidate.lean on a new best."""
import os as _os, sys as _sys
if _os.environ.get("LRA_CHECK_V2") != "1":   # no v1 form: the v1 drivers (and Codex) never advertise this tool
    print('{"ok": false, "errors": ["normalize_check.py is a driver v2 tool (LRA_CHECK_V2=1)"]}'); _sys.exit(2)
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); import _lra_v2; _sys.exit(_lra_v2.main("normalize_check"))
