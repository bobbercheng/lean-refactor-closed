KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for FieldSpecification.WickAlgebra.ι_timeOrderF_superCommuteF_eq_time
- Union best (a landmark reached by another line — your proofs are your own): 89.77 from the Opus 5.5 line (ccline-opus55-bounty1), 203 tokens, 5904 heartbeats.
- Each line's best: Opus 5.5 line 89.77, GPT Astra line 87.94, Flash line 76.43.
- Exchange rate on this problem: 1 token = 0.027 points, 100 heartbeats = 0.079 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
...p_smul, mul_smul_comm, crAnTimeOrderSign, crAnTimeOrderList` from the pos
   branch into the outer simp only (after the conv). The pos branch is then just
   `rw [Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ hq.symm]` (rw's rfl closes it). The diff branch `simp [..hq]` still works.

## Tried in run 7, not better
- side goals `by simp_all`: 248 tok but 18.7k hb. `by simp [hφψ, hψφ]`: +4 tok, same hb.
- diff branch `simp only [map_mul, ι_superCommuteF_of_diff_statistic hq, zero_mul, smul_zero]` (from simp?):
  -180 hb, +7 tok -> worse.
- deletions that FAIL: mul_one, ofCrAnListF_nil, first-simp mul_assoc, outer ofListBasis_eq_ofList,
  map_smul in the mem_center simp, last `← smul_mul_assoc`.
- `dsimp [mulLinearMap_apply, ofListBasis_eq_ofList]`: dsimp cannot use that lemma (FAIL).
- pos branch as `rw [timeOrderF_ofCrAnListF, mul_smul_comm, map_smul, crAnTimeOrderSign x2, koszul]; rfl`: +430 hb.

## Tooling
- python, sed with unicode/brackets in the pattern, cp from /tmp: BLOCKED. Simple ASCII `sed 's/a/b/' f > g` and
  `cp vN.lean candidate.lean` work. Otherwise use Write.
- lean_check_variants.py v1.lean v2.lean ... compiles several at once.

## Next ideas
- The f/g term (about 40 tokens) is the biggest chunk; maybe a shorter way to state the bilinear maps.
- The `repeat rw [...]; rw [...]` factoring block inside conv.

## Exchange rate
1 token ≈ 0.027 pts and 100 hb ≈ 0.079 pts.
- GPT Astra line notes (tail):
...instead of apply for LinearMap.ext_basis -> 232 tokens, 7216 heartbeats; fractionally worse].
- [tested: dsimp only [mulLinearMap_apply] -> no progress; omitting LinearMap.flip_apply from the full dsimp-only list leaves flip applications unnormalized].
- [tested: change the outer mapped goal then add mulLinearMap_apply to subsequent simp -> composition/flip applications remain and sign rewrite fails].
- [tested: delete either mul_smul_comm or smul_mul_assoc from the centrality simp -> unsolved goals].
- [tested: targeted final negative-branch simp only -> 238 tokens, 7095 heartbeats, score 87.87; worse].
- [tested: replace sign rw block by simp only -> recursion-depth failure].
- [tested: centrality via reverse .comm directly in simp -> invalid reverse propositional rule; .comm _ |>.eq compiles but is longer and slower].
- [tested: List.forall_mem_cons/List.forall_mem_nil targeted side-condition simp -> leaves quantified empty-list case; full explicit membership simplification works but adds too many tokens].

Useful alternatives are v10q.lean (winner), v10ab.lean (shorter close runner-up), and v10aj.lean (slightly faster close runner-up). Future work could target the bilinear-map setup further; a scratch profile attributed about 1900 heartbeats to setup/extensionality, 405 to dsimp, 2910 to the nested conv, and 1106 to final normalization before these final annotation savings.

