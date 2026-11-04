theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a a₁ a₂ h₁ h₂
  induction h₁ generalizing a₂
  case refl => exact ⟨_, h₂, .refl _⟩
  all_goals cases h₂
  case red_I.red_I | red_K.red_K | red_S.red_S => exact ⟨_, .refl _, .refl _⟩
  case red_I.refl | red_K.refl | red_S.refl | par.refl =>
    refine ⟨_, .refl _, ?_⟩
    constructor <;> assumption
  case par.par iha ihb a'' b'' ha' hb' =>
    obtain ⟨x, hx, hx'⟩ := iha ha'
    obtain ⟨y, hy, hy'⟩ := ihb hb'
    exact ⟨_, .par hx hy, .par hx' hy'⟩
  case par.red_I hb ihb ha iha =>
    rw [I_irreducible _ ha]
    exact ⟨_, .red_I _, hb⟩
  case par.red_K ha ih =>
    obtain ⟨x, hx, rfl⟩ := Ka_irreducible _ _ ha
    exact ⟨_, .red_K .., hx⟩
  case par.red_S hb ihb a c ha iha =>
    obtain ⟨x, y, hx, hy, rfl⟩ := Sab_irreducible a c _ ha
    exact ⟨_, .red_S .., .par (.par hx hb) (.par hy hb)⟩
  case red_I.par hc ha =>
    rw [I_irreducible _ hc]
    exact ⟨_, ha, .red_I _⟩
  case red_K.par ha hc =>
    obtain ⟨x, hx, rfl⟩ := Ka_irreducible _ _ ha
    exact ⟨_, hx, .red_K ..⟩
  case red_S.par hd hc =>
    obtain ⟨x, y, hx, hy, rfl⟩ := Sab_irreducible _ _ _ hd
    exact ⟨_, .par (.par hx hc) (.par hy hc), .red_S ..⟩
