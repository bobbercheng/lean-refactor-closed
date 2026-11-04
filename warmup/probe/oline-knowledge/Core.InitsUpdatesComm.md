KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for Core.InitsUpdatesComm
- Union best (a landmark reached by another line — your proofs are your own): 89.8 from the Opus 5.5 line (ccline-opus55-bounty1), 59 tokens, 183 heartbeats.
- Each line's best: Opus 5.5 line 89.8, GPT Astra line 89.75, Flash line 85.09.
- Exchange rate on this problem: 1 token = 0.149 points, 100 heartbeats = 0.784 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
...atedStates σ ks vs := updatedStates' σ (ks.zip vs).

## What failed / tried
- comm ▸ directly after the two ▸ (no delta): folded `updatedStates` → no match.
- `simp [*]` instead of `simp only [List.unzip_zip, *]`: simp turns unzip.1 into map Prod.fst (zip) → fails.
- rw [List.unzip_zip Hl, ...] : more tokens. delta vs unfold: same.
- Scoring: 1 token ≈ 0.15 score ≈ 19 HB.
## Next ideas
Near optimal. Only a shorter disjointness proof (currently 20 tokens: simp only/intro/cases) could help.

## Run 5 (re-verified best: 76 tok / 202 HB / 87.12)
Counted these on paper only; none were compiled. Each is worse on tokens:
- term `updatedStatesComm (List.unzip_zip this ▸ List.unzip_zip ‹_› ▸ fun a h2 h1 => …)`: ~15 tok vs 11.
- `exact fun a h2 h1 => Bool.noConfusion (…)` / `nomatch`: more tokens than `intro`+`cases`.
- an extra `have := InitStatesNotDefined Hinit` costs 4 tokens and saves only 2 (2 uses).
- `rw [List.unzip_zip this, List.unzip_zip]` leaves a length side goal, so it costs more.
Only context lemmas about Disjoint are inside updatedStatesComm's own proof; there's no helper lemma to reuse.
Conclusion: stop here unless a new lemma appears upstream.

## Run 6
Re-checked the best (76 tok / 202 HB / 87.12). Also counted on paper: putting UpdateStatesLength Hup inline in both places
(updatedStatesUpdate arg + simp arg) costs 5 tokens, the same as `have`+`this`. No gain. Stopped.
- GPT Astra line notes (tail):
...nal cases instead of injection -> 60 / 177.]
- [tested: all_goals simp only instead of simp -> 61 / 169; simp_all -> 60 / 188.]
- [tested: use uninstantiated InitStatesLength and UpdateStatesLength in simp
  or simp_all -> both fail to make progress (58 tokens).]
- [tested: two separate equality cases -> 60 / 181; rewrite both equalities
  -> 62 / 157; simp both equalities and updatedStates -> 62 / 164.]
- [tested: simp only [updatedStates, updatedStatesComm] -> does not establish
  the conditional commutation, so subsequent updatedStatesUpdate fails.]
- [tested: move combined equality cases immediately after initial intros ->
  60 / 173; after repeat constructor affects only initialization and fails
  later in the update goal.]
- [tested: delta instead of unfold, rcases instead of cases, split init
  lemma applications into apply/assumption -> each 60 / 171.]
- [tested: rw instead of rewrite for commutation -> 60 / 216.]
- [tested: use $ to combine definedness apply chain -> 60 / 172; combine
  initialization not-defined apply chain -> 60 / 171.]
- [tested: exact instead of apply for InitStatesNotDefined or
  UpdateStatesDefined' -> 60 / 171; InitStatesNodup -> 60 / 172.]
- [tested: repeat' constructor -> 60 / 174; swap tactic is unavailable.]
- Next possible direction: a structurally different proof of commutation or
  disjointness. No claim that the current proof is minimal.

