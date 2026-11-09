open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  rintro -
  apply List.Sublist.subset
  fun_induction extractOldExprVars <;> simp_all [List.Sublist.append, Imperative.HasVarsPure.getVars, Lambda.LExpr.LExpr.getVars]
