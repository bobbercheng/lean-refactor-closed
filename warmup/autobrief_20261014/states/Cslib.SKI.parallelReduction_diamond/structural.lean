theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a
  induction a with
  | S | K | I =>
    intro a₁ a₂ h₁ h₂
    cases h₁
    exact ⟨_, h₂, .refl _⟩
  | app a b iha ihb =>
    intro a₁ a₂ h₁ h₂
    cases h₁
    case refl => exact ⟨_, h₂, .refl _⟩
    all_goals cases h₂
    case par.par _ _ ha hb _ _ ha' hb' =>
      have hx := iha ha ha'
      have hy := ihb hb hb'
      exact ⟨_, hx.choose_spec.1.par hy.choose_spec.1, hx.choose_spec.2.par hy.choose_spec.2⟩
    case' par.red_I | par.red_K | par.red_S => apply symm
    case par.red_I hb ha | red_I.par ha hb =>
      cases ha
      exact ⟨_, hb, .red_I _⟩
    case par.red_K hb ha | red_K.par ha hc =>
      have := Ka_irreducible _ _ ha
      exact this.choose_spec.2.symm ▸ ⟨_, this.choose_spec.1, .red_K ..⟩
    case par.red_S hb _ _ ha | red_S.par ha hb =>
      have := (Sab_irreducible _ _ _ ha).choose_spec.choose_spec
      apply this.2.2.symm.subst
      exact ⟨_, (this.1.par hb).par (this.2.1.par hb), .red_S ..⟩
    all_goals
      refine ⟨_, .refl _, ?_⟩
      constructor <;> assumption
