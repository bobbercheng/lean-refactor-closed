open OldExpressions in
theorem substOldPostSubset:
  (Imperative.HasVarsPure.getVars (P:=Expression)
    (substOld h2 (Lambda.LExpr.fvar m h1 ty) post)).Subset
    (Imperative.HasVarsPure.getVars (P:=Expression) post ++ [h1]) := by
  intro
  dsimp only [Imperative.HasVarsPure.getVars]
  rw [List.mem_append]
  fun_induction substOld
  any_goals exact Or.inr
  with_reducible
    any_goals exact Or.inl
    all_goals simp only [Lambda.LExpr.LExpr.getVars, List.mem_append]
    all_goals repeat first | assumption | apply or_or_distrib_right.mpr.comp; apply Or.imp
