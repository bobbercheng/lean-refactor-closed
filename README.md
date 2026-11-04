# Lean Refactor Arena: closed-source LLM track (team Vexorium)

This repository holds our **closed-source LLM track** entry in the Lean Refactor Arena, a NeurIPS 2026 VERICODEGEN workshop
competition (username `Vexorium-Agent`): the final package that the organizers run, and the material to replicate our warm-up
results.

**This branch (`release/closed-run3-post`, 2026-11-04):** [`final/`](final/README.md) is the code of our closed official run 3 (commit
`402c44d2`, as on `main`) plus version 2 of the post-step (`final/harness/open_post.py`, `final/harness/post/`,
`final/infra/closed_package/post_step.py`; [`final/README.md`](final/README.md) section 10). The closed upload it documents is run 3's
merged output after that step, run without its kernel-skip op `kskip` (since 2026-11-04: the upload carries no `set_option
debug.skipKernelTC` and no `set_option debug.*`; our earlier upload `sub32`, code tag `closed-final-run3-postv2-20261104`, used it on 4
rows); how to replicate it, step by step: [`final/REPLICATE.md`](final/REPLICATE.md). Our code zip for that
upload is this `final/` with the exact files of the run's commit (here they keep the export's redactions), the withheld example file,
a `ZIP_NOTES.md`, and the post-step's files byte for byte (here 4 of them carry redactions in comments). The rest of this README
describes `main`.

## Contents

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

On the 60-problem final benchmark. **Our closed upload is `sub30` (2026-11-03): closed official run 1's output after the post-step; its code
is the `final/` of tag [`closed-final-run1-post-20261103`](https://github.com/bobbercheng/lean-refactor-closed/tree/closed-final-run1-post-20261103)
(branch `release/closed-run1-post`): run 1's code (commit `b5f036ab`) plus the post-step, see section 10 of its `final/README.md`.**
The `final/` on this `main` branch is closed run 3's code, not the uploaded one. Earlier uploads were probes:

| Upload | Uploaded (UTC) | Leaderboard | What it was |
|---|---|---|---|
| `sub20` | 2026-11-02 00:44 | 85.66 (L 75.62, H 81.38, Z 100) | closed official run 1's output (commit `b5f036ab`), with its code zip; release `closed-final-probe-20261102` |
| `sub22` | 2026-11-02 03:00 | 70.30 (L 51.89, H 59.01, Z 100) | closed official run 1's state 1.87 h into the run, proofs only: uploaded to show an early state on the board in place of run 1's final score |
| `sub23` | 2026-11-02 18:11 | 80.89 (L 67.76, H 74.91, Z 100) | closed official run 2's state 4 hours after its shards started (commit `0ea568e2`; the run was still going), proofs only; release `closed-final-run2-probe-20261102` |
| `sub25` | 2026-11-03 05:56 | 84.85 (L 73.85, H 80.71, Z 100) | closed official run 3's state about 10 hours in (commit `402c44d2`; the run was still going), proofs only |
| `sub27` | 2026-11-03 07:21 | 85.80 (L 75.52, H 81.87, Z 100) | closed official run 2's final output (commit `0ea568e2`), proofs only |
| `sub30` | 2026-11-03 17:23 | 86.85 (L 74.87, H 85.69, Z 100) | **our closed upload**: closed official run 1's final output after the post-step (4 rows changed); code: tag `closed-final-run1-post-20261103` |

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
the Final package section below.
[`final/CODE_VERSION.md`](final/CODE_VERSION.md) names the exported commit and what changed since the package of this run.

## Final package

[`final/`](final/) runs, for every benchmark row and from its seed proof (no stored proofs of the rows apart from the style rewrite's
example pairs; what it carries from our development work is at the end of this section): GPT-6.1 Sol (through OpenRouter) in tool-using sessions
until the row has spent $1.25, GPT-6.1 Terra for the later budget steps, a Gemini 4 Argon review with **repair + stack** (R6: a review
edit that does not compile gets one repair turn from the same model inside the row's room under the cap, and the review's compiling
edits, gains below its single-edit bar included, are also tried together in one compile on every listed toolchain; a verified
combination is kept for the end stage), the **Terra tail** (a row with at least $0.20 of room left under the cap gets up to 3 more Terra
sessions budgeted to exactly that room; their proof is kept only if it compiles on every listed toolchain and scores higher), a
model-free end stage that keeps a rewrite only if it compiles on every listed toolchain and scores higher, **+ approach pick (1 extra
group, time cap)** (the end stage then polishes the best proof of one other approach among the row's candidates the same way, under a
hard 1200 s cap per row, and keeps it only if it compiles on every listed toolchain and scores higher), and the **style rewrite**
(style_rw: GPT-6.1 Sol rewrites the row's final into the shortest idiom the scorer rewards, with at most $0.30 of the row's room under
the cap and at most 15 minutes; its proof is kept only if it compiles on every listed toolchain, passes the axiom audit and scores at
least 0.05 higher on a paired read). A **sorry guard** forces Lean's `warn.sorry` on in every compile and audits each row's final proof
on every listed toolchain before it is written; a proof found to depend on `sorry` is passed over for the row's next verified proof.
Inference spend is capped at **$3.00 per row** by the code itself. The exact pipeline, its version and how to run it are in
[`final/README.md`](final/README.md) and [`final/CODE_VERSION.md`](final/CODE_VERSION.md). [`final/`](final/) is the code of our
closed official run 3 on the final benchmark (2026-11-02, commit `402c44d2`): run 1's pipeline plus three model-free end-stage passes
(`--bets D2,D3,D4,D4P,D4S,D4C,D4N`; each output adopted only when it reads strictly higher on every listed toolchain) and the
reference step's env fix; section 9 of [`final/README.md`](final/README.md) lists the steps of run 3, run 2 (commit `0ea568e2`, the
`final/` of release `closed-final-run2-probe-20261102`) and run 1 (commit `b5f036ab`, release `closed-final-probe-20261102`). Runs 2
and 3 ran side by side on two hosts. Update 2026-11-03: the closed upload is `sub30`, run 1's output after the post-step, with the code of
tag `closed-final-run1-post-20261103` (run 1's code plus the post-step), not this branch's `final/`. What it carries from our development work: the style rewrite's nine example pairs
(five of them improved proofs of three warm-up theorems that are also final-benchmark rows); two end-stage passes, D3 and D4, developed
on the final benchmark after its release, mainly from our offline research (uncapped agent sessions of other closed models on 5 of
its rows, outside the $3 cap; none of their proofs is in any upload or package) and from our first run's results; the third pass,
D2, from our warm-up work before the release; the passes that run were chosen by measurements on final-benchmark rows; the run-2
fixes come from that first run's records ([`final/README.md`](final/README.md), top). The passes hold no row names and no proof text of
any row. [`final/`](final/) is not byte-identical to the code that ran: it keeps the export's
comment and docstring redactions, and one file of the style rewrite is withheld. The code zip submitted to the organizers has the exact
files ([`final/README.md`](final/README.md) section 8, Byte identity).

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

**Not a cold-start cost.** The model was given knowledge from earlier research, and the spend above does not include
that research:

- **Per-problem knowledge briefs.** They were built from earlier research lines on these same 15 problems: Claude Opus 5.5,
  GPT Astra and GLM-5.3-Flash. One brief also gained an addendum from an earlier GPT-6.1 Sol line, after the submitted
  snapshot.
  - They contain landmark numbers, lever lists and lists of failed attempts.
  - In places they also contain short Lean fragments and proof-structure outlines (for example `putnam_1964_b2`).
  - No brief contains a complete proof.
- **General habits.** The harness option `--closed-lessons` is on by default in this code. As a result, every session's
  first message carried a short list of general habits mined from the Opus 5.5 and GPT Astra lines.
- **Runner inputs.** The runner also read two sets of scores, both included here as scores only:
  - per-problem target scores, which are the union best over the earlier lines
  - the first-session scores of an earlier GPT-6.1 Sol line

Details are in [`warmup/README.md`](warmup/README.md) section 5.

## Clean pipeline from the seed proofs (2026-10-14, not submitted)

After the organizers ruled that the final starts from the seed proofs and runs through OpenRouter, we measured a clean pipeline:
- GPT-6.1 Sol via OpenRouter, from the seed proofs;
- general knowledge only, including an **auto-brief** computed by CPU from each seed in the run;
- a junk guard and no fresh restarts;
- a $0 cleanup at the end.

It scored **90.69** on the warm-up rows (local scorer, every proof re-checked on every toolchain) at **at most $2.60 per problem at list
price**. The working assumption was that this replicates (one run); the final package above superseded it (since 2026-11-02 that package
also holds end-stage passes, two of them developed on the final benchmark: see Final package). Details, records, code and
full trajectories:
[`warmup/AUTOBRIEF.md`](warmup/AUTOBRIEF.md).

## Documentation

- [`final/README.md`](final/README.md): requirements, install, the run command, a $0 dry run with a fake model, and what the package
  writes; [`final/CODE_VERSION.md`](final/CODE_VERSION.md): the exported commit and the edits made at export.
- [`warmup/README.md`](warmup/README.md) covers:
  - the result, the model and harness, and the budget-ladder protocol
  - the timeline
  - knowledge provenance and disclosure
  - environment setup
  - the exact commands to re-verify the submission and to replicate or continue the run
- [`warmup/BUDGET.md`](warmup/BUDGET.md): per-problem API spend, billed and at list price, at the submitted snapshot and at
  the point where the run was paused.
- [`warmup/CODE_VERSIONS.md`](warmup/CODE_VERSIONS.md) covers:
  - which project commit each round ran
  - the two code changes made during the run (as diffs)
  - the small edits made to the code in this folder at staging
  - the pinned upstream clones

## Before you replicate

The model's `shell` tool is guarded by a deny-list only; it is **not a sandbox**. Before running anything:

- Move `warmup/submit/candidates/`, `warmup/submit/results/` and the recorded runs and snapshots out of reach of the
  account that runs the model.
- Give that account nothing except its one API key.

[`warmup/README.md`](warmup/README.md) section 7.2 gives the steps.

## Credentials

No credentials are included. [`final/`](final/) takes one OpenRouter key, from `OPENROUTER_API_KEY` or `--key-file`
([`final/README.md`](final/README.md) section 3). For the code in `warmup/`, create your own key files at the paths named in
`warmup/README.md` (section 9).

## License

Our code, notes and run records are licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE): free for study,
research and other noncommercial use. **Commercial use needs a separate license**: contact b.cheng@vexorium.net. Third-party
material (upstream Lean library sources, competition data, model outputs) keeps its own terms; see [`NOTICE.md`](NOTICE.md),
which also lists the edits made for public release.
