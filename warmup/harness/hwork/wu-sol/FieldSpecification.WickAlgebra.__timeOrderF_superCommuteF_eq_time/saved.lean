lemma ι_timeOrderF_superCommuteF_eq_time {φ ψ : 𝓕.CrAnFieldOp}
    (hφψ : crAnTimeOrderRel φ ψ) (hψφ : crAnTimeOrderRel ψ φ) (a b : 𝓕.FieldOpFreeAlgebra) :
    ι 𝓣ᶠ(a * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * b) =
    ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(a * b)) := by
  let c := [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF
  let f := (mulLinearMap.comp (mulLinearMap.flip c)).compr₂ (ι.toLinearMap.comp timeOrderF)
  let g := mulLinearMap.compr₂ (ι.toLinearMap.comp ((mulLinearMap c).comp timeOrderF))
  suffices h : f = g from congrArg (fun k => k a b) h
  apply LinearMap.ext_basis ofCrAnListFBasis ofCrAnListFBasis
  intro l r
  simp only [f, g, LinearMap.compr₂_apply, LinearMap.comp_apply, LinearMap.flip_apply,
    AlgHom.toLinearMap_apply, mulLinearMap_apply, ofListBasis_eq_ofList]
  conv_lhs =>
    simp only [c, superCommuteF_ofCrAnOpF_ofCrAnOpF, mul_sub, sub_mul,
      mul_smul_comm, smul_mul_assoc, map_sub, map_smul, ← ofCrAnListF_singleton,
      ← ofCrAnListF_append, List.singleton_append, List.cons_append, List.nil_append, List.append_assoc,
      timeOrderF_ofCrAnListF]
    rw [← crAnTimeOrderSign_swap_eq_time hφψ hψφ]
    rw [smul_comm, ← smul_sub]
    simp only [crAnTimeOrderList,
      show l ++ φ :: ψ :: r = l ++ [φ, ψ] ++ r by simp,
      show l ++ ψ :: φ :: r = l ++ [ψ, φ] ++ r by simp,
      insertionSort_of_eq_list 𝓕.crAnTimeOrderRel φ l [φ, ψ] r (by simp_all),
      insertionSort_of_eq_list 𝓕.crAnTimeOrderRel φ l [ψ, φ] r (by simp_all),
      ofCrAnListF_append, map_mul, smul_mul_assoc]
    arg 2
    simp only [mul_assoc]
    rw [← mul_smul_comm, ← mul_smul_comm, ← mul_sub, ← mul_sub,
      ← smul_mul_assoc, ← sub_mul]
    simp only [ofCrAnListF_cons, ofCrAnListF_nil, mul_one]
    rw [← map_smul, ← map_sub, ← smul_mul_assoc, ← superCommuteF_ofCrAnOpF_ofCrAnOpF]
  simp only [← mul_assoc]
  rw [Subalgebra.mem_center_iff.mp (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ)]
  simp only [mul_assoc, ← map_mul, ← ofCrAnListF_append]
  have h := insertionSort_of_takeWhile_filter 𝓕.crAnTimeOrderRel φ l r
  simp only [decide_not, Bool.decide_and, List.append_assoc, List.cons_append] at h ⊢
  rw [← h, ← crAnTimeOrderList]
  by_cases hq : (𝓕 |>ₛ φ) ≠ (𝓕 |>ₛ ψ)
  · simp [c, ι_superCommuteF_of_diff_statistic hq]
  · rw [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ (by simp_all),
      ← crAnTimeOrderSign, timeOrderF_ofCrAnListF]
    simp only [c, List.nil_append, map_mul, map_smul, mul_smul_comm]
