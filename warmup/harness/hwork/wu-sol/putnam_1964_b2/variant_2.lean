theorem putnam_1964_b2
(S : Type*) [Fintype S] [Nonempty S]
(P : Finset (Set S))
(hPP : ∀ T ∈ P, ∀ U ∈ P, T ∩ U ≠ ∅)
(hPS : ¬∃ T : Set S, T ∉ P ∧ (∀ U ∈ P, T ∩ U ≠ ∅))
: (P.card = 2 ^ (Fintype.card S - 1)) := by
  simp_all only [Set.disjoint_iff_inter_eq_empty.not.symm]
  apply Nat.mul_left_cancel Nat.two_pos
  rw [mul_pow_sub_one Fintype.card_ne_zero, Fintype.card_set.symm, ← Set.Intersecting.is_max_iff_card_eq hPP]
  grind only [Set.Intersecting]
