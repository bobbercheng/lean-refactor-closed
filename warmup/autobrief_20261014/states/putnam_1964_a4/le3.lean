theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hB⟩ := boundedu
  obtain ⟨i, j, hij, heq⟩ := (Set.Finite.pi fun _ : Fin 4 => Set.finite_Icc B T).exists_lt_map_eq_of_forall_mem (by intro n k _; exact hB (n + k))
  have :=  @Nat.strongRec _ fun m ih => by
    by_cases hm : m ≤ 3
    · simpa using congrFun heq.symm ⟨m, hm⟩
    · clear hij
      rify
      simp (disch := omega) only [hu, Nat.add_sub_assoc, ih]
  use i, j - i, Nat.sub_pos_of_lt hij
  intro n hn
  convert this (n - i) using 2 <;> omega
