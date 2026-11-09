lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  have der' : Typing Γ t τ := der
  induction der <;> subst eq
  case var mem => grind
  case app t₁ _ _ t₂ l r ih_l ih_r =>
    right
    cases ih_l rfl l with
    | inl val_l =>
        cases ih_r rfl r with
        | inl val_r =>
            have ⟨σ, t₁, eq⟩ := l.canonical_form_abs val_l
            refine ⟨t₁ ^ᵗᵗ t₂, ?_⟩
            grind
        | inr red_r =>
            obtain ⟨t₂', _⟩ := red_r
            refine ⟨t₁.app t₂', ?_⟩
            grind
    | inr red_l =>
        obtain ⟨t₁', _⟩ := red_l
        refine ⟨t₁'.app t₂, ?_⟩
        grind
  case tapp σ' der _ ih =>
    right
    specialize ih rfl der
    cases ih with
    | inl val =>
        obtain ⟨_, t, _⟩ := der.canonical_form_tabs val
        exists t ^ᵗᵞ σ'
        grind
    | inr red =>
        obtain ⟨t', _⟩ := red
        refine ⟨.tapp t' σ', ?_⟩
        grind
  case let' t₁ σ t₂ τ L der _ ih _ =>
    right
    cases ih rfl der with
    | inl _ =>
        refine ⟨t₂ ^ᵗᵗ t₁, ?_⟩
        grind
    | inr red =>
        obtain ⟨t₁', _⟩ := red
        refine ⟨t₁'.let' t₂, ?_⟩
        grind
  case inl der _ ih =>
    cases (ih rfl der) with
    | inl val => grind
    | inr red =>
        right
        obtain ⟨t', _⟩ := red
        refine ⟨.inl t', ?_⟩
        grind
  case inr der _ ih =>
    cases (ih rfl der) with
    | inl val => grind
    | inr red =>
        right
        obtain ⟨t', _⟩ := red
        refine ⟨.inr t', ?_⟩
        grind
  case case t₁ _ _ t₂ _ t₃ _ der _ _ ih _ _ =>
    right
    cases ih rfl der with
    | inl val =>
        have ⟨t₁, lr⟩ := der.canonical_form_sum val
        cases lr <;> [exists t₂ ^ᵗᵗ t₁; refine ⟨t₃ ^ᵗᵗ t₁, ?_⟩] <;> grind
    | inr red =>
        obtain ⟨t₁', _⟩ := red
        refine ⟨t₁'.case t₂ t₃, ?_⟩
        grind
  case sub => grind
  case abs σ _ τ L _ _=>
    left
    constructor
    apply LC.abs L
    · grind only [→ wf, cases Term.LC]
    · grind
  case tabs L _ _=>
    left
    constructor
    apply LC.tabs L
    · grind only [→ wf, cases Term.LC]
    · grind
