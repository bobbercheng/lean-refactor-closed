## InitsUpdatesComm rewrite
Best checked proof in candidate.lean: 87 tokens, 271 heartbeats, score 84.95; compatible with all three toolchains.
Architecture avoids induction entirely:
- hn := UpdateStatesNotDefMonotone' (InitStatesNotDefined hi) hu
- initial InitStates via updatedStatesInit (InitStatesLength hi) hn (InitStatesNodup hi)
- rewrite final store via InitStatesUpdated hi and UpdateStatesUpdated hu
- unfold updatedStates; rw [updatedStatesComm]
- update constructor lemma updatedStatesUpdate (UpdateStatesLength hu) (updatedStatesDefMonotone (UpdateStatesDefined' hu))
- disjointness follows from original defined keys vs original undefined initialization keys. Simplify zipped unzips using length facts; intro x hx hx'; simpa [hn x hx'] using hk x hx.
Explicit disjointness proof saves ~220 hb versus grind. simp_all alone cannot close universal disjointness; grind [List.Disjoint,isDefined,isNotDefined] works but is slightly lower score.
Shared have for UpdateStatesLength hu saves 1 token. `simp [List.unzip_zip, hu', hl]` vs explicit simp only list saves 1 token for 17 hb (barely pays). All previous compilations banked by harness.
Final polish improved best to **83 tokens, 308 heartbeats, score 85.26** (all toolchains). Zip simplification is now `simp_all [List.unzip_zip]`, using the shared length hypotheses automatically. `simp_all only [List.unzip_zip]` also works: 84 tokens, 298 hb, score 85.19. `simp only [List.unzip_zip, *]` works but scores less.
Tried fresh comm-first architecture (110 tokens, 208 hb), explicit Option.isSome_iff_ne_none.mp contradiction (89 tokens, 276 hb), and broad grind closures. None improved. Broad grind cannot assemble the update-after-commutation chain even with many hints (and can cost 26k hb); explicit rewrite is preferable. `use` is unavailable in this project's tactic environment; `exists _, rfl, initProof` works but costs ~174 extra hb versus refine. Direct simplification of disjointness fails even after intros; specializing via `simpa [hn x hx'] using hk x hx` is key.

## Current run polish
Best now **81 tokens, 270 heartbeats, score 85.85**; candidate.lean banked and compatible across all requested toolchains.
- Combining `rw [InitStatesUpdated hi, UpdateStatesUpdated hu]; unfold updatedStates` into `simp [InitStatesUpdated hi, UpdateStatesUpdated hu, updatedStates]` saved 39 hb at same token count (83/269 before anonymous facts).
- Anonymous `have := InitStatesLength hi` immediately before refine, then anonymous `have := UpdateStatesLength hu` afterward, saves two tokens. Old `this` remains visible to simp_all after shadowing.
- [tested] `simp_all [List.unzip_zip, isDefined, isNotDefined]` cannot close disjointness; even after intros expanded simp_all alone fails.
- [tested] grind tail with the three definitions compiles (77 tokens/520 hb on the 83-token architecture) but does not pay. `grind only` with those definitions fails: it needs further Option simp facts. `simp_rw` tactic is unavailable.
- [tested] replacing `simpa [hn x hx'] using hk x hx` by `have := hk x hx; simp_all [hn x hx']` compiles but costs one more token and 26 hb.

## Latest continuation
Best checked now **79 tokens, 271 heartbeats, score 86.14**. Single improvement: final `exact nomatch hn x hx' ▸ hk x hx` → `cases hn x hx' ▸ hk x hx`. Banked in candidate.lean.
Tested alternatives on this architecture: `simp only` for store rewrites 81/277; lambda final disjoint proof 81/279; `simpa only [List.unzip_zip, *] using fun ... => nomatch ...` 84/245; `simp [List.unzip_zip, *]` at disjointness 81/235; `simp_all only [List.unzip_zip]` 80/262; `rw` store equalities then `dsimp [updatedStates]` 81/314. None improves the 79/271 candidate. Profile tool returned null individual block costs, total 278 for preceding seed.

## Follow-up run
Kept banked **79 tokens / 271 heartbeats** (score 86.14), no improvement found.
[tested: simp only instead of simp for store rewrite -> 80 tokens / 271 hb, no gain.]
[tested: convert tactic architecture -> unknown tactic in this environment.]
[tested: direct `(updatedStatesComm ?_).symm ▸ updatedStatesUpdate ...` -> fails motive inference; need explicit store instantiation, unlikely shorter.]
[tested: simp_all +contextual [List.unzip_zip,List.Disjoint,isDefined,isNotDefined] -> fails universal disjointness, 595 hb.]
[tested: simp_all zip then grind [isDefined,isNotDefined] without List.Disjoint -> fails, 446 hb; List.Disjoint must be supplied for this closure.]
lean_profile returned no block costs (all null), total 271. Current best still candidate.lean unchanged.
Additional tested fresh comm-first architecture: 105 tokens/248 hb; no gain. simp conditional comm with grind discharger fails to commute (permutation orientation) and costs 2205 hb. `exists` saves four tokens (75) but costs 441 hb; its core macro adds `try trivial`, explaining the overhead. Explicit witness and with_reducible did not help. `nomatch` instead of `cases` is 79/278 (slightly worse). `rw` and `erw` with only InitStatesUpdated,UpdateStatesUpdated,updatedStatesComm both FAIL: head matcher does not unfold updatedStates. Explicit repeated unfolding costs more, not less. Final verification confirms unchanged 79/271 banked best.

## Run 6 result
New best **76 tokens / 289 heartbeats / score 86.45**, all three toolchains. Banked in candidate.lean (also v3.lean).
Paying edits:
- Replace `simp [InitStatesUpdated hi, UpdateStatesUpdated hu, updatedStates]` with `cases InitStatesUpdated hi; cases UpdateStatesUpdated hu; unfold updatedStates`. Saves 2 tokens for ~20 hb.
- Inline the two uses of `UpdateStatesDefined' hu` and delete `have hk := ...`. Saves another token and 2 hb on this architecture.
Tested: `simp_all only [List.unzip_zip]` after these cases costs one extra token and saves only 9hb; `simp only [List.unzip_zip, *]` costs 3 extra tokens and saves 40hb, neither pays.
Tested: `erw [updatedStatesComm]` without unfolding fails to match, as does `rw [updatedStatesComm (σ := σ)]`. `delta updatedStates` equals unfold in cost.
Tested: `convert` tactic is unavailable in this environment. Direct `(updatedStatesComm ?_).symm ▸ updatedStatesUpdate ...` cannot infer comm's arguments/motive. Eq.mpr variant also needs explicit store/zip arguments.
Tested `grind only` tails with isDefined/isNotDefined/Option.isSome_none fail without List.Disjoint (even after simp zip); the all-in-one variant with List.Disjoint still fails to forward UpdateStatesDefined'. Not promising versus 9-token explicit contradiction.
Fresh comm-first rewrite skeleton checked hole-by-hole and completed in fresh.lean: 124 tokens / 230 hb, worse than best. It proves hd on original key lists, a typed hc commuting updatedStates, then simpa using updatedStatesUpdate. Explicit ves on update is needed for type inference in `simpa using`. Candidate.lean remains 76-token best.

## Additional polish run (current best unchanged: 76 tokens / 289 hb)
[tested] `simp_all only [List.unzip_zip]` at disjointness: 77 tokens / 280 hb; `simp only [List.unzip_zip, *]`: 79 / 251; explicit `rw [List.unzip_zip h, List.unzip_zip hl]`: 82 / 277. None pays.
[tested] Moving the two `cases ...Updated` before the witness (or before hn), or reversing them: same 76 tokens, 292–293 hb; no improvement.
[tested] `exists _, rfl, updatedStatesInit ...` after early cases: 72 tokens / 475 hb. `with_reducible exists ...` at original position: 73 / 453. Lean's exists macro is `refine ⟨...⟩; try trivial`, explaining extra elaboration. Explicit refine remains best.
[tested] `dsimp [updatedStates]` instead of unfold: 78 / 294; combined `rw [updatedStates, updatedStates, updatedStatesComm]` needs erw repair and 455 hb. Keep unfold + rw.
No new best; candidate.lean retains the supplied 76-token proof, compatible across all three toolchains.

## Continuation run (current best remains 76 tokens / 289 hb)
Read full goal map: final disjointness is zip/unzip-key disjointness, simplified using the two anonymous length facts to ks.Disjoint ks'. Current final `cases hn x hx' ▸ UpdateStatesDefined' hu x hx` is economical.
[tested] Replacing `unfold updatedStates` with `simp only [updatedStates]` compiles at 79 tokens / 297 hb; no improvement.
[tested] Dropping length haves and trying `simp_all [List.unzip_zip, InitStatesLength, UpdateStatesLength]` fails: these conditional length lemmas do not simplify the zip in this form; final hx' remains membership in map fst zip.
[tested] `exact nomatch hn x hx' ▸ UpdateStatesDefined' hu x hx` compiles at 77 / 296; worse.
[tested] Replacing x arguments in final cases with `_` compiles at 76 / 290; no improvement.
[tested] `rw [updatedStates, updatedStates, updatedStatesComm]` needed repair to erw and measured 78 / 455; worse.
Existing prior variants `delta updatedStates`, `simp_all only [List.unzip_zip]`, and `simp only [List.unzip_zip, *]` were detected as already checked; none improves best.
Library probe: List.of_mem_zip exists with signature `(a,b) ∈ l₁.zip l₂ → a ∈ l₁ ∧ b ∈ l₂`; guessed mem_of_mem_zip_left/of_mem_zip_left/fst_mem_of_mem_zip/mem_unzip_left do not exist. Avoid spending turns on these names.

## Run 9 polish
New best: **76 tokens, 283 heartbeats, score 86.50**. Single change `have hn := ...` to `let hn := ...` saves 6 heartbeats on the current cases-based architecture. Banked candidate.lean.
Tested: combining store cases into rw is 78 tokens/307 hb; subst_vars architecture 82/284. `rw [updatedStatesComm]` without unfolding fails to match the updatedStates' pattern; erw variant was already cached as failing. delta, simp_all only, simp only [updatedStates], and nomatch variants had already been tested in previous runs (cache hits). No upstream exploration done.
Further improvement: **73 tokens, 283 heartbeats, score 86.94**. `$` is ONE token whereas `<|` is TWO in this scoring tokenizer. Replaced the nested parentheses in `updatedStatesUpdate this $ updatedStatesDefMonotone $ UpdateStatesDefined' hu`, plus tuple component `updatedStatesInit this hn $ InitStatesNodup hi`. All compile.
[tested] on new best: simp_all only saves 8 hb but adds 1 token (74/275), simp only [List.unzip_zip, *] gives 76/254; neither pays. delta updatedStates unchanged 73/283. Generalized dot notation `hi.InitStatesNotDefined` fails because the theorem is not in the inductive namespace. Grind only with Option.isSome and inline defined fact works but 77/432 before dollar edits, worse. Eq.mpr transport rewrite leaves the implicit zip list as a separate goal, so `congr 1` before filling it does not operate on the desired store equality.
Final checks: replacing the two cases + unfold by simp [InitStatesUpdated hi, UpdateStatesUpdated hu, updatedStates] gives 75 tokens/263 hb (does not pay). `clear hi` after the cases fails because let hn depends on hi. `rintro` vs intro identical 73/283.

## Run 10
New best **73 tokens / 271 heartbeats / score 87.04**, banked candidate.lean, all three toolchains compatible. Paying change: the SECOND anonymous length fact is now `let := UpdateStatesLength hu` instead of `have := ...` (saves 12 hb).
[tested] Changing the FIRST length fact to anonymous let fails: the later anonymous have/let does not make `this` refer to the update length as desired; updatedStatesUpdate sees the initialization length instead. Changing both to lets fails likewise.
[tested] Without unfolding, both rw and erw [updatedStatesComm] fail to match (71 tokens); rw [updatedStates, updatedStatesComm] only unfolds the initial-store occurrence and fails to find commutation. `nomatch` final contradiction is 73/289; simpa contradiction is 75/281, both worse. Delta, simp_all only, and have hn variants hit existing cache. Profile still yields null per-line costs.
Continuation after early finish rejected: fresh typed-comm transport rewrite compiled in fresh.lean at 111 tokens/249 hb. A shorter unfolded transport `refine (updatedStatesComm ?_).symm ▸ ?_` DOES infer the equality and motive after the two store cases and unfold, contrary to older broad notes. Completing the two holes separately is 79/235; inlining updatedStatesUpdate into that refinement is 76/234. Still worse than 73/271. Using `$` immediately after `updatedStatesUpdate this` in the transport expression fails due parser precedence (transport then applies to an arrow rather than relation proof).
[tested] `cases updatedStatesComm ?_` does not infer the commutation arguments from the goal and fails; simp only [updatedStatesComm ?_] makes no progress. `apply` instead of `exact` on updatedStatesUpdate compiles with identical 73/271. Best candidate.lean remains unchanged.

## Run 11
Retained supplied best, 73 tokens / 271 hb. No meaningful scoring improvement.
[tested] Moving both `cases` immediately after intro compiles at 73/271; swapping order to UpdateStatesUpdated then InitStatesUpdated gives 73/270. Moving second anonymous length let below both cases also 73/270. Tool did not bank these (score null, best_variant null), so candidate remains supplied best.
[tested] Restricted single grind tail with `[List.unzip_zip, List.Disjoint, isNotDefined, isDefined, Option.isSome, UpdateStatesDefined']` fails (71 tokens/591 hb); simplifying zips first then same grind also fails (73/463). Forward hints may be needed, but current explicit closure is cheaper.
[tested] `have := UpdateStatesDefined' hu x hx; simp_all [hn x hx']` compiles at 76/286, worse. `have := updatedStatesUpdate this $ updatedStatesDefMonotone $ UpdateStatesDefined' hu; rwa [updatedStatesComm]` fails because the initial store and initializing zip cannot be inferred at the have.
Existing cache: first length `let` fails; simp_all only 74/266, rw store equalities 75/289, simp only [List.unzip_zip,*] 76/255 all compile but do not improve score.
