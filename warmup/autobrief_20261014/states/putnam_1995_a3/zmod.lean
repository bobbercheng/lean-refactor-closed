theorem putnam_1995_a3
(relation : (Fin 9 → ℤ) → (Fin 9 → ℤ) → Prop)
(digits_to_num : (Fin 9 → ℤ) → ℤ)
(hdigits_to_num : digits_to_num = fun dig => ∑ i : Fin 9, (dig i) * 10^i.1)
(hrelation : ∀ d e : (Fin 9 → ℤ), relation d e ↔ (∀ i : Fin 9, d i < 10 ∧ d i ≥ 0 ∧ e i < 10 ∧ e i ≥ 0) ∧ (∀ i : Fin 9, 7 ∣ (digits_to_num (fun j : Fin 9 => if j = i then e j else d j))))
: ∀ d e f : (Fin 9 → ℤ), ((relation d e) ∧ (relation e f)) → (∀ i : Fin 9, 7 ∣ d i - f i) := by
  letI : Fact (Nat.Prime 7) := ⟨by decide⟩
  let S (a : Fin 9 → ℤ) : ZMod 7 := ∑ j, (a j : ZMod 7) * 10^j.1
  have replace (a b : Fin 9 → ℤ) j :
      (digits_to_num (fun k => if k = j then b k else a k) : ZMod 7) =
      S a + ((b j : ZMod 7) * 10^j.1 - (a j : ZMod 7) * 10^j.1) := by
    apply eq_add_of_sub_eq'
    simp only [hdigits_to_num, S, Int.cast_sum, Int.cast_mul, Int.cast_pow,
      Int.cast_ofNat, ← Finset.sum_sub_distrib, Int.cast_ite, ite_mul,
      ite_sub, sub_self, Fintype.sum_ite_eq']
  have eqn a b (h : relation a b) : ∀ j, S a + ((b j : ZMod 7) * 10^j.1 - (a j : ZMod 7) * 10^j.1) = 0 := by
    intro j
    rw [← replace]
    exact (ZMod.intCast_zmod_eq_zero_iff_dvd _ 7).mpr (((hrelation a b).mp h).2 j)
  intro d e f h i
  have h₁ := eqn d e h.1
  have h₂ := eqn e f h.2 i
  have hs : S d + S e = 0 := by
    have hs := congrArg (fun g : Fin 9 → ZMod 7 => ∑ j, g j) (funext h₁)
    simp only [Finset.sum_add_distrib, Finset.sum_sub_distrib, Fin.sum_const,
      nsmul_eq_mul, Finset.sum_const_zero] at hs
    change 2 * S d + (S e - S d) = 0 at hs
    linear_combination hs
  apply (ZMod.intCast_zmod_eq_zero_iff_dvd (d i - f i) 7).mp
  have hz : ((d i : ZMod 7) - f i) * 10^i.1 = 0 := by
    linear_combination hs - h₁ i - h₂
  have := (mul_eq_zero.mp hz).resolve_right (pow_ne_zero _ (show (10 : ZMod 7) ≠ 0 by decide))
  simpa only [Int.cast_sub] using this
