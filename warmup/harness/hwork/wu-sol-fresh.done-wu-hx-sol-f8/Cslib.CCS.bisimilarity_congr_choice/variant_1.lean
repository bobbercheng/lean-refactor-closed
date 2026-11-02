theorem bisimilarity_congr_choice :
    (p ~[lts (defs := defs)] q) → (choice p r) ~[lts (defs := defs)] (choice q r) := by
  refine (⟨_, ChoiceBisim.choice ·, ?_⟩)
  rintro _ _ (h | h) μ <;> constructor <;> (
    intro s t
    case' choice => cases t <;> rename_i t
    case' choiceR => exact ⟨_, .choiceR t, .bisim (.refl _)⟩
    apply Exists.imp _
    · first | exact h.follow_fst t | exact h.follow_snd t
    · intro s h
      exact ⟨by first | exact h.1 | exact .choiceL h.1, .bisim h.2⟩)
