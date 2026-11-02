theorem bisimilarity_congr_choice :
    (p ~[lts (defs := defs)] q) → (choice p r) ~[lts (defs := defs)] (choice q r) := by
  intro hpq
  exists _, ChoiceBisim.choice hpq
  rintro _ _ (h | h) _ <;> constructor <;> intro s t
  case' choice.left | choice.right => cases t
  case choiceR | choiceR => use s, Tr.choiceR ‹_›, ChoiceBisim.bisim (.refl s)
  all_goals
    apply Exists.imp fun _ => And.imp ?_ .bisim
    apply_rules [h.follow_fst, h.follow_snd]
    first | exact id | exact Tr.choiceL
