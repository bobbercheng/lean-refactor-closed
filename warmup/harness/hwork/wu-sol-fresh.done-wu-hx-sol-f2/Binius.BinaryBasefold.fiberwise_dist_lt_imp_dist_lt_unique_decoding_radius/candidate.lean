theorem fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius (i : Fin ℓ) (steps : ℕ)
    [NeZero steps] (h_i_add_steps : i.val + steps ≤ ℓ)
    (f : OracleFunction 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  (h_fw_dist_lt : fiberwiseClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate)
    (i := i) (steps := steps) (h_i_add_steps := h_i_add_steps) (f := f)) :
  hammingClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ f := by
  classical
  obtain ⟨g, _, hg⟩ := Nat.sInf_mem (s := (fun g : BBF_Code 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, fin_ℓ_lt_ℓ_add_one i⟩ => (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g).ncard) '' Set.univ) (Set.image_nonempty.mpr Set.univ_nonempty)
  dsimp only at hg
  have hd : hammingDist f g ≤ (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g).ncard * 2 ^ steps := by
    rw [Set.ncard_eq_toFinset_card']
    refine (Finset.card_le_card ?_).trans (Finset.card_biUnion_le_card_mul _ (fun y => Finset.image (qMap_total_fiber 𝔽q β ⟨i, by omega⟩ steps (by apply Nat.lt_add_of_pos_right_of_le; exact h_i_add_steps) y) Finset.univ) _ ?_)
    · intro x hx
      have hx' : f x ≠ g.val x := (Finset.mem_filter.mp hx).2
      apply Finset.mem_biUnion.mpr
      refine ⟨iteratedQuotientMap 𝔽q β h_ℓ_add_R_rate i steps h_i_add_steps x, ?_, ?_⟩
      · exact Set.mem_toFinset.mpr ⟨x, rfl, hx'⟩
      · apply Finset.mem_image.mpr
        exact ⟨_, Finset.mem_univ _, (is_fiber_iff_generates_quotient_point 𝔽q β i steps h_i_add_steps x _).mp rfl⟩
    · intro y hy
      exact Finset.card_image_le.trans (by simp)
  unfold hammingClose
  refine (mul_le_mul_of_nonneg_left (Code.distFromCode_le_dist_to_mem f g g.2) bot_le).trans_lt ?_
  change ((2 * hammingDist f g : ℕ) : ℕ∞) < _
  rw [ENat.coe_lt_coe]
  refine (Nat.mul_le_mul_left 2 hd).trans_lt ?_
  rw [← mul_assoc, hg]
  have hb := Nat.mul_le_mul_right (2 ^ steps) (Nat.le_of_lt_succ (ENat.coe_lt_coe.mp h_fw_dist_lt))
  simpa (disch := omega) only [fiberwiseDistance, BBF_CodeDistance, Nat.add_sub_cancel, Nat.sub_mul, ← Nat.pow_add, ← Nat.sub_sub, Nat.sub_add_cancel] using Nat.lt_succ_of_le hb
