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
  dsimp [T, C, M]
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
      𝓣ᶠ(ofCrAnListF φs' * ofCrAnListF l * ofCrAnListF φs) =
      crAnTimeOrderSign (φs' ++ l ++ φs) •
        (ofCrAnListF L * ofCrAnListF l * ofCrAnListF R) := by
    rw [← ofCrAnListF_append, ← ofCrAnListF_append, timeOrderF_ofCrAnListF,
      crAnTimeOrderList, insertionSort_of_eq_list crAnTimeOrderRel φ φs' l φs hl]
    simp only [L, R, ofCrAnListF_append, mul_assoc]
  have empty := split []
  simp only [ofCrAnListF_nil, mul_one, List.append_nil] at empty
  rw [empty]
  simp only [superCommuteF_ofCrAnOpF_ofCrAnOpF, ← ofCrAnListF_singleton,
    ← ofCrAnListF_append, List.cons_append, List.nil_append, mul_sub, sub_mul,
    mul_smul_comm, smul_mul_assoc, map_sub, map_smul]
  rw [split [φ, ψ], split [ψ, φ],
    ← crAnTimeOrderSign_swap_eq_time hφψ hψφ]
  by_cases hq : 𝓕.crAnStatistics ψ = 𝓕.crAnStatistics φ
  · rw [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ hq,
      ← crAnTimeOrderSign]
    sorry
  · sorry
