#!/usr/bin/env python3
"""CLI wrapper over harness/lemma_search.py search (opencode line M0, cycle 89): exact?/apply? at each goal, idf-ranked
name search, same-file lemmas, simp/grind annotations, induction principles.
Usage (from the workspace): lemma_search_cli.py PROBLEM [FILE] [--top N] [--budget S]  (FILE default candidate.lean)"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
from lemma_search import search  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("problem")
ap.add_argument("file", nargs="?", default="candidate.lean")
ap.add_argument("--top", type=int, default=10)
ap.add_argument("--budget", type=float, default=120.0)
a = ap.parse_args()
r = search(a.problem, Path(a.file).read_text(), top=a.top, probes=True, budget=a.budget)
r.pop("debug", None)
print(json.dumps(r, ensure_ascii=False))
