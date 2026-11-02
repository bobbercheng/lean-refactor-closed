theorem fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius (i : Fin ℓ) (steps : ℕ)
    [NeZero steps] (h_i_add_steps : i.val + steps ≤ ℓ)
    (f : OracleFunction 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  (h_fw_dist_lt : fiberwiseClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate)
    (i := i) (steps := steps) (h_i_add_steps := h_i_add_steps) (f := f)) :
  hammingClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ f := by
  classical
  obtain ⟨⟨g, hg⟩, hd⟩ := Nat.sInf_mem (Set.range_nonempty
    (fun g : BBF_Code 𝔽q β _ => (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g.1).ncard))
  refine (mul_le_mul_left' (Code.distFromCode_le_dist_to_mem f g hg) 2).trans_lt (ENat.coe_lt_coe.2 ?_)
  have hh := Nat.mul_le_mul_right (2 ^ steps) (Nat.le_of_lt_succ (ENat.coe_lt_coe.1 h_fw_dist_lt))
  simp only [fiberwiseDistance, Set.image_univ, ←hd, Nat.mul_assoc, Nat.sub_mul,
    ←Nat.pow_add, ←Nat.sub_add_comm (h_i_add_steps.trans (Nat.le_add_right ..)),
    ←Nat.sub_add_comm h_i_add_steps, Nat.add_sub_add_right] at hh
  apply Nat.lt_succ_of_le
  refine (Nat.mul_le_mul_left 2 ?_).trans hh
  simp only [Set.ncard_eq_toFinset_card', ←Finset.card_fin (2 ^ steps), ←Finset.card_product]
  apply Finset.card_le_card_of_surjOn (fun p => qMap_total_fiber 𝔽q β _ steps
    (Nat.lt_add_of_pos_right_of_le _ _ _ h_i_add_steps) p.1 p.2)
  intro x hx
  refine ⟨(_, _), ?_, (is_fiber_iff_generates_quotient_point 𝔽q β i steps h_i_add_steps x _).mp rfl⟩
  exact Finset.mem_product.mpr ⟨Set.mem_toFinset.mpr
    ⟨x, rfl, (Finset.mem_filter.mp hx).2⟩, Finset.mem_univ _⟩
