theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hB⟩ := boundedu
  obtain ⟨i, j, hij, heq⟩ := (Set.Finite.pi fun _ => Set.finite_Icc B T).exists_lt_map_eq_of_forall_mem (by exact fun n (k : Fin 4) _ => hB (n + k))
  have h m (k : Fin 4) : u (i + m + k) = u (j + m + k) := by
    induction m generalizing k with
    | zero => exact congrFun heq k
    | succ m ih =>
      by_cases hk : (k : ℕ) < 3
      · convert ih ⟨k + 1, by omega⟩ using 2 <;> dsimp <;> omega
      · have hk : (k : ℕ) = 3 := by omega
        have ih' (r : ℕ) (hr : r < 4) := ih ⟨r, hr⟩
        clear hij
        simp only [Nat.add_assoc] at ih'
        apply @Int.cast_injective ℝ
        simp (disch := omega) only [hk, Nat.add_assoc, Nat.reduceAdd, hu, Nat.add_sub_assoc, Nat.reduceSub, ih']
  refine ⟨i, j - i, Nat.sub_pos_of_lt hij, ?_⟩
  intro n hn
  convert (h (n - i) 0).symm using 2 <;> simp <;> omega
