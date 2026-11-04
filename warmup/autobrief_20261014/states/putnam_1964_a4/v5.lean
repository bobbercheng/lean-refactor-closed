theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hB⟩ := boundedu
  let f := fun n => (u n, u (n + 1), u (n + 2), u (n + 3))
  have hf : ∀ n, f n ∈ Set.Icc (B, B, B, B) (T, T, T, T) := by
    intro n
    simp only [f, Set.mem_Icc, Prod.le_def]
    aesop only [hB]
  obtain ⟨i, j, hij, heq⟩ := Set.Finite.exists_lt_map_eq_of_forall_mem hf (Set.finite_Icc _ _)
  simp only [f, Prod.mk.injEq] at heq
  have h : ∀ m, u (i + m) = u (j + m) := by
    intro m
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · interval_cases m <;> simp_all
      · have hm : 4 ≤ m := by omega
        apply Int.cast_injective (α := ℝ)
        rw [(hu (i + m) (by omega)).1, (hu (j + m) (by omega)).1]
        simp (disch := omega) only [Nat.add_sub_assoc, ih]
  refine ⟨i, j - i, by omega, ?_⟩
  intro n hn
  have he := h (n - i)
  have hi : i + (n - i) = n := by omega
  have hj : j + (n - i) = n + (j - i) := by omega
  simpa only [hi, hj] using he.symm
