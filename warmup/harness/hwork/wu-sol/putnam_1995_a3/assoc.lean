theorem putnam_1995_a3
(relation : (Fin 9 → ℤ) → (Fin 9 → ℤ) → Prop)
(digits_to_num : (Fin 9 → ℤ) → ℤ)
(hdigits_to_num : digits_to_num = fun dig => ∑ i : Fin 9, (dig i) * 10^i.1)
(hrelation : ∀ d e : (Fin 9 → ℤ), relation d e ↔ (∀ i : Fin 9, d i < 10 ∧ d i ≥ 0 ∧ e i < 10 ∧ e i ≥ 0) ∧ (∀ i : Fin 9, 7 ∣ (digits_to_num (fun j : Fin 9 => if j = i then e j else d j))))
: ∀ d e f : (Fin 9 → ℤ), ((relation d e) ∧ (relation e f)) → (∀ i : Fin 9, 7 ∣ d i - f i) := by
  have swap (x y : _ → ℤ) i :
      digits_to_num (fun j => if j = i then y j else x j) =
      digits_to_num x + y i * 10 ^ i.1 - x i * 10 ^ i.1 := by
    rw [hdigits_to_num, ← sub_eq_iff_eq_add', ← Finset.sum_sub_distrib]
    simp only [ite_mul, ite_sub, sub_self, Finset.sum_ite_eq', Finset.mem_univ, if_true]
    abel
  intro d e f ⟨hd, he⟩
  rw [hrelation] at hd he
  simp only [swap] at hd he
  have hs := Finset.dvd_sum (s := Finset.univ) (fun i _ => hd.2 i)
  simp only [Finset.sum_add_distrib, Finset.sum_sub_distrib,
    Finset.sum_const, Finset.card_fin, nsmul_eq_mul, ← congrFun hdigits_to_num] at hs
  intro i
  apply (show IsCoprime (7 : ℤ) 10 by decide).pow_right.dvd_of_dvd_mul_right
  convert dvd_sub (dvd_sub hs (dvd_add (hd.2 i) (he.2 i))) (dvd_mul_right 7 (digits_to_num d)) using 1
  ring1
