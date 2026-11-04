theorem InitsUpdatesComm
  {P : PureExpr} {σ σ' σ'' : SemanticStore P}
  {ks ks' : List P.Ident} {vs vs' : List P.Expr} :
  UpdateStates σ ks vs σ' →
  InitStates σ' ks' vs' σ'' →
  ∃ σ₁,
    σ₁ = (updatedStates σ ks' vs') ∧
    InitStates σ ks' vs' σ₁ ∧
    UpdateStates σ₁ ks vs σ'' := by
  intros Hup Hinit
  refine ⟨(updatedStates σ ks' vs'), ?_⟩
  have Hk : (isDefined σ' ks) := UpdateStatesDefined Hup
  have Hlen1 := InitStatesLength Hinit
  have Hlen2 := UpdateStatesLength Hup
  induction Hup generalizing σ''
  case update_none =>
    simp_all
    apply And.intro
    refine updatedStatesInit Hlen1 ?_ ?_
    exact InitStatesNotDefined Hinit
    exact InitStatesNodup Hinit
    simp [InitStatesUpdated Hinit]
    constructor
  case update_some σ x v σ₀ xs vs σ₁ Hup Hups ih =>
    refine ⟨rfl, ?_, ?_⟩
    . apply updatedStatesInit Hlen1
      apply UpdateStateNotDefMonotone' ?_ Hup
      apply UpdateStatesNotDefMonotone' ?_ Hups
      exact InitStatesNotDefined Hinit
      exact InitStatesNodup Hinit
    . apply UpdateStates.update_some (σ':=updatedStates σ₀ ks' vs')
      . simp [UpdateStateUpdated Hup, updatedStates]
        rewrite [← updatedStateComm']
        . have Hdef := UpdateStateDefined' Hup
          simp [isDefined, Option.isSome] at Hdef
          split at Hdef <;> simp_all only [List.length_cons, Bool.false_eq_true]
          next val heq =>
          apply updatedStateUpdate (v':=val)
          apply InitStatesSomeMonotone heq
          apply updatedStatesInit
          . simp_all only
          . apply UpdateStateNotDefMonotone' ?_ Hup
            apply UpdateStatesNotDefMonotone' ?_ Hups
            apply InitStatesNotDefined Hinit
          . exact InitStatesNodup Hinit
        . rewrite [List.unzip_zip] <;> simp_all only [List.length_cons]
          have Hnd := InitStatesNotDefined Hinit
          simp only [isDefined] at *
          intros Hin
          specialize Hnd _ Hin
          simp_all
      . apply (ih Hinit ?_ ?_).2.2
        . simp [isDefined] at * <;> simp_all
        . grind
