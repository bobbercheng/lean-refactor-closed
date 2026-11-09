"""Pattern-keyed general knowledge (2026-10-13).

The theorem-keyed knowledge briefs (probe/oline-knowledge/<problem>.md: landmark scores, tested tactic lines, problem-local names) are a
'targeted optimization' risk in the final (the organizers review the code and report; the 15 warm-up rows are part of the final). This module
keeps what generalizes: techniques, selected by the SHAPE of the statement and proof, never by a theorem name, with no problem-local
identifier, no lemma that won a dev row, no measured number and no proof fragment (harness/test_pattern_cards.py and harness/leak_scan.py). Opt-in: agent.py --pattern-cards appends at most K cards after the technique cards; off by default (every default prompt unchanged).
"""
from __future__ import annotations

import re

# (name, detector over statement + current proof, text). Order = priority when more than K detectors fire.
PATTERN_CARDS: list[tuple[str, re.Pattern, str]] = [
    # 2026-10-21 (B62a): techniques only. No lemma that won a dev row, no
    # measured number, no proof fragment; harness/leak_scan.py enforces it. Simp-set engineering first: 3+ simp calls is a strong signal.
    ("simp_engineering",
     re.compile(r"simp[\s\S]*simp[\s\S]*simp", re.S),
     "PATTERN: SIMP-SET ENGINEERING (several simp calls on one goal). (1) Merging two adjacent simp calls rarely pays by itself (simultaneous "
     "rewriting changes the normal form): merge only lemmas that act on the same subterm, and check. (2) A hypothesis rewritten by `simp .. at h` "
     "and then used once can be passed as a simp lemma to the next call (`simp [.., h]`) instead, dropping the `at h` call and its `rw`. "
     "(3) Put the lemma that proves a side condition into the same simp set (raise `maxDischargeDepth` if needed) instead of a separate `have`. "
     "(4) A lemma whose side condition the discharger cannot prove is tried and fails on every matching subterm: that is where heartbeats go. "
     "Replace it by a variant without the side condition when one exists. (5) Structure-specific forms of a lemma can avoid typeclass searches "
     "that the generic form triggers: compile both. (6) Keep lemmas at one level of abstraction; do not unfold to a general form and back. "
     "(7) `simp_all [-lemma]` removes an expensive default simp lemma. Measure every change: tokens and heartbeats both count."),
    ("recursion_membership",
     re.compile(r"(∈|⊆|\bmem\b|Subset)", re.S),
     "PATTERN: STRUCTURAL RECURSION WITH MEMBERSHIP / SUBSET GOALS (a recursive function over a syntax tree, a goal about `∈` or `⊆` of its "
     "output). (1) `fun_induction f x` follows the function's own equations; `induction x <;> simp only [f, ...]` often leaves match branches "
     "open. (2) Close all cases with ONE shared closer and compare a pinned closer (`grind only [...]` with the definitions it needs) against a "
     "bare one (shorter, more heartbeats) by the exchange rate. (3) A full `simp` costs more heartbeats per goal than `simp only` with the "
     "needed lemmas; with many goals that dominates."),
    ("constructor_search",
     re.compile(r"(constructor|solve_by_elim|apply_rules|econstructor|∃|Exists)", re.S),
     "PATTERN: CLOSING GOALS WITH AN INDUCTIVE RELATION'S CONSTRUCTORS. (1) `solve_by_elim [C₁, C₂, ...]`: the constructor fallback commits to "
     "the FIRST constructor that unifies, so list later constructors explicitly; reordering the list rarely changes heartbeats. (2) A failing "
     "alternative search (a disjunct tried on goals it cannot close) is where heartbeats go: give such goals their own targeted closer. "
     "(3) In `first | a | b | c` put the alternative that succeeds most often first (the order changes heartbeats). (4) Parsing: `a <;> b <|> c` "
     "is `(a <;> b) <|> c`. (5) A destructuring pattern fails when a name shadows a hypothesis: use fresh names."),
    ("instances_coercions",
     re.compile(r"(ℕ∞|ENNReal|ℝ≥0∞|↑|Nat\.cast|•|ncard|\.card|Finset|Fintype)", re.S),
     "PATTERN: INSTANCES AND COERCIONS (casts, extended numbers, `•`, cardinalities). (1) Instance searches dominate many small proofs: provide "
     "a needed instance once up front with a local `have` instead of letting every step search for it. (2) Explicit arguments that fix a "
     "coercion early are a frequent big win; dropping a binder's type ascription can leave a type unknown. (3) For the same step, compare "
     "candidate lemmas by heartbeats: lemmas proving the same fact can differ in instance search. (4) `omega`, `ring` and "
     "especially `field_simp` have a fixed cost per call: explicit cancellation lemmas are often much cheaper than a heavy normaliser. "
     "(5) Lemma names and signatures drift across toolchains (renamed or deprecated forms): keep the form that compiles on every listed "
     "toolchain."),
    ("big_simp_algebra",
     re.compile(r"(simp only \[[^\]]{60,}\]|map_smul|LinearMap|smul_|conv_lhs|conv_rhs|\bconv\b)", re.S),
     "PATTERN: LARGE SIMP SETS AND ALGEBRAIC NORMALIZATION. (1) In a big `simp only`, generic lemmas can trigger expensive typeclass "
     "searches: compare the generic lemma with the form stated for the specific structure by compiling both. (2) `let` instead of `set` when nothing needs the abbreviation's equation (`set` does extra work). (3) Delete simp lemmas one at a "
     "time with a compile each (or start from the `simp?` list): many are required, some are free tokens. (4) `simp +decide` does not replace "
     "`↓reduceIte`: `if True/False` can remain. (5) `conv`: check the subterm path one `enter` level at a time; merge consecutive `conv_lhs` "
     "blocks. (6) `rw`'s trailing `rfl` closes goals for free: end a branch with `rw [...]` rather than `rw [...]; rfl`. (7) `convert ... using "
     "k`: a larger k can descend into the wrong arguments."),
    ("induction_principles",
     re.compile(r"(induction|Nat\.rec|∀ n|∀ m|ℕ)", re.S),
     "PATTERN: INDUCTION PRINCIPLES. (1) `induction h with | .. => ..` alternatives can be shorter but costlier: compare by the exchange "
     "rate. (2) Starting an induction one step earlier can remove a base-case side lemma; it pays only if the new base case is short."),
    ("term_mode_costs",
     re.compile(r"(fun |⟨|▸|match )", re.S),
     "PATTERN: TERM MODE IS NOT AUTOMATICALLY CHEAPER. A term-mode `match` or a destructuring `let ⟨..⟩ := ...` can cost more heartbeats "
     "than the tactic version (the elaborator unifies more); `h ▸ e` needs an inferable motive (often a type ascription) and fails otherwise. "
     "Measure both forms; positional arguments beat `(x := ..)` named ones by tokens, but a named argument can be the only way to fix an "
     "implicit."),
]


def pattern_cards_for(statement: str, proof: str = "", k: int = 2) -> str:
    """The first k pattern cards (priority order) whose detector fires on the statement or the current proof, as one block, or ""."""
    text = f"{statement}\n{proof}"
    picked = [c for name, rx, c in PATTERN_CARDS if rx.search(text)][:k]
    return ("PATTERN CARDS (general techniques for this proof's shape; no problem-specific answers):\n" + "\n".join(picked)) if picked else ""
