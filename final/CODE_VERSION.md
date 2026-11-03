# Code version

| | |
|---|---|
| source | our private development repository, branch `b71-final` (the code) and branch `b100-refhb-closed` (one tool) |
| commit | `b5f036abb80285c0b3b7b365146849be20c1d2aa` (2026-10-31 18:42:01 UTC), the reviewed closed final that our closed official run on the final benchmark executed (2026-11-01): arm B (the pipeline of submission `sub15`) + the Terra tail + the sorry guard + the review repair + stack (R6) + the style rewrite (style_rw) + the approach pick (1 extra group, time cap) + the forbidden list re-synced to the leaderboard (2026-10-28) + the auto-brief opening fix; the `c2` end-stage family is in the code but not enabled. Its code files are those of `bd26b620` (the previous export's commit): the two commits differ in documents and test records only |
| tool | `infra/refhb/make_ref_heartbeats.py` of `f5cdaa4201e82b6e11d2ede139219118b7262a23` (2026-11-01 02:15:07 UTC), the only file taken from that commit: the reference-heartbeats tool, copied into the official run's checkout (untracked) and run there before the launch |
| exported | 2026-11-01, with `git archive` of those commits (no history, no working-tree files); the previous `final/` was dropped and this folder written fresh |
| post-step | added 2026-11-03 (README.md section 10): `harness/open_post.py` and `harness/post/` of `5cb18d3bb80fc3ede09527eb36adf0ecf7759146` (2026-11-03 13:58:40 UTC, branch `open-post`), with `git archive`; `harness/post_support.py` (verbatim pieces of that commit's `harness/open_package.py`) and `infra/closed_package/post_step.py` written for this package. No file of the run changed |
| previous export | b71-final `bd26b6204096d193f6c3551f9350b4618089981c` (2026-10-31 16:24:16 UTC): the same pipeline |

## Added on 2026-11-03: the post-step

- **New, not part of the run:** `infra/closed_package/post_step.py` (the command), `harness/open_post.py` and `harness/post/` (the step
  and its ops `kskip`, `implied`, `inlineeq`, `closerprep` with their helpers `d4_kit`, `d4_measure`, `d3_simpconst`), and
  `harness/post_support.py` (`SORRY_GUARD_ENV`, `git_trust`, `audit_proof` and two constants, copied verbatim from `5cb18d3b`'s
  `harness/open_package.py`, the open package's module that `harness/open_post.py`'s own command line imports; this package calls
  the step through `post_step.py` instead). What the step does, its gate, how to run it and our run of it: README.md section 10. The
  op modules are the closed line's D4 code (`closed-bets-d4` `402c44d2`, `harness/tools/`) vendored unchanged except for one comment
  line and their `harness.post` imports; `kskip` is new (2026-11-03).
- **What it uses from the run's code, unchanged:** `harness/endstage.Meter` (with its `command()`), `harness/hb_tool_eval.Evaluator`,
  `scorer.tokenize`, `scorer.forbidden`, `scorer.accept`, `scorer.compile.audit_axioms`, `harness/normalize.py`'s and
  `harness/lint_delete.py`'s text helpers, `probe/verify_candidates.newest_first`, `harness/final_rows.py`, `harness/final_merge.py`,
  `harness/host_knobs.py`. Compared with the code our post-step run used (all of `5cb18d3b`), these differ only where the measurement
  does not: `harness/endstage.py` (its Meter differs only in the self-test's parallel pins and in `command()`, which `5cb18d3b`
  lacks and `harness/open_post.py` adds with the same code; `5cb18d3b`'s package dropped other end-stage code), `harness/normalize.py`
  (the three helpers the ops import, `_mask`, `_pairs` and `OPEN`, are the same), `scorer/memgate.py` and `harness/hb_tool_eval.py`
  (a lock fallback for filesystems without `flock`), `scorer/compile.py` (`ELAN_HOME`, an unknown library's environment directory),
  `harness/leantools.py` (row file overrides by environment variables, unset), and `scorer/score.py`: `5cb18d3b`'s honours
  `LRA_LOCAL_REF=none`, which our run set; here `post_step.py` empties the same table in its process.
- **`README.md`**: the top (the upload is the run's output after the step; the step's provenance), section 2 (the install sets
  `extensions.worktreeConfig` once: the shards' parallel sparse-checkout setups can otherwise collide), section 8 (the files, byte
  identity), section 10 (new). **`.gitignore`**: unchanged (the step's compile scratch is under the ignored `probe/hbtool/.scratch/`).

## Changed in the export of 2026-11-01 (since b71-final bd26b620)

- **Nothing in the pipeline.** The 133 code files are byte-identical to the previous export's (same commit content, the same
  redactions and scrub).
- **Added: `infra/refhb/make_ref_heartbeats.py`** (b100, 2026-11-01: the final benchmark's reference heartbeats are not published).
  It writes a heartbeats file in the warm-up release's format for a rows file, which `run_final.py run --heartbeats` then uses as
  is: each row's reference proof (`src`) compiled on its newest pin with the pinned `lean` binary on the built libraries (explicit
  `LEAN_PATH`, heartbeats under `Elab.async false`) plus 2, within 0.71 % of the official values on the 15 warm-up rows; warm-up rows
  reuse the published values; the scorer path (`lake env lean`) as a per-row fallback; each environment's commit checked against
  the row's pin (a warning, an error with `--strict`); a row no method measures stops the tool (exit 1, `OUT.partial`) unless
  `--allow-missing` gives it a flagged placeholder. The package's own staging is unchanged: without `--heartbeats`, `run_final.py`
  still measures a row without a reference through the scorer (`harness/final_rows.py measure`); the tool is not wired into it in
  this export.
- **`README.md`**: section 9 (the steps of the closed official run, its reference heartbeats, the lesson of its first launch: the
  ladder worktrees link `envs/` from the repository's main working tree), the `--heartbeats` bullet (the tool; a staged rows file
  keeps its heartbeats), the tool's row in section 8. **`.gitignore`**: the tool's default scratch `probe/refhb/.scratch/`.
  **`envs/README.md`**: the worktree note.

## Changed in the previous export (bd26b620)

- **The auto-brief opening shows the installed start** (b92, 2026-10-31, a defect fix): every row's first session runs with the CPU
  auto-brief (`--auto-brief`), which appends the brief to the session's opening message and, when the brief's start proof measures at
  least 0.05 above the workspace's best, checks it with the session's own compile and installs it as `candidate.lean`. The opening was
  rendered BEFORE that install, so the model was shown the seed as "candidate.lean (your current best)", the seed's score as the best
  so far and the seed's linter hints "on the current candidate", while the brief below said the workspace starts from the start proof.
  Now, after a successful install, `harness/agent.py` re-renders exactly those parts of the opening from the installed `candidate.lean`
  and the session's own check of it: the best-so-far sentence (the start's score, tokens, heartbeats), the candidate.lean block, the
  linter hints on the current candidate (the start's own, from the same check: no extra compile) and a start check's block. Everything
  else stays as rendered: the turn budget and every other session parameter are set before the install, the brief text, the cards and
  the leads. When no start is installed (no brief for the row, a start that does not compile, a start not 0.05 above the best) the
  opening is byte-identical to the previous export's. A re-render that raises, or a recorded span that no longer holds what was rendered,
  leaves the opening as rendered and never fails the session.
  - Checked at $0 (a scripted fake model, real Lean): sessions of the previous export's `agent.py` and of this one on warm-up rows with
    their real auto-brief files: with no start installed every request is identical; with a start installed the requests differ only
    in the opening's re-rendered spans, the turn budget equal; the package's fake-model dry run (two rows, auto-brief on) shows the
    installed start in both rows' first-session opening. The effect on score is not measured on paid rows.
  - `harness/agent.py` (+84 / -12) is the only changed file: no flag, prompt, budget step, gate, meter or money-path code changed.
    The router's code hash changes with `agent.py`, so a run directory started on the previous export's code is refused on resume
    (start the final fresh on this code).

## Changed in an earlier export (9d01d74c)

- **The forbidden-construct list re-synced to the leaderboard** (2026-10-30): `scorer/forbidden.py` now mirrors the leaderboard Space's
  `_FORBIDDEN_PATTERNS` as of its 2026-10-28 update. Added: `IO` (any use), `run_tac`, `by_elab`, `run_meta`, `simproc`, `eval%`,
  `unsafe IO`, `decide +native` / `native := true`, and any identifier containing "heartbeat" other than the `maxHeartbeats` option.
  The previous list (2026-10-06) accepted these, so a pipeline could have kept a proof that the evaluation worker rejects. Every
  candidate is checked against this list (acceptance, end stage, style rewrite, approach pick), so the change can only reject more
  candidates; the earlier submissions, our proof pool and every benchmark statement and reference proof pass the new list. No other file
  changed.

## Changed in an earlier export (9c4d9c6b)

- **The approach pick (1 extra group, time cap)** (b84, adopted 2026-10-30 below the bar we had set for it, as a model-free step that
  cannot lower a row): every shard's end step runs with `--end-approach on --end-approach-groups 1 --end-approach-seconds 1200`
  (`run_final.APPROACH_ARGS`; frozen into each shard's `config.json` as `end_approach` = `{"groups": 1, "seconds": 1200.0}`, and a
  resume with other values is refused). It runs inside the end step, before the style rewrite.
  - GROUPS: after the end stage has settled a row's proof, the row's candidates (what the end stage read, those with a stored score)
    are grouped by approach: the lemma names and top-level case splits a proof uses (the library's constructor names left out), the
    names used by 3% to 97% of the row's candidates, complete-link Jaccard >= 0.5.
  - POLISH: the best proof group other than the final's (by best stored score) is polished by the same model-free end stage
    (`probe/b63/r10_candidate.json`) in a child process, under a hard wall cap of 1200 s per row, never more than what is left of the
    end stage's own 3600 s clock (sweep + tool phase). At the cap the child and every process it started are killed and its work is
    dropped.
  - GATE: the polished proof replaces the row's proof only when it compiles on every listed toolchain (Z 100), keeps the statement, has
    no forbidden construct, reads higher back to back on the end stage's meter (`scorer.accept.decide`), passes the axiom audit (no
    `sorry`) and reads higher again on a second back-to-back read; otherwise the row's proof stays byte for byte. No model call; an
    error or a timeout leaves the row's proof.
  - Measured out of sample (64 samples: the recorded banks of an internal held-out set and of an earlier candidate pool, the end stage
    replayed on each group): **4 improved, 60 unchanged, 0 worse, +0.011 per row (95% CI +0.001 to +0.024)**; the 1200 s cap keeps all
    4 gains on the recorded timings (the slowest polish took 983 s; under about 3x core oversubscription it took longer than the cap and
    was dropped, with no harm); added wall per row p50 466 s, p95 1200 s, 11 of 64 samples at the cap.
  - WALL with the style rewrite: the style rewrite's cap counts the end stage's own seconds, so a row's end step takes at most its end
    stage's time + 1200 s + 900 s.
  - `harness/approach_pick.py` (new), `harness/router.py` (the end step), `infra/closed_package/run_final.py`; `harness/leak_scan.py`
    allows one more Lean core tactic name (`simp_all!`, which the grouping's filter names).
- Unchanged: `scorer/`, `llm/`, `harness/agent.py`, `harness/endstage.py`, `harness/style_rw.py`, `harness/review.py`,
  `harness/postpass.py`, `harness/final_writer.py`, `harness/hx_heldout.py`, the prompts, the budget steps, the cap and the meter, R6,
  the tail, the sorry guard, the style rewrite and the end-stage configuration.
- The previous export's changes (the style rewrite) are in this commit unchanged.

## What was exported

The file list is the package's own definition of what a run needs: the same rule and the same 133 files as the previous export (the
list of the approach pick's export), plus `infra/refhb/make_ref_heartbeats.py` (134 files; the tool imports only modules of this
list: `scorer.compile`, `harness.hb_tool_eval`, `probe.verify_candidates`):
- the session worktree's whitelist (`harness/hx_heldout.py` `CLEAN_PATHS`): `harness/*.py`, `harness/tools/*.py`, `scorer/*.py`,
  `llm/*.py`, `bank/*.py`, `probe/verify_candidates.py`, `data/benchmark_warmup.jsonl`, `data/benchmark_heartbeats.jsonl`,
  `data/reference_heartbeats_local.json`;
- plus the package (`infra/closed_package/`), the runaway guard (`harness/runaway_guard.sh`), the end-stage configurations
  (`probe/b63/r10_candidate.json`, `probe/b66/smoke_end.json`) and the installer's optional restore path (`infra/sync/restore_envs.sh`,
  `infra/vast/envs_kaggle.tsv`, `infra/vast/harness_envs.json`);
- plus `harness/tools/tables/` (the generated tables the end-stage families and the brief read; `CLEAN_PATHS` does not list them, so
  the sessions' worktree runs without them exactly as in the measured runs, while the router's model-free stages read them).

Left out: tests and self-test harnesses; development-only drivers and tools the final never runs (other model lines' drivers, status,
relay, audit and proxy scripts); the environment build scripts and manifest (`install_envs.sh` replaces them); every development set,
run record, document and submission file (among them the opt-in configurations of `c2`, the gate records, the R6 A/B's tools and
records, the style rewrite's replay, the approach pick's out-of-sample replay and the opening fix's tests and dry-run records). An import trace of the launch path and of every
exported module from the exported tree finds no missing local module, and a static trace of every import statement finds two
imports inside functions whose modules are not exported, neither reachable in the final: `llm.codex_review` (harness/review.py, only for a
`codex:` review model; the final reviews with gemini-4-argon) and `harness.prompt_v2` (harness/transfer.py, inside try/except).
`env_fixes/envfix.py` (added 2026-11-01) is not package code: it is the env-side workaround applied on the run host (README section 9).
`harness/style_rw_exemplars.json` (sha256 `c03ffd730e950d93...`, byte-identical to the commit) was exported, but it is withheld from the
public repository (removed from this folder on 2026-11-01): 133 of the 134 files are here. The organizers receive it in the submitted
code zip. Without it the style rewrite step cannot run (README, the style rewrite).

## Staging edits (the only differences from the commit)

No line of logic changed. Every edit of a code file keeps its line count, so line numbers in the code match the commit. Two layers
(neither touches `infra/refhb/make_ref_heartbeats.py`, which is byte-identical to its commit):

**1. Export redactions** (the same policy and the same 62 line edits as the previous export, at this commit's line numbers):
- **Comments, docstrings and help texts**: warm-up row names, nicknames and their measured moves replaced by "a dev row" or a generic
  phrase (`harness/agent.py` 318, 319, 325, 326, 336, 337, 344, 345, 503, 596, 878, 1744, 2188, 2214; `harness/architect.py` 132, 134,
  178; `harness/goals.py` 3; `harness/hb_rewrite.py` 61, 71, 78, 1154, 1155; `harness/router.py` 19, 170; `harness/leantools.py` 51,
  218, 219; `harness/mine.py` 32, 313, 358, 359; `harness/lemma_search.py` 4, 5, 6, 601; `harness/oracle_rules.py` 6, 7;
  `harness/postpass.py` 28; `harness/profile.py` 3; `scorer/compile.py` 7; `harness/tools/t6_transpile.py` 2;
  `harness/tools/t7_defer.py` 3; `harness/review.py` 452); references to notes on other entries removed (`harness/agent.py` 2952,
  `harness/hb_rewrite.py` 2, `harness/cards.py` 63, `harness/hx_heldout.py` 1378); statistics and ruling files of internal held-out sets
  removed (`harness/hb_rewrite.py` 59, 60; `harness/hx_heldout.py` 12, 19, 246, 247; `harness/inrun.py` 2; the refusal message of
  `harness/discover.py` 163; `harness/tools/c2_lemvar.py` 8; `infra/closed_package/run_final.py` 92); development host names and paths
  removed (`harness/lemma_search.py` 54, 56; `harness/workbench.py` 6).
- **`harness/runaway_guard.sh` 11**: the guard log's default path was a development home directory; it is now
  `probe/runaway_guard.log` of the checkout. The package always passes `GUARD_LOG`, so a run never uses the default.
- **`probe/b63/r10_candidate.json`**: the development copy's documentation keys (every key starting with `_`, which the end stage's
  loader ignores) are removed and the description is rewritten. `harness/endstage.load_config` returns identical values for both
  files; the file's sha256 (recorded in each run's config) changes from `fecbf742...` to `29976efe...`.

**2. Public-release scrub** (the tool that prepared this repository's history for publication, run on this folder with `scrub.py dir`;
[`../NOTICE.md`](../NOTICE.md), "Edits for public release", describes it): 166 lines in 38 files, comments, docstrings, help texts, log
messages and one refusal message only. Development notes and attributions of decisions (with their quotes) removed, workflow ids
removed, the development home directory replaced by a generic path, and the development-only Vertex AI path reads its GCP project from
`LRA_GCP_PROJECT` (`harness/agent.py` `VERTEX_PROXY`, `llm/anthropic_vertex.py`; the final calls OpenRouter and never uses Vertex). Every
changed Python file parses, keeps its line count and has the commit's syntax tree apart from those strings and the Vertex edit.

**Files new in this folder**:
- **`README.md`** (at the top of this folder): `infra/closed_package/README.md` of the commit, moved here, with the install step for
  this export (the folder becomes its own git checkout), the example input, how the upload file is produced, the $0 dry run (two warm-up
  rows, one of them a PhysLib row; the fake's adversarial, R6 and style_rw modes), the one change after the R6 A/B, the approach pick,
  this folder's contents and the closed official run's steps (section 9); pointers to development documents replaced by "in our development repository" or removed.
- **`.gitignore`**: what a run writes inside the checkout.
- **`envs/README.md`** (tracked): in the development repository `envs/` always held tracked files; with none, `git status` reports the
  whole `envs/` as one untracked entry, the sessions' stray-file masking (`hx_heldout.stray_masks`) masks it and docker refuses the
  container (`Duplicate mount point`), so every session fails. The tracked file and the `envs/*` ignore rule keep the development
  repository's behaviour.
- **`CODE_VERSION.md`**: this file.
