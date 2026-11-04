# Code versions of the warm-up GPT-6.1 Sol run

This file covers:

- which project commit each round of the run used
- what changed between those commits
- how the code in this folder differs from them
- how to reproduce the recorded sequence

Paths are relative to `warmup/`. The run itself is described in [README.md](README.md). The project's commit history is
not part of this repository: commit times and parentage below come from it, and the two run-relevant diffs are included
in `code_history/`.

## 1. Which commit each round ran

The agent sessions ran in a git worktree of the project (`~/source/lra-ab/wu-hx`). The runner (`harness/hx_heldout.py`)
and the helper scripts in `probe/heldout/` ran from the project's main checkout.

| Rounds | agent.py and scorer (project commit) | Evidence |
|---|---|---|
| 1–4, fresh f2, f3, f4 (and the aborted round 5) | `579e3634` | `jobs.log` 20:00:21 worktree line |
| 8 and fresh f8 | `0672126b` | `jobs.log` 23:20:14 worktree line. Both processes started at 23:20, before the 23:37:52 deploy. |
| 9, 10, 11, rescue f12, 13, 14 | `08002e91` | `jobs.log` 23:37:52 `DEPLOY` line. Round 9 is the first round launched after it; sessions already running kept the code they had loaded. |

**The runner** ran from the main checkout:

- It was launched at 20:00:21 at `579e3634`.
- It was restarted at 23:20:14 with the stuck-only rescue rule in the working copy. That rule was committed as `f7d41ecf`
  at 23:22:24, about two minutes later.
- So the code of the running runner cannot be shown to be byte-identical to `f7d41ecf`.
- The rule acted once, at the $2.00 milestone (00:23:56).

## 2. What changed during the run

All times are UTC on 2026-10-11. Each commit is the direct child of the one above it.

| Commit | Time | Run-relevant change | Diff in this folder |
|---|---|---|---|
| `579e3634` | 20:00:15 | the code the run started with | — |
| `0672126b` | 20:46:20 | none (no run-relevant file changed) | — |
| `f7d41ecf` | 23:22:24 | runner: a per-rung gain history and the stuck-only rescue rule. Memory gate: bounded waits (the reserve is waived after 600 s, and the gate gives up after 1,800 s). | `code_history/579e3634..f7d41ecf.diff` |
| `08002e91` | 23:36:43 | `agent.py`: a tool call cut off at the output cap inside its arguments is dropped from the history and replaced by a stub. The output cap is not raised when the cut tail is degenerate repetition. | `code_history/f7d41ecf..08002e91.diff` |

**Why the agent.py change matters.** The diff's own comment gives the reason. About this run before the deploy, it says:
"20 of 54 sessions had a turn cut at the 12k output cap, 22% of the run's spend".

- Each cut call stayed in the conversation and was re-sent on every later turn.
- That inflated the input and the budget gate's reserve.
- A replication that runs this code from round 1 therefore spends its budget differently in rounds 1–8.

**Checking the diffs against the files.** The diffs' `index` lines give git blob hashes:

| File | Before | After |
|---|---|---|
| `harness/hx_heldout.py` | `57dbb06e` | `9fa2da8c` |
| `scorer/memgate.py` | `10f96b88` | `5faa878e` |
| `harness/agent.py` | `3632e7e9` | `9e26cc07` |

`scorer/memgate.py` in this folder has blob hash `5faa878e`, the post-image. `harness/agent.py` and
`harness/hx_heldout.py` differ from their post-images only by the staging edits in section 3.

## 3. The code in this folder

The code is the project's committed `HEAD` at staging time. Every code file in it was compared with the run's worktree,
which was at `08002e91`. All are byte-identical, apart from three groups.

**Edits made at staging.** Five files were edited, in comments, docstrings and help text only, except for two small
changes to `harness/hx_heldout.py`:

| File | Change |
|---|---|
| `harness/agent.py` | Three comments and the `--closed-lessons` help string reworded. They had cited evaluation work outside this warm-up. |
| `harness/leantools.py` | Four comments reworded, for the same reason. The technical rationale is kept. |
| `harness/selftest.py` | One comment reworded, for the same reason. |
| `harness/hx_heldout.py` | The module docstring and the docstrings of `setup_worktree()` and `states()` were rewritten. Two small behaviour changes: **`SETS` keeps only the `warmup` entry**, and **`--set` defaults to `warmup`**. The default used to name a set that is not part of this repository. `Set()` loads only the chosen key, so with `--set warmup`, as in every command in [README.md](README.md), the runner behaves as it did. |
| `probe/heldout/resume_on_credits.py` | The docstring no longer states the account balance at the HTTP 402 stop. This script is not in the worktree; it was compared with the main checkout's copy. |

**Later than the run.** `submit/upload.py` gained `--user` / `--key-file` and first-upload key capture for this
submission, after `08002e91`. The run does not use it.

**Not in the worktree.**

- The `probe/heldout/*.py` helper scripts ran from the main checkout.
- `envs/pin_upstream.sh` was added at staging.
- `code_history/`, `leaderboard/problem_scores.json` and `harness/hwork/solknow/` were added at staging. They hold the
  runner inputs as scores only: [README.md](README.md) section 5, item 3.

**Not runnable as staged.** `harness/selftest.py` cannot run from this folder:

- it reads another line's work root (`harness/work/`)
- it needs the built Lean environments
- without the `anthropic` package, it needs `LRA_SELFTEST_OAI_ONLY=1`

## 4. Defaults that shaped what the model saw

The runner passes neither of these options. Both are defaults of `harness/agent.py` in every commit above.

- **`--closed-lessons`: on by default.** It appends the "five habits" block, general habits mined from the Claude Opus 5.5
  and GPT Astra lines, to every session's first message.
  - All 126 trajectory files of the run contain it.
  - `--no-closed-lessons` turns it off.
- **Upstream history: on by default.** For each project row, the opening message carries the `UPSTREAM` digest from
  `harness/leantools.py` (`upstream_digest`), and the model is pointed at `git log -p` on `envs/<project>.git-main`.
  - What this shows depends on the head of those clones. `envs/pin_upstream.sh` pins them to the heads the run saw:
    Strata `02f873ed7a89`, CSLib `ea16de32af9c`, PhysLib `bae4db68ef61` and ArkLib `35ddcaa83f68` ([README.md](README.md)
    section 6).
  - `--no-upstream-history` turns it off.

## 5. Reproducing the recorded sequence

A replication from this folder runs the `08002e91` agent code and the bounded memory-gate waits from round 1. The
recorded rounds 1–8 ran without them.

To reproduce the recorded sequence, patch `agent.py` and `scorer/memgate.py` back before the base commit (step 1) and
forward again while the second $2.00-rung round is running (step 2). In the recorded run, the deploy came during round
8, and round 9 was the first round to start on the new code.

**Step 1.** In the main checkout, before the base commit of [README.md](README.md) section 7.2 A:

```bash
patch -R -p1 < code_history/f7d41ecf..08002e91.diff
sed -n '/^diff --git a\/scorer\/memgate.py/,$p' code_history/579e3634..f7d41ecf.diff | patch -R -p1
```

**Step 2.** While the second $2.00-rung round is running:

```bash
patch -p1 < code_history/f7d41ecf..08002e91.diff
sed -n '/^diff --git a\/scorer\/memgate.py/,$p' code_history/579e3634..f7d41ecf.diff | patch -p1
git commit -qam "agent.py and memgate.py as in 08002e91"
git -C ~/source/lra-ab/wu-hx checkout -q --detach "$(git rev-parse HEAD)"
```

What the patches give:

- Both apply cleanly to the files in this folder.
- Reversed, `scorer/memgate.py` becomes blob `10f96b88`, the rounds 1–8 version.
- Reversed, `harness/agent.py` becomes the rounds 1–8 version apart from the staging comment edits.

The runner part of `579e3634..f7d41ecf.diff` is not needed:

- The recorded runner already had the stuck-only rule when it reached the $2.00 milestone, the only place the rule acts.
- The per-rung gain history it adds was backfilled for round 4 in the recorded run (`jobs.log` 23:20:25 note).
