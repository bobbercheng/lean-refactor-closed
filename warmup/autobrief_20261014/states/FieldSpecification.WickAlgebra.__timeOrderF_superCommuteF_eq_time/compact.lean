lemma ι_timeOrderF_superCommuteF_eq_time {φ ψ : 𝓕.CrAnFieldOp}
    (hφψ : crAnTimeOrderRel φ ψ) (hψφ : crAnTimeOrderRel ψ φ) (a b : 𝓕.FieldOpFreeAlgebra) :
    ι 𝓣ᶠ(a * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * b) =
    ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(a * b)) := by
  let pb (b : 𝓕.FieldOpFreeAlgebra) (hc : b ∈ Submodule.span ℂ (Set.range ofCrAnListFBasis)) :
    Prop := ι 𝓣ᶠ(a * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * b) =
    ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(a * b))
  change pb b $ Basis.mem_span _ b
  apply Submodule.span_induction
  · rintro x ⟨φs, rfl⟩
    simp only [ofListBasis_eq_ofList]
    let pa (a : 𝓕.FieldOpFreeAlgebra) (hc : a ∈ Submodule.span ℂ (Set.range ofCrAnListFBasis)) :
      Prop := ι 𝓣ᶠ(a * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * ofCrAnListF φs) =
      ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(a* ofCrAnListF φs))
    change pa a $ Basis.mem_span _ a
    apply Submodule.span_induction
    · rintro x ⟨φs', rfl⟩
      simp only [pa, ofListBasis_eq_ofList]
      let X := ι (ofCrAnListF (List.takeWhile (fun c => ¬crAnTimeOrderRel φ c)
        (List.insertionSort crAnTimeOrderRel (φs' ++ φs)))) *
        ι (ofCrAnListF (List.filter (fun c => crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ) φs'))
      let Y := ι (ofCrAnListF (List.filter (fun c => crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ) φs)) *
        ι (ofCrAnListF (List.filter (fun c => crAnTimeOrderRel φ c ∧ ¬crAnTimeOrderRel c φ)
        (List.insertionSort crAnTimeOrderRel (φs' ++ φs))))
      have split (l : List 𝓕.CrAnFieldOp)
          (hl : ∀ c ∈ l, crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ) :
          ι (ofCrAnListF (crAnTimeOrderList (φs' ++ l ++ φs))) =
          X * ι (ofCrAnListF l) * Y := by
        rw [crAnTimeOrderList, insertionSort_of_eq_list _ _ _ _ _ hl]
        simp only [ofCrAnListF_append, map_mul, X, Y, mul_assoc]
      have pair : ι (ofCrAnListF [φ, ψ]) -
          𝓢(𝓕.crAnStatistics φ, 𝓕.crAnStatistics ψ) • ι (ofCrAnListF [ψ, φ]) =
          ι [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF := by
        rw [superCommuteF_ofCrAnOpF_ofCrAnOpF, ← ofCrAnListF_singleton,
          ← ofCrAnListF_singleton]
        simp only [← ofCrAnListF_append, List.cons_append, List.nil_append, map_sub, map_smul, Algebra.smul_mul_assoc]
      calc
        _ = crAnTimeOrderSign (φs' ++ φ :: ψ :: φs) •
            (X * ι [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * Y) := by
          conv_lhs =>
            rw [superCommuteF_ofCrAnOpF_ofCrAnOpF]
            simp only [mul_sub, sub_mul, Algebra.mul_smul_comm, Algebra.smul_mul_assoc,
              map_sub, map_smul, ← ofCrAnListF_singleton, ← ofCrAnListF_append,
              List.cons_append, List.nil_append, List.append_assoc]
            rw [timeOrderF_ofCrAnListF, timeOrderF_ofCrAnListF]
          have s1 := split [φ, ψ] (by simp_all)
          have s2 := split [ψ, φ] (by simp_all)
          simp only [List.append_assoc, List.cons_append, List.nil_append] at s1 s2
          simp only [map_smul]
          rw [← crAnTimeOrderSign_swap_eq_time hφψ hψφ, s1, s2, ← pair]
          simp only [mul_sub, sub_mul, Algebra.mul_smul_comm, Algebra.smul_mul_assoc]
          module
        _ = _ := by
          rw [Subalgebra.mem_center_iff.mp (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ)]
          have hsort := insertionSort_of_takeWhile_filter 𝓕.crAnTimeOrderRel φ φs' φs
          have hXY : X * Y = ι (ofCrAnListF (crAnTimeOrderList (φs' ++ φs))) := by
            conv_rhs => rw [crAnTimeOrderList, hsort]
            simp only [X, Y, ofCrAnListF_append, map_mul, mul_assoc]
          rw [mul_assoc, hXY]
          by_cases hq : (𝓕 |>ₛ φ) ≠ (𝓕 |>ₛ ψ)
          · simp only [ι_superCommuteF_of_diff_statistic hq, zero_mul, smul_zero, map_mul]
          · rw [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ (by simp_all),
              ← crAnTimeOrderSign, ← ofCrAnListF_append, timeOrderF_ofCrAnListF]
            simp only [map_mul, map_smul, Algebra.mul_smul_comm]
    · simp only [map_mul, zero_mul, map_zero, mul_zero, pa]
    · intro x y hx hy hpx hpy
      simp_all only [map_mul, add_mul, map_add, mul_add, pa]
    · intro x hx hpx
      simp_all only [map_mul, Algebra.smul_mul_assoc, map_smul, Algebra.mul_smul_comm, implies_true, pa]
  · simp only [map_mul, mul_zero, map_zero, pb]
  · intro x y hx hy hpx hpy
    simp_all only [map_mul, mul_add, map_add, pb]
  · intro x hx hpx
    simp_all only [map_mul, Algebra.mul_smul_comm, map_smul, implies_true, pb]
