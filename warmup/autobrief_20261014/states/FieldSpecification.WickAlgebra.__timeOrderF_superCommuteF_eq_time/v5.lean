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
  simp only [LinearMap.compr₂_apply, LinearMap.comp_apply, LinearMap.mulRight_apply,
    LinearMap.mulLeft_apply, LinearMap.mul_apply', ofListBasis_eq_ofList,
    AlgHom.toLinearMap_apply, T, C, M]
  let S := List.insertionSort crAnTimeOrderRel (φs' ++ φs)
  let E := fun c => crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ
  let X := ι (ofCrAnListF (List.takeWhile (fun c => ¬crAnTimeOrderRel φ c)
    S)) *
    ι (ofCrAnListF (List.filter E φs'))
  let Y := ι (ofCrAnListF (List.filter E φs)) *
    ι (ofCrAnListF (List.filter (fun c => crAnTimeOrderRel φ c ∧ ¬crAnTimeOrderRel c φ)
    S))
  have split (l : List 𝓕.CrAnFieldOp)
      (hl : ∀ c ∈ l, E c) :
      ι (ofCrAnListF (crAnTimeOrderList (φs' ++ l ++ φs))) =
      X * ι (ofCrAnListF l) * Y := by
    rw [crAnTimeOrderList, insertionSort_of_eq_list _ _ _ _ _ hl]
    simp only [ofCrAnListF_append, map_mul, X, Y, E, S, mul_assoc]
  calc
    _ = crAnTimeOrderSign (φs' ++ φ :: ψ :: φs) •
        (X * ι C * Y) := by
      conv_lhs =>
        rw [superCommuteF_ofCrAnOpF_ofCrAnOpF]
        simp only [mul_sub, sub_mul, ← ofCrAnListF_singleton, ← ofCrAnListF_append, List.append_assoc, map_sub, map_smul, smul_mul_assoc, mul_smul_comm, List.singleton_append, List.cons_append, List.nil_append]
        rw [timeOrderF_ofCrAnListF, timeOrderF_ofCrAnListF]
      have s1 := split [φ, ψ] (by simp [E, hφψ, hψφ, crAnTimeOrderRel_refl])
      have s2 := split [ψ, φ] (by simp [E, hφψ, hψφ, crAnTimeOrderRel_refl])
      simp only [List.append_assoc, List.cons_append, List.nil_append] at s1 s2
      simp only [map_smul]
      rw [← crAnTimeOrderSign_swap_eq_time hφψ hψφ, s1, s2]
      simp [C, superCommuteF_ofCrAnOpF_ofCrAnOpF, ← ofCrAnListF_singleton,
        ← ofCrAnListF_append, mul_sub, sub_mul]
      rw [smul_sub, smul_comm]
    _ = _ := by
      rw [Subalgebra.mem_center_iff.mp (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ)]
      have hXY := split [] (by simp)
      simp only [List.append_nil, ofCrAnListF_nil, map_one, mul_one] at hXY
      rw [mul_assoc, ← hXY]
      by_cases hq : (𝓕 |>ₛ φ) ≠ (𝓕 |>ₛ ψ)
      · simp only [ι_superCommuteF_of_diff_statistic hq, zero_mul, smul_zero]
      · rw [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ (not_not.mp hq).symm,
          ← crAnTimeOrderSign, ← ofCrAnListF_append, timeOrderF_ofCrAnListF]
        simp only [map_smul, mul_smul_comm]
