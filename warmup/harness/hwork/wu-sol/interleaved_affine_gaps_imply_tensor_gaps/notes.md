# Notes (yours to keep; persisted across runs)

Continuation findings (current run):
- NEW BEST: 100 tokens / 1313 heartbeats / score 92.87, all three toolchains. Delete `unfold multilinearCombine_affineComb_split_last_close` in inductive probability bridge: `rwa [← prob_split_last_uniform_sampling_of_finFun]` alone closes by definitional reduction. Previous notes missed this.
- Profile total 1324, floor 694; base block 251, step block 343. Explicit arguments to CA_split_rowwise_implies_CA MC u e worsen to 1980 hb. Explicit Pr_le_Pr_of_implies _ _ _ costs four tokens and 4 hb.
- simp_rw in both simp-only locations: 100 tok /1442 hb, worse. Only recursive simp_rw: 101 tok/1347 hb, worse. Splitting base cast rewrites from simp: 106tok/1420hb, worse.
- Moving recursive simp after rw on goal using `simpa only [...] using hp` FAILS: the target retains multilinearCombine_affineComb_split_last_close; simpa using does not definally unfold target unlike `rwa` + assumption.
- Further tiny NEW BEST 100tok/1311hb, score 92.88: final subtype argument `⟨_, hr⟩` instead of `⟨r, hr⟩`. Saved to candidate by variant banking.
- A genuine induction-from-zero skeleton works: prove `have h : ∀ n, δ_ε_multilinearCorrelatedAgreement_Nat (F := F) (A := A) (ι := ι) (C := MC) n e ε`, then induction n. Step identical; base remains a one-row distance lifting. Both A and ι explicit are REQUIRED in have type to permit coercion of MC; absent them causes type errors/timeout. Abandoned because stronger have header costs >30 tokens and base needs proximity witness construction, not likely to beat current 100tok proof.
- Direct membership bridge: `classical; apply Pr_le_Pr_of_implies; intro r hr; apply ih; exact (Finset.mem_filter.mp hr).2` compiles 99tok/1391hb, worse. Without classical use `((@Finset.mem_filter ..).mp hr).2` compiles 103tok/1364hb, worse. Explicit @ and .. enable inferring the DecidablePred from hr (ordinary projection triggers premature instance synthesis).
- Final refine instead of apply: 100tok/1375hb; lambda exact closer 101tok/1436hb. Moving base simp after affine-gap apply: 100tok/1314hb. Explicit induction m:=1: 105tok/1302hb, worse score.

Continuation run 6:
- Baseline 100tok/1311hb retained. `letI : Nonempty F := Zero.instNonempty` checked 100tok/1310hb but score not banked; only marginal difference.
- [tested: with_reducible apply CA_split_rowwise_implies_CA -> compiles 101tok/1311hb, worse]
- [tested: with_reducible exact final correlatedAgreement helper -> 200k heartbeat timeout/type mismatch on WordStack coercion]
- [tested: with_reducible apply hC -> fails to unfold jointProximityNat₂]
- refine h_interleaved_gaps _ Nat.one_le_two_pow _ _ ?_: 103tok/1317hb.
- refine hC _ _ ?_: 103tok/1313hb.
- apply CA_split_rowwise_implies_CA _: 101tok/1329hb.
- Explicit `(↑MC)` to split helper fails due to unknown Set type parameters.
- rw recursive lemma at hp auto-repaired to simp_rw; repaired proof 99tok/1334hb, worse.
- convert base attempt requires `(↑MC)` with explicit type parameters for congrArg; MC cannot infer set coercion absent context.

Run 6 new architecture:
- Completed zero-induction rewrite in zero-rewrite.lean, 244tok/2651hb (worse). This is a real checked proof for all n including 0, avoiding hC entirely.
- Zero base: `have hm (r : Fin 0 → F) : multilinearCombine u r = u 0 := by ext i; simp [multilinearCombine, multilinearWeight]` works.
- To get proximity from >0 probability: simp only [hm, Nat.cast_zero, ENNReal.coe_zero, zero_mul, ENNReal.zero_div] at hp; by_contra h; rw [prob_uniform_eq_card_filter_div_card] at hp; simp [h] at hp.
- PMF.map_const/bind_const do NOT rewrite the functor map probability surface in this goal with simp.
- Lift one-row witness v: use closeToCode_iff_closeToCodeword_of_minDist both sides. Interleaved witness `fun i _ => v i`; membership `change ∀ k, v ∈ MC; exact fun _ => hv`; distance `simpa [hammingDist, Interleavable.interleave, interleaveWordStack, funext_iff] using hd`.
- convert base rewrite also completed convert-base.lean, 105tok/1403hb, worse. `convert hC (u 0) (u 1) ?_ using 1` equality goal is jointProximityNat ↑MC u = jointProximityNat₂ ↑MC (u 0) (u 1). `congr 1; apply List.ofFn_injective; rfl` closes. Exact `(List.ofFn_injective rfl).symm` fails premature elaboration.

Continuation run 7:
- NEW BEST: 100 tokens / 1303 heartbeats / 92.91, all three toolchains. Change transitivity to `refine lt_of_le_of_lt' ?_ (prob_R_star_gt_threshold MC u e ?_)` and put the membership-probability bound bullet FIRST, then the recursive sampling bullet. Candidate restored from ltprime.lean.
- `.trans_le` version compiles 100tok/1308hb, minor improvement over old baseline but worse than reversed transitivity.
- [tested: Nat.leRecOn hn with step before base -> 103tok/1314hb; works but worse]. Skeleton verified unchanged step/base goals.
- [tested: base equality transport `(show finMapTwoWords _ _ = u from List.ofFn_injective rfl) ▸ hC _ _ ?_` -> 102tok/1306hb; worse score].
- [tested: explicit F in either sampling rewrite -> 105tok/1297 or1298hb, worse]. Explicit predicate underscore -> 101tok/1310hb.
- [tested: refine CA_split_rowwise_implies_CA _ ?_ -> stuck DecidableEq metavariable; fails].
- On new reversed-transitivity candidate, letI and anonymous `intro n _ ih u hp` both unchanged 100tok/1303hb. Moving recursive simp immediately after intro gives1304hb; moving base simp after hC application gives1304hb. No further gain.
