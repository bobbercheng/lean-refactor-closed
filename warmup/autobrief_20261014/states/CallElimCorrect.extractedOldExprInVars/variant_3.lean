open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  rintro -
  apply List.Sublist.subset
  fun_induction extractOldExprVars
  all_goals simp_all only [Imperative.HasVarsPure.getVars, Lambda.LExpr.LExpr.getVars, List.nil_sublist, List.Sublist.refl, List.Sublist.append]
