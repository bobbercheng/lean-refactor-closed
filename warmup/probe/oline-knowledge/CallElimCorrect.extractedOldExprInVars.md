KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for CallElimCorrect.extractedOldExprInVars
- Union best (a landmark reached by another line — your proofs are your own): 94.69 from the Opus 5.5 line (ccline-opus55-bounty1), 19 tokens, 199 heartbeats.
- Each line's best: Opus 5.5 line 94.69, GPT Astra line 91.08, Flash line 79.33.
- Exchange rate on this problem: 1 token = 0.150 points, 100 heartbeats = 1.236 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
...end to simp: 33 tok / 980 hb. `solve_by_elim* [Or.imp, Or.inr]`: 33 / 866.
- [tested: `rfl` for [v]⊆[v] -> no @[refl] lemma for List.Subset]. `simp` there: fails later.
- [tested: `induction Hnorm <;> unfold ...` -> same tokens, 739]. `all_goals apply_assumption` final: 739.
- [tested: `apply_rules [Or.imp]` replacing repeat+solve_by_elim* -> 32 tok / 811 hb = 85.18]
- [tested: `solve_by_elim* [Or.imp]` without repeat -> 33 / 802]
- [tested: exact List.Subset.refl _ / exact List.nil_subset _ -> 35 / 758]
- [tested: unfold only in app + extractOldExprVars in the simp list -> 36 / 823]
- Imperative.HasVarsPure.getVars is required in the simp list (removing it fails).
- Sandbox: `sed -i`, `;` chains and mkdir need approval. Use the Write tool for each variant and lean_check_variants.py.

## Older (runs 3-6): K-lemma approach, 56 tok / 733 hb = 82.54
- `have K {A B C D} : A ⊆ C → B ⊆ D → A ++ B ⊆ C ++ D := by grind` + `repeat' first | assumption | apply K | apply List.nil_subset`.
- The panic branch closes by `apply List.nil_subset` (default = [] by defeq).
- K-free subset loop: 34 tok / 1216 hb. No core lemma for append_subset_append.

## Next ideas
- Find a way to expose the app match without realizing eq_def (e.g. a `match fn, e with` tactic block? costs many tokens).
- Is there a cheaper replacement for intro+simp only+Or.imp at the Subset level? (List.append_subset costs more)
- GPT Astra line notes (tail):
...ro - a` -> fails: retained normalization evidence affects induction hypotheses. `rintro - _` is equivalent in cost.]
- [tested: `repeat` instead of `repeat'` -> adds 8 heartbeats.]
- [tested: moving empty-case elimination into the repeat loop -> 441 heartbeats with the apply-composition proof; no improvement.]
- [tested: putting `exact id` before composition -> slower; replacing assumption with apply_assumption -> stack overflow.]
- [tested: replacing ?_ holes with _ in apply-composition -> same 428 heartbeats.]
- [tested: `.mpr`/`.mp` instead of `.2`/`.1` -> 437 heartbeats.]
- [tested: exact instead of apply for the composition -> fails; refine' -> 470 heartbeats.]
- [tested: explicit `fun_induction extractOldExprVars post` -> one more token, no heartbeat improvement.]
- [tested: `induction post using extractOldExprVars.induct` -> leaves app match branches unsolved.]
- [tested: early List.Subset.refl plus removing final identity branch -> 25 tokens / 494 heartbeats.]
- [tested: any_goals exact List.Subset.empty, exact False.elim, exact List.not_mem_nil -> fail.]

Next idea: further reduce membership-transport elaboration or induction dispatch. No lower bound established. Use the new functional-induction proof, not the obsolete normalization-induction proofs above. Batch checker appears to process at most eight supplied files; run batches sequentially to avoid best-state races.

