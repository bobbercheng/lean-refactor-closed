open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  rintro - a
  fun_induction extractOldExprVars post
  all_goals repeat' first | assumption | apply List.nil_subset | apply List.mem_append.2 ∘ Or.imp ?_ ?_ ∘ List.mem_append.1 | exact id
