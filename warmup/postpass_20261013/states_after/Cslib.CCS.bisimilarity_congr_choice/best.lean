theorem bisimilarity_congr_choice :
    (p ~[lts (defs := defs)] q) → (choice p r) ~[lts (defs := defs)] (choice q r) := by
  intro hpq
  exists _, ChoiceBisim.choice hpq
  rintro _ _ (h | h) _ <;> constructor <;> intro s t
  case' choice.left | choice.right => cases t
  case choiceR | choiceR => use s, Tr.choiceR ‹_›, ChoiceBisim.bisim $ .refl s
  all_goals
    apply Exists.imp λ_ => And.imp ?_ .bisim
    first | apply h.follow_fst | apply h.follow_snd
    assumption
    first | exact id | apply Tr.choiceL
