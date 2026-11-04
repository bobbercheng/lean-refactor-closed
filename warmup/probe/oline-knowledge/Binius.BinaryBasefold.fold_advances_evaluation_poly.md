KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for Binius.BinaryBasefold.fold_advances_evaluation_poly
- Union best (a landmark reached by another line — your proofs are your own): 93.52 from the Opus 5.5 line (ccline-opus55-relay1), 145 tokens, 5455 heartbeats.
- Each line's best: Opus 5.5 line 93.52, GPT Astra line 93.11, Flash line 87.4.
- Exchange rate on this problem: 1 token = 0.017 points, 100 heartbeats = 0.074 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
... qMap`
  before qMap_total_fiber_one_level_eq rewrites x. Without `↓` the merged simp fails (v3, v12). -3 tok, -60 hb.
- In the merged simp, `hP` no longer needs `↓` (-1 tok). [tested: v10 OK]
- `reduceIte` without `↓` also works (-1 tok, +16 hb, which ties the score). [tested: v9, v11 OK]

## What failed (run 5)
- hP simp: dropping `mul_assoc` → rfl fails; dropping `add_mul` → fails.
- Main simp: dropping `zero_smul, zero_add`, `one_smul`, or `Submodule.coe_add` → unsolved goals.
- `+decide` instead of `one_ne_zero, ↓reduceIte` → `if True/False` stays.
- `_ _` instead of `𝔽q β` in both lemma args: compiles but 6020 hb (worse).

## What failed (run 4)
- `qMap_total_fiber_one_level_eq ..`: the proof mvar leaves the target type-incorrect, so the simp makes no progress.
- Full `simp +zetaDelta [...]` for hP: simp normalises to C-polynomials and `rfl` fails; 9.7k hb.
- Dropping `.trans (iteratedQuotientMap_k_eq_1_is_qMap ..)` (unverified hypothesis): the lemma never fires.

## Next ideas
- Remove hP: put its simp set into the main simp and close by ring (risk: Finset.mul_sum loops, match form vs rfl).
- Something cheaper than `Fin2ToF2, one_ne_zero, reduceIte` (e.g. a `show Fin2ToF2 𝔽q 1 = 1 from rfl`-style lemma is longer).
- Tooling: python scripts, sed and compound Bash commands need approval. Write each variant file into the workspace,
  then run lean_check_variants.py on them.
- GPT Astra line notes (tail):
...p`, then use `congrArg Subtype.val`.
- Replace the long calculation with rewriting the split identities and `sub_eq_iff_eq_add.mp h_fiber_diff`, then `ring`.
- Evaluate polynomial sums directly, use `Finset.sum_mul` and reverse `Finset.sum_add_distrib`, then `Finset.sum_congr` and `ring`.
- Use `let` instead of `set`; reuse `h_i_succ_lt` for the fiber bound. This saved about 1,500 heartbeats.
- Upstream commit 00d1e2bd7 supplied the main one-level fiber and polynomial-sum simplification ideas; adapted to existing older APIs.

## Failures / compatibility
- `Polynomial.eval_finsetSum` is unavailable on v4.29.0. Use `Polynomial.eval_finset_sum`, which works on all three toolchains.
- Deleting original `h_j_lt` before removing its downstream index constructions breaks their omega proofs.
- Replacing the final `ring` with `simp only [add_mul, mul_comm, mul_left_comm, mul_assoc]` failed and cost 40,760 heartbeats; reverted.
- `get_sDomain_first_basis_eq_1` used upstream is unavailable here; use `get_sDomain_basis` and `normalizedWᵢ_eval_βᵢ_eq_1`.

## Next idea
The current proof is compact. If pursuing further reductions, specialize the final distributivity proof using explicit `mul_add` and associativity rather than permutation simp; benchmark against the current `ring`.

## Environment
The shell PATH omits elan. Before harness commands use `export PATH=/home/user/.elan/bin:$PATH`.

