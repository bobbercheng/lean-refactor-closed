
EARLIER SOL LINE ON THIS PROBLEM: DIAGNOSIS AND MEASURED DEAD ENDS (knowledge only; no proof is given)
- Landmark: an earlier GPT-6.1 Sol line with the same briefs reached 339 tokens / 5,593 heartbeats (score 84.89) on this problem.
- Diagnosis: this line's best when this note was written (446 tokens / 12,426 heartbeats, score 73.89) trails that landmark mostly on HEARTBEATS: at the exchange rate above, about 8.5 of the 11 points are heartbeats (12,426 vs 5,593) and about 2.6 are tokens (446 vs 339). Measure where the heartbeats go before shortening text.
- Measured dead ends (tried on that earlier line's own proof; each failed, or compiled but scored worse than the same proof without the change; the figures belong to that proof, not to yours):
  1. ContDiff with the literal index 3: electricField_apply_contDiff_space cannot unify it with its implicit n+1.
  2. Space.deriv_commute applied to its differentiability argument with only (v := i) supplied: its other index was not inferred, so the simp rule went unused and the divergence sum did not commute. (The bare simp form `Space.deriv_commute (v := i)` in the Opus notes above is a different case.)
  3. Replacing a final `ring` by `simp only [mul_left_comm]`: compiles, 343 tokens / 6,284 heartbeats, worse than `ring`.
  4. Adding one_mul and mul_left_comm to a coefficient simp to drop the final `ring`: compiles, but 362 tokens / 5,717 heartbeats on an older, longer version of that proof, worse than keeping `ring` there.
  5. Replacing the generic `_root_.*_apply` lemmas (the IsSubApply/IsSMulApply cost in the heartbeat profile above) by ContinuousLinearMap.coe_sub / coe_smul / coe_sum together with Pi.*_apply: the derivative applications stay unchanged. FunLike.coe_sub / coe_smul / coe_sum exist but go through the same generic Is*Apply typeclasses, so swapping them in does not remove that search cost either.
  6. A recursive simp discharger that re-elaborates differentiability lemmas at every side goal: 297 tokens but 7,170 heartbeats; the repeated elaboration costs more than it saves.
  7. A recursive discharger that decomposes side goals (intro) before closing them: side goals stated as a global `Differentiable` get unfolded by intro and fail.
  8. fun_prop with an explicit discharger on a coefficient-times-sum term: fails, because there are no fun_prop rules for Space.deriv.
- Names that do not exist (unknown constants): Time.deriv_sub, Time.deriv_const_mul, Space.fun_deriv_sum, Space.fun_deriv_const_mul.
