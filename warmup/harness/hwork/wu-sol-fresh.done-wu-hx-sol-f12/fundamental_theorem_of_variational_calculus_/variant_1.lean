lemma fundamental_theorem_of_variational_calculus' {f : Y → V}
    (μ : Measure Y) [IsFiniteMeasureOnCompacts μ] [μ.IsOpenPosMeasure]
    [OpensMeasurableSpace Y]
    (hf : Continuous f) (hg : ∀ g, IsTestFunction g → ∫ x, ⟪f x, g x⟫_ℝ ∂μ = 0) :
    f = 0 := by
  funext x₀
  false_or_by_contra
  rename_i hx₀
  have hc := Continuous.inner' (𝕜 := ℝ) f (λ_ => f x₀) hf continuous_const
  have hp := real_inner_self_nonneg'.lt_of_ne' $ inner_self_eq_zero'.not.mpr hx₀
  obtain ⟨φ, hφs, hφc, hφd, hφn, hφ1⟩ :=
    exists_contDiff_tsupport_subset $ hc.continuousAt.eventually_const_lt hp
  refine' ((hφd.continuous.fun_mul hc).integral_pos_of_hasCompactSupport_nonneg_nonzero
    (μ := μ) hφc.mul_right _ (hφ1.symm ▸ (one_mul _).symm ▸ hp.ne')).ne' $ by
      simpa only [inner_smul_right'] using
        hg _ $ IsTestFunction.smul_right ⟨hφd, hφc⟩ contDiff_const
  intro x
  by_cases hx : φ x = 0
  · simp [hx]
  · exact mul_nonneg (Set.range_subset_iff.mp hφn x).1 (hφs $ subset_tsupport φ hx).le
