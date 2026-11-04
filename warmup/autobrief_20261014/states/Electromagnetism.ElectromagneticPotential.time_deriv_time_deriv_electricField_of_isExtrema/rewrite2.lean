lemma time_deriv_time_deriv_electricField_of_isExtrema {A : ElectromagneticPotential d}
    {𝓕 : FreeSpace}
    (hA : ContDiff ℝ ∞ A) (J : LorentzCurrentDensity d)
    (hJ : ContDiff ℝ ∞ J) (h : IsExtrema 𝓕 A J)
    (t : Time) (x : Space d) (i : Fin d) :
    ∂ₜ (∂ₜ (A.electricField 𝓕.c · x i)) t =
      𝓕.c ^ 2 * ∑ j, (∂[j] (∂[j] (A.electricField 𝓕.c t · i)) x) -
      𝓕.c ^ 2 / 𝓕.ε₀ * ∂[i] (J.chargeDensity 𝓕.c t ·) x -
      𝓕.c ^ 2 * 𝓕.μ₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
  have hJ1 := hJ.differentiable (by simp)
  have hA3 : ContDiff ℝ 3 A := hA.of_le ENat.LEInfty.out
  have hEs j := @electricField_apply_contDiff_space d j 2 A 𝓕.c hA3 t
  have hEd := fun j => Space.deriv_differentiable (hEs j)
  have hB j := @magneticFieldMatrix_contDiff d 2 𝓕.c A hA3 (j, i)
  have hg := congrArg (fun f => fderiv ℝ f x (Space.basis i))
    (funext fun y => ((isExtrema_iff_gauss_ampere_magneticFieldMatrix hA J hJ).mp h t y).1)
  unfold Space.div at hg
  simp only [div_eq_mul_inv, fderiv_fun_sum (fun j _ => (hEd j j).differentiableAt),
    fderiv_mul_const (LorentzCurrentDensity.chargeDensity_differentiable_space
      hJ1 t).differentiableAt] at hg

  conv_lhs =>
    enter [1, s]
    rw [Time.deriv_euclid (electricField_differentiable_time
      hA3.of_succ _), time_deriv_electricField_of_isExtrema hA J hJ h]
  have hBt j := Space.space_deriv_differentiable_time (i := j) (hB j) x t
  have hJt := @LorentzCurrentDensity.currentDensity_apply_differentiable_time d 𝓕.c J hJ1 x i t
  simp (disch := fun_prop) only [Time.deriv_eq, fderiv_fun_sub, fderiv_const_mul, fderiv_fun_sum, ContinuousLinearMap.sub_apply, ContinuousLinearMap.smul_apply,
    smul_eq_mul, FunLike.coe_sum, Finset.sum_apply,
    ← Space.deriv_eq_fderiv_basis] at hg ⊢
  simp only [← Time.deriv_eq,
    fun j => Space.time_deriv_comm_space_deriv (i := j) (hB j),
    time_deriv_magneticFieldMatrix _ hA3.of_succ,
    Space.fun_deriv_sub _ _ (hEd i _) (hEd _ i),
    fun j => @Space.deriv_commute ℝ d j i _ _ _ (hEs j),
    Finset.sum_sub_distrib, hg, FreeSpace.c_sq, mul_comm 𝓕.ε₀ 𝓕.μ₀, mul_inv_rev,
    div_eq_mul_inv, mul_sub, mul_assoc, inv_mul_cancel_left₀ 𝓕.μ₀_ne_zero, one_mul]
