# Replicating our closed-track upload, step by step

This file takes you from the final benchmark's rows file to the file we uploaded on 2026-11-03 (closed track, `Vexorium-Agent`):
closed official run 1's merged `submission.jsonl` after the post-step, `submission.post.jsonl`. Each step names its section of
[README.md](README.md), which has the details and the reasons. The package commands are README.md's. Two other kinds of command
appear here:
- the command line of `env_fixes/envfix.py`, the env-side fix that README section 9 describes;
- read-only checks: `sha256sum`, `wc` and two `python3 -c` one-liners.

This file puts the commands in order and adds, for each step, what it prints when it works, how long it takes and what it costs.

| | |
|---|---|
| the file to upload | `~/lra-final/submission.post.jsonl` (step 8): one `{"name", "proof"}` line per row, in the rows file's order |
| wall time | ~17 h for 60 rows on 64 vCPU / 256 GB (our run 1: 17.06 h, step 6), plus the install (step 2), the reference heartbeats (minutes) and the post-step (15-21 min) |
| cost | at most $3.00 per row, enforced by the code (60 rows: at most $180 of OpenRouter credit). Our run 1: $167.95 reported, $175.14 at the cap price. The dry run and the post-step cost $0 |
| what repeats exactly | the post-step: on our run 1's output it rebuilt our upload file byte for byte (3 runs). The run itself does not: the models sample, so a rerun gives other proofs and another score (step 10) |

## 0. Prerequisites (README section 1)

| item | what the package needs | what we ran |
|---|---|---|
| OS | Linux x86-64 or aarch64 with systemd | Ubuntu 24.04 x86-64 (Azure D64ads_v7) |
| CPU, RAM | at least 16 vCPU and 64 GB. The knobs are derived from the host; `python3 harness/host_knobs.py --shards 4 --rows 15` prints them | 64 vCPU (32 cores x SMT 2), 256 GB |
| GPU | none: the models are called through OpenRouter | none |
| disk | ~250 GB free for the Lean environments of 60 rows, plus ~20 GB for the run (`run` refuses with less than 20 GB free) | 495 GB OS disk + local NVMe scratch |
| containers | Docker, with your user in the `docker` group (see below) | Docker 29 |
| systemd | user units: `loginctl enable-linger $USER`; cgroup v2 with the memory controller delegated; `systemctl --user show-environment` must work in the shell of step 6 | |
| software | git, curl, Python >= 3.11 with `requests`, ripgrep, zstd, jq. `install_envs.sh` installs the missing ones with apt when it can | Python 3.13 |
| Lean | elan. `install_envs.sh` installs it into `~/.elan` with no default toolchain; each environment's `lean-toolchain` file installs its own toolchain | |
| network | GitHub (project repositories, Mathlib cache), Docker Hub (`python:3.13-slim`), openrouter.ai | |
| key | one OpenRouter API key with at least $3.00 x rows of credit (60 rows: $180), able to call `openai/gpt-6.1-sol`, `openai/gpt-6.1-terra` and `google/gemini-4-argon` (step 6) | |

**Docker and podman.** The model sessions and the auto-brief run in containers started with the `docker` command (image `lra-agent:1`,
built in step 2). The dry run's local fake model listens on the Docker bridge. We have run this package only with Docker; it has not
been tested with podman or podman-hpc. The post-step and the check (steps 8 and 9) need neither Docker nor systemd: `python3` and the
Lean environments are enough.

**systemd.** `run` starts each shard as a systemd user unit with a memory cap (`--runner systemd`, the default, as in our run).
`--runner local` runs the shards as child processes instead, with no memory caps; the dry run uses it. In a non-login shell,
`systemctl --user` needs `XDG_RUNTIME_DIR=/run/user/$(id -u)` and `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus`; our
launch script set both.

## 1. Get the code as its own git checkout (README section 2)

Use the code zip. It holds every file the run needs, including `harness/style_rw_exemplars.json`: the style rewrite's example pairs,
which `run_final.py` pins by hash.

```bash
unzip -q vexorium-closed-final-run1-post.zip            # one top folder: vexorium-closed-final-run1-post/
mkdir ~/lra && cp -a vexorium-closed-final-run1-post/. ~/lra/ && cd ~/lra
git init -q && git add -A && git -c user.name=lra -c user.email=lra commit -qm "closed final package"
git config extensions.worktreeConfig true               # once: the shards' parallel worktree setups (README section 2)
sha256sum harness/style_rw_exemplars.json               # starts c03ffd730e950d93 (the run refuses any other file)
```

The same code is in our repository at tag `closed-final-run1-post-20261103b` (folder `final/`, branch `release/closed-run1-post`).
The repository is private, and it does not have `harness/style_rw_exemplars.json`, so a checkout made from it stops at router start in
steps 3 and 6 (README section 7).

Run every later command in `~/lra`, in a shell where these are set:

```bash
cd ~/lra
export PATH="$HOME/.elan/bin:$PATH"                     # elan (installed in step 2)
ROWS=/path/to/final_rows.jsonl                          # the final benchmark's rows file, as an absolute path
HB=~/lra-in/heartbeats.jsonl                            # the reference heartbeats, written in step 5
```

## 2. Install (README section 2)

```bash
sha256sum "$ROWS"                                       # ours: d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682 (60 rows)
python3 -c "import requests" || sudo apt-get install -y python3-requests
infra/closed_package/install_envs.sh "$ROWS"
infra/closed_package/build_image.sh
```

- `install_envs.sh` derives one environment per (project, pinned toolchain) from the rows. For each, it clones the project, checks out
  the pinned commit, fetches Mathlib's prebuilt cache and builds the rows' modules.
  - On our rows file it ended `INSTALL DONE ok=17 failed=0` (17 environments of 6 projects), then
    `60 row(s): 0 error(s), 0 warning(s), 0 environment(s) missing or off-pin`.
  - It took 12 min on our host, where 6 of the 17 environments were already present. We did not time an install on an empty host.
    `RESTORE=1` first restores our public archives of the warm-up pins.
  - It is re-runnable; its logs are in `envs/logs/`.
- `build_image.sh` builds the session image and ends `IMAGE OK lra-agent:1`.

## 3. First test: the $0 dry run (README section 7)

The dry run needs no key and makes no model call: a scripted local server answers instead of OpenRouter. It runs the whole pipeline on
two warm-up rows in about an hour, and so checks Docker, Lean, every stage, the writers and the merge before any money is spent. Its
proofs improve only through the model-free stages.

```bash
sed -n '1p;4p' data/benchmark_warmup.jsonl > /tmp/dry_rows.jsonl     # 2 warm-up rows: a Strata row, a PhysLib row
infra/closed_package/install_envs.sh /tmp/dry_rows.jsonl               # their 2 environments
python3 infra/closed_package/run_final.py run --rows /tmp/dry_rows.jsonl --heartbeats data/benchmark_heartbeats.jsonl \
  --out /tmp/lra-dry --tag dry --shards 2 --runner local --fake-model --shared-slots 1 --workers 1 --jobs 1 --router-mem-gb 16 \
  --brief-row-workers 1 --brief-compile-workers 1 --brief-docker-memory-gb 12 --agent-docker-memory-gb 12 \
  --runtime-hours 5 --wait-hours 4.5 --restart-delay 60 --report-every 300 --ladder-extra "--auto-brief-budget 4" \
  --router-extra "--clean-stages free --clean2-stages free --clean-deadline-s 300 --end-config probe/b66/smoke_end.json"
python3 harness/final_merge.py --rows /tmp/dry_rows.jsonl --check /tmp/lra-dry/submission.jsonl
```

- Expected: the run's last line is `exit 0: every shard finished; the upload file is complete`, and the check prints
  `/tmp/lra-dry/submission.jsonl: OK (2 row(s), 0 problem(s))`.
- On a shared host, run the dry run inside a memory-capped unit (README section 7).
- The dry run stages its two rows into `data/final/` of the checkout. So add `--force-stage` to the first real `run` (step 6).

## 4. The env-side fix for 5 rows (README section 9)

5 rows have declarations that sit directly under a chain of `... in` modifiers (README section 9 names them). In our run, every candidate
on those rows failed until `env_fixes/envfix.py` edited the environments' copies of their files, 16 min into the run. To start in the
state our run was in from then on, apply the fix now: after step 2 and before step 5.

The script changes no package file and acts only on those 5 row names. In each of their files, on every pin, it strips the trailing
` in` from that chain; the line count stays the same.

```bash
python3 env_fixes/envfix.py "$(pwd -P)" "$ROWS"                                    # dry: one EDIT line per line it would change
python3 env_fixes/envfix.py "$(pwd -P)" "$ROWS" --apply --backup ~/lra-envfix-backup
```

- The first argument is the checkout's absolute path.
- Always pass `--backup`: without it, the originals go to `/workspace/final-in/envfix_backup`, a path on our host. The backup keeps each
  original under its path, with `/` replaced by `__`.
- On our rows file, the fix edited 10 files in 8 environments: each of the 5 rows on its 2 pins.
- Do not run `install_envs.sh` again afterwards. README section 9 says to apply the fix only to environments whose modules are already
  built, because `lake build` compiles whole files.
- `CHECK_ONLY=1 infra/closed_package/install_envs.sh "$ROWS"` is safe to run. It reports these 8 environments as `ENV MISSING`, because
  `lake build --no-build` sees the edited module as out of date. Its closing check and the run's preflight still report 0 missing. This
  is expected.

## 5. Reference heartbeats (README sections 3 and 9)

The final benchmark's reference heartbeats are not published. This tool measures each row's reference proof on its newest pin and writes
a file in the warm-up release's format:

```bash
python3 infra/refhb/make_ref_heartbeats.py --rows "$ROWS" --out "$HB" --jobs 16 --allow-missing
```

- `--jobs 16` is the setting of our 64 vCPU host. The default is min(8, nproc/4, MemAvailable GB/8).
- Our run ran the tool in a memory-capped user unit; README section 9 has that form. It took 227 s on our host.
- Expected last line: `REFHB OK 60/60 (...) -> <the --out file>`. A `REFHB PLACEHOLDERS ...` line names rows that could not be measured
  and got a flagged stand-in (`--allow-missing`). In our run, those were the 5 rows of step 4; they were measured again after the fix
  (README section 9 lists the values).

## 6. The run (README section 3)

Open a long-lived shell (for example `tmux`) in `~/lra` with the variables of step 1 set, then:

```bash
read -rs OPENROUTER_API_KEY && export OPENROUTER_API_KEY   # paste the key: not echoed, not in the shell history
python3 infra/closed_package/run_final.py plan --rows "$ROWS"   # optional, $0: shard split, knobs, preflight; launches nothing
python3 infra/closed_package/run_final.py run --rows "$ROWS" --heartbeats "$HB" --out ~/lra-final   # + --force-stage after step 3
```

- **The key.**
  - `run` writes the key to `~/.config/vexorium/openrouter_api_key`, with mode 600 and outside the checkout. Every model preset reads it
    from there. The key is never printed or logged.
  - `--key-file PATH` reads the key from a file instead of the environment.
  - Keep the key and any key file out of the package folder and out of every commit.
  - The post-step needs no key, so you can delete the key file once this step has ended.
- **What we ran** (README section 9): this command with `--tag final --scratch-root /scratch/work/final --shards 4 --runner systemd`.
  - All of those are the defaults except `--scratch-root`, which puts the sessions' compile scratch on a local NVMe disk.
  - We passed no other option. The pipeline is frozen in `run_final.py`, and the rehearsal options are refused without `--fake-model`.
- **Before any spend**, `run` checks:
  - Python and `requests`;
  - that `harness/`, `scorer/` and `llm/` are clean;
  - the rows and every pin's environment;
  - elan, the image and the systemd user manager;
  - the leak scan, the disk and the key.

  Each check prints an `ok` or `BAD` line, and any `BAD` refuses the run with exit 2.
- **While it runs:**
  - The 4 shards run as systemd user units `lra-final-s1` to `lra-final-s4`, each with its own memory-guard unit.
  - The command reports every 10 min, on the terminal and in `~/lra-final/logs/launcher.log`.
  - To check progress from another shell: `python3 infra/closed_package/run_final.py status --out ~/lra-final`.
  - A row counts as finished only after its end step, so `0/15 rows finished` for the first ~10 h is normal.
  - In our run 1, the 4 shards finished 11.7, 12.1, 14.5 and 17.1 h after the launch. The slowest shard sets the wall time.
- **Done** when the command prints two lines like these and exits 0 (ours, at the end of run 1; home directory shortened to `~`):
  ```
  [run_final 00:30:37] merged ~/lra-final/submission.jsonl: 60 line(s) for 60 row(s): 60 from the shards, 0 seed; check OK
  [run_final 00:30:37] exit 0: every shard finished; the upload file is complete
  ```
  The other exit codes:
  - 5: the file checks, but a shard did not finish (run the same command again);
  - 3: the wait limit (61 h) passed;
  - 1: the merged file fails its check;
  - 2: refused before launch.
- **Outputs** (README section 4), all in `~/lra-final/`:
  - `submission.jsonl`: the run's upload file before the post-step;
  - `merge_report.json`, `plan.json`;
  - `shards/s<k>/`: each shard's `finals.json`, `summary.json`, `router.log` and more;
  - `logs/`;
  - `hx/`: the sessions' workspaces and full trajectories.
- **Wall time.** Our run 1 took 17.06 h on the host of step 0: from the shards' start (2026-11-01 07:27 UTC) to the merge (2026-11-02
  00:30 UTC).
- **Cost.** The code caps spend at $3.00 per row:
  - each model call is priced at its worst case before it is sent;
  - after the call, it is metered at the higher of OpenRouter's billed cost and the list price;
  - a row's spend is kept across restarts.

  To read the spend after the run, in `~/lra-final`:
  ```bash
  python3 -c 'import json,glob; r=[v for f in sorted(glob.glob("shards/s*/summary.json")) for v in json.load(open(f))["per_row"].values()]; print(len(r), "rows: $%.2f reported, $%.2f at the cap price; per row at most $%.3f / $%.3f" % (sum(x["spend"] for x in r), sum(x["cap_spend"] for x in r), max(x["spend"] for x in r), max(x["cap_spend"] for x in r)))'
  ```
  Ours printed `60 rows: $167.95 reported, $175.14 at the cap price; per row at most $2.898 / $2.985`. No row went over the cap.

## 7. If the run stops (README section 6)

- Run the same `run` command again. Finished shards are kept; unfinished ones resume from their run directories (spend, steps done, best
  proofs), and the merge is redone. The command also restarts a shard that ended unfinished once on its own (`--max-restarts 1`).
- If only the waiting command died (for example, a closed terminal), the shard units keep running. The same `run` command finds them
  (`shard s<k>: already running`) and waits again.
- `python3 infra/closed_package/run_final.py stop --out ~/lra-final` stops every unit; the routers write their outputs on the way out, and
  the next `run` resumes. `python3 infra/closed_package/run_final.py merge --out ~/lra-final` merges what exists.
- Keep `--out` and the rows file the same on a resume: `run` refuses an `--out` that holds a run of another rows file.

## 8. The post-step (README section 10)

After step 6 has ended with exit 0, from the same checkout:

```bash
python3 infra/closed_package/post_step.py --out ~/lra-final
```

- **Requirements:** none beyond `python3` and the Lean environments. The step costs $0 and uses no model, no key, no Docker and no
  systemd.
- **Inputs:**
  - `~/lra-final/submission.jsonl`, which it reads and never writes;
  - each shard's `finals.json`;
  - the rows and heartbeats the run staged in `data/final/`, checked against `plan.json` (`--rows` / `--heartbeats` name other files).
- **Settings:** the defaults are our run's: every row at once, min(32, physical cores) compile slots, 7200 s for the step, and 2400 s and
  120 compiles per row.
- **Wall time:** 15-21 min on our host with 32 compile slots. Our own run of the step took 1,271 s; three runs from the code zip took
  914-1,009 s.
- **Done** when it prints a line like the one below and exits 0:
  ```
  [...] [post_step] done in N s: K row(s) changed (...), stored mean A -> B; upload <out>/submission.post.jsonl (sha256 ...; checked); report <out>/post_report.json
  ```
  On a copy of our run 1's `--out`, it printed `done in 914 s: 4 row(s) changed (row#11, row#12, row#13, row#14), stored mean 85.709 -> 86.8983;
  upload .../submission.post.jsonl (sha256 1a39b98f30a3f4b4; checked)`.
- **Exit 1:** the step's result failed a check, and no `submission.post.jsonl` was written. Then `submission.jsonl` is the file to
  upload.
- **Exit 2:** refused before the step, for example because `~/lra-final/post_step/` exists. Move it aside to run the step again.
- **Outputs:**
  - `submission.post.jsonl`: the upload file;
  - `post_report.json`: per row, the status, the ops adopted and the readings before and after;
  - `post_step/`: the step's input and output, and every decision.

## 9. Check the upload file

```bash
cd ~/lra
python3 harness/final_merge.py --rows "$ROWS" --check ~/lra-final/submission.post.jsonl   # ...: OK (60 row(s), 0 problem(s))
wc -l < ~/lra-final/submission.post.jsonl                                                   # 60
python3 -c 'import json,sys; a=[json.loads(l) for l in open(sys.argv[1])]; b=[json.loads(l) for l in open(sys.argv[2])]; print(sum(x["name"]==y["name"] and x["proof"]!=y["proof"] for x,y in zip(a,b)), "of", len(b), "line(s) changed")' ~/lra-final/submission.jsonl ~/lra-final/submission.post.jsonl
sha256sum ~/lra-final/submission.post.jsonl
```

- The check is static: it compiles nothing. It confirms one `{"name", "proof"}` line per row in the rows file's order, with every proof
  non-empty, starting with its row's statement and free of forbidden constructs.
- The compiles happened earlier. The run audits each row's final proof on every listed toolchain before it writes the row's line
  (README, sorry guard). The post-step adopts a change only when it compiles on every listed toolchain (README section 10, gate).
- On our files, the third command prints `4 of 60 line(s) changed`.

**Upload `~/lra-final/submission.post.jsonl`.**

## 10. How our run compares

| | our closed upload |
|---|---|
| rows file | 60 rows, sha256 `d53690b057f9...` |
| host | Azure D64ads_v7: 64 vCPU, 256 GB, Ubuntu 24.04 x86-64 |
| run (step 6) | 2026-11-01 07:27 to 2026-11-02 00:30 UTC (17.06 h); exit 0; 60 lines from the shards, 0 seeds |
| spend | $167.95 reported, $175.14 at the cap price; per row at most $2.898 / $2.985 |
| `submission.jsonl` | sha256 `8f0ac8590a48...`; mean 85.709 on our meter; Arena 85.66 (uploaded alone on 2026-11-02) |
| post-step (step 8) | 4 rows changed (README section 10 lists them and their ops); mean 85.709 -> 86.898 on our meter |
| `submission.post.jsonl` | sha256 `1a39b98f30a3...`; **Arena 86.85** (60/60 compiled); uploaded 2026-11-03 17:23 UTC |

- **The run does not repeat byte for byte.** The models (GPT-6.1 Sol and Terra, Gemini 4 Argon) sample their answers, and timed limits
  stop work by the clock (README section 5). A rerun of step 6 therefore writes other proofs, another `submission.jsonl` and gets
  another score. We have not rerun this exact code, so we have no measured spread for it.
- **The post-step does repeat.** We ran it three times from the code zip on a copy of our run 1's `--out`:
  - twice with the rows and heartbeats staged in `data/final/` (once with run 1's own heartbeats, once with those of our run of the
    step);
  - once with the rows and our run of the step's heartbeats passed by `--rows` / `--heartbeats`.

  Each time it wrote `submission.post.jsonl` with sha256 `1a39b98f30a3...`, byte-identical to our upload. Each of the three made 107
  compiles; our original run of the step, from the development commit, made 128. The number of `closerprep` variants measured per file
  depends on the measured compile seconds, so the compile count varies, but the output did not change. Our run's `--out` is not part of
  this package.
