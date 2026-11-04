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


  have ht := congrArg (fun f => ∂ₜ f t) (funext fun s =>
    (Time.deriv_euclid (electricField_differentiable_time hA3.of_succ x) s).trans
      (time_deriv_electricField_of_isExtrema hA J hJ h s x i))
  have hBt j := Space.space_deriv_differentiable_time (i := j) (hB j) x t
  have hJt := @LorentzCurrentDensity.currentDensity_apply_differentiable_time d 𝓕.c J hJ1 x i t
  sorry
