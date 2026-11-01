lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  let := der.wf.2.1
  generalize eq : [] = Γ at der
  induction der <;> subst_vars
  all_goals grind (gen := 2) [→ canonical_form_abs, → canonical_form_tabs, → canonical_form_sum, → Red.abs, → Red.appₗ, → Red.appᵣ, → Red.tapp, → Red.tabs, → Red.let_bind, → Red.let_body, → Red.inl, → Red.inr, → Red.case_inl, → Red.case_inr, → Red.case]
