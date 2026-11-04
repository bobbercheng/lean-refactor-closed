KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for interleaved_affine_gaps_imply_tensor_gaps
- Union best (a landmark reached by another line — your proofs are your own): 92.33 from the Opus 5.5 line (ccline-opus55-relay1), 104 tokens, 1438 heartbeats.
- Each line's best: Opus 5.5 line 92.33, GPT Astra line 87.05, Flash line 89.48.
- Exchange rate on this problem: 1 token = 0.025 points, 100 heartbeats = 0.362 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
...ress" (goal is folded under δ_ε_... def).
- `List.ofFn_injective rfl ▸` without the type ascription: ▸ can't find the motive.
- `X ▸ h` in place of `?_` + `rwa [← X]` (both cases): "typeclass instance problem is stuck Nonempty ?m"; would need (F := F), +4 tokens.
- `ENNReal.coe_natCast` in place of `ENNReal.coe_one`: assumption fails. `Nat.cast_succ, Nat.cast_zero, zero_add`: 108 / 1490.
- Profile: header elaboration ~27 ms + binder instances (unavoidable); in the proof, the step `refine` ~25 ms,
  base simp ~16 ms (↑1 =?= ↑(Nat.succ 0) ~6 ms), simp at hP ~7 ms, each rwa ~6-9 ms.

## Unexplored idea
- Induction from 0 instead of 1: the step case works for any ϑ (needs only 1 ≤ 2^ϑ), so the base case would become
  ϑ = 0: Pr over (Fin 0 → F) > 0 -> jointProximityNat MC u e for a one-row stack u. Needs Δ₀(⋈|u, interleaved MC) ≤ e
  from Δ₀(u 0, MC) ≤ e; no obvious lemma in context.lean. Pays off only if that proof is under ~40 tokens.
  (hC would then be unused.)

## Earlier findings (runs 1-4)
- `have : Nonempty F := ⟨0⟩` up front: the instance search cost ~50 ms otherwise (2081 -> 1493 hb).
- `rwa [← prob_*_eq]` on the goal works (rw ← finds P through the RHS's higher-order pattern).
- `finMapTwoWords _ _ = u`: rfl unification fills in the arguments.
- Dropping multilinearCombine₁ from the base simp -> whnf timeout. The threshold needs Nat.cast_one, ENNReal.coe_one and one_mul.
- GPT Astra line notes (tail):
...beats for 12 fewer tokens and improves the score.
- Applied the induction principle directly: `refine Nat.le_induction ?_ ?_`, with `intro n hn ih u hP_multilinearCombine_close_gt` in the step. Saves another 10 tokens and 2 heartbeats.
- Final best checked on v4.31.0, v4.30.0, and v4.29.0. Restored candidate from best.lean and confirmed statement bytes match original.

Additional experiments in this continuation:
- Deleting Nat.zero_add from the old nested-induction base case fails (numeric cast threshold not simplified); the new induction genuinely removes the need for it.
- `prob_uniform_singleton_finFun_eq _` in simp is unused and fails to convert the probability.
- `induction hϑ with | refl => ... | @step n hn ih => ...` compiles, saves 3 tokens, but adds 34 heartbeats and lowers score.
- Combining `convert ... using 1; congr 1` into `convert ... using 2` fails: congruence proceeds into the wrong arguments, including e.
- `erw [prob_uniform_singleton_finFun_eq]` after the base-case simp fails with the same instances-transparency issue as rw.
- Inlining `(lt_of_lt_of_eq hprob_gt (prob_uniform_singleton_finFun_eq _))` into the affine-gap application fails to infer the predicate, even with `(F := F)` supplied, and costs many heartbeats.
- Supplying explicit u to `multilinearCombine₁_eq_affineLineEvaluation u` in simp compiles but increases cost to 136 tokens / 2792 heartbeats.

