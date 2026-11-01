# substOldPostSubset
Best checked proof in candidate.lean: 30 tokens, 1551 heartbeats, score 86.81, compatible v4.26.0.
Architecture: `dsimp [Imperative.HasVarsPure.getVars]`; `intro x`; `fun_induction substOld h2 (Lambda.LExpr.fvar m h1 ty) post`; `simp only [Lambda.LExpr.LExpr.getVars, List.mem_append] at *`; all goals `grind only`.
Fun induction handles the special old-application match and if automatically, unlike syntax induction. Introducing the membership variable before induction specializes IHs and saves ~470 hb. Reducing the HasVarsPure projection before induction saves ~147 hb. `grind only` can handle nil/singleton membership without explicit simp lemmas; dropping these gave another ~100 hb and 4 tokens.
Tried structural induction (explicit app splits), full simp, simp_all only, dsimp getVars + grind membership hints, cheap explicit False.elim/Or.inl/Or.inr/assumption passes: all worse. `aesop`, `tauto`, `intuition` unavailable. `unfold HasVarsPure.getVars` or bare `dsimp` don't reduce the instance projection fully, fail without later projection simplification. `dsimp [HasVarsPure.getVars]` is necessary.
Further potential optimizations are small: replacing grind with case-specific propositional terms probably increases tokens more than hb saved. No sorry or auxiliary declarations used.
Final additional checks: a fresh structural pointwise rewrite with grind handling the match compiled but cost 2507 hb/34 tokens; explicit shared splits cost 2186 hb/51 tokens. Simplifying List.Subset up front, introducing both x and hx, and simp_all only also lost. Current candidate remains the banked 30-token proof.

## Run 3 improvements
Best now candidate.lean: 33 tokens, 1176 heartbeats, score 88.91 (v4.26.0).
- `fun_induction substOld` automatically finds all arguments in the goal! Replaces `fun_induction substOld h2 (Lambda.LExpr.fvar m h1 ty) post`, saving 8 tokens and 5 hb. Short baseline is 22 tokens, 1546 hb.
- Before the shared simp, `any_goals with_reducible exact List.mem_append_left _` closes unchanged constructor cases without simplifying. Crucially `with_reducible` makes failures cheap: without it 2010 hb, with it 1289 hb (27 tokens).
- Before shared simp, `case case7 => exact List.mem_append_right _` closes replacement branch, saving 113 hb at cost 6 tokens; modest score improvement to 88.91.
- `with_reducible` right-membership prepass fails on ALL goals (getVars of fvar not reducible). Targeted case7 at default transparency works.
Tried: direct `induction post using substOld.induct h2` does not handle old-app cases as efficiently (even simp_all leaves un-reduced getVars and default app match). grind flags (-linarith, -mbtc, splits:=0) add ~516 hb, not improvements. omega cannot prove pure propositional goals. solve_by_elim [Or.elim, Or.inl, Or.inr] reaches heartbeat limit. simp configs -zetaDelta/-dsimp/-zeta all worse. Simp_all contextual much worse. Dropping up-front dsimp and adding HasVarsPure.getVars to shared simp saves 2 tokens but costs 83 hb (loses). any_goals assumption after simp saves 27 hb at cost 2 tokens (loses). dsimp only projection saves 1 hb at cost 1 token. No further promising cheap passes found.

## Run 4
Best improved slightly: 37 tokens, 1089 heartbeats, score 89.04. Added `case case5 => assumption` before shared simp to discharge abs by definitional reduction. This saves 87 hb at cost 4 tokens. A general `any_goals with_reducible assumption` fails; default-transparency targeted assumption works.
Tested fresh negative-membership architecture: `by_cases hx : x ∈ [h1]`, positive by append_right, negative fun_induction + simp [getVars,mem_append,hx,or_false,false_implies], then `repeat' first | assumption | apply Or.imp`. Compiles 54 tokens/1221 hb; solve_by_elim [Or.imp] 51/1383. Not competitive. Cases inside by_cases have names `neg.case7` rather than `case7`. lean_skeleton's `all_goals sorry` nesting transformation failed, lean_run with trace_state works.
Other polish tests: dsimp only instead of dsimp saves only 1 hb for +1 token. Separating getVars and mem_append simp passes costs +4 tokens/+51 hb; dsimp getVars then simp mem costs +4/+31. Grind only [getVars,mem_append] without simp compiles 32 tokens/1675 hb. Simp on goal only + grind [mem_append] compiles 38/1546. Explicit [h1] rather than `_` in append_left adds 2 tokens and 83 hb.

## Run 6 (2026-10-08)
Best improved to score 89.88, 38 tokens / 943 hb, v4.26.0 compatible; candidate.lean banked.
Architecture unchanged, but drop `case case5 => assumption`: simplifying this case then assumption costs only 42 hb for 4 saved tokens. Crucial: run the final repeated closer under `with_reducible` (saves 64 hb in failed assumption attempts). Group shared simp and closer under one all_goals. Finally move `with_reducible` outside the prepass and shared all_goals, drop targeted case7; shared closer tries `exact Or.inr` after assumption, handling replacement branch after simp. This saves 4 tokens for +62 hb versus 42-token/881 hb version.
42-token/881 hb alternative: inside outer with_reducible, after prepass use `case case7 => with_unfolding_all exact List.mem_append_right _`, then shared simp and `repeat' first | assumption | refine or_or_distrib_right.mpr ∘ Or.imp ?_ ?_` (no exact Or.inr). Score89.85, nearly tied.
Rejected: repeat refine before assumption (1574hb), reverse refine/assumption (1428hb), distribution in simp loops, List.mem_append-only simp fails to expose constructors, explicit [h1] in left prepass adds84hb, separate dsimp getVars + simp append adds126hb. `with_reducible` cannot surround `intro x`: List.Subset is not reducible there.
Fresh rewrite: split x=h1 before induction; positive simp, negative `simp [hx]` removes target append; fun_induction, reducible id prepass, shared simp getVars/mem_append/mem_singleton/hx; repeat assumption/False.elim/Or.imp. Compiles 54tokens859hb, worse. So conditional invariant isn't worth tokens.
Tool lean_skeleton bug: `all_goals sorry` gets misinstrumented as a term; use `all_goals exact (by sorry)` to inspect skeleton.
Additional rewrite after finish requested more exploration: defer x introduction until after fun_induction, use List.subset_append_left/right. Reducible prepass fails because `.Subset` is not reducible. Default prepass plus shared simp List.Subset/getVars/mem_append + grind compiles 38tokens2532hb. A specialized apply_assumption closer stack-overflows. No new library leads from lean_search. `exact` instead of final `refine` does not expose holes, fails; `refine Or.inr` ties exact.

## Run 7 (current)
Best improved to **37 tokens, 922 heartbeats, score 90.12**, candidate.lean banked.
Single paying refinement: change the reducible prepass from `any_goals exact List.mem_append_left _` to `any_goals apply List.mem_append_left`. `apply` can infer the explicit list argument while matching the implication goal (no `_` needed). Intermediate `apply ... _` was 38 tokens/929 hb vs original 38/943.
Current full body:
```
  dsimp [Imperative.HasVarsPure.getVars]
  intro x
  fun_induction substOld
  with_reducible
    any_goals apply List.mem_append_left
    all_goals
      simp only [Lambda.LExpr.LExpr.getVars, List.mem_append] at *
      repeat' first | assumption | exact Or.inr | refine or_or_distrib_right.mpr ∘ Or.imp ?_ ?_
```
Measured unsuccessful alternatives: initial `simp only [HasVarsPure.getVars]` 39/945; `dsimp only` 39/942; intro before dsimp 38/969; unprimed repeat 38/956; restricting with_reducible to prepass 38/1021; no prepass + Or.inl closer 37/1088; Or.inr before assumption 38/977. `apply_rules [Or.inr, fun f g => or_or_distrib_right.mpr ∘ Or.imp f g]` compiles 38/1285 but loses. `solve_by_elim only` same rules fails; applying bare `or_or_distrib_right.mpr ∘ Or.imp` fails, needs explicit metavariables for f/g. Profile returned no per-line cost data, total 943 for original inherited candidate.
Further run-7 improvements: final **36 tokens / 919 hb / score 90.25**. `or_or_distrib_right.2` costs 3 fewer hb than `.mpr`, same tokens. Crucially use **`intro` with no identifier**, saving one token because the variable is not referenced syntactically later.
Additional architectures checked:
- subset-level local `merge` lemma for append preserving a shared tail compiles 91 tokens / 1527 hb; local helper's signature too long.
- case split on membership variable equaling h1 strengthens induction goal to no-new-variable implication. Compressed form `by_cases hx : x = h1 <;> simp [hx]`, then fun induction, `simp only [getVars, List.mem_append, List.mem_singleton, hx, false_implies, imp_self] at *`, repeat assumption/Or.imp compiles **45/1130**, loses.
- Short grind fallback with `with_reducible` and `apply List.mem_append_left` prepass: 24/1265. Additional assumption/Or.inr prepasses lose by tokens. Adding or_imp or or_assoc to simp loses; adding `or_or_distrib_right` to simp loops (duplication!), don't do it.
- `solve_by_elim [Or.inr, fun f g => or_or_distrib_right.2 ∘ Or.imp f g]` compiles 36/1268, loses. The `only` version fails because it excludes local IHs.
- default transparency with apply prepass:35/1353; `with_reducible_and_instances`:36/947; `with_unfolding_all`:36/1349.
- Abs targeted preclose adds4 tokens saves46hb; replacement targeted preclose adds6 saves53hb: both lose.

## Run 8
Current best improves 36 tokens / 919 hb to 36 tokens / 914 hb, score 90.28: replace `exact Or.inr` with `apply Or.inr` in the shared `repeat' first` closer. All other structure unchanged. Compatible v4.26.0.
Checked batch alternatives: `exact List.mem_append_left _` prepass 37/939; removing reducible for simp/closer 36/997; placing Or.inr before assumption 36/953; placing composite refine before Or.inr 36/947; `.mpr` instead of `.2` 36/918; upfront `dsimp only` 37/913 (not worth extra token); adding List.Subset to dsimp 38/919; `simp -implicitDefEqProofs` 38/1107. `apply or_or_distrib_right.2 ∘ Or.imp` fails (composition cannot infer partial function application); `apply_rules [Or.inr, or_or_distrib_right.2 ∘ Or.imp]` fails for same reason. No Function.trans lemma. lean_profile returned null per-block costs. The composite refine with two placeholders remains needed.

## Run 9
No improvement over the banked 36 tokens / 914 hb. Checked 9 variants: `apply or_or_distrib_right.2 ∘ Or.imp ?_ ?_` ties `refine` exactly (36/914); reversing simp lemma order ties; rintro x adds one token with identical hb. `apply_assumption` in repeated closer stack-overflows; `exact ‹_›` cannot infer the local IH reliably. Separating distribution and Or.imp fails because apply Or.imp greedily maps to the wrong disjunction; the composition is important for constraining intermediates. Point-free composition cannot be rewritten using `(Or.imp ?_ ?_ ·)` (unresolved implicits). lean_profile still returns null for per-block heartbeat data. Keep current candidate unchanged.

## Run 10 (preserved existing 36-token / 914-hb best)
Current candidate remains the supplied best, using `with_reducible` around both prepass and simp/closer, `apply List.mem_append_left`, and `refine or_or_distrib_right.2 ∘ Or.imp ?_ ?_`.
No improvement across 12 fresh checked variants:
- Moving `with_reducible` to prepass only: 36 tokens / 990 hb.
- `exact List.mem_append_left _` prepass: 37 / 934.
- Initial `simp only` instead of `dsimp`: 37 / 915.
- Putting `apply Or.inr` before `assumption` in closer: 36 / 935.
- `change (Lambda.LExpr.LExpr.getVars _).Subset _` fails: RHS stays projected and prepass fails.
- Adding `or_or_distrib_right` to simp loops (lemma duplicates shared right disjunct, so simp recursively rewrites its own output). Repeated `rw` likewise times out.
- `refine ... Or.imp ..` fills THREE arguments, so yields disjunction rather than function; fails. `apply ... ∘ Or.imp` cannot synthesize partial application. `( ... ∘ Or.imp · ·)` yields a lambda and does not generate tactic goals. Keep the two explicit holes.
- `exact ... Or.imp ‹_› ‹_›` solves binary cases but not ternary ite; nested version loses binary cases, larger regardless.
`lean_profile` returned total 914 but no per-block costs on this toolchain.
Additional run-10 architectures after initial finish was rejected for budget:
- Contradiction induction (`intro x hx; apply Classical.byContradiction; intro h; fun_induction substOld; simp only [getVars, List.mem_append] at *; grind only`): 26 tokens / 1755 hb. `by_contra` tactic is unavailable, as is lemma `not_imp_not`. simp_all-only version 24 / 3546. IHs acquire both positive membership and negative RHS premises, explaining cost.
- Subset-level functional induction without upfront membership intro: `any_goals apply List.subset_append_left` at default transparency, then simp getVars and grind [List.Subset,List.mem_append]: 25 / 3358. At reducible transparency that prepass fails on ALL goals because the lemma concludes typeclass `⊆` and `List.instHasSubset` cannot reduce there. Explicit args cost 27 / 3852. This is a genuine different architecture but not competitive.
- Abs prepass `case case5 => assumption`: 40 / 868, insufficient hb saved for 4 added tokens. Replacement prepass `case case7 => apply List.mem_append_right`: 41 / 855, likewise not enough.
- Intro before initial dsimp: 36 / 937. Combined tactical chain `fun_induction ... <;> with_reducible first | ... | ...`: 38 / 921.
- Eagerly solving right IH (`Or.imp ?_ ‹_›`): 38 / 922. `(by assumption)` costs 39 / 920. No gain.
- `refine Or.inr` instead of apply: 36 / 918. `refine List.mem_append_left _`: 37 / 934. `exact Or.inr` already checked in earlier runs, no gain.
Restored candidate.lean to 36 / 914 best. No new score improvement this run.

## Run 11
Preserved 36 tokens / 914 hb best. New checked variations:
- `refine ... Or.imp _ _` and `exact ... Or.imp ?_ ?_` do not expose pending metavariables as tactic goals, unlike refine with explicit holes; fail binary and ternary cases.
- `refine Or.inr ?_` commits the shared first closer at the wrong shape in composite cases and fails; plain `apply Or.inr` remains necessary.
- Reverse distribution `← or_or_distrib_right` in simp does not normalize the needed goal: lemma's forward direction expands, reverse direction contracts already-duplicated formulas. Forward version was already known to loop. Separate `simp only [← or_or_distrib_right]` also fails the no-progress check in abstraction case.
- apply_rules inline composite closer compiles 36 tokens / 1267 hb, loses.
Profile again supplies only total 914, null per-block data. Many seemingly new minor edits are deduplicated against the 200+ historical attempts, so avoid rechecking dsimp-only, initial simp-only, change-lambda, exact prepass, or mpr/2 variations.
Run-11 additional rewrites after early finish rejected by budget guard:
- Conjunctive implication architecture: adding `or_imp` to shared simplification then `simp_all only` + grind costs 24/2467. Recursive `And.intro`/Or.imp_left composition does not constrain intermediates enough; fails. Original fused Or.imp/distribution remains superior.
- Exclude fresh-variable membership first (`by_cases h : x ∈ [h1]` then simp) gives pure Or.imp induction, but costs 48/1234 (full simp first) or 55/1211 (simp-only first); loses.
- Prepass `solve_by_elim [List.mem_append_left]`: 38/2797. Default-transparency assumption after append prepass: 39/1157.
- Shared simp `-dsimp`: 38/1028, `-zetaDelta`: 38/1107; initial dsimp `-zeta`: 38/935.
- Fresh direct recursor architecture `induction post using substOld.induct h2`: full `simp_all [substOld,getVars,List.mem_append]` then all_goals grind only compiles 23/4418. simp-only needs Bool.false_eq_true/if_false/if_true and getVars grind hint, gives 33/3390. Direct recursor does not substitute result equations as fun_induction does, so simplifies all repeated substOld calls and is costlier. Note use separate `all_goals` for grind because some cases close completely in simp.
No improvement; candidate.lean still 36/914 best.

## Run 12
Preserved banked 36 tokens / 914 hb best. Profile still gives no per-line costs. Fresh checked variations:
- `simp +contextual only [getVars,mem_append] at *; grind only`: 26 tokens / 1751 hb.
- `first | assumption | grind only` after normal shared simp: 28 / 1240 (not enough heartbeat saving versus small grind baseline).
- Combining assumption/right injection as `solve_by_elim [Or.inr]` inside the repeated closer: 36 / 1929.
- Explicit projection-and-instance unfold: `unfold Imperative.HasVarsPure.getVars Core.instHasVarsPureExpressionExpr` compiles 35 / 1044; `delta` instead 35 / 1042. One token saved but ~130 hb lost, so reject.
- A direct Or.elim/Or.imp_left composition did not sufficiently constrain intermediate types; failed.
Confirmed actual instance name via #synth: `Core.instHasVarsPureExpressionExpr`. Generic `#synth Imperative.HasVarsPure Expression` is incomplete (needs Expression.Expr argument).
No score improvement. candidate.lean remains the supplied 36/914 best.
