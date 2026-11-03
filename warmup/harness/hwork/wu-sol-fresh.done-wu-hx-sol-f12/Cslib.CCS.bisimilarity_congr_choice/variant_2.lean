theorem bisimilarity_congr_choice :
    (p ~[lts (defs := defs)] q) → (choice p r) ~[lts (defs := defs)] (choice q r) := by
  refine (⟨_, ChoiceBisim.choice ·, ?_⟩)
  rintro _ _ (h | h) μ <;> constructor <;> intro s t
  case' choice.left | choice.right => cases t <;> rename_i t
  all_goals first
  | (refine ⟨_, .choiceR ?_, .bisim (.refl _)⟩; assumption)
  | apply Exists.imp fun _ => And.imp ?_ ChoiceBisim.bisim
    first | exact h.follow_fst t | exact h.follow_snd t
    first | exact id | exact Tr.choiceL
