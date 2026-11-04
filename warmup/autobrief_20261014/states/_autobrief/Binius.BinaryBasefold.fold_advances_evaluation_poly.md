AUTO-BRIEF (measured on THIS seed by the harness before your session: single edits compiled on the primary toolchain; facts about single edits, not limits: combinations and rewrites can do better)
- Seed: 1906 tokens, 46028 heartbeats, score 33.37. Free passes applied (lint_delete): start candidate 1903 tokens, 46027 heartbeats, score 33.42.
- Best combination of the paying single edits below: 1901 tokens, 45877 heartbeats, score 33.56 (Z 100.0); your workspace starts from it.
- Exchange rate here: 1 token = 0.017 points, 100 heartbeats = 0.072 points.
- Single edits that PAY:
  - line 61: delete `succ_eq_add_one` from the simp list: -2 tokens, -150 hb, score +0.14
  - line 61: delete `lt_add_iff_pos_left` from the simp list: -2 tokens, -142 hb, score +0.14
- Compile but do not pay alone: line 106 the proof of `have h_equation_39_x₀ : P_i.eval x₀.val…` (line 106) by `aesop` (-22 tok, +33260 hb); line 109 the proof of `have h_equation_39_x₁ : P_i.eval x₁.val…` (line 109) by `aesop` (-22 tok, +39297 hb); line 72 the proof of `have h_getBit_0_of_0 : Nat.getBit (k :=…` (line 72) by `aesop` (-10 tok, +60444 hb).
- Deletions that FAIL (needed as they stand): line 27 `Subtype.eq_iff` from the simp list; line 35 `Subtype.eq_iff` from the simp list; line 47 `x₁` from the simp list; line 47 `x₀` from the simp list; line 47 `fiberMap` from the simp list; line 49 `AddSubmonoidClass.coe_finset_sum` from the simp list.
- Closers that do NOT close: the whole proof (grind/simp_all/aesop); the proof of `have h_fiber_diff : x₁.val - x₀.val = 1…` (line 46) (grind/simp_all/aesop); the proof of `have h_eval_qMap_x₀ : (AdditiveNTT.qMap…` (line 25) (grind/simp_all/aesop); the proof of `have h_eval_qMap_x₁ : (AdditiveNTT.qMap…` (line 33) (grind/simp_all/aesop); the proof of `have h2 : 2^(ℓ - i) = 2^(ℓ - (i + 1)) *…` (line 12) (grind/simp_all/aesop).
