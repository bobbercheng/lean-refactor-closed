open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  rintro - a
  fun_induction extractOldExprVars post <;> try apply List.nil_subset
  all_goals simp_all +contextual [Imperative.HasVarsPure.getVars, Lambda.LExpr.LExpr.getVars, or_imp]
