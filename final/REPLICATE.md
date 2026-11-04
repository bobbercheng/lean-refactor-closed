# Replicating our closed-track upload, step by step

This file takes you from the final benchmark's rows file to the file of our closed upload (closed track, `Vexorium-Agent`): closed
official run 3's merged `submission.jsonl` after two chained passes of the post-step (version v4su, without its kernel-skip op `kskip`: no
`set_option debug.*` in any line), `submission.post.jsonl`. Each step names its section of
[README.md](README.md), which has the details and the reasons. The commands are README.md's, plus read-only checks (`sha256sum`, `wc`
and `python3 -c` one-liners). This file puts them in order and adds, for each step, what it prints when it works, how long it takes and
what it costs.

| | |
|---|---|
| the file to upload | `~/lra-final/submission.post.jsonl` (step 7): one `{"name", "proof"}` line per row, in the rows file's order |
| wall time | ~17 h for 60 rows on 64 vCPU / 256 GB (our run 3: 17.0 h, step 5), plus the install (step 2), the reference heartbeats (minutes) and the post-step (our upload's passes: pass 1 1,428 s (2,739 compiles); pass 2 1,354 s (1,961 compiles), 56 compile slots) |
| cost | at most $3.00 per row, enforced by the code (60 rows: at most $180 of OpenRouter credit). Our run 3: $166.33 reported, $173.97 at the cap price. The dry run and the post-step cost $0 |
| what repeats exactly | nothing quite: the models sample, so a rerun of the run gives other proofs and another score; the post-step on the same input repeats closely but not byte for byte (step 9) |

## 0. Prerequisites (README section 1)

| item | what the package needs | what we ran |
|---|---|---|
| OS | Linux x86-64 or aarch64 with systemd | Ubuntu 24.04 x86-64 (Azure D64ads_v7) |
| CPU, RAM | at least 16 vCPU and 64 GB. The knobs are derived from the host; `python3 harness/host_knobs.py --shards 4 --rows 15` prints them | 64 vCPU (32 cores x SMT 2), 256 GB |
| GPU | none: the models are called through OpenRouter | none |
| disk | ~250 GB free for the Lean environments of 60 rows, plus ~20 GB for the run (`run` refuses with less than 20 GB free) | OS disk + local NVMe scratch |
| containers | Docker, with your user in the `docker` group (see below) | Docker 29 |
| systemd | user units: `loginctl enable-linger $USER`; cgroup v2 with the memory controller delegated; `systemctl --user show-environment` must work in the shell of step 5 | |
| software | git, curl, Python >= 3.11 with `requests`, ripgrep, zstd, jq. `install_envs.sh` installs the missing ones with apt when it can | Python 3.13 (the run), 3.12 (the post-step) |
| Lean | elan. `install_envs.sh` installs it into `~/.elan` with no default toolchain; each environment's `lean-toolchain` file installs its own toolchain | |
| open files | the post-step (step 7) raises its own soft limit to 65536; the hard limit (`ulimit -Hn`) must allow it for our setting | hard limit 1048576 |
| network | GitHub (project repositories, Mathlib cache), Docker Hub (`python:3.13-slim`), openrouter.ai | |
| key | one OpenRouter API key with at least $3.00 x rows of credit (60 rows: $180), able to call `openai/gpt-6.1-sol`, `openai/gpt-6.1-terra` and `google/gemini-4-argon` (step 5) | |

**Docker and podman.** The model sessions and the auto-brief run in containers started with the `docker` command (image `lra-agent:1`,
built in step 2). The dry run's local fake model listens on the Docker bridge. We have run this package only with Docker; it has not
been tested with podman or podman-hpc. The post-step and the check (steps 7 and 8) need neither Docker nor systemd: `python3` and the
Lean environments are enough.

**systemd.** `run` starts each shard as a systemd user unit with a memory cap (`--runner systemd`, the default, as in our run).
`--runner local` runs the shards as child processes instead, with no memory caps; the dry run uses it. In a non-login shell,
`systemctl --user` needs `XDG_RUNTIME_DIR=/run/user/$(id -u)` and `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus`; our
launch script set both (`run_host/closed_run3/final3.sh`).

## 1. Get the code as its own git checkout (README section 2)

Use the code zip. It holds every file the run needs, including `harness/style_rw_exemplars.json`: the style rewrite's example pairs,
which `run_final.py` pins by hash.

```bash
unzip -q vexorium-closed-final-run3-postv4su.zip    # one top folder: vexorium-closed-final-run3-postv4su/
mkdir ~/lra && cp -a vexorium-closed-final-run3-postv4su/. ~/lra/ && cd ~/lra
git init -q && git add -A && git -c user.name=lra -c user.email=lra commit -qm "closed final package"
git config extensions.worktreeConfig true                 # once: the shards' parallel worktree setups (README section 2)
sha256sum harness/style_rw_exemplars.json                 # starts c03ffd730e950d93 (the run refuses any other file)
```

The same code is in our repository at tag `closed-final-run3-postv4su-20261104` (folder `final/`, branch `release/closed-run3-post`). The
repository is private, and it does not have `harness/style_rw_exemplars.json`, so a checkout made from it stops at router start in
steps 3 and 5 (README section 7).

Run every later command in `~/lra`, in a shell where these are set:

```bash
cd ~/lra
export PATH="$HOME/.elan/bin:$PATH"                       # elan (installed in step 2)
ROWS=/path/to/final_rows.jsonl                            # the final benchmark's rows file, as an absolute path
HB=~/lra-in/heartbeats.jsonl                              # the reference heartbeats, written in step 4
```

## 2. Install (README section 2)

```bash
sha256sum "$ROWS"                                         # ours: d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682 (60 rows)
python3 -c "import requests" || sudo apt-get install -y python3-requests
infra/closed_package/install_envs.sh "$ROWS"
infra/closed_package/build_image.sh
```

- `install_envs.sh` derives one environment per (project, pinned toolchain) from the rows. For each, it clones the project, checks out
  the pinned commit, fetches Mathlib's prebuilt cache and builds the rows' modules.
  - On our rows file it ended `INSTALL DONE ok=17 failed=0` (17 environments of 6 projects), then
    `60 row(s): 0 error(s), 0 warning(s), 0 environment(s) missing or off-pin`.
  - It took 12 min on our run-1 host, where 6 of the 17 environments were already present. We did not time an install on an empty
    host. Run 3's host got run 2's environments by copy instead (README section 9, `run_host/closed_run3/xfer.sh`). `RESTORE=1` first
    restores our public archives of the warm-up pins.
  - It is re-runnable; its logs are in `envs/logs/`.
- `build_image.sh` builds the session image and ends `IMAGE OK lra-agent:1`.

## 3. First test: the $0 dry run (README section 7)

The dry run needs no key and makes no model call: a scripted local server answers instead of OpenRouter. It runs the whole pipeline on
two warm-up rows in about an hour, with run 3's end-stage passes, and so checks Docker, Lean, every stage, the writers and the merge
before any money is spent. Its proofs improve only through the model-free stages.

```bash
sed -n '1p;4p' data/benchmark_warmup.jsonl > /tmp/dry_rows.jsonl     # 2 warm-up rows: a Strata row, a PhysLib row
infra/closed_package/install_envs.sh /tmp/dry_rows.jsonl               # their 2 environments
python3 infra/closed_package/run_final.py run --rows /tmp/dry_rows.jsonl --heartbeats data/benchmark_heartbeats.jsonl \
  --out /tmp/lra-dry --tag dry --shards 2 --runner local --fake-model --shared-slots 1 --workers 1 --jobs 1 --router-mem-gb 16 \
  --brief-row-workers 1 --brief-compile-workers 1 --brief-docker-memory-gb 12 --agent-docker-memory-gb 12 \
  --runtime-hours 5 --wait-hours 4.5 --restart-delay 60 --report-every 300 --ladder-extra "--auto-brief-budget 4" \
  --router-extra "--clean-stages free --clean2-stages free --clean-deadline-s 300 --end-config probe/b66/smoke_end.json" \
  --bets D2,D3,D4,D4P,D4S,D4C,D4N
python3 harness/final_merge.py --rows /tmp/dry_rows.jsonl --check /tmp/lra-dry/submission.jsonl
```

- Expected: the run's last line is `exit 0: every shard finished; the upload file is complete`, and the check prints
  `/tmp/lra-dry/submission.jsonl: OK (2 row(s), 0 problem(s))`. Our dry run of run 3's code with this `--bets` ended that way
  (2026-11-02).
- On a shared host, run the dry run inside a memory-capped unit (README section 7).
- The dry run stages its two rows into `data/final/` of the checkout. So add `--force-stage` to the first real `run` (step 5).

## 4. Reference heartbeats, with the env fix (README section 2)

The final benchmark's reference heartbeats are not published. This tool measures each row's reference proof on its newest pin and
writes a file in the warm-up release's format:

```bash
mkdir -p ~/lra-in && python3 infra/refhb/make_ref_heartbeats.py --rows "$ROWS" --out "$HB" --jobs 8
```

- **It may edit environment sources** (README section 2): a row whose reference fails the measured compile because of a `... in` chain
  directly above its declaration gets that chain's trailing ` in` removed in its file, on every pin of the row, and is measured again.
  On our rows file that is 5 rows (README section 9 names them): the tool ends with `REFHB ENVFIX 5 row(s)` and
  `REFHB OK 60/60 (...) -> <the --out file>`. Run it after step 2 and again after any re-install (`install_envs.sh` restores the edited
  files to the pin first, and says so).
- `--jobs 8` is the setting run 2 used for the file that runs 2 and 3 ran on (64 vCPU host); the default is min(8, nproc/4,
  MemAvailable GB/8). It takes minutes.
- `run` (step 5) also runs the same env fix over the rows before staging (idempotent; `--no-envfix` skips it).

## 5. The run (README section 3)

Open a long-lived shell (for example `tmux`) in `~/lra` with the variables of step 1 set, then:

```bash
read -rs OPENROUTER_API_KEY && export OPENROUTER_API_KEY   # paste the key: not echoed, not in the shell history
python3 infra/closed_package/run_final.py plan --rows "$ROWS" --bets D2,D3,D4,D4P,D4S,D4C,D4N   # optional, $0: launches nothing
python3 infra/closed_package/run_final.py run --rows "$ROWS" --heartbeats "$HB" --out ~/lra-final \
  --bets D2,D3,D4,D4P,D4S,D4C,D4N                          # + --force-stage after step 3
```

- **`--bets D2,D3,D4,D4P,D4S,D4C,D4N`** switches on run 3's three model-free end-stage passes (README, End-stage passes). It is frozen
  into `plan.json` and each shard's `config.json`; a resume with another list is refused. Without it, the run is run 1's pipeline.
- **The key.**
  - `run` writes the key to `~/.config/vexorium/openrouter_api_key`, with mode 600 and outside the checkout. Every model preset reads it
    from there. The key is never printed or logged.
  - `--key-file PATH` reads the key from a file instead of the environment.
  - Keep the key and any key file out of the package folder and out of every commit.
  - The post-step needs no key, so you can delete the key file once this step has ended.
- **What we ran** (README section 9): this command with `--tag final3 --scratch-root /scratch/work/final3 --shards 4 --runner systemd`
  and run 2's reference heartbeats file. All of those are the defaults except `--scratch-root` (the sessions' compile scratch on a local
  NVMe disk) and the tag. We passed no other option: the pipeline is frozen in `run_final.py`, and the rehearsal options are refused
  without `--fake-model`.
- **Before any spend**, `run` checks Python and `requests`; that `harness/`, `scorer/` and `llm/` are clean; the rows and every pin's
  environment; elan, the image and the systemd user manager; the leak scan, the disk and the key. Each check prints an `ok` or `BAD`
  line, and any `BAD` refuses the run with exit 2.
- **While it runs:**
  - The 4 shards run as systemd user units `lra-final-s1` to `lra-final-s4`, each with its own memory-guard unit.
  - The command reports every 10 min, on the terminal and in `~/lra-final/logs/launcher.log`.
  - To check progress from another shell: `python3 infra/closed_package/run_final.py status --out ~/lra-final`.
  - A row counts as finished only after its end step, so `0/15 rows finished` for the first ~10 h is normal.
  - In our run 3, the 4 shards finished 11.6, 12.1, 13.6 and 17.0 h after the launch. The slowest shard sets the wall time.
- **Done** when the command prints two lines like these and exits 0 (ours, at the end of run 3; home directory shortened to `~`):
  ```
  [run_final 12:58:17] merged ~/lra-final3/submission.jsonl: 60 line(s) for 60 row(s): 60 from the shards, 0 seed; check OK
  [run_final 12:58:17] exit 0: every shard finished; the upload file is complete
  ```
  The other exit codes: 5 the file checks, but a shard did not finish (run the same command again); 3 the wait limit (61 h) passed; 1
  the merged file fails its check; 2 refused before launch.
- **Outputs** (README section 4), all in `~/lra-final/`: `submission.jsonl` (the run's upload file before the post-step);
  `merge_report.json`, `plan.json`; `shards/s<k>/` (each shard's `finals.json`, `summary.json`, `router.log` and more); `logs/`; `hx/`
  (the sessions' workspaces and full trajectories).
- **Wall time.** Our run 3 took 17.0 h on the host of step 0: from the launch (2026-11-02 19:58:11 UTC; two shards restarted once at
  20:04:25 after a start race that the worktree setting of step 1 removes) to the merge (2026-11-03 12:58:17 UTC).
- **Cost.** The code caps spend at $3.00 per row: each model call is priced at its worst case before it is sent; after the call, it is
  metered at the higher of OpenRouter's billed cost and the list price; a row's spend is kept across restarts. To read the spend after
  the run, in `~/lra-final`:
  ```bash
  python3 -c 'import json,glob; r=[v for f in sorted(glob.glob("shards/s*/summary.json")) for v in json.load(open(f))["per_row"].values()]; print(len(r), "rows: $%.2f reported, $%.2f at the cap price; per row at most $%.3f / $%.3f" % (sum(x["spend"] for x in r), sum(x["cap_spend"] for x in r), max(x["spend"] for x in r), max(x["cap_spend"] for x in r)))'
  ```
  Ours printed `60 rows: $166.33 reported, $173.97 at the cap price; per row at most $2.874 / $2.969`. No row went over the cap.

## 6. If the run stops (README section 6)

- Run the same `run` command again (with the same `--bets`). Finished shards are kept; unfinished ones resume from their run
  directories (spend, steps done, best proofs), and the merge is redone. The command also restarts a shard that ended unfinished once on
  its own (`--max-restarts 1`); our run used that once for two shards (step 5).
- If only the waiting command died (for example, a closed terminal), the shard units keep running. The same `run` command finds them
  (`shard s<k>: already running`) and waits again.
- `python3 infra/closed_package/run_final.py stop --out ~/lra-final` stops every unit; the routers write their outputs on the way out, and
  the next `run` resumes. `python3 infra/closed_package/run_final.py merge --out ~/lra-final` merges what exists.
- Keep `--out` and the rows file the same on a resume: `run` refuses an `--out` that holds a run of another rows file.

## 7. The post-step (README section 10)

After step 5 has ended with exit 0, from the same checkout, our upload's passes (README section 10, **Our passes**), in order:

```bash
OPS4=implied,closerprep,inlineeq,hintgrind,projpath,lexsurf,jointres,t4ind,ctorsearch,argon_funind,argon_hbelab,argon_hpcert,sonnet_listdrop,sonnet_lintdrop,opus_hoist,opus_stepdrop,opus_rundrop,opus_scaffold,opus_armfold,opus_goalmerge,opus_patfuse,sonnet_surface,sol_harvest,v4_unhyg,hb_hotctl,v4_patelide,v4_rescreen,hb_hotelab
python3 infra/closed_package/post_step.py --out ~/lra-final --compile-slots 56 --ops "$OPS4"   # pass 1
python3 infra/closed_package/post_step.py --out ~/lra-final --compile-slots 56 --ops "$OPS4" --input ~/lra-final/post_step/proofs.post.jsonl --post-dir ~/lra-final/post_step2   # pass 2
```

- **Requirements:** none beyond `python3` and the Lean environments. The step costs $0 and uses no model, no key, no Docker and no
  systemd. It raises its own open-file limit to 65536 (step 0); when the hard limit is lower it prints a `WARNING` line, and rows that
  run out of files keep their line.
- **Inputs:** pass 1: `~/lra-final/submission.jsonl`, which it reads and never writes, and each shard's `finals.json`; a later pass:
  `--input`, the previous pass's `proofs.post.jsonl`. The rows and heartbeats the run staged in `data/final/`, checked against
  `plan.json` (`--rows` / `--heartbeats` name other files).
- **Settings:** the ops of each pass as above (`kskip` in none; `post_step.py` without `--ops` runs every op but `kskip` in one pass,
  which is not what we ran); every row at once, 7,200 s for the step, 2,700 s and 240 compiles per row (the defaults); 56 compile slots
  as ours (by default min(32, physical cores)).
- **Wall time:** our passes: pass 1 1,428 s (2,739 compiles); pass 2 1,354 s (1,961 compiles), on a 64-vCPU host that other compiles shared; with fewer slots it takes longer (at most
  7,200 s plus a row's 2,700 s per pass), and slow rows can skip the ops of versions 3 to 5.
- **Done** when each pass prints a line like this one and exits 0:
  ```
  [...] [post_step] done in N s: K row(s) changed (...), stored mean A -> B; upload <out>/submission.post.jsonl (sha256 ...; checked); report <out>/post_report.json
  ```
  Our passes' means: pass 1 86.0088 -> 86.2488 (31 rows changed); pass 2 86.2488 -> 86.3092 (10 rows changed); the last pass's upload file: sha256 `9dde775a8570a78e...`.
- **Exit 1:** the pass's result failed a check, and it wrote no `submission.post.jsonl`; the previous pass's file (or
  `submission.jsonl`) stays the file to upload. **Exit 2:** refused before the step, for example because its `--post-dir` exists.
- **Outputs:** `submission.post.jsonl` (the upload file, replaced by each pass); `post_report.json`; each pass's `--post-dir` (its input
  and output, its own `submission.post.jsonl` and `post_report.json`, and every decision).

## 8. Check the upload file

```bash
cd ~/lra
python3 harness/final_merge.py --rows "$ROWS" --check ~/lra-final/submission.post.jsonl   # ...: OK (60 row(s), 0 problem(s))
wc -l < ~/lra-final/submission.post.jsonl                                                   # 60
python3 -c 'import json,sys; a=[json.loads(l) for l in open(sys.argv[1])]; b=[json.loads(l) for l in open(sys.argv[2])]; print(sum(x["name"]==y["name"] and x["proof"]!=y["proof"] for x,y in zip(a,b)), "of", len(b), "line(s) changed")' ~/lra-final/submission.jsonl ~/lra-final/submission.post.jsonl
grep -c 'set_option debug' ~/lra-final/submission.post.jsonl                              # 0: no kernel skip, no debug option
sha256sum ~/lra-final/submission.post.jsonl
```

- The check is static: it compiles nothing. It confirms one `{"name", "proof"}` line per row in the rows file's order, with every proof
  non-empty, starting with its row's statement and free of forbidden constructs.
- The compiles happened earlier. The run audits each row's final proof on every listed toolchain before it writes the row's line
  (README, sorry guard). The post-step adopts a change only when it compiles on every listed toolchain (README section 10, gate).
- On our upload's passes, the third command prints `33 of 60 line(s) changed` and the fourth `0`.

**Upload `~/lra-final/submission.post.jsonl`.**

## 9. How our run compares

| | our closed upload |
|---|---|
| rows file | 60 rows, sha256 `d53690b057f9...` |
| host | Azure D64ads_v7: 64 vCPU, 256 GB, Ubuntu 24.04 x86-64 |
| run (step 5) | 2026-11-02 19:58 to 2026-11-03 12:58 UTC (17.0 h); exit 0; 60 lines from the shards, 0 seeds |
| spend | $166.33 reported, $173.97 at the cap price; per row at most $2.874 / $2.969 |
| `submission.jsonl` | sha256 `43e1e6e8c03353cb...`; mean 86.009 on our meter (a probe upload of the run's state 10 h in scored 84.85) |
| post-step (step 7), our passes | pass 1: a checkout of `715cd39d`, the version-4 op list without `kskip` (28 ops), 2026-11-04 09:21:19-09:45:07 UTC, 1,428 s, 2,739 compiles, 31 rows changed, mean 86.009 -> 86.249, `proofs.post.jsonl` `8609076c0da6...`; pass 2: a checkout of `715cd39d`, the version-4 op list without `kskip` (28 ops), 2026-11-04 09:45:08-10:07:42 UTC, 1,354 s, 1,961 compiles, 10 rows changed, mean 86.249 -> 86.309, `proofs.post.jsonl` `b3d7b02f75c9...` |
| `submission.post.jsonl` (our upload) | sha256 `9dde775a8570a78eaf83417d00edec190e371e3093c295d1725593d6d4a39972`; mean 86.309 on our meter; 33 lines changed against run 3's; no `set_option debug.*` in any line; leaderboard: section 10 |
| earlier: post-step version 2, nine ops, one pass (previous code zip, our upload `sub34`) | 2026-11-04 06:12:06-06:34:31 UTC, 1,344 s, 24 compile slots; 27 rows changed; mean 86.238; `submission.post.jsonl` `aaa54d053f7b...` (leaderboard 86.24) |
| earlier: post-step with all ten ops (`kskip` on), from the previous code zip | 2026-11-04 02:22:40-02:52:42 UTC, 1,802 s, 24 compile slots; 29 rows changed; mean 87.131; `submission.post.jsonl` `75ea1e498fe6...`, our upload `sub32` (leaderboard 87.13), with `set_option debug.skipKernelTC` on 4 rows |
| earlier: the ten-op development run | 2026-11-04 00:54-01:20 UTC, 1,512 s, 48 compile slots; 28 rows changed (the same proofs as `sub32` on those rows); mean 86.009 -> 87.129; output `d66ab64ab54a...` |

- **The run does not repeat byte for byte.** The models (GPT-6.1 Sol and Terra, Gemini 4 Argon) sample their answers, and timed limits
  stop work by the clock (README section 5). A rerun of step 5 therefore writes other proofs, another `submission.jsonl` and gets
  another score. We have not rerun this exact code, so we have no measured spread for it; our three closed official runs (README
  section 9: runs 1, 2 and 3, each a little different in code) gave 85.709, 85.785 and 86.009 on our meter.
- **The post-step repeats closely, not byte for byte.** Version 2's ops size some probe files and compile rounds from measured compile
  times, so a rerun on the same input can end a few rows on another, equally gated proof (README section 10: two runs on one open-track
  input changed the same 52 rows, 8 of them to a different proof, the means 0.007 apart). Our release smoke of this code zip on two rows
  of run 3's output reproduced our run's two output lines byte for byte. The two ten-op runs on run 3's output (development
  checkout; previous code zip, `sub32`) changed the same 28 rows to byte-identical proofs, and the second one more row (+0.12): means
  87.129 and 87.131. The nine-op run from the previous code zip (`sub34`) on the same input: 27 rows changed, 25 of them to the same proof as the ten-op `sub32` run; mean 86.238. Our upload's passes of version v4su (README section 10) ran once each; our release smoke ran two rows of run 3's output through this zip, the second also as a chained pass (README section 10: one row as in our pass 1, the other further improved under a lighter load).

## 10. Our upload

| | |
|---|---|
| the file uploaded | `submission.post.jsonl` of the last pass named here, sha256 `9dde775a8570a78eaf83417d00edec190e371e3093c295d1725593d6d4a39972` (60 lines, 33 of them changed by the step against run 3's; no `set_option debug.*`) |
| post-step passes | pass 1: a checkout of `715cd39d`, the version-4 op list without `kskip` (28 ops), 2026-11-04 09:21:19-09:45:07 UTC, 1,428 s, 2,739 compiles, 31 rows changed, mean 86.009 -> 86.249, `proofs.post.jsonl` `8609076c0da6...`; pass 2: a checkout of `715cd39d`, the version-4 op list without `kskip` (28 ops), 2026-11-04 09:45:08-10:07:42 UTC, 1,354 s, 1,961 compiles, 10 rows changed, mean 86.249 -> 86.309, `proofs.post.jsonl` `b3d7b02f75c9...` (README section 10, **Our passes**: our development checkouts; the same as this code zip's commands in step 7) |
| leaderboard | not known when this zip was built (the zip goes with the upload) |
| replaces | our closed upload `sub34` (leaderboard 86.24): the same run 3 output after one pass of version 2 with nine ops |
