# Lean Refactor Arena: closed-source LLM track (team Vexorium)

This repository holds our **closed-source LLM track** entry in the Lean Refactor Arena, a NeurIPS 2026 VERICODEGEN workshop
competition (username `Vexorium-Agent`): the final package that the organizers run, and the material to replicate our warm-up
results.

## Contents

| Folder | What it holds |
|---|---|
| [`final/`](final/) | The closed-track final as one self-contained package: the code, the session container, the environment installer and the one command that turns a benchmark rows file into the upload file. Start with [`final/README.md`](final/README.md); [`final/CODE_VERSION.md`](final/CODE_VERSION.md) names the exported commit and every edit made at export. Also `env_fixes/envfix.py` (the env-side workaround applied during our closed official run) and `infra/refhb/make_ref_heartbeats.py` (the reference-heartbeats tool). The official run's records and result are not included, and one file of the style rewrite, `harness/style_rw_exemplars.json`, is withheld from this public repository |
| [`warmup/`](warmup/) | Everything needed to replicate the warm-up result: code, knowledge briefs, runner inputs, data, logs, full trajectories, the submitted file and its ledger; plus the CPU post-passes ([`POSTPASS.md`](warmup/POSTPASS.md)) and the clean from-seed pipeline at 90.69 ([`AUTOBRIEF.md`](warmup/AUTOBRIEF.md), folder `warmup/autobrief_20261014/`) |

## Our closed-track uploads

All under username `Vexorium-Agent`, all on the 15-problem warm-up subset. The leaderboard shows a team's latest upload.

| Upload | Uploaded (UTC) | Official score | What it was |
|---|---|---|---|
| `sub06` | 2026-10-12 01:20 | 89.46 | GPT-6.1 Sol on our harness, with knowledge briefs from earlier research; replicated in [`warmup/`](warmup/) (section below) |
| `sub12` | 2026-10-22 21:27 | 93.06 | a development union: per problem, the best proof from our earlier research lines and golf passes (several closed models, not only through OpenRouter); not from the seed proofs and not within the $3 cap |
| `sub15` | 2026-10-28 00:57 | 91.70 | the from-seed pipeline within the $3 cap (next section) |
| `sub16` | 2026-10-30 20:23 | 93.40 | a test upload: the best proofs of a ceiling run that started from union proofs, with GPT-6 Astra and GPT-6.1 Sol sessions on Azure; not from the seed proofs and not within the cap. It is our latest closed-track upload |

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
2026-10-28 list and the auto-brief opening fix (a session's opening shows the brief's installed start proof as its current best);
see the Final package section below.
[`final/CODE_VERSION.md`](final/CODE_VERSION.md) names the exported commit and what changed since the package of this run.

## Final package

[`final/`](final/) runs, for every benchmark row and from its seed proof only: GPT-6.1 Sol (through OpenRouter) in tool-using sessions
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
closed official run on the final benchmark (2026-11-01) plus the reference-heartbeats tool that run used; section 9 of
[`final/README.md`](final/README.md) lists that run's steps. It is not byte-identical to the code that ran: it keeps the export's
comment and docstring redactions, and one file of the style rewrite is withheld. The code zip submitted to the organizers has the exact
files ([`final/README.md`](final/README.md) section 8, Byte identity). On this branch (`release/closed-run1-post`), [`final/`](final/)
also holds the **post-step** (2026-11-03): our closed upload is that run's output after this $0, model-free, accept-gated step; its
command, what it does, its provenance (its ops were developed on the final benchmark) and our run of it are in
[`final/README.md`](final/README.md) section 10.

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
price**. The working assumption was that this replicates (one run); the final package above superseded it. Details, records, code and
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
