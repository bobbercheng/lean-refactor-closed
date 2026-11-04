theorem fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius (i : Fin ℓ) (steps : ℕ)
    [NeZero steps] (h_i_add_steps : i.val + steps ≤ ℓ)
    (f : OracleFunction 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  (h_fw_dist_lt : fiberwiseClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate)
    (i := i) (steps := steps) (h_i_add_steps := h_i_add_steps) (f := f)) :
  hammingClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ f := by
  classical
  obtain ⟨g, _, hg⟩ := Nat.sInf_mem (s := (fun g : BBF_Code 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ => (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g).ncard) '' Set.univ) (Set.image_nonempty.mpr Set.univ_nonempty)
  dsimp only at hg
  have hd : hammingDist f g ≤ (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g).ncard * 2 ^ steps := by
    let q := iteratedQuotientMap 𝔽q β h_ℓ_add_R_rate i steps h_i_add_steps
    let k := pointToIterateQuotientIndex 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ steps h_i_add_steps
    have hinv (x) := (is_fiber_iff_generates_quotient_point 𝔽q β i steps h_i_add_steps x (q x)).mp rfl
    have hh := Set.ncard_le_ncard_of_injOn (s := {x | f x ≠ g.val x}) (t := (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g) ×ˢ (Set.univ : Set (Fin (2 ^ steps)))) (fun x => (q x, k x)) (by intro x hx; exact ⟨⟨x, rfl, hx⟩, trivial⟩) (by
      intro x hx y hy hxy
      have hq := congrArg Prod.fst hxy
      have hk := congrArg Prod.snd hxy
      dsimp only at hq hk
      dsimp only [k] at hk
      rw [← hinv x, ← hinv y, hq, hk])
    rw [Set.ncard_prod, Set.ncard_univ, Nat.card_fin] at hh
    simpa only [hammingDist, Set.ncard_eq_toFinset_card', Set.toFinset_setOf] using hh
  unfold hammingClose
  refine (mul_le_mul_of_nonneg_left (Code.distFromCode_le_dist_to_mem f g g.2) bot_le).trans_lt ?_
  change ((2 * hammingDist f g : ℕ) : ℕ∞) < _
  rw [ENat.coe_lt_coe]
  have hb : 2 * (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g).ncard ≤ BBF_CodeDistance ℓ 𝓡 ⟨i.val + steps, by omega⟩ - 1 := by
    rw [hg]
    exact Nat.le_of_lt_succ (ENat.coe_lt_coe.mp h_fw_dist_lt)
  have he : (BBF_CodeDistance ℓ 𝓡 ⟨i.val + steps, by omega⟩ - 1) * 2 ^ steps = BBF_CodeDistance ℓ 𝓡 ⟨i, by omega⟩ - 1 := by
    simp only [BBF_CodeDistance, Nat.add_sub_cancel, Nat.sub_mul, ← Nat.pow_add]
    congr 1 <;> congr 1 <;> omega
  apply Nat.lt_of_le_pred (Nat.succ_pos _)
  change 2 * hammingDist f g ≤ BBF_CodeDistance ℓ 𝓡 ⟨i, by omega⟩ - 1
  rw [← he]
  exact (Nat.mul_le_mul_left 2 hd).trans (by simpa [mul_assoc] using Nat.mul_le_mul_right (2 ^ steps) hb)
