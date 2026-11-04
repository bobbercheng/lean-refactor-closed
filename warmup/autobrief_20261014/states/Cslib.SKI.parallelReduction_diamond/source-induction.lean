theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a
  induction a with
  | S | K | I =>
    intro a₁ a₂ h₁ h₂
    cases h₁
    cases h₂
    exact ⟨_, .refl _, .refl _⟩
  | app a b iha ihb =>
    intro a₁ a₂ h₁ h₂
    cases h₁
    case refl => exact ⟨_, h₂, .refl _⟩
    all_goals cases h₂
    case par.par a' b' ha hb a'' b'' ha' hb' =>
      have hx := iha ha ha'
      have hy := ihb hb hb'
      exact ⟨_, hx.choose_spec.1.par hy.choose_spec.1, hx.choose_spec.2.par hy.choose_spec.2⟩
    case' par.red_I | par.red_K | par.red_S => apply symm
    case par.red_I hb ha | red_I.par ha hb =>
      cases ha
      exact ⟨_, hb, .red_I _⟩
    case par.red_K ha hb | red_K.par ha hc =>
      obtain ⟨x, hx, rfl⟩ := Ka_irreducible _ _ ha
      use x, hx, ParallelReduction.red_K ..
    case par.red_S hb a c ha | red_S.par ha hb =>
      obtain ⟨x, y, hx, hy, rfl⟩ := Sab_irreducible _ _ _ ha
      exact ⟨_, (hx.par hb).par (hy.par hb), .red_S ..⟩
    all_goals
      refine ⟨_, .refl _, ?_⟩
      constructor <;> assumption