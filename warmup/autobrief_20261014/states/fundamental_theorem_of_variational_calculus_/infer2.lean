lemma fundamental_theorem_of_variational_calculus' {f : Y → V}
    (μ : Measure Y) [IsFiniteMeasureOnCompacts μ] [μ.IsOpenPosMeasure]
    [OpensMeasurableSpace Y]
    (hf : Continuous f) (hg : ∀ g, IsTestFunction g → ∫ x, ⟪f x, g x⟫_ℝ ∂μ = 0) :
    f = 0 := by
  ext x₀
  by_contra hx
  have hp := real_inner_self_nonneg'.lt_of_ne' (inner_self_eq_zero'.not.mpr hx)
  have hc := hf.inner' f (fun _ => f x₀) continuous_const
  obtain ⟨φ, hs, hk, hd, hr, he⟩ := exists_contDiff_tsupport_subset
    (hc.continuousAt.preimage_mem_nhds (Ici_mem_nhds hp))
  exact ((hd.continuous.mul hc).integral_pos_of_hasCompactSupport_nonneg_nonzero
    hk.mul_right (fun x => if hx : φ x = 0 then (mul_eq_zero_of_left hx _).ge
      else mul_nonneg (hr (Set.mem_range_self x)).1 (hs (subset_closure hx)))
    (mul_ne_zero (ne_zero_of_eq_one he) hp.ne')).ne' (by
      simpa only [inner_smul_right', Pi.mul_apply] using hg _ ((IsTestFunction.mk hd hk).smul_right contDiff_const))
