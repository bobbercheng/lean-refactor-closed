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
  have hs := fun x y => insertionSort_of_eq_list 𝓕.crAnTimeOrderRel φ l [x, y] r
  simp only [List.append_assoc, List.cons_append, List.nil_append] at hs
  conv_lhs =>
    arg 2
    simp only [c, superCommuteF_ofCrAnOpF_ofCrAnOpF, mul_sub, sub_mul,
      mul_smul_comm, smul_mul_assoc, map_sub, map_smul, ← ofCrAnListF_singleton,
      ← ofCrAnListF_append, List.singleton_append, List.cons_append, List.nil_append, List.append_assoc,
      timeOrderF_ofCrAnListF]
    rw [← crAnTimeOrderSign_swap_eq_time hφψ hψφ, smul_comm, ← smul_sub]
    simp (disch := simp [hφψ, hψφ]) only [crAnTimeOrderList, hs,
      ofCrAnListF_append, ofCrAnListF_cons, mul_assoc]
    arg 2
    repeat rw [← mul_smul_comm, ← mul_sub]
    simp only [← mul_assoc]
    repeat rw [← smul_mul_assoc, ← sub_mul]
    rw [← smul_mul_assoc, ← superCommuteF_ofCrAnOpF_ofCrAnOpF]
  simp only [map_smul, map_mul, ← mul_assoc]
  rw [Subalgebra.mem_center_iff.mp (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ)]
  simp only [mul_assoc, ← map_mul, ← ofCrAnListF_append]
  have h := insertionSort_of_takeWhile_filter 𝓕.crAnTimeOrderRel φ l r
  simp only [decide_not, Bool.decide_and, List.append_assoc] at h ⊢
  rw [← h, ← crAnTimeOrderList]
  by_cases hq : (𝓕 |>ₛ φ) = (𝓕 |>ₛ ψ)
  · rw [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ hq.symm,
      ← crAnTimeOrderSign, timeOrderF_ofCrAnListF]
    simp only [c, map_mul, map_smul, mul_smul_comm]
  · simp [c, ι_superCommuteF_of_diff_statistic hq]
