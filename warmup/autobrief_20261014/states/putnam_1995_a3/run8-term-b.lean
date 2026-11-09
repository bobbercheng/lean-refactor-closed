theorem putnam_1995_a3
(relation : (Fin 9 → ℤ) → (Fin 9 → ℤ) → Prop)
(digits_to_num : (Fin 9 → ℤ) → ℤ)
(hdigits_to_num : digits_to_num = fun dig => ∑ i : Fin 9, (dig i) * 10^i.1)
(hrelation : ∀ d e : (Fin 9 → ℤ), relation d e ↔ (∀ i : Fin 9, d i < 10 ∧ d i ≥ 0 ∧ e i < 10 ∧ e i ≥ 0) ∧ (∀ i : Fin 9, 7 ∣ (digits_to_num (fun j : Fin 9 => if j = i then e j else d j))))
: ∀ d e f : (Fin 9 → ℤ), ((relation d e) ∧ (relation e f)) → (∀ i : Fin 9, 7 ∣ d i - f i) := by
  have split_term (p : Prop) [Decidable p] (a b c : ℤ) :
      (if p then a else b) * c = b * c + if p then (a - b) * c else 0 := by
    split <;> simp_all only [ite_true, ite_false, sub_mul, add_sub_cancel_left, add_zero]
  intro d e f h i
  simp only [hrelation] at h
  choose k hk using h.1.2
  obtain ⟨l, hl⟩ := h.2.2 i
  apply (show IsCoprime (7 : ℤ) 10 by decide).pow_right |>.dvd_of_dvd_mul_right
  use (∑ j, k j) - digits_to_num d - k i - l
  simp only [mul_sub, Finset.mul_sum, ← hk, ← hl, hdigits_to_num]
  simp only [split_term, Finset.sum_add_distrib, Fintype.sum_ite_eq',
    Finset.sum_const, Finset.card_fin, nsmul_eq_mul, sub_mul,
    Finset.sum_sub_distrib, ← Finset.mul_sum]
  ring1
