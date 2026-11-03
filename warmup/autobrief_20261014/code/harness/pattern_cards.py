"""Pattern-keyed general knowledge (2026-10-13).

The theorem-keyed knowledge briefs (probe/oline-knowledge/<problem>.md: landmark scores, tested tactic lines, problem-local names) are a
'targeted optimization' risk in the final (the organizers review the code and report; the 15 warm-up rows are part of the final). This module
keeps what generalizes: techniques and measured costs, selected by the SHAPE of the statement and proof, never by a theorem name, and with no
problem-local identifier (harness/test_pattern_cards.py checks every card against the warm-up statements and a list of names from the
briefs). Opt-in: agent.py --pattern-cards appends at most K cards after the technique cards; off by default (every default prompt unchanged).
"""
from __future__ import annotations

import re

# (name, detector over statement + current proof, text). Order = priority when more than K detectors fire.
PATTERN_CARDS: list[tuple[str, re.Pattern, str]] = [
    ("recursion_membership",
     re.compile(r"(∈|⊆|\bmem\b|Subset)", re.S),
     "PATTERN: STRUCTURAL RECURSION WITH MEMBERSHIP / SUBSET GOALS (a recursive function over a syntax tree, a goal about `∈` or `⊆` of its "
     "output). (1) `fun_induction f x` follows the function's own equations; `induction x <;> simp only [f, ...]` often leaves match branches "
     "open. (2) Close all cases with ONE shared closer and compare the two forms by the exchange rate: `grind only [f, List.mem_append]` (fewer "
     "heartbeats) vs bare `grind` (one token shorter, more heartbeats). (3) Subset goals over appended lists: a local "
     "`have K : A ⊆ C → B ⊆ D → A ++ B ⊆ C ++ D := by grind` with `repeat' first | assumption | apply K | apply List.nil_subset` beats unfolding "
     "every case; `List.Subset` has no `@[refl]` lemma (`rfl` fails: use `List.Subset.refl _`). (4) A full `simp` costs about 70 heartbeats more "
     "per goal than `simp only` with the needed lemmas; with many goals that dominates."),
    ("constructor_search",
     re.compile(r"(constructor|solve_by_elim|apply_rules|econstructor|∃|Exists)", re.S),
     "PATTERN: CLOSING GOALS WITH AN INDUCTIVE RELATION'S CONSTRUCTORS. (1) `solve_by_elim [C₁, C₂, ...]`: the constructor fallback commits to "
     "the FIRST constructor that unifies, so list later constructors explicitly; reordering the list rarely changes heartbeats. (2) A failing "
     "alternative search (e.g. `Or.inr` tried on goals it cannot close) is where heartbeats go: give such goals their own targeted closer. "
     "(3) In `first | a | b | c` put the alternative that succeeds most often first (the order changes heartbeats). (4) `exists _, C a` infers a "
     "relation from an explicitly named constructor where Mathlib `use` may fail to infer implicit arguments. (5) `rintro s ⟨⟩` then "
     "`<;> rename_i t` is cheaper than `‹_›` (3 tokens). (6) Parsing: `a <;> b <|> c` is `(a <;> b) <|> c`. (7) `obtain ⟨_, h, rfl⟩` fails when "
     "a name shadows a hypothesis: use fresh names."),
    ("instances_coercions",
     re.compile(r"(ℕ∞|ENNReal|ℝ≥0∞|↑|Nat\.cast|•|ncard|\.card|Finset|Fintype)", re.S),
     "PATTERN: INSTANCES AND COERCIONS (casts, ℕ∞ / ENNReal, `•`, cardinalities). (1) Instance searches dominate many small proofs: provide a "
     "needed instance once up front (`have : Nonempty F := ⟨0⟩` cut 2,081 -> 1,493 heartbeats on one proof). (2) Explicit arguments that fix a "
     "coercion early are a frequent big win; dropping a binder's type ascription can leave a type unknown. (3) For the same step, compare "
     "candidate lemmas by heartbeats: one ordered-semiring inequality cost 325-425 with `mul_le_mul_of_nonneg_left` + `bot_le` and 729-940 with "
     "`mul_le_mul'` / `mul_right_mono`. (4) `omega` costs about 300-500 heartbeats per call; `field_simp` is costly (explicit cancellation "
     "lemmas are much cheaper); `ring` about 240. (5) Lemma names and signatures drift across toolchains (`zero_le` vs `bot_le`, "
     "`Polynomial.eval_finset_sum` vs `eval_finsetSum`): keep the form that compiles on every listed toolchain."),
    ("big_simp_algebra",
     re.compile(r"(simp only \[[^\]]{60,}\]|map_smul|LinearMap|smul_|conv_lhs|conv_rhs|\bconv\b)", re.S),
     "PATTERN: LARGE SIMP SETS AND ALGEBRAIC NORMALIZATION. (1) In a big `simp only`, generic `map_*` / `*_apply` lemmas trigger expensive "
     "typeclass searches: prefer specialized variants (`AlgHom.map_smul_of_tower` over `map_smul`; semilinear `compr₂ₛₗ` over forms needing "
     "IsScalarTower / SMulCommClass). (2) `let` instead of `set` (each `set` costs about 165 heartbeats; one switch saved about 1,500). "
     "(3) Delete simp lemmas one at a time with a compile each (or start from the `simp?` list): many are required, some are free tokens. "
     "(4) `simp +decide` does not replace `↓reduceIte`: `if True/False` can remain. (5) `conv`: check the subterm path one `enter` level at a "
     "time; merge consecutive `conv_lhs` blocks. (6) `rw`'s trailing `rfl` closes goals for free: end a branch with `rw [...]` rather than "
     "`rw [...]; rfl`. (7) `convert ... using k`: a larger k can descend into the wrong arguments."),
    ("induction_principles",
     re.compile(r"(induction|Nat\.rec|le_induction|∀ n|∀ m|ℕ)", re.S),
     "PATTERN: INDUCTION PRINCIPLES. (1) Apply the principle directly: `refine Nat.le_induction ?_ ?_` (base at a bound) saved 10 tokens over "
     "`induction` with case handling. (2) A pointwise invariant along a recursion: `Nat.recAux (by simpa using h) fun m ih => ...`. "
     "(3) `induction h with | refl => .. | @step n hn ih => ..` can be shorter but costlier: compare by the exchange rate. (4) Starting an "
     "induction one step earlier can remove a base-case side lemma; it pays only if the new base case is short."),
    ("term_mode_costs",
     re.compile(r"(fun |⟨|▸|match )", re.S),
     "PATTERN: TERM MODE IS NOT AUTOMATICALLY CHEAPER. A term-mode `match` cost 10,663 heartbeats where the tactic version cost about 500; "
     "`let ⟨..⟩ := ...` destructuring added about 1,300; `h ▸ e` needs an inferable motive (often a type ascription) and fails otherwise. "
     "Measure both forms; positional arguments beat `(x := ..)` named ones by tokens, but a named argument can be the only way to fix an "
     "implicit."),
]


def pattern_cards_for(statement: str, proof: str = "", k: int = 2) -> str:
    """The first k pattern cards (priority order) whose detector fires on the statement or the current proof, as one block, or ""."""
    text = f"{statement}\n{proof}"
    picked = [c for name, rx, c in PATTERN_CARDS if rx.search(text)][:k]
    return ("PATTERN CARDS (general techniques for this proof's shape; measured costs; no problem-specific answers):\n" + "\n".join(picked)) if picked else ""
