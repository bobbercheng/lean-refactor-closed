theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a a₁ a₂ h₁ h₂
  induction h₁ generalizing a₂
  case refl => exact ⟨_, h₂, .refl _⟩
  all_goals cases h₂
  case red_I.red_I | red_K.red_K | red_S.red_S | red_I.refl | red_K.refl | red_S.refl | par.refl =>
    refine ⟨_, .refl _, ?_⟩
    constructor <;> assumption
  case par.par iha ihb a'' b'' ha' hb' =>
    obtain ⟨x, hx, hx'⟩ := iha ha'
    obtain ⟨y, hy, hy'⟩ := ihb hb'
    exact ⟨_, .par hx hy, .par hx' hy'⟩
  case' par.red_I | par.red_K | par.red_S => apply symm
  case par.red_I hb ihb ha iha | red_I.par ha hb =>
    rw [I_irreducible _ ha]
    exact ⟨_, hb, .red_I _⟩
  case par.red_K ha ih | red_K.par ha hc =>
    obtain ⟨x, hx, rfl⟩ := Ka_irreducible _ _ ha
    exact ⟨_, hx, .red_K ..⟩
  case par.red_S hb ihb a c ha iha | red_S.par ha hb =>
    obtain ⟨x, y, hx, hy, rfl⟩ := Sab_irreducible _ _ _ ha
    exact ⟨_, .par (.par hx hb) (.par hy hb), .red_S ..⟩
