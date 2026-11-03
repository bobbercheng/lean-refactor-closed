KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for putnam_1995_a3
- Union best (a landmark reached by another line — your proofs are your own): 96.12 from the Opus 5.5 line (ccline-opus55-relay1), 177 tokens, 1042 heartbeats.
- Each line's best: Opus 5.5 line 96.12, GPT Astra line 95.4, Flash line 92.68.
- Exchange rate on this problem: 1 token = 0.008 points, 100 heartbeats = 0.236 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
...1 HB but 197 tokens (95.98).
- `rw [hrelation] at h1 h2; simp only [key] at h1 h2`: 1120 HB (worse).
Failed / worse this run:
- subst at top level + key LHS as an explicit ∑: needs `(x y : Fin 9 → ℤ)`; with simp only 1162 HB; with rw+▸ it FAILS (the hypothesis keeps the beta-redex `(fun dig => ..) (..)`).
- `dsimp only` instead of beta_reduce: +24 HB. RHS without parens + add_sub_assoc: 1052 HB, same tokens.
- explicit `dvd_mul_right 7 $ ∑ j, d j * 10 ^ j.1`: 1090 HB (worse than `_`). ring_nf instead of ring1: 2794 HB.
- term-mode key (`eq_add_of_sub_eq' $ (Finset.sum_sub_distrib _ _).symm.trans ...`): 1063 HB, 185 tokens; worse.
  Finset.sum_sub_distrib takes f g EXPLICITLY (so `Finset.sum_sub_distrib.symm` fails).
  Without beta_reduce, `if_neg h ▸` fails on the `(fun j => ..) b` redex.
Older notes: `(x y : _ → ℤ) i` binders; `IsCoprime _ 10` fails (mvars); `dvd_mul_right 7 _` works because ring1 assigns ?X to the first atom (D);
grind finish fails; `simp only [...] at *` costs +100 HB.
Next ideas: the ring1 step (~270 HB) and the key proof are the remaining costs; maybe generalize 10^i.1 to an atom; maybe a cheaper hc construction.
- Bash: use the Write tool for files; no compound commands, sed -i, env-var prefixes, or python heredocs. `#count_heartbeats in` hangs in lean_run.
UNVERIFIED CLAIMS: treat as hypotheses; test with one cheap check before letting one block an idea.
- GPT Astra line notes (tail):
... ten.

Failed or lower-scoring experiments:
- Removing Finset.card_fin fails: ring1 does not evaluate univ.card.
- Moving all sum simplifications into the final goal saves 4 tokens but costs 111 heartbeats.
- Removing `using 1` from convert generates inappropriate deeper congruence goals.
- Finset.dvd_sum needs explicit `(s := Finset.univ)`.
- IsCoprime needs explicit integer type; otherwise it defaults to naturals.
- The final dvd_mul_right needs explicit digits_to_num d; ring1 cannot infer that multiplicand.
- Completely untyped d/e binders in swap fail to infer the function type.
- Final simp only [sub_mul]; abel1 fails in the combined algebra calculation.
- Replacing digits_to_num globally via subst would require spelling out its sum in local declarations; abandoned.
- Earlier runs: combining swap rw and simp only into one simp only saves 2 tokens but adds 58 heartbeats; explicit Bezout witness costs more than decide; prime-based cancellation is slower/longer; omega needs dsimp only and loses score.
- eq_add_iff_sub_eq, eq_add_iff_sub_eq', add_eq_iff_eq_sub are not available lemma names.

Next idea: current proof is compact; any further gains likely require reducing the final algebra elaboration or replacing the local swap identity with an existing sum-update theorem.

Environment: prepend /home/user/.elan/bin to PATH before invoking supplied lean_check.py or lean_run.py.

