theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a a₁ a₂ h₁ h₂
  induction h₁ generalizing a₂
  case refl => exact ⟨_, h₂, .refl _⟩
  all_goals cases h₂
  case par.par iha ihb a'' b'' ha' hb' =>
    have hx := iha ha'
    have := ihb hb'
    exact ⟨_, hx.choose_spec.1.par this.choose_spec.1, hx.choose_spec.2.par this.choose_spec.2⟩
  case' par.red_I | par.red_K | par.red_S => apply symm
  case par.red_I hb ihb ha iha | red_I.par ha hb =>
    cases ha
    exact ⟨_, hb, .red_I _⟩
  case par.red_K ha ih | red_K.par ha hc =>
    obtain ⟨x, hx, rfl⟩ := Ka_irreducible _ _ ha
    use x, hx, ParallelReduction.red_K ..
  case par.red_S hb ihb a c ha iha | red_S.par ha hb =>
    have := Sab_irreducible _ _ _ ha
    rw [this.choose_spec.choose_spec.2.2]
    exact ⟨_, (this.choose_spec.choose_spec.1.par hb).par (this.choose_spec.choose_spec.2.1.par hb), .red_S ..⟩
  all_goals
    refine ⟨_, .refl _, ?_⟩
    constructor <;> assumption
