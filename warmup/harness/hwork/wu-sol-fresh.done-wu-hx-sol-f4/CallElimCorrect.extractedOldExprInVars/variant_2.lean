open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  rintro - a
  fun_induction extractOldExprVars
  any_goals apply List.nil_subset
  all_goals repeat' first | assumption | with_reducible apply List.mem_append.2 ∘ Or.imp ?_ ?_ ∘ List.mem_append.1 | apply List.mem_append_right
