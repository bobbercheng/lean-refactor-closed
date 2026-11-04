# Code version

| | |
|---|---|
| source | our private development repository, branch `closed-bets-d4` |
| commit | `402c44d2c49a0d90dabaa9e413cf269f93a69e34` (2026-11-02 15:37 UTC), the code of our closed official run 3 on the final benchmark (launched 2026-11-02 19:58:11 UTC with `--bets D2,D3,D4,D4P,D4S,D4C,D4N`): closed run 2's code (`0ea568e2`) + two more default-off sub-switches of D4, D4C (closerprep) and D4N (simpnorm) |
| exported | 2026-11-02, with `git archive` of that commit (no history, no working-tree files), over the previous `final/` |
| post-step | added 2026-11-04 (README.md section 10, version 2): `harness/open_post.py` and `harness/post/` of `ee48034b032380966de26e733f6f6b74fdd503b4` (2026-11-03, branch `open-post-v2`), with `git archive`; `harness/post/_v2deps/` (that commit's `probe/open_rederive/opentables.py`, byte for byte, and an installer written for this package); `harness/post_support.py` (verbatim pieces of that commit's `harness/open_package.py`; the same file as in our run-1 post-step code zip) and `infra/closed_package/post_step.py` written for this package. No file of the run changed |
| previous export | `0ea568e281db8f8873d7ef323abc1db9e14f7afc` (closed official run 2) |

## Added on 2026-11-04: the post-step (version 2) and REPLICATE.md

- **New, not part of the run:** `infra/closed_package/post_step.py` (the command), `harness/open_post.py` and the 16 files of
  `harness/post/` (the step and its ten ops `kskip`, `implied`, `closerprep`, `inlineeq`, `hintgrind`, `projpath`, `lexsurf`,
  `jointres`, `t4ind`, `ctorsearch` with their helpers `d4_kit`, `d4_measure`, `d3_simpconst`, `spans`, `joint`), `harness/post_support.py`
  (`SORRY_GUARD_ENV`, `git_trust`, `audit_proof` and two constants, verbatim from `harness/open_package.py`, the open package's module
  that `harness/open_post.py`'s own command line imports; this package calls the step through `post_step.py` instead) and
  `harness/post/_v2deps/` (below). What the step does, its gate, its provenance, how to run it and our run of it: README.md section 10.
  `implied`, `inlineeq` and `closerprep` and their helpers `d4_kit`, `d4_measure` and `d3_simpconst` are this run's own D3/D4 code
  (`402c44d2`, `harness/tools/`) vendored unchanged except for one comment line and their `harness.post` imports; the other seven ops
  and their helpers are new (2026-11-03).
- **`post_step.py` against version 1's** (our run-1 post-step zip): the ten ops (`--ops`, default `all`, as `harness/open_post.py`'s
  own option), a row's 3600 s and 240 compiles (`harness/open_post.py`'s version-2 defaults; version 1: 2400 s and 120), its own
  open-file limit raised to 65536 (`RLIMIT_NOFILE`, capped by the hard limit, recorded), the vendored module registered before the step
  starts, the input label `closed-run3`, and the report block's new fields (`ops`, `open_files`, `vendored`). Input building, the
  checks of the upload file and the outputs are version 1's.
- **Post-step v2: dependency check.** The step's files ran, in our run of it, in a checkout of `ee48034b`; here they run on this
  package's modules (closed run 3's `402c44d2`). From every package import of the 17 post files (top level and inside functions, module
  aliases followed attribute by attribute), every definition the step reaches was walked on both sides, through differing definitions
  too, and compared by syntax tree with docstrings removed (`harness/open_package.py`'s pieces read from `harness/post_support.py`, the
  vendored module from `harness/post/_v2deps/`): **700 definitions in 28 modules are identical.** The rest differ only where the step's
  process does not reach a difference:
  - `harness/endstage.Meter`: this package's has `command()` (which `harness/open_post.py`'s `PostMeter` overrides with the same code)
    and the self-test's parallel pins (`_test_pin`; `self_test(pin_results=None)` makes the same compiles in the same order).
  - `harness/sweep.py` (`candidates`, `_hb_rewrite`, `HR_SKIP`) and `harness/hb_rewrite.py` (`sites`, `V_OPS`, `_TOKEN_FINDERS`,
    `_env_index`, `_lemmavariant` and the `genform` operator's definitions): this package's sweep has the environment-reading operator
    `genform` with its context plumbing (`sites(ctx=)`). `jointres` calls `sweep.candidates` without a context and the sweep's `HR_SKIP`
    leaves `genform` and `lemmavariant` out, so its operator list and every other operator's code are the same. Checked by running the
    pure generators (`sweep.candidates`, `hb_rewrite.sites` with the sweep's operators, `jointres.edits`, `open_post.sites`) in both
    trees on 573 distinct proofs (our runs' outputs on the 60 final rows and the seed proofs of the final and warm-up rows):
    byte-identical output for every proof (98,242 sweep candidates, 21,233 rewrite sites, 76,901 joint edits).
  - `harness/hb_tool_eval.Evaluator` (`__init__`, `_slot`) and `scorer/memgate.py` (`acquire`, `release`, `run_lean`,
    `_cgroup_avail_mb`): `ee48034b` adds `$LRA_LOCK_DIR` for the lock files, in-process fallbacks when `flock` fails (a filesystem
    without it) and a cgroup v1 opt-in (`LRA_MEMGATE_CGROUP_V1=1`); this package's memgate refuses new compiles once
    `LRA_COMPILES_CLOSED=1` (set only on the router's exit path). With those variables unset and `flock` working, as on our hosts, the
    same.
  - `scorer/compile.py` (`ELAN_BIN`, `project_env_dir`): `ee48034b` reads `ELAN_HOME` and maps a library outside the six known ones to
    `envs/<source>-<version>`: the same with `ELAN_HOME` unset and the final's six libraries.
  - `harness/leantools.py` `ROWS`: `ee48034b` reads `LRA_ROWS_FILE` when set (unset: the same warm-up file).
  - `scorer/score.py` `local_reference_heartbeats`: `ee48034b` honours `LRA_LOCAL_REF=none`, which `harness/open_post.py`'s command
    line sets; `post_step.py` empties the same table in its process (the step's only Python process) instead.
  - **Not in this package:** `probe/open_rederive/opentables.py` (`jointres._entry_ok` imports its `entry_of`, which keeps the
    sweep's table-driven operators `combdrop` and `ctorshort` to the entries of the open package's frozen configuration; without the
    module both would propose nothing, unlike in our run). Vendored byte for byte as
    `harness/post/_v2deps/probe/open_rederive/opentables.py` (sha256 `4576e703...`); `post_step.py` calls
    `harness.post._v2deps.install()`, which checks that sha256 and registers the file as `probe.open_rederive.opentables` in the
    step's process (a parent package holding only it), so the post files import it unchanged and nothing of the run sees it. `entry_of`
    reads only the candidate's note and the module's constant `_CTOR_SHORT`; the module's other functions read tables relative to its
    own path and are not called by the step. `harness/open_package.py` is not in this package either: `harness/post_support.py` holds
    its three pieces the step uses, identical to `ee48034b`'s.
  - **Run check:** the release smoke (README.md section 10) ran two rows from the code zip with the same input as our run; with our
    run's rows and heartbeats files, every logged decision, the compile counts, the adopted ops and the readings equal our run's on
    both rows, and the two output lines are byte-identical to our run's (with run 3's staged heartbeats file too).
- **`README.md`**: the top (the upload is run 3's output after the step), a section "How to replicate our upload" (the overview after it
  now has the heading "The pipeline"), the provenance list (the post-step), section 2 (the clone line names this code's tag
  `closed-final-run3-postv2-20261104`, plus the code zip's commands), section 8 (the files, byte identity), section 9 (run 3's end),
  section 10 (new). **`REPLICATE.md`** (new): the steps that replicate our upload, in order, with their expected outputs, wall time and
  cost. **`.gitignore`**: unchanged (the step's compile scratch is under the ignored `probe/hbtool/.scratch/`).

## Changed in the export of 2026-11-02 (402c44d2, closed official run 3)

- **D4C and D4N** (README, End-stage passes; distilled from our offline research on two final-benchmark rows: README, top): `harness/tools/d4_closerprep.py`, `harness/tools/d4_simpnorm.py` and their measured-query
  prefilter `harness/tools/d4_measure.py` (new), run by `harness/end_d4.py` in a second end stage after D4's own, each behind its own
  sub-switch (router `--end-d4-closerprep`, `--end-d4-simpnorm`; `run_final.py --bets ...,D4C,D4N`), default off: with them off every
  command is closed run 2's. `harness/leak_scan.py`: the preflight's allow list gains D4N's 13 generic lemma names.
  `harness/router.py`, `harness/tools/__init__.py`, `infra/closed_package/run_final.py`, `infra/closed_package/bets_test.sh`: the
  switches and the bet lists.
- **Files**: 3 new, 6 changed, the other 145 byte-identical to the previous export's (144 here: the exemplar file stays withheld).
- **`README.md`**: the passes (D4C, D4N), the `--bets` bullet, section 8, section 9 = run 3's steps first. **`run_host/closed_run3/`**:
  run 3's launcher, its reference check and the copy of run 2's environments to its host.

## Changed in the previous export (0ea568e2, closed official run 2)

- **The pipeline gains three end-stage passes, off by default** (two of them, D3 and D4, developed on the final benchmark: README,
  top), which run 2 switches on with `--bets D2,D3,D4,D4P,D4S` (README, End-stage
  passes of closed run 2): `harness/end_dialect.py` + `harness/dialect.py`, `dialect_union.py`, `dialect_unhyg.py` (D2);
  `harness/end_ops.py` + `harness/tools/d3_grind.py`, `d3_simpconst.py` (D3); `harness/end_d4.py` + `harness/tools/d4_implied.py`,
  `d4_inlineeq.py`, `d4_search.py`, `d4_lex.py`, `d4_micro.py`, `d4_kit.py` (D4, D4P, D4S). The router runs them after the style rewrite
  (`harness/router.py` `end_dialect_step`, `end_ops_step`, `end_d4_step`), each accept-gated against the row's final. `run_final.py`
  gains `--bets` (the list, frozen in `plan.json` and each shard's `config.json`; a resume with another set is refused).
- **The run-2 fixes** (README, Fixes of closed run 2): `infra/refhb/make_ref_heartbeats.py` with `infra/refhb/envfix.py` (the `... in`
  chain edit; Lean's heartbeat-limit error is not taken for a timeout) and the same edit before staging in `run_final.py run`
  (`--no-envfix`); `harness/agent.rescore_best`; `harness/router.no_headroom_of`; `harness/autobrief.sweep` on idle slots; `harness/router.stage_local_refs` with
  `scorer/score.py` `LRA_LOCAL_REF` (the router's own stages score against the run's references);
  `infra/closed_package/install_envs.sh` restores files the env fix edited (its marker) before its build check.
- **The bets we did not ship**, default off: B2 (Terra at a stall), B3 (an Argon restart) and D1 (a profiler change), no evidence of gain in
  our paired test on 12 final-benchmark rows; R2 (5 review rounds) and R3 (no tail), skipped without a test; and the two-arm bet test (`--backend azure-vertex`, `infra/closed_package/bets_test.sh`,
  `bets_readout.py`), which runs on development deployments.
- **Files**: 17 new code files (the passes, `infra/refhb/envfix.py`, the bet test's two files); 11 changed (`harness/agent.py`,
  `autobrief.py`, `endstage.py`, `hx_heldout.py`, `profile.py`, `router.py`, `harness/tools/__init__.py`, `scorer/score.py`,
  `infra/closed_package/install_envs.sh`, `run_final.py`, `infra/refhb/make_ref_heartbeats.py`); the other 123 byte-identical to the
  previous export's (122 here: the exemplar file stays withheld). `env_fixes/envfix.py` (run 1's hand workaround) is gone: run 2's reference step makes that edit itself.
- **`README.md`**: the passes and the fixes (top), the reference step (section 2), the env fix and `--bets` bullets (section 3), the
  new files (section 8), section 9 = the steps of run 2, then run 1's.

## Changed in the previous export (b5f036ab, closed official run 1)

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

The file list is the package's own definition of what a run needs, the same rule as the previous exports: run 1's 134 files (now
all from this commit, `infra/refhb/make_ref_heartbeats.py` included), the 17 new code files of run 2 (the three passes and their tools,
`infra/refhb/envfix.py`, the bet test's `bets_test.sh` and `bets_readout.py`) and the 3 of run 3 (D4C, D4N, their prefilter): 154 files.
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
`harness/style_rw_exemplars.json` (sha256 `c03ffd730e950d93...`, byte-identical to the commit) was exported, but it is withheld from the
public repository (as since 2026-11-01): 153 of the 154 files are here. The organizers receive it in the submitted
code zip. Without it the style rewrite step cannot run (README, the style rewrite).

## Staging edits (the only differences from the commit)

No line of logic changed. Every edit of a code file keeps its line count, so line numbers in the code match the commit. Two layers
(neither touches `infra/refhb/make_ref_heartbeats.py` or `infra/refhb/envfix.py`, which are byte-identical to the commit):

**1. Export redactions** (the same policy and the same 62 line edits as the previous export, at this commit's line numbers):
- **Comments, docstrings and help texts**: warm-up row names, nicknames and their measured moves replaced by "a dev row" or a generic
  phrase (`harness/agent.py` 354, 355, 361, 362, 372, 373, 380, 381, 539, 632, 914, 1780, 2224, 2250; `harness/architect.py` 132, 134,
  178; `harness/goals.py` 3; `harness/hb_rewrite.py` 61, 71, 78, 1154, 1155; `harness/router.py` 19, 173; `harness/leantools.py` 51,
  218, 219; `harness/mine.py` 32, 313, 358, 359; `harness/lemma_search.py` 4, 5, 6, 601; `harness/oracle_rules.py` 6, 7;
  `harness/postpass.py` 28; `harness/profile.py` 3; `scorer/compile.py` 7; `harness/tools/t6_transpile.py` 2;
  `harness/tools/t7_defer.py` 3; `harness/review.py` 452); references to notes on other entries removed (`harness/agent.py` 2988,
  `harness/hb_rewrite.py` 2, `harness/cards.py` 63, `harness/hx_heldout.py` 1516); statistics and ruling files of internal held-out sets
  removed (`harness/hb_rewrite.py` 59, 60; `harness/hx_heldout.py` 12, 19, 246, 247; `harness/inrun.py` 2; the refusal message of
  `harness/discover.py` 163; `harness/tools/c2_lemvar.py` 8; `infra/closed_package/run_final.py` 107); development host names and paths
  removed (`harness/lemma_search.py` 54, 56; `harness/workbench.py` 6).
- **`harness/runaway_guard.sh` 11**: the guard log's default path was a development home directory; it is now
  `probe/runaway_guard.log` of the checkout. The package always passes `GUARD_LOG`, so a run never uses the default.
- **`probe/b63/r10_candidate.json`**: the development copy's documentation keys (every key starting with `_`, which the end stage's
  loader ignores) are removed and the description is rewritten. `harness/endstage.load_config` returns identical values for both
  files; the file's sha256 (recorded in each run's config) changes from `fecbf742...` to `29976efe...`.

**2. Public-release scrub** (the tool that prepared this repository's history for publication, run on this folder with `scrub.py dir`;
[`../NOTICE.md`](../NOTICE.md), "Edits for public release", describes it): 164 lines in 37 files, comments, docstrings, help texts, log
messages and one refusal message only; plus 12 lines in 6 files of the code new since run 1 where the scrub's check found
attributions of decisions that its rules do not rewrite, edited by hand the same way (`harness/dialect.py` 16, `harness/end_d4.py` 12,
14, `harness/router.py` 3825, 3829, `harness/tools/d4_implied.py` 34, 37, `harness/leak_scan.py` 88,
`infra/closed_package/bets_test.sh` 2, `infra/closed_package/run_final.py` 187, 190, 212). Development notes and attributions of decisions (with their quotes) removed, workflow ids
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
- **`REPLICATE.md`** (2026-11-04): the steps that replicate our upload (README.md, "How to replicate our upload").
- **`run_host/`**: the scripts of our run hosts (README section 9, [`run_host/README.md`](run_host/README.md)); not package code, not
  read by it. Copied as they ran, comments scrubbed.
