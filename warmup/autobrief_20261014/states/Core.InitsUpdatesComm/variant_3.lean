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
  let hn := UpdateStatesNotDefMonotone' (InitStatesNotDefined hi) hu
  have := InitStatesLength hi
  refine ⟨_, rfl, updatedStatesInit this hn $ InitStatesNodup hi, ?_⟩
  let := UpdateStatesLength hu
  cases InitStatesUpdated hi
  cases UpdateStatesUpdated hu
  unfold updatedStates
  rw [updatedStatesComm]
  exact updatedStatesUpdate this $ updatedStatesDefMonotone $ UpdateStatesDefined' hu
  simp_all [List.unzip_zip]
  intro x hx hx'
  have := UpdateStatesDefined' hu x hx
  simp_all [hn x hx']
