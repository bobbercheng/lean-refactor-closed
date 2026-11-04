lemma time_deriv_time_deriv_electricField_of_isExtrema {A : ElectromagneticPotential d}
    {𝓕 : FreeSpace}
    (hA : ContDiff ℝ ∞ A) (J : LorentzCurrentDensity d)
    (hJ : ContDiff ℝ ∞ J) (h : IsExtrema 𝓕 A J)
    (t : Time) (x : Space d) (i : Fin d) :
    ∂ₜ (∂ₜ (A.electricField 𝓕.c · x i)) t =
      𝓕.c ^ 2 * ∑ j, (∂[j] (∂[j] (A.electricField 𝓕.c t · i)) x) -
      𝓕.c ^ 2 / 𝓕.ε₀ * ∂[i] (J.chargeDensity 𝓕.c t ·) x -
      𝓕.c ^ 2 * 𝓕.μ₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
  have hEs : ∀ j, ContDiff ℝ 2 (A.electricField 𝓕.c t · j) :=
    fun j => electricField_apply_contDiff_space (hA.of_le (right_eq_inf.mp rfl)) t
  have hEd := fun j k => Space.deriv_differentiable (hEs j) k
  have hb : ∀ j, ∂ₜ (fun s => ∂[j] (A.magneticFieldMatrix 𝓕.c s · (j, i)) x) t =
      ∂[j] (∂[j] (A.electricField 𝓕.c t · i)) x -
      ∂[i] (∂[j] (A.electricField 𝓕.c t · j)) x := by
    intro j
    rw [Space.time_deriv_comm_space_deriv
      (magneticFieldMatrix_contDiff _ (hA.of_le (right_eq_inf.mp rfl)) (j, i))]
    simp only [time_deriv_magneticFieldMatrix _ (hA.of_le (right_eq_inf.mp rfl))]
    rw [Space.fun_deriv_sub _ _ (hEd i j) (hEd j i), Space.deriv_commute _ (hEs j)]
  have hg : (∑ j, ∂[i] (∂[j] (A.electricField 𝓕.c t · j)) x) =
      1 / 𝓕.ε₀ * ∂[i] (J.chargeDensity 𝓕.c t ·) x := by
    have gauss : (fun y => ∑ j, ∂[j] (A.electricField 𝓕.c t · j) y) =
        fun y => 1 / 𝓕.ε₀ * J.chargeDensity 𝓕.c t y := by
      funext y
      exact ((isExtrema_iff_gauss_ampere_magneticFieldMatrix hA J hJ).mp h t y).1.trans
        (by ring)
    trans ∂[i] (fun y => ∑ j, ∂[j] (A.electricField 𝓕.c t · j) y) x
    · rw [Space.deriv_eq_fderiv_basis, fderiv_fun_sum
        (fun j _ => (hEd j j).differentiableAt)]
      simp only [FunLike.coe_sum, Finset.sum_apply, ← Space.deriv_eq_fderiv_basis]
    · rw [gauss, Space.deriv_eq_fderiv_basis, fderiv_const_mul
        (LorentzCurrentDensity.chargeDensity_differentiable_space
          (hJ.differentiable (by simp)) t).differentiableAt]
      simp only [ContinuousLinearMap.smul_apply, smul_eq_mul, Space.deriv_eq_fderiv_basis]
  conv_lhs =>
    enter [1, s]
    rw [Time.deriv_euclid (electricField_differentiable_time
      (hA.of_le (right_eq_inf.mp rfl)) _), time_deriv_electricField_of_isExtrema hA J hJ h]
  have hBt := fun j => Space.space_deriv_differentiable_time (i := j)
    (magneticFieldMatrix_contDiff (c := 𝓕.c) _ (hA.of_le (right_eq_inf.mp rfl)) (j, i)) x
  have hJt := LorentzCurrentDensity.currentDensity_apply_differentiable_time (c := 𝓕.c)
    (hJ.differentiable (by simp)) x i
  rw [Time.deriv_eq,
    fderiv_fun_sub ((Differentiable.fun_sum fun j _ => hBt j).const_mul _).differentiableAt
      (hJt.const_mul _).differentiableAt,
    fderiv_const_mul (Differentiable.fun_sum fun j _ => hBt j).differentiableAt,
    fderiv_const_mul hJt.differentiableAt]
  simp only [FunLike.coe_sub, Pi.sub_apply, ContinuousLinearMap.smul_apply, smul_eq_mul,
    ← Time.deriv_eq]
  rw [Time.deriv_fun_sum _ _ (fun j _ => (hBt j).differentiableAt)]
  simp only [hb, Finset.sum_sub_distrib, hg]
  generalize (∑ j, ∂[j] (∂[j] (A.electricField 𝓕.c t · i)) x) = a
  simp only [FreeSpace.c_sq]
  field_simp
