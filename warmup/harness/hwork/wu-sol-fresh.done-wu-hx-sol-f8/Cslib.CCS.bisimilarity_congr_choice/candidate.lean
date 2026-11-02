theorem bisimilarity_congr_choice :
    (p ~[lts (defs := defs)] q) → (choice p r) ~[lts (defs := defs)] (choice q r) := by
  refine (⟨_, ChoiceBisim.choice ·, ?_⟩)
  intro s1 s2 hr μ
  constructor <;> (
    intro s t
    cases hr <;> rename_i h
    case' choice => cases t <;> rename_i t
    case' choiceR => exact ⟨_, .choiceR t, .bisim (.refl _)⟩
    all_goals (
      apply Exists.imp _
      · first | exact h.follow_fst t | exact h.follow_snd t
      · intro s h
        exact ⟨by first | exact h.1 | exact .choiceL h.1, .bisim h.2⟩))
