theorem fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius (i : Fin ℓ) (steps : ℕ)
    [NeZero steps] (h_i_add_steps : i.val + steps ≤ ℓ)
    (f : OracleFunction 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  (h_fw_dist_lt : fiberwiseClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate)
    (i := i) (steps := steps) (h_i_add_steps := h_i_add_steps) (f := f)) :
  hammingClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ f := by
  unfold fiberwiseClose at h_fw_dist_lt
  classical
  let C := BBF_Code 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩
  let d := fiberwiseDistance 𝔽q β i steps h_i_add_steps f
  haveI : Nonempty C := ⟨0⟩
  obtain ⟨g, hg, hd⟩ : ∃ g ∈ C, d = (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g).ncard := by
    obtain ⟨g, _, he⟩ := Nat.sInf_mem (Set.image_nonempty.mpr
      (Set.univ_nonempty : (Set.univ : Set C).Nonempty))
    exact ⟨g, g.2, he.symm⟩
  have hb : hammingDist f g ≤ d * 2 ^ steps := by
    rw [hd]
    set ΔH := Finset.filter (fun x => f x ≠ g x) Finset.univ
    have h_dist_eq_card : hammingDist f g = ΔH.card := by
      simp only [hammingDist, ne_eq, ΔH]
    rw [h_dist_eq_card]
    -- Y_bad is the set of quotient points y that THERE EXISTS a bad fiber point x
    set Y_bad := fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g
    simp only at * -- simplify domain indices everywhere

    -- ⊢ #ΔH ≤ Y_bad.ncard * 2 ^ steps

    have hFinType_Y_bad : Fintype Y_bad := by exact Fintype.ofFinite ↑Y_bad
    -- Every point of disagreement `x` must belong to a fiber over some `y` in `Y_bad`,
    -- BY DEFINITION of `Y_bad`. Therefore, `ΔH` is a subset of the union of the fibers
    -- of `Y_bad`
    have h_ΔH_subset_bad_fiber_points : ΔH ⊆ Finset.biUnion Y_bad.toFinset
        (t := fun y => ((qMap_total_fiber 𝔽q β (i := ⟨i, by omega⟩) (steps := steps)
          (h_i_add_steps := by apply Nat.lt_add_of_pos_right_of_le; omega) (y := y)) ''
          (Finset.univ : Finset (Fin ((2:ℕ)^steps)))).toFinset) := by
      -- ⊢ If any x ∈ ΔH, then x ∈ Union(qMap_total_fiber(y), ∀ y ∈ Y_bad)
      intro x hx_in_ΔH; -- ⊢ x ∈ Union(qMap_total_fiber(y), ∀ y ∈ Y_bad)
      simp only [ΔH, Finset.mem_filter] at hx_in_ΔH
      -- Now we actually apply iterated qMap into x to get y_of_x,
      -- then x ∈ qMap_total_fiber(y_of_x) by definition
      let y_of_x := iteratedQuotientMap 𝔽q β h_ℓ_add_R_rate i steps h_i_add_steps x
      apply Finset.mem_biUnion.mpr; use y_of_x
      -- ⊢ y_of_x ∈ Y_bad.toFinset ∧ x ∈ qMap_total_fiber(y_of_x)
      have h_elemenet_Y_bad : y_of_x ∈ Y_bad.toFinset := by
        -- ⊢ y ∈ Y_bad.toFinset
        simp only [fiberwiseDisagreementSet, iteratedQuotientMap, ne_eq, Subtype.exists,
          Set.toFinset_setOf, mem_filter, mem_univ, true_and, Y_bad]
        -- one bad fiber point of y_of_x is x itself
        let X := x.val
        have h_X_in_source : X ∈ sDomain 𝔽q β h_ℓ_add_R_rate (i := ⟨i, by omega⟩) := by
          exact Submodule.coe_mem x
        use X
        use h_X_in_source
        -- ⊢ Ŵ_steps⁽ⁱ⁾(X) = y (iterated quotient map) ∧ ¬f ⟨X, ⋯⟩ = g ⟨X, ⋯⟩
        have h_forward_iterated_qmap : Polynomial.eval X
            (intermediateNormVpoly 𝔽q β h_ℓ_add_R_rate ⟨↑i, by omega⟩
              ⟨steps, by simp only; omega⟩) = y_of_x := by
          simp only [iteratedQuotientMap, X, y_of_x];
        have h_eval_diff : f ⟨X, by omega⟩ ≠ g ⟨X, by omega⟩ := by
          unfold X
          simp only [Subtype.coe_eta, ne_eq, hx_in_ΔH, not_false_eq_true]
        simp only [h_forward_iterated_qmap, Subtype.coe_eta, h_eval_diff,
          not_false_eq_true, and_self]
      simp only [h_elemenet_Y_bad, true_and]

      set qMapFiber := qMap_total_fiber 𝔽q β (i := ⟨i, by omega⟩) (steps := steps)
        (h_i_add_steps := by apply Nat.lt_add_of_pos_right_of_le; omega) (y := y_of_x)
      simp only [coe_univ, Set.image_univ, Set.toFinset_range, mem_image, mem_univ, true_and]
      use (pointToIterateQuotientIndex (i := ⟨i, by omega⟩) (steps := steps)
        (h_i_add_steps := by omega) (x := x))
      have h_res := is_fiber_iff_generates_quotient_point 𝔽q β i steps (by omega)
        (x := x) (y := y_of_x).mp (by rfl)
      exact h_res
    -- ⊢ #ΔH ≤ Y_bad.ncard * 2 ^ steps
    -- The cardinality of a subset is at most the cardinality of the superset.
    apply (Finset.card_le_card h_ΔH_subset_bad_fiber_points).trans
    -- The cardinality of a disjoint union is the sum of cardinalities.
    rw [Finset.card_biUnion]
    · -- The size of the sum is the number of bad fibers (`Y_bad.ncard`) times
      -- the size of each fiber (`2 ^ steps`).
      simp only [Set.toFinset_card]
      have h_card_fiber_per_quotient_point := card_qMap_total_fiber 𝔽q β
        (h_ℓ_add_R_rate := h_ℓ_add_R_rate) i steps h_i_add_steps
      simp only [Set.image_univ, Fintype.card_ofFinset,
        Subtype.forall] at h_card_fiber_per_quotient_point
      have h_card_fiber_of_each_y : ∀ y ∈ Y_bad.toFinset,
          Fintype.card ((qMap_total_fiber 𝔽q β (i := ⟨↑i, by omega⟩) (steps := steps)
            (h_i_add_steps := by apply Nat.lt_add_of_pos_right_of_le; omega) (y := y)) ''
            ↑(Finset.univ : Finset (Fin ((2:ℕ)^steps)))) = 2 ^ steps := by
        intro y hy_in_Y_bad
        have hy_card_fiber_of_y := h_card_fiber_per_quotient_point (a := y) (b := by
          exact Submodule.coe_mem y)
        simp only [coe_univ, Set.image_univ, Fintype.card_ofFinset, hy_card_fiber_of_y]
      rw [Finset.sum_congr rfl h_card_fiber_of_each_y]
      -- ⊢ ∑ x ∈ Y_bad.toFinset, 2 ^ steps ≤ Y_bad.encard.toNat * 2 ^ steps
      simp only [sum_const, Set.toFinset_card, smul_eq_mul, ofNat_pos, pow_pos,
        _root_.mul_le_mul_right, ge_iff_le]
      conv_rhs => rw [←_root_.Nat.card_coe_set_eq] -- convert .ncard back to .card
      -- ⊢ Fintype.card ↑Y_bad ≤ Nat.card ↑Y_bad
      simp only [card_eq_fintype_card, le_refl]
    · -- Prove that the fibers for distinct quotient points y₁, y₂ are disjoint.
      intro y₁ hy₁ y₂ hy₂ hy_ne
      have h_disjoint := qMap_total_fiber_disjoint (i := ⟨↑i, by omega⟩) (steps := steps)
        (h_i_add_steps := by omega) (y₁ := y₁) (y₂ := y₂) (hy_ne := hy_ne)
      simp only [Function.onFun, coe_univ]
      exact h_disjoint
  have hn : 2 * hammingDist f g < BBF_CodeDistance ℓ 𝓡 ⟨i, by omega⟩ := by
    have hf : 2 * d ≤ BBF_CodeDistance ℓ 𝓡 ⟨i.val + steps, by omega⟩ - 1 :=
      Nat.le_of_lt_succ (WithTop.coe_lt_coe.1 h_fw_dist_lt)
    have he : (BBF_CodeDistance ℓ 𝓡 ⟨i.val + steps, by omega⟩ - 1) * 2 ^ steps =
        BBF_CodeDistance ℓ 𝓡 ⟨i, by omega⟩ - 1 := by
      dsimp [BBF_CodeDistance]
      rw [Nat.sub_mul, ←Nat.pow_add, ←Nat.pow_add]
      congr 2 <;> omega
    have hh := (Nat.mul_le_mul_left 2 hb).trans
      (by simpa only [←mul_assoc] using Nat.mul_le_mul_right (2 ^ steps) hf)
    rw [he] at hh
    exact Nat.lt_of_le_pred (Nat.succ_pos _) hh
  unfold hammingClose
  have hc : Code.distFromCode f C ≤ (hammingDist f g : ℕ∞) := by
    apply sInf_le
    exact ⟨g, hg, le_rfl⟩
  exact (mul_le_mul_left' hc 2).trans_lt (by exact_mod_cast hn)
