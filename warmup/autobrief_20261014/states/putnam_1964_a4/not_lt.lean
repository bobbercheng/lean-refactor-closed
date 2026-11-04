theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hB⟩ := boundedu
  obtain ⟨i, j, hij, heq⟩ := (Set.Finite.pi fun _ => Set.finite_Icc B T).exists_lt_map_eq_of_forall_mem (by exact fun n (k : Fin 4) _ => hB (n + k))
  refine ⟨i, j - i, Nat.sub_pos_of_lt hij, fun n => Nat.strong_induction_on n ?_⟩
  intro n ih hn
  by_cases hm : ¬n < i + 4
  · clear hij
    apply @Int.cast_injective ℝ
    simp (disch := omega) only [hu, Nat.sub_add_comm, ih]
  · convert (congrFun heq ⟨n - i, by omega⟩).symm using 2 <;> dsimp <;> omega
