lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  have der' := der
  induction der <;> subst eq
  case var => simp_all
  case abs => exact Or.inl (.abs der'.wf.2.1)
  case tabs => exact Or.inl (.tabs der'.wf.2.1)
  case sub h s ih => exact ih rfl h
  case' app l r il ir => rcases il rfl l with vl | ⟨_, red⟩
  case' app.inl => rcases ir rfl r with vr | ⟨_, red⟩
  case' app.inl.inl => obtain ⟨_, _, rfl⟩ := l.canonical_form_abs vl
  case' tapp h s ih => rcases ih rfl h with v | ⟨_, red⟩
  case' tapp.inl => obtain ⟨_, _, rfl⟩ := h.canonical_form_tabs v
  case' let' h b ih _ => rcases ih rfl h with v | ⟨_, red⟩
  case' inl h w ih | inr h w ih => rcases ih rfl h with v | ⟨_, red⟩
  case' case h b c ih _ _ => rcases ih rfl h with v | ⟨_, red⟩
  case' case.inl =>
    obtain ⟨_, rfl | rfl⟩ := h.canonical_form_sum v
    all_goals cases v
  all_goals
    have lc := der'.wf.2.1
    try apply body_let.mp at lc
    try apply body_case.mp at lc
    rcases lc with ⟨⟩
    try cases_type* And
    first
    | solve_by_elim [Or.inl, Value.inl, Value.inr]
    | right; solve_by_elim (maxDepth := 8) [Exists.intro, Value.lc, Red.appᵣ, Red.abs, Red.tabs, Red.let_body, Red.case, Red.case_inl, Red.case_inr]
