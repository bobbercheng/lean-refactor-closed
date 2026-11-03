# Clean pipeline from the seed proofs: 90.69 within the cap (2026-10-14)

From the **seed proofs** of the 15 warm-up rows, with **general knowledge only** (no theorem-keyed briefs, no earlier proofs), GPT-6.1
Sol through **OpenRouter** scored **90.69** on our local scorer (L 84.07, H 88.00, Z 100 on all 15 rows), at **at most $2.60 per
problem at list price** ($38.62 in all). Every final proof was re-checked on every listed toolchain (`snapshot/*.verify.json`: 15 of 15,
mean 90.69). This entry was **not submitted**.

**Working assumption (2026-10-14): this result replicates.** It is one run; two runs of the clean baseline differed by 0.28,
and a confirmation run is planned but on hold.

> **2026-10-28:** this pipeline was developed further into the closed-track final package in [`../final/`](../final/) (GPT-6.1 Sol,
> then GPT-6.1 Terra, a Gemini 4 Argon review and a model-free end stage, all from the seed proofs within $3.00 per row), which scored
> **91.70** officially on these 15 rows (submission `sub15`). No separate confirmation run of the 90.69 pipeline was made.

## Why this run exists

The organizers ruled on 2026-10-12 that:
- the final refactors from the provided seed proofs, so earlier proofs cannot be reused;
- the closed track runs through OpenRouter;
- the $3 cap counts final inference at list price;
- the winner is decided by the organizers' reruns of the submitted code (the board is a reference).

The submitted warm-up entry in this folder (89.46 official, [README.md](README.md)) used per-problem knowledge briefs built from earlier
research on these same 15 problems. That knowledge cannot carry into the final, so we measured what a clean pipeline reaches.

## The pipeline

1. **Model:** `openai/gpt-6.1-sol` via OpenRouter, reasoning effort medium. Turns are **streamed with a junk guard** (`llm/junk.py`): a
   tool call that degenerates into repeated text is cut at once (OpenRouter stops billing on cancel) and never executed or re-sent.
2. **Agent:** our harness (`harness/agent.py`), 40 turns per session. The general knowledge in its prompt:
   - **pattern cards** (`harness/pattern_cards.py`, `--pattern-cards`);
   - the general habits (`--closed-lessons`, on by default);
   - the technique cards.

   No theorem-keyed brief.
3. **Auto-brief** (`harness/autobrief.py`, `--agent-auto-brief`). Before the first session, CPU only, from each row's seed:
   - free passes: normalizer, heartbeat rewrite, heartbeat polish, lint deletions;
   - heartbeat hot spots;
   - a bounded single-edit sweep: 80 compiles per row, deletions and closer swaps;
   - the best combination, checked on every toolchain.

   The session starts from that candidate, with a ~2.5k-character brief of the measured facts. Same code for every row, nothing stored
   per problem.
4. **Budget ladder:** every row is filled to $1.00, then $2.00, then $2.85 (`harness/hx_heldout.py`), **without fresh restarts or
   rescue sessions** (`--no-lineage-rule --rescue 0`).
5. **$0 cleanup** on each final best: the same free passes and sweep (`harness/autobrief.py --from-work-root`). A change is kept only
   when the whole proof scores higher on every toolchain.

Isolation: the run used a whitelist sparse worktree (code and the three data files only; no bank records, run records, docs or briefs)
inside a container that also masks stray files of the Lean environments, with a private compile scratch.

## Result next to the other warm-up pipelines (local scorer, same 15 rows, <= $2.85 per row)

| Pipeline | After round 1 | $1.00 rung | $2.00 rung | Raw at $2.85 | After $0 cleanup |
|---|---|---|---|---|---|
| **This run** | 83.58 | 87.80 | 89.82 | 90.56 | **90.69** |
| Clean, pattern cards only (2 runs) | 76.25 / 76.95 | 82.17 / 83.68 | 88.42 / 88.96 | 89.63 / 89.91 | 89.82 / 90.15 |
| Submitted warm-up run, briefed | 84.37 | 85.80 | 89.76 | 90.45 | 90.55 ([POSTPASS.md](POSTPASS.md)) |

Mean score at equal spend per row: $0.25 per row: this run **81.20**, briefed 73.80, clean 63.10 / 61.72; $0.50 per row: **86.08** /
78.49 / 76.77 / 82.12.

## Per-row result

| Problem | Ladder best | Final (verified) | L | H | Tokens | Heartbeats | Source | Spend (list) |
|---|---|---|---|---|---|---|---|---|
| `CallElimCorrect.substOldPostSubset` | 90.86 | 90.86 | 87.22 | 85.37 | 40 | 757 | ladder | $2.57 |
| `CallElimCorrect.extractedOldExprInVars` | 94.64 | 94.64 | 91.89 | 92.03 | 18 | 215 | ladder | $2.56 |
| `Core.InitsUpdatesComm` | 87.04 | 87.38 | 67.41 | 94.74 | 73 | 226 | cleanup | $2.58 |
| `fundamental_theorem_of_variational_calculus'` | 91.19 | 91.54 | 85.78 | 88.84 | 121 | 1,334 | cleanup | $2.59 |
| `Electromagnetism.ElectromagneticPotential.time_deriv_time_deriv_electricField_of_isExtrema` | 87.09 | 87.46 | 80.39 | 81.98 | 269 | 4,886 | cleanup | $2.57 |
| `FieldSpecification.WickAlgebra.ι_timeOrderF_superCommuteF_eq_time` | 81.84 | 82.11 | 69.10 | 77.23 | 376 | 9,589 | cleanup | $2.60 |
| `Cslib.LambdaCalculus.LocallyNameless.Fsub.Typing.progress` | 91.13 | 91.13 | 82.84 | 90.54 | 70 | 5,664 | ladder | $2.56 |
| `Cslib.SKI.parallelReduction_diamond` | 77.91 | 77.96 | 63.14 | 70.75 | 150 | 416 | cleanup | $2.56 |
| `Cslib.CCS.bisimilarity_congr_choice` | 87.31 | 87.40 | 70.92 | 91.29 | 73 | 338 | cleanup | $2.56 |
| `Binius.BinaryBasefold.fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius` | 91.22 | 91.45 | 87.42 | 86.93 | 184 | 2,092 | cleanup | $2.58 |
| `Binius.BinaryBasefold.fold_advances_evaluation_poly` | 94.34 | 94.35 | 95.33 | 87.73 | 89 | 5,653 | cleanup | $2.55 |
| `interleaved_affine_gaps_imply_tensor_gaps` | 92.08 | 92.26 | 91.20 | 85.57 | 119 | 1,354 | cleanup | $2.58 |
| `putnam_1964_a4` | 96.94 | 97.03 | 93.67 | 97.43 | 112 | 2,872 | cleanup | $2.58 |
| `putnam_1964_b2` | 98.89 | 98.89 | 98.57 | 98.09 | 25 | 2,576 | ladder | $2.59 |
| `putnam_1995_a3` | 95.87 | 95.88 | 96.16 | 91.48 | 157 | 1,214 | cleanup | $2.59 |
| **Mean** | **90.56** | **90.69** | **84.07** | **88.00** | | | | **$38.62** |

Spend is the harness meter at OpenRouter list price ($2.50 input, $10 output, $0.10 cached input per 1M; cached tokens counted at the
cache price, which the meter overstates slightly against OpenRouter's billed usage). The cleanup made no API calls.

## Knowledge provenance and disclosure

- **Seed proofs only.** Every session started from the row's provided reference proof, or from the auto-brief candidate computed from
  it in this run. No earlier proof of these rows was available to the agent: the whitelist worktree holds none, and the container
  masks the stray environment files.
- **Pattern cards** were distilled on 2026-10-13 from the theorem-keyed briefs, keeping only techniques selected by the shape of a
  proof. `code/harness/test_pattern_cards.py` blocks every warm-up theorem name, every problem-local identifier of the warm-up
  statements and a list of names from the briefs. The **general habits** were mined from earlier Opus 5.5 and GPT Astra lines. Both
  came from research that included these rows, and both are general by construction; we disclose them.
- **Auto-brief:** computed by CPU from each seed with the same code for every row. For 11 rows it was computed by our $0 measurement
  run (same code, same seeds) and copied in; the other 4 were computed inside the run's container. Byte-identical inputs and code.
- **Runner inputs:** none from earlier runs. Rescue and fresh-restart targets are 100 for every row on this clean set.

## Interruption

At 08:56 UTC the OpenRouter key's own $190 limit was reached and calls returned 403. The ladder was stopped by hand; nothing was lost
(three sessions ended early). The run resumed at 11:53 UTC after the limit was raised to $210, at a later commit whose run code is
identical (the only change between the two commits is the spend guard). The guard now also stops on a key's own limit.

## Where everything is (`autobrief_20261014/`)

| Folder | What it holds |
|---|---|
| `snapshot/` | the final proofs in submission format (`autobrief-ab1-20261014.jsonl`), per-row scores and sources (`.predictions.json`), the re-check on every toolchain (`.verify.json`, `verify.log`) |
| `code/` | the exact files the run's worktree held (whitelist), plus the launcher `probe/heldout/run_wuclean_ab.sh`, the spend guard, the snapshot builder and the tests |
| `states/` | each row's workspace at the end (state, notes, best proof) and `_autobrief/`: the 15 auto-briefs as given to the sessions (`.md`) with all measured edits (`.json`) |
| `runs/` | every round's records: verified candidates, session summaries and **full trajectories** (gzipped) |
| `logs/` | the ladder's logs (`jobs.log`, one log per round, the auto-brief pre-step) and the spend guard's log |
| `cleanup/` | the $0 cleanup's per-row results and log |
| `baseline/` | the two clean runs: ladder logs and per-row bests (scores only) |

## Re-run

1. Set up the environments as in [README.md](README.md) section 6.
2. Put an OpenRouter key at the path named by the `gpt-6.1-sol` preset in `code/harness/agent.py`.
3. From a checkout of this code, run `bash probe/heldout/run_wuclean_ab.sh`. It creates the whitelist worktree, measures the auto-briefs
   (CPU) and runs the ladder.
4. Then run the cleanup and the snapshot:
   ```
   python3 harness/autobrief.py --from-work-root <worktree>/harness/hwork/wuclean-solab1 --out-dir <dir>
   python3 probe/autobrief/build_snapshot.py --work-root <...> --cleanup <dir> --out <stem>
   python3 probe/autobrief/build_snapshot.py --verify <stem>.jsonl
   ```

Expect about $39 at list price and about 8 hours of wall time on one machine (this run: about 1 h of auto-brief measurement and 6.7 h
of ladder, not counting the 3 h pause). A rerun is a new draw: the clean baseline's two runs
differed by 0.28.
