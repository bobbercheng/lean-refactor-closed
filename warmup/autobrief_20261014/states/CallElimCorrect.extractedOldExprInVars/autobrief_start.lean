open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  intros Hnorm
  induction post <;>
    simp only [extractOldExprVars, Imperative.HasVarsPure.getVars, Lambda.LExpr.LExpr.getVars, List.append_assoc] at * <;>
    try simp_all
  case app fn e fn_ih e_ih =>
    unfold extractOldExprVars
    split
    . simp
      intros x Hin
      exact Hin
    . next Hfalse =>
      cases Hnorm with
      | app H1 H2 Hn =>
      exfalso
      specialize Hn ?_
      constructor
      cases Hn
      apply Hfalse
      rfl
    . cases Hnorm with
      | app H1 H2 Hn =>
      apply List.Subset.app
      . apply List.Subset.trans
        apply fn_ih
        exact H1
        intros x Hin
        simp_all
      . apply List.Subset.trans
        apply e_ih
        exact H2
        intros x Hin
        simp_all
  case abs ih =>
    cases Hnorm
    grind
  case quant trih eih =>
    cases Hnorm
    apply List.Subset.app
    . apply List.Subset.trans
      apply trih <;> assumption
      intros x Hin
      simp_all
    . apply List.Subset.trans
      apply eih <;> assumption
      intros x Hin
      simp_all
  case ite cih tih eih =>
    cases Hnorm
    apply List.Subset.app
    . apply List.Subset.trans
      apply cih <;> assumption
      intros x Hin
      simp_all
    apply List.Subset.app
    . apply List.Subset.trans
      apply tih <;> assumption
      intros x Hin
      simp_all
    . apply List.Subset.trans
      apply eih <;> assumption
      intros x Hin
      simp_all
  case eq ih1 ih2 =>
    cases Hnorm
    apply List.Subset.app
    . apply List.Subset.trans
      apply ih1 <;> assumption
      intros x Hin
      simp_all
    . apply List.Subset.trans
      apply ih2 <;> assumption
      intros x Hin
      simp_all
