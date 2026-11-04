theorem bisimilarity_congr_choice :
    (p ~[lts (defs := defs)] q) → (choice p r) ~[lts (defs := defs)] (choice q r) := by
  intro h
  refine ⟨_, ChoiceBisim.choice h, ?_⟩
  intro s1 s2 hr μ
  cases hr <;> constructor <;> intro s t
  case' choice.left => cases t
  case' choice.right => cases t
  case' choice.left.choiceR | choice.right.choiceR => exact ⟨_, .choiceR ‹_›, .bisim (.refl _)⟩
  all_goals
    apply Exists.imp fun _ => .imp (by intro t; solve_by_elim [Tr.choiceL]) .bisim
    solve_by_elim [Bisimilarity.follow_fst, Bisimilarity.follow_snd]
