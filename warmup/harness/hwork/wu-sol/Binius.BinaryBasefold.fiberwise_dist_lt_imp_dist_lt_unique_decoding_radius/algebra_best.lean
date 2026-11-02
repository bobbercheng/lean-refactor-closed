theorem fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius (i : Fin ℓ) (steps : ℕ)
    [NeZero steps] (h_i_add_steps : i.val + steps ≤ ℓ)
    (f : OracleFunction 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  (h_fw_dist_lt : fiberwiseClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate)
    (i := i) (steps := steps) (h_i_add_steps := h_i_add_steps) (f := f)) :
  hammingClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ f := by
  classical
  obtain ⟨g, _, hg⟩ := Nat.sInf_mem (s := (fun g : BBF_Code 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, fin_ℓ_lt_ℓ_add_one i⟩ => (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g).ncard) '' Set.univ) (Set.image_nonempty.mpr Set.univ_nonempty)
  dsimp only at hg
  refine (mul_le_mul_of_nonneg_left (Code.distFromCode_le_dist_to_mem f g g.2) bot_le).trans_lt ?_
  apply ENat.coe_lt_coe.mpr
  refine (Nat.mul_le_mul_left 2 (show hammingDist f g ≤ (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g).ncard * 2 ^ steps from ?_)).trans_lt ?_
  · rw [Set.ncard_eq_toFinset_card', ← Fintype.card_fin (2 ^ steps), ← Finset.card_univ, ← Finset.card_product]
    refine Finset.card_le_card_of_surjOn (fun p => qMap_total_fiber 𝔽q β _ _ (Nat.lt_add_of_pos_right_of_le _ _ _ h_i_add_steps) p.1 p.2) ?_
    intro x hx
    refine ⟨⟨_, _⟩, ?_, (is_fiber_iff_generates_quotient_point 𝔽q β i steps h_i_add_steps x _).mp rfl⟩
    exact Finset.mem_product.mpr ⟨Set.mem_toFinset.mpr ⟨x, rfl, (Finset.mem_filter.mp hx).2⟩, Finset.mem_univ _⟩
  · rw [← mul_assoc, hg]
    have hb := Nat.mul_le_mul_right (2 ^ steps) (Nat.le_of_lt_succ (ENat.coe_lt_coe.mp h_fw_dist_lt))
    simpa only [fiberwiseDistance, BBF_CodeDistance, Nat.add_sub_cancel, Nat.sub_mul, ← Nat.pow_add, ← Nat.sub_add_comm (h_i_add_steps.trans (Nat.le_add_right ℓ 𝓡)), ← Nat.sub_add_comm h_i_add_steps, Nat.add_sub_add_right] using Nat.lt_succ_of_le hb
