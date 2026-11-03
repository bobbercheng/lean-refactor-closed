open OldExpressions in
theorem substOldPostSubset:
  (Imperative.HasVarsPure.getVars (P:=Expression)
    (substOld h2 (Lambda.LExpr.fvar m h1 ty) post)).Subset
    (Imperative.HasVarsPure.getVars (P:=Expression) post ++ [h1]) := by
  dsimp [Imperative.HasVarsPure.getVars]
  intro
  simp only [List.mem_append]
  fun_induction substOld
  with_reducible
    any_goals apply Or.inl
    all_goals
      simp only [Lambda.LExpr.LExpr.getVars, List.mem_append] at *
      grind only
