theorem bisimilarity_congr_choice :
    (p ~[lts (defs := defs)] q) → (choice p r) ~[lts (defs := defs)] (choice q r) := by
  refine (⟨_, ChoiceBisim.choice ·, ?_⟩)
  rintro _ _ (h | h) μ <;> constructor <;> intro s t
  case' choice.left | choice.right => cases t
  all_goals grind only [ChoiceBisim.bisim, Tr.choiceL, Tr.choiceR, → Bisimilarity.follow_fst, → Bisimilarity.follow_snd, HomBisimilarity.refl]
