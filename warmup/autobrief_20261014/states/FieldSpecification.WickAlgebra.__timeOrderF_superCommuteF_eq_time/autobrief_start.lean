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
      dsimp only [pa]
      calc _
        /- Split the commutator. -/
        _ = crAnTimeOrderSign (φs' ++ φ :: ψ :: φs) •
          ι (ofCrAnListF $ crAnTimeOrderList (φs' ++ φ :: ψ :: φs)) -
            crAnTimeOrderSign (φs' ++ ψ :: φ :: φs) •
          𝓢(𝓕.crAnStatistics φ, 𝓕.crAnStatistics ψ) •
            ι (ofCrAnListF $ crAnTimeOrderList (φs' ++ ψ :: φ :: φs)) := by
          conv_lhs =>
            rw [← ofCrAnListF_singleton, ← ofCrAnListF_singleton,
              superCommuteF_ofCrAnListF_ofCrAnListF]
            simp only [ofListBasis_eq_ofList, List.cons_append, List.nil_append, ofList_singleton, mul_sub, ← ofCrAnListF_append, Algebra.mul_smul_comm, sub_mul, List.append_assoc, Algebra.smul_mul_assoc, map_sub, map_smul]
            rw [timeOrderF_ofCrAnListF, timeOrderF_ofCrAnListF]
          simp only [map_smul, sub_right_inj]
          module
        /- Simplify the signs. -/
        _ = crAnTimeOrderSign (φs' ++ φ :: ψ :: φs) •
          (ι (ofCrAnListF $ crAnTimeOrderList (φs' ++ φ :: ψ :: φs)) -
          𝓢(𝓕.crAnStatistics φ, 𝓕.crAnStatistics ψ) •
            ι (ofCrAnListF $ crAnTimeOrderList (φs' ++ ψ :: φ :: φs))) := by
          rw [crAnTimeOrderSign_swap_eq_time hφψ hψφ]
          module
        /- Splitting the time-ordered lists. -/
        _ = crAnTimeOrderSign (φs' ++ [φ, ψ] ++ φs) •
          (ι (ofCrAnListF $ List.takeWhile (λc => ¬crAnTimeOrderRel φ c)
                (List.insertionSort crAnTimeOrderRel $ φs' ++ φs)) *
              ι (ofCrAnListF $ List.filter (λc =>
                (crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ)) φs') *
              ι (ofCrAnListF [φ, ψ]) *
              ι (ofCrAnListF $ List.filter (λc =>
                (crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ)) φs) *
              ι (ofCrAnListF $ List.filter (λc => (crAnTimeOrderRel φ c ∧ ¬crAnTimeOrderRel c φ))
                (List.insertionSort crAnTimeOrderRel $ φs' ++ φs)) -
          𝓢(𝓕.crAnStatistics φ, 𝓕.crAnStatistics ψ) •
          ι (ofCrAnListF $ List.takeWhile (λc => ¬crAnTimeOrderRel φ c)
                      (List.insertionSort crAnTimeOrderRel $ φs' ++ φs)) *
              ι (ofCrAnListF $ List.filter (λc =>
                (crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ)) φs') *
              ι (ofCrAnListF [ψ, φ]) *
              ι (ofCrAnListF $ List.filter (λc =>
                (crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ)) φs) *
              ι (ofCrAnListF
              (List.filter (λc => decide (crAnTimeOrderRel φ c ∧ ¬crAnTimeOrderRel c φ))
                (List.insertionSort crAnTimeOrderRel $ φs' ++ φs)))) := by
          have h1 := insertionSort_of_eq_list 𝓕.crAnTimeOrderRel φ φs' [φ, ψ] φs
            (by simp_all only [List.mem_cons, List.not_mem_nil, or_false, forall_eq_or_imp, crAnTimeOrderRel_refl, and_self, implies_true])
          rw [crAnTimeOrderList, show φs' ++ φ :: ψ :: φs = φs' ++ [φ, ψ] ++ φs by simp only [List.append_assoc, List.cons_append, List.nil_append], h1]
          have h2 := insertionSort_of_eq_list 𝓕.crAnTimeOrderRel φ φs' [ψ, φ] φs
            (by simp_all only [List.nil_append, List.mem_cons, List.not_mem_nil, or_false, forall_eq_or_imp, and_self, crAnTimeOrderRel_refl, implies_true])
          rw [crAnTimeOrderList, show φs' ++ ψ :: φ :: φs = φs' ++ [ψ, φ] ++ φs by simp only [List.append_assoc, List.cons_append, List.nil_append], h2]
          simp only [ofCrAnListF_append]
          simp only [List.append_assoc, List.cons_append, List.nil_append, decide_not, Bool.decide_and, map_mul, Algebra.smul_mul_assoc]
        _ = crAnTimeOrderSign (φs' ++ [φ, ψ] ++ φs) •
            (ι (ofCrAnListF $ List.takeWhile (λc => ¬crAnTimeOrderRel φ c)
                (List.insertionSort crAnTimeOrderRel $ φs' ++ φs)) *
              ι (ofCrAnListF $ List.filter (λc => (crAnTimeOrderRel φ c ∧
                crAnTimeOrderRel c φ)) φs') *
              (ι (ofCrAnListF [φ, ψ]) - 𝓢(𝓕.crAnStatistics φ, 𝓕.crAnStatistics ψ) •
                ι (ofCrAnListF [ψ, φ])) *
              ι (ofCrAnListF $ List.filter (λc => (crAnTimeOrderRel φ c ∧
                crAnTimeOrderRel c φ)) φs) *
              ι (ofCrAnListF $ List.filter (λc => (crAnTimeOrderRel φ c ∧ ¬crAnTimeOrderRel c φ))
                (List.insertionSort crAnTimeOrderRel $ φs' ++ φs))) := by
            simp only [List.append_assoc, List.cons_append, List.nil_append, decide_not, Bool.decide_and, Algebra.smul_mul_assoc, mul_sub, Algebra.mul_smul_comm, sub_mul]
        _ = crAnTimeOrderSign (φs' ++ [φ, ψ] ++ φs) •
            (ι (ofCrAnListF $ List.takeWhile (λc => ¬crAnTimeOrderRel φ c)
                (List.insertionSort crAnTimeOrderRel $ φs' ++ φs)) *
              ι (ofCrAnListF $ List.filter (λc => (crAnTimeOrderRel φ c ∧
                crAnTimeOrderRel c φ)) φs') *
              ι [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF *
              ι (ofCrAnListF $ List.filter (λc => (crAnTimeOrderRel φ c ∧
                crAnTimeOrderRel c φ)) φs) *
              ι (ofCrAnListF $ List.filter (λc => (crAnTimeOrderRel φ c ∧ ¬crAnTimeOrderRel c φ))
                (List.insertionSort crAnTimeOrderRel $ φs' ++ φs))) := by
            congr
            rw [superCommuteF_ofCrAnOpF_ofCrAnOpF, ← ofCrAnListF_singleton,
              ← ofCrAnListF_singleton]
            simp only [← ofCrAnListF_append, List.cons_append, List.nil_append, Algebra.smul_mul_assoc, map_sub, map_smul]
      rw [Subalgebra.mem_center_iff.mp $ ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ]
      simp only [mul_assoc]
      rw [← map_mul, ← map_mul, ← map_mul, ← ofCrAnListF_append, ← ofCrAnListF_append,
        ← ofCrAnListF_append]
      have h1 := insertionSort_of_takeWhile_filter 𝓕.crAnTimeOrderRel φ φs' φs
      simp only [decide_not, Bool.decide_and, List.append_assoc, List.cons_append, List.nil_append, ofListBasis_eq_ofList, map_mul] at h1 ⊢
      rw [← h1, ← crAnTimeOrderList]
      by_cases hq : (𝓕 |>ₛ φ) ≠ (𝓕 |>ₛ ψ)
      · simp only [ι_superCommuteF_of_diff_statistic hq, zero_mul, smul_zero]
      · rw [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ $ by simp_all only [ne_eq, Decidable.not_not],
          ← crAnTimeOrderSign, ← ofCrAnListF_append, timeOrderF_ofCrAnListF]
        simp only [map_smul, Algebra.mul_smul_comm]
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
