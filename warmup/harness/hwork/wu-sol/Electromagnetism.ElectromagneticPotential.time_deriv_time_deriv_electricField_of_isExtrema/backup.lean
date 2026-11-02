lemma time_deriv_time_deriv_electricField_of_isExtrema {A : ElectromagneticPotential d}
    {𝓕 : FreeSpace}
    (hA : ContDiff ℝ ∞ A) (J : LorentzCurrentDensity d)
    (hJ : ContDiff ℝ ∞ J) (h : IsExtrema 𝓕 A J)
    (t : Time) (x : Space d) (i : Fin d) :
    ∂ₜ (∂ₜ (A.electricField 𝓕.c · x i)) t =
      𝓕.c ^ 2 * ∑ j, (∂[j] (∂[j] (A.electricField 𝓕.c t · i)) x) -
      𝓕.c ^ 2 / 𝓕.ε₀ * ∂[i] (J.chargeDensity 𝓕.c t ·) x -
      𝓕.c ^ 2 * 𝓕.μ₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
  have hA3 : ContDiff ℝ (2+1) A := hA.of_le (by decide)
  have hJd := hJ.differentiable nofun
  have hBt (j : Fin d) := Space.space_deriv_differentiable_time (i := j)
    (magneticFieldMatrix_contDiff (c := 𝓕.c) A hA3 (j, i)) x
  have hBs := Differentiable.fun_sum (u := Finset.univ) fun j _ => hBt j
  have hJt := LorentzCurrentDensity.currentDensity_apply_differentiable_time (c := 𝓕.c) hJd x i
  have hEd (j k : Fin d) := Space.deriv_differentiable
    (electricField_apply_contDiff_space (c := 𝓕.c) (i := j) hA3 t) k
  have hJs := LorentzCurrentDensity.chargeDensity_differentiable_space (c := 𝓕.c) hJd t
  have hg := congrArg (fun f => ∂[i] f x)
    (funext fun y => ((isExtrema_iff_gauss_ampere_magneticFieldMatrix hA J hJ).mp h t y).1)
  conv_lhs =>
    enter [1, s]
    rw [Time.deriv_euclid (electricField_differentiable_time hA3.of_succ _),
      time_deriv_electricField_of_isExtrema hA J hJ h]
  rw [Time.deriv_eq, fderiv_fun_sub (hBs.const_mul _).differentiableAt
    (hJt.const_mul _).differentiableAt, fderiv_const_mul hBs.differentiableAt,
    fderiv_const_mul hJt.differentiableAt, fderiv_fun_sum fun j _ => (hBt j).differentiableAt]
  simp only [_root_.sub_apply, _root_.smul_apply, _root_.sum_apply, smul_eq_mul, ← Time.deriv_eq, Space.time_deriv_comm_space_deriv
    (magneticFieldMatrix_contDiff A hA3 _), time_deriv_magneticFieldMatrix _ hA3.of_succ]
  simp only [Space.deriv_eq, div_eq_inv_mul] at hg
  unfold Space.div at hg
  simp only [Space.deriv_eq_fderiv_fun] at hEd
  simp (disch := solve_by_elim only [hEd, hJs, Differentiable.differentiableAt]) only [Space.deriv_eq, fderiv_fun_sub, fderiv_fun_sum,
    fderiv_const_mul, _root_.sub_apply, _root_.sum_apply, _root_.smul_apply, smul_eq_mul] at hg ⊢
  simp only [← Space.deriv_eq, Space.deriv_commute (v := i) _
    (electricField_apply_contDiff_space hA3 t), Finset.sum_sub_distrib] at hg ⊢
  rw [hg]
  simp only [FreeSpace.c_sq, one_div, mul_inv_rev, div_eq_mul_inv]
  simp only [mul_right_comm (𝓕.μ₀⁻¹) (𝓕.ε₀⁻¹) 𝓕.μ₀, inv_mul_cancel₀ 𝓕.μ₀_ne_zero, one_mul]
  ring
