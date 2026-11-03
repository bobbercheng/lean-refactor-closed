# Vexorium closed-track package: README for the organizers

This folder is the closed-track final as one self-contained package: the code, the session container, the environment installer and
the one command that turns a benchmark rows file into the upload file. It is a clean export of one reviewed commit plus one standalone tool
and the post-step's files
(see [CODE_VERSION.md](CODE_VERSION.md)), not the development history: the code of our closed official run on the final benchmark
(2026-11-01, commit `b5f036ab`), with the reference-heartbeats tool that run used (`infra/refhb/make_ref_heartbeats.py` of `f5cdaa42`).
It is not byte-identical to that code: it keeps the export's comment and docstring redactions and one file is withheld (section 8,
**Byte identity**). Section 9 lists the steps of that run. **Our closed upload is that run's output after the post-step**
(section 10, added 2026-11-03): one $0, model-free, accept-gated pass over the run's merged `submission.jsonl`, a command of its own
(`infra/closed_package/post_step.py`, running `harness/open_post.py` and `harness/post/` of our development commit `5cb18d3b`) that
runs after `run_final.py` has ended and changes neither the run nor its files.

## How to replicate our upload

**[REPLICATE.md](REPLICATE.md)** has every step with its expected output, wall time and cost, a $0 dry run to try first, and how our
run compares. The chain, from this folder made its own git checkout (section 2), on Linux with Docker and systemd user units:
```bash
infra/closed_package/install_envs.sh ROWS.jsonl && infra/closed_package/build_image.sh            # section 2
python3 env_fixes/envfix.py "$(pwd -P)" ROWS.jsonl --apply --backup ~/lra-envfix-backup             # 5 rows' env files (section 9)
python3 infra/refhb/make_ref_heartbeats.py --rows ROWS.jsonl --out ~/lra-in/heartbeats.jsonl --allow-missing   # sections 3, 9
export OPENROUTER_API_KEY=...                                                                        # >= $3.00 x rows of credit
python3 infra/closed_package/run_final.py run --rows ROWS.jsonl --heartbeats ~/lra-in/heartbeats.jsonl --out ~/lra-final   # ~17 h
python3 infra/closed_package/post_step.py --out ~/lra-final                                          # section 10: $0, 15-21 min
python3 harness/final_merge.py --rows ROWS.jsonl --check ~/lra-final/submission.post.jsonl          # the file to upload
```
Upload `~/lra-final/submission.post.jsonl`. A rerun gives other proofs (the models sample); the post-step alone is deterministic.

## The pipeline

What it does: for every benchmark row, OpenAI GPT-6.1 Sol (through OpenRouter) refactors the seed proof in tool-using sessions (compile,
scratch Lean, grep, multi-variant checks) inside a container until the row has spent $1.25; OpenAI GPT-6.1 Terra (through OpenRouter,
the same key) runs the sessions of the later budget steps, toward $1.90 and toward $2.75; model-free stages (CPU only) clean the proof
between steps; Google Gemini 4 Argon (through OpenRouter) reviews the result with the row's remaining room under the cap (an edit of the
review that does not compile gets one repair turn, and the compiling edits are also combined: **review repair + stack**, below); then
the **Terra tail**: every row that still has at least $0.20 of room under the cap gets up to 3 more Terra sessions whose budget is
exactly that room, and their proof is kept only if it compiles on every listed toolchain and scores higher; then a model-free end stage
searches mechanical rewrites that compile on every listed toolchain and score higher, and then polishes the best proof of ONE other
approach among the row's candidates the same way (**approach pick**, below); finally the **style rewrite** (below): Sol is asked once or
twice to rewrite the row's final into the shortest idiom the scorer rewards, with at most $0.30 of the row's remaining room and at most
15 minutes, and its proof is kept only if it compiles on every listed toolchain, passes the axiom audit and scores at least 0.05 higher
on a paired read. The output is one proof per row. Everything starts from the seed proofs in your rows file: no stored proofs and no
per-problem knowledge, with one exception in the style rewrite. Its prompt carries nine fixed example pairs (a proof before and after a
rewrite into the scored idiom) from our development runs, in `harness/style_rw_exemplars.json` (withheld from this public tree; see
the style rewrite below). A pair is left out only when its theorem name equals the name of the row being rewritten. 5 of the 9 pairs are
proofs of 3 warm-up theorems that are also rows of the final benchmark, so each of those rows does not see its own pairs. One pair is of
a theorem that is a final row under a later upstream name: the name check does not leave it out, so that row's prompt shows a proof
of its own theorem.

**The post-step (section 10) is not independent of the final benchmark.** Its four ops were developed on the final benchmark after its
release (2026-11-01 06:48 UTC), like the D3 and D4 end-stage passes of our closed runs 2 and 3: `implied`, `inlineeq` and `closerprep`
are D4's rules R1 (with D4P's point-free spellings), R2 and D4C, vendored from our closed-run-3 code (development commit `402c44d2`;
`inlineeq` uses D3's simpconst helper). Their main source is our offline research: uncapped agent sessions of other closed models
(GPT-6 Astra, Claude Opus 5.5, Fable 5.1, Gemini 4 Argon), run outside the $3 cap on the 5 final-benchmark rows where this run was at
a structural ceiling; none of their proofs is in any upload or package. The rules were distilled by comparing those research proofs
and session histories with this run's finals of those rows, then sized and smoke-tested on this run's 60 finals. `kskip` was written on
2026-11-03 for the kernel-skip construct (`set_option debug.skipKernelTC true in` before `decide +kernel`), which our open-track run 3
had banked on one final-benchmark row and our same-day review of the final rows with heavy kernel checks measured on others. Which
output we uploaded after the step was chosen from runs of the step on our runs' finals (in sample; section 10). The ops hold no row
names and no proof text of any row.

**Sorry guard.** Every compile of the run, the session containers' included, has Lean's `warn.sorry` forced on
(`LRA_FORCE_WARN_SORRY=1`; a project whose lakefile turns it off, e.g. PhysLib, would otherwise accept a proof that depends on `sorryAx`
without the literal word, such as Lean's `impossible by ...` from v4.31 or `stop`), and before a row's line is written its final proof is
audited on every listed toolchain (`#print axioms` with `warn.sorry` on; a proof that uses `sorry` is passed over for the row's next
verified proof, else its seed). Heartbeats are unchanged by the flag.

**Auto-brief opening.** Every row's first session runs with the CPU auto-brief, which may install the brief's start proof as
`candidate.lean` after the session's own compile of it. When it does, the session's opening message shows that start as the current
best (the best-so-far sentence, the candidate.lean block, its linter hints, a start check) instead of the seed it was rendered from;
when no start is installed the opening is unchanged. A fix of 2026-10-31 ([CODE_VERSION.md](CODE_VERSION.md)).

**Review repair + stack.** Every shard's review runs with `--review-repair 3 --review-stack` (`run_final.R6_ARGS`), the flags exactly as
measured in our A/B (15 warm-up rows, the final's pipeline forked at the review: +0.049 per row paired, 3 rows up, 0 down), plus one
later fix (the last item below):
- **Repair:** an edit the reviewer proposed that does not compile gets one repair turn from the same model (Gemini 4 Argon), at most 3
  per row per review round, in the reviewer's order. The turn shows only the edit, the compile error and the local goal. The corrected
  edit is compiled once, like any single edit; a give-up, a still-failing or a refused repair changes nothing.
- **Stack:** after each review round, every edit that compiled and scored within 0.02 of the round's starting proof (gains below the
  review's +0.05 single-edit bar included) is applied together and checked in one full compile on every listed toolchain (a short
  greedy fallback when the combination fails). A stack that compiles everywhere, keeps the statement, has no forbidden construct and
  scores higher becomes the round's output when it beats the round's own result, and is kept as a candidate (`review_stack`) that the
  end stage measures back to back with its incumbent under the same acceptance rule as every other candidate. The stack makes no model
  call; a stack that fails, fails a toolchain or raises leaves the round's result and keeps nothing.
- **Money path:** a repair call is a review call. It is priced at its worst case at the cap price (Argon at its announced $4 / $20 per
  1M; input bound + output cap, at most 8,000 output tokens) **before** it is sent, inside what the row's review budget (the row's room
  under $3.00) has left, and is not sent when it does not fit (`harness/review.py`: `_repairs` -> `PricedCaller(kind="repair")` ->
  `call_retry` -> `plan`, the same gate as the review's own calls). Each answered call is booked once into the review's spend and the
  row's ledger (and `review_calls.jsonl`, type `repair`); a refused request (an HTTP 4xx) books nothing.
- **A verified stack reaches the end stage on every row** (a fix made after the A/B and kept; **the A/B's +0.049 was measured without
  it**): the measured code kept a verified stack for the end stage only when the review's input proof carried the row's ladder
  workspace, and dropped it when that proof came from a crossover or cleanup step (2 of the A/B's 6 rows with verified stacks). This
  package keeps it in the row's ladder workspace then too, so the end stage reads it. It makes no model call and only adds end-stage
  candidates, each accepted only under the end stage's paired rule; on the A/B's rows it would have added 4 stacks, each equal to or
  below what the end stage already read there ([CODE_VERSION.md](CODE_VERSION.md)).

**Approach pick.** Every shard's end step runs with `--end-approach on --end-approach-groups 1 --end-approach-seconds 1200`
(`run_final.APPROACH_ARGS`; `harness/approach_pick.py`). After the end stage has settled a row's proof, the row's candidates (everything
the end stage read) are grouped by approach (the lemma names and top-level case splits a proof uses, the library's constructor names
left out; complete-link Jaccard >= 0.5), and the best proof group other than the final's (the one with the best stored score) is
polished by the same model-free end stage in a child process. The child has a **hard wall cap of 1200 s per row**, never more than what
is left of the end stage's own 3600 s clock (sweep + tool phase); a polish still running at the cap is killed with every process it
started and its work is dropped. The polished proof replaces the row's proof only when it compiles on every listed toolchain, keeps the
statement, has no forbidden construct, reads higher back to back on the end stage's meter, passes the axiom audit (no `sorry`) and reads
higher again on a second back-to-back read; otherwise the row's proof stays byte for byte. No model call; an error or timeout leaves the
row's proof. Measured out of sample on our recorded banks (64 samples): 4 improved, 60 unchanged, 0 worse, +0.011 per row (95% CI +0.001
to +0.024); the cap keeps all 4 of those gains; added wall per row p50 466 s, p95 1200 s. The style rewrite below runs after the
approach pick with its own wall cap (counted on the end stage's own seconds), so a row's end step takes at most its end stage's time +
1200 s + 900 s (+ 2100 s while the end stage used <= 1500 s of its 3600 s clock).

**Style rewrite.** After every row's end stage, `harness/style_rw.py` (`run_final.STYLE_RW_ARGS` = `--style-rw on --style-rw-usd 0.30
--style-rw-preset gpt-6.1-sol-main --style-rw-effort medium --style-rw-exemplars <sha16 of harness/style_rw_exemplars.json>
--style-rw-wall-s 900`; design, build and validation in our development repository):
- **Calls:** GPT-6.1 Sol (OpenRouter, the ladder's preset, pinned at its list price) is shown the row's statement, its current final
  with its token / heartbeat reading and goal states, the scoring rule with the row's exchange rate, a short guide to the idiom
  (`unhygienic` auto names, positional cases, uniform closers, `.imp` pre-shaping, `exists`) and the nine compiled before / after pairs
  (minus any pair whose name is the row's; see above), and asked for four complete declarations; a candidate that does not compile gets
  one repair call with the exact error; a second round is seeded with the first round's results. When the budget allows, up to two other
  verified proofs of the row from the run's own candidates get the same treatment, one at a time.
- **Acceptance:** every candidate is compiled on every listed toolchain with the sorry guard and the forbidden-construct check; the best
  one is audited (`#print axioms`), polished by the same model-free end stage, and read back to back with the current final on the same
  meter: it replaces the final only when it scores at least 0.05 higher there, otherwise the final stays byte-identical.
- **Money path:** the row's budget for the step is min($0.30, $3.00 - the row's spend at the cap price - $0.001). Each call is priced at
  its worst case (its whole input uncached plus its output cap, at the cap price) **before** it is sent, the output cap is shrunk to what
  the budget has left, and a call below the floor is not sent (`harness/review.py` `PricedCaller`, the review's own gate, kind
  `style_rw`). A failed attempt that may have been billed (a 5xx, a broken stream) is charged its worst case once; a refused request
  (4xx) and a rate limit (429, waited out) book nothing; a confirmed pin of the preset ends the step at $0. The step's spend is booked
  once into the row (`rows/<row>.json` step `style_rw`, the row ledger's `style_rw` label, `review_calls.jsonl` type `style_rw`); a
  shard killed inside the step books the row's whole step budget on the resume. Nothing of the step can push a row past $3.00.
- **Wall cap:** the whole step (calls, compiles, audit, polish, confirm read) gets at most min(900 s, the row's end-stage clock left =
  the end config's wall budget per start, 3600 s, minus the seconds the row's end stage used) from its start. Inside, no new call starts
  with less than 300 s left, compiles are clipped to the time left, the polish is stopped at the cap minus the audit and confirm
  reserve, and the confirm read runs only when it fits. The router waits for the step at most that long: anything still running then is
  abandoned (no later call is sent, the final stays byte-identical, the calls' spend is booked, or the whole step budget when a call
  was in flight). A row with less than 300 s on that clock skips the step at $0.
- Before any spend the router checks that every module the step imports is present in the checkout (`style_rw.preflight`).
- Every call's full prompt and reply is written to `trajectories/style_rw-<row>.jsonl` in the shard's run directory.
- Frozen into each shard's `config.json` (`style_rw`; a resume with other values is refused). `STYLE_RW_ARGS = ()` turns it off (no key, no
  code of the module runs).
- **Withheld file.** The nine example pairs are in `harness/style_rw_exemplars.json` (sha256 `c03ffd730e950d93...`; these first 16 hex
  digits are the value `run_final.STYLE_RW_EXEMPLARS` freezes). The file is withheld from the public repository and its history. The organizers receive
  it in the submitted code zip. Without it, this public tree cannot replicate the style rewrite step: with the frozen flags every shard's
  router refuses at start, before any model call (`--style-rw on: missing in this checkout: harness/style_rw_exemplars.json`), and the
  $0 dry run of section 7 refuses the same way. `STYLE_RW_ARGS = ()` in `infra/closed_package/run_final.py` runs the rest of the
  pipeline without the step; that is not the pipeline of our official run.

Inference spend is capped at **$3.00 per row** by the code itself: every request is priced at its worst case before it is sent, metered at
the higher of OpenRouter's billed cost and the list price after it, and a row's spend survives a crash or restart. The tail spends the
room the review leaves, so a row can end just under $3.00 at the cap price (its sessions' budget top is $3.00 - $0.001).

## 1. Requirements

| item | minimum | what we ran |
|---|---|---|
| OS | Linux x86-64 or aarch64 with systemd (user units, cgroup v2 with the memory controller delegated: `loginctl enable-linger $USER`) | Ubuntu 24.04 x86-64 (Azure D64ads_v7); Ubuntu 24.04 aarch64 |
| CPU | 16 vCPU | 64 vCPU (32 cores x SMT 2) |
| RAM | 64 GB | 256 GB |
| disk | ~250 GB free for the Lean environments of 60 rows (the 15 warm-up rows alone need ~117 GB of envs + ~30 GB of toolchains; LeanPool ~25 GB), plus ~20 GB for the run | 495 GB OS disk + local NVMe scratch |
| software | Docker (the user in the `docker` group), git, curl, Python >= 3.11 (`tomllib`; Ubuntu 24.04's 3.12 is fine, 22.04's 3.10 is not) with `requests`, ripgrep, zstd; elan installs Lean | Docker 29, Python 3.13 |
| network | GitHub (project repositories, Mathlib cache), Docker Hub (python:3.13-slim), openrouter.ai | |
| key | one OpenRouter API key with >= $3.00 x rows of credit (60 rows: $180); it is used for `openai/gpt-6.1-sol`, `openai/gpt-6.1-terra` and `google/gemini-4-argon` | |

The speed and memory knobs are derived from the host (`python3 harness/host_knobs.py --shards 4 --rows 15` prints them and why); a
host below the minimum still runs, only slower.

## 2. Install (once per host)

The package must be the root of its own git checkout (a git worktree of another checkout also works, but then read the note at
the end of section 9): the sessions' worktree is checked out from that checkout's HEAD (a sparse
whitelist of the code and the rows), the preflight requires `harness/`, `scorer/` and `llm/` to be clean, and every run records the
commit. So copy this folder out and commit it once:

```bash
git clone --branch closed-final-run1-post-20261103b https://github.com/bobbercheng/lean-refactor-closed.git lra-closed   # this code's tag
mkdir ~/lra && cp -a lra-closed/final/. ~/lra/ && cd ~/lra   # this folder becomes the repository root
#   or from the code zip, which also holds harness/style_rw_exemplars.json (withheld from the repository, section 7):
#   unzip -q vexorium-closed-final-run1-post.zip && mkdir ~/lra && cp -a vexorium-closed-final-run1-post/. ~/lra/ && cd ~/lra
git init -q && git add -A && git -c user.name=lra -c user.email=lra commit -qm "closed final package"
git config extensions.worktreeConfig true          # once, before the first run: see the note below (added 2026-11-03)
python3 -c "import requests" || sudo apt-get install -y python3-requests   # (install_envs.sh tries pip, then apt)
infra/closed_package/install_envs.sh ROWS.jsonl     # tools, elan, every (project, toolchain) environment the rows pin; ends "INSTALL DONE ok=N failed=0"
infra/closed_package/build_image.sh                 # the session container image lra-agent:1; ends "IMAGE OK lra-agent:1"
```
**Worktree setting (once per checkout; added 2026-11-03).** Each shard checks out its sessions' worktree with a sparse checkout, and
the shards start in the same second. In a checkout without `extensions.worktreeConfig`, each of those sparse-checkout setups first
writes that setting into the shared `.git/config`, and they can collide on its lock: the shard exits at once ($0) and uses its one
automatic restart (`--max-restarts 1`, after 300 s). Setting it once after `git init`, as above, removes the race (4 parallel setups
the way the shards make them, 100 tries each on a fresh repository: 17 failures without the setting, 0 with it; measured for our later
closed runs' package, whose worktree setup is the same). The $0 dry run of this package on 2026-11-03 (section 7, without the
setting) hit it once: one shard's first start exited in its sparse-checkout setup and its restart ran the row. The run itself is
unchanged by the setting.
`install_envs.sh` derives the environment list from the rows (`infra/closed_package/envs_from_rows.py`: one entry per project and
pinned toolchain, LeanPool included), clones each project, checks out a worktree at each pinned commit, fetches Mathlib's prebuilt
cache and builds the rows' modules. It is re-runnable (finished environments are kept); `CHECK_ONLY=1` only reports which environments
are present at their pins. `RESTORE=1` first restores our public archives of the warm-up pins (anonymous HTTPS,
`infra/sync/restore_envs.sh`), which saves most of the build time when the final reuses them.
A project we have not seen needs its repository URL: `infra/closed_package/envs_from_rows.py --url NAME=<git url>` (and a scorer
entry; the run refuses an unknown source before it starts).

**Example input.** `data/benchmark_warmup.jsonl` (the 15 public warm-up rows) and `data/benchmark_heartbeats.jsonl` (their reference
heartbeats) are the rows-file and heartbeats formats the package expects; `--rows data/benchmark_warmup.jsonl --heartbeats
data/benchmark_heartbeats.jsonl` runs the warm-up set. The code also reads these two files and `data/reference_heartbeats_local.json`
as its reference data: keep them in place.

## 3. Run (one command)

```bash
export OPENROUTER_API_KEY=...          # or --key-file PATH; written to ~/.config/vexorium/openrouter_api_key (mode 600), never printed
python3 infra/closed_package/run_final.py run --rows ROWS.jsonl [--heartbeats HEARTBEATS.jsonl] --out ~/lra-final
```
Run it in `tmux` (or any long-lived shell): it launches the work as systemd user units and waits for them.
- **The default is the closed final**: Sol sessions up to $1.25 per row, Terra sessions toward $1.90 and $2.75, the Argon review, the
  Terra tail, the end stage of `probe/b63/r10_candidate.json`, the sorry guard, the $3.00 cap. Nothing needs to be chosen;
  `run_final.py` holds the frozen pipeline in one place (`ladder_args()` / `router_args()`), and the rehearsal-only options below are
  refused without `--fake-model`.
- `--heartbeats`: the reference heartbeats in the warm-up release's format (`{"name", "heartbeat"}` lines). Without it, a row's own
  `heartbeat` field is used, else the seed is measured on its newest toolchain through the scorer before the launch (minutes). The
  final benchmark's reference heartbeats are not published: `infra/refhb/make_ref_heartbeats.py` writes such a file from the rows
  (section 9), and a file passed here is used as is. The rows staged in `data/final/` keep the heartbeats they were staged with: the
  same rows staged again are left unchanged, `--force-stage` included, so move `data/final/` aside (when no run reads it) before
  passing other heartbeats for the same rows.
- **Shards.** The rows are split into 4 balanced shards (`--shards 4`, the default; `--shards N` for another count); each shard is one
  router (unit `lra-final-s<k>`, its own run directory, compile slots, session scratch and memory-pressure guard `lra-final-s<k>-guard`).
  60 rows give 4 x 15.
- Before anything is spent the command checks: the rows (schema, statements, sources), every pin's environment, the image, elan,
  systemd, a leak scan, disk space and the key. Any failure refuses with exit 2 and says what to do.
- `run_final.py plan --rows ROWS.jsonl` shows the shard split, the knobs, the pipeline and the exact router command without launching.
- Every shard's router command ends with the tail's frozen flags `--tail-preset gpt-6.1-terra-main --tail-min-room 0.10 --tail-effort medium --tail-max-sessions 3`
  (`run_final.TAIL_ARGS`): exactly the flags of the measured tail (section 5).
- Every shard's router command also carries the review's frozen R6 flags `--review-repair 3 --review-stack` (`run_final.R6_ARGS`,
  right after the tail's): exactly the measured TREAT arm's (`config.json` `review_r6` = `{"repair": 3, "stack": true, "stack_eps": 0.02}`;
  a resume with other values is refused).
- Every shard's router command also carries the end step's frozen approach-pick flags `--end-approach on --end-approach-groups 1
  --end-approach-seconds 1200` (`run_final.APPROACH_ARGS`, right after `--end-dual-start`; `config.json` `end_approach` = `{"groups": 1,
  "seconds": 1200.0}`; a resume with other values is refused).
- Every shard's router command then carries the style rewrite's frozen flags (`run_final.STYLE_RW_ARGS`, right after R6's; `config.json`
  `style_rw` = `{"usd": 0.3, "preset": "gpt-6.1-sol-main", "effort": "medium", "exemplars": "<sha16>", "wall_s": 900.0}`; a resume with other values, or a
  changed or missing `harness/style_rw_exemplars.json`, is refused before any spend).
- Every shard's environment carries `LRA_FORCE_WARN_SORRY=1` (`run_final.SORRY_GUARD_ENV`, the sorry guard above), passed into the
  session containers too.
- The rows are staged into `data/final/` of the checkout (the pipeline reads them there at every phase). A second, different rows file
  in the same checkout is refused until no run uses the first: then pass `--force-stage` once (or use another clone).

## 4. Outputs (`--out`, default `~/lra-final`)

| path | what |
|---|---|
| `submission.jsonl` | **the upload file**: exactly one `{"name", "proof"}` line per row, in the rows file's order |
| `merge_report.json` | per row: the shard its line came from (or `seed` and why), the shard writer's verdict; per shard: its final state |
| `shards/s<k>/` | each router's run directory: `finals.json`, `submission.jsonl` (its rows), `submission_check.json` (per row the writer's verdict and the axiom audit of the line written, `audit_counts`), `summary.json` (spend per row, exit reason, the `tail` block, the `review_r6` block: repairs sent / compiled / paying, stacks verified / picked, rows whose end stage read a stack), `router.log`, `rows/`, `review_calls.jsonl`, `tail.json` / `tail_tops.json` (the tail's rows, each row's budget top, its worst case), `ladder-tail.log` (the tail's sessions) |
| `logs/` | `launcher.log`, `s<k>.router.out`, `s<k>.guard.log` |
| `hx/` | the sessions' workspaces and full trajectories (`hx/finalc-final-s<k>-hx/probe/runs/`) |
| `plan.json` | the shard split, the knobs and how they were derived |

**How `submission.jsonl` is produced.** Every shard's router keeps its own `submission.jsonl` complete at all times (seed lines at
start, each row's verified result as it finishes, every row again on any exit), so a merged file is valid even after a crash. When the
shards have finished, `run` merges them (`harness/final_merge.py`): per row the owning shard's line if it is non-empty, starts with the
row's statement byte for byte and has no forbidden construct, else the row's seed; one line per row in the rows file's order; the
written file is read back and checked. `run_final.py merge --out ~/lra-final` redoes the merge alone, and
`python3 harness/final_merge.py --rows ROWS.jsonl --check FILE` checks any upload file against the rows.

## 5. Wall time and cost

| host | sessions at once | expected wall for 60 rows |
|---|---|---|
| 64 vCPU / 256 GB | 16 (4 per shard) | ~6-8 h for the paid steps (bound by API latency), the model-free stages overlap; ~10 h end to end, plus ~0.5-1 h for the tail (below) |
| 16 vCPU / 64 GB | 4 (1 per shard) | ~1-1.5 days, plus ~2 h for the tail |

**The tail's wall time.** A shard's tail starts when its slowest row has finished its review (every row's room is known only then) and
the end stage of its rows runs after the tail (before b70 each row went on to its end stage as soon as its own review ended). The tail
runs one session per row at a time, at most `--workers` (4 per shard on the 64 vCPU host, 1 on the 16 vCPU one) at once. Measured (the
fork test below, 11 rows, 6 sessions at once): the sessions took 295-893 s each (10-37 turns), the tail 24 min, then the acceptance
and the end stage of those 11 rows 29 min. On the 64 vCPU host a 15-row shard with ~11 eligible rows needs ~25-35 min of tail sessions,
so the shards (which run side by side) end ~0.5-1 h later than without the tail; on the 16 vCPU host ~2 h later. No default limit cuts
the tail or the end stage short: the tail's sessions run as a ladder phase under `--ladder-timeout 172800`, and the shard units' 60 h /
the wait's 61 h are far above the ~11 h expected.

Cost: at most $3.00 per row by construction (60 rows: <= $180); the measured candidate-final (arm B without the tail, 15 warm-up rows)
spent $2.67 per row on average and $2.79 at most ($2.97 at most at the cap price). The tail (`--tail-preset gpt-6.1-terra-main
--tail-min-room 0.10 --tail-effort medium --tail-max-sessions 3`) then spends part of the room the review left: in its fork test on arm
B's final states it ran on the 11 of 15 rows with at least $0.20 of room, one session each, $1.62 in all ($0.10-0.18 a row), and the
rows ended at $2.78 on average ($2.80 at most) reported, $2.86 on average and **$2.97 at most at the cap price** (no row over the cap).
By construction a tail row can reach $3.00 - $0.001 at the cap price: expect up to just under $3.00 per row (60 rows: just under $180).
Score: +0.024 per row paired over the 15 rows (bootstrap 95% CI +0.001 to +0.056).
**Review repair + stack** (b75; its A/B forked the same arm B at the review, without the tail): CONTROL 91.75, TREAT 91.80, **+0.049
per row paired** (95% CI +0.00 to +0.13; 3 rows up, 0 down). The repairs: 69 sent, 19 compiled, 3 paid alone; $0.585 billed, **$1.17
at the cap price over 15 rows ($0.078 a row)**; 10 stacks verified, 7 became their round's output. The review spends its repairs from
the same room as its own calls, so it leaves a little less room for the tail: the room after the review was $0.187 a row on average
with R6 against $0.220 without (9 vs 8 of 15 rows with at least the tail's $0.20). The cap is unchanged: every row ended at $2.98 at
most at the cap price.

**Approach pick** (model-free): at most 1200 s more per row inside the end step (out of sample on recorded banks: p50 466 s, p95
1200 s, mean 573 s; 11 of 64 samples reached the cap), i.e. roughly +0.5-1 h per shard with 3 rows at once; $0.
**Style rewrite**: at most $0.30 a row more at the cap price, inside the same $3.00 cap (the room the tail and the review leave; rows at
the cap get nothing). Its validation replay ran the packaged step on recorded runs (Sol, medium effort, the same prices; 2026-10-30): on
10 held-out library rows taken at their end-stage finals with $0.56-0.63 spent, +0.750 a row (95% CI +0.32 to +1.23; 7 accepted, 0
worse; $0.17 a row), and with the wall cap as built, estimated from the replay's recorded timings, +0.697 (+0.554 when every row that
took longer than 15 minutes counts as abandoned); on the 15 warm-up rows at the final's own end-stage finals and room ($2.68-2.98
already spent, as the final's rows will arrive), +0.030 a row (2 accepted, 4 rows without room for one call; $0.105 a row). Expect the
warm-up figure in the final. Wall time: at most 15 min per row (the wall cap above; less when the row's end stage used most of its
clock). These are estimates from 15-row runs; the 60-row wall has not been measured end to end.

**$0 rehearsal of this package with the tail** (2026-10-28, in our development repository): a fresh clone of the release branch, the
`--fake-model` path (a scripted local endpoint, no key, $0), 3 warm-up rows in 2 shards, `--runner local`. The tail fired on all 3 rows
(each with $0.3379 of room after the review: one Terra session, $0.21, budget top $2.9629); every Terra request of the tail came after
its shard's last review call (fake endpoint request log, matched by generation id); every row ended at $2.853 reported / $2.871 at the
cap price; a shard's router stopped by SIGTERM inside its tail resumed on the next `run` to the same saved tops (no second room: the row
that had spent its session got none, the other one its first), booking each row's tail once; `submission.jsonl` 3 lines, check OK, exit 0.
**The sorry guard** was rehearsed the same way (2026-10-28: the fake in its adversarial mode, below; 4 warm-up rows incl. a PhysLib row,
2 shards): exit 0; on the PhysLib row the sessions' proofs that depend on `sorryAx` without the word were rejected and the review's
`stop` edit gained nothing; nothing that depends on `sorry` was banked or written. **The review repair + stack** was rehearsed the same
way on this package (2026-10-29: the fake in its R6 mode, below; 2 warm-up rows incl. the PhysLib row, 2 shards): exit 0; every review
round sent repair turns (10 answered, each booked once into the review's spend and the row's ledger; 3 refused with HTTP 400, booking
nothing); on the row with 3 toolchains a stack of 3 edits verified on all of them, was kept as `review_stack` and was read by the end
stage; on the PhysLib row the tail still fired; the rows ended at $2.82 and $2.91 at the cap price.

### Counted and timed limits (what a different host can change)

Counted limits do not depend on the host's speed: the budget steps ($1.25, $1.90, $2.75 per row at the cap price) and the $3.00 cap; at
most 30 ladder rounds (`--max-rounds 30`); the brief's 80 compiles per row; the review's 3 rounds of 5 candidates (16,000 output tokens
per call) inside the row's room under the cap, with at most 3 repair turns per round (8,000 output tokens each, inside the same room)
and one stack per round (one full compile on every toolchain; when that fails, a fallback of at most 6 single-toolchain compiles and one
more full check); the tail's at most 3 Terra sessions per row (`--tail-max-sessions 3`, each at most 40 turns), only on a row with at
least $0.20 of room (Terra's session floor; `--tail-min-room 0.10`), each with the row's room as its budget; the end stage's 6
re-measured candidates and its per-family and per-phase compile caps (600 compiles per phase); the style rewrite's at most 2 rounds of 4
candidates plus one repair per failing candidate (at most 4 per round; 24,000 / 12,000 output tokens per call) per unit, up to 3 units
(the final + 2 other proofs), inside min($0.30, the row's room), its one end-stage polish and its single paired confirm read, all inside
its wall cap.

Timed limits stop work by the clock, so a slower or busier host does less work under them than our runs did:
| limit | value | where |
|---|---|---|
| model-free cleanups between steps | 1800 s per row and cleanup | router `--clean-deadline-s` (default) |
| end stage: sweep phase, tool phase | 1800 s each per row (or 600 compiles, whichever comes first) | `probe/b63/r10_candidate.json` `budgets` |
| end step's approach pick (one other approach group's polish) | 1200 s per row, hard (killed and dropped at the cap), never more than what is left of the 3600 s above | `run_final.APPROACH_ARGS` |
| style rewrite: the whole step (calls, compiles, polish, confirm) | min(900 s, the row's end-stage clock left) from the step's start; what runs past it is abandoned | `run_final.STYLE_RW_WALL_S`, `harness/style_rw.py` |
| style rewrite: new model calls | none with less than 300 s of that cap left | `harness/style_rw.py` `CALL_MIN_LEFT_S` |
| style rewrite: the polish of its best candidate | stopped at the cap minus the audit and confirm reserve (`end_stage(stop_at=...)`), inside the end stage's own 1800 s per phase | `harness/style_rw.py`, `probe/b63/r10_candidate.json` `budgets` |
| brief (seed measurement before the first sessions; round-1 sessions wait for it) | 36000 s for a shard's rows; rows not done then go on without a brief | `--auto-brief-timeout 36000` |
| one ladder phase; also the tail's sessions (one phase) | 172800 s (48 h) | router `--ladder-timeout 172800` |
| each Lean compile | its own timeout (300-900 s); a compile waits at most 1800 s for memory | `scorer/`, `harness/` |
| one model call on HTTP 429 | 1800 s of retries | `harness/agent.py --rate-limit-budget` |
| a shard's unit, the `run` command's wait | 60 h, 61 h | `run_final.py --runtime-hours 60 --wait-hours 61` |

In our 15-row development runs the end stage's 1800 s limits ended 24 of 105 sweep phases and 10 of 105 tool phases before their
compile caps, and 14 of 405 cleanups hit their 1800 s (7 runs). The measured candidate-final ran 15 rows in one router with
32 compile slots; the default 4-shard final runs 60 rows on the same host with 8 slots per shard, so these limits can bind more often
there than in the measured run.

## 6. Resume after a crash

Run the same command again. Finished shards are kept; an unfinished one resumes from its run directory (spend so far, steps done,
best proofs); the merge is redone. The command itself restarts a shard that ended unfinished once (`--max-restarts`). To follow a run:
`run_final.py status --out ~/lra-final`; to stop it: `run_final.py stop --out ~/lra-final` (the routers write their outputs on the way
out; a `run` still waiting restarts nothing after a stop, and the next `run` resumes); to merge what exists: `run_final.py merge --out ~/lra-final`.
An `--out` belongs to one kind of run: `run` refuses to resume a `--fake-model` rehearsal's directory as a real run (or the reverse).
A shard stopped inside its tail resumes it to the same budget top: each row's top is saved before its first tail session (step
`tail_started`) and never recomputed, so a restart gives no row a second room, and the tail's spend is booked once (the growth of the
row's spend since that step). A run directory started before b70 (no tail in its frozen `config.json`) is not resumed by this version:
the router refuses a resume that adds the tail.

Exit codes of `run`: 0 every shard finished and `submission.jsonl` checks; 5 the file checks but a shard did not finish (its rows carry
their best-so-far or seed lines: run again to resume); 3 the wait limit passed; 1 the merged file fails its check; 2 refused before launch.

## 7. A $0 dry run (no key, no model calls)

In this public repository the dry run and the one command of section 3 stop at router start: they need
`harness/style_rw_exemplars.json`, which is withheld here (see "Withheld file" above; the organizers have it in the code zip).

`--fake-model` replaces OpenRouter with a scripted local server (`infra/closed_package/fake_openrouter.py`, on the docker bridge; no
key is read or sent) and runs the whole pipeline: staging, preflight, shards, briefs, sessions in containers, the model-free stages,
the review, the Terra tail, the end stage, the writers (with the axiom audit) and the merge. Its proofs only improve through the
model-free stages. The rehearsal-only options shrink the $0 budgets so it finishes in about an hour on a few rows (two rows of the
warm-up file, a strata row and a PhysLib row, two shards):
```bash
sed -n '1p;4p' data/benchmark_warmup.jsonl > /tmp/dry_rows.jsonl
python3 infra/closed_package/run_final.py run --rows /tmp/dry_rows.jsonl --heartbeats data/benchmark_heartbeats.jsonl \
  --out /tmp/lra-dry --tag dry --shards 2 --runner local --fake-model --shared-slots 1 --workers 1 --jobs 1 --router-mem-gb 16 \
  --brief-row-workers 1 --brief-compile-workers 1 --brief-docker-memory-gb 12 --agent-docker-memory-gb 12 \
  --runtime-hours 5 --wait-hours 4.5 --restart-delay 60 --report-every 300 --ladder-extra "--auto-brief-budget 4" \
  --router-extra "--clean-stages free --clean2-stages free --clean-deadline-s 300 --end-config probe/b66/smoke_end.json"
```
It ends `exit 0: every shard finished; the upload file is complete` with `/tmp/lra-dry/submission.jsonl` (one line per row); each
shard's `submission_check.json` holds the axiom audit of its lines (`audit_counts`) and its `summary.json` the tail (`tail`), the
approach pick (`end.approach`; the fake's proofs stay the seeds, so a row's candidates usually form one approach and the pick is
skipped there). With
`LRA_FAKE_SORRY_PROOFS=1` in the command's environment (`--runner local`) the fake turns adversarial: its sessions write proofs that
depend on `sorryAx` without the word `sorry` and its review proposes `stop`, which the sorry guard must reject. With `LRA_FAKE_R6=1`
instead, the fake's review proposes edits by generic text rules (a broken edit, a type-ascription drop, deletions of tactic lines, a
comment) and answers the repair turns (the broken edit with a compiling fix, the other failed edits with a give-up or an HTTP 400
refusal), so the review's repair and stack run (the `review_r6` block of each shard's `summary.json` counts them). With
`LRA_FAKE_STYLE_RW=1` the fake also answers the style rewrite's calls (rewrites that are unchanged, `:= by unhygienic`, broken or
re-typed, and repairs that drop the broken line), so the step runs end to end (the `style_rw` block of each shard's `summary.json`
counts it); add `--tail-min-room 0.40` to `--router-extra` so that the fake tail leaves the step room for a call. `--runner local` keeps
the shards as child processes of the command (no per-shard memory caps), so run it inside a memory-capped unit (`systemd-run --user -p
MemoryMax=48G ...`) on a shared host. With an existing `~/.config/vexorium/openrouter_api_key` the dry run leaves it alone (the
containers mount it read-only; nothing reads it); without one it writes a placeholder and removes it at the end.

## 8. What is in this folder

| path | what |
|---|---|
| `REPLICATE.md` | the steps that replicate our upload, in order, with their expected outputs, wall time and cost (added 2026-11-03) |
| `infra/closed_package/` | `run_final.py` (the one command), `install_envs.sh` + `envs_from_rows.py` (environments), `Dockerfile` + `build_image.sh` (session image), `fake_openrouter.py` (dry run) |
| `harness/` | the pipeline: `router.py` (per shard: budget steps, cleanups, review, the tail, end stage, the style rewrite, writer), `final_writer.py` (the writer and its axiom audit), `hx_heldout.py` (the session ladder), `agent.py` (one tool-using session), `autobrief.py` (the CPU brief), `postpass.py`, `review.py`, `endstage.py`, `approach_pick.py` (the end step's approach pick), `style_rw.py` (the style rewrite; its nine example pairs, `style_rw_exemplars.json`, are withheld from this public tree: see the style rewrite above), `final_rows.py` / `final_merge.py` / `host_knobs.py` (package helpers), `leak_scan.py` (preflight), `runaway_guard.sh`; `harness/tools/` the session tools and end-stage families, `harness/tools/tables/` their generated tables (each states its generating rule and query) |
| `scorer/` | the official metrics: lexer, compile and heartbeat measurement, forbidden constructs, score |
| `llm/` | the model clients (the final uses the OpenAI-compatible one, through OpenRouter) and the junk-answer guard |
| `bank/` | the per-row candidate store |
| `probe/b63/r10_candidate.json` | the frozen end-stage configuration of the final |
| `probe/b66/smoke_end.json` | the dry run's end-stage configuration (tiny budgets; never a real run's) |
| `probe/verify_candidates.py` | toolchain ordering used by the pipeline |
| `infra/refhb/make_ref_heartbeats.py` | writes a reference-heartbeats file for a rows file (a command of its own; pass its output with `--heartbeats`) |
| `data/` | the warm-up rows and reference heartbeats (example input and reference data) |
| `envs/` | where `install_envs.sh` puts the Lean environments; keep its tracked `README.md` (it says why) |
| `infra/sync/restore_envs.sh`, `infra/vast/envs_kaggle.tsv`, `infra/vast/harness_envs.json` | the optional `RESTORE=1` path of the installer |
| `env_fixes/envfix.py` | the env-side workaround for rows under a `... in` modifier chain, applied on our run host (section 9); not package code |
| `infra/closed_package/post_step.py`, `harness/open_post.py`, `harness/post/`, `harness/post_support.py` | the post-step (section 10): the command, the step (written for our open-track package, hence its name), its four ops and their helpers, and the pieces of the open package's module that the step uses |

The code supports more than the final uses (other sets, drivers and opt-in levers, e.g. the end-stage family `c2` in
`harness/tools/c2_lemvar.py`, which the final's end-stage configuration does not enable); the final's choices are the ones `run_final.py`
writes. Comments in the code cite internal design notes and development records (`docs/...`, `probe/...`) that are not part of this
export.

**Byte identity.** The code zip we submit to the organizers (2026-11-03) holds the exact files of the frozen commit `b5f036ab` and the
tool of `f5cdaa42`, and the post-step's files (last bullet). This public folder keeps the export's comment and docstring redactions
instead. Compared file by file with those commits:
- 89 files are byte-identical, among them `infra/refhb/make_ref_heartbeats.py` (against `f5cdaa42`), all of `data/`,
  `scorer/forbidden.py`, `harness/style_rw.py` and `harness/tools/tables/`. One of the 89, `harness/style_rw_exemplars.json`, is
  withheld from this public tree (the style rewrite, above), so 88 of them are here.
- 44 code files differ only by the export redactions: comments, docstrings, help texts and log or refusal messages, with the same line
  counts ([CODE_VERSION.md](CODE_VERSION.md), Staging edits). Three of them also change a value that the final never uses: the
  development-only Vertex AI path (`harness/agent.py`, `llm/anthropic_vertex.py`) reads its GCP project from `LRA_GCP_PROJECT`, and the
  default log path of `harness/runaway_guard.sh` points into the checkout (the package always passes `GUARD_LOG`).
- `probe/b63/r10_candidate.json` has its documentation keys removed (the end stage's loader ignores them and returns the same values;
  sha256 `29976efe...` here, `fecbf742...` in the run), and `.gitignore` is the export's own.
- `README.md` is the commit's `infra/closed_package/README.md`, moved and rewritten; `CODE_VERSION.md`, `REPLICATE.md`,
  `envs/README.md` and `env_fixes/envfix.py` are new.
- The post-step's files (added 2026-11-03, section 10): `harness/open_post.py` and the 8 files of `harness/post/` are those of our
  development commit `5cb18d3b` (branch `open-post`), byte for byte in the code zip; here 3 of them carry the export's redactions of
  decision attributions in comments and docstrings (4 lines, same line counts). `harness/post_support.py` (verbatim pieces of that
  commit's `harness/open_package.py`, listed in its docstring) and `infra/closed_package/post_step.py` are new, the same here and in
  the zip. No file the run imports changed, but the router's code hash covers every `.py` file under `harness/`, so a run of this
  version records another `code_hash` than our run's `config.json`.

So a run from this folder records a different router code hash and `end_config_sha256` than our run's `config.json`, and the sessions'
read-only copy of the harness shows the redacted comments and docstrings, not the run's.

## 9. The closed official run (2026-11-01): what we ran

Our closed official run on the final benchmark (60 rows) ran this folder's code on the host of section 1 (Azure D64ads_v7, Ubuntu
24.04 x86-64, local NVMe scratch), from a checkout at the exported commit with the tool copied in (untracked: the preflight's
cleanliness check covers `harness/`, `scorer/` and `llm/` only). The steps, in order:

```bash
infra/closed_package/install_envs.sh ROWS.jsonl                      # INSTALL DONE ok=17 failed=0 (17 environments, 6 projects; 12 min:
                                                                       # 11 built (8 new pins + LeanPool rc3 at its pin + new modules in
                                                                       # shared environments), 6 already present)
python3 harness/final_rows.py check --rows ROWS.jsonl --envs          # 60 rows, 0 errors, 0 warnings, no environment missing or off its pin
# the reference heartbeats, in a memory-capped user unit (a user unit starts in $HOME: give it the checkout, PATH, HOME, absolute paths)
systemd-run --user --wait --pipe --collect -p MemoryMax=120G -p OOMPolicy=continue -p CPUWeight=50 --unit lra-refhb-final \
  --working-directory=$PWD -E PATH=$PATH -E HOME=$HOME \
  python3 infra/refhb/make_ref_heartbeats.py --rows $PWD/ROWS.jsonl --out $PWD/HEARTBEATS.jsonl --jobs 16 --allow-missing
python3 infra/closed_package/run_final.py run --rows ROWS.jsonl --heartbeats HEARTBEATS.jsonl --out ~/lra-final --tag final \
  --scratch-root /scratch/work/final --shards 4 --runner systemd     # no knob overrides: the knobs are derived from the host
```
- **Reference heartbeats:** 55 of the 60 rows were measured at first (the pinned `lean` binary on the built libraries, heartbeats
  under `Elab.async false`, plus 2; warm-up rows reuse their published values). The other 5 got the tool's flagged placeholders
  (`--allow-missing`) instead of stopping the run.
- **The 5 rows and the env-side workaround (applied 07:43 UTC, about 16 min into the run).** All 5 declarations sit directly under a
  chain of `... in` modifiers (`omit ... in`, `set_option ... in`, `open ... in` lines above an `omit`). `scorer/compile.py`
  `split_modifiers` moves only `open ... in` lines, docstrings and attributes below the heartbeat-measuring command and stops at the
  first `omit`/`set_option ... in`, so the rest of the chain binds to the measuring command and the declaration compiles without it.
  This is in the measured compile the whole pipeline uses (sessions, accept, end stage, the tool), so until the workaround every
  candidate on these 5 rows failed. Workaround, no change to the frozen code: `env_fixes/envfix.py` strips the trailing ` in` from that
  chain in the environment's copy of each row's file, on every pin (same line count; the compile truncates the file after the
  declaration, so the now-global commands reach only that declaration). Apply it only to environments whose modules are already built
  (`lake build` compiles whole files). Then the tool re-measured the 5 rows directly (211576 / 21247 / 163584 / 60889 / 9702
  heartbeats) and the placeholders were replaced in the run's heartbeat files (input, staged `data/final/heartbeats.jsonl`, the shard
  worktrees' `data/benchmark_heartbeats.jsonl`). Rows: `HermitianMat.inv_convex`, `Lambda.callOfLFunc_eraseMetadata_congr`,
  `ProximityGap.RS_exists_nonzero_kernelVec_of_det_eq_zero_natDegree_le_one`, `ProximityGap.RS_jointAgreement_of_goodCoeffs_card_gt`,
  `Vlasov.transportedIntegral_continuousOn`. The proper package fix (move the whole chain below the measuring command) is pending.
- **Run:** `run_final.py run` with the frozen pipeline and no option beyond those above (the dry-run options of section 7 are
  rehearsal-only); the env-side workaround above is the only change to its inputs.

**Lesson from our first launch (environments of a worktree).** The sessions' ladder worktrees (`harness/hx_heldout.py`
`setup_worktree`) link `envs/` from the MAIN working tree of the repository (`git rev-parse --git-common-dir`), not from the checkout
the command runs in. Our official checkout was a git worktree of a larger checkout, and `install_envs.sh`, run in it, built the 8
toolchain pins new in the final rows inside that worktree's `envs/`; the main checkout's `envs/` lacked them and held one LeanPool
environment at an older commit than the rows' pin. The first launch was refused at once: all 4 shards stopped within a second with
"no built environment in the worktree for ..." before any session or model call ($0 spent). We linked the 8 environments into the main
checkout's `envs/`, moved the off-pin LeanPool environment aside for one at the pin, and relaunched (07:26 UTC). So: when this folder
runs as a git worktree, build the environments in, or link them into, the main checkout's `envs/` at the rows' pinned commits (or run
from a checkout of its own, as in section 2, where both are the same directory).

## 10. The post-step (2026-11-03): our upload is run 1's output after it

**What we uploaded.** Our closed upload of 2026-11-03 (17:23 UTC) is closed official run 1's merged `submission.jsonl` (section 9;
sha256 `8f0ac8590a48...`, uploaded alone on 2026-11-02 as a probe: Arena 85.66) after this post-step: 4 of the 60 lines changed,
Arena **86.85** (60/60 compiled). The step is a command of its own that runs after the run has ended; the organizers' guidance of
2026-11-03 is that small changes after a run need no rerun as long as README.md documents how to run the system, which this section
does.

**What it does.** `infra/closed_package/post_step.py` builds the step's input from the run's `--out` and runs `harness/open_post.py`
(written for our open-track package, hence its name; the same step runs on both tracks) on it. The step is $0 (no model, no key),
deterministic and accept-gated. Four ops propose rewrites of a row's final, and every candidate is measured like an end-stage candidate:
- `kskip`: when the proof's last tactic is `decide +kernel`, `set_option debug.skipKernelTC true in` goes in front of it, in place
  (`kskip:inplace`), or the body becomes `unfold P` and that line, P the head predicate of the statement (`kskip:unfold`).
- `implied` (D4's rule R1 with D4P's point-free spellings): a `decide`-family closer decides the hypothesis Q of a library theorem
  `Q -> P` (or `P <-> Q`) that a query of the row's environment finds, instead of the goal P.
- `closerprep` (D4C): `conv_rhs => reduce` (or lhs / both) before a `decide`-family closer, alone and together with a minimal drop of
  the simp lemma list before it (the proposals chosen by one measured file of variants).
- `inlineeq` (D4's rule R2): an equation proved inline in a simp lemma list becomes `← by simpa using h ARGS` from its own hint or that
  hint's siblings in the environment, plus its pure trims.

Each op reads only the proof, the statement and the row's own environment (no row name, table or proof text).

**Gate (never harm).** A candidate replaces the row's proof only when all of these hold, measured on the end stage's meter
(`harness/endstage.Meter`, the direct path) against the reference heartbeats file: it starts with the row's exact statement followed by
`:=`; it passes `scorer/forbidden.py` (unchanged); its reading on the primary toolchain scores higher; it compiles on every listed
toolchain (Z 100); a fresh back-to-back re-reading of the current proof and the candidate still passes `scorer.accept.decide` with the
candidate's worse reading against the current proof's better one and a strictly higher score; its rounded score is above the row's
stored score; and the sorry audit (`#print axioms` with `warn.sorry` forced on; the sorry message check alone where the row's file is a
Lean module) does not flag it. Anything else, an exception, a timeout or a budget stop included, leaves the row's line byte for byte.
Per row: at most 3 passes over the ops (in the order kskip, implied, closerprep, inlineeq; at most 4 / 12 / 3 / 6 readings per op and
pass), 120 compiles and 2400 s; every row runs at once and no row starts after 7200 s. A row where no op has a site is not compiled.

**About `debug.skipKernelTC`.** The option makes Lean skip the kernel's check of the declaration, so the decision that `decide +kernel`
leaves to the kernel is not checked: with the option, a false decidable proposition is accepted too (our test with Lean v4.32.0,
v4.34.1 and v4.35.0-rc3: `2 + 2 = 5` by `decide +kernel` fails; with the option it compiles and `#print axioms` lists no axiom, so the
audit above cannot tell). The option is neither on the Arena's forbidden list (the Space's list as of 2026-10-28) nor in
`scorer/forbidden.py`, and the Arena compiled and graded the 4 kernel-skipped rows of our upload. Each of those 4 statements also has a
kernel-checked proof in the run's own output: its line in `submission.jsonl`, which compiles on every listed toolchain.

**Run it.** After `run_final.py run` has ended, from the same checkout:
```bash
python3 infra/closed_package/post_step.py --out ~/lra-final     # the run's --out
```
- **Input:** `<out>/submission.jsonl` (read, never written) and, per row, the stored score, tokens and heartbeats of its shard's final
  (`shards/s<k>/finals.json`) when that final is the line's proof; the rows and reference heartbeats the run staged in `data/final/`
  (checked against `plan.json`), or `--rows ROWS.jsonl --heartbeats HEARTBEATS.jsonl`.
- **Settings** (the defaults are our run's): every row at once (`--jobs`); this host's compile slots (`--compile-slots`; default
  `harness/host_knobs.py` for one shard, min(32, physical cores): 32 on the host of section 1); the step's wall 7200 s, a row's 2400 s
  and 120 compiles; the sorry guard (`LRA_FORCE_WARN_SORRY=1`); git's `safe.directory` for this process tree; and the reference
  heartbeats file only (the warm-up table `data/reference_heartbeats_local.json`, which the run's own meter reads for the 13
  warm-up-named rows, is not read).
- **Outputs:** **`<out>/submission.post.jsonl`, the file to upload**: one `{"name", "proof"}` line per row in the rows' order, written
  only when it passes `harness/final_merge.py`'s check against the rows and every line that differs from `submission.jsonl` is a row
  the step adopted (otherwise exit 1 and no file: upload `submission.jsonl`). `<out>/post_report.json`: per row the status, the sites,
  the readings before and after, the ops adopted, compiles and seconds, and the block `post_step` (input and output sha256, settings).
  `<out>/post_step/`: the step's input `proofs.jsonl`, its own output `proofs.post.jsonl` (each adopted row with its measured score)
  and every decision in `post/decisions.jsonl`. The command refuses (exit 2) when `<out>/post_step/` exists: move it aside to run the
  step again.
- **Wall:** 17-21 min on the host of section 1 (32 compile slots); a row stops at its 2400 s (plus the compile in flight). It needs no key,
  no model and not the withheld file (section 7). `--problems NAME ...` restricts it to some rows (a smoke test).
- **To disable it**, do not run it: `submission.jsonl` stays the run's upload file. The ops have no switches of their own (the op
  list is `harness/open_post.ORDER`).

**Our run of it** (2026-11-03 15:21:59-15:43:11 UTC, on the host of section 1, from a checkout of our development commit `5cb18d3b`:
`python3 harness/open_post.py --jobs 60` with 32 compile slots; this command reproduces its input and settings). Input: the merged
`submission.jsonl` with each row's stored score from the shards' `finals.json` (sha256 `5c5cdc991a7d...`, byte-identical to what this
command writes as `post_step/proofs.jsonl`); the rows file of section 9; the reference heartbeats of our open-track run's measurement of
the same rows (equal to section 9's file on 36 rows, within 0.05 % on the other 24). 1,271 s, 128 compiles; 54 rows without a site,
2 kept, 4 changed:

| row | stored score before -> after (our meter) | ops adopted |
|---|---|---|
| `FTheory.SU5.ChargeSpectrum.isPhenoClosedQ5_viableCharges` | 42.89 -> 72.19 | kskip:inplace |
| `FTheory.SU5.ChargeSpectrum.isPhenoClosedQ10_viableCharges` | 43.85 -> 72.19 | kskip:unfold |
| `PauliMatrix.pauliContrDown_mul_pauliContr_mul_pauliContrDown` | 73.89 -> 79.29 | kskip:inplace, then inlineeq:simpa |
| `PauliMatrix.pauliContr_mul_pauliContrDown_mul_pauliContr` | 70.34 -> 78.66 | kskip:inplace, then inlineeq:simpa |

60-row mean on our meter: 85.709 -> 86.898. The upload file (the `{"name", "proof"}` lines of the step's output) has sha256
`1a39b98f30a3...`; Arena 86.85 (60/60 compiled). On the same input without `kskip` (a test-only setting, not shipped) the step changed
the same 4 rows with `implied`, `closerprep` and `inlineeq` alone (49.99, 49.99, 77.03, 74.23): mean 86.047.

**This package reproduces it.** Release smoke, 2026-11-03 17:47:26-18:04:14 UTC on the same host: this folder's code zip unpacked and
installed as in section 2, the rows and heartbeats above staged as `run_final.py` stages them, then
`python3 infra/closed_package/post_step.py --out <a copy of the run's --out>` with the defaults. The same input (`5c5cdc991a7d...`),
the same 4 rows with the same ops and scores, `post_step/proofs.post.jsonl` byte-identical to our run's output (`959b16122894...`) and
`submission.post.jsonl` byte-identical to the uploaded file (`1a39b98f30a3...`); 1,009 s and 107 compiles (the number of `closerprep`
variants measured per file depends on the row's measured compile seconds, so the compile count varies between runs).
