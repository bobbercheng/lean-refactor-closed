lemma ι_timeOrderF_superCommuteF_eq_time {φ ψ : 𝓕.CrAnFieldOp}
    (hφψ : crAnTimeOrderRel φ ψ) (hψφ : crAnTimeOrderRel ψ φ) (a b : 𝓕.FieldOpFreeAlgebra) :
    ι 𝓣ᶠ(a * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * b) =
    ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(a * b)) := by
  let m := @mulLinearMap 𝓕
  let c := [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF
  let f := (m.flip.compl₂ (m.flip c)).flip.compr₂ (ι.toLinearMap.comp timeOrderF)
  let g := m.compr₂ (ι.toLinearMap.comp ((m c).comp timeOrderF))
  suffices h : f = g from congrArg (fun k => k a b) h
  apply LinearMap.ext_basis ofCrAnListFBasis ofCrAnListFBasis
  intro x y
  dsimp only [f, g, m, LinearMap.compr₂_apply, LinearMap.compl₂_apply,
    LinearMap.flip_apply, LinearMap.comp_apply, AlgHom.toLinearMap_apply]
  simp only [mulLinearMap_apply, ofListBasis_eq_ofList]
  conv_lhs =>
    simp only [c, superCommuteF_ofCrAnOpF_ofCrAnOpF, mul_sub, sub_mul,
      mul_smul_comm, smul_mul_assoc, ← ofCrAnListF_singleton, ← ofCrAnListF_append,
      List.singleton_append, List.cons_append, List.nil_append, map_sub, map_smul,
      timeOrderF_ofCrAnListF]
    rw [crAnTimeOrderList,
      insertionSort_of_eq_list 𝓕.crAnTimeOrderRel φ x [φ, ψ] y (by simp_all),
      crAnTimeOrderList,
      insertionSort_of_eq_list 𝓕.crAnTimeOrderRel φ x [ψ, φ] y (by simp_all)]
    simp only [ofCrAnListF_append, map_mul]
    simp only [List.append_assoc, List.cons_append, List.nil_append]
    rw [← crAnTimeOrderSign_swap_eq_time hφψ hψφ, smul_comm, ← smul_sub]
    enter [2]
    rw [← smul_mul_assoc, ← smul_mul_assoc,
      ← sub_mul, ← sub_mul, ← mul_smul_comm, ← mul_sub]
    rw [← map_smul, ← map_sub]
    simp only [ofCrAnListF_cons, ofCrAnListF_nil, mul_one, ← smul_mul_assoc,
      ← superCommuteF_ofCrAnOpF_ofCrAnOpF]
  rw [Subalgebra.mem_center_iff.mp (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ)]
  simp only [mul_assoc, ← map_mul, ← ofCrAnListF_append]
  rw [← insertionSort_of_takeWhile_filter 𝓕.crAnTimeOrderRel φ x y]
  by_cases hq : (𝓕 |>ₛ φ) ≠ (𝓕 |>ₛ ψ)
  · simp [c, ι_superCommuteF_of_diff_statistic hq]
  · rw [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ (by simp_all),
      ← crAnTimeOrderSign, timeOrderF_ofCrAnListF]
    simp only [c, map_mul, map_smul, mul_smul_comm, crAnTimeOrderList]
