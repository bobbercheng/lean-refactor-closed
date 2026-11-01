theorem bisimilarity_congr_choice :
    (p ~[lts (defs := defs)] q) → (choice p r) ~[lts (defs := defs)] (choice q r) := by
  intro h
  rw [HomBisimilarity.symm_simulation]
  exists _, ChoiceBisim.choice h
  constructor
  · constructor
    rintro _ _ ⟨⟩ <;> constructor <;> solve_by_elim
  · rintro _ _ (h | h) μ s ht
    case' choice =>
      cases ht <;> rename_i ht
      case choiceR =>
        use s, Tr.choiceR ht
        constructor
        apply_rfl
    all_goals
      apply h.follow_fst at ht
      use ht.choose, ?_, ChoiceBisim.bisim ht.choose_spec.2
      try apply Tr.choiceL
      exact ht.choose_spec.1
