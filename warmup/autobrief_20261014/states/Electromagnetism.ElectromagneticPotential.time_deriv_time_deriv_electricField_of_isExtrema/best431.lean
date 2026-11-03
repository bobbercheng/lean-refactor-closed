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
  have hEs j : ContDiff ℝ 2 (A.electricField 𝓕.c t · j) :=
    electricField_apply_contDiff_space hA3 t
  have hEd := fun j k => Space.deriv_differentiable (hEs j) k
  have hb j := Space.time_deriv_comm_space_deriv (i := j)
    (magneticFieldMatrix_contDiff (c := 𝓕.c) _ hA3 (j, i)) t x
  have hs j := Space.fun_deriv_sub (u := j) _ _ (hEd i j) (hEd j i)
  have hc j := Space.deriv_commute (u := j) (v := i) _ (hEs j)
  simp only [time_deriv_magneticFieldMatrix _ (hA.of_le ENat.LEInfty.out), hs, hc] at hb
  have hg : (∑ j, ∂[i] (∂[j] (A.electricField 𝓕.c t · j)) x) =
      1 / 𝓕.ε₀ * ∂[i] (J.chargeDensity 𝓕.c t ·) x := by
    simp only [Space.deriv_eq_fderiv_basis]
    rw [← Finset.sum_apply, ← FunLike.coe_sum, ← fderiv_fun_sum
      (fun j _ => (hEd j j).differentiableAt)]
    conv_lhs =>
      enter [1, 2, y]
      change (∇ ⬝ (A.electricField 𝓕.c t)) y
      rw [((isExtrema_iff_gauss_ampere_magneticFieldMatrix hA J hJ).mp h t y).1]
      rw [div_eq_mul_inv, mul_comm]
    rw [fderiv_const_mul
      (LorentzCurrentDensity.chargeDensity_differentiable_space
        hJ1 t).differentiableAt]
    simp only [ContinuousLinearMap.smul_apply, smul_eq_mul, one_div]
  conv_lhs =>
    enter [1, s]
    rw [Time.deriv_euclid (electricField_differentiable_time
      (hA.of_le ENat.LEInfty.out) _), time_deriv_electricField_of_isExtrema hA J hJ h]
  have hBt := fun j => Space.space_deriv_differentiable_time (i := j)
    (magneticFieldMatrix_contDiff (c := 𝓕.c) _ hA3 (j, i)) x
  have hJt := LorentzCurrentDensity.currentDensity_apply_differentiable_time (c := 𝓕.c)
    hJ1 x i
  have hsum := Differentiable.fun_sum (u := Finset.univ) fun j _ => hBt j
  rw [Time.deriv_eq,
    fderiv_fun_sub (hsum.const_mul _).differentiableAt
      (hJt.const_mul _).differentiableAt,
    fderiv_const_mul hsum.differentiableAt,
    fderiv_const_mul hJt.differentiableAt]
  simp only [FunLike.coe_sub, Pi.sub_apply, ContinuousLinearMap.smul_apply, smul_eq_mul,
    ← Time.deriv_eq]
  rw [Time.deriv_fun_sum _ _ (fun j _ => (hBt j).differentiableAt)]
  simp only [hb, Finset.sum_sub_distrib, hg, FreeSpace.c_sq, mul_comm 𝓕.ε₀ 𝓕.μ₀, mul_inv_rev,
    div_eq_mul_inv, mul_sub, mul_assoc, inv_mul_cancel_left₀ 𝓕.μ₀_ne_zero, one_mul]
