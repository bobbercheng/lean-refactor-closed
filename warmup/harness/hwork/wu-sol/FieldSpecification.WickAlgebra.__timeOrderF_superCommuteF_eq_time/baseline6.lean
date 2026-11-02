lemma ι_timeOrderF_superCommuteF_eq_time {φ ψ : 𝓕.CrAnFieldOp}
    (hφψ : crAnTimeOrderRel φ ψ) (hψφ : crAnTimeOrderRel ψ φ) (a b : 𝓕.FieldOpFreeAlgebra) :
    ι 𝓣ᶠ(a * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * b) =
    ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(a * b)) := by
  let c := [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF
  suffices h : (mulLinearMap.comp (mulLinearMap.flip c)).compr₂ (ι.toLinearMap.comp timeOrderF) =
      mulLinearMap.compr₂ (ι.toLinearMap.comp ((mulLinearMap c).comp timeOrderF)) from
    congrArg (fun k => k a b) h
  apply LinearMap.ext_basis ofCrAnListFBasis ofCrAnListFBasis
  intro l r
  dsimp
  simp only [mulLinearMap_apply, ofListBasis_eq_ofList]
  have hs := fun x y => insertionSort_of_eq_list 𝓕.crAnTimeOrderRel φ l [x, y] r
  conv at hs =>
    intro x y h
    lhs
    simp only [List.append_assoc, List.cons_append, List.nil_append]
  conv_lhs =>
    arg 2
    simp [c, superCommuteF_ofCrAnOpF_ofCrAnOpF, mul_sub, sub_mul,
      ← ofCrAnListF_singleton, ← ofCrAnListF_append, List.append_assoc, timeOrderF_ofCrAnListF]
    rw [← crAnTimeOrderSign_swap_eq_time hφψ hψφ, smul_comm, ← smul_sub]
    simp (disch := simp [hφψ, hψφ]) only [crAnTimeOrderList, hs,
      ofCrAnListF_append, ofCrAnListF_cons, ofCrAnListF_nil, mul_one]
    arg 2
    repeat rw [← smul_mul_assoc, ← sub_mul]
    repeat rw [← mul_smul_comm, ← mul_sub]
    rw [← smul_mul_assoc, ← superCommuteF_ofCrAnOpF_ofCrAnOpF]
  conv_rhs =>
    rw [← ofCrAnListF_append, timeOrderF_ofCrAnListF, crAnTimeOrderList, insertionSort_of_takeWhile_filter 𝓕.crAnTimeOrderRel φ l r]
  simp only [c, ofCrAnListF_append, map_mul, map_smul]
  rw [Subalgebra.mem_center_iff.mp (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ)]
  simp only [mul_assoc, mul_smul_comm, crAnTimeOrderSign]
  by_cases hq : 𝓕.crAnStatistics φ = 𝓕.crAnStatistics ψ
  · rw [Wick.koszulSign_eq_rel_eq_stat 𝓕.crAnStatistics 𝓕.crAnTimeOrderRel hφψ hψφ hq.symm]
  · simp [ι_superCommuteF_of_diff_statistic hq]
