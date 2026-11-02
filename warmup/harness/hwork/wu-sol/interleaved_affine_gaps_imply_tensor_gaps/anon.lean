theorem interleaved_affine_gaps_imply_tensor_gaps
    (hC_proximityGapAffineLines : e_ε_correlatedAgreementAffineLinesNat
      (F := F) (A := A) (ι := ι) (C := MC) (e := e) (ε := ε))
    (h_interleaved_gaps : ∀ m : ℕ, m ≥ 1 →
      e_ε_correlatedAgreementAffineLinesNat (F := F)
        (A := InterleavedSymbol A (Fin m)) (ι := ι) (C := MC ^⋈ (Fin m)) e ε) :
    ∀ (ϑ : ℕ), (hϑ_gt_0 : ϑ > 0) → δ_ε_multilinearCorrelatedAgreement_Nat (F := F) (A := A)
      (ι := ι) (C := MC) (ϑ := ϑ) (e := e) (ε := ε) := by
  have : Nonempty F := Zero.instNonempty
  refine Nat.le_induction ?_ ?_
  · intro u hp
    simp only [multilinearCombine₁_eq_affineLineEvaluation, Nat.cast_one,
      ENNReal.coe_one, one_mul] at hp
    rw [← show finMapTwoWords _ _ = u from List.ofFn_injective rfl]
    apply hC_proximityGapAffineLines
    rwa [← prob_uniform_singleton_finFun_eq]
  · intro n _ ih u hp
    apply CA_split_rowwise_implies_CA
    apply h_interleaved_gaps _ Nat.one_le_two_pow
    refine lt_of_le_of_lt' ?_ (prob_R_star_gt_threshold MC u e ?_)
    · apply Pr_le_Pr_of_implies
      intro r hr
      apply correlatedAgreement_of_mem_R_star_tensor MC ih u ⟨_, hr⟩
    · simp only [multilinearCombine_recursive_form] at hp
      rwa [← prob_split_last_uniform_sampling_of_finFun]
