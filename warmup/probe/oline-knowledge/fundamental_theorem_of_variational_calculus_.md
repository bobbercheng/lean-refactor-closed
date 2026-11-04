KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for fundamental_theorem_of_variational_calculus'
- Union best (a landmark reached by another line — your proofs are your own): 92.13 from the Opus 5.5 line (ccline-opus55-normalize1), 109 tokens, 1290 heartbeats.
- Each line's best: Opus 5.5 line 92.13, GPT Astra line 91.69, Flash line 88.42.
- Exchange rate on this problem: 1 token = 0.039 points, 100 heartbeats = 0.279 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
... ?_ $\n by rw [hφ1, one_mul]\n apply hpos.ne').ne' $\n by simpa ... using hg _ $ IsTestFunction...`
  and `exists_contDiff_tsupport_subset $ hinner_cont...`. -4 tok, 0 hb. The normalizer did NOT apply these, so do them by hand.
- [tested, worse] (hφn ⟨x, rfl⟩).1 instead of Set.range_subset_iff.1 hφn x: +1 tok. by_contra hx0 instead of false_or_by_contra+rename_i: -1 tok, +18 hb (91.77 vs 91.78).
  by_cases hx : x ∈ tsupport φ + simp [image_eq_zero_of_notMem_tsupport hx]: -1 tok, +23 hb. The two combined give 118/1304, worse.
  Term-mode `if hx : φ x = 0 then (mul_eq_zero_of_left hx _).ge else ...` inline: 126/1241, worse. refine (no '), exact vs apply, simp [*], subset_tsupport: all noise or worse.
  `(by simp [hφ1, hpos.ne'])` for center: FAIL (the implicit x is not fixed). simp only [hx, zero_mul, le_refl]: FAIL (`0 x ≤ 0` remains).
- exact? finds no lemma for 0 ≤ a*b from (a ≠ 0 → 0 ≤ b), and none for 0 < ⟪x,x⟫ (InnerProductSpace'). No real_inner_self_pos', inner_self_ne_zero'.
- Profiler (set_option profiler true in + threshold 1 in lean_run works): costs spread over obtain ~3.6ms, simpa ~4.4ms, apply ~2.2ms, simp ~1.4ms.
- Sandbox: python scripts, redirected sed, and grep outside the workspace are blocked. Write variants with the Write tool.
Next ideas: an integrand ⟪f x, φ x • f x₀⟫ directly (no simpa, center via one_smul), which needs a HasCompactSupport lemma for inner.
- GPT Astra line notes (tail):
...qualified `Filter.Tendsto.eventually_const_lt hpos hinner_cont.continuousAt` -> 127 / 1290 before the successful changes; worse.]
- [tested: center nonzero `rwa [hφ1, one_mul, ne_eq, inner_self_eq_zero']` -> 128 / 1318 before the successful changes; worse. Omitting `ne_eq` fails.]
- [tested: center nonzero `mul_ne_zero (hφ1 ▸ one_ne_zero) hpos.ne'` -> 124 / 1351 before the successful changes; worse.]
- [tested: `<|` throughout final positive branch -> identical metrics.]
- [tested: `let hinner_cont` with `_` in place of its constant-function argument -> fails unresolved metavariables, just as `have` does.]
- [tested: `change 0 ≤ _` after `intro x` -> 130 / 1308 before the successful changes; worse.]
- [tested: `refine'` instead of `apply` in the last branch -> 126 / 1300; worse. In center nonzero -> 126 / 1286; worse. `exact'` is not an available tactic.]
- [tested: `apply Classical.byContradiction; intro hx0` -> 128 / 1256, narrowly worse than 126 / 1284 despite the same rounded score.]
- [tested: `by_contra! hx0` -> 127 / 1292; worse.]
- [tested: eliminate `rename_i` and use `(by assumption)` or `‹_›` for the nonzero hypothesis -> 128 / 1335 and 127 / 1335; both worse.]

Next idea: look for other tactic elaboration savings while retaining the existing mathematical argument. The two successful changes concern tactic elaboration only; no claim of an optimal lower bound is made.

