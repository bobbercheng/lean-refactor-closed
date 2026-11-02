KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for Cslib.CCS.bisimilarity_congr_choice
- Union best (a landmark reached by another line — your proofs are your own): 91.14 from the Opus 5.5 line (ccline-opus55-bounty1), 51 tokens, 243 heartbeats.
- Each line's best: Opus 5.5 line 91.14, GPT Astra line 90.95, Flash line 82.65.
- Exchange rate on this problem: 1 token = 0.133 points, 100 heartbeats = 0.864 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
...ore, 1 hb ≈ 0.0086 score, so 1 token ≈ 15 hb.
- Run 4 wins (106 -> 86):
  - factor `.imp fun _ => ...` out: `apply Exists.imp fun _ => .imp .choiceL .bisim` WORKS with apply;
    then `exacts [h.follow_fst t, ...]`.
  - `<;> rename_i t` after `rintro s ⟨⟩` (‹_› = 3 tokens).
  - `refine (⟨_, ChoiceBisim.choice ·, ?_⟩)` instead of `refine fun hpq => ⟨...⟩` (−1).
- Failed / worse:
  - `rintro s ⟨t⟩` / `(t | t)`: names line up with Tr's constructor order, choiceL doesn't get `t`.
  - Merging both cases in one `<;> first | (cases t ...) | ...` chain: 81 tok but 878 hb -> 81.70.
  - `<;> [(C); B]` + `all_goals first | exact h.follow_fst t | exact h.follow_snd t`: 85 tok, 538 hb.
  - `<;> [C; B]` + one 4-item exacts, or `swap` + B first: net 0 tokens.
  - C case as 4-term `exacts [...]`: 387 hb but 105 tok.
  - B case as one `exact ⟨fun _ t => (h.follow_fst t).imp .., ..⟩`: 97 tok.
  - `exists s, .choiceR t, ...` fails on the snd/choiceR goal.
  - `a <;> b <|> c` parses as `(a <;> b) <|> c`.
- API: Bisimilarity.{follow_fst,follow_snd,isBisimulation (lts₁ lts₂ explicit),symm,trans},
  HomBisimilarity.refl (s explicit), IsBisimulation.{sup,comp,inv,le_bisimilarity,follow_*}. No Tr inversion lemmas.
- Tooling: grep/git outside the workspace, pipes, heredoc python and `~[` in bash are blocked; use Write tool for
  files and lean_run `#check`/`#print`.
- Probably optimal or within 1 token.
- GPT Astra line notes (tail):
...elation hypothesis a_2, transition a_1.]
- [tested: replace initial `refine ⟨_, ChoiceBisim.choice a, ?_⟩` with `exists ChoiceBisim, ChoiceBisim.choice a` -> 64 tokens / 457 heartbeats, compatible on all toolchains.]
- [tested: use `exists _, ChoiceBisim.choice a` -> 64 tokens / 455 heartbeats, best. Unlike `use`, `exists` successfully infers the relation from the explicitly named constructor.]
- [tested: `use ChoiceBisim, ChoiceBisim.choice a` -> fails to infer implicit defs.]
- [tested: replace right-choice exact tuple with `exists _, Tr.choiceR a_1, ChoiceBisim.bisim (HomBisimilarity.refl _)` -> invalid tuple notation for ChoiceBisim.]
- [tested: right-choice `exists _, Tr.choiceR a_1` followed by exact bisim/refl -> compiles, 62 tokens / 748 heartbeats, worse score 85.34.]
- [tested: `repeat' intro` instead of `repeat intro`, or `case choiceR` instead of `case' choiceR` -> same 64 tokens / 455 heartbeats.]
- [tested: final transition mapping `apply_rules [Tr.choiceL]` -> fails to introduce the function argument.]
- [tested: `intro ..` -> syntax error; not a replacement for repeated introductions.]
- [tested: `apply Exists.imp _` instead of apply plus rotate_left -> 64 tokens / 456 heartbeats.]

Next possible direction: avoid the closing automation cost of `exists` while retaining its shorter witness syntax, or find a cheaper right-choice witness tactic. No optimality claim.

