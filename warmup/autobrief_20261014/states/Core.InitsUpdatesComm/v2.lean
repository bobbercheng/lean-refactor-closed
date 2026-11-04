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
  have hk := UpdateStatesDefined' hu
  have := InitStatesLength hi
  refine ⟨_, rfl, updatedStatesInit this hn (InitStatesNodup hi), ?_⟩
  have := UpdateStatesLength hu
  cases InitStatesUpdated hi
  cases UpdateStatesUpdated hu
  unfold updatedStates
  rw [updatedStatesComm]
  exact updatedStatesUpdate this (updatedStatesDefMonotone hk)
  simp only [List.unzip_zip, *]
  intro x hx hx'
  cases hn x hx' ▸ hk x hx
