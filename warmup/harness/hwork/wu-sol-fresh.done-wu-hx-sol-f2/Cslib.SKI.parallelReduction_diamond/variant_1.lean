theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a b c h k
  induction h generalizing c
  case refl => exact ⟨_, k, .refl _⟩
  case' par ha hb iha ihb =>
    cases k
    case par ka kb =>
      obtain ⟨d, hd, kd⟩ := iha ka
      obtain ⟨e, he, ke⟩ := ihb kb
      exact ⟨_, .par hd he, .par kd ke⟩
    case refl => exact ⟨_, .refl _, .par ha hb⟩
  case' red_I | red_K | red_S =>
    cases k
    case' par ha hb => skip
    any_goals solve | refine ⟨_, .refl _, ?_⟩; constructor
  all_goals
    first
    | cases I_irreducible _ ha
    | obtain ⟨_, hh, rfl⟩ := Ka_irreducible _ _ ha
    | obtain ⟨_, _, hh, hh', rfl⟩ := Sab_irreducible _ _ _ ha
    constructor
    first
    | apply And.intro hb
    | apply And.intro hh
    | apply And.intro ?_ hb
    | apply And.intro ?_ hh
    | apply And.intro (.red_S ..)
    | apply And.intro ?_ (.red_S ..)
    all_goals constructor <;> constructor <;> assumption
