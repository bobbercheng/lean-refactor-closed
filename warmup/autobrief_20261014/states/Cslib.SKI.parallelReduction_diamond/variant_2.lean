theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a a₁ a₂ h₁ h₂
  induction h₁ generalizing a₂
  case refl => use a₂, h₂, ParallelReduction.refl _
  case' par ha hb iha ihb => skip
  all_goals cases h₂
  case par.par ha' hb' =>
    specialize iha ha'
    specialize ihb hb'
    exact ⟨_, iha.choose_spec.1.par ihb.choose_spec.1, iha.choose_spec.2.par ihb.choose_spec.2⟩
  case' par.red_I | par.red_K | par.red_S => apply symm
  case par.red_I | red_I.par ha hb =>
    cases ha
    exact ⟨_, hb, .red_I _⟩
  case par.red_K | red_K.par ha hc =>
    have := Ka_irreducible _ _ ha
    exact this.choose_spec.2.symm ▸ ⟨_, this.choose_spec.1, .red_K ..⟩
  case par.red_S | red_S.par ha hb =>
    apply Sab_irreducible at ha
    have := ha.choose_spec.choose_spec
    apply this.2.2.symm.subst
    exact ⟨_, (this.1.par hb).par (this.2.1.par hb), .red_S ..⟩
  all_goals
    refine ⟨_, .refl _, ?_⟩
    constructor <;> assumption
