theorem fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius (i : Fin ℓ) (steps : ℕ)
    [NeZero steps] (h_i_add_steps : i.val + steps ≤ ℓ)
    (f : OracleFunction 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  (h_fw_dist_lt : fiberwiseClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate)
    (i := i) (steps := steps) (h_i_add_steps := h_i_add_steps) (f := f)) :
  hammingClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ f := by
  classical
  obtain ⟨⟨g, hg⟩, _, hd⟩ := Nat.sInf_mem (s :=
    (fun g : BBF_Code 𝔽q β _ => (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g.1).ncard) '' Set.univ)
    ⟨_, 0, trivial, rfl⟩
  apply (mul_le_mul_left' (Code.distFromCode_le_dist_to_mem f g hg) 2).trans_lt
  apply ENat.coe_lt_coe.2
  have hh := Nat.mul_le_mul_right (2 ^ steps) (Nat.le_of_lt_succ (ENat.coe_lt_coe.1 h_fw_dist_lt))
  simp only [fiberwiseDistance, ←hd, Nat.mul_assoc] at hh
  dsimp [BBF_CodeDistance] at hh ⊢
  rw [Nat.sub_mul, ←Nat.pow_add, ←Nat.pow_add] at hh
  simp only [Nat.sub_add_eq,
    Nat.sub_add_cancel (Nat.le_sub_of_add_le' (h_i_add_steps.trans (Nat.le_add_right ..))),
    Nat.sub_add_cancel (Nat.le_sub_of_add_le' h_i_add_steps)] at hh
  apply Nat.lt_succ_of_le
  refine (mul_le_mul_left' ?_ 2).trans hh
  simp only [Set.ncard_eq_toFinset_card', ←Finset.card_fin (2 ^ steps), ←Finset.card_product]
  apply Finset.card_le_card_of_surjOn (fun p => qMap_total_fiber 𝔽q β _ steps
    (Nat.lt_add_of_pos_right_of_le _ _ _ h_i_add_steps) p.1 p.2)
  intro x hx
  refine ⟨(_, _), ?_, (is_fiber_iff_generates_quotient_point 𝔽q β i steps h_i_add_steps x _).mp rfl⟩
  exact Finset.mem_product.mpr ⟨Set.mem_toFinset.mpr
    ⟨x, rfl, (Finset.mem_filter.mp hx).2⟩, Finset.mem_univ _⟩

