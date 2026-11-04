AUTO-BRIEF (measured on THIS seed by the harness before your session: single edits compiled on the primary toolchain; facts about single edits, not limits: combinations and rewrites can do better)
- Seed: 408 tokens, 59876 heartbeats, score 33.33. Free passes applied (hb_rewrite): start candidate 448 tokens, 24651 heartbeats, score 49.67.
- Best combination of the paying single edits below: 438 tokens, 24854 heartbeats, score 50.38 (Z 100.0); your workspace starts from it.
- Exchange rate here: 1 token = 0.082 points, 100 heartbeats = 0.056 points.
- Single edits that PAY:
  - line 83: replace the bullet at line 83 (`· grind only [→ wf]`) by `grind`: -5 tokens, +97 hb, score +0.36
  - line 77: replace the bullet at line 77 (`· grind only [→ wf]`) by `grind`: -5 tokens, +111 hb, score +0.35
- Deletions that FAIL (needed as they stand): line 3 the tactic `have der' : Typing Γ t τ := der`; line 12 the tactic `have ⟨σ, t₁, eq⟩ := l.canonical_form_abs val_l`; line 65 the tactic `have ⟨t₁, lr⟩ := der.canonical_form_sum val`; line 2 the tactic `generalize eq : [] = Γ at der`; line 4 the tactic `induction der <;> subst eq`; line 7 the tactic `right`.
- Closers that do NOT close: the whole proof (grind/simp_all/aesop); the closing tactic at line 66 (`cases lr <;> [exists t₂ ^ᵗᵗ t₁; refine …`) (grind/simp_all/aesop); the bullet at line 76 (`· grind only [→ wf, cases Term.LC]`) (grind/simp_all/aesop); the bullet at line 82 (`· grind only [→ wf, cases Term.LC]`) (grind/simp_all/aesop); the bullet at line 77 (`· grind only [→ wf]`) (simp_all/aesop).
