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
  intro φs' φs
  dsimp only [LinearMap.compr₂_apply, LinearMap.comp_apply, LinearMap.mulRight_apply,
    LinearMap.mulLeft_apply, LinearMap.mul_apply', AlgHom.toLinearMap_apply, T, C, M]
  simp only [ofListBasis_eq_ofList]
  let S := List.insertionSort crAnTimeOrderRel (φs' ++ φs)
  let E := fun c => crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ
  let L := List.takeWhile (fun c => ¬crAnTimeOrderRel φ c)
    S ++
    List.filter E φs'
  let R := List.filter E φs ++
    List.filter (fun c => crAnTimeOrderRel φ c ∧ ¬crAnTimeOrderRel c φ)
    S
  have split (l : List 𝓕.CrAnFieldOp)
      (hl : ∀ c ∈ l, E c :=
        by simp [E, hφψ, hψφ, crAnTimeOrderRel_refl]) :
      crAnTimeOrderList (φs' ++ (l ++ φs)) = L ++ l ++ R := by
    rw [crAnTimeOrderList, ← List.append_assoc, insertionSort_of_eq_list _ _ _ _ _ hl]
    simp only [L, R, List.append_assoc]
    rfl
  sorry
