theorem InitsUpdatesComm
  {P : PureExpr} {σ σ' σ'' : SemanticStore P}
  {ks ks' : List P.Ident} {vs vs' : List P.Expr} :
  UpdateStates σ ks vs σ' →
  InitStates σ' ks' vs' σ'' →
  ∃ σ₁,
    σ₁ = (updatedStates σ ks' vs') ∧
    InitStates σ ks' vs' σ₁ ∧
    UpdateStates σ₁ ks vs σ'' := by
  intro hu hi
  have hn := UpdateStatesNotDefMonotone' (InitStatesNotDefined hi) hu
  have hl := InitStatesLength hi
  have hk := UpdateStatesLength hu
  have hd : ks.Disjoint ks' := by
    intro x hx hx'
    cases hn x hx' ▸ UpdateStatesDefined' hu x hx
  have hc : updatedStates (updatedStates σ ks vs) ks' vs' = updatedStates (updatedStates σ ks' vs') ks vs := by
    exact updatedStatesComm (by simpa [List.unzip_zip, hl, hk] using hd)
  refine ⟨_, rfl, updatedStatesInit hl hn (InitStatesNodup hi), ?_⟩
  sorry
