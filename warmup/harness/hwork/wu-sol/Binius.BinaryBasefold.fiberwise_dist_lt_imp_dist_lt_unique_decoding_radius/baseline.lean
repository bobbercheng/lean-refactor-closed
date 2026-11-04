theorem fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius (i : Fin ℓ) (steps : ℕ)
    [NeZero steps] (h_i_add_steps : i.val + steps ≤ ℓ)
    (f : OracleFunction 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  (h_fw_dist_lt : fiberwiseClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate)
    (i := i) (steps := steps) (h_i_add_steps := h_i_add_steps) (f := f)) :
  hammingClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ f := by
  classical
  unfold fiberwiseClose fiberwiseDistance at h_fw_dist_lt
  obtain ⟨g, _, hg⟩ := Nat.sInf_mem (Set.image_nonempty.mpr Set.univ_nonempty)
    (s := (fun g : BBF_Code 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ =>
      (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g).ncard) '' Set.univ)
  have hb : hammingDist f g ≤ (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g).ncard * 2 ^ steps := by
    let Y := fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g
    let Q := qMap_total_fiber 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) (i := ⟨i, by omega⟩) (steps := steps) (h_i_add_steps := by dsimp; have := pos_of_neZero 𝓡; omega)
    have hs : {x | f x ≠ g.val x} ⊆ (fun p => Q p.1 p.2) '' (Y ×ˢ (Set.univ : Set (Fin (2 ^ steps)))) := by
      intro x hx
      refine ⟨⟨iteratedQuotientMap 𝔽q β h_ℓ_add_R_rate i steps h_i_add_steps x, pointToIterateQuotientIndex 𝔽q β ⟨i, by omega⟩ steps h_i_add_steps x⟩, ⟨⟨x, rfl, hx⟩, trivial⟩, ?_⟩
      exact (is_fiber_iff_generates_quotient_point 𝔽q β i steps h_i_add_steps x _).mp rfl
    have hc := (Set.ncard_le_ncard hs).trans Set.ncard_image_le
    simpa [Set.ncard_prod, Set.ncard_univ, Nat.card_eq_fintype_card, hammingDist, Set.ncard_eq_toFinset_card'] using hc
  have he : (BBF_CodeDistance ℓ 𝓡 ⟨i.val + steps, by omega⟩ - 1) * 2 ^ steps =
      BBF_CodeDistance ℓ 𝓡 ⟨i, by omega⟩ - 1 := by
    dsimp [BBF_CodeDistance]
    rw [Nat.sub_mul, ← Nat.pow_add, ← Nat.pow_add]
    congr 1 <;> congr 1 <;> omega
  unfold hammingClose
  have hd : Code.distFromCode f (BBF_Code 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩) ≤ (hammingDist f g : ℕ∞) := sInf_le ⟨g, g.property, le_rfl⟩
  apply lt_of_le_of_lt (mul_le_mul_of_nonneg_left hd (bot_le : (0 : ℕ∞) ≤ 2))
  change ((2 : ℕ) : ℕ∞) * ↑(hammingDist f g) < _
  rw [← ENat.coe_mul, ENat.coe_lt_coe]
  have hf := ENat.coe_lt_coe.mp h_fw_dist_lt
  rw [← hg] at hf
  exact Nat.lt_of_le_pred (Nat.succ_pos _) ((Nat.mul_le_mul_left 2 hb).trans (by
    rw [← mul_assoc]
    exact (Nat.mul_le_mul_right (2 ^ steps) (Nat.le_pred_of_lt hf)).trans_eq he))
