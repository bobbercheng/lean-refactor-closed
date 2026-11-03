theorem putnam_1964_b2
(S : Type*) [Fintype S] [Nonempty S]
(P : Finset (Set S))
(hPP : ∀ T ∈ P, ∀ U ∈ P, T ∩ U ≠ ∅)
(hPS : ¬∃ T : Set S, T ∉ P ∧ (∀ U ∈ P, T ∩ U ≠ ∅))
: (P.card = 2 ^ (Fintype.card S - 1))  := by
  classical
  have h : P.compls = Pᶜ := by
    sorry
  have hc := Finset.card_compls P
  rw [h, Finset.card_compl, Fintype.card_set, ← mul_pow_sub_one NeZero.out] at hc
  omega
