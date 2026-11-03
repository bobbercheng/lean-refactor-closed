theorem putnam_1995_a3
(relation : (Fin 9 → ℤ) → (Fin 9 → ℤ) → Prop)
(digits_to_num : (Fin 9 → ℤ) → ℤ)
(hdigits_to_num : digits_to_num = fun dig => ∑ i : Fin 9, (dig i) * 10^i.1)
(hrelation : ∀ d e : (Fin 9 → ℤ), relation d e ↔ (∀ i : Fin 9, d i < 10 ∧ d i ≥ 0 ∧ e i < 10 ∧ e i ≥ 0) ∧ (∀ i : Fin 9, 7 ∣ (digits_to_num (fun j : Fin 9 => if j = i then e j else d j))))
: ∀ d e f : (Fin 9 → ℤ), ((relation d e) ∧ (relation e f)) → (∀ i : Fin 9, 7 ∣ d i - f i) := by
  have replace (a b : _ → _) i :
      digits_to_num (fun j => if j = i then b j else a j) =
        digits_to_num a + (b i * 10^i.1 - a i * 10^i.1) := by
    apply eq_add_of_sub_eq'
    simp only [hdigits_to_num, ← Finset.sum_sub_distrib,
      ite_mul, ite_sub, sub_self, Fintype.sum_ite_eq']
  intro d e f h i
  simp only [hrelation, replace] at h
  choose k hk using h.1.2
  choose l hl using h.2.2
  apply (show IsCoprime (7 : ℤ) 10 by decide).pow_right |>.dvd_of_dvd_mul_right
  use (∑ j, k j) - digits_to_num d - k i - l i
  simp only [mul_sub, Finset.mul_sum, ← hk, ← hl i, Finset.sum_add_distrib, Finset.sum_sub_distrib,
    Fin.sum_const, Int.nsmul_eq_mul]
  rw [hdigits_to_num]
  ring1
