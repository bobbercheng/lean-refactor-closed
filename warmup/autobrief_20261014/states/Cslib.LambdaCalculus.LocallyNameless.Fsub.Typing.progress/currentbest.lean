lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  have der' := der
  induction der <;> subst eq <;> have lc := der'.wf.2.1
  case var => grind
  case abs | tabs => left; constructor; exact lc
  case sub => grind
  case app l r ih_l ih_r =>
    right
    rcases ih_l rfl l with vl | ⟨t', red⟩
    · rcases ih_r rfl r with vr | ⟨t', red⟩
      · obtain ⟨σ, b, rfl⟩ := l.canonical_form_abs vl
        exact ⟨_, .abs vl.lc vr⟩
      · exact ⟨_, .appᵣ vl red⟩
    · exact ⟨_, .appₗ r.wf.2.1 red⟩
  case tapp der sub ih =>
    have ht := ih rfl der
    cases lc
    grind only [→ canonical_form_tabs, → Red.tapp, → Red.tabs, → Value.lc]
  case let' der _ ih _ =>
    have ht := ih rfl der
    have body := (body_let.mp lc).2
    grind only [→ Red.let_bind, → Red.let_body]
  case inl der _ ih =>
    have ht := ih rfl der
    grind only [→ Red.inl, → Value.inl]
  case inr der _ ih =>
    have ht := ih rfl der
    grind only [→ Red.inr, → Value.inr]
  case case der _ _ ih _ _ =>
    right
    have bodies := (body_case.mp lc).2
    rcases ih rfl der with val | ⟨t', red⟩
    · obtain ⟨b, lr⟩ := der.canonical_form_sum val
      rcases lr with rfl | rfl <;> cases val <;>
        exact ⟨_, by solve_by_elim [Red.case_inl, Red.case_inr, bodies.1, bodies.2]⟩
    · exact ⟨_, .case red bodies.1 bodies.2⟩
