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
  all_goals
    first
    | refine ⟨_, .refl _, ?_⟩; constructor <;> assumption
    | unfold Join
      aesop (add safe forward [Ka_irreducible, Sab_irreducible, I_irreducible]) (add unsafe constructors ParallelReduction)
