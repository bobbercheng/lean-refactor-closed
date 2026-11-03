theorem putnam_1995_a3
(relation : (Fin 9 → ℤ) → (Fin 9 → ℤ) → Prop)
(digits_to_num : (Fin 9 → ℤ) → ℤ)
(hdigits_to_num : digits_to_num = fun dig => ∑ i : Fin 9, (dig i) * 10^i.1)
(hrelation : ∀ d e : (Fin 9 → ℤ), relation d e ↔ (∀ i : Fin 9, d i < 10 ∧ d i ≥ 0 ∧ e i < 10 ∧ e i ≥ 0) ∧ (∀ i : Fin 9, 7 ∣ (digits_to_num (fun j : Fin 9 => if j = i then e j else d j))))
: ∀ d e f : (Fin 9 → ℤ), ((relation d e) ∧ (relation e f)) → (∀ i : Fin 9, 7 ∣ d i - f i) := by
  have replace (a b : Fin 9 → ℤ) (i : Fin 9) :
      digits_to_num (fun j => if j = i then b j else a j) =
        digits_to_num a + (b i - a i) * 10^i.1 := by
    apply eq_add_of_sub_eq'
    simp only [hdigits_to_num, ← Finset.sum_sub_distrib, ← sub_mul,
      ite_sub, sub_self, ite_mul, Finset.sum_ite_eq', Finset.mem_univ, if_true]
  intro d e f h i
  have h₁ := (hrelation d e).mp h.1 |>.2
  have h₂ := (hrelation e f).mp h.2 |>.2
  simp only [replace] at h₁ h₂
  choose k hk using h₁
  obtain ⟨l, hl⟩ := h₂ i
  apply (show IsCoprime (7 : ℤ) 10 by norm_num).pow_right (n := i.1) |>.dvd_of_dvd_mul_right
  refine ⟨(∑ j, k j) - digits_to_num d - k i - l, ?_⟩
  simp only [mul_sub, Finset.mul_sum, ← hk, ← hl]
  simp only [sub_mul, Finset.sum_add_distrib, Finset.sum_sub_distrib,
    Finset.sum_const, Finset.card_fin, nsmul_eq_mul]
  rw [hdigits_to_num]
  ring1
