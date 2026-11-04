theorem interleaved_affine_gaps_imply_tensor_gaps
    (hC_proximityGapAffineLines : e_ε_correlatedAgreementAffineLinesNat
      (F := F) (A := A) (ι := ι) (C := MC) (e := e) (ε := ε))
    (h_interleaved_gaps : ∀ m : ℕ, m ≥ 1 →
      e_ε_correlatedAgreementAffineLinesNat (F := F)
        (A := InterleavedSymbol A (Fin m)) (ι := ι) (C := MC ^⋈ (Fin m)) e ε) :
    ∀ (ϑ : ℕ), (hϑ_gt_0 : ϑ > 0) → δ_ε_multilinearCorrelatedAgreement_Nat (F := F) (A := A)
      (ι := ι) (C := MC) (ϑ := ϑ) (e := e) (ε := ε) := by
  classical
  intro n hn
  induction n, hn using Nat.le_induction with
  | base =>
    simp only [Nat.succ_eq_add_one, zero_add, ModuleCode]
    intro u hp
    simp only [multilinearCombine₁_eq_affineLineEvaluation,
      prob_uniform_singleton_finFun_eq (fun r => Δ₀(affineLineEvaluation (u 0) (u 1) r, MC) ≤ e), Nat.cast_one, ENNReal.coe_one, one_mul] at hp
    have hu : u = finMapTwoWords (u 0) (u 1) := by
      funext i
      fin_cases i <;> rfl
    rw [hu]
    exact hC_proximityGapAffineLines (u 0) (u 1) hp
  | succ n hn ih =>
    intro u hp
    have hs := prob_split_last_uniform_sampling_of_finFun (F := F)
      (P := fun s r => Δ₀(multilinearCombine u (Fin.snoc r s), MC) ≤ e)
    simp only [← Fin.init_def, Fin.snoc_init_self] at hs
    rw [hs] at hp
    simp only [multilinearCombine_recursive_form, Fin.snoc_last, Fin.init_snoc] at hp
    have hr := prob_R_star_gt_threshold (MC := MC) u e hp
    apply CA_split_rowwise_implies_CA (C := MC) u e
    apply h_interleaved_gaps (2 ^ n) Nat.one_le_two_pow
    apply lt_of_lt_of_le hr
    apply Pr_le_Pr_of_implies
    intro r hmem
    exact correlatedAgreement_of_mem_R_star_tensor MC ih u ⟨r, hmem⟩
