open OldExpressions in
theorem substOldPostSubset:
  (Imperative.HasVarsPure.getVars (P:=Expression)
    (substOld h2 (Lambda.LExpr.fvar m h1 ty) post)).Subset
    (Imperative.HasVarsPure.getVars (P:=Expression) post ++ [h1]) := by
  intro
  rw [List.mem_append]
  fun_induction substOld
  with_reducible
    any_goals apply Or.inl
    all_goals
      simp only [Imperative.HasVarsPure.getVars, Lambda.LExpr.LExpr.getVars, List.mem_append] at *
      repeat' first | assumption | apply Or.inr | refine or_or_distrib_right.2 ∘ Or.imp ?_ ?_
