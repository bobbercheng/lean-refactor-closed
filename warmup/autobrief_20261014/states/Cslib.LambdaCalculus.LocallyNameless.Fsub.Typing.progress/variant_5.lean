lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  let := der.wf.2.1
  generalize eq : [] = Γ at der
  induction der <;> subst_vars
  all_goals grind (gen := 2) [→ canonical_form_abs, → Red.abs, → Red.appₗ, → Red.appᵣ, → canonical_form_tabs, → Red.tapp, → Red.tabs, → Red.let_bind, → Red.let_body, Red.inl, Red.inr, → canonical_form_sum, → Red.case_inl, → Red.case_inr, → Red.case]
