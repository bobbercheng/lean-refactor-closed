lemma fundamental_theorem_of_variational_calculus' {f : Y → V}
    (μ : Measure Y) [IsFiniteMeasureOnCompacts μ] [μ.IsOpenPosMeasure]
    [OpensMeasurableSpace Y]
    (hf : Continuous f) (hg : ∀ g, IsTestFunction g → ∫ x, ⟪f x, g x⟫_ℝ ∂μ = 0) :
    f = 0 := by
  ext x₀
  apply inner_self_eq_zero'.mp
  by_contra hx
  have hp := real_inner_self_nonneg'.lt_of_ne' hx
  have hc := hf.inner' (𝕜 := ℝ) f (fun _ => f x₀) continuous_const
  sorry
