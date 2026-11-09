theorem interleaved_affine_gaps_imply_tensor_gaps
    (hC_proximityGapAffineLines : e_ε_correlatedAgreementAffineLinesNat
      (F := F) (A := A) (ι := ι) (C := MC) (e := e) (ε := ε))
    (h_interleaved_gaps : ∀ m : ℕ, m ≥ 1 →
      e_ε_correlatedAgreementAffineLinesNat (F := F)
        (A := InterleavedSymbol A (Fin m)) (ι := ι) (C := MC ^⋈ (Fin m)) e ε) :
    ∀ (ϑ : ℕ), (hϑ_gt_0 : ϑ > 0) → δ_ε_multilinearCorrelatedAgreement_Nat (F := F) (A := A)
      (ι := ι) (C := MC) (ϑ := ϑ) (e := e) (ε := ε) := by
  apply Nat.le_induction
  · intro u hp
    rw [show u = finMapTwoWords (u 0) (u 1) from funext (Fin.forall_fin_two.2 ⟨rfl, rfl⟩)]
    apply hC_proximityGapAffineLines
    rw [← prob_uniform_singleton_finFun_eq]
    simpa only [← multilinearCombine₁_eq_affineLineEvaluation (u := u),
      Nat.cast_one, ENNReal.coe_one, one_mul, ENNReal.coe_natCast] using hp
  · intro n hn ih u hp
    apply CA_split_rowwise_implies_CA _ u
    apply h_interleaved_gaps _ Nat.one_le_two_pow
    refine lt_of_lt_of_le (prob_R_star_gt_threshold MC u e ?_) ?_
    · simpa only [← prob_split_last_uniform_sampling_of_finFun,
        multilinearCombine_affineComb_split_last_close, ← Fin.init_def,
        ← multilinearCombine_recursive_form, ENNReal.coe_mul, ENNReal.coe_natCast] using hp
    · apply Pr_le_Pr_of_implies
      intro r hmem
      exact correlatedAgreement_of_mem_R_star_tensor MC ih u ⟨r, hmem⟩
