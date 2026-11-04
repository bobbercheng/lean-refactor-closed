#!/usr/bin/env python3
"""Leak check for harness/pattern_cards.py (2026-10-13): no card may contain a warm-up theorem name, a problem-local identifier from the
warm-up statements, or a name from the theorem-keyed briefs that is not general library vocabulary. Plus selection sanity checks.
    python3 harness/test_pattern_cards.py"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from harness.pattern_cards import PATTERN_CARDS, pattern_cards_for  # noqa: E402

rows = [json.loads(l) for l in open(ROOT / "data/benchmark_warmup.jsonl") if l.strip()]
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_'₀-₉ₛₗ]*(?:\.[A-Za-z_][A-Za-z0-9_'₀-₉ₛₗ]*)*")
# general vocabulary allowed even if it appears in a warm-up statement (Lean / Mathlib roots and common binder names)
GENERAL = {"List", "Nat", "Set", "Finset", "Fintype", "Polynomial", "AlgHom", "LinearMap", "ENNReal", "Exists", "Or", "And", "True", "False",
           "Nonempty", "Subset", "fun", "by", "have", "let", "match", "with", "in", "at", "only", "simp", "rw", "grind", "induction", "exists",
           "refine", "apply", "exact", "intro", "rintro", "obtain", "first", "repeat", "assumption", "constructor", "omega", "ring", "conv",
           "set", "use", "rfl", "x", "f", "h", "s", "t", "a", "b", "c", "k", "m", "n", "e", "A", "B", "C", "D", "K", "F", "S", "I", "Type",
           # English words / keywords that also occur in statements (false positives of the identifier scan; reviewed 2026-10-13)
           "_", "lemma", "open", "vs", "g", "relation", "then", "if", "Measure"}
# problem-local names seen in the theorem-keyed briefs (probe/oline-knowledge/*.md)
BRIEF_LOCAL = {"getVars", "substOld", "LExpr", "updatedStates", "updatedStatesComm", "ChoiceBisim", "Tr", "Red", "qMap", "Fin2ToF2", "BBF_Code",
               "distFromCode", "multilinearCombine", "finMapTwoWords", "crAnTimeOrderSign", "koszulSign", "Space", "electricField",
               "InitStatesNotDefined", "UpdateStatesLength", "extractOldExprVars", "Ka_irreducible", "I_irreducible", "fiberwiseClose",
               "prob_uniform_singleton_finFun_eq", "jointProximityNat", "Bisimilarity", "HomBisimilarity", "ParallelReduction",
               "iteratedQuotientMap_k_eq_1_is_qMap", "qMap_total_fiber_one_level_eq", "ofCrAnListF", "timeOrderF", "mulLinearMap_apply",
               "is_fiber_iff_generates_quotient_point", "FreeSpace", "Typing", "canonical_form_abs", "body_let", "body_case"}

fails = []
names = {r["name"] for r in rows} | {r["name"].split(".")[-1] for r in rows}
stmt_ids = set()
for r in rows:
    for t in IDENT.findall(r["statement"]):
        stmt_ids.add(t); stmt_ids.update(t.split("."))
deny = (stmt_ids - GENERAL) | BRIEF_LOCAL | names
for name, rx, text in PATTERN_CARDS:
    toks = set(IDENT.findall(text)); toks |= {p for t in toks for p in t.split(".")}
    bad = sorted(toks & deny)
    if bad:
        fails.append(f"{name}: problem-specific identifier(s) {bad}")
    if re.search(r"\b\d{2}\.\d{2}\b", text):
        fails.append(f"{name}: looks like a landmark score")
print("PASS leak check" if not fails else "FAIL leak check:\n  " + "\n  ".join(fails))

ok = True
s = pattern_cards_for("theorem t (l : List ℕ) : a ∈ f l → a ∈ g l", "by\n  fun_induction f l <;> grind")
ok &= "MEMBERSHIP" in s and s.count("PATTERN:") <= 2
ok &= pattern_cards_for("theorem t : True", "by trivial") == ""
ok &= pattern_cards_for("theorem t (x : ℕ∞) : x ≤ x", "", k=3).count("PATTERN:") <= 3
print("PASS selection" if ok else "FAIL selection")
sys.exit(0 if (ok and not fails) else 1)
