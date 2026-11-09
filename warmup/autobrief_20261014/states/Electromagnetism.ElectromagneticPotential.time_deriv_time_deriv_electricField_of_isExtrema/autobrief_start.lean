lemma time_deriv_time_deriv_electricField_of_isExtrema {A : ElectromagneticPotential d}
    {𝓕 : FreeSpace}
    (hA : ContDiff ℝ ∞ A) (J : LorentzCurrentDensity d)
    (hJ : ContDiff ℝ ∞ J) (h : IsExtrema 𝓕 A J)
    (t : Time) (x : Space d) (i : Fin d) :
    ∂ₜ (∂ₜ (A.electricField 𝓕.c · x i)) t =
      𝓕.c ^ 2 * ∑ j, (∂[j] (∂[j] (A.electricField 𝓕.c t · i)) x) -
      𝓕.c ^ 2 / 𝓕.ε₀ * ∂[i] (J.chargeDensity 𝓕.c t ·) x -
      𝓕.c ^ 2 * 𝓕.μ₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
  have hEs : ∀ j, ContDiff ℝ 2 (λy => A.electricField 𝓕.c t y j) :=
    λj => electricField_apply_contDiff_space (i := j) (hA.of_le $ right_eq_inf.mp rfl) t
  have hEd : ∀ j k, Differentiable ℝ (∂[k] λy => A.electricField 𝓕.c t y j) :=
    λj k => Space.deriv_differentiable (hEs j) k
  have hBt : ∀ j, Differentiable ℝ
      (λs => ∂[j] (λy => A.magneticFieldMatrix 𝓕.c s y (j, i)) x) :=
    λj => Space.space_deriv_differentiable_time (i := j)
      (magneticFieldMatrix_contDiff _ (hA.of_le $ right_eq_inf.mp rfl) (j, i)) x
  have hJt : Differentiable ℝ (λs => J.currentDensity 𝓕.c s x i) :=
    LorentzCurrentDensity.currentDensity_apply_differentiable_time (hJ.differentiable $ by simp only [ne_eq, WithTop.coe_eq_zero, ENat.top_ne_zero, not_false_eq_true]) x i
  calc _
    _= ∂ₜ (λt =>
      1 / (𝓕.μ₀ * 𝓕.ε₀) * ∑ j, Space.deriv j (λx => magneticFieldMatrix 𝓕.c A t x (j, i)) x -
      1 / 𝓕.ε₀ * LorentzCurrentDensity.currentDensity 𝓕.c J t x i) t := by
        conv_lhs =>
          enter [1]
          enter [t]
          rw [Time.deriv_euclid $ electricField_differentiable_time
            (hA.of_le $ right_eq_inf.mp rfl) _,
            time_deriv_electricField_of_isExtrema hA J hJ h]
    _ = 1 / (𝓕.μ₀ * 𝓕.ε₀) * ∂ₜ (λt => ∑ j, ∂[j] (A.magneticFieldMatrix 𝓕.c t · (j, i)) x) t -
      1 / 𝓕.ε₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
      rw [Time.deriv_eq]
      rw [fderiv_fun_sub]
      simp only [FunLike.coe_sub, Pi.sub_apply]
      rw [fderiv_const_mul (Differentiable.fun_sum λj _ => hBt j).differentiableAt]
      rw [fderiv_const_mul hJt.differentiableAt]
      simp only [_root_.smul_apply, smul_eq_mul, Time.deriv_eq]
      · exact ((Differentiable.fun_sum λj _ => hBt j).const_mul _).differentiableAt
      · exact hJt.differentiableAt.const_mul _
    _ = 1 / (𝓕.μ₀ * 𝓕.ε₀) * ((∑ j, ∂ₜ λt => ∂[j] (A.magneticFieldMatrix 𝓕.c t · (j, i)) x) t) -
      1 / 𝓕.ε₀ * (∂ₜ (J.currentDensity 𝓕.c · x i) t) := by
      congr
      rw [Time.deriv_eq]
      rw [fderiv_fun_sum λi _ => (hBt i).differentiableAt]
      simp only [FunLike.coe_sum, Finset.sum_apply]
      rfl
    _ = 1 / (𝓕.μ₀ * 𝓕.ε₀) * (∑ j, ∂[j] λx => ∂ₜ (A.magneticFieldMatrix 𝓕.c · x (j, i)) t) x -
        1 / 𝓕.ε₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
      congr
      simp only [Finset.sum_apply]
      congr
      funext k
      rw [Space.time_deriv_comm_space_deriv]
      apply magneticFieldMatrix_contDiff
      apply hA.of_le $ right_eq_inf.mp rfl
    _ = 1 / (𝓕.μ₀ * 𝓕.ε₀) *(∑ j, ∂[j] λx => ∂[j] (A.electricField 𝓕.c t · i) x -
        ∂[i] (A.electricField 𝓕.c t · j) x) x -
        1 / 𝓕.ε₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
        congr
        simp only [Finset.sum_apply]
        congr
        funext k
        congr
        funext x
        rw [time_deriv_magneticFieldMatrix _ $ hA.of_le $ ENat.LEInfty.out]
    _ = (1 / (𝓕.μ₀ * 𝓕.ε₀) * ∑ j, (∂[j] (λx => ∂[j] (A.electricField 𝓕.c t · i) x) x -
          ∂[j] (λx => ∂[i] (A.electricField 𝓕.c t · j) x) x)) -
          1 / 𝓕.ε₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
        congr
        simp only [Finset.sum_apply]
        congr
        funext j
        rw [Space.deriv_eq_fderiv_basis]
        rw [fderiv_fun_sub (hEd _ _).differentiableAt (hEd _ _).differentiableAt]
        simp only [_root_.sub_apply, ← deriv_eq_fderiv_basis]
    _ = 1 / (𝓕.μ₀ * 𝓕.ε₀) * ∑ j, (∂[j] (λx => ∂[j] (A.electricField 𝓕.c t · i) x) x) -
          1 / (𝓕.μ₀ * 𝓕.ε₀) * ∑ j, (∂[j] (λx => ∂[i] (A.electricField 𝓕.c t · j) x) x) -
          1 / 𝓕.ε₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by simp only [mul_inv_rev, Finset.sum_sub_distrib, mul_sub]
    _ = 1 / (𝓕.μ₀ * 𝓕.ε₀) * ∑ j, (∂[j] (λx => ∂[j] (A.electricField 𝓕.c t · i) x) x) -
        1 / (𝓕.μ₀ * 𝓕.ε₀) * ∑ j, (∂[i] (λx => ∂[j] (A.electricField 𝓕.c t · j) x) x) -
        1 / 𝓕.ε₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
        congr
        funext j
        rw [Space.deriv_commute _ $ hEs _, Space.deriv_eq_fderiv_basis]
      _ = 1 / (𝓕.μ₀ * 𝓕.ε₀) * ∑ j, (∂[j] (λx => ∂[j] (A.electricField 𝓕.c t · i) x) x) -
          1 / (𝓕.μ₀ * 𝓕.ε₀) * (∂[i] (λx => ∑ j, ∂[j] (A.electricField 𝓕.c t · j) x) x) -
          1 / 𝓕.ε₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
        congr
        rw [Space.deriv_eq_fderiv_basis]
        rw [fderiv_fun_sum]
        simp only [_root_.sum_apply, ← deriv_eq_fderiv_basis]
        intro j _
        exact (hEd j j).differentiableAt
      _ = 1 / (𝓕.μ₀ * 𝓕.ε₀) * ∑ j, (∂[j] (λx => ∂[j] (A.electricField 𝓕.c t · i) x) x) -
          1 / (𝓕.μ₀ * 𝓕.ε₀) * (∂[i] (λx => (∇ ⬝ (A.electricField 𝓕.c t)) x) x) -
          1 / 𝓕.ε₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
        rfl
      _ = 1 / (𝓕.μ₀ * 𝓕.ε₀) * ∑ j, (∂[j] (∂[j] (A.electricField 𝓕.c t · i)) x) -
          1 / (𝓕.μ₀ * 𝓕.ε₀ ^ 2) * ∂[i] (J.chargeDensity 𝓕.c t ·) x -
          1 / 𝓕.ε₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
        congr 2
        rw [isExtrema_iff_gauss_ampere_magneticFieldMatrix] at h

        conv_lhs =>
          enter [2, 2, x]
          rw [(h t x).1]
        trans 1 / (𝓕.μ₀ * 𝓕.ε₀) * Space.deriv i
            (λx => (1/ 𝓕.ε₀) * LorentzCurrentDensity.chargeDensity 𝓕.c J t x) x
        · congr
          funext x
          ring
        · rw [Space.deriv_eq_fderiv_basis]
          rw [fderiv_const_mul]
          simp only [_root_.smul_apply, ← deriv_eq_fderiv_basis, smul_eq_mul]
          field_simp
          apply Differentiable.differentiableAt
          apply LorentzCurrentDensity.chargeDensity_differentiable_space
          exact hJ.differentiable $ by simp only [ne_eq, WithTop.coe_eq_zero, ENat.top_ne_zero, not_false_eq_true]
        · exact hA
        · exact hJ
      _ = 𝓕.c ^ 2 * ∑ j, (∂[j] (∂[j] (A.electricField 𝓕.c t · i)) x) -
            𝓕.c ^ 2 / 𝓕.ε₀ * ∂[i] (J.chargeDensity 𝓕.c t ·) x -
            𝓕.c ^ 2 * 𝓕.μ₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
          simp only [FreeSpace.c_sq]
          field_simp
