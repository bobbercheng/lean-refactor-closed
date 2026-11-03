theorem InitsUpdatesComm
  {P : PureExpr} {σ σ' σ'' : SemanticStore P}
  {ks ks' : List P.Ident} {vs vs' : List P.Expr} :
  UpdateStates σ ks vs σ' →
  InitStates σ' ks' vs' σ'' →
  ∃ σ₁,
    σ₁ = (updatedStates σ ks' vs') ∧
    InitStates σ ks' vs' σ₁ ∧
    UpdateStates σ₁ ks vs σ'' := by
  intro u i
  cases UpdateStatesUpdated u ▸ InitStatesUpdated i
  repeat constructor
  apply updatedStatesInit
  rotate_left
  apply UpdateStatesNotDefMonotone' _ u
  exact InitStatesNotDefined i
  exact InitStatesNodup i
  unfold updatedStates
  rewrite [updatedStatesComm]
  apply updatedStatesUpdate
  any_goals simp [List.unzip_zip, UpdateStatesLength u, InitStatesLength i]
  apply updatedStatesDefMonotone
  exact UpdateStatesDefined' u
  intro x hx hy
  cases InitStatesNotDefined i x hy ▸ UpdateStatesDefined u x hx
