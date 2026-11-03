KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for Electromagnetism.ElectromagneticPotential.time_deriv_time_deriv_electricField_of_isExtrema
- Union best (a landmark reached by another line — your proofs are your own): 91.62 from the Opus 5.5 line (ccline-opus55-bounty1), 158 tokens, 3693 heartbeats.
- Each line's best: Opus 5.5 line 91.62, GPT Astra line 90.27, Flash line 81.81.
- Exchange rate on this problem: 1 token = 0.024 points, 100 heartbeats = 0.124 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
... worse).
- hg via `congrArg (fderiv ℝ · x (Space.basis i))` with div_eq_inv_mul moved into the big simp: 185 tokens but 4509 hb → 89.96 (just below).
  With `simp only [div_eq_inv_mul] at hg` kept: 190 tokens, 4530 hb (worse). So the fderiv-lambda congrArg itself costs ≈ +130 hb.
- `unfold Space.div Space.deriv at hg`: it also unfolds the inner Space.deriv, which breaks the discharges. Fails.

## Run 5 wins (239 -> 202, 4834 -> 4406 hb)
- `unfold Space.div at hg` after `simp only [div_eq_inv_mul, Space.deriv_eq] at hg`.
- hA3 form (2+1) unifies with ?n+1; `hA3.of_succ` for ContDiff 2.
- `hJ.differentiable nofun` proves the `∞ ≠ 0` side goal.

## Heartbeat profile
- Statement alone 660; hJd +51; hA3 +95; hg +63. Big simp ≈ 1450 (the `_root_.*_apply` typeclass searches IsSubApply/IsSMulApply/IsZeroApply are a big part), second ≈ 370, last simp ≈ 220, ring ≈ 240.

## Workspace quirks
- Bash sed/python heredoc/`python3 sub.py` get rejected (approval). Use Write for whole files; keep each Bash call to a single command.

## Next ideas
- Try moving `div_eq_inv_mul` alone into the big simp while keeping `∂[i]` congrArg + `rw [Space.deriv_eq] at hg` (token-neutral; check hb).
- `Space.deriv_commute (v := i)` / `electricField_apply_contDiff_space hA3 t` appear in both simps: look for a way to share them.
- Find a cheaper end than the last simp + ring (field_simp is likely too expensive).
- GPT Astra line notes (tail):
...ul_assoc, mul_comm 𝓕.ε₀⁻¹ 𝓕.μ₀⁻¹]`.
- Merge consecutive conv_lhs blocks and inline the Gauss-law projection.

Tested failures/tradeoffs:
- [tested: final `simp only [FreeSpace.c_sq]; ring` -> failed because inverse cancellation and derivative definitional equality remained.]
- [tested: AC simp plus inv_mul_cancel₀ / mul_inv_cancel_left₀ -> failed; AC ordering separated the inverse factors. Explicit mul_right_comm via simp_rw works.]
- [tested: extracting the divergence identity with final field_simp -> 425 tokens, 9,671 heartbeats; replacing field_simp by explicit cancellation reduced this substantially. Thus the previous higher cost of this structure was not intrinsic.]
- [tested: shared hBs differentiability fact -> needed `(u := Finset.univ)` and slightly worsened both size and cost.]
- [tested: conv equals at enter [1,2] -> selected coefficient times sum; correct path is [1,2,2].]
- Previous run tested ENat.LEInfty.out at order (2 + 1): instance synthesis failed. Current proof uses by decide there, and ENat.LEInfty.out only where already compiling.

Environment: export PATH=/home/user/.elan/bin:$PATH before the prescribed Python harness commands. Project sources were read only.

Potential next idea: combine the fderiv finite-sum rewrite with the initial derivative algebra, avoiding the temporary conversion back to Time.deriv before Time.deriv_fun_sum. Not tested this run.


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
