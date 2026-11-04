theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a a₁ a₂ h₁ h₂
  induction h₁ generalizing a₂
  case refl => exact ⟨_, h₂, .refl _⟩
  all_goals cases h₂
  case par.par iha ihb a'' b'' ha' hb' =>
    have hx := iha ha'
    have hy := ihb hb'
    exact ⟨_, .par hx.choose_spec.1 hy.choose_spec.1, .par hx.choose_spec.2 hy.choose_spec.2⟩
  case' par.red_I | par.red_K | par.red_S => apply symm
  case par.red_I hb ihb ha iha | red_I.par ha hb =>
    cases ha
    use b', hb, ParallelReduction.red_I _
  case par.red_K ha ih | red_K.par ha hc =>
    obtain ⟨x, hx, rfl⟩ := Ka_irreducible _ _ ha
    use x, hx, ParallelReduction.red_K ..
  case par.red_S hb ihb a c ha iha | red_S.par ha hb =>
    obtain ⟨x, y, hx, hy, rfl⟩ := Sab_irreducible _ _ _ ha
    exact ⟨_, .par (.par hx hb) (.par hy hb), .red_S ..⟩
  all_goals
    refine ⟨_, .refl _, ?_⟩
    constructor <;> assumption
