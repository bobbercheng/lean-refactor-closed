open OldExpressions in
theorem substOldPostSubset:
  (Imperative.HasVarsPure.getVars (P:=Expression)
    (substOld h2 (Lambda.LExpr.fvar m h1 ty) post)).Subset
    (Imperative.HasVarsPure.getVars (P:=Expression) post ++ [h1]) := by
  intro
  simp only [Imperative.HasVarsPure.getVars, List.mem_append]
  fun_induction substOld
  any_goals exact Or.inr ∘ id
  with_reducible
    any_goals exact Or.inl
    all_goals simp only [Lambda.LExpr.LExpr.getVars, List.mem_append]
    all_goals repeat first | assumption | apply or_or_distrib_right.mpr.comp; apply Or.imp
