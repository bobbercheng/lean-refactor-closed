theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a b c h₁ h₂
  induction h₁ generalizing c
  case refl => exact ⟨_, h₂, .refl _⟩
  all_goals cases h₂
  case par.par ha hb iha ihb d e hc hd =>
    obtain ⟨_, hx⟩ := iha hc
    obtain ⟨_, hy⟩ := ihb hd
    exact ⟨_, .par hx.1 hy.1, .par hx.2 hy.2⟩
  all_goals
    try
      constructor
      constructor <;> constructor <;> assumption
  all_goals
    first
    | cases I_irreducible _ ‹_›
    | obtain ⟨_, h, rfl⟩ := Ka_irreducible _ _ ‹_›
    | obtain ⟨_, _, h, h', rfl⟩ := Sab_irreducible _ _ _ ‹_›
    constructor
    constructor
    all_goals
      try
        repeat' apply ParallelReduction.par
        all_goals assumption
    all_goals constructor
