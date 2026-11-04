theorem bisimilarity_congr_choice :
    (p ~[lts (defs := defs)] q) → (choice p r) ~[lts (defs := defs)] (choice q r) := by
  refine (⟨_, ChoiceBisim.choice ·, ?_⟩)
  intro s1 s2 hr μ
  cases hr <;> constructor <;> grind [→ Bisimilarity.follow_fst, → Bisimilarity.follow_snd, ChoiceBisim.bisim, HomBisimilarity.refl, lts]
