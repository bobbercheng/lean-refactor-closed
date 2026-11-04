lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  let := der.wf.2.1
  generalize eq : [] = Γ at der
  induction der <;> subst_vars
  all_goals grind (gen := 2) [→ Red.case, → Red.case_inr, → Red.case_inl, → canonical_form_sum, → Red.inr, → Red.inl, → Red.let_body, → Red.let_bind, → Red.tabs, → Red.tapp, → canonical_form_tabs, → Red.appᵣ, → Red.appₗ, → Red.abs, → canonical_form_abs]
