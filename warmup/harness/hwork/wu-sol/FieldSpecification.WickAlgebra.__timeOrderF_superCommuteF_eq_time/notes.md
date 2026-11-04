Run 8 best: binder.lean, 254 tokens / 7967 hb, score 86.74, compiles v4.32.0. Restore binder.lean to candidate.lean. Improves previous 260/8142 only modestly.
Winning changes: combine map-expansion simp and centrality rewrite into one simp only [c, ofCrAnListF_append, map_mul ι, map_smul ι, Subalgebra.mem_center_iff.mp (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ)], THEN separate simp only [mul_assoc,mul_smul_comm,crAnTimeOrderSign]. Using map_mul ι/map_smul ι saves ~140hb for 2tokens. hs defined as `have hs x y := insertionSort_of_eq_list 𝓕.crAnTimeOrderRel φ l [x,y] r` (binder syntax instead of lambda saves2tokens). Normalize only lhs of hs via `conv at hs => intro x y h; lhs; rw [List.append_assoc]; dsimp` (saves4tokens vs three-lemma simp). dsimp is essential: simp matching needs syntactically reduced cons append.
Profile original candidate: setup suffices1485hb, conv2715hb, map-expansion1526hb, centrality1028hb, dsimp387hb. Proof floor303hb. Largest room structural setup and avoiding map expansion.
[tested: simp-center-inline variant, combining center AND mul_assoc in same simp -> FAIL: associativity normalizes before center can match].
[tested: smallhs.lean, normalize hs lhs only rw[List.append_assoc] without dsimp -> FAIL: hs not used by simp, sign/factor rewrite later fails].
[tested: happ.lean simp only[List.append_assoc,List.append] -> FAIL same pattern].
[tested: hspecial.lean explicit hs φ ψ and hs ψ φ without dsimp -> FAIL same pattern].
[tested: rewrite hs on BOTH sides, use sorted simp mul_assoc then prefix factoring, ←mul_assoc then suffix factoring -> centrality no longer matches unless reassociating afterwards; attempted candidate FAIL].
[tested: msetup.lean unary map m := mulLinearMap commutator, lhs mulLinearMap.compl₂ m -> FAIL: original congrArg requires dsimp conversion; dsimp[m] then first simp rewrites fields to singleton before matching supercommute. Not pursued].
[tested: full annotation ι(𝓕:=𝓕) in map lemmas and center ->279tokens/7739hb, worse].
[tested: full annotations on setup ι.toLinearMap and Subalgebra.mem_center_iff(R:=ℂ) ->284/7931 worse].
[tested: Subsemiring.mem_center_iff.mp instead center ->254/7974, slightly worse].
[tested: center (A:=𝓕.WickAlgebra) ->262/7964 worse].
[tested: direct fun x => ((centerproof).comm x).eq.symm ->261/7970 worse].
[tested: mapminimal.lean distribute only three map_mul on LHS, commute center, then reverse map_mul to reassemble ->262/8515 worse].
[tested: earlycases.lean split statistic before final normalization, cancel common scalar in pos using congr1 ->266/10575 worse].
Confirmed: map_mul f x y, map_smul f c x; Subsemiring.mem_center_iff; IsMulCentral.comm; membership Subalgebra.center reducibly has .comm yielding Commute. [tested lean_run: AlgHom.map_mul and AlgHom.map_smul unknown]; [tested lean_run: ι.toLinearMap(𝓕:=𝓕) invalid argument name; must annotate receiver].
Next idea: genuinely new architecture needed to reach cross-line 203/5904; setup bilinear ext still ~1500hb, huge sort/factor conv ~2700hb. Current hs LHS-only normalization preserves left-associated RHS; factoring two repeat rw blocks is robust. Could replace scalar/factoring block with a narrowly stated local distributivity helper, but expression naming may offset savings. No upstream simplification exists.
