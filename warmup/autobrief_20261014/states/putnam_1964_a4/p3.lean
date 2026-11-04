theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hB⟩ := boundedu
  let f (n : ℕ) (k : Fin 4) := u (n + k)
  have hf : ∀ n, f n ∈ Set.pi Set.univ (fun _ => Set.Icc B T) :=
    fun n k _ => hB _
  obtain ⟨i, j, hij, heq⟩ := Set.Finite.exists_lt_map_eq_of_forall_mem hf (Set.Finite.pi fun _ => Set.finite_Icc _ _)
  have h : ∀ m, u (i + m) = u (j + m) := by
    intro m
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · exact congrFun heq ⟨m, hm⟩
      · have hm : 4 ≤ m := by omega
        apply Int.cast_injective (α := ℝ)
        rw [(hu (i + m) (by omega)).1, (hu (j + m) (by omega)).1]
        simp (disch := omega) only [Nat.add_sub_assoc, ih]
  refine ⟨i, j - i, by omega, ?_⟩
  intro n hn
  simpa [show i + (n - i) = n by omega, show j + (n - i) = n + (j - i) by omega] using (h (n - i)).symm
