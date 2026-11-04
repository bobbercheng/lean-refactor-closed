theorem fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius (i : Fin ℓ) (steps : ℕ)
    [NeZero steps] (h_i_add_steps : i.val + steps ≤ ℓ)
    (f : OracleFunction 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  (h_fw_dist_lt : fiberwiseClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate)
    (i := i) (steps := steps) (h_i_add_steps := h_i_add_steps) (f := f)) :
  hammingClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ f := by
  classical
  obtain ⟨g, _, hg⟩ := Nat.sInf_mem (s := (fun g : BBF_Code 𝔽q β _ => (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g.1).ncard) '' Set.univ) (Set.image_nonempty.mpr Set.univ_nonempty)
  dsimp only at hg
  have hb := Nat.lt_succ_of_le (Nat.mul_le_mul_right (2 ^ steps) (Nat.le_of_lt_succ (ENat.coe_lt_coe.mp h_fw_dist_lt)))
  simp only [fiberwiseDistance, ← hg, mul_assoc, Nat.sub_mul, ← Nat.pow_add, ← Nat.sub_add_comm (h_i_add_steps.trans (Nat.le_add_right ℓ 𝓡)), ← Nat.sub_add_comm h_i_add_steps, Nat.add_sub_add_right] at hb
  refine (mul_le_mul_of_nonneg_left (Code.distFromCode_le_dist_to_mem f _ g.2) bot_le).trans_lt (ENat.coe_lt_coe.mpr ((Nat.mul_le_mul_left 2 ?_).trans_lt hb))
  rw [← Set.ncard_coe_finset]
  conv_rhs => rw [← Nat.card_fin (2 ^ steps), ← Set.ncard_univ, ← Set.ncard_prod]
  refine (Set.ncard_le_ncard (t := (fun p => qMap_total_fiber _ _ _ _ (fin_ℓ_steps_lt_ℓ_add_R i steps h_i_add_steps) p.1 p.2) '' ((fiberwiseDisagreementSet _ _ i steps h_i_add_steps f g.1) ×ˢ (Set.univ : Set (Fin (2 ^ steps))))) ?_).trans Set.ncard_image_le
  intro x hx
  exact ⟨⟨_, _⟩, ⟨⟨x, rfl, (Finset.mem_filter.mp hx).2⟩, trivial⟩, (is_fiber_iff_generates_quotient_point _ _ i _ h_i_add_steps x _).mp rfl⟩
