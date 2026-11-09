KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for CallElimCorrect.substOldPostSubset
- Union best (a landmark reached by another line — your proofs are your own): 92.09 from the GPT Astra line (cxline-astra-relay2), 37 tokens, 616 heartbeats.
- Each line's best: Opus 5.5 line 91.41, GPT Astra line 92.09, Flash line 84.08.
- Exchange rate on this problem: 1 token = 0.106 points, 100 heartbeats = 0.644 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
... tok 1523 hb, 88.48.
- first full simp + second simp only + `grind only` (19 tok, 1281 hb): FAIL only case7 (a ∈ [h1] vs a = h1).
  The same with bare `grind`: OK 18 tok 1368 hb, 89.27. With mem_singleton in the 2nd simp: OK 21 tok 1321 hb, 89.25.
- first full simp + `simp_all [getVars]` closer (13 tok): FAIL on the or-split cases, 2662 hb.
- A full simp costs ~70 hb more than simp only on the first step and much more per goal (11 goals).
Next idea: a cheap way to make case7 work for the 19-token variant (1281 hb would score 89.73), e.g. a 0- or 1-token change
that keeps a ∈ [h1] on the target side. None found yet.

Run 6: [tested] after intro+simp: `fun_induction substOld <;> grind only [LExpr.getVars, List.mem_append]` -> OK 19 tok but 2865 hb (79.5). Worse.
Considered converged at 89.6; candidate.lean restored to best.

Run 7 (no improvement; best still 89.6, 22 tok 1250 hb, reproduces exactly). All [tested] on the best base:
- 2nd simp + or_imp: 24/1456; + or_assoc: 24/1272; + or_imp, imp_self: 26/1500.
- grind only [cases Or]: 26/1253; extra `<;> intro` before grind: 24/1259.
- dsimp only [getVars] then simp only [mem_append]: FAIL.
- induction post <;> simp only [substOld, getVars, mem_append] <;> grind only: FAIL (app match case).
- grind only [→ List.mem_append]: FAIL; simp_all only [imp_self, or_true, ...] pre-pass: FAIL.
Converged; no further ideas with expected gain.
- GPT Astra line notes (tail):
... 59/964; final no parentheses -> 57/963.]
- [tested: `apply` instead of `refine` for composition -> same 57/963.]
- [tested: replace the two holes by `..` -> fails recursive cases.]
- [tested: remove base constructor cases and add `exact Or.inl` to repeat-first -> 49/1208, worse score.]
- [tested: global `unfold substOld` immediately after induction instead of app unfold/final simp entry -> 56/1054; global `dsimp only [substOld]` -> 59/987, both worse.]
- [tested on prior 52/1104 base: remove abs case but keep grind -> 48/1177; use plain grind -> 51/1126; add or_assoc to final simp -> 54/1111; app simp only instead of unfold -> 55/1333; grind -mbtc -> 54/1292; grind -revert is invalid.]
- [tested: functional induction with default simp and grind -> 27/2059, compiles but worse score. Functional induction with simp only fails special app cases unless additional conditional simplification is supplied.]
- [tested: removing getVars from final simp -> fails; adding * to final simp with abs omitted -> 50/1237 on grind base; default simp only at end -> fails because singleton membership differs from IH.]
Statement prefix remains byte-for-byte identical to original.lean. No auxiliary declarations or forbidden proof escapes were added.
Next idea: further reduce the direct disjunction composition proof, or reduce constructor handling overhead; the direct closure is now cheaper than grind.

