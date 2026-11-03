# Notes (yours to keep; persisted across runs)

## Current run
Best checked: 175 proof tokens, 5775 heartbeats, score 92.76, all v4.29/30/31 compatible.
Architecture: introduce theorem lets; hP rewrites next polynomial as C(1-r)*even + C(r)*odd via coefficient distributivity, sum distributivity, associativity, rfl. hq is inferred from congrArg Subtype.val of generates_quotient_point_if_is_fiber_of_y.trans(iteratedQuotientMap_k_eq_1_is_qMap). Must `dsimp only at hq` to remove subtype constructor projection before using it as simp rule. Main merged simp uses downward inverse `↓←hq` BEFORE one-level fiber rewrite, splits evaluation and uses qMap_total_fiber_one_level_eq, then get_sDomain_basis, add_zero and normalizedWᵢ_eval_βᵢ_eq_1; close ring.
Failures: hP with RHS `_` placeholder fails elaboration. Inferring hP from Eq.refl P' and conv_rhs normalization yields dependent-sum index mismatch (even after unfolding even/odd), ring cannot identify sums; typed hP is robust. hq inferred without dsimp does not fire as simp (even with downward marker). Fin.coe_ofNat_eq_mod, zero_mod, Fin.eta unused in main simp; deleted.

## Latest run
Best: 153 proof tokens, 5667 heartbeats, score 93.22, all three toolchains compatible. Stored in candidate.lean.
Winning polish: `iteratedQuotientMap_k_eq_1_is_qMap ..` works inside `.trans` (inferred from first equality), `have hq k` needs no Fin2 binder annotation. Replace both explicit omega proofs for i+1≤ℓ with `i.2` (definitional Nat.lt). Remove Fin.isValue from main simp; use reduceIte without down-arrow.
Profile: floor2536, main simp1623, hP995, ring380, hq225. Main target after simplify is interpolation identity in even/odd evals and lifted y, ring closes.
Fresh rewrite tried removing hP and distributing evaluations over sums: `simp only [P',cs,evenRefinement,oddRefinement,intermediateEvaluationPoly, Polynomial.eval_finset_sum,Polynomial.eval_mul,Polynomial.eval_C,add_mul,mul_assoc,Finset.sum_add_distrib,←Finset.mul_sum]; ring!` COMPILES (143tok,9181hb), but ring fails (dependent sum index mismatch). ring! uses reducible transparency to identify sums. Worse score.
Failures: removing add_zero from main simp stops normalizedW evaluation lemma; removing P' or cs from hP simp fails (simp does not unfold them). `evenRefinement 𝔽q β ..` and odd version cannot synthesize implicit ℓ/rate/i/coeffs before tactic proof. Replacing hP simp only by simp removes C_add/C_mul and still needs rfl, costly.
Forward sum_add_distrib in hP with Finset.mul_sum works (152tok5752hb), but worse than reverse. Reverse mul_sum plus forward sum_add_distrib works (153tok5702hb), slightly worse than baseline direction.

## Continuation run
No improvement beyond baseline 154 tokens / 5546 hb (score93.29). Restored candidate.lean to baseline.
Tested main `simp` instead of curated simp only: compiles128tok9414hb, worse. Opposite hP distribution/C directions:158tok5697hb, worse. Splitting hP unfold into dsimp then simp requires rfl still (without rfl unresolved dependent-sum equality); simp! likewise cannot close hP automatically.
Fresh removal of hP: distribute evals over sums directly and normalize Nat.sub_add_eq; ring still fails on dependent-sum atoms (125tok14180hb), Nat.sub_add_eq unused. This is not solved by normalizing subtraction in ordinary simp. ring! previously compiles but expensive.
Polynomial.eval_X_mul does NOT exist. Polynomial.eval₂_X_mul exists but does not fire on Polynomial.eval goals, so cannot replace eval_mul plus eval_X.
Final polish DID improve: anonymous `have : P' = ...` referenced by `this` instead of `hP` saves1token; `ring1` saves1heartbeat vs ring. NEW best153tok5545hb, score93.31 compatible all3 toolchains. candidate.lean and best.lean hold this.
`dsimp at hq` saves1token but adds38hb (152tok5583hb), slightly worse. `grind` and `grind only` both close final polynomial interpolation goal but ~10100totalhb, worse than ring1.

## Continuation (latest run)
Best now 142 tokens / 5385 hb / score93.62; all v4.29/30/31 compile. candidate.lean holds it.
Winning edits:
- `have hq k := Subtype.mk.inj ((generates_quotient_point_if_is_fiber_of_y ...).trans (iteratedQuotientMap_k_eq_1_is_qMap ..))` replaces congrArg Subtype.val AND removes `dsimp only at hq`. Subtype.mk.inj normalizes constructor projections enough to match simp; saves5 tokens. [tested: v5 OK]
- `simp +zetaDelta only` in hP removes explicit P',cs; same in main removes f',f,P. Combined saves6 tokens and31hb. IMPORTANT earlier failure concerned full simp, not simp only; curated simp only with zetaDelta WORKS. [tested: v12,v13,v14 OK]
- Main `simp +zetaDelta +decide only` removes `one_ne_zero` but KEEP `reduceIte`. This saves132hb at same tokens. [tested: v18 OK] Earlier +decide failure removed reduceIte too; do not generalize it.
Failures: `Subtype.ext_iff.mp` without dsimp does not match hq (unlike Subtype.mk.inj). `simp_rw`/`simpa only` in hP without rfl still fail dependent sum defeq. smul RHS hP compiles but extra simp lemmas make it worse. `Polynomial.eval_C` instead of downward eval_C_mul compiles but +118hb. `Polynomial.eval_C_mul` without downward marker fails (eval_mul wins first). Reverse C-add/mul plus reverse associativity/distributivity compiles but worse. norm_num main without one_ne_zero,reduceIte leaves conditionals. ring vs ring1 same tokens, +1hb for ring.

## Final fresh rewrite experiments
Best remains v18 (142tok5385hb93.62), restored candidate.lean.
Fresh outline (draft.lean) removes hP, simplifies fold/split/fibers, then evaluates all even/odd/next polynomial sums. Hole checked by lean_skeleton. [tested: rw1 default ring1 -> FAIL dependent sums count as distinct atoms; rw2 ring1! -> OK108tok8943hb, worse score91.64; rw3 with_reducible ring1 -> same failure]. `dsimp only` after sum simplification makes no progress and detects instances-transparency type mismatch in auxiliary fiber proof (i.2 used as successor bound). [tested: first rewrite check -> FAIL]. `ring_nf; rfl` doesn't repair this and costs12.6k hb; normalize before and after sum evaluation also fails at13.7k [tested: rw4,rw5].
A different successful fresh architecture: after fold/split/fiber simp, `trans (1-r_chal)*(evenRefinement ...).eval y.val + r_chal*(oddRefinement ...).eval y.val`; ring1 for interpolation, then simp only `[evenRefinement,oddRefinement,intermediateEvaluationPoly,Polynomial.eval_finset_sum,Polynomial.eval_mul,Polynomial.eval_C,add_mul,mul_assoc,Finset.sum_add_distrib,←Finset.mul_sum]`; rfl. [tested: rw6 -> OK140tokens5676hb, score93.45, worse than v18]. This removes the typed polynomial identity and its scalar evaluations. Most promising next idea: streamline this last evaluation-sum block to shave >244hb; it has less tokens than best but elaborates slightly slower.
Confirmed Polynomial.smul_eq_C_mul and Polynomial.eval_smul exist; Polynomial.eval_smul_of_tower does not [tested: lean_run #check]. Scalar-smul hP variants compile but extra normalization rules outweigh type-token savings [tested: v7,v8 -> 150/151tok5638/5611hb].
