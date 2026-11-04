theorem bisimilarity_congr_choice :
    (p ~[lts (defs := defs)] q) → (choice p r) ~[lts (defs := defs)] (choice q r) := by
  refine (⟨_, ChoiceBisim.choice ·, ?_⟩)
  rintro _ _ (h | h) μ <;> constructor <;> intro s t
  case' choice.left | choice.right =>
    change Tr _ _ _ at t
    cases t <;> rename_i t
  case' choice.left.choiceR | choice.right.choiceR => exact ⟨_, .choiceR t, .bisim (.refl _)⟩
  all_goals
    apply Exists.imp fun _ => And.imp ?_ ChoiceBisim.bisim
    first | exact h.follow_fst t | exact h.follow_snd t
    first | exact id | exact Tr.choiceL
