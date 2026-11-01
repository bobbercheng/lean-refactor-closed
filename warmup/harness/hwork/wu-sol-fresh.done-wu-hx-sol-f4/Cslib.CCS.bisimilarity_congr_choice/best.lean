theorem bisimilarity_congr_choice :
    (p ~[lts (defs := defs)] q) → (choice p r) ~[lts (defs := defs)] (choice q r) := by
  intro h
  refine ⟨_, ChoiceBisim.choice h, ?_⟩
  intro s1 s2 hr μ
  cases hr with
  | choice h =>
    constructor <;> intro s t <;> cases t <;> rename_i t
    case' left.choiceR | right.choiceR => exact ⟨_, .choiceR t, .bisim (.refl _)⟩
    all_goals apply Exists.imp fun _ => .imp .choiceL .bisim
    exacts [h.follow_fst t, h.follow_snd t]
  | bisim h =>
    constructor <;> intro s t
    all_goals apply Exists.imp fun _ => .imp id .bisim
    exacts [h.follow_fst t, h.follow_snd t]
