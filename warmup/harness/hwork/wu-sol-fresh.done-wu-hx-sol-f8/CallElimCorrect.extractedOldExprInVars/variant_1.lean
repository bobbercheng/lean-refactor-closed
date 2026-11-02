open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  rintro - a
  fun_induction extractOldExprVars post <;> simp_all [Imperative.HasVarsPure.getVars, Lambda.LExpr.LExpr.getVars, or_imp] <;> apply List.nil_subset
