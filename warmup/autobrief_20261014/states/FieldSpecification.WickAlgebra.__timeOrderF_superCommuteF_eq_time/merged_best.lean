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
  intro φs' φs
  dsimp only [LinearMap.compr₂_apply, LinearMap.comp_apply, LinearMap.mulRight_apply,
    LinearMap.mulLeft_apply, LinearMap.mul_apply', AlgHom.toLinearMap_apply, T, C, M]
  simp only [ofListBasis_eq_ofList]
  let S := List.insertionSort crAnTimeOrderRel (φs' ++ φs)
  let E := fun c => crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ
  let L := List.takeWhile (fun c => ¬crAnTimeOrderRel φ c)
    S ++
    List.filter E φs'
  let R := List.filter E φs ++
    List.filter (fun c => crAnTimeOrderRel φ c ∧ ¬crAnTimeOrderRel c φ)
    S
  have split (l : List 𝓕.CrAnFieldOp)
      (hl : ∀ c ∈ l, E c :=
        by simp [E, hφψ, hψφ, crAnTimeOrderRel_refl]) :
      crAnTimeOrderList (φs' ++ (l ++ φs)) = L ++ (l ++ R) := by
    simpa only [crAnTimeOrderList, L, R, List.append_assoc] using
      insertionSort_of_eq_list crAnTimeOrderRel φ φs' l φs hl
  trans crAnTimeOrderSign (φs' ++ φ :: ψ :: φs) •
        (ι (ofCrAnListF L) * ι C * ι (ofCrAnListF R)) 
  · conv_lhs =>
        rw [superCommuteF_ofCrAnOpF_ofCrAnOpF]
        simp only [← ofCrAnListF_singleton, ← ofCrAnListF_append, List.cons_append,
          List.nil_append, smul_mul_assoc, mul_sub, mul_smul_comm, sub_mul,
          List.append_assoc, map_sub, map_smul, timeOrderF_ofCrAnListF]
    erw [← crAnTimeOrderSign_swap_eq_time hφψ hψφ, split [φ, ψ], split [ψ, φ]]
    simp only [List.cons_append, List.nil_append, C, superCommuteF_ofCrAnOpF_ofCrAnOpF,
      ofCrAnListF_append, ofCrAnListF_cons,
      map_mul, map_sub, map_smul, mul_sub, sub_mul, mul_smul_comm,
      smul_mul_assoc, mul_assoc]
    rw [smul_sub, smul_comm]
  ·
      rw [Subalgebra.mem_center_iff.mp (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ)]
      rw [mul_assoc, ← map_mul, ← ofCrAnListF_append]
      erw [← split []]
      by_cases hq : 𝓕.crAnStatistics ψ = 𝓕.crAnStatistics φ
      · rw [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ hq,
          ← crAnTimeOrderSign, ← ofCrAnListF_append, timeOrderF_ofCrAnListF]
        simp only [List.nil_append, map_smul, mul_smul_comm]
      · simp only [ι_superCommuteF_of_diff_statistic (Ne.symm hq), zero_mul, smul_zero]
