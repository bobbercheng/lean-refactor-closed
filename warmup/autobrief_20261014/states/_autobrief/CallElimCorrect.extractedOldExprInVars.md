AUTO-BRIEF (measured on THIS seed by the harness before your session: single edits compiled on the primary toolchain; facts about single edits, not limits: combinations and rewrites can do better)
- Seed: 222 tokens, 2698 heartbeats, score 33.33. Free passes applied (hb_polish, lint_delete): start candidate 213 tokens, 2432 heartbeats, score 37.97.
- Best combination of the paying single edits below: 210 tokens, 2450 heartbeats, score 38.2 (Z 100.0); your workspace starts from it.
- Exchange rate here: 1 token = 0.15 points, 100 heartbeats = 1.235 points.
- Single edits that PAY:
  - line 36: replace the closing tactic at line 36 (`apply ih <;> assumption`) by `grind`: -3 tokens, +17 hb, score +0.24
- Deletions that FAIL (needed as they stand): line 4 `extractOldExprVars` from the simp list; line 4 `Imperative.HasVarsPure.getVars` from the simp list; line 4 `Lambda.LExpr.LExpr.getVars` from the simp list; line 7 the tactic `unfold extractOldExprVars`; line 2 the tactic `intros Hnorm`; line 8 the tactic `split`.
- Closers that do NOT close: the whole proof (grind/simp_all/aesop); the bullet at line 21 (`. cases Hnorm with`) (grind/simp_all/aesop); the bullet at line 12 (`. next Hfalse =>`) (grind/simp_all/aesop); the bullet at line 24 (`. apply List.Subset.trans`) (grind/simp_all/aesop); the bullet at line 29 (`. apply List.Subset.trans`) (grind/simp_all/aesop).
