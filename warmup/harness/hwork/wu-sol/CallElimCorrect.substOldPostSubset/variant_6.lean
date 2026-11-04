open OldExpressions in
theorem substOldPostSubset:
  (Imperative.HasVarsPure.getVars (P:=Expression)
    (substOld h2 (Lambda.LExpr.fvar m h1 ty) post)).Subset
    (Imperative.HasVarsPure.getVars (P:=Expression) post ++ [h1]) := by
  intro
  simp only [Imperative.HasVarsPure.getVars, List.mem_append]
  fun_induction substOld
  case case7 => exact Or.inr
  with_reducible
    any_goals exact Or.inl
    all_goals simp -beta only [Lambda.LExpr.LExpr.getVars, List.mem_append]
    all_goals repeat first | assumption | apply or_or_distrib_right.mpr.comp; apply Or.imp
