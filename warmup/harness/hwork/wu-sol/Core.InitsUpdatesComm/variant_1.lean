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
  rcases UpdateStatesUpdated hu ▸ InitStatesUpdated hi
  have hn := InitStatesNotDefined hi
  repeat constructor
  apply updatedStatesInit
  rotate_left
  apply UpdateStatesNotDefMonotone' hn hu
  apply InitStatesNodup hi
  unfold updatedStates
  rewrite [updatedStatesComm]
  apply updatedStatesUpdate
  rotate_left
  apply updatedStatesDefMonotone
  apply UpdateStatesDefined' hu
  all_goals simp [List.unzip_zip, UpdateStatesLength hu, InitStatesLength hi]
  intro k hk hk'
  cases hn k hk' ▸ UpdateStatesDefined hu k hk
