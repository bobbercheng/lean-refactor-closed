lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  let := der.wf.2.1
  generalize eq : [] = Γ at der
  induction der <;> subst_vars
  all_goals grind (gen := 2) [→ Red.abs, → Red.tabs, → Red.let_body, → Red.case_inl, → Red.case_inr, → Red.appₗ, → Red.appᵣ, → Red.tapp, → Red.let_bind, → Red.inl, → Red.inr, → Red.case, → canonical_form_abs, → canonical_form_tabs, → canonical_form_sum]
