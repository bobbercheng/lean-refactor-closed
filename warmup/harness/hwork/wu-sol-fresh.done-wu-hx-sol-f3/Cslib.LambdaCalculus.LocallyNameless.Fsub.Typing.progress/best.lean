lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  have lc := der.wf.2.1
  induction der <;> subst eq
  case var => simp_all
  case abs => exact Or.inl (.abs lc)
  case tabs => exact Or.inl (.tabs lc)
  case sub => grind
  case' app l r il ir =>
    cases lc
    rcases il rfl (by assumption) with v | ⟨_, red⟩
    case' inl =>
      rcases ir rfl (by assumption) with v' | ⟨_, red⟩
      case' inl => obtain ⟨_, _, rfl⟩ := l.canonical_form_abs v
  case' tapp d s ih =>
    cases lc
    rcases ih rfl (by assumption) with v | ⟨_, red⟩
    case' inl => obtain ⟨_, _, rfl⟩ := d.canonical_form_tabs v
  case' let' d h ih _ =>
    obtain ⟨lc, body⟩ := body_let.mp lc
    rcases ih rfl lc with v | ⟨_, red⟩
  case' inl d h ih | inr d h ih =>
    cases lc
    rcases ih rfl (by assumption) with v | ⟨_, red⟩
  case' case d h h' ih _ _ =>
    obtain ⟨lc, b, b'⟩ := body_case.mp lc
    rcases ih rfl lc with v | ⟨_, red⟩
    case' inl => obtain ⟨_, h | h⟩ := d.canonical_form_sum v <;> subst h <;> cases v
  all_goals solve_by_elim (maxDepth := 7) [Or.inl, Or.inr, Exists.intro, Value.inl, Value.inr, Red.appₗ, Red.appᵣ, Red.abs, Red.tabs, Red.tapp, Red.let_bind, Red.let_body, Red.inl, Red.inr, Red.case, Red.case_inl, Red.case_inr]
