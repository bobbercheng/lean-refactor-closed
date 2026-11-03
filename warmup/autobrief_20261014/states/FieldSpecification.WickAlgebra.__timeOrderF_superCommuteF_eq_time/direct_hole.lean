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
  conv_rhs =>
    rw [← ofCrAnListF_append, timeOrderF_ofCrAnListF, map_smul,
      mul_smul_comm]
    erw [split []]
    simp only [List.nil_append, ofCrAnListF_append, map_mul]
    rw [← mul_assoc, ← Subalgebra.mem_center_iff.mp
      (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ)]
  conv_lhs =>
    rw [superCommuteF_ofCrAnOpF_ofCrAnOpF]
    simp [mul_sub, sub_mul, ← ofCrAnListF_singleton, ← ofCrAnListF_append]
    rw [timeOrderF_ofCrAnListF, timeOrderF_ofCrAnListF]
  simp only [map_smul]
  erw [← crAnTimeOrderSign_swap_eq_time hφψ hψφ, split [φ, ψ], split [ψ, φ]]
  by_cases hq : (𝓕 |>ₛ ψ) = (𝓕 |>ₛ φ)
  · rw [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ hq,
      ← crAnTimeOrderSign]
    simp only [List.cons_append, List.nil_append, superCommuteF_ofCrAnOpF_ofCrAnOpF,
      ofCrAnListF_append, ofCrAnListF_cons,
      map_mul, map_sub, map_smul, mul_sub, sub_mul, mul_smul_comm,
      smul_mul_assoc, mul_assoc]
    rw [smul_sub, smul_comm]
  · have hz := ι_superCommuteF_of_diff_statistic (Ne.symm hq)
    simp only [superCommuteF_ofCrAnOpF_ofCrAnOpF, map_sub, map_smul, map_mul] at hz
    simp only [List.cons_append, List.nil_append, ofCrAnListF_append,
      ofCrAnListF_cons, map_mul, mul_assoc]
    sorry
