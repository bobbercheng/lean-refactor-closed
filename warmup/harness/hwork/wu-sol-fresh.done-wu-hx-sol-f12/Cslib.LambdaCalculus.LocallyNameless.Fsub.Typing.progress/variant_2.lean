lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  have lc := der.wf.2.1
  generalize eq : [] = Γ at der
  induction der <;> subst eq
  case var => grind
  any_goals (left; constructor; assumption)
  all_goals simp_all only [body_let, body_case, true_imp_iff]
  all_goals cases lc <;> try simp_all only [true_imp_iff]
  all_goals casesm* _ ∨ _, ∃ _, _, _ ∧ _
  case' app.app.inl.inl vl vr => obtain ⟨_, _, rfl⟩ := Typing.canonical_form_abs vl ‹_›
  case' tapp.tapp.inl v => obtain ⟨_, _, rfl⟩ := Typing.canonical_form_tabs v ‹_›
  case' case.intro.inl.intro _ _ v => obtain ⟨_, rfl | rfl⟩ := Typing.canonical_form_sum v ‹_› <;> cases v
  any_goals (left; constructor; assumption)
  all_goals right; solve_by_elim (constructor := true) [Exists.intro, Red.appᵣ, Red.abs, Red.tabs, Red.let_body, Red.case, Red.case_inl, Red.case_inr]
