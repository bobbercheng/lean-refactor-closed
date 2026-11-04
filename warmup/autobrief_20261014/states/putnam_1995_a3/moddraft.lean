theorem putnam_1995_a3
(relation : (Fin 9 → ℤ) → (Fin 9 → ℤ) → Prop)
(digits_to_num : (Fin 9 → ℤ) → ℤ)
(hdigits_to_num : digits_to_num = fun dig => ∑ i : Fin 9, (dig i) * 10^i.1)
(hrelation : ∀ d e : (Fin 9 → ℤ), relation d e ↔ (∀ i : Fin 9, d i < 10 ∧ d i ≥ 0 ∧ e i < 10 ∧ e i ≥ 0) ∧ (∀ i : Fin 9, 7 ∣ (digits_to_num (fun j : Fin 9 => if j = i then e j else d j))))
: ∀ d e f : (Fin 9 → ℤ), ((relation d e) ∧ (relation e f)) → (∀ i : Fin 9, 7 ∣ d i - f i) := by
  have replace (a b : _ → _) i :
      digits_to_num (fun j => if j = i then b j else a j) =
        digits_to_num a + (b i - a i) * 10^i.1 := by
    apply eq_add_of_sub_eq'
    simp only [hdigits_to_num, ← Finset.sum_sub_distrib, ← sub_mul,
      ite_sub, sub_self, ite_mul, Fintype.sum_ite_eq']
  intro d e f h i
  simp only [hrelation, replace] at h
  letI : Fact (Nat.Prime 7) := ⟨by decide⟩
  have h₁ (j : Fin 9) : (digits_to_num d : ZMod 7) + ((e j : ZMod 7) - d j) * 10^j.1 = 0 := by
    exact_mod_cast (ZMod.intCast_zmod_eq_zero_iff_dvd _ 7).mpr (h.1.2 j)
  have h₂ : (digits_to_num e : ZMod 7) + ((f i : ZMod 7) - e i) * 10^i.1 = 0 := by
    exact_mod_cast (ZMod.intCast_zmod_eq_zero_iff_dvd _ 7).mpr (h.2.2 i)
  have hs := Finset.sum_eq_zero (s := Finset.univ) (fun j _ => h₁ j)
  have ht : (digits_to_num d : ZMod 7) + digits_to_num e = 0 := by
    sorry
  apply (ZMod.intCast_zmod_eq_zero_iff_dvd _ 7).mp
  push_cast
  have hn : (10 : ZMod 7)^i.1 ≠ 0 := pow_ne_zero _ (by decide)
  apply (mul_eq_zero.mp (show ((d i : ZMod 7) - f i) * 10^i.1 = 0 by
    linear_combination ht - h₁ i - h₂)).resolve_right hn
