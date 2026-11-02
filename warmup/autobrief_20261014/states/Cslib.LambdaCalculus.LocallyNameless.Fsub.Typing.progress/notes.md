# Current banked best
candidate.lean confirmed: anonymous `let := der.wf.2.1`, generalize eq env, induction der <;> subst_vars, shared grind (gen := 2) forwarding canonical_form_abs/tabs/sum and all 12 Red constructors. 70 tokens, 5663 heartbeats, score91.13; all toolchains compatible. New improvement this run: replacing `have` with `let` saved156hb without token change. Local definition remains after induction and IH no longer has LC antecedent (confirmed lean_goals).

# Tested this run
- [tested: noSubwf/noWfLC variants -> each fails tapp] Need Sub.wf and Ty.Wf.lc for argument type LC.
- [tested: noTypingwf -> fails app] IH in have version requires subterm LC.
- [tested: noTypingCases/noLCtapp -> grind rejects unmarked attributes].
- [tested: LCsplit-no-wf -> compiles81tok/8566hb; LCsplit-no-wfs ->87/8099; targetLC app+tapp ->77/5834] LC inversion retaining original copy is not competitive.
- [tested: intro-red-imp, intro-red-moregen, intro-red-suggestions -> all fail app] `intro Red` exists but registers default conclusion patterns, not forward constructor patterns.
- [tested: suggest-canon -> fails app at34214hb] +suggestions does not replace canonical hints.
- Fresh AESOP architecture compiles84tok/58931hb: same original haveLC setup, then `all_goals aesop (add safe forward [wf, Sub.wf, Ty.Wf.lc, Value.lc, canonical_form_abs, canonical_form_tabs, canonical_form_sum]) (add safe constructors Value) (add unsafe constructors Red) (add norm simp [body_let, body_case]) (add safe cases Value (cases_patterns := [Value (.inl _), Value (.inr _)]))`.
- [tested: aesop forward [*] -> syntax error] Wildcard forward syntax unsupported.
- [tested: aesop without cases_patterns clause -> leaves case goals]. Restricted sum Value cases resolves this.
- [tested: aesop-Red-safe -> fails many reduction branches].
- [tested: aesop-only -> fails; aesop-small-simp -> fails var; aesop-no-simpall -> fails app/tapp/etc].
- [tested: direct induction der skeleton -> index [] not variable] Generalization needed.
- [tested: let-gen1 -> fails app] Removing IH LC antecedent still does not make gen1 enough.
- [tested: let-wf ->70tok/6144hb; let-der ->fails tapp; let-der-gen3 ->70/10959; let-gen3 ->70/28707] Retain letLC gen2.
- [tested: let-no-subst ->68tok/6754hb; let-subst-eq ->71/5584; let-minimal-canon (remove Red.abs arrow) ->69/6234] All score worse.
- [tested: let-nozetaDelta ->72/5668; let-noabstract ->72/5581; let-ematch2 ->75/5432] All score worse.

# Confirmed library facts
Typing.wf, Sub.wf, Ty.Wf.lc, Value.lc, Typing.canonical_form_abs/tabs/sum, body_let, body_case exist. `intro Red` is valid grind syntax; `→ Red` is not [tested previous run: rejected non-theorem inductive parameter]. Qualified canonical lemma names needed in lean_run outside theorem namespace.

# Earlier runs and remaining ideas
Original shared-grind architecture had70tokens/5819hb. Many previous small configuration and hint deletions were tested without gains. Gen2 bounds avoid irrelevant recursive reduction construction. Most promising fresh possibility: exploit the now-unconditional IHs produced by `let` with a more selective constructor synthesis architecture; current AESOP version is much too slow. No clear further local edit; keep banked let proof rather than regress.

# Run 10 continuation
Retained banked 70-token/5663hb proof unchanged; confirmed candidate via lean_check cache. lean_profile returns null per-block counts (not informative).
Additional tested variants (all worse): let der.wf.2 (70/6069), cases eq rather than subst_vars (71/5691), named let lc (71/5664). Generalize without equation fails var; removing all three canonical-form forward arrows fails app.
Grind flags -clean, -lookahead, -mbtc, -verbose, -funext each compile at72tokens/~5665hb, so no benefit. +splitImp fails case branch. These flags need not be re-tested.
Fresh rewrite tried AESOP depth-first: haveLC version compiles94tok/59248hb vs best-first85/58931; letLC version fails var/case (AESOP doesn't exploit let LC properly). `dsimp at *` makes no progress in var.
Grind hint order permutations (canonical first/last; Red native/reverse; bodies first/last) all compile70tok/5663-5665hb: ordering has essentially no effect.
New compressed `intro Red`/`! Red` architectures with symbol priority 0 or1 all fail app (even adding forward beta constructors); do not retry. `symbol low Red` syntax rejected (priority must be numeric here).
Arrow deletion confirmed: default Red.tabs69/6344, Red.let_body69/6271, Red.case_inl69/6224, Red.case_inr69/6224; all five beta constructors default65/8627. Default Red.inl fails. These are all worse than retained best.
lean_skeleton parser needs `all_goals exact (by sorry)`, not `all_goals sorry` (tool hole rewriting mistakes latter for term syntax).

# Continuation run (no improvement banked)
- [tested: no arrows on congruence constructors ->63tok/9885hb FAIL app; no arrows on all hints ->55tok/15548hb FAIL app; no arrows on Red.inl/inr ->68tok/7277hb FAIL inl]. Beta-no-arrows already checked in earlier run, compiles but no improvement.
- [tested: `subst Γ` -> FAIL (induction rebinds environment as Γ✝); `cases eq` already checked earlier].
- [tested: `-Typing.sub`, `-Typing.app` -> grind reports not marked attribute, despite source having `[grind .]`]. `-Sub.trans` compiles73tok/5632hb but loses token tradeoff. `-wf` fails app.
- [tested: combining all_goals with `<;>` ->70tok/5665hb; `-mbtc`, `-clean` ->72tok/5665hb].
- [tested: anonymous generalize already checked earlier FAIL; `generalize _ : ...` invalid parser].
- [tested: beta-first hint ordering ->70tok/5664hb; all-canon-first, reverse-hints, congruence-first were cache hits from earlier runs]. Hint reorder seems to leave essentially identical heartbeat counts for these permutations.
- lean_profile returns no per-block heartbeat information for current proof, total5664. Current original best70tok/5663hb retained unchanged.
