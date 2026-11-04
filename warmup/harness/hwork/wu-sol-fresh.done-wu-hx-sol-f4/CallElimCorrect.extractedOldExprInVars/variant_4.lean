open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  rintro - a
  fun_induction extractOldExprVars post <;> try apply List.nil_subset
  all_goals repeat' first | assumption | apply (List.mem_append.mpr ∘ Or.imp ?_ ?_ ∘ List.mem_append.mp) | apply List.mem_append_right
