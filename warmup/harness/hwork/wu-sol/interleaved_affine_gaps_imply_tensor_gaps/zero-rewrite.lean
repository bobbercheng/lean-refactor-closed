theorem interleaved_affine_gaps_imply_tensor_gaps
    (hC_proximityGapAffineLines : e_ε_correlatedAgreementAffineLinesNat
      (F := F) (A := A) (ι := ι) (C := MC) (e := e) (ε := ε))
    (h_interleaved_gaps : ∀ m : ℕ, m ≥ 1 →
      e_ε_correlatedAgreementAffineLinesNat (F := F)
        (A := InterleavedSymbol A (Fin m)) (ι := ι) (C := MC ^⋈ (Fin m)) e ε) :
    ∀ (ϑ : ℕ), (hϑ_gt_0 : ϑ > 0) → δ_ε_multilinearCorrelatedAgreement_Nat (F := F) (A := A)
      (ι := ι) (C := MC) (ϑ := ϑ) (e := e) (ε := ε) := by
  classical
  have : Nonempty F := Zero.instNonempty
  suffices h : ∀ n, δ_ε_multilinearCorrelatedAgreement_Nat (F := F) (A := A) (ι := ι) (C := MC) n e ε by exact fun n _ => h n
  intro n
  induction n with
  | zero =>
    intro u hp
    have hm (r : Fin 0 → F) : multilinearCombine u r = u 0 := by
      ext i
      simp [multilinearCombine, multilinearWeight]
    have hc : Δ₀(u 0, MC) ≤ e := by
      simp only [hm, Nat.cast_zero, ENNReal.coe_zero, zero_mul, ENNReal.zero_div] at hp
      by_contra h
      rw [prob_uniform_eq_card_filter_div_card] at hp
      simp [h] at hp
    obtain ⟨v, hv, hd⟩ := closeToCode_iff_closeToCodeword_of_minDist _ _ |>.mp hc
    unfold jointProximityNat
    apply (closeToCode_iff_closeToCodeword_of_minDist _ _).mpr
    refine ⟨fun i _ => v i, ?_, ?_⟩
    · change ∀ k, v ∈ MC
      exact fun _ => hv
    · simpa [hammingDist, Interleavable.interleave, interleaveWordStack, funext_iff] using hd
  | succ n ih =>
    intro u hp
    apply CA_split_rowwise_implies_CA
    apply h_interleaved_gaps _ Nat.one_le_two_pow
    refine lt_of_lt_of_le (prob_R_star_gt_threshold MC u e ?_) ?_
    · simp only [multilinearCombine_recursive_form] at hp
      rwa [← prob_split_last_uniform_sampling_of_finFun]
    · apply Pr_le_Pr_of_implies
      intro r hr
      apply correlatedAgreement_of_mem_R_star_tensor MC ih u ⟨_, hr⟩
