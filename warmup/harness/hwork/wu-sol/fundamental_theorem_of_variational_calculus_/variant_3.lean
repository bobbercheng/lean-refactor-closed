lemma fundamental_theorem_of_variational_calculus' {f : Y → V}
    (μ : Measure Y) [IsFiniteMeasureOnCompacts μ] [μ.IsOpenPosMeasure]
    [OpensMeasurableSpace Y]
    (hf : Continuous f) (hg : ∀ g, IsTestFunction g → ∫ x, ⟪f x, g x⟫_ℝ ∂μ = 0) :
    f = 0 := by
  funext x
  false_or_by_contra
  rename_i hx
  have hc := Continuous.inner' (𝕜 := ℝ) _ (λ_ => f x) hf continuous_const
  have hp := real_inner_self_nonneg'.lt_of_ne' $ inner_self_eq_zero'.not.mpr hx
  obtain ⟨φ, hs, hk, hd, hn, hφ⟩ := exists_contDiff_tsupport_subset $ hc.continuousAt.eventually_const_lt hp
  refine' ((hd.continuous.fun_mul hc).integral_pos_of_hasCompactSupport_nonneg_nonzero hk.mul_right ?_ $ by rw [hφ, one_mul]; apply hp.ne').ne' $ by
    simpa only [inner_smul_right'] using hg _ $ IsTestFunction.smul_right ⟨hd, hk⟩ contDiff_const
  intro y
  by_cases hy : y ∈ tsupport φ
  · apply mul_nonneg (Set.range_subset_iff.1 hn y).1 (hs hy).le
  · simp [image_eq_zero_of_notMem_tsupport hy]
