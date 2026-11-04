KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for Cslib.SKI.parallelReduction_diamond
- Union best (a landmark reached by another line — your proofs are your own): 82.19 from the Opus 5.5 line (ccline-opus55-bounty1), 103 tokens, 400 heartbeats.
- Each line's best: Opus 5.5 line 82.19, GPT Astra line 81.46, Flash line 69.38.
- Exchange rate on this problem: 1 token = 0.082 points, 100 heartbeats = 2.410 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
... h₂ => by` (-2 tok) was only usable with recursion; induction needs the name c for generalizing.
- Merged outer red_I/K/S into one `| _ => cases h₂ with | par h h' => first | I | K | S` then `| _ => exact ⟨_, .refl _, by constructor⟩`.
- SHADOWING TRAP: `obtain ⟨_, h, rfl⟩ := Ka_irreducible _ _ h` fails. Use fresh names.
- `by constructor <;> constructor <;> assumption` instead of `.par (.par h hb) (.par h' hb)`: small net gain.
- HARNESS QUIRK (flaky): "Parser skipped input between top-level statements". Put `first` alone on its own line; rerun.
- Term-mode match: 10663 hb.
Exchange rate: 1 token ≈ 0.082 score, 1 hb ≈ 0.024 score.

Next ideas (untested): un-merge the outer red_X cases (needs a drop of more than 135 hb for +40 tok, unlikely);
`@fun _ _ c h₁ h₂ => by induction ...` (same token count).

Run 6: confirmed best 262 tok / 499 hb (66.85) still in candidate.lean.
- outer first-alt order S,K,I: 516 hb (worse). Order I,K,S is the best measured.
- Counted on paper and not worth running (more tokens): `.elim fun _ ⟨..⟩ =>` chains or `And.intro` to merge the two IH obtains;
  splitting `rcases ha with _ | ⟨⟨⟩, h⟩` for red_K (two goals, no shared closer).
- Bash in this workspace: pipes, `&&` chains, and python heredocs need approval. Use the Write tool and single commands.
Conclusion: looks like a local optimum. The remaining ideas don't pay off at 0.082/token and 0.024/hb.
- GPT Astra line notes (tail):
...`cases hc` instead of cases I_irreducible _ hc -> -2 tokens, +9 heartbeats, slightly worse score]
- [tested: keeping an equality name and rw instead of rfl in either K or S obtain -> +4 tokens, +17 heartbeats]
- [tested: S obtain ⟨e,f,h⟩ then cases h.2.2, building join with projections -> 147 / 404, score 78.49]
- [tested: rcases instead of obtain for both induction results -> identical tokens and heartbeats]
- [tested: named ParallelReduction.par instead of outer field notation in S -> same tokens, +1 heartbeat]
- [tested: econstructor instead of second constructor in final block -> same tokens, +1 heartbeat]

Prior experiments:
- Let instead of obtain for induction results added 32 heartbeats.
- Flattening both induction-result conjunctions added four tokens and two heartbeats in an earlier version.
- Explicit orientation dispatch via `first | apply And.intro hjoin | apply And.intro ?_ hjoin | apply And.intro (.refl _)` worked, but the current shared two-goal processing is shorter.
- Generic early reflexive-case solving and And.symm variants scored worse.

Environment:
- [tested: bare python3 lean_check.py -> FileNotFoundError for lake]
- Use `PATH=/home/user/.elan/bin:$PATH python3 /home/user/source/lean-refactor/harness/tools/lean_check.py`.

Possible next experiments: further reduce induction overhead or assumption traversal. No claim that the current proof is minimal.

