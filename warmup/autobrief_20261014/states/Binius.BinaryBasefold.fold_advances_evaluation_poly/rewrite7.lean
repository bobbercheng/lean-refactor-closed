theorem fold_advances_evaluation_poly
  (i : Fin (ℓ)) (h_i_succ_lt : i + 1 < ℓ + 𝓡)
  (coeffs : Fin (2 ^ (ℓ - ↑i)) → L) (r_chal : L) :
  let P_i : L[X] := intermediateEvaluationPoly 𝔽q β h_ℓ_add_R_rate (i := ⟨i, by
    exact Nat.lt_trans (n := i) (k := ℓ+1) (m := ℓ) (h₁ := i.isLt) (by exact Nat.lt_add_one ℓ)
  ⟩) coeffs
  let f_i := fun (x : (sDomain 𝔽q β h_ℓ_add_R_rate)
      ⟨i, by exact Nat.lt_trans (n := i) (k := r) (m := ℓ) (h₁ := by omega) (by omega)⟩) =>
    P_i.eval (x.val : L)
  let f_i_plus_1 := fold (i := ⟨i, by omega⟩) (h_i := by omega) (f := f_i) (r_chal := r_chal)
  let new_coeffs := fun j : Fin (2^(ℓ - (i + 1))) =>
    (1 - r_chal) * (coeffs ⟨j.val * 2, by
      rw [←Nat.add_zero (j.val * 2)]
      apply mul_two_add_bit_lt_two_pow (c := ℓ - i) (a := j) (b := ℓ - (↑i + 1))
        (i := 0) (by omega) (by omega)
    ⟩) +
    r_chal * (coeffs ⟨j.val * 2 + 1, by
      apply mul_two_add_bit_lt_two_pow (c := ℓ - i) (a := j) (b := ℓ - (↑i + 1))
        (i := 1) (by omega) (by omega)
    ⟩)
  let P_i_plus_1 :=
    intermediateEvaluationPoly 𝔽q β h_ℓ_add_R_rate (i := ⟨i+1, by omega⟩) new_coeffs
  ∀ (y : (sDomain 𝔽q β h_ℓ_add_R_rate)
    ⟨i+1, by omega⟩), f_i_plus_1 y = P_i_plus_1.eval y.val := fun y => by
  have h_eval_qMap k :=
    congrArg Subtype.val (generates_quotient_point_if_is_fiber_of_y 𝔽q β i 1 i.2
      _ y ⟨k, rfl⟩).symm
  simp_rw [iteratedQuotientMap_k_eq_1_is_qMap] at h_eval_qMap
  trans Polynomial.eval y.val
    (Polynomial.C (1-r_chal) * evenRefinement 𝔽q β h_ℓ_add_R_rate i coeffs +
      Polynomial.C r_chal * oddRefinement 𝔽q β h_ℓ_add_R_rate i coeffs)
  · simp only [fold, evaluation_poly_split_identity, Polynomial.eval_add, eval_comp,
      h_eval_qMap, Polynomial.eval_mul, Polynomial.eval_X, Polynomial.eval_C]
    simp only [qMap_total_fiber_one_level_eq 𝔽q β i i.2, Fin2ToF2, one_ne_zero,
      ↓reduceIte, one_smul, Submodule.coe_add, get_sDomain_first_basis_eq_1, zero_smul, zero_add]
    ring1
  · congr 1
    sorry
