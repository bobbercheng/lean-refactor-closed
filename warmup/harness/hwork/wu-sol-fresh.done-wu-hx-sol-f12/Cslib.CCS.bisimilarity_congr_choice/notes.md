# Cslib.CCS.bisimilarity_congr_choice — Scout C

Best banked proof: candidate.lean, 80 tokens, 460 heartbeats, score 85.42, compatible with all three toolchains. Original: 251 tokens / 3858 HB.

Architecture: initial point-free `refine (⟨_, ChoiceBisim.choice ·, ?_⟩)` (parentheses REQUIRED), `rintro _ _ (h | h) μ <;> constructor <;> intro s t`; case' choice.left | choice.right splits transition, shared right trivial cells, all remaining cells mapped by Exists.imp / And.imp / ChoiceBisim.bisim.

Important discoveries:
- `rintro ... ⟨h⟩ ...` binds h ONLY in first constructor; use `(h | h)` to bind in both.
- `case' choiceR` handles only first matching suffix; `case' choice.left.choiceR | choice.right.choiceR` handles both.
- `apply Exists.imp fun _ => And.imp ?_ ChoiceBisim.bisim` creates the source existential FIRST, plus a predicate metavariable goal and the mapper goal. Do NOT rotate_left here. `first | exact h.follow_fst t | exact h.follow_snd t` resolves source and predicate metas, then `first | exact id | exact Tr.choiceL` handles mapper.
- Qualified And.imp with explicit ?_ works; `.imp ?_ .bisim` produced unresolved placeholder / no-goals errors. Fully specified `.imp (by first | exact Tr.choiceL | exact id) .bisim` works but 82 tokens, no improvement.
- `apply Exists.imp` with no mapper specified DOES need rotate_left before source follows, but is longer (~90 tokens).
- Exact-list follow calls after constrained apply fail because predicate goals interleave source existentials. Earlier branch-separated complete mapper + exacts two calls works, 97 tokens /365 HB.
- `any_goals exact ⟨_, .choiceR t, ...⟩` leaks elaboration mismatch. Safe `any_goals (refine ⟨_, .choiceR ?_, .bisim (.refl _)⟩; assumption)` works but slower (615 HB) at same 80 tokens.

Profile best: floor37; point-free refine15; rintro+constructor+intro54; choice transition cases+rename169; shared right witnesses33; shared Exists map+two first calls152. Explicit using Tr.casesOn same HB; change Tr at t before cases adds tokens without savings.

API available: Bisimilarity.follow_fst / follow_snd / isBisimulation (lts1,lts2 explicit), HomBisimilarity.refl (state explicit), IsBisimulationUpTo.isBisimulation, IsBisimulation.le_bisimilarity. No of_matching / of_follow API. UpTo is closure by bisimilarity composition, not merely union, so probably too much overhead here.

Automation approaches tried: grind with generic/specialized follow hints, unfold lts, fixed defs in constructors, -Tr, splits:=0, and aesop forward follow + safe constructors all fail or are far slower. Grind matching needs unfold lts to invoke h.follow, but specialized forward follows then loop generating new witnesses. -Tr suppresses inductive splits but does not solve construction; splits:=0 also blocks existential witness elimination. Bare solve_by_elim on follows selects wrong orientation unless mapper fixes relation first. With fixed mapper it compiles but ~795HB. Generic whole-proof grind is not productive.

Tool quirk: lean_skeleton cannot process `all_goals sorry` (rewrites it to invalid tactic syntax); use `all_goals exact (by sorry)`.
