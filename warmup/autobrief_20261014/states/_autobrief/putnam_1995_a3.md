AUTO-BRIEF (measured on THIS seed by the harness before your session: single edits compiled on the primary toolchain; facts about single edits, not limits: combinations and rewrites can do better)
- Seed: 4085 tokens, 14249 heartbeats, score 33.33. Free passes applied (normalize, hb_rewrite, hb_polish, lint_delete): start candidate 4110 tokens, 11468 heartbeats, score 39.63.
- Best combination of the paying single edits below: 3534 tokens, 10916 heartbeats, score 45.62 (Z 100.0); your workspace starts from it.
- Exchange rate here: 1 token = 0.008 points, 100 heartbeats = 0.234 points.
- Single edits that PAY:
  - line 139: replace the proof of `have h₁₃ : 7 ∣ digits_to_num e + digits…` (line 139) by `grind`: -576 tokens, -552 hb, score +5.99
  - line 143: replace the proof of `have h₁₅ : 7 ∣ 2 * digits_to_num d + ∑ …` (line 143) by `grind`: -491 tokens, +354 hb, score +3.18
  - line 145: replace the proof of `have h₁₇ : 7 ∣ 2 * digits_to_num d + ∑ …` (line 145) by `grind`: -415 tokens, +577 hb, score +2.04
- Deletions that FAIL (needed as they stand): line 19 `hdigits_to_num` from the simp list; line 29 `h` from the simp list; line 29 `↓reduceIte` from the simp list; line 31 `h` from the simp list; line 31 `↓reduceIte` from the simp list; line 31 `zero_mul` from the simp list.
- Closers that do NOT close: the whole proof (grind/simp_all/aesop); the proof of `have h_main : ∀ (d e f : (Fin 9 → ℤ)), …` (line 2) (grind/simp_all/aesop); the proof of `have h₇ : 7 ∣ digits_to_num e + digits_…` (line 107) (grind/simp_all/aesop); the proof of `have h₆ : ∀ (i : Fin 9), 7 ∣ (f i - e i…` (line 60) (grind/simp_all/aesop); the proof of `have h₅ : ∀ (i : Fin 9), 7 ∣ (e i - d i…` (line 13) (grind/simp_all/aesop).
