# Core.InitsUpdatesComm — current run

Best checked candidate: score 89.14, 63 proof tokens, 192 HB (reference 224/4251). candidate.lean holds it. Initial fresh rewrite checked at 107 tokens/311 HB; all recorded improving candidates compile on all three target toolchains.

## Architecture
No induction. Eliminate the output equalities using `cases UpdateStatesUpdated u ▸ InitStatesUpdated i`. Build the existential and conjunctions using `repeat constructor`. Rebuild initialization with updatedStatesInit and UpdateStatesNotDefMonotone'. Unfold updatedStates, commute the two zipped update lists using updatedStatesComm, and rebuild the update using updatedStatesUpdate plus updatedStatesDefMonotone and UpdateStatesDefined'.

## Goal ordering optimization
`apply updatedStatesInit` followed immediately by `rotate_left` moves its length goal to the very end, after the outer update goal. Solve not-defined and Nodup first. `apply updatedStatesUpdate` (without a placeholder) leaves length, definedness, disjointness. `any_goals simp [List.unzip_zip, UpdateStatesLength u, InitStatesLength i]` solves all length goals and reduces unzip/disjointness while tolerating the unchanged definedness goal. Then solve definedness and disjointness.

Disjointness closer: `intro x hx hy; cases InitStatesNotDefined i x hy ▸ UpdateStatesDefined u x hx`. Here the first lemma gives σ' x = none and the second gives (σ' x).isSome = true, yielding an impossible Bool equality.

## Existing lemmas
- UpdateStatesNotDefMonotone' : isNotDefined σ' hs → UpdateStates σ ks vs σ' → isNotDefined σ hs
- UpdateStatesDefined' : UpdateStates σ ks vs σ' → isDefined σ ks
- UpdateStatesDefined : same → isDefined σ' ks
- updatedStatesDefMonotone : isDefined σ hs → isDefined (updatedStates' σ kvs) hs
- updatedStatesInit : hs.length = vs.length → isNotDefined σ hs → hs.Nodup → InitStates σ hs vs (updatedStates σ hs vs)
- updatedStatesUpdate : hs.length = vs.length → isDefined σ hs → UpdateStates σ hs vs (updatedStates σ hs vs)
- updatedStatesComm : kvs.unzip.1.Disjoint kvs'.unzip.1 → updatedStates' (updatedStates' σ kvs) kvs' = updatedStates' (updatedStates' σ kvs') kvs
- InitStatesUpdated / UpdateStatesUpdated give the output-store equalities.

## Failed or inferior ideas
- `swap` tactic unavailable. rotate_left is available.
- Must unfold updatedStates before rewriting updatedStatesComm; `erw` does not match folded updatedStates either. `rw [updatedStates, updatedStatesComm]` unfolds only the first occurrence, still fails.
- `all_goals simp` and `all_goals simp_all` fail with "made no progress" on definedness. any_goals avoids this, with no extra try token.
- simp only adds a token and saves essentially no HB here (64/191 vs 63/192).
- solve_by_elim for the initialization branch using five lemmas fails after 1156 HB.
- Direct field notation i.InitStatesNodup / u.UpdateStatesDefined' unavailable (would need declarations inside namespace of the relation).
- grind disjointness without unfolding List.Disjoint fails; extra hints are not promising on score.
- exact instead of apply on three terminal lemma calls: 63/194 (slightly worse).
- repeat' constructor: 63/196 (worse).
- any_goals exact updatedStatesDefMonotone (...) before simplification: 65/207; dollar form 64/207.
- Earlier 64/180 proof uses apply updatedStatesUpdate _ and solves definedness before `all_goals simp`; 63/192 is marginally better.

## Profile of best
Total HB192, floor33. any_goals simp costs100; equality cases25; repeat constructor10; comm rewrite8; small applications remainder. 1 token ~19.2 HB, so further explicit simp term expansion is generally not worthwhile.
