open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  rintro -
  apply List.Sublist.subset
  fun_induction extractOldExprVars
  any_goals apply List.nil_sublist
  any_goals assumption
  repeat' apply List.Sublist.append
  all_goals first | assumption | apply List.Sublist.refl
