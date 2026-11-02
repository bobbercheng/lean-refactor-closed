# Current best
candidate.lean is fully checked on v4.32.0: 284 proof tokens, 4886 heartbeats, score 87.09 (previous best 290 /4859 /86.98).

## Architecture and winning edit
Keep smoothness facts hA3 : ContDiff ℝ 3 A, hEs j for E, hEd for spatial partials, hB j for B, and time differentiability hBt/hJt.
Construct hg using `congrArg (fun f => fderiv ℝ f x (Space.basis i)) (funext fun y => ((isExtrema_iff_gauss_ampere_magneticFieldMatrix hA J hJ).mp h t y).1)`, then `unfold Space.div at hg`.
Defer ALL hg expansion to the main `simp (disch := fun_prop) only [...] at hg ⊢`. Include `div_eq_mul_inv`, explicitly specialized `fderiv_fun_sum (fun j _ => (hEd j j).differentiableAt)` and `fderiv_mul_const (LorentzCurrentDensity.chargeDensity_differentiable_space hJ1 t).differentiableAt`. Main simp also has generic fderiv_fun_sum for B time derivatives.
This removes the earlier separate hg simp+erw stages. No type annotation is needed on f in congrArg (checked in the 284-token winner).
Final curated simp commutes derivatives, substitutes Faraday, distributes subtraction, uses hg, then normalizes constants with FreeSpace.c_sq and inv_mul_cancel_left₀.

## Tested alternatives
[tested: explicit hBs and specialized fderiv_sub/fderiv_const_mul instead of fun_prop discharge -> compiles but 328 tokens /4989 hb, worse.]
[tested: solve_by_elim [DifferentiableAt.const_mul, DifferentiableAt.fun_sum] instead of fun_prop -> compiles but 295 tokens /6123 hb, worse.]
[tested: rewrite only outer Time.deriv_eq before main simp -> compiles but 292 tokens /4910 hb, worse than old best.]
[tested: split final simp into derivative and algebra stages -> 293 tokens /4918 hb, worse.]
[tested: fun j => Space.deriv_commute (u := j) _ (hEs j), omitting explicit v -> unused simp argument and unsolved mixed-partial sum. Keep @Space.deriv_commute ℝ d j i _ _ _ (hEs j).]
[tested: defer hg fderiv_fun_sum using only generic lemma and fun_prop discharge -> hg remains an unexpanded derivative of a sum, so final hg rewrite is unused. Explicit hEd side condition fixes this.]
[tested: erw [div_eq_mul_inv] at hg -> cannot find division under lambda; simp only rewrites under it successfully.]
[tested: typed congrArg fderiv basis, separate hg simp+erw -> 298 tokens /4856 hb. Removing type annotation and merging simp gives the winner.]

## Confirmed lemma names
Space.deriv_commute; Space.fun_deriv_sub; Space.time_deriv_comm_space_deriv; Space.space_deriv_differentiable_time; Time.deriv_eq; Time.deriv_fun_sum; Time.deriv_mul_const; Time.deriv_euclid; fderiv_fun_sum; fderiv_fun_sub; fderiv_const_mul; fderiv_mul_const; DifferentiableAt.fun_sum; DifferentiableAt.const_mul; LorentzCurrentDensity.chargeDensity_differentiable_space; LorentzCurrentDensity.currentDensity_apply_differentiable_time; FreeSpace.c_sq; FreeSpace.μ₀_ne_zero; inv_mul_cancel_left₀.
Prior-run tested unknown names: [tested: fderiv_div_const and fderiv_fun_div_const -> unknown identifiers].

## Profile and next idea
Profile of old 290-token proof: total4859, floor660; main+final simp about3111 hb; hg erw expansion515 hb. Most remaining gains likely token-level or shortening explicitly specialized derivatives in the combined simp. A possible next idea is a better library sum-of-spatial-derivatives rule that avoids basis/fderiv expansion, but no such lemma has been confirmed. Do not spend time on upstream history: user precomputed no later simplification.
