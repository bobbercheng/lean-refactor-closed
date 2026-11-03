theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a a₁ a₂ h₁ h₂
  cases h₁
  case refl => exact ⟨a₂, h₂, .refl a₂⟩
  case par a a' b b' ha' hb' =>
    cases h₂
    case refl =>
      refine ⟨a' ⬝ b', ?_⟩
      exact ⟨.refl $ a' ⬝ b', .par ha' hb'⟩
    case par a'' b'' ha'' hb'' =>
      let ⟨a₃, ha⟩ := parallelReduction_diamond ha' ha''
      let ⟨b₃, hb⟩ := parallelReduction_diamond hb' hb''
      refine ⟨a₃ ⬝ b₃, ?_⟩
      constructor
      · exact .par ha.1 hb.1
      · exact .par ha.2 hb.2
    case red_I =>
      rewrite [I_irreducible a' ha']
      use b', .red_I b'
    case red_K =>
      let ⟨a₂', ha₂'⟩ := Ka_irreducible a₂ a' ha'
      rewrite [ha₂'.2]
      refine ⟨a₂', ?_⟩
      exact ⟨.red_K a₂' b', ha₂'.1⟩
    case red_S a c =>
      let ⟨a'', c', h⟩ := Sab_irreducible a c a' ha'
      rewrite [h.2.2]
      refine ⟨a'' ⬝ b' ⬝ (c' ⬝ b'), .red_S a'' c' b', ?_⟩
      apply ParallelReduction.par <;>
        apply ParallelReduction.par <;>
        grind
  case red_I =>
    cases h₂
    case refl => refine ⟨a₁, ?_⟩; exact ⟨.refl a₁, .red_I a₁⟩
    case par c a₁' hc ha =>
      rewrite [I_irreducible c hc]
      refine ⟨a₁', ?_⟩
      exact ⟨ha, .red_I a₁'⟩
    case red_I => refine ⟨a₁, ?_⟩; exact ⟨.refl a₁, .refl a₁⟩
  case red_K c =>
    cases h₂
    case refl => refine ⟨a₁, ?_⟩; exact ⟨.refl a₁, .red_K a₁ c⟩
    case par a' c' ha hc =>
      let ⟨a₁', h'⟩ := Ka_irreducible a₁ a' ha
      rewrite [h'.2]
      refine ⟨a₁', ?_⟩
      exact ⟨h'.1, .red_K a₁' c'⟩
    case red_K =>
      refine ⟨a₁, ?_⟩
      exact ⟨.refl a₁, .refl a₁⟩
  case red_S a b c =>
    cases h₂
    case refl =>
      refine ⟨a ⬝ c ⬝ (b ⬝ c), ?_⟩
      exact ⟨.refl _, .red_S ..⟩
    case par d c' hd hc =>
      let ⟨a', b', h⟩ := Sab_irreducible a b d hd
      rewrite [h.2.2]
      refine ⟨a' ⬝ c' ⬝ (b' ⬝ c'), ?_⟩
      constructor
      · apply ParallelReduction.par
        · exact .par h.left hc
        · exact .par h.2.1 hc
      · exact .red_S ..
    case red_S => exact ⟨a ⬝ c ⬝ (b ⬝ c), .refl _, .refl _,⟩
