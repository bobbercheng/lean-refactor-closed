# Core.InitsUpdatesComm
Best checked candidate: 64 tokens / 180 heartbeats / score 89.08; all three toolchains compile.
Architecture: eliminate final store via `cases UpdateStatesUpdated hu ▸ InitStatesUpdated hi`; repeat constructor chooses functional intermediate store. Apply updatedStatesInit and rotate_left to defer its length premise; discharge undefined by UpdateStatesNotDefMonotone' and nodup by InitStatesNodup. Unfold updatedStates, rewrite [updatedStatesComm], apply updatedStatesUpdate, rotate_left to defer length, defined monotonicity via updatedStatesDefMonotone + UpdateStatesDefined'. Shared all_goals simp [List.unzip_zip, UpdateStatesLength hu, InitStatesLength hi] closes lengths and reduces commutation premise to ks.Disjoint ks'. Contradiction by `cases InitStatesNotDefined hi k hk' ▸ UpdateStatesDefined hu k hk`.
Important: rewrite instead of rw saves ~45 HB. Parentheses around transport operands unnecessary. apply closers saved 1 HB vs exact. rotate_left works; swap is unknown tactic in this environment.
Failed: cases length equalities (dependent elimination fails); combined length equality transport invalid (independent types). simp without List.unzip_zip rewrites to map fst zip and fails membership typing. simp only works but +1 token with negligible HB improvement. Inline functional lemma applications give no token improvement. No inductive proof needed.
Further checks: a fresh automation architecture using solve_by_elim for init/update branches fails (unification/search), while grind can close init but update solve_by_elim still fails; all-grind disjoint with unzip incurs ~19k HB and fails. Post-simp `grind [List.Disjoint, isDefined, isNotDefined, → InitStatesNotDefined, → UpdateStatesDefined]` compiles but is 64 tokens/333 HB, inferior to transport contradiction. simp_all alone does NOT cover all length goals. `apply updatedStatesUpdate _` instead of apply+rotate_left is equivalent, 64 tokens/180 HB. Init placeholder requires an extra rotation and costs +1 token. Profile total180 floor33; no significant worthwhile heartbeat opportunities. Best candidate remains banked.

## Further continuation
- Tested explicit length arguments for both init/update: compiles 69 tokens / 155 HB, inferior to 64/180.
- Hoisting both length equalities then `all_goals simp only [List.unzip_zip, *]`: 69 tokens / 176 HB, inferior.
- Combining not-defined and defined apply chains: 64 tokens / 180 HB, no gain.
- `apply updatedStatesInit _` leaves the length goal first (unfold subsequently fails); unlike update placeholder, needs rotate.
- `apply_rules` init with updatedStatesInit, UpdateStatesNotDefMonotone', InitStatesNotDefined, InitStatesNodup fails with unconstrained store metavariable; update analogue fails too. Not a viable shortcut.
- Definitions: isDefined σ ks = ∀ k ∈ ks, (σ k).isSome = true; isNotDefined σ ks = ∀ k ∈ ks, σ k = none. Existing transport/cases contradiction remains economical.
Best banked proof unchanged: 64 tokens / 180 HB, all three toolchains.

## Continuation run: injection improvement
- Best now 64 tokens / 173 heartbeats / score 89.14: change final `cases InitStatesNotDefined hi k hk' ▸ UpdateStatesDefined hu k hk` to `injection` with the identical expression. Banked in candidate.lean.
- Explicit nodup argument to updatedStatesInit costs +3 tokens; without rotate fails on length goal.
- Hoist both lengths and use simp_all only: 68/184; simp only [List.unzip_zip,*]: 70/157; defer lengths then all_goals simp_all only: 67/228. Inferior.
- Fresh simp-based initialization works with updatedStatesInit plus its three facts, but simp-based update after unfolding fails to match the folded conclusion. No benefit.
- exact nomatch contradiction:65/185, inferior. delta updatedStates, reversed simp fact order, and apply updatedStatesUpdate _ each remain64/173 with injection.
- exact for three terminal apply steps:64/175. simp only final:65/172, inferior.
- Fresh term-transport rewrite: two length facts, explicit Disjoint proof, explicit functional commutation equality and `(UpdateStatesUpdated hu ▸ InitStatesUpdated hi).trans hc ▸ updatedStatesUpdate ...` compiles, but 117/197, inferior; returns to banked tactic proof.
- Instantiated `grind [InitStatesNotDefined hi, UpdateStatesDefined hu]` alone fails because grind does not unfold List.Disjoint/isDefined/isNotDefined. Including all three defs succeeds64/315; omitting either state predicate def fails. aesop is unavailable (unknown tactic).
- with_reducible apply updatedStatesUpdate fails on folded updatedStates; with_reducible repeat constructor65/173 inferior.
- Profile injection best:173 total,33 floor; large apparent81-HB block at second rotate_left includes later closure elaboration. Explicit update length67/161; hoisting it as this67/160, both inferior. No useful further length cuts found. Final candidate restored from best.lean (64/173).

## Continuation run
Best remains banked 64 tokens / 173 HB (injection closer).
- `apply updatedStatesInit _` queues undefined, nodup, length, then update; rotation before undefined fails (nodup goal), rotation after nodup is required. No shortening.
- Fully applied update `apply updatedStatesUpdate _ $ updatedStatesDefMonotone $ UpdateStatesDefined' hu` works, 64 tokens / 174 HB; no gain.
- `with_reducible rewrite [updatedStatesComm]` does not unfold `updatedStates` for rewrite matching; explicit unfold necessary.
- Explicit `Bool.noConfusion $ ...` compiles 66 tokens / 177 HB, inferior to injection.
- Fresh disjoint-first architecture checked via skeleton then completed: 91 tokens / 152 HB, far worse length. Transport-based current architecture is better.
- Combining monotonicity application chains is 64 tokens / 180 HB, no gain.
Additional checked outcomes:
- `simp_all` is single-goal, so replacing `all_goals simp` leaves two length goals unsolved; `simp_all only` does too.
- Deferring semantic obligations (isNotDefined, Nodup, isDefined) to shared simp: 66 tokens / 241 HB, inferior.
- `simp_all [List.Disjoint, InitStatesNotDefined hi, UpdateStatesDefined hu]` cannot establish disjointness without introducing a key and membership assumptions.
- `List.map_fst_zip` instead of `List.unzip_zip` compiles 64 tokens / 188 HB, inferior.
- Profile: total173, floor33; only ~1.09 heartbeat-score points available. Transport costs25, constructors9, rewrite7. Profile attributes final deferred simp cost to rotate_left (~81HB).
Final fresh rewrite: explicit transported update via `(updatedStatesComm ?_).symm ▸ updatedStatesUpdate ...` compiled from a checked skeleton. Fully term version 88 tokens / 168 HB; retaining automatic init/deferred lengths gives 68 tokens / 182 HB. Both inferior. Best remains initial 64-token / 173-HB candidate unchanged.
