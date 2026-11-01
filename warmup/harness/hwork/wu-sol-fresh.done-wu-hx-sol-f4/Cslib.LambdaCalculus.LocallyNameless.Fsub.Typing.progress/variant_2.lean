lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  have der' := der
  induction der <;> subst eq
  case var => simp_all
  all_goals
    have lc := der'.wf.2.1
    simp_all only [true_implies]
    casesm* (_ ∨ _) (∃ _, _)
    first
    | solve_by_elim [Or.inl, Value.abs, Value.tabs, Value.inl, Value.inr]
    | simp only [body_let, body_case] at lc
      cases lc
      aesop (add safe forward [canonical_form_abs, canonical_form_tabs, canonical_form_sum, Value.lc]) (add unsafe constructors Red) (add safe constructors Value)
