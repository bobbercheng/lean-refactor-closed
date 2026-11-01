theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hB⟩ := boundedu
  obtain ⟨i, j, hij, h⟩ := (Set.Finite.pi (fun _ => Set.finite_Icc B T)).exists_lt_map_eq_of_forall_mem
    (f := fun n (k : Fin 4) => u (n+k)) (by intro n k hk; apply hB)
  have key m : u (i+m) = u (j+m) := by
    clear hij
    induction m using Nat.strong_induction_on
    rename_i m ih
    by_cases hm : m < 4
    · exact congrFun h ⟨m, hm⟩
    · apply @Int.cast_injective ℝ
      simp (disch := omega) [hu, Nat.add_sub_assoc, ih]
  use i, j-i, Nat.sub_pos_of_lt hij
  intro n hn
  rw [← Nat.add_sub_cancel' hn, key, Nat.add_right_comm, Nat.add_sub_cancel' hij.le]
