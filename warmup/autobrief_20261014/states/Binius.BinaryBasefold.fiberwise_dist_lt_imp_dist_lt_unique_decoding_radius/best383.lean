theorem fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius (i : Fin ℓ) (steps : ℕ)
    [NeZero steps] (h_i_add_steps : i.val + steps ≤ ℓ)
    (f : OracleFunction 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  (h_fw_dist_lt : fiberwiseClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate)
    (i := i) (steps := steps) (h_i_add_steps := h_i_add_steps) (f := f)) :
  hammingClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ f := by
  unfold fiberwiseClose at h_fw_dist_lt
  classical
  let C := BBF_Code 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, Nat.lt_succ_of_lt i.2⟩
  let d := fiberwiseDistance 𝔽q β i steps h_i_add_steps f
  haveI : Nonempty C := ⟨0⟩
  obtain ⟨⟨g, hg⟩, _, hd⟩ := Nat.sInf_mem ((Set.image_nonempty (f :=
    fun g : C => (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g.1).ncard)).mpr Set.univ_nonempty)
  have hb : hammingDist f g ≤ d * 2 ^ steps := by
    rw [show d = _ from hd.symm]
    let H := Finset.univ.filter (fun x => f x ≠ g x)
    let Y := fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g
    let Q := qMap_total_fiber 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, i.2.trans ((Nat.le_add_right ℓ 𝓡).trans_lt h_ℓ_add_R_rate)⟩ steps
      (Nat.lt_add_of_pos_right_of_le _ _ _ h_i_add_steps)
    change H.card ≤ Y.ncard * 2 ^ steps
    rw [Set.ncard_eq_toFinset_card', ←Fintype.card_fin (2 ^ steps), ←Finset.card_univ (α := Fin (2 ^ steps)), ←Finset.card_product]
    apply Finset.card_le_card_of_surjOn (fun p => Q p.1 p.2)
    intro x hx
    let y := iteratedQuotientMap 𝔽q β h_ℓ_add_R_rate i steps h_i_add_steps x
    refine ⟨(y, _), ?_, (is_fiber_iff_generates_quotient_point 𝔽q β i steps h_i_add_steps x y).mp rfl⟩
    exact Finset.mem_product.mpr ⟨Set.mem_toFinset.mpr
      ⟨x, rfl, (Finset.mem_filter.mp hx).2⟩, Finset.mem_univ _⟩
  have hn : 2 * hammingDist f g < BBF_CodeDistance ℓ 𝓡 i.castSucc := by
    have hf := Nat.le_of_lt_succ (WithTop.coe_lt_coe.1 h_fw_dist_lt)
    have hh := (Nat.mul_le_mul_left 2 hb).trans
      (by simpa only [←mul_assoc] using Nat.mul_le_mul_right (2 ^ steps) hf)
    dsimp [BBF_CodeDistance] at hh ⊢
    rw [Nat.sub_mul, ←Nat.pow_add, ←Nat.pow_add] at hh
    simp only [Nat.sub_add_eq,
      Nat.sub_add_cancel (Nat.le_sub_of_add_le' (h_i_add_steps.trans (Nat.le_add_right ℓ 𝓡))),
      Nat.sub_add_cancel (Nat.le_sub_of_add_le' h_i_add_steps)] at hh
    exact Nat.lt_succ_of_le hh
  unfold hammingClose
  have hc := Code.distFromCode_le_dist_to_mem f g hg
  exact (mul_le_mul_left' hc 2).trans_lt (by exact_mod_cast hn)
