lemma ι_timeOrderF_superCommuteF_eq_time {φ ψ : 𝓕.CrAnFieldOp}
    (hφψ : crAnTimeOrderRel φ ψ) (hψφ : crAnTimeOrderRel ψ φ) (a b : 𝓕.FieldOpFreeAlgebra) :
    ι 𝓣ᶠ(a * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * b) =
    ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(a * b)) := by
  let T := (ι (𝓕 := 𝓕)).toLinearMap.comp timeOrderF
  let C := [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF
  let M := LinearMap.mul ℂ 𝓕.FieldOpFreeAlgebra
  apply LinearMap.congr_fun₂ (f := (M.comp (LinearMap.mulRight ℂ C)).compr₂ T)
    (g := M.compr₂ ((LinearMap.mulLeft ℂ (ι C)).comp T))
  apply LinearMap.ext_basis ofCrAnListFBasis ofCrAnListFBasis
  intro u v
  dsimp [T, C, M]
  simp only [ofListBasis_eq_ofList]
  obtain ⟨L, R, split⟩ : ∃ L R, ∀ l : List 𝓕.CrAnFieldOp,
      (∀ c ∈ l, crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ) →
      ofCrAnListF (crAnTimeOrderList (u ++ (l ++ v))) =
        L * ofCrAnListF l * R := by
    sorry
  have s l (hl : ∀ c ∈ l, crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ :=
      by simp [hφψ, hψφ, crAnTimeOrderRel_refl]) := split l hl
  trans ι (crAnTimeOrderSign (u ++ φ :: ψ :: v) • (L * C * R))
  · sorry
  · sorry
