lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  have lc := der.wf.2.1
  induction der <;> subst eq
  case var => simp_all
  case abs => exact Or.inl (.abs lc)
  case tabs => exact Or.inl (.tabs lc)
  all_goals grind only [→ canonical_form_abs, → canonical_form_tabs, → canonical_form_sum,
    body_let, body_case, cases Term.LC, cases Value, Red.appₗ, Red.appᵣ, Red.abs, Red.tabs, Red.tapp, Red.let_bind, Red.let_body, Red.inl, Red.inr, Red.case, Red.case_inl, Red.case_inr]
