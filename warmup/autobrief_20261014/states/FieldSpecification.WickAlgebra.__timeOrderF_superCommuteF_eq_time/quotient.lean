lemma ι_timeOrderF_superCommuteF_eq_time {φ ψ : 𝓕.CrAnFieldOp}
    (hφψ : crAnTimeOrderRel φ ψ) (hψφ : crAnTimeOrderRel ψ φ) (a b : 𝓕.FieldOpFreeAlgebra) :
    ι 𝓣ᶠ(a * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * b) =
    ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(a * b)) := by
  let T := (ι (𝓕 := 𝓕)).toLinearMap.comp timeOrderF
  let C := [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF
  let M := LinearMap.mul ℂ 𝓕.FieldOpFreeAlgebra
  apply LinearMap.congr_fun₂ (f := (M.comp (LinearMap.mulRight ℂ C)).compr₂ T)
    (g := M.compr₂ ((LinearMap.mulLeft ℂ (ι C)).comp T))
  apply LinearMap.ext_basis ofCrAnListFBasis ofCrAnListFBasis
  intro u v
  dsimp [T, C, M]
  simp only [ofListBasis_eq_ofList]
  obtain ⟨L, R, s⟩ : ∃ L R : 𝓕.WickAlgebra, ∀ (l : List 𝓕.CrAnFieldOp)
      (hl : ∀ c ∈ l, crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ :=
        by simp [hφψ, hψφ, crAnTimeOrderRel_refl]),
      ι (ofCrAnListF (crAnTimeOrderList (u ++ (l ++ v)))) =
        L * ι (ofCrAnListF l) * R := by
    refine ⟨?_ * ?_, ?_ * ?_, ?_⟩
    rotate_left 4
    intro l hl
    rw [crAnTimeOrderList, ← List.append_assoc, insertionSort_of_eq_list crAnTimeOrderRel φ u l v hl]
    simp only [ofCrAnListF_append, map_mul, mul_assoc]
    exact rfl
  trans crAnTimeOrderSign (u ++ φ :: ψ :: v) • (L * ι C * R)
  · conv_lhs =>
      rw [superCommuteF_ofCrAnOpF_ofCrAnOpF]
      simp [mul_sub, sub_mul, ← ofCrAnListF_singleton, ← ofCrAnListF_append,
        timeOrderF_ofCrAnListF]
    erw [← crAnTimeOrderSign_swap_eq_time hφψ hψφ, s [φ, ψ], s [ψ, φ]]
    simp only [C, superCommuteF_ofCrAnOpF_ofCrAnOpF, ofCrAnListF_cons, ofCrAnListF_nil,
      map_sub, map_smul, map_mul, map_one, mul_one,
      mul_sub, sub_mul, mul_smul_comm, smul_mul_assoc, mul_assoc]
    rw [smul_sub, smul_comm]
  · rw [Subalgebra.mem_center_iff.mp (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ),
      mul_assoc]
    have h := s []
    simp only [List.nil_append, ofCrAnListF_nil, map_one, mul_one] at h
    rw [← h]
    by_cases hq : 𝓕.crAnStatistics ψ = 𝓕.crAnStatistics φ
    · rw [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ hq,
        ← crAnTimeOrderSign, ← ofCrAnListF_append, timeOrderF_ofCrAnListF]
      simp only [map_smul, mul_smul_comm]
    · simp only [ι_superCommuteF_of_diff_statistic (Ne.symm hq), zero_mul, smul_zero]
