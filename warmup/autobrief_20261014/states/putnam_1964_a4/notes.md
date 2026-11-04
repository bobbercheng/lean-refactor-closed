Best checked: p12.lean / candidate.lean, 161 tokens, 4201 hb, score95.71, all three toolchains compatible.
Architecture: finite windows as functions Fin4 → ℤ, contained in Set.pi univ (fun _ => Icc B T). Set.Finite.pi + Set.finite_Icc + Set.Finite.exists_lt_map_eq_of_forall_mem give i<j and window equality. Use congrFun heq ⟨m,hm⟩ for m<4. Strong induction propagates recurrence. Cast injectivity then simp (disch := omega) only [hu, Nat.add_sub_assoc, ih] closes all recurrence bookkeeping. Period j-i, final convert equality at offset n-i, congr 1 and omega.
Key elaboration: inline pigeonhole membership MUST be (by exact fun n k _ => hB _) instead of direct lambda, to defer elaboration until set t inferred. Dropping Fin4 type on Set.Finite.pi works when f is explicit lambda.
Pitfalls: full simp_all in base cases cost >20k hb; simp_all only [Nat.add_zero] avoids that but function windows avoid cases completely. Final bare grind (after have := h(n-i)) costs 224k hb because hu quantified recurrence is active; avoid. Nat.strong_induction_on is an eliminator, `apply Nat.strong_induction_on m` failed (expected type unavailable), use induction tactic or refine with hole. Best may be polished with refine Nat.strong_induction_on m ?_.
Tuple alternative v9: 251 tokens/7116 hb. Pi base pi_base: 220/3073. p1 (without redundant have hm)211/3074; p5 with simp hu183/4267. p9 inline f165/4200; p12 binder-style h m saves4 tokens.

Final improvement p15 / candidate:158 tokens,4218hb,score95.76,all toolchains. refine Nat.strong_induction_on m ?_ works, then intro m ih. Removing using 1 from final convert FAILS: default deeper congruence generates impossible equalities.

Run 3 improvements (checked all 3 toolchains): candidate.lean now 141 tokens, 4082 hb, score 96.12. Same finite-window/strong-induction architecture.
- `have h m : ... := Nat.strong_induction_on m fun m ih => by ...` saves 1 token vs refine+intro.
- Final `convert (h (n - i)).symm using 2 <;> omega` WORKS, saves 3 tokens vs using1 then congr1. [tested: using2 -> OK; default deeper convert previously failed].
- `Nat.sub_pos_of_lt hij` replaces `by omega`, same tokens and ~157hb saved.
- `apply @Int.cast_injective ℝ` saves 3 tokens vs `(α := ℝ)`, unchanged hb. [tested: omit ℝ entirely -> FAIL synth CharZero ?α].
- BIG elaboration improvement: eliminate `(f := ...)` from pigeonhole; membership proof `by exact fun n (k : Fin 4) _ => hB (n + k)` infers f and the index type. n needs NO type annotation. This saves 9 tokens vs former explicit f. `<| by exact ...` also compiles, same token count, 1 hb less.
- [tested: direct membership lambda without `by exact`, even with explicit Fin4 binder -> FAIL expected set metavariable]. The tactic boundary is useful; explicit named f is NOT necessary.
- [tested: `(by (repeat intro); apply hB)` works with former explicit f and saves1 token. Without parentheses, `repeat intro; apply hB` rolls back all introductions on failing apply -> FAIL]. Current inferred-f proof uses lambda instead.
- [tested: projecting hu first costs13 extra tokens and does not reduce hb].
- [tested: non-only simp costs7889hb vs4216; `simp +arith only` makes no progress].
- `convert!` unknown tactic in this context.
Best snapshots best5.lean (141/4083) and best6.lean (141/4082). candidate restored to best6, no holes.

Run 5 best: candidate.lean / run5_ifgele.lean, 142 tokens, 3016 hb, score96.42, compatible v4.27/26/25. Same finite-window architecture. Small improvements:
- [tested] Replace `=> by by_cases hm ...` with `=> if hm : m < 4 then congrFun ... else by apply ...; simp ...`: 141tokens/3142hb (run5_ifapply), saving1token/3hb over previous142/3145.
- [tested] Reverse conditional to `if hm : 4 ≤ m then by apply ...; simp ... else congrFun heq ⟨m, Nat.lt_of_not_ge hm⟩`:142tokens/3016hb, slightly better overall score. Explicit Nat.lt_of_not_ge saves73hb vs `by omega` here. No unverified claims about lower limits.
- [tested] simp without only:141/5377, worse. Nat.strongRecOn vs strong_induction_on: identical142/3145 on old architecture. Induction tactic:146/3135. Extracting hu.1 as local have:153/3164, worse. simp_all does NOT support disch option. Extra simp argument Nat.le_add_left unused.
- [tested] `Set.Finite.exists_lt_map_eq_of_forall_mem (by exact fun n (k : Fin 4) _ => hB (n+k)) <| Set.Finite.pi ...` works without named f; same token count,4hb more. `<| by exact ...` instead of parenthesized membership also identical cost.
- [tested] Term-mode if with fully explicit @Int.cast_injective and 4 underscores:146/3143; `else by apply @Int.cast_injective ℝ` is shorter.
- Lean profile tool returned null per-block costs on this proof; total3145 at old candidate only. No block-cost conclusions drawn.

Run5 FINAL rewrite (after finish was rejected with21turns remaining): candidate.lean / run5_clearhij.lean is now124tokens/4002hb, score96.47, all3toolchains. Significant new architecture: construct period witnesses FIRST, then strong-induct directly on actual n with invariant `n≥i → u(n+(j-i))=u n`. No separate h m lemma or final convert! Base n<i+4 uses `convert (congrFun heq ⟨n-i, by omega⟩).symm using 2 <;> dsimp <;> omega`. dsimp required: without it omega treats coercion of Fin.mk as opaque. Step n≥i+4 casts to ℝ and `simp (disch := omega) only [hu, Nat.sub_add_comm, ih]`. Important: FORWARD ih now best (reversed costs6023hb). Nat.sub_add_comm (k≤n): n+m-k=n-k+m is correct normalization here (NOT Nat.add_sub_assoc).
- [tested] Original direct architecture induction tactic127/4211, refine term in tuple122/4226; positive branch n≥i+4 first122/4203.
- [tested] Clearing hij ONLY in recurrence branch: adds2tokens but saves201hb =>124/4002 best. Clearing hB heq too126/3971 worse. Base still needs hij for index conversion.
- [tested] Explicit base bound `(Nat.sub_lt_iff_lt_add' hn).2 hm` on n<i+4 architecture:126/4069, loses to byomega.
- [tested] `convert ← congrFun heq ...` does NOT take symmetric proof: it reverses new equalities, so goal sides mismatch and fails. `convert!` unknown tactic in this environment. Ordinary simp without only costs5856hb.
Next potential check (not done): base `convert ... using 1 <;> congr 1 <;> omega` might reduce Fin.mk and replace dsimp, but no claim it works or pays. Current final proof is banked, no need to pursue.

Run 6: retained baseline 124 tokens / 4002hb / score96.47, candidate restored from baseline.lean. No improvement found.
[tested] Nat.strongRecOn in place of strong_induction_on:124/4003, inferior by 1hb.
[tested] base `with_reducible convert ... using 2 <;> omega` fails: omega treats Fin.val constructor as unrelated atom. `dsimp` still useful. `simpa +arith using ...` also fails (does not establish index shift).
[tested] typed Set.Finite.pi `(ι := Fin 4)` with direct membership lambda still fails expected-set inference. Membership tactic boundary works.
[tested] extracting hu first projection with `[fun n h => (hu n h).1,...]`:133/4005, no benefit. `rw [← Int.cast_inj (α := ℝ)]`:130/4013, worse than apply.
[tested] by_cases `4 ≤ n-i`:124/5243; `i+3<n`:124/4088; `¬n<i+4`:125/4035, all inferior.
NEW REWRITE completed windows-induction.lean: ordinary induction of four-element sliding windows, generalizing k; base congrFun heq, k<3 branch shift k+1; k=3 branch recurrence. Compiles228/5249, worse than baseline. Key pitfall: hu simp recursively expands previous values on j side if hij is in context; clear hij before simp prevents this. Normalize ih' using Nat.add_assoc before recurrence simp. This rewrite was outlined with skeleton and holes filled.

Run 9: new best candidate/use.lean, 127 tokens,2823hb,score96.76, all three toolchains compatible.
PAYING inference architecture: `have h := @Nat.strongRec _ fun m ih => if hm : m < 4 then by simpa using congrFun heq ⟨m,hm⟩ else by ...`. No explicit equality motive needed! `@Nat.strongRec _` bypasses elab_as_elim requirement for expected type. Crucially `simpa using` in base reduces Fin.val of constructor before motive unification; bare `congrFun` or `by exact` FAILS higher-order motive inference (hm appears in unreduced type). Remove parens around then-by branch. `simpa only` also works but costs extra token, saves only4hb. Existing recurrence and final convert unchanged.
PAYING: `use i, j-i, Nat.sub_pos_of_lt hij` works in place of refine triple with hole; saves4 tokens at cost23hb. `use` supports conjunction proof as a supplied witness.
Tested: direct membership lambda STILL FAILS even with Fin4 annotation on Set.Finite.pi binder, because theorem elaborates membership before dotted finite argument; retain `by exact` boundary.
Tested: unrestricted simp in recurrence works but costs5016hb vs2823, not worth1token. `convert congrFun...` in base infers wrong motive and fails. Clearing extra heq hB saves35hb for2tokens, not worth it. Nat.strongRec with explicit ∀ motive costs+1token and saves12hb vs original, not worth. StrongRecOn same cost as original.

Run 10: Best candidate now 124 tokens, 2890 hb, score 96.80, compatible all three toolchains. Only paying change from 127/2823 seed: replace `apply @Int.cast_injective ℝ` with tactic `rify` (3 tokens saved for 67 hb). candidate.lean updated to this proof.
Tested refinements: removing clear hij yields 122/4137 (worse); clear hij heq hB saves35 hb at cost2tokens (worse). Reversing ih no benefit. Base `simpa only using` saves3 hb but adds1token (worse). Base exact/apply/refine fail motive unification: Fin.val_mk must reduce before higher-order metavariable inference; raw term base also fails. Removing `by exact` in membership FAIL (expected-set metavariable); hB _ cannot infer index and FAIL. `Nat.strongRec` without @ _ FAIL expected type unavailable. `rify only` invalid syntax. `clear! hij` same hb and extra token. lean_profile returned null block costs, no actionable breakdown.
Run 10 continuation after finish budget rejection: new best 117 tokens / 2871hb / score96.94, all three toolchains checked. candidate.lean contains best.
Paying changes on top of rify: replace dependent if with `by by_cases hm : m < 4` and bullets (-1 token,+5hb); MOVE Fin4 annotation from membership lambda to `.pi fun _ : Fin 4 =>` (-2tokens,-20hb); membership `by intro n k _; exact hB (n+k)` saves4hb vs lambda, same tokens; anonymous `have := @Nat.strongRec ...` and final `this` saves1token; use heq.symm in base, then final `convert this (n-i) using 2 <;> omega` saves3tokens with no hb change.
Further tests: direct membership lambda still FAIL even with annotated pi. Plain simp instead of simp only adds2195hb for saving1token, worse. Pipeline `.exists ... <| .pi ...` compiles with same tokens and +5hb (no gain). simp_all does not support disch option (tested FAIL). push_cast cannot replace rify (tested FAIL).

Run 11: retained best 117 tokens / 2871hb / score96.94. No improving edit found; candidate unchanged.
[tested] Exact base (instead of simpa) still fails higher-order motive inference (Fin.val unreduced). `simpa only` works118/2867, no improvement. Reversing ih118/2872, no improvement.
[tested] Removing clear hij115/3185; reordering simp list to [ih,Nat.add_sub_assoc,hu] gives same115/3185 (worse score96.88). Explicit cast injectivity120/2804 is worse on score. Membership lambda with `by exact`117/2875 also worse.
[tested] Case m≤3 without modifying Fin proof fails bound mismatch; putting recurrence first (3<m) fails clear hij because the motive has not yet been inferred by the base branch and ih still depends on hij. lean_profile again gives null block costs; total2872.
No new architecture completed this run. Current best remains in candidate.lean; don't replace it with order.lean/le3.lean/lt5.lean.
