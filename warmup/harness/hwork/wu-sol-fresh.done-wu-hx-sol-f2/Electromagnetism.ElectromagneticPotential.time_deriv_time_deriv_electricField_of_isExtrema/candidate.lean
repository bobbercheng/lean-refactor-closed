lemma time_deriv_time_deriv_electricField_of_isExtrema {A : ElectromagneticPotential d}
    {𝓕 : FreeSpace}
    (hA : ContDiff ℝ ∞ A) (J : LorentzCurrentDensity d)
    (hJ : ContDiff ℝ ∞ J) (h : IsExtrema 𝓕 A J)
    (t : Time) (x : Space d) (i : Fin d) :
    ∂ₜ (∂ₜ (A.electricField 𝓕.c · x i)) t =
      𝓕.c ^ 2 * ∑ j, (∂[j] (∂[j] (A.electricField 𝓕.c t · i)) x) -
      𝓕.c ^ 2 / 𝓕.ε₀ * ∂[i] (J.chargeDensity 𝓕.c t ·) x -
      𝓕.c ^ 2 * 𝓕.μ₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
  have hA3 : ContDiff ℝ (2 + 1) A := hA.of_le (by decide)
  have hJd := hJ.differentiable (by simp)
  have hEs := fun j => electricField_apply_contDiff_space (i := j) (c := 𝓕.c) hA3 t
  have hEd := fun j k => Space.deriv_differentiable (hEs j) k
  have hBt := fun j => Space.space_deriv_differentiable_time (i := j)
    (magneticFieldMatrix_contDiff (c := 𝓕.c) _ hA3 (j, i)) x
  have hJt := LorentzCurrentDensity.currentDensity_apply_differentiable_time (c := 𝓕.c) hJd x i
  have hg := congrArg (fun f => Space.deriv i f x) (funext fun y =>
    ((isExtrema_iff_gauss_ampere_magneticFieldMatrix hA J hJ).mp h t y).1)
  have ht : (∂ₜ (A.electricField 𝓕.c · x i)) =
      (fun s => 1 / (𝓕.μ₀ * 𝓕.ε₀) * ∑ j, ∂[j] (A.magneticFieldMatrix 𝓕.c s · (j,i)) x -
      1 / 𝓕.ε₀ * J.currentDensity 𝓕.c s x i) := by
    funext s
    rw [Time.deriv_euclid (electricField_differentiable_time hA3.of_succ _)]
    exact time_deriv_electricField_of_isExtrema hA J hJ h s x i
  rw [ht, Time.deriv_eq]
  simp only [fderiv_fun_sub ((Differentiable.fun_sum fun j _ => hBt j).const_mul _).differentiableAt
    (hJt.const_mul _).differentiableAt, fderiv_const_mul
    (Differentiable.fun_sum fun j _ => hBt j).differentiableAt,
    fderiv_const_mul hJt.differentiableAt, fderiv_fun_sum fun j _ => (hBt j).differentiableAt,
    _root_.sub_apply, _root_.smul_apply, _root_.sum_apply, smul_eq_mul, ← Time.deriv_eq]
  simp_rw [Space.time_deriv_comm_space_deriv (magneticFieldMatrix_contDiff (c := 𝓕.c) _ hA3 _),
    time_deriv_magneticFieldMatrix A hA3.of_succ]
  have hs : ∀ j, ∂[j] (fun y => ∂[j] (A.electricField 𝓕.c t · i) y -
      ∂[i] (A.electricField 𝓕.c t · j) y) x =
      ∂[j] (∂[j] (A.electricField 𝓕.c t · i)) x -
      ∂[i] (∂[j] (A.electricField 𝓕.c t · j)) x := by
    intro j
    rw [Space.deriv_eq, fderiv_fun_sub (hEd i j).differentiableAt (hEd j i).differentiableAt]
    simp only [_root_.sub_apply, ← Space.deriv_eq, Space.deriv_commute _ (hEs j)]
  simp_rw [hs]
  rw [Finset.sum_sub_distrib]
  simp only [div_eq_inv_mul, Space.deriv_eq] at hg
  unfold Space.div at hg
  simp only [fderiv_fun_sum fun j _ => (hEd j j).differentiableAt,
    fderiv_const_mul (LorentzCurrentDensity.chargeDensity_differentiable_space hJd t).differentiableAt,
    _root_.sum_apply, _root_.smul_apply, smul_eq_mul] at hg
  simp only [← Space.deriv_eq] at hg
  rw [hg]
  simp [FreeSpace.c_sq]
  ring
