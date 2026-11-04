open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  rintro -
  apply List.Sublist.subset
  fun_induction extractOldExprVars
  any_goals apply List.nil_sublist
  all_goals repeat apply List.Sublist.append
  any_goals assumption
  apply List.Sublist.refl
