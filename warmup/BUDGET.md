# API spend of the warm-up GPT-6.1 Sol run

This file gives per-problem OpenRouter spend at two points:

- **the submitted snapshot**, 2026-10-11 23:52:47 UTC
- **the pause**: the runner stopped at 01:34 UTC on 2026-10-12, and the state was snapshotted at 01:46:26

All figures were computed from these files:

- `probe/heldout/wu-hx-sol/snapshots/*/scores.json`
- the per-problem `state.json` files in `harness/hwork/wu-sol/`
- the `cost` field of every call that returned usage, in `probe/runs/wu-hx-sol-*/trajectories/*.jsonl.gz`

Paths are relative to `warmup/`. The run itself is described in [README.md](README.md).

## How spend is metered

- **The meter.** Each problem's `api_spend` in `state.json` is the sum of the cost OpenRouter reports (`usage.cost`) for
  every model call on that problem that returned usage. It covers every session and lineage of the problem:
  - Main lineage: resume rounds.
  - Fresh and rescue lineages: they are seeded with the problem's spend so far, and the larger value is carried back.
    Both lineages therefore count against one meter and one cap (`fresh_round` in `harness/hx_heldout.py`).
- **Billed versus list price.** The meter records OpenRouter's billed cost, which is 0.99 × list price. In this file,
  **list = billed / 0.99**.
  - The price table in `harness/agent.py` (`MODEL_PRESETS["gpt-6.1-sol"]`) lists GPT-6.1 Sol at $2.50 per 1M uncached
    input tokens, $10.00 per 1M output tokens and $0.10 per 1M cache-read tokens.
  - A comment beside that table records that a fit over 1,493 billed Sol turns gave exactly 0.99 × those rates.
  - As a cross-check, the column "list (tokens)" recomputes list price from each call's own token counts. It agrees with
    billed / 0.99 to within $0.0004 per problem.
- **Every call that returned usage is counted**, billed at 0.99 × list.
  - Up to the submitted snapshot: 1,624 calls.
  - Up to the pause: 2,208 calls. Each has a `turn` line with a `cost` value in the trajectories.
  - The per-call `cost` values in the trajectories add up to each problem's `api_spend` to within $0.00001. The run total
    is $31.838659 from the trajectories against $31.838668 from the state files.
  - The 20 requests that failed with HTTP 402 (rounds 13 and 14) returned no usage, and the meter recorded nothing for
    them.
  - **Retried transport failures are not logged.** `harness/agent.py` retries a call that fails in transport (connection
    reset, timeout, decode error) up to 6 attempts in all. It logs an `api_error` only when the last attempt fails. A
    request the provider billed but the client never received would therefore be missing from the meter.
  - The team checked that the OpenRouter account's billing reconciles with this meter to the cent. No billing export
    is included in this folder.
- **The cap is a hard bound.** Each session runs with `--budget-usd` set to the current rung: $1.00, then $2.00, then
  $2.85.
  - Before every turn, `agent.py` reserves the worst case of the next turn: the whole context billed as uncached input
    plus the full output cap, at list prices, and at least 1.25 × the session's costliest turn.
  - If spend + reserve would exceed the cap, the session ends before the call.
  - The cap applies to the metered (billed) spend. The highest cap, $2.85 billed, equals $2.879 at list price.
  - When the submitted snapshot was taken, the run was on the $2.00 rung.

## At the submitted snapshot (2026-10-11 23:52:47 UTC)

Source: `snapshots/reached89.5-20261011T235247Z/scores.json`, plus trajectory calls up to that time.

| # | Problem | Local score | Billed calls | Billed $ | List $ (billed / 0.99) | List $ (tokens) |
|---|---|---|---|---|---|---|
| 1 | `CallElimCorrect.substOldPostSubset` | 92.00 | 108 | 1.7186 | 1.7360 | 1.7361 |
| 2 | `CallElimCorrect.extractedOldExprInVars` | 93.82 | 130 | 1.5560 | 1.5717 | 1.5719 |
| 3 | `Core.InitsUpdatesComm` | 89.14 | 109 | 1.5703 | 1.5862 | 1.5864 |
| 4 | `fundamental_theorem_of_variational_calculus'` | 91.58 | 100 | **1.7386** | **1.7561** | **1.7563** |
| 5 | `Electromagnetism.ElectromagneticPotential.time_deriv_time_deriv_electricField_of_isExtrema` | 73.89 | 91 | 1.7015 | 1.7187 | 1.7188 |
| 6 | `FieldSpecification.WickAlgebra.ι_timeOrderF_superCommuteF_eq_time` | 83.46 | 117 | 1.3545 | 1.3682 | 1.3684 |
| 7 | `Cslib.LambdaCalculus.LocallyNameless.Fsub.Typing.progress` | 85.55 | 105 | 1.6376 | 1.6542 | 1.6543 |
| 8 | `Cslib.SKI.parallelReduction_diamond` | 76.75 | 83 | 1.4726 | 1.4875 | 1.4876 |
| 9 | `Cslib.CCS.bisimilarity_congr_choice` | 87.03 | 82 | 1.6676 | 1.6845 | 1.6846 |
| 10 | `Binius.BinaryBasefold.fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius` | 90.97 | 145 | 1.3008 | 1.3139 | 1.3141 |
| 11 | `Binius.BinaryBasefold.fold_advances_evaluation_poly` | 93.62 | 165 | 1.3452 | 1.3588 | 1.3590 |
| 12 | `interleaved_affine_gaps_imply_tensor_gaps` | 92.88 | 95 | 1.3545 | 1.3682 | 1.3683 |
| 13 | `putnam_1964_a4` | 96.82 | 84 | 1.6440 | 1.6606 | 1.6607 |
| 14 | `putnam_1964_b2` | 99.26 | 117 | 1.3958 | 1.4099 | 1.4100 |
| 15 | `putnam_1995_a3` | 95.88 | 93 | 1.7175 | 1.7348 | 1.7349 |
| | **Total** | mean **89.51** | **1,624** | **23.1751** | **23.4092** | **23.4116** |
| | **Mean per problem** | | | 1.5450 | 1.5606 | |
| | **Max per problem** | | | **1.7386** | **1.7561** | **1.7563** |
| | **Min per problem** | | | 1.3008 | 1.3139 | |

**Maximum per problem.** The highest spend was $1.7386 billed, on `fundamental_theorem_of_variational_calculus'`. At list
price that is $1.7561 by billed / 0.99, or $1.7563 when recomputed from token counts. The ledger note in
`submit/ledger.jsonl` quotes the $1.7563 figure. Either way it is **at most $1.76 per problem at list price**.

At this point no problem had reached $2. Every `budget_milestones` field in `scores.json` is empty.

## At the pause (snapshot `paused402-20261012T014625Z`)

Spend has not changed since round 13 ended at 01:09:34. Round 14 (01:09–01:34) got HTTP 402 on every request and was not
billed. The state files agree with `scores.json` exactly. That `scores.json` was written ad hoc from the state files
by an interactive session, not by `snapshot_watch.py` (README section 8).

The last column shows the `budget_milestones["2"]` record from `state.json`: billed spend when $2 was crossed / best score
at that moment / session / time (UTC).

| # | Problem | Local score | Billed calls | Billed $ | List $ (billed / 0.99) | List $ (tokens) | Left to $2.85 cap (billed) | $2 crossed |
|---|---|---|---|---|---|---|---|---|
| 1 | `CallElimCorrect.substOldPostSubset` | 92.00 | 137 | 2.0313 | 2.0518 | 2.0520 | 0.8187 | 2.0058 / 92.00 / r13 / 00:45 |
| 2 | `CallElimCorrect.extractedOldExprInVars` | 94.49 | 174 | 1.9712 | 1.9911 | 1.9914 | 0.8788 | not crossed |
| 3 | `Core.InitsUpdatesComm` | 89.14 | 145 | 2.5498 | 2.5755 | 2.5758 | 0.3002 | 2.0069 / 89.08 / f12 / 00:29 |
| 4 | `fundamental_theorem_of_variational_calculus'` | 91.58 | 133 | **2.6215** | **2.6480** | **2.6482** | 0.2285 | 2.0014 / 90.70 / f12 / 00:28 |
| 5 | `Electromagnetism.ElectromagneticPotential.time_deriv_time_deriv_electricField_of_isExtrema` | 83.24 | 125 | 2.1345 | 2.1560 | 2.1562 | 0.7155 | 2.0016 / 73.89 / r13 / 00:49 |
| 6 | `FieldSpecification.WickAlgebra.ι_timeOrderF_superCommuteF_eq_time` | 86.74 | 201 | 2.2642 | 2.2871 | 2.2874 | 0.5858 | 2.0011 / 86.57 / r13 / 00:44 |
| 7 | `Cslib.LambdaCalculus.LocallyNameless.Fsub.Typing.progress` | 85.76 | 160 | 2.5160 | 2.5414 | 2.5416 | 0.3340 | 2.0075 / 81.25 / f12 / 00:30 |
| 8 | `Cslib.SKI.parallelReduction_diamond` | 76.91 | 121 | 2.0748 | 2.0958 | 2.0960 | 0.7752 | 2.0029 / 76.91 / r13 / 00:51 |
| 9 | `Cslib.CCS.bisimilarity_congr_choice` | 87.03 | 129 | 2.5470 | 2.5727 | 2.5729 | 0.3030 | 2.0051 / 85.42 / f12 / 00:29 |
| 10 | `Binius.BinaryBasefold.fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius` | 91.52 | 185 | 1.8996 | 1.9188 | 1.9191 | 0.9504 | not crossed |
| 11 | `Binius.BinaryBasefold.fold_advances_evaluation_poly` | 93.62 | 230 | 1.9044 | 1.9236 | 1.9240 | 0.9456 | not crossed |
| 12 | `interleaved_affine_gaps_imply_tensor_gaps` | 92.99 | 133 | 1.9024 | 1.9216 | 1.9218 | 0.9476 | not crossed |
| 13 | `putnam_1964_a4` | 96.82 | 97 | 1.9770 | 1.9970 | 1.9971 | 0.8730 | not crossed |
| 14 | `putnam_1964_b2` | 99.26 | 145 | 1.7276 | 1.7450 | 1.7453 | 1.1224 | not crossed |
| 15 | `putnam_1995_a3` | 95.88 | 93 | 1.7175 | 1.7348 | 1.7349 | 1.1325 | not crossed |
| | **Total** | mean **90.47** | **2,208** | **31.8387** | **32.1603** | **32.1636** | **10.9113** | 8 problems past $2 |
| | **Mean per problem** | | | 2.1226 | 2.1440 | | | |
| | **Max per problem** | | | **2.6215** | **2.6480** | **2.6482** | | |
| | **Min per problem** | | | 1.7175 | 1.7348 | | | |

**`$2 crossed` in the rescue rows.** For the four rows crossed in the rescue session `f12`, the recorded "best score at
that moment" is the best of the fresh rescue lineage. That lineage started from the reference proof. The problem's main
best at the same moment was higher:

| Problem | Recorded (f12 lineage) | Main best at that moment |
|---|---|---|
| `Core.InitsUpdatesComm` | 89.08 | 89.14 |
| `fundamental_theorem_of_variational_calculus'` | 90.70 | 91.58 |
| `Cslib.LambdaCalculus.LocallyNameless.Fsub.Typing.progress` | 81.25 | 85.55 |
| `Cslib.CCS.bisimilarity_congr_choice` | 85.42 | 87.03 |

The f12 lineage was not adopted for any of them.

**Maximum per problem.** At the pause the highest spend was $2.621 billed ($2.648 at list price), again on
`fundamental_theorem_of_variational_calculus'`. This is below the $2.85 billed hard cap.

**Unfinished budget.** The run was meant to climb every problem to the $2.85 cap. At most 15 × $2.85 − $31.84 = **$10.91**
more could have been spent.

**The 90.47 snapshot.** The pause-point mean of 90.47 is a local prediction. That snapshot was not submitted and has no
verify run.

## Spend and score at the run's milestones

Values below are from `probe/heldout/wu-hx-sol/jobs.log`, rounded as logged. Every dollar figure in this table is billed
(list = billed / 0.99). The pause-point mean per problem was computed from `scores.json`.

| Point | Time (UTC) | Local mean | Total billed | Mean per problem (billed) | Max per problem (billed) |
|---|---|---|---|---|---|
| $1.00 milestone (after round 3) | 10-11 21:40:36 | 85.80 | $11.33 | $0.755 | $0.855 |
| Submitted snapshot (during round 9) | 23:52:47 | 89.51 | $23.18 | $1.545 | $1.739 |
| $2.00 milestone (after round 11) | 10-12 00:23:56 | 89.76 | $26.24 | $1.750 | $1.863 |
| After the rescue session (f12) | 00:35:55 | 89.76 | $28.46 | $1.897 | $2.325 |
| Pause (spend frozen since 01:09:34) | 01:46:26 | 90.47 | $31.84 | $2.123 | $2.621 |

## Token totals

These totals come from the trajectory `turn` lines. No cache writes were reported.

| | Billed calls | Input tokens | of which cache read | Output tokens | List $ (tokens) |
|---|---|---|---|---|---|
| Up to the submitted snapshot | 1,624 | 48,813,258 | 45,796,643 | 1,129,040 | 23.4116 |
| Up to the pause | 2,208 | 64,600,434 | 60,381,438 | 1,557,794 | 32.1636 |

How the pause-point list cost of $32.1636 breaks down (components rounded to 4 decimals):

- uncached input: 4,218,996 tokens × $2.50 per 1M = $10.5475
- cache reads: 60,381,438 tokens × $0.10 per 1M = $6.0381
- output: 1,557,794 tokens × $10.00 per 1M = $15.5779

## What these figures do not include

- **Earlier research. This is not a cold-start cost.** The figures exclude the earlier research lines on these same 15
  problems: Claude Opus 5.5, GPT Astra, GLM-5.3-Flash and earlier GPT-6.1 Sol lines. Their results reached this run in
  four ways:
  - **The per-problem knowledge briefs.** These hold landmark numbers, lever lists and lists of failed attempts. In places
    they also hold short Lean fragments and proof-structure outlines (for example `putnam_1964_b2`). They contain no
    complete proofs.
  - **The "five habits" block.** It is a short list of general habits mined from the Opus 5.5 and GPT Astra lines.
    `--closed-lessons` is on by default in this code, so the block was in every session's first message.
  - **The runner's per-problem targets.** These are scores only.
  - **The typical first-session scores.** These are scores only.

  See README section 5.
- **Local compute.** Lean compiles, the lemma search and the verification and upload steps make no model API calls.
- **Failed requests.**
  - The 20 HTTP 402 requests returned no usage and were not billed.
  - Transport failures that were retried are not logged (see "How spend is metered").

## Recompute

Run this from `warmup/`. It needs Python 3 and no extra packages:

```bash
python3 - <<'EOF'
import glob, gzip, json
snaps = {"submitted": "reached89.5-20261011T235247Z", "pause": "paused402-20261012T014625Z"}
cut = {"submitted": "2026-10-11T23:52:47Z", "pause": "9999"}
calls = [(e["t"], e) for f in glob.glob("probe/runs/wu-hx-sol-*/trajectories/*.jsonl.gz")
         for e in map(json.loads, gzip.open(f, "rt")) if e.get("type") == "turn"]
for k, d in snaps.items():
    s = json.load(open(f"probe/heldout/wu-hx-sol/snapshots/{d}/scores.json"))["problems"]
    billed = [p["spend"] for p in s.values()]
    sel = [e for t, e in calls if t <= cut[k]]
    tok_list = sum(((e["input_tokens"] - e["cache_read"]) * 2.50 + e["cache_read"] * 0.10 + e["output_tokens"] * 10.0) / 1e6 for e in sel)
    print(f"{k}: calls {len(sel)}, billed total {sum(billed):.4f}, list total {sum(billed)/0.99:.4f} (tokens {tok_list:.4f}), "
          f"max billed {max(billed):.4f} = list {max(billed)/0.99:.4f}")
EOF
```

Expected output:

```
submitted: calls 1624, billed total 23.1751, list total 23.4092 (tokens 23.4116), max billed 1.7386 = list 1.7561
pause: calls 2208, billed total 31.8387, list total 32.1603 (tokens 32.1636), max billed 2.6215 = list 2.6480
```
