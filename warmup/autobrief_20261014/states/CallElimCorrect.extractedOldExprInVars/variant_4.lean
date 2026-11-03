open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  rintro -
  apply List.Sublist.subset
  induction post using Lambda.LExpr.rec
  any_goals apply List.nil_sublist
  case app =>
    unfold extractOldExprVars
    split
    · apply List.Sublist.refl
    · apply List.nil_sublist
    · apply List.Sublist.append <;> assumption
  all_goals repeat apply List.Sublist.append
  all_goals assumption
