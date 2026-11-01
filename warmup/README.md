# Warm-up results: the closed-source LLM track

This folder contains the code, knowledge briefs, data, logs and full per-message trajectories behind our warm-up work for the
**Lean Refactor Arena** (NeurIPS 2026 VERICODEGEN workshop competition), **closed-source LLM track**, on the 15-problem
warm-up subset. All paths below are relative to this `warmup/` folder.

Spend figures for the first submission's run are in [BUDGET.md](BUDGET.md).

## From-seed pipeline submission (2026-10-28): 91.70

| | |
|---|---|
| Pipeline | the closed-track final package in [`../final/`](../final/) (arm B of our final candidates): GPT-6.1 Sol in tool-using sessions until a problem has spent $1.25, GPT-6.1 Terra for the later budget steps, a Gemini 4 Argon review and a model-free end stage, all through OpenRouter and all from the seed proofs |
| Problems | the 15-problem warm-up subset |
| Submission | `sub15-closed-armB-final`, username `Vexorium-Agent`, uploaded 2026-10-28 00:57 UTC |
| Official score | **91.70** (L 85.65, H 89.44, Z 100: every proof compiles on every listed toolchain) |
| Local scorer | 91.744 in the run; 91.701 on a regrade on every toolchain |
| API spend | mean **$2.67**, max **$2.79** per problem at list prices; the cap is $3.00 per problem, enforced in code |

That run's records are not in this folder; [`../final/`](../final/) holds the reviewed package of its pipeline plus five later
additions that run did not use, the Terra tail, the sorry guard, the review repair + stack (R6), the style rewrite (style_rw)
and the approach pick (1 extra group, time cap), with the forbidden-construct list re-synced to the leaderboard's 2026-10-28 list
and the auto-brief opening fix ([`../final/CODE_VERSION.md`](../final/CODE_VERSION.md)). Since 2026-11-01, `../final/` is the code
of our closed official run on the final benchmark (commit `b5f036ab`), plus the reference-heartbeats tool and the env-side workaround
that run used ([`../final/README.md`](../final/README.md) section 9). Our two other closed-track uploads, `sub12` (2026-10-22, a
development union) and `sub16` (2026-10-30, a test upload of a ceiling run), were not from the seed proofs; [`../README.md`](../README.md)
lists every upload. This folder documents the earlier work that led to `../final/`: the **first submission** (`sub06`, 89.46 official, 2026-10-12), which sections 1 to 10 below
describe and replicate, the CPU post-passes ([POSTPASS.md](POSTPASS.md)) and the clean from-seed pipeline ([AUTOBRIEF.md](AUTOBRIEF.md)).

> **2026-10-14:** a clean pipeline from the seed proofs (general knowledge only, auto-brief, junk guard, $0 cleanup) scored **90.69**
> within the cap; this folder's original run below used per-problem briefs. See [AUTOBRIEF.md](AUTOBRIEF.md).

## 1. Result of the first submission (sub06)

| | |
|---|---|
| Submission (ledger id) | `sub06-closed-8951` |
| Username | `Vexorium-Agent` |
| Uploaded | 2026-10-12 01:20:23 UTC (`sent_at` in `submit/ledger.jsonl`) |
| Official worker score | **89.46** (mean of the 15 worker rows in `submit/results/sub06-closed-8951.worker.json`: 89.4627) |
| Local prediction | 89.51 (`predicted_combined` in the ledger) |
| Compiled | 15/15, each on every listed toolchain (36 of 36 problem-toolchain pairs) |
| Leaderboard | rank #2 at upload, with 89.53 above and 89.38 below. This comes from the project commit log. The ledger record has `leaderboard_rank: null`. |
| Submitted file | `submit/candidates/sub06_closed_wu_sol_8951.jsonl` (sha256 `a2764df1…`) |
| Same file as | `probe/heldout/wu-hx-sol/snapshots/reached89.5-20261011T235247Z/submission.jsonl` (byte-identical) |
| Benchmark | `data/benchmark_warmup.jsonl` (sha256 `6209680c…`), reference heartbeats `data/benchmark_heartbeats.jsonl` (sha256 `f342873a…`) |

**Scoring.** For each problem the score is the mean of three percentages:

- length reduction: proof tokens compared with the reference proof
- heartbeat reduction: elaboration cost compared with the reference
- compatibility: the share of the problem's listed toolchains on which the proof compiles

A problem that does not compile scores 0. The overall score is the mean over all 15 problems. The local formulas are in
`scorer/score.py` and the lexer is in `scorer/tokenize.py`.

**Which snapshot was submitted.** The file we submitted is the snapshot of the run taken the first time its local mean
reached 89.5, at 2026-10-11 23:52:47 UTC. It was not picked for a leaderboard position. The run kept going after this
point. At the moment of the snapshot:

- local mean: 89.51
- total API spend: $23.18 billed
- highest spend on any one problem: $1.7386 billed, which is $1.7561 at list price ($1.7563 when recomputed from token counts)

**The spend claim.** We claim **at most $1.76 per problem at list price ($1.7386 billed), with a hard cap per problem**.

- Every call that returned usage is counted: 1,624 calls up to this snapshot.
- Billed cost is 0.99 × list price.
- The team checked that account billing reconciles with the meter to the cent.
- A transport failure that the harness retried is not logged ("How spend is metered" in [BUDGET.md](BUDGET.md)).

This is **not a cold-start cost** (section 5). [BUDGET.md](BUDGET.md) has the per-problem figures.

**Per-problem results of the submitted file.** The last column names the session that first produced the submitted proof:
`rN` is a resume round and `fN` is a fresh-lineage session.

| # | Problem | Project | Toolchains | Tokens (worker) | Heartbeats (worker) | Local | Worker | Compat | From |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `CallElimCorrect.substOldPostSubset` | strata | 1 | 39 of 313 | 597 of 5,175 | 92.00 | 92.00 | 1/1 | r9 |
| 2 | `CallElimCorrect.extractedOldExprInVars` | strata | 1 | 20 of 222 | 258 of 2,696 | 93.82 | 93.81 | 1/1 | r9 |
| 3 | `Core.InitsUpdatesComm` | strata | 3 | 64 of 224 | 175 of 4,251 | 89.14 | 89.10 | 3/3 | r4 |
| 4 | `fundamental_theorem_of_variational_calculus'` | physlib | 1 | 119 of 851 | 1,375 of 11,947 | 91.58 | 91.50 | 1/1 | r4 |
| 5 | `Electromagnetism.ElectromagneticPotential.time_deriv_time_deriv_electricField_of_isExtrema` | physlib | 1 | 446 of 1,372 | 12,411 of 26,970 | 73.89 | 73.82 | 1/1 | r4 |
| 6 | `FieldSpecification.WickAlgebra.ι_timeOrderF_superCommuteF_eq_time` | physlib | 1 | 304 of 1,217 | 10,371 of 42,225 | 83.46 | 83.49 | 1/1 | r2 |
| 7 | `Cslib.LambdaCalculus.LocallyNameless.Fsub.Typing.progress` | cslib | 3 | 127 of 408 | 7,275 of 59,830 | 85.55 | 85.57 | 3/3 | r8 |
| 8 | `Cslib.SKI.parallelReduction_diamond` | cslib | 4 | 135 of 407 | 521 of 1,383 | 76.75 | 76.39 | 4/4 | f8 |
| 9 | `Cslib.CCS.bisimilarity_congr_choice` | cslib | 3 | 72 of 251 | 396 of 3,858 | 87.03 | 87.02 | 3/3 | r1 |
| 10 | `Binius.BinaryBasefold.fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius` | arklib | 4 | 220 of 1,463 | 1,917 of 15,645 | 90.97 | 90.90 | 4/4 | r8 |
| 11 | `Binius.BinaryBasefold.fold_advances_evaluation_poly` | arklib | 3 | 142 of 1,906 | 5,350 of 45,273 | 93.62 | 93.58 | 3/3 | r8 |
| 12 | `interleaved_affine_gaps_imply_tensor_gaps` | arklib | 3 | 100 of 1,353 | 1,301 of 9,198 | 92.88 | 92.82 | 3/3 | r4 |
| 13 | `putnam_1964_a4` | putnambench | 3 | 136 of 1,769 | 2,070 of 111,476 | 96.82 | 96.82 | 3/3 | r8 |
| 14 | `putnam_1964_b2` | putnambench | 2 | 25 of 1,754 | 1,055 of 134,499 | 99.26 | 99.26 | 2/2 | r8 |
| 15 | `putnam_1995_a3` | putnambench | 3 | 181 of 4,085 | 1,130 of 14,130 | 95.88 | 95.86 | 3/3 | r4 |

**Pre-upload checks**, both stored in the snapshot directory:

- `verify.log` / `verify.json`: an independent re-check of every row, starting from a fresh state. It covered the
  byte-identical statement, the forbidden-construct filter, the primary compile, a compile on every listed toolchain and
  the local score. All 15 rows compile everywhere, and the re-verified mean is 89.51.
- `optcheck.log`: the lakefile-options check. The Strata rows were compiled with `-DwarningAsError=true` and the ArkLib rows
  with `-DautoImplicit=false`, on every listed toolchain, for both the snapshot proof and the reference proof.
  - The two `CallElimCorrect` rows fail for the snapshot and the reference alike, with `171:8: declaration uses 'sorry'`.
    That `sorry` belongs to an earlier declaration in the upstream file `Strata/Transform/CallElimCorrect.lean`, not to
    our proofs.
  - Every other checked row compiles under the options.

**The run did not finish.** It was meant to climb to a $2.85 cap per problem. OpenRouter account credits ran out during
round 13, and the runner stopped at 01:34 UTC when every round-14 request got HTTP 402. The team then paused the
OpenRouter arms.

The state at the pause is saved as `probe/heldout/wu-hx-sol/snapshots/paused402-20261012T014625Z`:

- local mean 90.47, total spend $31.84 billed
- this snapshot was **not** submitted and has no verify/optcheck run
- its `scores.json` was written ad hoc by an interactive session, not by `snapshot_watch.py` (section 8)

**CPU post-passes, 2026-10-13: 90.47 -> 90.55 with no API spend.** Four deterministic passes (lexer normalizer, transfer lane over
the run's own bests, heartbeat polish, heartbeat micro-normalizer) changed 10 rows, each kept only when strictly better on every
listed toolchain. Spend is unchanged ($31.84 billed, at most $2.6215 per problem). Snapshot
`probe/heldout/wu-hx-sol/snapshots/postpass-20261013T192012Z` (local mean 90.55, **not** submitted); details, code and records in
[POSTPASS.md](POSTPASS.md).

## 2. Model and harness

**Model.** GPT-6.1 Sol through OpenRouter, API model `openai/gpt-6.1-sol`. The harness selects it with the preset
`gpt-6.1-sol` in `MODEL_PRESETS` in `harness/agent.py`:

- OpenAI-compatible `/chat/completions` at `https://openrouter.ai/api/v1`, via `llm/openai_compat.py`
- reasoning details are passed back to the model on later turns
- provider-reported cost is requested on every response
- reasoning effort `medium`; the rescue sessions used `high`
- every trajectory header records the model, API model, endpoint, effort, 40-turn budget and `max_tokens` 4000

**Harness: `harness/agent.py`.** Each problem has a persistent workspace that every session resumes:

- Location: `harness/hwork/wu-sol/<problem>/`.
- Contents: `original.lean`, `context.lean`, `candidate.lean`, `best.lean`, the model's own `notes.md`, and `state.json`
  (best proof and score, attempt history, runs, `api_spend`, `budget_milestones`, `fresh_lineages`).
- Model tools: `read_file`, `write_file` (writing `candidate.lean` also compiles it), `lean_check`, `lean_check_variants`,
  `lean_run`, `lean_skeleton`, `lean_goals`, `lean_profile`, `lean_mine`, `lean_search`, `shell` and `finish`.
- The `shell` tool can run `git log -p` / `git show` on the problem's file in the project's upstream clone
  (`envs/<project>.git-main`). This upstream-history hint is on by default; `--no-upstream-history` turns it off.
- `read_file` and `write_file` are confined to the workspace. `shell` is not: it runs `bash -lc` as the invoking account,
  guarded only by a deny-list (section 7.2).
- Every compiling check is scored by the local scorer and recorded. The harness keeps the best compiling candidate even if
  the model never calls `finish`.
- Sessions are 40 turns with `--no-adaptive-turns`. The output cap is 12,000 tokens per turn (`--max-tokens 4000` × 3),
  raised to 16,000 after a truncated turn.
- A model tool call that is cut off at the output cap is dropped from the conversation history. This runaway-call fix is
  in agent.py from commit `08002e91`. In the recorded run it was active from round 9 on, but the code in this folder applies
  it in every round (section 4 and [CODE_VERSIONS.md](CODE_VERSIONS.md)).
- All results are tagged `closed-dev-only` and are never written to the proof bank (`bank/`).

The opening message of a session contains:

- the problem
- the workspace digest and notes
- technique cards (`harness/cards.py`)
- the "five habits" block (`--closed-lessons`, on by default in this code). It holds general habits mined from the Opus 5.5
  and GPT Astra lines. All 126 trajectory files contain it (section 5).
- for the 12 project rows (not the 3 PutnamBench rows), an `UPSTREAM` digest: the theorem as it stands at the head of the
  project's upstream clone (section 5)
- library leads from the lemma search
- the knowledge brief (section 5)
- an "opening move" instruction

**Compiling and scoring.**

- `scorer/compile.py` runs `lake env lean --json` inside the prepared environment for the problem's toolchain (`envs/`).
- Heartbeats are measured by an injected `IO.getNumHeartbeats` command under `set_option Elab.async false`. They are
  compared with reference heartbeats measured by the same counter (`data/reference_heartbeats_local.json`, measured
  2026-10-06).
- The primary toolchain is the newest one listed for the problem. A proof that improves is also compiled on every other
  listed toolchain.
- Every Lean process goes through `scorer/memgate.py`, a memory admission gate under a file lock:
  - default claim 8 GB plus an 8 GB reserve; Lean runs with `-M 16000`
  - the reserve is waived after 600 s of waiting, and the gate gives up after 1,800 s. These bounded waits came with
    commit `f7d41ecf` and were active in the recorded run from round 9 on.
  - environment variables `LRA_MEMGATE_*` and `LRA_LEAN_MEMORY_MB`

## 3. The budget-ladder protocol (`harness/hx_heldout.py`)

The runner drives rounds of `agent.py` sessions over all 15 problems. Spend is metered per problem, and the meter covers
every lineage of that problem.

- **Rungs: $1.00, $2.00, $2.85 per problem, billed.** All rungs, caps and spend figures in this protocol are in billed
  dollars, as metered. Every problem is filled up to a rung before any problem may pass it.
  - A problem takes part in a round while its spend + $0.30 (`SESSION_FLOOR`) is below the current rung.
  - When every problem has reached a rung, the runner writes a `MILESTONE` report to `jobs.log`: mean score, per-repository
    means, billed spend total/mean/max, and score at budget.
- **Hard per-problem gate.** Every session runs with `--budget-usd <rung>`.
  - Before each turn, `agent.py` reserves the worst case of the next turn, priced at list prices:
    - the whole context billed as uncached input: estimated tokens + 20,000
    - plus the full output cap
    - and never less than 1.25 × the most expensive turn of the session so far
  - If spend + reserve would exceed the cap, the session ends before the call.
  - The provider cannot bill more output than `max_tokens`, so a problem's metered spend cannot cross the rung.
  - `--budget-milestones 2.0` records the turn on which a problem's spend crosses $2 (the `budget_milestones` field in
    `state.json`).
- **Lineage rule (fresh restarts).** After each round, a problem restarts in an empty workspace if it is at least 3 points
  below its target and either:
  - its last session gained less than 0.5, or
  - its first session landed at least 4 points below the typical first session.

  The target and the typical first-session score are runner inputs taken from earlier lines (section 5, item 3).

  How a fresh restart works:
  - At most 2 fresh restarts per problem.
  - The fresh workspace starts with no proof, notes or variants. It is seeded only with the problem's spend so far, so the
    same cap covers both lineages.
  - The fresh best replaces the main best only if it is strictly higher.
  - The fresh workspace is then archived as `harness/hwork/wu-sol-fresh.done-<run>` and never resumed.
- **Rescue.** After the $2.00 milestone (`--rescue 4 --rescue-rung 2.0 --rescue-effort high`), there is one fresh
  RESTRUCTURE session for the 4 stuck problems furthest below their target.
  - The session starts from the reference proof with `--brief restructure`, at effort high, capped at the next rung ($2.85).
  - "Stuck" means the problem gained less than 0.5 over the whole $2.00 rung. This stuck-only rule was deployed at 23:20
    (section 4).
  - The marker file `rescue.done` stops the rescue from running twice.
- **Early stop rule: cancelled.** The run was launched with `--stop-at 90.5 --stop-rung 2.0`. The team cancelled it
  (run to the cap) by arming `probe/heldout/nostop_guard.py` at 23:51:47.
  - The guard would have relaunched the runner without the rule if the rule had fired.
  - The rule did not fire, because the $2.00 milestone mean was 89.76, below 90.5. The guard exited at 00:23:57.
  - Launching without `--stop-at/--stop-rung` therefore behaves the same as this run.
- **Snapshot watcher.** `probe/heldout/snapshot_watch.py` (armed 23:50–23:51, threshold 89.5, polling every 60 s) saved
  the state the first time the mean reached 89.5 without stopping the run.
  - It writes `submission.jsonl`, in the Arena upload format: every row, with the reference proof where nothing improved.
  - It also writes `scores.json`: per-problem local score, tokens, heartbeats and billed spend.
- **Scores in this protocol are local predictions.** They come from the calibrated local scorer, not from the Arena worker.

**Command as launched** (from the runner's own checkout root):

```bash
python3 harness/hx_heldout.py --set warmup --arm sol --preset gpt-6.1-sol --effort medium \
  --rungs 1.0,2.0,2.85 --workers 4 --max-rounds 20 --brief-dir probe/oline-knowledge \
  --stop-at 90.5 --stop-rung 2.0 --rescue 4 --rescue-rung 2.0 --rescue-effort high
```

**What the runner runs per round.** It runs `agent.py` in a git worktree at `~/source/lra-ab/wu-hx`, checked out at the
runner checkout's `HEAD`. The worktree is where `harness/hwork/wu-sol*` and `probe/runs/wu-hx-sol-*` are written. The
`envs/` checkouts are symlinked into the worktree. Each resume round runs:

```bash
python3 harness/agent.py --model-preset gpt-6.1-sol --reasoning-effort medium --turns 40 --no-adaptive-turns \
  --max-tokens 4000 --budget-usd <rung> --budget-milestones 2.0 --workers 4 --work-root harness/hwork/wu-sol \
  --run-id wu-hx-sol-r<N> --brief-dir probe/oline-knowledge --problems <problems in this round>
```

Fresh sessions use the same command with these differences:

- `--work-root harness/hwork/wu-sol-fresh` and `--run-id wu-hx-sol-f<N>`
- for the rescue session: `--from-reference --brief restructure` and `--reasoning-effort high`

The runner's log, lineage and snapshots go to `probe/heldout/wu-hx-sol/` in the runner's own checkout.

## 4. Timeline and code versions

All times are UTC, from `probe/heldout/wu-hx-sol/jobs.log`. Every dollar figure in this section is billed (0.99 × list).
"Spend after" is the cumulative billed spend over all 15 problems.

| Round | Rung | Start → end | Sessions | agent.py | Mean after | Spend after |
|---|---|---|---|---|---|---|
| 1 | $1.00 | 10-11 20:00:21 → 20:50:55 | 15 resume (all from the reference) | `579e3634` | 84.37 | $5.88 |
| 2 | $1.00 | 20:50:55 → 21:23:50 | 12 resume + 3 fresh (f2) | `579e3634` | 85.68 | $9.78 |
| 3 | $1.00 | 21:23:50 → 21:40:36 | 10 resume + 2 fresh (f3) | `579e3634` | 85.80 | $11.33 |
| — | **$1.00 milestone** | 21:40:36 | mean 85.80, max $0.855 billed per problem | | | |
| 4 | $2.00 | 21:40:36 → 22:17:37 | 11 resume + 4 fresh (f4) | `579e3634` | 88.88 | $18.03 |
| 5 | $2.00 | 22:17:37 → 22:18:02 | stopped before any API call (fresh seeds archived as `wu-sol-fresh.aborted-wu-hx-sol-f5`, no spend) | — | — | $18.03 |
| — | pause | 22:17 → 23:20 | approved pause (63 min) to deploy the stuck-only rescue rule | | | |
| 8 | $2.00 | 23:20:14 → 23:47:51 | 11 resume + 4 fresh (f8) | `0672126b` | 89.31 | $22.57 |
| — | deploy | 23:37:52 | worktree → `08002e91` (runaway tool-call drop + bounded memgate waits). Processes already running keep the code they loaded. | | | |
| 9 | $2.00 | 23:47:51 → 00:10:02 | 13 resume | `08002e91` | 89.76 | $25.22 |
| — | **snapshot, submitted** | 23:52:47 | `reached89.5`: mean 89.51, total $23.18 billed, max $1.739 billed per problem | | | |
| — | brief addendum | 10-12 00:05:28 | Electromagnetism brief gains the option-B addendum (section 5) | | | |
| 10 | $2.00 | 00:10:02 → 00:20:21 | 6 resume | `08002e91` | 89.76 | $26.03 |
| 11 | $2.00 | 00:20:21 → 00:23:56 | 2 resume | `08002e91` | 89.76 | $26.24 |
| — | **$2.00 milestone** | 00:23:56 | mean 89.76, max $1.863 billed per problem | | | |
| 12 (f12) | rescue, cap $2.85 | 00:23:56 → 00:35:55 | 4 fresh RESTRUCTURE sessions, effort high; none adopted | `08002e91` | 89.76 | $28.46 |
| 13 | $2.85 | 00:35:55 → 01:09:34 | 15 resume. Credits ran out from 01:03:12: 6 sessions ended on HTTP 402 (`putnam_1964_b2` and `putnam_1995_a3` before their first turn) | `08002e91` | 90.47 | $31.84 |
| 14 | $2.85 | 01:09:34 → 01:34:27 | 14 resume, every request HTTP 402, nothing billed; runner stopped | `08002e91` | 90.47 | $31.84 |
| — | snapshot | 01:46:26 | `paused402`: mean 90.47, total $31.84 billed, max $2.621 billed per problem | | | |
| — | paused | 02:02:15 | OpenRouter arms paused; resume-on-credits watcher stopped | | | |

Notes on the timeline:

- **Missing round numbers.** Rounds 6 and 7 do not exist. On restart the runner numbers the next round from the run
  directories that already exist: four resume rounds plus three fresh rounds gives round 8. Round 12 is the rescue (`f12`).
- **Lines that are not real milestones.** The `MILESTONE $1.00 … 88.88` line at 23:20:14 is the restart re-printing the
  current state; the real $1.00 milestone is the 21:40:36 line (85.80). The `REPORT … 85.81` line at 21:46 comes from a separate
  `--report` invocation during round 4. The 23:20:25 note in `jobs.log` calls the $1 milestone 85.81, but the milestone line
  itself prints 85.80.
- **Round 14 lineage entries.** Every round-14 request failed with HTTP 402. Its zero-gain lineage entries were removed
  afterwards so the restart rule does not read them as stalled sessions. The backup is `lineage.json.bak-pre-402fix`.
- **Resume-on-credits watcher.** `probe/heldout/resume_on_credits.py` was armed at 01:47:24 to relaunch the runner when the
  OpenRouter balance reached $12. The team stopped it at 02:02:15.

**Code versions.** [CODE_VERSIONS.md](CODE_VERSIONS.md) has the details. The project's commit history is not part of
this repository; the run-relevant changes made during the run are included as two diffs in `code_history/`.

| Rounds | agent.py and scorer (project commit) | Evidence |
|---|---|---|
| 1–4, fresh f2, f3, f4 (and the aborted round 5) | `579e3634` | `jobs.log` 20:00:21 worktree line |
| 8 and fresh f8 | `0672126b` | `jobs.log` 23:20:14 worktree line. Both processes started at 23:20, before the 23:37:52 deploy. |
| 9, 10, 11, rescue f12, 13, 14 | `08002e91` | `jobs.log` 23:37:52 `DEPLOY` line. Round 9 is the first round launched after it. |

- **What changed between these commits.** `0672126b` is the direct child of `579e3634` and changes no run-relevant file.
  Only two later commits changed run-relevant code:
  - `f7d41ecf` changed the runner and the memory gate: `code_history/579e3634..f7d41ecf.diff`.
  - `08002e91` changed `agent.py` (the runaway tool-call drop): `code_history/f7d41ecf..08002e91.diff`.

  Rounds 1–8 therefore ran identical agent and scorer code. From round 9 on, the sessions also had the bounded memory-gate
  waits and the runaway tool-call drop.
- **The code in this folder** is the project's committed `HEAD` at staging time. Its run-relevant files equal `08002e91`
  except for edits made at staging (see the next bullet). A replication from this folder therefore runs the `08002e91`
  code from round 1. [CODE_VERSIONS.md](CODE_VERSIONS.md) shows how to reproduce the recorded sequence instead.
- **Edits made at staging.** Four files differ from their source commit, in comments, docstrings and help text only:
  `harness/agent.py`, `harness/leantools.py`, `harness/selftest.py` and `harness/hx_heldout.py`. The wording that changed
  referred to evaluation work outside this warm-up. Two further changes in `harness/hx_heldout.py` affect behaviour:
  - its `SETS` table holds only the `warmup` entry
  - `--set` defaults to `warmup`

  `probe/heldout/resume_on_credits.py` lost an account-balance figure from its docstring. No other logic changed.
- **Runner version.** `harness/hx_heldout.py` runs from the main checkout, not the worktree.
  - It was launched at 20:00:21 from `579e3634`.
  - It was restarted at 23:20:14 with the stuck-only rescue rule in the working copy. That rule was committed as
    `f7d41ecf` at 23:22:24 UTC, about two minutes after the restart (project history).
  - So the code of the running runner cannot be shown to be byte-identical to `f7d41ecf`.
  - The rescue at 00:23:56 used this rule.
- **Helper scripts.** `snapshot_watch.py`, `nostop_guard.py`, `resume_on_credits.py`, `verify_snapshot.py` and
  `optcheck_snapshot.py` also ran from the main checkout.
- **Origin of the submitted proofs** (the "From" column in section 1):
  - 7 proofs from code `579e3634`: r1 ×1, r2 ×1, r4 ×5
  - 6 proofs from code `0672126b`: r8 ×5, f8 ×1
  - 2 proofs from code `08002e91`: r9 ×2 (`substOldPostSubset` reached 92.00 at 23:50:37 and `extractedOldExprInVars`
    reached 93.82 at 23:52:17, both before the 23:52:47 snapshot)

## 5. Knowledge given to the model, and disclosure

The model was given knowledge from earlier research on **these same 15 warm-up problems**. The sources are listed below,
together with exactly what reached the model.

**1. Per-problem knowledge briefs.** These are the files `probe/oline-knowledge/<problem>.md`. They are passed with
`--brief-dir` and appended to every session's opening message.

They were built from earlier research lines of this project on these 15 problems: a Claude Opus 5.5 line, a GPT Astra
line and a GLM-5.3-Flash line. An earlier GPT-6.1 Sol line contributed only the Electromagnetism addendum (item 2). Each
brief contains:

- the union best on the problem, a landmark: score, tokens, heartbeats, and which line reached it
- each line's best score
- the problem's exchange rate: points per token and per 100 heartbeats
- the scorer's lexer rules
- the tail of the Opus 5.5 and GPT Astra lines' notes on that problem:
  - lever lists
  - tested edits with their measured outcomes
  - lists of failed attempts
  - lemma names that were confirmed, or that do not exist

**What the briefs contain, exactly.** No brief contains a complete proof. In places, though, the note tails quote short
Lean fragments or outline the structure of those lines' proofs.

- **`putnam_1964_b2.md`** is the clearest case. In a few lines it outlines the Opus 5.5 line's proof: the top-level tactic
  chain and the library lemmas it rewrites with, with two sub-proofs left out.
- **The brief headers** say "facts and skills only — NO proofs are given". Judge that claim against the files, which are
  the as-used copies.
- **The `putnam_1964_b2` landmark is unattributed.** Its brief credits the union best, 98.57 (45 tokens, 2,337
  heartbeats), to "the bounty compile () (bounty)" with an empty run id. Which line produced it cannot be verified from
  this repository.
- **`REST10.txt`** is a list of 10 problem names. Neither the runner nor `agent.py` reads it.

**Host-specific lines in the briefs.** Seven of the as-used briefs tell the model to put the original machine's absolute
`.elan/bin` path on `PATH`:

- `fold_advances_evaluation_poly`
- `putnam_1964_b2`, `putnam_1964_a4` and `putnam_1995_a3`
- `Fsub.Typing.progress`
- `Electromagnetism` (both the `.md` and the `.pre-addendum` copy)
- `SKI.parallelReduction_diamond`

The SKI brief also names a `lean_check.py` path in the original machine's main checkout. These hints were carried over
from earlier lines and kept verbatim for fidelity. `agent.py`'s shell already puts `~/.elan/bin` first on `PATH`. The SKI
path will not resolve on another host.

**2. Electromagnetism addendum (option B).** At 2026-10-12 00:05:28 UTC, after the submitted snapshot, the brief
for `Electromagnetism.ElectromagneticPotential.time_deriv_time_deriv_electricField_of_isExtrema` gained an addendum. The
text is in `probe/heldout/wu-electro-addendum-B.md`. It contains:

- an earlier GPT-6.1 Sol line's landmark on this problem: 339 tokens / 5,593 heartbeats, score 84.89
- a diagnosis: the gap to that landmark is mostly heartbeats
- 8 measured dead ends and 4 names that do not exist
- no technique and no proof text

Which version each session saw:

- The `.md` file in `probe/oline-knowledge/` ends with the addendum.
- The `.md.pre-addendum` file is the version used before 00:05:28.
- The trajectories confirm that the Electromagnetism sessions of r1, f2, f3, r4 and r8 saw the brief without the
  addendum. Round 13 was the only billed session that saw it; in that round the problem went from 73.89 to 83.24.
- The submitted snapshot (23:52:47) predates the addendum.

**3. Runner inputs taken from earlier lines.** These are scores only, and both are included in this folder. The runner
reads them from its own checkout, not from the worktree the sessions run in.

- **Targets: `leaderboard/problem_scores.json`.** The lineage and rescue rules use a per-problem target, the `union` field:
  the best score any earlier line had reached on the problem.
  - The values are those of project commit `280604e3`, the last change to that file before both runner launches (20:00:21
    and 23:20:14).
  - Whether the working copy at launch differed from that commit cannot be verified.
  - For `putnam_1964_b2` the file gives 97.87 while the brief gives 98.57. The problem was at 99.07 after round 1, above
    both, so the difference changes no decision.
- **Typical first-session scores: `harness/hwork/solknow/<problem>/state.json`.** The bad-draw test uses these. They are
  stubs holding only the first-session attempt scores of an earlier GPT-6.1 Sol + briefs line on each problem, with no
  proofs and no notes. `typical_first()` takes the best of them.
- **These inputs reproduce the recorded decisions.** We replayed the runner's restart rule over the recorded rounds, using
  the recorded outcomes:
  - With these two inputs, the predicted fresh-restart set equals the recorded one in all 10 decision rounds (1, 2, 3, 4,
    the aborted 5, 8, 9, 10, 11 and 13). The $2.00 rescue pick is also reproduced.
  - Without them, the runner falls back to target 100 for every problem and skips the bad-draw test. The fallback differs
    from the recorded fresh-restart sets in 9 of the 10 rounds.

**4. General, non-problem-specific knowledge built into the harness.**

- the system prompt and the token rules in `harness/agent.py`
- the technique cards in `harness/cards.py`, which "describe proof PATTERNS, never a warm-up problem"
- **the "five habits" block.** It is a short list of general habits mined from the Opus 5.5 and GPT Astra lines, for
  example letting `simp` discharge side conditions, writing each piece once, `fun_induction`, a cheap reducible pre-pass
  and syntactic closers.
  - The option `--closed-lessons` adds it to the first message and is **on by default** in this code.
  - It was on throughout this run: all 126 trajectory files contain it.
- the lemma search in `harness/lemma_search.py`

**5. Upstream project history.** For the 12 project rows, the opening message carries a precomputed `UPSTREAM` digest
(`harness/leantools.py`, `upstream_digest`). It shows the theorem as it stands at the head of the project's upstream clone
`envs/<project>.git-main`, and lists the commits that touched its file since the benchmark's pin. The opening message
also points the model at `git log -p` on that clone ("newer commits may contain a simplified version of this very proof").

- **This matters.** For example, the CCS digest reports an upstream proof of 180 tokens against the 251-token reference.
- **The upstream heads the run saw** are recorded in the digests (103 sessions): Strata `02f873ed7` (2026-10-05), CSLib
  `ea16de32` (2026-10-05), PhysLib `bae4db68` (2026-10-05) and ArkLib `35ddcaa83` (2026-10-04).
- `envs/pin_upstream.sh` pins the clones to these heads (section 6).
- The 3 PutnamBench rows get no digest.

**Disclosure.**

- **Not a cold start.** The run's API cost covers only this run's own model calls. It excludes the earlier research that
  produced the briefs, the five-habits block, the targets and the typical first-session scores: the Opus 5.5, GPT Astra,
  GLM-5.3-Flash and earlier Sol lines.
- **No proof was given as a starting point.** Every session began either from the reference proof or from this run's own
  stored best. The reference start covers all 15 round-1 sessions, and every fresh session starts at score 33.33. Item 1
  says what the briefs do contain.
- **The ledger note.** "No proofs reused" in `submit/ledger.jsonl` is the text as written when the submission was
  prepared. It is qualified by the `putnam_1964_b2` disclosure in item 1.
- **What is not measured here.** This run does not measure score or cost on problems without such briefs.

## 6. Environment setup (`envs/`)

**Platform of the recorded run.** All local scoring ran on one host, and `data/reference_heartbeats_local.json` was
measured there on 2026-10-06. The host:

- Linux on aarch64
- 20 cores and 121 GB RAM
- Python 3.13.9

**Prerequisites:**

- Linux
- `git`, `bash` and `curl`. Mathlib's `lake exe cache get` downloads with `curl`.
- **Python.** The tested version is 3.13.9, the one that ran the run. All 42 `.py` files in this folder also parse under
  Python 3.11; older versions are untested.
  - You need the `requests` package.
  - The `anthropic` package is optional and not used by this run's OpenAI-compatible path.
- ripgrep (`rg`), used by the lemma-name index and the lemma search
- `elan`, installed at `~/.elan/bin`, where the scripts look for it. elan fetches each Lean toolchain from the
  `lean-toolchain` files. The 15 environments use 10 distinct toolchains.
- **Disk.** About 90 GB for the `.lake` build directories: the sizes in `envs/manifest.json` sum to 90.3 GB. On top of that
  come the 10 toolchains under `~/.elan` and the git clones; neither was measured. Build time was not recorded.
- **A systemd user instance**, for the `systemd-run --user` commands in section 7. Enable lingering
  (`loginctl enable-linger <user>`) so that a multi-hour run survives logout.
- **RAM for several concurrent compiles.**
  - Each Lean process runs with `-M 16000` (`LRA_LEAN_MEMORY_MB`).
  - Each claims 8,000 MB in the memory gate (`LRA_MEMGATE_CLAIM_MB`) and waits until a further 8,000 MB reserve is also
    free (`LRA_MEMGATE_RESERVE_MB`).
  - The run used 4 workers.
- **Host paths with environment overrides:**
  - the lemma-search cache, `LRA_LEMMA_CACHE` (default `/tmp/lra-lemma-index`)
  - the memory-gate lock directory, `LRA_MEMGATE_DIR` (default `/tmp`, lock file `lra-memgate.lock`)

**Build steps**, in this order:

```bash
cd envs
bash setup_projects.sh        # blobless clones of Strata, CSLib, PhysLib, ArkLib + one worktree per pinned commit (creates envs/logs)
bash pin_upstream.sh          # detach each <project>.git-main clone at the upstream head the run saw (see below)
bash setup_mathlib.sh         # mathlib4 worktrees at the three PutnamBench pins + `lake exe cache get` (needs envs/logs)
bash build_strata.sh          # builds the warm-up modules at each pin
bash build_cslib.sh
bash build_physlib_arklib.sh
python3 manifest.py           # writes envs/manifest.json; every entry should report ok=True
cd ..
```

Scripts that build every module of each project are not included; the warm-up rows do not need them.

**Upstream clones (pinned).** The `envs/<project>.git-main` clones are not the benchmark pins. They are blobless clones with
the full commit history, and their head drives two things:

- the `UPSTREAM` digest in each opening message (section 5, item 5)
- what the model sees through `git log -p` / `git show`

`setup_projects.sh` clones each repository's current default branch. A clone made today shows later upstream proofs than
the run saw. `pin_upstream.sh` therefore fetches and detaches each clone at the head recorded in the run's digests:

| Clone | Upstream head the run saw | Date |
|---|---|---|
| `strata.git-main` | `02f873ed7a89099aacae18e7b78e74ca5d4ef8db` | 2026-10-05 |
| `cslib.git-main` | `ea16de32af9cd93796505668672297df9c422052` | 2026-10-05 |
| `physlib.git-main` | `bae4db68ef61fc01a190fd232f82d2ad6508164e` | 2026-10-05 |
| `arklib.git-main` | `35ddcaa83f683011f944f58904be779495a5709a` | 2026-10-04 |

Every session of the run saw these same four heads.

**The 15 environments.** These are the pins from each row's `version_info` in `data/benchmark_warmup.jsonl`. The primary
toolchain of a row is the newest one it lists.

| `envs/` directory | Repository commit | Toolchain | Rows |
|---|---|---|---|
| `strata-v4.26.0` | `451e5f04` | v4.26.0 | substOldPostSubset, extractedOldExprInVars, InitsUpdatesComm |
| `strata-v4.27.0` | `4348c65a` | v4.27.0 | InitsUpdatesComm |
| `strata-v4.29.1` | `384e2237` | v4.29.1 | InitsUpdatesComm |
| `cslib-v4.33.0-rc2` | `3aa9d441` | v4.33.0-rc2 | Fsub progress, SKI, CCS |
| `cslib-v4.32.0` | `197a7be6` | v4.32.0 | Fsub progress, SKI, CCS |
| `cslib-v4.31.0` | `8ea71c8d` | v4.31.0 | Fsub progress, SKI, CCS |
| `cslib-v4.30.0` | `c7944a9f` | v4.30.0 | SKI |
| `physlib-v4.32.0` | `c4843367` | v4.32.0 | variational calculus, Electromagnetism, WickAlgebra |
| `arklib-v4.31.0` | `c1712f6c` | v4.31.0 | fiberwise, fold_advances, interleaved |
| `arklib-v4.30.0` | `e6d77b18` | v4.30.0 | fiberwise, fold_advances, interleaved |
| `arklib-v4.29.0` | `de71a9df` | v4.29.0 | fiberwise, fold_advances, interleaved |
| `arklib-v4.28.0` | `673fa440` | v4.28.0 | fiberwise |
| `mathlib-v4.25.0` | `1ccd71f8` | v4.25.0 | putnam_1964_a4, putnam_1964_b2, putnam_1995_a3 |
| `mathlib-v4.26.0` | `2df2f015` | v4.26.0 | putnam_1964_a4, putnam_1964_b2, putnam_1995_a3 |
| `mathlib-v4.27.0` | `a3a10db0` | v4.27.0 | putnam_1964_a4, putnam_1995_a3 |

**Harness self-test: not runnable from this folder.** `harness/selftest.py` drives `agent.py` with a scripted local fake
model and makes no API calls. As staged, though, it cannot run:

- **It reads another line's work root.** It needs `harness/work/putnam_1964_b2/best.lean` and
  `harness/work/putnam_1964_a4/best.lean`, which are not in this folder, and some of its checks expect particular proof
  text in them.
- **It needs the built Lean environments**, and its upstream-digest check needs a CSLib clone whose head simplifies the CCS
  proof.
- **It needs `LRA_SELFTEST_OAI_ONLY=1`** when the `anthropic` package is not installed.

It is included as the record of what the harness was tested against, not as a step of the replication.

**Heartbeat calibration.** Local heartbeat scores divide by `data/reference_heartbeats_local.json`, which was measured on
the host above.

- On another host, especially another architecture, local heartbeat ratios may shift slightly. The re-verified mean of
  89.51 (section 7.1) is what that host gives; other hosts are untested.
- `python3 scorer/calibrate.py` re-measures the references and **overwrites** that file.
- For a replication, run it (if at all) before the base commit in section 7.2. The sessions read the committed copy in the
  worktree.

## 7. Commands

### 7.1 Re-verify the submitted snapshot (no API calls)

Run these from this `warmup/` folder after building `envs/`. They compile Lean, so a memory-capped unit is advisable
(`systemd-run --user --scope -p MemoryMax=48G …`).

```bash
S=probe/heldout/wu-hx-sol/snapshots/reached89.5-20261011T235247Z
cmp "$S/submission.jsonl" submit/candidates/sub06_closed_wu_sol_8951.jsonl    # identical files
python3 probe/heldout/verify_snapshot.py "$S" | tee /tmp/verify.log             # expects 15 x ok=True, all compat n/n, mean 89.51
python3 probe/heldout/optcheck_snapshot.py "$S" | tee /tmp/optcheck.log         # expects the result described in section 1
```

`verify_snapshot.py` rewrites `$S/verify.json`. Neither script writes to the bank or to any state.

### 7.2 Replicate the run

> **Warning: the model's `shell` tool is not a sandbox.**
>
> - It runs `bash -lc` in the problem's workspace as the account that runs the runner, with that account's login profile.
> - It is guarded only by a deny-list:
>   - no `rm`, `mv`, `chmod`, `sudo`, `pip`, `curl`, `wget` or `ssh`
>   - no URLs
>   - no `lake build`
>   - no `git checkout`, `commit` and similar commands
>   - no redirects outside the workspace
> - Reads are not restricted, so the model can `cat` any file that account can read. Lean snippets run with `lean_run`
>   are not filtered either.
>
> For a replication:
>
> - Run the runner under a dedicated account or in a container.
> - Move `submit/candidates/`, `submit/results/` and the recorded runs and snapshots out of that account's reach: another
>   account's private directory, or another machine.
> - Give that account nothing except its one API key.
>
> In the recorded run, the worktree was a checkout of the whole project repository. We checked all 515 `shell` calls in
> the trajectories: none read or wrote `bank/`, `submit/`, `probe/runs/`, `probe/heldout/` or another problem's workspace.

The runner creates a git worktree of its own checkout, so `warmup/` must be the **root of a git repository**.

**Common preparation**, as the run account. `$REC` stands for storage the run account cannot read.

```bash
git clone https://github.com/bobbercheng/lean-refactor-closed.git lra-closed
cp -a lra-closed/warmup ~/lra-wu && cd ~/lra-wu       # the runner's checkout root ("main checkout")
# build envs/ here, including envs/pin_upstream.sh (section 6); if you recalibrate heartbeats, do it now
# move the answer key and the recorded run out of reach (to $REC), then delete the lra-closed clone, which holds the same files:
#   submit/candidates/  submit/results/                                  (the submitted proofs and the worker table)
#   harness/hwork/wu-sol/  harness/hwork/wu-sol-fresh.*/  probe/runs/wu-hx-sol-*/   (recorded per-problem state and runs)
printf '%s\n' 'envs/mathlib4/' 'envs/mathlib-*/' 'envs/*.git-main/' 'envs/strata-*/' 'envs/cslib-*/' 'envs/physlib-*/' \
  'envs/arklib-*/' 'envs/logs/' 'harness/hwork/' '__pycache__/' > .gitignore
```

Notes on the preparation:

- **The env checkouts must be git-ignored.** The runner symlinks every ignored `envs/` entry into its worktree, and this
  also keeps tens of GB out of the commit.
- **Keep `harness/hwork/solknow/` and `leaderboard/problem_scores.json` in the main checkout.** These are the runner
  inputs (section 5, item 3); the runner reads them from there.
- **Commit order.** The sessions see only what is committed into the worktree. Any change to `data/` or the code (a
  recalibration, the optional code-sequence patches below) must therefore come before the base commit.
- **What stays visible.** Everything committed is visible to the model through `shell`.
  - `submit/ledger.jsonl` and these docs give per-problem scores and token counts of the recorded run, but no proof text.
  - Move the ledger to `$REC` too if the run should not see those numbers.

**API key and credit.**

- Create your own OpenRouter API key and store it at exactly
  `~/.config/vexorium/oline-keys/openrouter_openai_gpt-6.1-sol.key` (one line, mode 600).
  - The `gpt-6.1-sol` preset sets this path itself, so `--api-key-file` cannot move it.
  - Without that file the harness sends no valid key, no spend is recorded, and the runner stops after the first round.
- Fund the OpenRouter account for the remaining cap: at least **$42.75** for A or **$10.91** for B (billed). Otherwise
  sessions end on HTTP 402, as in rounds 13–14.

**A. From scratch** (empty state, original start conditions):

```bash
B=probe/oline-knowledge/Electromagnetism.ElectromagneticPotential.time_deriv_time_deriv_electricField_of_isExtrema.md
# move to $REC as well: probe/heldout/wu-hx-sol/ (recorded jobs.log, lineage.json, rescue.done, snapshots),
#   the as-used brief "$B" and the addendum text probe/heldout/wu-electro-addendum-B.md; then:
cp "$B.pre-addendum" "$B"   # the brief as it was when the run started
# optional: patch agent.py and scorer/memgate.py back to the rounds 1-8 code (CODE_VERSIONS.md, "Reproducing the recorded sequence")
git init -q && git add -A && git commit -qm "warm-up replication base"
mkdir -p ~/source/lra-ab
systemd-run --user --unit lra-hx-warmup -p MemoryMax=48G -p MemoryHigh=44G --working-directory="$PWD" -E PATH -E HOME \
  python3 harness/hx_heldout.py --set warmup --arm sol --preset gpt-6.1-sol --effort medium \
  --rungs 1.0,2.0,2.85 --workers 4 --max-rounds 20 --brief-dir probe/oline-knowledge \
  --rescue 4 --rescue-rung 2.0 --rescue-effort high
# optional, the same watcher that produced the submitted snapshot (start it once the runner has created probe/heldout/wu-hx-sol/):
python3 probe/heldout/snapshot_watch.py --root ~/source/lra-ab/wu-hx/harness/hwork/wu-sol \
  --out probe/heldout/wu-hx-sol --threshold 89.5 --interval 60 --max-hours 10
```

Notes for a from-scratch run:

- **Early stop rule.** The command above leaves it out. The as-launched command in section 3 includes it, but in this run
  the rule could not fire (section 3).
- **Worktree path.** The runner always uses `~/source/lra-ab/wu-hx` as its worktree. If that path already exists as a
  worktree of another repository, the launch fails at the worktree checkout, before any API call. Move it aside first.
- **Code.** Without the optional patches, every round runs the `08002e91` agent code: the runaway tool-call drop and the
  bounded memory-gate waits. The recorded rounds 1–8 ran without them (section 4). The runner itself is the version
  with the stuck-only rescue rule, as the recorded rescue used.
- **Electromagnetism addendum.** To reproduce it, copy the as-used brief from `$REC` over `$B` in the **worktree**,
  `~/source/lra-ab/wu-hx/probe/oline-knowledge/`, after the $2.00 milestone. The sessions read briefs from the worktree.
  In the recorded run, the first Electromagnetism session to see the addendum was in round 13.
- **Runner inputs.** They are included (section 5, item 3). With them, the replayed restart rule reproduces every recorded
  fresh-restart decision and the rescue pick. A live replication still diverges as soon as a session scores differently.
- **Upstream clones.** Run `envs/pin_upstream.sh` (section 6). Unpinned clones change the `UPSTREAM` digest and the git
  history the model sees.
- **Variation.** Model sampling is not deterministic, so a replication reproduces the protocol and spend bounds, not the
  exact proofs.
- **Spend ceiling.** At most 15 × $2.85 = $42.75 billed. The recorded run spent $23.18 billed up to the submitted snapshot
  and $31.84 billed up to the pause.

**B. Continue the paused run** to the $2.85 cap, as intended:

```bash
# keep probe/heldout/wu-hx-sol (lineage.json, rescue.done, jobs.log) in place; keep the as-used briefs
git init -q && git add -A && git commit -qm "warm-up continuation base"
mkdir -p ~/source/lra-ab && git worktree add --detach ~/source/lra-ab/wu-hx HEAD
mkdir -p ~/source/lra-ab/wu-hx/harness/hwork ~/source/lra-ab/wu-hx/probe/runs
# copy the recorded state back from $REC into the worktree (the run's own state; submit/ stays out of reach):
#   wu-sol/  wu-sol-fresh.*/   ->  ~/source/lra-ab/wu-hx/harness/hwork/
#   wu-hx-sol-*/               ->  ~/source/lra-ab/wu-hx/probe/runs/
# then launch the same systemd-run command as in A (no early stop rule)
```

How the continuation behaves:

- The runner resumes the $2.85 rung. Fourteen problems are still eligible; `fundamental_theorem_of_variational_calculus'`,
  at $2.62 billed, is within $0.30 of the cap.
- Spend is bounded by 15 × $2.85 − $31.84 = **$10.91** more, billed.
- `rescue.done` prevents a second rescue.
- It runs the `08002e91` code, as the recorded rounds 9–14 did.

**Report.** `python3 harness/hx_heldout.py --set warmup --arm sol --rungs 1.0,2.0,2.85 --report` appends a `REPORT` line
to `jobs.log`, computed from the worktree's state. In this copy `--set` defaults to `warmup`, the only entry in `SETS`.

### 7.3 How the file was uploaded

The upload went through the Arena's Gradio API, using `submit/upload.py`. The ledger was kept with `submit/ledger.py`.

| Step | Tool | Recorded in |
|---|---|---|
| register | `ledger.py register … --predictions submit/candidates/sub06_closed_wu_sol_8951.predictions.json` | ledger line `prepared` 2026-10-12T01:11:18Z |
| send | `upload.py --user Vexorium-Agent --key-file <your key file> send --file submit/candidates/sub06_closed_wu_sol_8951.jsonl --track closed --new-user` | ledger line `sent` 01:20:23Z |
| fetch results | `upload.py view`, then `parse_view.py` | the worker table `submit/results/sub06-closed-8951.worker.json` |
| scored | `ledger.py scored` | ledger line `scored` 01:21:53Z, `worker_combined` 89.46 |

`--new-user` is for a username's first upload only: the key the Space issues is saved to `--key-file` with mode 600 and
is never printed. The exact flags used for each step are not recorded in this folder beyond what the ledger shows.

**Reading the ledger note.** The `note` field was written when the submission was prepared and copied unchanged into the
`sent` and `scored` lines. Three parts of it need context:

- **"Not uploaded: needs a go decision."** This was true at preparation and is stale in the `sent` and `scored` lines.
- **"Expected worker ~89.48 … -> #2 behind 89.53."** This is the expected outcome, written at preparation. It was not a
  selection rule: the file is the snapshot taken when the run's local mean first reached 89.5 (section 1).
- **"No proofs reused".** This is qualified by the `putnam_1964_b2` disclosure in section 5, item 1.

## 8. Where every artifact lives

| Path | Contents |
|---|---|
| `data/benchmark_warmup.jsonl`, `data/benchmark_heartbeats.jsonl` | the 15 official warm-up rows and their reference heartbeats |
| `data/reference_heartbeats_local.json` | reference heartbeats measured with the local counter on the host in section 6 (calibration) |
| `harness/agent.py`, `harness/hx_heldout.py` | the agent harness and the budget-ladder runner |
| `harness/*.py`, `harness/tools/` | tool backends: `leantools`, `lemma_search`, `goals`, `mine`, `normalize`, `profile`, `cards`, and the CLI wrappers |
| `harness/selftest.py`, `harness/selftest_fixtures/` | the harness self-test and one fixture; not runnable from this folder (section 6) |
| `llm/` | `openai_compat.py` (the client used here), `zai_client.py` (not used by this run), `prompts.py` |
| `scorer/` | compile, heartbeat measurement, tokenizer, forbidden-construct filter, score formulas, memory gate, calibration |
| `probe/verify_candidates.py`, `bank/store.py` | `newest_first` toolchain ordering (imported by `agent.py`); the proof bank, read only for bank-sync on another work root and not used by this run |
| `envs/` | environment build scripts, `pin_upstream.sh` (upstream clone pins, section 6) and `manifest.json` (the built checkouts are not included) |
| `code_history/` | the two run-relevant diffs made during the run (section 4, [CODE_VERSIONS.md](CODE_VERSIONS.md)) |
| `leaderboard/problem_scores.json` | runner input: per-problem union target scores only (section 5, item 3) |
| `harness/hwork/solknow/<problem>/state.json` | runner input: first-session scores of an earlier Sol + briefs line, no proofs or notes (section 5, item 3) |
| `probe/oline-knowledge/` | the 15 knowledge briefs as used, plus the Electromagnetism `.pre-addendum` copy |
| `probe/heldout/wu-electro-addendum-B.md` | the addendum text |
| `probe/heldout/wu-hx-sol/jobs.log` | the run's event log (rounds, milestones, snapshots, deploys, pauses) |
| `probe/heldout/wu-hx-sol/lineage.json` (+ `.bak-pre-gains`, `.bak-pre-402fix`) | per-problem session count, fresh-restart count, per-rung gains |
| `probe/heldout/wu-hx-sol/rescue.done` | rescue marker (2026-10-12T00:35:55Z) |
| `probe/heldout/wu-hx-sol/wu-hx-sol-r*.log`, `wu-hx-sol-f*.log` | per-round agent stdout. `r5`/`f5` are empty (aborted round). |
| `probe/heldout/wu-hx-sol/snapshots/reached89.5-20261011T235247Z/` | the submitted snapshot: `submission.jsonl` and `scores.json` (written by `snapshot_watch.py`), `verify.json`, `verify.log`, `optcheck.log` |
| `probe/heldout/wu-hx-sol/snapshots/paused402-20261012T014625Z/` | state at the pause: `submission.jsonl`, `scores.json` (not submitted, not verified). **Produced ad hoc** (see below). |
| `probe/heldout/*.py` | `snapshot_watch`, `nostop_guard`, `resume_on_credits`, `verify_snapshot`, `optcheck_snapshot` |
| `probe/runs/wu-hx-sol-r{1,2,3,4,8,9,10,11,13,14}/`, `probe/runs/wu-hx-sol-f{2,3,4,8,12}/` | one directory per round (details below) |
| `harness/hwork/wu-sol/<problem>/` | final main-lineage workspace per problem: `state.json`, `notes.md`, `best.lean`, `candidate.lean`, variants and drafts |
| `harness/hwork/wu-sol-fresh.done-wu-hx-sol-f{2,3,4,8,12}/` | archived fresh lineages (never resumed) |
| `harness/hwork/wu-sol-fresh.aborted-wu-hx-sol-f5/` | round-5 fresh seeds, never run (no spend) |
| `submit/` | upload and ledger tools, the submitted file and its predictions (**produced ad hoc**, see below), the worker table, the ledger |

**Two files were produced ad hoc.** No script in this folder writes them: an interactive session made each with an inline
script.

- **`submit/candidates/sub06_closed_wu_sol_8951.predictions.json`.** This holds per-row `L`, `H_pred`, `Z`, `score` and
  `hb_local`, plus `_predicted_combined` 89.51.
  - Its inputs were the snapshot's `verify.json` and `data/reference_heartbeats_local.json`.
  - `ledger.py register --predictions` read it into the ledger.
- **`snapshots/paused402-20261012T014625Z/scores.json`.** It was written from the per-problem state files at the pause.
  - It lacks the `spend_mean` field that `snapshot_watch.py` always writes.
  - Its figures agree with the state files exactly ([BUDGET.md](BUDGET.md)).

Each round directory under `probe/runs/` contains:

- `trajectories/<problem>.jsonl.gz`: the full per-message trajectory. It starts with a header (model, effort, system
  prompt, tools, best at start). Then come every message exactly as sent and received, one `turn` line per billed call
  (tokens, `cost`, `best_so_far`), and events (`budget_milestone`, `api_error`, `end`).
- `turns.jsonl`: a thin per-turn log.
- `verified.jsonl`: every compiling candidate with tokens, heartbeats, compatibility and score.
- `summary.json`: per-session summary.

In total there are 126 sessions, 110 of them with at least one billed call, and 2,208 billed calls. The `cost` values in
the trajectories sum, per problem, to each `state.json` `api_spend` to within $0.00001. The run total is $31.838659 from
the trajectories against $31.838668 from the state files.

**What was changed in the trajectories.** Only the 20 `api_error` lines were changed: the HTTP 402 errors of rounds 13
(6 files) and 14 (14 files).

- Their error text carried an OpenRouter key-management URL with the key's identifier. At staging that identifier was
  replaced with `<key-id>`. It was an identifier, not the secret key.
- Nothing else in the trajectories was changed. The `turn` lines are as recorded, so every spend sum above and in
  [BUDGET.md](BUDGET.md) reproduces exactly.

**Paths of the original machine.** Absolute paths under the original account's home directory appear in several places,
left as recorded:

- the trajectories
- `jobs.log`
- some briefs (section 5)

**Problem-name mapping.** Work directories and trajectory file names replace characters outside `[A-Za-z0-9_.-]` with `_`.
For example `fundamental_theorem_of_variational_calculus'` becomes `fundamental_theorem_of_variational_calculus_`, and
`FieldSpecification.WickAlgebra.ι_timeOrderF_…` becomes `FieldSpecification.WickAlgebra.__timeOrderF_…`.

## 9. Credentials

This repository contains no credentials. Create your own key files where you need them:

| File | Used by |
|---|---|
| `~/.config/vexorium/oline-keys/openrouter_openai_gpt-6.1-sol.key` (exactly this path; the preset overrides `--api-key-file`) | the `gpt-6.1-sol` preset in `harness/agent.py`, and `probe/heldout/resume_on_credits.py` |
| `~/.config/vexorium/lra_submission_key` (or any path given with `--key-file`) | `submit/upload.py` |

`harness/agent.py` and `llm/zai_client.py` also name key files for other endpoints and presets. This run does not use them.
The account that runs the model should hold the one OpenRouter key and nothing else (section 7.2).

**Credit.** The OpenRouter account needs credit for the remaining cap: at least $42.75 for a from-scratch run, or $10.91
to continue (billed). Otherwise sessions end on HTTP 402, as in rounds 13–14.

## 10. Facts that cannot be verified from this folder

- **Leaderboard rank.** Rank #2 with 89.53 above and 89.38 below comes from the project commit log. The ledger has
  `leaderboard_rank: null`.
- **Billing reconciliation.** The statement that the OpenRouter account's billing matches the meter to the cent is reported
  by the team. No billing export is included.
  - The meter counts every call that returned usage.
  - A transport failure that the harness retried is not logged. If the provider billed such a call, it would be missing
    from the meter.
- **Commit times and parentage.** The commits run `579e3634` → `0672126b` → `f7d41ecf` → `08002e91`, each the direct
  child of the one before. The commit times are 20:00:15, 20:46:20, 23:22:24 and 23:36:43 UTC on 2026-10-11. Both facts
  come from the project history, which is not in this folder.
  - `jobs.log` records `579e3634`, `0672126b` and `08002e91`.
  - The diffs in `code_history/` name `f7d41ecf`.
- **The runner's code after the 23:20:14 restart.** It was the working copy two minutes before `f7d41ecf` was committed.
  Its byte-identity with `f7d41ecf` cannot be shown.
- **Runner unit settings.** The memory limits of the original runner unit are not recorded. The systemd settings shown in
  section 7.2 are the ones the relaunch helpers (`nostop_guard.py`, `resume_on_credits.py`) use.
- **Runner inputs at launch.** The included targets are the values of project commit `280604e3`. Whether the working copy
  at launch differed cannot be verified. These values do reproduce every recorded decision (section 5, item 3).
- **Platform.** The host details in section 6 are reported by the team. Heartbeat ratios on other architectures are
  untested.
