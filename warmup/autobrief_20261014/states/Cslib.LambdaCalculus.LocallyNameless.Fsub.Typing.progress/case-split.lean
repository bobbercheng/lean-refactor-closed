lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  have lc := der.wf.2.1
  generalize eq : [] = Γ at der
  induction der <;> subst eq
  case var => grind
  case abs | tabs => left; constructor; exact lc
  case sub => grind
  case app l r ih_l ih_r =>
    right
    rcases ih_l l.wf.2.1 rfl with vl | ⟨t', red⟩
    · rcases ih_r r.wf.2.1 rfl with vr | ⟨t', red⟩
      · obtain ⟨σ, b, rfl⟩ := l.canonical_form_abs vl
        exact ⟨_, .abs vl.lc vr⟩
      · exact ⟨_, .appᵣ vl red⟩
    · exact ⟨_, .appₗ r.wf.2.1 red⟩
  case tapp der sub ih =>
    have ht := ih der.wf.2.1 rfl
    cases lc
    grind only [→ canonical_form_tabs, → Red.tapp, → Red.tabs, → Value.lc]
  case let' der _ ih _ =>
    have ht := ih der.wf.2.1 rfl
    have body := (body_let.mp lc).2
    grind only [→ Red.let_bind, → Red.let_body]
  case inl der _ ih | inr der _ ih =>
    have ht := ih der.wf.2.1 rfl
    grind only [→ Red.inl, Value.inl, → Red.inr, Value.inr]
  case case der _ _ ih _ _ =>
    right
    have bodies := (body_case.mp lc).2
    rcases ih der.wf.2.1 rfl with val | ⟨t', red⟩
    · grind only [→ canonical_form_sum, cases Value, → Red.case_inl, → Red.case_inr]
    · exact ⟨_, .case red bodies.1 bodies.2⟩
