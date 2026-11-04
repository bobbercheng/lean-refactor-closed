# CPU post-passes of 2026-10-13: 90.47 -> 90.55 with no API spend

After the run was paused (local mean 90.47, snapshot `paused402-20261012T014625Z`, [README.md](README.md) section 1), four
deterministic, model-free post-passes were applied to the run's own stored bests on 2026-10-13. None of them calls a model, so
the API spend is unchanged: **$31.84 billed in total, at most $2.6215 billed on any problem** (identical to the pause). Each pass
keeps a rewrite only if the whole proof compiles on every listed toolchain with compatibility (Z) unchanged and scores strictly
higher; every kept proof was re-checked through the standard checker and recorded as a verified record. This entry was **not
submitted**.

| Pass | Code | Run id | Kept | Summed gain |
|---|---|---|---|---|
| 1. Lexer normalizer: `fun x =>` -> `λx =>`, `f (g x)` -> `f $ g x`, bare trailing `fun` arguments, `<\|` -> `$` | `harness/normalize.py --bests wu-sol`, then `probe/normalize/record_wusol.py` | `wu-hx-sol-normalize1` | 7 of 15 rows | +0.81 |
| 2. Transfer lane: rules, spans and closers mined from this run's own bests only (no other line's proofs), compiled on every row | `harness/transfer.py --work-root harness/hwork/wu-sol --run-id wu-hx-sol-xfer1 --ops normalize --jobs 2` | `wu-hx-sol-xfer1` | 9 hits | +0.29 |
| 3. Heartbeat polish: `?`-certificates turned into `only` lists, unused lemmas pruned | `harness/hb_polish.py --work-root harness/hwork/wu-sol --run-id wu-hx-sol-polish1` | `wu-hx-sol-polish1` | 1 row | +0.04 |
| 4. Heartbeat micro-normalizer: `rw` -> `rewrite`, `simp only` -> `dsimp only`, `simp_rw` / `repeat rw` -> `simp only`, `use` / `exists` -> `refine` / `exact`, `with_reducible` inside `first` | `harness/hb_rewrite.py --work-root harness/hwork/wu-sol --run-id wu-hx-sol-hbrewrite1 --deadline-s 7200 --max-compiles 24` | `wu-hx-sol-hbrewrite1` | 1 row | +0.11 |
| Total | | | 10 rows changed | +1.25 summed = **+0.08 mean: 90.47 -> 90.55** |

Before pass 3, heartbeat profiles of five rows were taken with `probe/solattack/profile_seeds.py` (CPU only;
`profiles/profiles-wusol-weak.json`); they inform later work and did not change any proof.

## Per-row changes (local scores; snapshot `paused402` -> `postpass`)

| Problem | Before | After | Tokens | Heartbeats |
|---|---|---|---|---|
| `Binius.BinaryBasefold.fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius` | 91.52 | 91.65 | 207 -> 203 | 1,806 -> 1,790 |
| `Cslib.CCS.bisimilarity_congr_choice` | 87.03 | 87.30 | 72 -> 70 | 397 -> 396 |
| `Cslib.LambdaCalculus.LocallyNameless.Fsub.Typing.progress` | 85.76 | 85.92 | 127 -> 125 | 6,942 -> 6,944 |
| `Electromagnetism.ElectromagneticPotential.time_deriv_time_deriv_electricField_of_isExtrema` | 83.24 | 83.54 | 347 -> 341 | 6,771 -> 6,647 |
| `FieldSpecification.WickAlgebra.ι_timeOrderF_superCommuteF_eq_time` | 86.74 | 86.89 | 254 -> 259 | 7,967 -> 7,595 |
| `fundamental_theorem_of_variational_calculus'` | 91.58 | 91.61 | 119 -> 119 | 1,348 -> 1,337 |
| `interleaved_affine_gaps_imply_tensor_gaps` | 92.99 | 93.07 | 98 -> 97 | 1,293 -> 1,279 |
| `putnam_1964_a4` | 96.82 | 96.86 | 136 -> 134 | 2,073 -> 2,073 |
| `putnam_1964_b2` | 99.26 | 99.27 | 25 -> 25 | 1,055 -> 1,047 |
| `putnam_1995_a3` | 95.88 | 95.96 | 181 -> 173 | 1,131 -> 1,122 |

The other five rows are unchanged. Scores are local (our scorer); on the submitted snapshot the official worker read 0.05 lower
than the local prediction (89.46 vs 89.51), so expect about 90.50 on the worker.

## Where everything is

| Path (relative to `warmup/`) | Content |
|---|---|
| `probe/heldout/wu-hx-sol/snapshots/postpass-20261013T192012Z/` | `submission.jsonl` (the 15 proofs after the passes, the format of the earlier snapshots) and `scores.json` |
| `postpass_20261013/runs/<run id>/verified.jsonl` | every kept proof with its numbers and provenance (`normalized` / transfer / polish / hb-rewrite markers) |
| `postpass_20261013/logs/` | the passes' logs (counts and per-row lines) and the normalizer's per-row report (`normalize_wu-sol.jsonl`) |
| `postpass_20261013/transfer/` | the transfer lane's mined mechanisms, hits and dispositions |
| `postpass_20261013/states_after/` | each problem's state file and best proof after the passes |
| `postpass_20261013/profiles/` | the heartbeat profiles (block costs and the statement's heartbeat floor) |
| `postpass_20261013/code/` | the code that ran, see below |

## Code

The passes ran in the run's worktree at project commit `e830d933` (`probe/normalize/record_wusol.py` from the main checkout at the
same commit). `postpass_20261013/code/` holds that commit's files needed by the four passes (import closure of `normalize.py`,
`transfer.py`, `hb_polish.py`, `hb_rewrite.py`, `record_wusol.py`, `profile_seeds.py`), separate from the run's own code in
`harness/` (section 4 of [CODE_VERSIONS.md](CODE_VERSIONS.md) is unchanged). Staging edits, as for the first upload:

- Comments, docstrings and help text that named internal evaluation work outside this warm-up were generalized (38 places).
- `harness/transfer.py` and `harness/discover.py`: the guard strings that refuse mining runs of internal evaluation sets now use
  neutral prefixes (`internal`, `internalpool`); this only changes which run ids are refused and has no effect on warm-up runs.
- `harness/hx_heldout.py` is an extract: only `_kill_marked`, which `transfer.kill_own` calls at shutdown.
- Not included (not needed by these passes): the Claude Code and Codex drivers, `prompt_v2.py`, `exemplars.py`, `cc_meter.py`.
  `transfer.py` imports `prompt_v2.review_for` inside a `try`, so without it a row is never treated as having a pending review.

To re-run a pass on the paused state, copy the paused run's work root and run the commands above from a checkout of `code/` with
the Lean environments of section 6 of [README.md](README.md); compile in a memory-capped process (each compile waits for memory in
`scorer/memgate.py`).
