lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  have lc := der.wf.2.1
  induction der <;> subst eq
  case var => simp_all
  any_goals solve_by_elim
  case' app l _ _ _ => have := l.canonical_form_abs
  case' tapp d _ _ => have := d.canonical_form_tabs
  case' case d _ _ _ _ _ => have := d.canonical_form_sum
  all_goals repeat' first | simp_all only [body_let, body_case, true_implies] | casesm* And .., Or .., Exists .., Value $ .inl _, Value $ .inr _ <;> subst_vars | cases lc
  any_goals left; constructor; assumption
  all_goals right; solve_by_elim only [*, Exists.intro, Red.appᵣ, Red.abs, Red.tabs, Red.let_body, Red.case_inl, Red.case_inr, Red.case]
