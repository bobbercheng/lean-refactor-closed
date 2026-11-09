# Results and runs: closed-source LLM track (team Vexorium)

The record behind the summary in [`README.md`](README.md): our final upload, every closed-track upload, and our earlier warm-up
pipelines. The disclosures for these results are in [`DISCLOSURES.md`](DISCLOSURES.md).

## Final result

**Our final closed-track upload is `sub41` (2026-11-04 10:27 UTC): leaderboard score 86.31 (L 77.07, H 81.86, Z 100), eighth on the
closed-track leaderboard at the deadline (2026-11-04 11:59 UTC).**

| | |
|---|---|
| Proofs | the merged output of our closed official run 3 (commit `402c44d2`, from the seed proofs, within the $3 cap per problem; stored mean 86.0088 on our meter), then two passes of the model-free post-step in version v4su (every version-4 op except the kernel-skip op `kskip`): stored mean 86.3092 on our meter. The upload carries no `set_option` of any kind (no `debug.skipKernelTC`) |
| Code | the code ZIP we submitted with it, sha256 `abc1b0e29dcd29d37ddd8889f35265d57f5233f9310cb3eca8882d672fec877a`: its code and docs are the `final/` of the tag [`closed-final-sub41-20261104`](https://github.com/bobbercheng/lean-refactor-closed/tree/closed-final-sub41-20261104) (there the code files keep the export's comment redactions and one example file is withheld, the ZIP has the exact files). The older tag `closed-final-run3-postv4su-20261104` has the same code with the docs of a three-pass variant that we did not upload |
| All uploads | every closed upload, warm-up and final benchmark, is in the section "Our closed-track uploads" below |

## What this repository holds

| Folder | What it holds |
|---|---|
| [`final/`](final/) | The closed-track final as one self-contained package: the code, the session container, the environment installer and the one command that turns a benchmark rows file into the upload file. Start with [`final/README.md`](final/README.md); [`final/CODE_VERSION.md`](final/CODE_VERSION.md) names the exported commit and every edit made at export. Since 2026-11-02 it is the code of our closed official run 3 (commit `402c44d2`: run 1's pipeline plus three model-free end-stage passes, switched on with `--bets` (two of them developed on the final benchmark: [`final/README.md`](final/README.md), top), and the reference step's env fix in `infra/refhb/`); run 2's code (`0ea568e2`) is the `final/` of release `closed-final-run2-probe-20261102`. The official run's records and result are not included, and one file of the style rewrite, `harness/style_rw_exemplars.json`, is withheld from this public repository |
| [`warmup/`](warmup/) | Everything needed to replicate the warm-up result: code, knowledge briefs, runner inputs, data, logs, full trajectories, the submitted file and its ledger; plus the CPU post-passes ([`POSTPASS.md`](warmup/POSTPASS.md)) and the clean from-seed pipeline at 90.69 ([`AUTOBRIEF.md`](warmup/AUTOBRIEF.md), folder `warmup/autobrief_20261014/`) |

## Our closed-track uploads

All under username `Vexorium-Agent`. The leaderboard shows a team's latest upload.

On the 15-problem warm-up subset:

| Upload | Uploaded (UTC) | Official score | What it was |
|---|---|---|---|
| `sub06` | 2026-10-12 01:20 | 89.46 | GPT-6.1 Sol on our harness, with knowledge briefs from earlier research; replicated in [`warmup/`](warmup/) (section below) |
| `sub12` | 2026-10-22 21:27 | 93.06 | a development union: per problem, the best proof from our earlier research lines and golf passes (several closed models, not only through OpenRouter); not from the seed proofs and not within the $3 cap |
| `sub15` | 2026-10-28 00:57 | 91.70 | the from-seed pipeline within the $3 cap (next section) |
| `sub16` | 2026-10-30 20:23 | 93.40 | a test upload: the best proofs of a ceiling run that started from union proofs, with GPT-6 Astra and GPT-6.1 Sol sessions on Azure; not from the seed proofs and not within the cap. It is our latest warm-up upload |

On the 60-problem final benchmark. **Our final closed upload is `sub41` (2026-11-04 10:27 UTC, leaderboard 86.31, eighth on the
closed-track leaderboard at the deadline, 2026-11-04 11:59 UTC): closed official run 3's
merged output after two passes of the post-step (version v4su: the version-4 ops, every op except the kernel-skip op `kskip`); the
upload carries no `set_option` of any kind (no `debug.skipKernelTC`). Its code is the uploaded code ZIP (sha256 abc1b0e2...), whose code and docs are
the `final/` of tag [`closed-final-sub41-20261104`](https://github.com/bobbercheng/lean-refactor-closed/tree/closed-final-sub41-20261104)
(the older tag `closed-final-run3-postv4su-20261104` has the same code with the docs of a three-pass variant, with an extra
elaborator-option pass, which we did not upload).**
The `final/` on this `main` branch is closed run 3's code without the post-step. Earlier uploads were probes:

| Upload | Uploaded (UTC) | Leaderboard | What it was |
|---|---|---|---|
| `sub20` | 2026-11-02 00:44 | 85.66 (L 75.62, H 81.38, Z 100) | closed official run 1's output (commit `b5f036ab`), with its code zip; release `closed-final-probe-20261102` |
| `sub22` | 2026-11-02 03:00 | 70.30 (L 51.89, H 59.01, Z 100) | closed official run 1's state 1.87 h into the run, proofs only: uploaded to show an early state on the board in place of run 1's final score |
| `sub23` | 2026-11-02 18:11 | 80.89 (L 67.76, H 74.91, Z 100) | closed official run 2's state 4 hours after its shards started (commit `0ea568e2`; the run was still going), proofs only; release `closed-final-run2-probe-20261102` |
| `sub25` | 2026-11-03 05:56 | 84.85 (L 73.85, H 80.71, Z 100) | closed official run 3's state about 10 hours in (commit `402c44d2`; the run was still going), proofs only |
| `sub27` | 2026-11-03 07:21 | 85.80 (L 75.52, H 81.87, Z 100) | closed official run 2's final output (commit `0ea568e2`), proofs only |
| `sub30` | 2026-11-03 17:23 | 86.85 (L 74.87, H 85.69, Z 100) | closed official run 1's final output after the post-step (4 rows changed; used `debug.skipKernelTC`: [`DISCLOSURES.md`](DISCLOSURES.md), "Kernel skip"); code: tag `closed-final-run1-post-20261103` |
| `sub32` | 2026-11-04 03:05 | 87.13 (L 75.85, H 85.56, Z 100) | closed official run 3's merged output after the post-step (29 rows changed; used `debug.skipKernelTC` on 4 rows: [`DISCLOSURES.md`](DISCLOSURES.md), "Kernel skip"); code: tag `closed-final-run3-postv2-20261104` |
| `sub34` | 2026-11-04 06:54 | 86.24 (L 76.91, H 81.81, Z 100) | closed official run 3's merged output after the post-step without its kernel-skip op (27 rows changed); no `debug.skipKernelTC`, no `set_option debug.*`; code: tag `closed-final-run3-postv2-nokskip-20261104` |
| `sub41` | 2026-11-04 10:27 | 86.31 (L 77.07, H 81.86, Z 100) | **our final closed upload**: closed official run 3's merged output after two post-step passes (v4 ops without `kskip`); no `set_option` of any kind; code ZIP abc1b0e2 (tag `closed-final-sub41-20261104`) |

The kernel-skip disclosure for `sub30` and `sub32` is in [`DISCLOSURES.md`](DISCLOSURES.md), section "Kernel skip".

## From-seed pipeline submission (2026-10-28): 91.70

| | |
|---|---|
| Pipeline | the closed-track final package in [`final/`](final/) (arm B of our final candidates): GPT-6.1 Sol in tool-using sessions until a problem has spent $1.25, GPT-6.1 Terra for the later budget steps, a Gemini 4 Argon review and a model-free end stage, all through OpenRouter and all from the seed proofs |
| Problems | the 15-problem warm-up subset |
| Submission | `sub15-closed-armB-final`, username `Vexorium-Agent`, uploaded 2026-10-28 00:57 UTC |
| Official score | **91.70** (L 85.65, H 89.44, Z 100: every proof compiles on every listed toolchain) |
| Local scorer | 91.744 in the run; 91.701 on a regrade on every toolchain |
| API spend | mean **$2.67**, max **$2.79** per problem at list prices; the cap is $3.00 per problem, enforced in code |

The run's records are not part of this repository. [`final/`](final/) holds the reviewed package of this pipeline **plus** five later
additions that this submission did not use: the Terra tail, the sorry guard, the review repair + stack (R6), the style rewrite
(style_rw) and the approach pick (1 extra group, time cap), with its forbidden-construct list re-synced to the leaderboard's
2026-10-28 list and the auto-brief opening fix (a session's opening shows the brief's installed start proof as its current best),
and since 2026-11-02 the end-stage passes and fixes of closed runs 2 and 3 (two of the passes developed on the final benchmark); see
[`DISCLOSURES.md`](DISCLOSURES.md), section "The final package and what it carries from our development work".
[`final/CODE_VERSION.md`](final/CODE_VERSION.md) names the exported commit and what changed since the package of this run.

## Earlier: the first warm-up submission (2026-10-12), replicated in `warmup/`

| | |
|---|---|
| Model | GPT-6.1 Sol through OpenRouter, run on our own agent harness |
| Problems | the 15-problem warm-up subset |
| Submission | `sub06-closed-8951`, username `Vexorium-Agent` |
| Submitted file | the snapshot of the run taken when its local mean first reached 89.5 (2026-10-11 23:52:47 UTC); the run kept going afterwards |
| Uploaded | 2026-10-12 01:20 UTC |
| Official score | **89.46**, with 15/15 problems compiled |
| API spend at the submitted snapshot | at most **$1.7386 billed per problem**, which is **$1.76 at list price** (OpenRouter bills 0.99 × list); a hard cap applies per problem |

**How spend was counted.** Every call that returned usage is counted: 1,624 calls up to the submitted snapshot and 2,208 up
to the point where the run was paused. The meter records OpenRouter's billed cost, which is 0.99 × list price. The
team checked that the account's billing reconciles with the meter to the cent; no billing export is included. A
transport failure that the harness retried is not logged.

The knowledge this run started from (it was not a cold start) is in [`DISCLOSURES.md`](DISCLOSURES.md), section
"Knowledge given to the first warm-up submission".

## Clean pipeline from the seed proofs (2026-10-14, not submitted)

After the organizers ruled that the final starts from the seed proofs and runs through OpenRouter, we measured a clean pipeline:
- GPT-6.1 Sol via OpenRouter, from the seed proofs;
- general knowledge only, including an **auto-brief** computed by CPU from each seed in the run;
- a junk guard and no fresh restarts;
- a $0 cleanup at the end.

It scored **90.69** on the warm-up rows (local scorer, every proof re-checked on every toolchain) at **at most $2.60 per problem at list
price**. The working assumption was that this replicates (one run); the final package in [`final/`](final/) superseded it (since 2026-11-02 that package
also holds end-stage passes, two of them developed on the final benchmark: [`DISCLOSURES.md`](DISCLOSURES.md), section "The final package and what it carries from our development work"). Details, records, code and
full trajectories:
[`warmup/AUTOBRIEF.md`](warmup/AUTOBRIEF.md).
