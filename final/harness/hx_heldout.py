#!/usr/bin/env python3
"""Closed-track pipeline check on a SEALED held-out set (2026-10-11: a $3-compliant held-out check, first at a $2 cap,
then decide whether to go up; a $2 warning milestone per problem). One hosted model, the current harness, every
problem in its own work root (so state.json api_spend is that problem's whole spend).

BUDGET LADDER (default rungs $2.00, $2.85): rounds of 40-turn sessions fill EVERY problem up to a rung before any problem may pass it
(breadth-first). Each finished rung writes a MILESTONE report (mean score, spend, per-repo means, score at budget) over all problems,
so the $2 snapshot is complete and uncensored before any money goes past $2. The agent's gate is a hard bound (it reserves each
turn's worst case), so no problem's spend ever crosses the current rung; agent.py also records the moment a problem's spend crosses
$2 (state.json budget_milestones). Resumable: rerunning continues at the next round and rung.

Sets: see SETS below (held-out sets, the warm-up rows, final-clean = the package's staged rows), abpool (the
frame A/B pool). Run ids start with sealed2- / sealed3- / abpool-, which every mining tool skips. Only scores, spend and the per-turn
cost/best numbers are read, never proof, trajectory text or errors.
    python3 harness/hx_heldout.py --set heldout2 --arm sol [--rungs 2.0,2.85] [--report]
Claude Code (2026-10-12, docs/cc_driver_v2.md §5): --driver claude --claude-prompt v1|v2 --claude-effort E --claude-cache 1h|5m; Phase A runs
one gated session per row: --rungs 2.85 --max-rounds 1 --no-lineage-rule (probe/abpool/run_phase_a.sh). Sealed sets need --claude-sealed and
an own-worktree set (heldout3-cc); Claude batches run one at a time (<= --workers sessions) and spill folders are moved after each batch.
Round 2 (2026-10-12, docs/cc_driver_v2.md §9): after every Claude batch, in-run learning (2026-10-12:
nothing leaves the run; default on with --claude-prompt v2, --claude-inrun / --no-claude-inrun): harness/discover.py --ledger-only over this
line's runs so far, then harness/inrun.py builds <work root>/_run_techniques.json; with --claude-polish first harness/hb_polish.py over the
batch's stored bests ($0 CPU, banked as run <prefix>-hx-<arm>-p<round>). Counts only reach the logs; every step is bounded.
Round-2 review (2026-10-12): a line's runs are selected by exact name (another arm whose name extends this one is never mined into it); a
fresh lineage left unmerged by a ladder that died is merged at start-up (its spend); a signal to the ladder during a post-batch step kills
the step, and a restarted ladder stops a dead one's leftover step (LRA_POSTPASS_LINE).
Reviewer, A4 and ceiling (2026-10-12, docs/cc_driver_v2.md §11): --claude-review runs
agent_claude_code.py --review after every batch but the last round, for the rows the next round resumes (a fresh lineage never sees
review.md), as one Claude batch whose spend counts toward that round's rung (run <prefix>-hx-<arm>-v<next round>; a row with less than the
review budget + SESSION_FLOOR left is not reviewed); --round-per-rung climbs one rung per round (A4: a $1.50 session, the review, a session
to $2.85, for every row); --claude-ceiling lifts the driver's $2.85 cap to the rung (a ceiling measurement, never a submission);
--claude-fresh-facts gives each fresh lineage the main lineage's facts sheet (lineage_facts.md, no proof text).
Exemplars (2026-10-13; docs/cc_driver_v2.md §13):
--claude-exemplars runs harness/exemplars.py at ladder start and after every batch (this line's run dirs with verified records, plus
--claude-exemplars-extra ROOT RUNSDIR pairs of other lines on the same set, checked at launch; bounded, counts only) and passes --exemplars to
every session, which then shows each row's <work root>/_exemplars/<ws>.md (the rows >= --claude-exemplars-target: their style, retrieved
transformations; never proofs) with this best's hot families.
Auto-brief speed (2026-10-22, docs/speed_review.md items 6-7; docs/auto_brief_plan.md "Pipelined auto-brief"): --auto-brief-row-workers N
(autobrief.py --row-workers, default 2 as before) and --auto-brief-longest-first (autobrief.py --longest-first: the longest seeds start
first). --auto-brief-pipeline (default off): the brief container starts in the BACKGROUND (same command, container, private scratch and
--auto-brief-timeout) and round 1 starts at once; its agent.py batch gets --auto-brief-wait (harness/brief_gate.py), so a row's session
starts when its own brief JSON exists (ready rows first, in row order), or once the brief process has ended (finished / timed out / stopped:
the ladder writes <work root>/_autobrief/.brief_ended), or after the brief's timeout plus a grace. After round 1 (and before a rescue) the
ladder waits for the brief process (bounded by its timeout), so later rounds start as before; on any exit or SIGTERM / SIGHUP the brief
container is stopped as on its timeout. Memory: during round 1 the brief container (48g) and the round's session container (48g) run
together, 96g of caps on the 121 GB host, the same as a later round's resume + fresh containers (a first round with a resume AND a fresh
batch, i.e. a resumed ladder, lets the brief finish first: never 3 containers at once); expected resident use is far lower
(each compile ~0.3-0.4 GB anonymous plus shared .olean cache, memgate admits at most ~5 per 48g container and also checks the host).
Brief container knobs (2026-10-26, b64-brief; the it3vm finding on the 64-vCPU VM: 0 of 15 rows in 896 s, ~3 compiles at once): every
--agent-docker container gets the ladder's own LRA_MEMGATE_* (but LRA_MEMGATE_DIR, a host path) and LRA_HBTOOL_SLOTS variables as -e NAME=value
(DOCKER_PASS_ENV; nothing else of the ladder's environment, never a key), so a router unit's claim / reserve reach the compiles; without such
variables every docker command line is byte-identical to before. --auto-brief-docker-memory (default: --agent-docker-memory) sizes the brief
container only; --auto-brief-compile-workers N (default 3, the old literal) is autobrief.py --workers (the sweep's compiles per row at once).
Async ladder (2026-10-26; probe/b63/fast_iteration.md): --async-ladder (default OFF; --driver agent
only) replaces the synchronized rounds (every row one session, the round ends when the slowest session ends: it1b round 3 took 57.6 min
for a 39 min ideal packing) by a pool of --workers workers: a free worker starts the next session of ANY row that is below the rung, not
in flight and not past --max-rounds, ordered by (the row's session index, its spend; with --low-first its score before the spend; then row
order). One session = one agent.py process with --workers 1 --problems ROW (one container with --agent-docker, named with the row's index
s<NN>, never its name). A row never has two sessions in flight. Run ids are the round ladder's: a row's j-th session on a rung runs as
<prefix>-hx-<arm>-r<k> (f<k> for a lineage-rule restart), k = (the rounds before the rung) + j, where the count starts as the round
ladder's (this line's r / f runs) and grows by the rung's longest row, so with --workers >= rows (and session spends that do not depend on
timing) both modes issue the same sessions (same run ids, budgets and flags but --workers / --problems); rows that finish sooner simply
start their next round sooner. Rungs stay barriers: no row passes a rung before every row is done with it,
then the MILESTONE, stop rule and rescue run exactly as in the round ladder (the rescue is one batch, as there). Per session: the lineage
entry (same rule, sessions under $0.05 left out), a jobs.log line (row#NN, round, spend, score, seconds), the log
<run id>.s<NN>.log, a line in probe/runs/<run id>/async_sessions.jsonl, and the run's summary.json rebuilt from the end events of its
trajectories (concurrent agent.py processes of one round would otherwise overwrite each other's summary). A session without spend: its log
says "budget reached" -> the row is full on this rung (as a round ladder's "rung full"); otherwise it is retried, and after
ASYNC_MAX_DRY such sessions in a row it is parked and the ladder exits 1 at the rung end (the router's short-stop then stops before any
gate); nothing in flight and every row still below the rung last ended without spend -> "no spend recorded (API or key problem?);
stopping" (exit 1, as a round ladder's round in which no session spent anything). Pipelined
auto-brief: a row's first session starts once its brief exists or the brief has ended (rows with a brief first); the ladder waits for the
brief at the end of the first rung. A lineage-rule restart runs in the row's own fresh root (<root>-fresh.s<NN>, archived as
<root>-fresh.done-<run id>.s<NN>); a leftover one is merged at start-up like <root>-fresh. --workers auto = min(rows, $LRA_OR_MAX_CONCURRENCY
or 15). Memory: one container per session, each with its own memory gate (the gate's machine-wide MemAvailable check still applies; the
gate's per-container ramp accounting does not span containers), so compiles are no longer throttled by one 48g container's claims (it1b:
135-169 gate holds per round, 2.3-4.0 k seconds summed); keep the runaway guard in pressure mode on.
"""
from __future__ import annotations

import argparse, gzip, json, math, os, pathlib, re, shutil, signal, statistics, subprocess, sys, threading, time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait as fwait

MAIN = pathlib.Path(__file__).resolve().parents[1]
SETS = {"heldout2": ("data/heldout2/heldout2.jsonl", "data/heldout2/heartbeats.jsonl", "sealed2", "probe/heldout/sealed2-ede9d54/jobs.log"),
        "heldout3": ("data/heldout3/heldout3.jsonl", "data/heldout3/heartbeats.jsonl", "sealed3", "probe/heldout/sealed3-e9af1337/jobs.log"),
        "abpool": ("data/abpool/abpool.jsonl", "data/abpool/heartbeats.jsonl", "abpool", None),
        # the 15 official warm-up rows (2026-10-11: warm-up run, knowledge and tools reused, proofs not; target >= 89.5)
        "warmup": ("data/benchmark_warmup.jsonl", "data/benchmark_heartbeats.jsonl", "wu", None),
        # the same 15 rows for the Codex driver (2026-10-12): own worktree and work roots, so it never
        # touches the agent.py Sol run's (wu-hx, harness/hwork/wu-sol)
        "warmup-cx": ("data/benchmark_warmup.jsonl", "data/benchmark_heartbeats.jsonl", "wucx", None),
        # sealed set #3 for the Codex driver (2026-10-12, Codex + Sol and DeepSeek on set #3): its own worktree, so its container
        # (which mounts the worktree) never sees another line's work root; run ids sealed3-cx-hx-*
        "heldout3-cx": ("data/heldout3/heldout3.jsonl", "data/heldout3/heartbeats.jsonl", "sealed3-cx", "probe/heldout/sealed3-e9af1337/jobs.log"),
        # sealed set #3 for the Claude Code driver (2026-10-12 review): Claude Code runs on the HOST, so its own worktree keeps other lines'
        # work roots (best proofs of the same rows) out of its neighbourhood; run ids sealed3-cc-hx-*; spill folders moved after every batch
        "heldout3-cc": ("data/heldout3/heldout3.jsonl", "data/heldout3/heartbeats.jsonl", "sealed3-cc", "probe/heldout/sealed3-e9af1337/jobs.log"),
        # 2026-10-13 clean recheck (OpenRouter-funded, from the seed proofs, general knowledge only): the warm-up rows in a
        # WHITELIST sparse worktree (CLEAN_PATHS: code and the three data files, no bank records, runs, docs, briefs or work roots, all of
        # which hold earlier proofs of these rows), rescue and lineage choices blind to earlier scores, stray env files masked
        "warmup-clean": ("data/benchmark_warmup.jsonl", "data/benchmark_heartbeats.jsonl", "wuclean", None),
        # 2026-10-18 router v2.2 sealed A/B (docs/router_v2.md): the sealed sets in whitelist worktrees, one PER ARM (a shared worktree's
        # container would see other arms' bests of the same rows); setup_worktree writes the set's rows into the worktree's data files.
        # Prefixes start with "sealed", so every mining tool skips their runs.
        # 2026-10-25 (b63 item 16, G7 adoption probes T3/T7): NON-row sibling theorems built by probe/b63/g7_rows.py, in a WHITELIST worktree
        # per arm like warmup-clean (review 2026-10-25: the full repository tracks earlier best proofs of the warm-up rows, among them the
        # rows these siblings sit next to; a session that read them would adopt their scaffold from there, not from what the probe shows)
        "g7-clean": ("data/g7/g7.jsonl", "data/g7/heartbeats.jsonl", "g7c", None),
        "heldout2-clean": ("data/heldout2/heldout2.jsonl", "data/heldout2/heartbeats.jsonl", "sealed2c", None),
        "heldout3-clean": ("data/heldout3/heldout3.jsonl", "data/heldout3/heartbeats.jsonl", "sealed3c", None),
        # 2026-10-25 (LeanPool, the sixth library; docs/leanpool_env.md §7): the frame-matched LeanPool slices drawn by
        # probe/b63/leanpool_draw.py (one row per project, seed 20261025): a visible dev slice and a sealed slice (counts only)
        "leanpool-dev-clean": ("data/leanpool_dev/rows.jsonl", "data/leanpool_dev/heartbeats.jsonl", "lpdevc", None),
        "heldout4lp-clean": ("data/heldout4lp/heldout4lp.jsonl", "data/heldout4lp/heartbeats.jsonl", "sealed4lpc", None),
        # 2026-10-27 (b66 closed package, retro A1: the organizers' 60-row final, or ANY rows file): harness/final_rows.py stage copies a
        # validated rows file (the warm-up file's schema, LeanPool rows included) and its reference heartbeats to data/final/ (untracked,
        # .gitignore); a whitelist worktree per arm like warmup-clean, one arm per shard (infra/closed_package/run_final.py)
        "final-clean": ("data/final/rows.jsonl", "data/final/heartbeats.jsonl", "finalc", None)}
# "-clean" sets whose rows are NOT benchmark rows (G7 siblings): a facts-only --brief-dir (neighbour proofs of non-row library declarations,
# probe/b63/g7_brief.py) is allowed there; it is copied into the worktree's work root, the only place its container can read it
NONROW_SETS = ("g7-clean",)
# the only paths a "-clean" set's worktree checks out (git sparse-checkout, non-cone patterns)
CLEAN_PATHS = ["/harness/*.py", "/harness/tools/*.py", "/scorer/*.py", "/llm/*.py", "/bank/*.py", "/probe/verify_candidates.py",
               "/data/benchmark_warmup.jsonl", "/data/benchmark_heartbeats.jsonl", "/data/reference_heartbeats_local.json",
               "/envs/manifest.json", "/envs/manifest.py"]
# 2026-10-27 (b66 closed package): the directory that holds the sets' worktrees (<prefix>-hx, <prefix>-<arm>-hx); $LRA_HX_BASE moves them
# (the package puts them under its --out), default ~/source/lra-ab as before
HX_BASE = pathlib.Path(os.environ.get("LRA_HX_BASE") or pathlib.Path.home() / "source/lra-ab")
LIST_PRICES = None     # (input, output, ...) $/1M of a list-price agent.py preset, for curve(); set in main
LINE_PRESET = None     # b64 planner (--first-preset): the line's --preset; curve() prices another preset's session at its cap price; set in main
PIN_GONE: set = set()  # b66 (A3): the presets --preset-fallback moved away from (CONFIRMED pinned); their markers / events are not this run's stop
# b65 pin: agent.py's exit code and run-dir marker of a CONFIRMED max_price pin (b65-final: harness/pinwatch.py, which agent.py uses too;
# test_hx_async_ladder checks they agree). agent.py itself is not imported (~0.5 s; pin_stop runs in the async scheduler's loop)
if str(MAIN) not in sys.path:
    sys.path.insert(0, str(MAIN))
from harness import pinwatch as PW  # noqa: E402
PIN_FATAL_RC, PIN_MARKER = PW.PIN_FATAL_RC, PW.PIN_MARKER
SESSION_FLOOR = 0.30   # no session starts with less left: the first turn's worst case (opening context uncached + 12k output) is ~$0.15-0.27
# 2026-10-22 (lever 5, --agent-budget-reclaim: every session runs agent.py --budget-reclaim): a session's first turn may then be shrunk to
# agent.RECLAIM_FLOOR (2,000) output tokens, so the floor only has to cover THAT turn's worst case: the opening context billed uncached plus
# 2,000 output tokens, at the preset's list prices. The opening context is agent.py's first-turn estimate ((len(SYSTEM) + len(json(msgs)))
# // 2 + 20,000): median 35.2k, p99 42.1k, max 43.3k tokens over 929 Sol sessions of earlier non-sealed dev runs (the provider reported
# at most 20.9k input tokens on those first turns); bounded here by RECLAIM_OPEN_CTX = 60k (1.39x that max). Sol ($2.50 in /
# $10 out per 1M): 60,000 x 2.50 + 2,000 x 10 = $0.150 + $0.020 = $0.170 <= RECLAIM_SESSION_FLOOR $0.20, so the floor drops from $0.30
# to $0.20 (at $0.20 the max-size opening still leaves (0.20 - 43,251 x 2.5e-6) / 1e-5 = 9.2k output tokens for the first turn). A preset
# whose first-turn worst case is above $0.30 keeps $0.30 (Opus: 60,000 x 5.00 + 2,000 x 20 = $0.34): the floor is lowered only when it fits.
RECLAIM_OPEN_CTX = 60000
RECLAIM_SESSION_FLOOR = 0.20
# 2026-10-26 (b64 L1, --agent-skeleton-fix): the agent.py flags of the lean_skeleton junk fix (schema order, salvage, combinator holes,
# billing reconcile)
SKELETON_FIX_FLAGS = ["--skeleton-path-first", "--skeleton-salvage", "--skeleton-combinator-holes", "--junk-billing-reconcile"]


def reclaim_session_floor(prices, floor_tokens: int, base: float = 0.30) -> float:
    """--agent-budget-reclaim: the session floor (see RECLAIM_OPEN_CTX): the first turn's worst case at the reclaim floor, rounded up to the
    cent and never below RECLAIM_SESSION_FLOOR; `base` (the old floor) when that worst case does not fit under it."""
    pi, po, _pr, pw = prices
    worst = (RECLAIM_OPEN_CTX * max(pi, pw) + floor_tokens * po) / 1e6
    if worst > base:
        return base
    return min(base, max(RECLAIM_SESSION_FLOOR, math.ceil(worst * 100 - 1e-9) / 100))


class Set:
    def __init__(self, key: str, arm: str):
        path, hb, self.prefix, self.ref_log = SETS[key]
        self.clean = key.endswith("-clean")
        self.rows_rel = path
        self.rows = [json.loads(l) for l in (MAIN / path).open() if l.strip()]
        self.names = [r["name"] for r in self.rows]
        self.hb_path = MAIN / hb
        # a "-clean" set: one worktree PER ARM (its container mounts the worktree's hwork and probe/runs, so arms on one worktree would
        # read each other's bests and the repeated runs would not be independent draws)
        self.wt = HX_BASE / (f"{self.prefix}-{arm}-hx" if self.clean else f"{self.prefix}-hx")
        self.root = f"harness/hwork/{self.prefix}-{arm}"
        self.run_prefix = f"{self.prefix}-hx-{arm}-r"
        self.out = MAIN / f"probe/heldout/{self.prefix}-hx-{arm}"


def stage_inputs(S: Set, a) -> tuple[int, int]:
    """Per-row inputs copied into the line's work root (the container mounts only the worktree; a "-clean" worktree is sparse): the non-row
    set's --brief-dir briefs (<ws>.md) into <root>/_brief, the --agent-artifact records (<ws>.artifact.json, harness/artifacts.write_record)
    into <root>/_artifacts. Only the set's rows. Returns (briefs, artifacts) staged."""
    def src(p):
        p = pathlib.Path(p); return p if p.is_absolute() else MAIN / p
    counts = []
    for opt, sub, suffix in (("brief_dir", "_brief", ".md"), ("agent_artifact", "_artifacts", ".artifact.json")):
        n = 0
        if getattr(a, opt, None) and (opt != "brief_dir" or S.clean):
            dst = S.wt / S.root / sub; dst.mkdir(parents=True, exist_ok=True)
            for name in S.names:
                f = src(getattr(a, opt)) / (re.sub(r"[^A-Za-z0-9_.-]", "_", name) + suffix)
                if f.is_file():
                    shutil.copy2(f, dst / f.name); n += 1
        counts.append(n)
    return counts[0], counts[1]


def setup_worktree(S: Set, ref: str, log) -> None:
    """Worktree at `ref` whose data files carry the set's rows; envs symlinked from the main checkout (the built environments live only
    there, so the ladder also runs from another worktree of the repository)."""
    if getattr(S, "clean", False):   # whitelist sparse checkout (CLEAN_PATHS); patterns re-applied on every start, then the tree is checked out at ref
        if not (S.wt / ".git").exists():   # (a directory without .git, e.g. left by agent_docker's mkdirs, makes git worktree add refuse)
            subprocess.run(["git", "worktree", "add", "--no-checkout", "--detach", str(S.wt), ref], cwd=MAIN, check=True, capture_output=True)
        subprocess.run(["git", "-C", str(S.wt), "sparse-checkout", "set", "--no-cone", *CLEAN_PATHS], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(S.wt), "read-tree", "-mu", ref], check=True, capture_output=True)
    elif not S.wt.exists():
        subprocess.run(["git", "worktree", "add", "--detach", str(S.wt), ref], cwd=MAIN, check=True, capture_output=True)
    subprocess.run(["git", "-C", str(S.wt), "checkout", "-q", "--detach", ref], check=True)
    (S.wt / "envs").mkdir(exist_ok=True)
    env_src = _env_src()
    for d in env_links(env_src):
        p = S.wt / d
        if p.is_dir() and not p.is_symlink() and not any(p.iterdir()):
            p.rmdir()   # an env swept into a commit as a gitlink checks out as an empty directory: the link replaces it
        if not p.exists() and not p.is_symlink():
            p.symlink_to(env_src / d)
    if S.rows_rel == "data/benchmark_warmup.jsonl":   # official rows already live in data/; their local reference heartbeats are calibrated
        log(f"worktree {S.wt} at {ref}: warm-up rows used as committed"); return
    names = set(S.names)
    # 2026-10-13 (Phase A launch): with --problems S.rows is the subset, so only its heartbeats go in (the abpool file holds all 51 rows)
    hbs = [h for h in (json.loads(l) for l in S.hb_path.open() if l.strip()) if h["name"] in names]
    for f, new in (("data/benchmark_warmup.jsonl", S.rows), ("data/benchmark_heartbeats.jsonl", hbs)):
        p = S.wt / f
        keep = [l for l in p.read_text().splitlines() if l.strip() and json.loads(l)["name"] not in names]
        p.write_text("\n".join(keep + [json.dumps(r, ensure_ascii=False) for r in new]) + "\n")
    p = S.wt / "data/reference_heartbeats_local.json"; d = json.loads(p.read_text())
    for h in hbs:
        r = next(x for x in S.rows if x["name"] == h["name"])
        d[h["name"]] = {"toolchain": list(r["version_info"][0])[0], "heartbeats_local": h["heartbeat"], "heartbeats_official": h["heartbeat"], "ok": True}
    p.write_text(json.dumps(d, indent=1))
    log(f"worktree {S.wt} at {ref} ({subprocess.run(['git', '-C', str(S.wt), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()}), {len(S.rows)} rows")


def focus(todo: list, st: dict, a) -> list:
    """2026-10-13: give priority to the lowest-scoring rows and stop optimizing rows above 90. --skip-above X drops rows
    whose stored best is >= X (they count as done for the rung); --low-first orders the rest from the lowest best up, so the workers
    start on the rows furthest from the target."""
    sc = lambda n: (st.get(n) or {}).get("score", 33.33)
    if getattr(a, "skip_above", None) is not None:
        todo = [n for n in todo if sc(n) < a.skip_above]
    return sorted(todo, key=sc) if getattr(a, "low_first", False) else todo


def states(S: Set) -> dict:
    """Keyed by the problem name stored IN each state.json: work-dir names are sanitized and differ for some problems (2 rows of a
    held-out set on 2026-10-11, which the first version counted as unstarted: 33.33 and $0)."""
    res = {}
    for st in (S.wt / S.root).glob("*/state.json"):
        d = json.loads(st.read_text())
        if d.get("problem") in S.names:
            res[d["problem"]] = row_spend(d, {"score": d["best"].get("score") or 33.33})
    return res


def row_spend(d: dict, out: dict) -> dict:
    """b64 planner: a state's spend for the rung checks = api_spend (the metered, billed spend) + cap_extra (what the turns of a cap-priced
    session, e.g. an Argon first session, add at the cap price: agent.py b64 L0); `billed` = api_spend, only when they differ. Without
    cap_extra (every all-Sol row) the entry is {"score", "spend": api_spend}, as before."""
    billed, cx = float(d.get("api_spend") or 0), float(d.get("cap_extra") or 0)
    out["spend"] = billed + cx
    if cx:
        out["billed"] = billed
    return out


def targets(S: Set) -> dict:
    """Per-problem target score for choosing rescue problems: the union best on the warm-up (a score, not a proof); 100 elsewhere and on a
    "-clean" set (it knows nothing of earlier runs, as the final pipeline on a new row)."""
    if getattr(S, "clean", False):
        return {n: 100.0 for n in S.names}
    try:
        u = {e["name"]: e.get("union") for e in json.loads((MAIN / "leaderboard/problem_scores.json").read_text())["problems"]}
    except (OSError, ValueError, KeyError):
        u = {}
    return {n: (u.get(n) or 100.0) for n in S.names}


def safe(n: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", n)   # agent.py's work-dir / trajectory name for problem n


def typical_first(S: Set) -> dict:
    """Warm-up only: the score Sol + briefs typically reaches in its FIRST session on each problem (scores from the earlier solknow arm;
    knowledge, never proofs). Used to spot a bad first draw."""
    if S.prefix != "wu":
        return {}
    out = {}
    for st in (MAIN / "harness/hwork/solknow").glob("*/state.json"):
        d = json.loads(st.read_text())
        runs = [r.get("run_id") for r in d.get("runs", []) if r.get("run_id")]
        if runs:
            sc = [a.get("score") or 0 for a in d.get("attempts", []) if a.get("run_id") == runs[0] and a.get("ok")]
            if sc:
                out[d["problem"]] = max(sc)
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------
# b64 planner (T2, docs/first_half_gap.md section 6.2): --first-preset P [--first-effort E] --first-budget USD (--driver agent; off by
# default). A row's FIRST ladder session (session index 1 on the row: nothing spent on it yet, and no `first` record in lineage.json)
# runs agent.py --model-preset P --reasoning-effort E --budget-usd min(USD, the rung); every later session, a resumed ladder's included,
# runs the line's own --preset. The same opening, brief and per-session flags (`extra`) as every other session. agent.py gates the first
# session at P's CAP price (b64 L0, agent.cap_prices: Gemini 4 Argon at its announced $4 / $20, cached $0.20) and keeps the difference to
# the metered (billed) spend in state.json cap_extra; every later session's gate (agent.py _gate_spend) and this ladder's rung checks
# (row_spend) count it, so the rungs and the cap hold at the cap price; the reports keep the billed spend and add the cap-priced one.
# lineage.json `first` (per row): the preset, effort, budget, run id, billed and cap-priced spend and the score after the session; written
# once the first session has spent something (a first session without spend is retried with P, never marked full on the rung).
def first_on(a) -> bool:
    return bool(getattr(a, "first_preset", None)) and getattr(a, "driver", "agent") == "agent"


def first_due(a, n: str, st: dict, lin: dict) -> bool:
    """--first-preset: row n's next session is its first ladder session (no spend at the cap price, no lineage.json `first` record)."""
    return first_on(a) and float((st.get(n) or {}).get("spend") or 0) <= 0.0 and not (lin.get(n) or {}).get("first")


def first_budget(a, rung: float) -> float:
    """The first session's --budget-usd: min(--first-budget, the rung) (the row has spent nothing, so that is all of its room)."""
    return round(min(float(a.first_budget), float(rung)), 6)


def first_record(a, run_id: str, rung: float, s0: dict, s1: dict) -> dict:
    """The lineage.json `first` record of a first session that spent: s0 / s1 = the row's states() entry before / after."""
    return {"preset": a.first_preset, "effort": a.first_effort or a.effort, "budget": first_budget(a, rung), "run_id": run_id, "rung": rung,
            "billed": round(float(s1.get("billed", s1.get("spend", 0))) - float(s0.get("billed", s0.get("spend", 0))), 6),
            "cap": round(float(s1.get("spend", 0)) - float(s0.get("spend", 0)), 6), "score": s1.get("score")}


def first_turn_worst(prices, out_tokens: int) -> float:
    """The first turn's worst case at a price table (agent.py's gate: the opening context bounded by RECLAIM_OPEN_CTX, billed uncached, plus
    out_tokens of output): what a first session's budget must cover, or the session ends before its first call."""
    pi, po, _pr, pw = prices
    return (RECLAIM_OPEN_CTX * max(pi, pw) + out_tokens * po) / 1e6


def first_check(S: "Set", a, rungs: list[float]) -> str | None:
    """--first-preset at start-up, before any spend: the preset exists here and in the worktree's agent.py (at --ref), that agent.py gates at
    the cap price (agent.cap_prices, b64 L0) and counts cap_extra in every session's gate, and the first session's budget covers the first
    turn's worst case at the cap price (with --agent-budget-reclaim at the reclaim floor, else at the 12k first-turn cap). The reason
    otherwise."""
    sys.path.insert(0, str(MAIN))
    from harness.agent import MODEL_PRESETS, RECLAIM_FLOOR, cap_prices   # noqa: E402
    P = a.first_preset
    pp = MODEL_PRESETS.get(P)
    if not pp or pp.get("anthropic_vertex"):
        return f"--first-preset {P}: not an agent.py session preset"
    try:
        src = (S.wt / "harness/agent.py").read_text()
    except OSError:
        src = ""
    gate = re.search(r"def _gate_spend\(\)[^\n]*\n(?:[ \t]*#[^\n]*\n)*[ \t]*return ([^\n]+)", src)
    if f'"{P}"' not in src or "def cap_prices(" not in src:
        return f"--first-preset: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) has no preset {P} or no cap prices (b64 L0)"
    if not gate or "cap_extra" not in gate.group(1) or "_cap_diff" in gate.group(1):
        return (f"--first-preset: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) does not count cap_extra in every session's gate "
                "(a later session would gate the row without the first session's cap-price difference)")
    out = int(pp.get("adaptive_min", 6000)) if pp.get("adaptive_cap") else \
        (RECLAIM_FLOOR if getattr(a, "agent_budget_reclaim", False) else max(4000 * 3, int(pp.get("min_cap", 0))))
    worst = first_turn_worst(cap_prices(P), out)
    b = min(float(a.first_budget), min(rungs))
    if b + 1e-9 < worst:
        return (f"--first-budget: the first session's budget ${b:.2f} is below its first turn's worst case ${worst:.3f} at {P}'s cap price "
                f"({out} output tokens{' at the reclaim floor' if out == RECLAIM_FLOOR else ''}): it would end before its first call")
    return None


# ---------------------------------------------------------------------------------------------------------------------------------------
# b65 steps (T3-T5, probe/b65/steps_tests.md): --preset-by-rung "R1:P1[@E1],R2:P2[@E2],..." (--driver agent; off by default). A session
# working toward ladder rung R (the lowest rung above the row's spend: the rung the ladder is filling) runs agent.py --model-preset P
# [--reasoning-effort E]; a rung not listed runs --preset / --effort. Round and async mode, fresh lineages and the rescue (at the rung it
# fills), a resumed ladder and a checkpoint start (a row with inherited spend works toward the rung above it) alike; a first session
# (--first-preset) keeps its own preset. Every gate holds at the session preset's cap price: agent.py meters each turn at its preset's table
# (a list_price preset) and keeps any cap-price difference in state.json cap_extra (b64 L0), which every later session's gate and these rungs
# (row_spend) count, whatever preset ran it; with --agent-budget-reclaim a listed rung's session floor is its own preset's (rung_floor).
# Frozen in <out>/presets.json at the arm's first start (a resume that changes, adds or drops it is refused); router.py freezes it in
# config.json too. LINE_PRESET = --preset, so curve() prices the other presets' sessions at their cap price.
def rung_presets(spec: str | None) -> dict:
    """--preset-by-rung -> {rung (rounded to the cent): (preset, effort or None)}; ValueError on a malformed entry or a repeated rung."""
    out = {}
    for part in (spec or "").split(","):
        if not part.strip():
            continue
        r, sep, pe = part.strip().partition(":")
        p, _, e = pe.strip().partition("@")
        if not sep or not p.strip():
            raise ValueError(f"{part.strip()!r} is not RUNG:PRESET[@EFFORT]")
        R = round(float(r), 2)
        if not R > 0 or R in out:
            raise ValueError(f"rung {r.strip()} is not positive or appears twice")
        out[R] = (p.strip(), e.strip() or None)
    return out


def at_rung(a, rung: float):
    """The line's namespace for a session working toward `rung`: --preset-by-rung's preset and effort for that rung (a copy), else `a`."""
    hit = (getattr(a, "rung_map", None) or {}).get(round(float(rung), 2))
    if not hit or getattr(a, "driver", "agent") != "agent":
        return a
    return argparse.Namespace(**dict(vars(a), preset=hit[0], effort=hit[1] or a.effort))


# b66 (retro A3, docs/b66_robust.md): --preset-fallback "X:Y,...", the router's preset fallback after a CONFIRMED max_price pin of X. A
# substitution at the one place a session's preset is chosen (session_cmd: every session kind, the container's key mount included) and in
# the session floor (floor_at); the configured presets (presets.json, LINE_PRESET, LIST_PRICES, the reports) stay as they were.
def fallback_map(spec: str | None) -> dict:
    """--preset-fallback -> {X: Y}; ValueError on a malformed entry, X == Y or an X given twice."""
    out = {}
    for part in (spec or "").split(","):
        if not part.strip():
            continue
        x, sep, y = part.strip().partition(":")
        if not sep or not x.strip() or not y.strip() or x.strip() == y.strip() or x.strip() in out:
            raise ValueError(f"{part.strip()!r} is not X:Y (two different presets, each X once)")
        out[x.strip()] = y.strip()
    return out


def eff_preset(a, preset: str | None) -> str | None:
    """The preset a session configured for `preset` runs (--preset-fallback), else `preset`."""
    return (getattr(a, "fallback", None) or {}).get(preset, preset) if preset else preset


def fallback_check(S: "Set", a) -> str | None:
    """--preset-fallback at start-up, before any spend: every Y is an agent.py session preset on X's OpenRouter key, here and in the
    worktree's agent.py (at --ref), and that agent.py counts cap_extra in every session's gate (Y's cap price then holds on rows X began)."""
    sys.path.insert(0, str(MAIN))
    from harness.agent import MODEL_PRESETS   # noqa: E402
    try:
        src = (S.wt / "harness/agent.py").read_text()
    except OSError:
        src = ""
    for X, Y in sorted(a.fallback.items()):
        px, py = MODEL_PRESETS.get(X) or {}, MODEL_PRESETS.get(Y) or {}
        if not py or py.get("anthropic_vertex") or "openrouter.ai" not in (py.get("base_url") or ""):
            return f"--preset-fallback {X}:{Y}: {Y} is not an OpenRouter agent.py session preset"
        if px and px.get("key") != py.get("key"):
            return f"--preset-fallback {X}:{Y}: {Y} reads another key file than {X}"
        if f'"{Y}"' not in src:
            return f"--preset-fallback: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) has no preset {Y}"
    gate = re.search(r"def _gate_spend\(\)[^\n]*\n(?:[ \t]*#[^\n]*\n)*[ \t]*return ([^\n]+)", src)
    if not gate or "cap_extra" not in gate.group(1) or "_cap_diff" in gate.group(1):
        return f"--preset-fallback: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) does not count cap_extra in every session's gate"
    return None


def floor_at(a, rung: float) -> float:
    """The session floor of a rung: its --preset-by-rung preset's (a.rung_floor, set with --agent-budget-reclaim), else SESSION_FLOOR.
    b66 (A3): under --preset-fallback the floor of the preset the rung's sessions now run (a.fallback_floor, with --agent-budget-reclaim)."""
    ff = getattr(a, "fallback_floor", None)
    if ff:
        hit = (getattr(a, "rung_map", None) or {}).get(round(float(rung), 2))
        P = eff_preset(a, hit[0] if hit else a.preset)
        if P in ff:
            return ff[P]
    return (getattr(a, "rung_floor", None) or {}).get(round(float(rung), 2), SESSION_FLOOR)


def rung_check(S: "Set", a) -> str | None:
    """--preset-by-rung at start-up, before any spend: every preset is an agent.py session preset here and in the worktree's agent.py (at
    --ref), and that agent.py counts cap_extra in every session's gate (presets of different cap prices then share a row). The reason otherwise."""
    sys.path.insert(0, str(MAIN))
    from harness.agent import MODEL_PRESETS   # noqa: E402
    try:
        src = (S.wt / "harness/agent.py").read_text()
    except OSError:
        src = ""
    for R, (P, _e) in sorted(a.rung_map.items()):
        pp = MODEL_PRESETS.get(P)
        if not pp or pp.get("anthropic_vertex"):
            return f"--preset-by-rung {R:.2f}:{P}: not an agent.py session preset"
        if f'"{P}"' not in src:
            return f"--preset-by-rung: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) has no preset {P}"
    gate = re.search(r"def _gate_spend\(\)[^\n]*\n(?:[ \t]*#[^\n]*\n)*[ \t]*return ([^\n]+)", src)
    if not gate or "cap_extra" not in gate.group(1) or "_cap_diff" in gate.group(1):
        return (f"--preset-by-rung: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) does not count cap_extra in every session's gate")
    return None


def presets_freeze(S: "Set", a) -> str | None:
    """--preset-by-rung frozen in <out>/presets.json at the arm's first start (written only when set); the reason when a resume changes,
    adds or drops it (an arm that ran sessions without it has no file and refuses it)."""
    f = S.out / "presets.json"
    cur = {f"{R:.2f}": {"preset": P, "effort": E or a.effort} for R, (P, E) in sorted((getattr(a, "rung_map", None) or {}).items())} or None
    old = (json.loads(f.read_text()).get("preset_by_rung") or None) if f.exists() else None
    if f.exists() and old != cur:
        return f"--preset-by-rung: this arm started with {old}, now {cur} (frozen; a new --arm)"
    if cur and not f.exists():
        if rounds(S) or fresh_rounds(S):
            return f"--preset-by-rung: this arm ran sessions without it (frozen; a new --arm)"
        _write_json(f, {"preset_by_rung": cur, "preset": a.preset, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return None


def session_cmd(a, rung: float, root: str, run_id: str, names: list[str], workers: int, effort: str, restructure: bool, extra: list,
                tag: str | None = None, preset: str | None = None, budget: float | None = None) -> list:
    """One batch of sessions. --driver agent: harness/agent.py with the hosted preset (hard per-turn gate at list prices). --driver codex
    (2026-10-12): GPT-6.1 Sol through the Codex CLI on the ChatGPT plan, in Docker, priced at list prices from Codex's own token counts with
    a time gate and a per-call watchdog (harness/agent_codex.py); at most 3 containers; no restructure brief (a codex rescue is a plain
    fresh session at the rescue effort). --driver claude (2026-10-12, docs/cc_driver_v2.md §5): Opus through Claude Code on the subscription,
    list-metered with the hard per-session gate at the rung (harness/agent_claude_code.py --budget-usd); a restructure session is
    --from-reference under prompt v2 and a plain fresh session under v1."""
    if a.driver == "claude":
        return ["python3", "harness/agent_claude_code.py", "--model", a.claude_model, "--prompt", a.claude_prompt, "--effort", effort,
                "--cache-ttl", a.claude_cache, "--turns", "40", "--workers", str(workers), "--budget-usd", str(rung),
                "--budget-milestones", "1.0,1.4,1.7,2.0", "--work-root", root, "--run-id", run_id,
                *(["--from-reference"] if restructure and a.claude_prompt == "v2" else []), *(["--sealed"] if a.claude_sealed else []),
                *(["--gate-cap", str(a.claude_gate_cap)] if getattr(a, "claude_gate_cap", None) is not None else []),
                *(["--ceiling"] if getattr(a, "claude_ceiling", False) else []),
                *(["--exemplars"] if getattr(a, "claude_exemplars", False) and a.claude_prompt == "v2" else []), *extra, "--problems", *names]
    if a.driver == "codex":
        return ["python3", "harness/agent_codex.py", "--model", a.codex_model, "--effort", effort, "--turns", "40", "--workers", str(max(1, min(workers, 3))),
                "--budget-usd", str(rung), "--budget-milestones", "2.0", "--work-root", root, "--run-id", run_id,
                *(["--docker", a.codex_docker, "--docker-memory", a.codex_docker_memory] if a.codex_docker else []),
                *(["--sealed", "--private-scratch", a.codex_private_scratch] if a.codex_sealed else []),
                *(["--max-usd-per-min", str(a.max_usd_per_min)] if a.max_usd_per_min else []), *extra, "--problems", *names]
    # b64 planner: `preset` / `budget` (a first session, --first-preset) replace --preset / the rung for this batch only; the container then
    # mounts that preset's key (agent_docker reads it from a.preset). b66 (A3): --preset-fallback substitutes the preset here, once for
    # every session kind (round, async, fresh lineage, rescue, first session)
    if getattr(a, "fallback", None) and eff_preset(a, preset or a.preset) != (preset or a.preset):
        preset = eff_preset(a, preset or a.preset)
    inner = ["python3", "harness/agent.py", "--model-preset", preset or a.preset, "--reasoning-effort", effort, "--turns", "40", "--no-adaptive-turns",
             "--max-tokens", "4000", "--budget-usd", str(rung if budget is None else budget), "--budget-milestones", "2.0", "--workers", str(workers),
             "--work-root", root, "--run-id", run_id, *(["--from-reference", "--brief", "restructure"] if restructure else []),
             *extra, "--problems", *names]
    return agent_docker(a if preset is None else argparse.Namespace(**dict(vars(a), preset=preset)), run_id, inner, tag) if a.agent_docker else inner


REVIEW_TIMEOUT = 1200   # seconds per reviewer session (one message, no tool calls: minutes)


def review_cmd(a, rung: float, root: str, run_id: str, names: list[str], workers: int) -> list:
    """One batch of reviewer sessions (--claude-review, docs/cc_driver_v2.md §11): agent_claude_code.py --review at the review effort, gated at
    the review budget within the rung (the ledger is the rows' own), same model, cache TTL, sealing and ceiling as the line's sessions."""
    return ["python3", "harness/agent_claude_code.py", "--model", a.claude_model, "--prompt", "v2", "--review", "--review-budget",
            str(a.claude_review_budget), "--effort", a.claude_review_effort, "--cache-ttl", a.claude_cache, "--timeout", str(REVIEW_TIMEOUT),
            "--workers", str(workers), "--budget-usd", str(rung), "--budget-milestones", "1.0,1.4,1.7,2.0", "--work-root", root, "--run-id", run_id,
            *(["--sealed"] if a.claude_sealed else []), *(["--ceiling"] if getattr(a, "claude_ceiling", False) else []),
            *(["--gate-cap", str(a.claude_gate_cap)] if getattr(a, "claude_gate_cap", None) is not None else []), "--problems", *names]   # 2026-10-13: without it a review's gate was $2.85 minus the row's spend, i.e. skipped


def cc_spill(S: Set, say) -> int:
    """--driver claude on a sealed set (2026-10-12 review; probe/heldout/run_sealed3_opus.sh does the same per pass): Claude Code writes
    project folders named after the session's cwd, i.e. the sealed problem's name, under ~/.claude/projects even with
    --no-session-persistence (commit 78595cfa). After every batch they are moved into this line's own records, with a warning."""
    pj = pathlib.Path.home() / ".claude/projects"
    hits = sorted(pj.glob(f"*lra-ab-{S.prefix}-hx*")) if pj.is_dir() else []
    if hits:
        dst = S.out / "claude_projects"; dst.mkdir(parents=True, exist_ok=True)
        for h in hits:
            shutil.move(str(h), str(dst / f"{h.name}.{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}"))
        say(f"WARNING: {len(hits)} Claude Code project folder(s) named after sealed rows were under ~/.claude/projects; moved to {dst}")
    return len(hits)


def _env_src() -> pathlib.Path:
    """The checkout that holds the built environments (envs/ of the repository's main working tree; worktrees link to it)."""
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=MAIN, capture_output=True, text=True).stdout.strip()
    return pathlib.Path(common).parent if common else MAIN


def compile_env(p: pathlib.Path) -> bool:
    """A built compile environment: a real directory with a lakefile, not a *.git-main upstream clone or the mathlib4 source checkout."""
    real = p.resolve()
    return (real.is_dir() and not real.name.endswith(".git-main") and real.name != "mathlib4"
            and any((real / f).exists() for f in ("lakefile.lean", "lakefile.toml")))


def env_links(env_src: pathlib.Path) -> list:
    """envs/ entries a set's worktree links to env_src's: every entry env_src's .gitignore ignores (built envs, upstream clones, logs)
    PLUS every compile env by shape whatever its git status. 2026-10-25 (LeanPool, the sixth library): an env that main's .gitignore
    does not cover - no pattern yet, or swept into a commit as a gitlink by an `add -A` - was never linked, so its rows had no
    environment in the set's worktree (the v3 launch incident's class: every compile fails, the spend is wasted)."""
    ign = subprocess.run(["git", "status", "--ignored", "--porcelain", "envs"], cwd=env_src, capture_output=True, text=True).stdout
    out = {l[3:].rstrip("/") for l in ign.splitlines() if l.startswith("!!")}
    if (env_src / "envs").is_dir():
        out |= {f"envs/{e.name}" for e in (env_src / "envs").iterdir() if compile_env(e)}
    return sorted(out)


def missing_envs(S: "Set") -> list:
    """`<source>@<toolchain>` of every pin a row of the set lists whose compile env does not resolve in the set's worktree (no lakefile
    there). Sources and toolchains only, never row names (sealed sets). Called before the first session: a missing env means every
    compile of those rows fails."""
    sys.path.insert(0, str(MAIN))
    from scorer.compile import PROJECT_DIRS   # noqa: E402
    miss = set()
    for r in S.rows:
        for v in (k for d in r.get("version_info") or [] for k in d):
            d = f"mathlib-{v}" if r["source"] == "putnambench" else f"{PROJECT_DIRS.get(r['source'], r['source'])}-{v}"
            if not compile_env(S.wt / "envs" / d):
                miss.add(f"{r['source']}@{v}")
    return sorted(miss)


def scratch_binds(private_root: str) -> list:
    """Nested binds that give a container its own compile scratch: <private_root>/<env> over every compile env's LRAScratch (docker mounts
    parents first). Compile envs only: a lakefile, not the *.git-main upstream clones or the mathlib4 source checkout. 2026-10-25: the envs
    are enumerated in this checkout's envs/ AND in the main checkout's (a fresh run checkout has none until linked by hand: v3 incident)."""
    vols, seen = [], set()
    srcs = [MAIN / "envs", _env_src() / "envs"]
    for e in sorted({x for s in srcs if s.is_dir() for x in s.iterdir()}, key=lambda x: x.name):
        real = e.resolve()
        if real in seen:
            continue
        seen.add(real)
        if compile_env(e):
            (real / "LRAScratch").mkdir(exist_ok=True)
            mine = pathlib.Path(private_root).resolve() / real.name; mine.mkdir(parents=True, exist_ok=True)
            vols += ["-v", f"{mine}:{real / 'LRAScratch'}:rw"]
    return vols


_STRAYS: list = []   # (host path, is_dir) of the stray env files, listed once per ladder


def stray_masks(private_root: str) -> list:
    """--agent-mask-strays (2026-10-13 clean recheck review): the read-only envs mount also shows files that hold proofs of benchmark rows:
    untracked files at the top of the main envs/ (envs/notes.md: notes on warm-up proofs) and untracked files inside each env checkout (old
    probes and scratch, e.g. LRAProbe/, scratch/, s25.lean). Each is covered by an empty read-only file or directory in the container."""
    if not _STRAYS:
        def untracked(cwd: pathlib.Path, *path: str) -> list:
            out = subprocess.run(["git", "status", "--porcelain", "-z", "--untracked-files=normal", *path], cwd=cwd, capture_output=True,
                                 text=True).stdout
            return [cwd / e[3:].rstrip("/") for e in out.split("\0") if e.startswith("?? ")]
        # the env directories live in the main checkout (worktrees link to them), so the strays are looked up there whatever runs this
        _common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=MAIN, capture_output=True, text=True).stdout.strip()
        env_src = pathlib.Path(_common).parent if _common else MAIN
        hits = [h for h in untracked(env_src, "envs") if not compile_env(h)]   # 2026-10-25: an env not yet in .gitignore is not a stray
        # review 2026-10-21: tracked files at the top of envs/ other than the manifest and the build scripts (envs/notes.md: warm-up notes)
        _tr = subprocess.run(["git", "ls-files", "-z", "envs"], cwd=env_src, capture_output=True, text=True).stdout.split("\0")
        hits += [env_src / t for t in _tr if t.count("/") == 1 and not re.match(r"envs/(manifest\.(json|py)|[\w.-]+\.sh)$", t)
                 and (env_src / t).is_file()]
        for e in sorted({x.resolve() for s in (MAIN / "envs", env_src / "envs") if s.is_dir() for x in s.iterdir()}):   # 2026-10-25: + main's
            real = e.resolve()
            if real.is_dir() and real.name.endswith(".git-main"):   # 2026-10-21 (no upstream history): later versions of the proofs
                hits.append(real); continue
            if real.is_dir() and (real / ".git").exists():
                hits += [h for h in untracked(real) if h.name not in ("LRAScratch", ".lake")]
        _STRAYS.extend((h, h.is_dir()) for h in hits)
    m = pathlib.Path(private_root).resolve() / "_mask"; (m / "dir").mkdir(parents=True, exist_ok=True); (m / "file").touch()
    vols = []
    for h, isdir in _STRAYS:
        vols += ["-v", f"{m / ('dir' if isdir else 'file')}:{h}:ro"]
    return vols


def autobrief_plan(S: Set, a) -> tuple | None:
    """--agent-auto-brief: (brief dir relative to the worktree, rows without a brief yet, run id, command) or None when every row has one.
    The command is harness/autobrief.py, in the line's container when --agent-docker; --auto-brief-row-workers (default 2) and
    --auto-brief-longest-first (2026-10-22) are its only knobs, so with both at their defaults it is the command used before them.
    2026-10-26 (b64-brief): --auto-brief-compile-workers N (default 3, the literal it replaces) is autobrief.py --workers, and
    --auto-brief-docker-memory (default: --agent-docker-memory) is the brief container's --memory; at the defaults the command is unchanged."""
    od = f"{S.root}/_autobrief"
    todo = [n for n in S.names if not (S.wt / od / f"{safe(n)}.json").exists()]
    if not todo:
        return None
    inner = ["python3", "-u", "harness/autobrief.py", "--out-dir", od, "--budget", str(a.auto_brief_budget),
             "--workers", str(getattr(a, "auto_brief_compile_workers", 3)),
             "--row-workers", str(getattr(a, "auto_brief_row_workers", 2)),
             *(["--longest-first"] if getattr(a, "auto_brief_longest_first", False) else []), "--problems", *todo]
    rid = f"{S.run_prefix[:-1]}ab"
    return od, todo, rid, (agent_docker(a, rid, inner, memory=autobrief_docker_memory(a)) if a.agent_docker else inner)


def autobrief_docker_memory(a) -> str:
    """The brief container's --memory (and --memory-swap): --auto-brief-docker-memory, else --agent-docker-memory (2026-10-26, b64-brief)."""
    return getattr(a, "auto_brief_docker_memory", None) or a.agent_docker_memory


def c0_plan(S: Set, a) -> tuple | None:
    """--agent-c0: (rows without a C0 record yet, run id, command) or None. harness/cpu_pass.py over the line's work root and auto-brief dir,
    in the line's container when --agent-docker (the same mounts as the brief: the work root is writable there)."""
    todo = [n for n in S.names if not (S.wt / S.root / safe(n) / "cpu_pass.json").exists()]
    if not todo:
        return None
    inner = ["python3", "-u", "harness/cpu_pass.py", "--work-root", S.root, "--auto-brief-dir", f"{S.root}/_autobrief", "--config", a.agent_c0,
             "--jobs", "2", "--problems", *todo]
    rid = f"{S.run_prefix[:-1]}c0"
    return todo, rid, (agent_docker(a, rid, inner) if a.agent_docker else inner)


def c0_start(S: Set, a, say) -> None:
    """--agent-c0 (b63 item 6): the C0 pre-session pass after the auto-brief, before any session; bounded by --c0-timeout."""
    plan = c0_plan(S, a)
    if not plan:
        return
    todo, rid, cmd = plan
    say(f"C0 pass: {len(todo)} seed(s) through the end stage {a.agent_c0} (timeout {a.c0_timeout}s)")
    t0 = time.time()
    with (S.out / "c0.log").open("a") as f:
        try:
            subprocess.run(cmd, cwd=S.wt, stdout=f, stderr=subprocess.STDOUT, timeout=a.c0_timeout)
        except subprocess.TimeoutExpired:
            if a.agent_docker:
                subprocess.run(["docker", "stop", container_name(rid)], capture_output=True)
            say("C0 pass: timeout; the remaining rows start from their brief's start candidate")
    done = sum((S.wt / S.root / safe(n) / "cpu_pass.json").exists() for n in todo)
    say(f"C0 pass: {done}/{len(todo)} rows with a record in {time.time() - t0:.0f}s")


def autobrief_knobs(a) -> str:
    """The knobs line of the brief's start message; the 2026-10-26 knobs appear only when not at their defaults (the line is unchanged)."""
    cw, mem = getattr(a, "auto_brief_compile_workers", 3), getattr(a, "auto_brief_docker_memory", None)
    return (f"row workers {getattr(a, 'auto_brief_row_workers', 2)}, {'longest seed first' if getattr(a, 'auto_brief_longest_first', False) else 'listed order'}"
            f"{f', compile workers {cw}' if cw != 3 else ''}{f', container memory {mem}' if mem and getattr(a, 'agent_docker', None) else ''}"
            f"{', pipelined with round 1' if getattr(a, 'auto_brief_pipeline', False) else ''}")


def autobrief_start(S: Set, a, say) -> None:
    """--agent-auto-brief: harness/autobrief.py over the rows without a brief yet, CPU only, before any session; in the line's container
    (its private scratch, its view) when --agent-docker. Bounded by --auto-brief-timeout: on expiry the container is stopped and the rows
    without a brief go on without one (agent.py says so per row)."""
    plan = autobrief_plan(S, a)
    if not plan:
        return
    od, todo, rid, cmd = plan
    (S.wt / od).mkdir(parents=True, exist_ok=True)
    say(f"auto-brief: measuring {len(todo)} seed(s) (budget {a.auto_brief_budget} compiles per row, timeout {a.auto_brief_timeout}s; "
        f"{autobrief_knobs(a)})")
    t0 = time.time()
    with (S.out / "autobrief.log").open("a") as f:
        try:
            subprocess.run(cmd, cwd=S.wt, stdout=f, stderr=subprocess.STDOUT, timeout=a.auto_brief_timeout)
        except subprocess.TimeoutExpired:
            if a.agent_docker:
                subprocess.run(["docker", "stop", container_name(rid)], capture_output=True)
            say("auto-brief: timeout; the remaining rows go on without a brief")
    done = sum((S.wt / od / f"{safe(n)}.json").exists() for n in todo)
    say(f"auto-brief: {done}/{len(todo)} rows measured in {time.time() - t0:.0f}s")


AB_GRACE = 300   # seconds past the brief's timeout that a gated session may still wait for the end marker (stop + marker take ~10-130 s)


class AutoBrief:
    """--auto-brief-pipeline (2026-10-22, docs/speed_review.md item 7): the auto-brief of autobrief_start in the BACKGROUND. Same command,
    container, private scratch and --auto-brief-timeout; a watcher thread enforces the timeout exactly as autobrief_start does (the docker
    client killed, then `docker stop` of the container), logs the same lines, and then writes the end marker (brief_gate.ENDED) that opens
    every waiting session's gate. gate_args() is what round 1's agent.py batch adds (--auto-brief-wait: the brief's remaining timeout plus
    AB_GRACE, so a session never waits unboundedly, even for a ladder that died before writing the marker). finish() waits for the end
    (bounded); stop() ends it early (any exit of the ladder, or SIGTERM / SIGHUP: the container never outlives the ladder)."""

    def __init__(self, S: Set, a, say, od: str, todo: list, rid: str, cmd: list):
        sys.path.insert(0, str(MAIN))
        from harness.brief_gate import ENDED   # noqa: E402  (the marker name; the worktree's agent.py reads the same constant)
        self.S, self.a, self.say, self.od, self.todo, self.rid = S, a, say, od, todo, rid
        self.name = container_name(rid) if a.agent_docker else None
        self.marker = S.wt / od / ENDED
        self.timeout = float(a.auto_brief_timeout)
        self.stopping: str | None = None
        self.timed_out = False
        self._kill_lock = threading.RLock(); self._killed = False   # reentrant: a signal handler may run inside the main thread's _kill
        self._prev: dict = {}
        (S.wt / od).mkdir(parents=True, exist_ok=True)
        try:
            self.marker.unlink()   # a marker left by an earlier pipelined ladder would open every gate at once
        except FileNotFoundError:
            pass
        say(f"auto-brief: measuring {len(todo)} seed(s) (budget {a.auto_brief_budget} compiles per row, timeout {a.auto_brief_timeout}s; "
            f"{autobrief_knobs(a)})")
        self.t0 = time.time()
        with (S.out / "autobrief.log").open("a") as f:   # the child keeps its own copy of the descriptor
            self.p = subprocess.Popen(cmd, cwd=S.wt, stdout=f, stderr=subprocess.STDOUT)
        self.watcher = threading.Thread(target=self._watch, name="lra-autobrief-watch", daemon=True)
        self.watcher.start()
        if threading.current_thread() is threading.main_thread():
            for sg in (signal.SIGTERM, signal.SIGHUP):
                h = signal.getsignal(sg)
                if h is not None and h != signal.SIG_IGN:   # an ignored signal (nohup) stays ignored; None (a C-level handler) cannot be restored
                    self._prev[sg] = signal.signal(sg, self._on_signal)

    def gate_args(self) -> list:
        left = max(0.0, self.timeout - (time.time() - self.t0))
        return ["--auto-brief-wait", str(int(left + AB_GRACE))]

    def _kill(self) -> None:
        """The timeout path of autobrief_start: kill the (docker client) process, then stop the container by name; once, bounded."""
        with self._kill_lock:
            if self._killed:
                return
            self._killed = True
        try:
            self.p.kill()
        except OSError:
            pass
        if self.name:
            try:
                subprocess.run(["docker", "stop", self.name], capture_output=True, timeout=120)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def _watch(self) -> None:
        try:
            self.p.wait(timeout=max(0.0, self.timeout - (time.time() - self.t0)))
        except subprocess.TimeoutExpired:
            self.timed_out = True
            self._kill()
        killed = self._killed   # False: the process ended by itself (a stop() arriving after that changes nothing)
        try:
            self.p.wait(timeout=AB_GRACE)
        except subprocess.TimeoutExpired:
            pass
        if self.timed_out:
            self.say("auto-brief: timeout; the remaining rows go on without a brief")
        elif killed and self.stopping:
            self.say(f"auto-brief: stopped ({self.stopping}); the remaining rows go on without a brief")
        done = sum((self.S.wt / self.od / f"{safe(n)}.json").exists() for n in self.todo)
        self.say(f"auto-brief: {done}/{len(self.todo)} rows measured in {time.time() - self.t0:.0f}s")
        tmp = self.marker.with_name(self.marker.name + ".tmp")
        try:
            tmp.write_text(json.dumps({"ended": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rc": self.p.returncode,
                                       "timeout": self.timed_out, "stopped": self.stopping, "measured": done, "rows": len(self.todo)}) + "\n")
            os.replace(tmp, self.marker)
        except OSError as e:   # the gated sessions still start at their wait bound
            self.say(f"auto-brief: could not write the end marker ({type(e).__name__}: {e}); waiting sessions start at their wait bound")

    def _restore(self) -> None:
        if threading.current_thread() is threading.main_thread():
            for sg, h in self._prev.items():
                signal.signal(sg, h)
        self._prev = {}

    def finish(self) -> None:
        """Wait for the brief process to end (bounded by its own timeout plus the grace); stop it if it somehow has not."""
        self.watcher.join(timeout=max(0.0, self.timeout - (time.time() - self.t0)) + AB_GRACE)
        if self.watcher.is_alive():
            self.stop("still running past its timeout")
        self._restore()

    def stop(self, why: str, join_s: float = AB_GRACE) -> None:
        """End the brief process now (the ladder is ending), as its timeout would; bounded."""
        if self.watcher.is_alive():
            self.stopping = why
            if self.p.poll() is None:
                self._kill()
            self.watcher.join(timeout=join_s)
        self._restore()

    def _on_signal(self, signum, frame) -> None:
        prev = dict(self._prev)
        self.stop(f"signal {signal.Signals(signum).name}", join_s=60)   # the signal's own action follows within a minute at most
        h = prev.get(signum, signal.SIG_DFL)
        if callable(h):
            h(signum, frame)
        elif h == signal.SIG_DFL:
            os.kill(os.getpid(), signum)


def autobrief_launch(S: Set, a, say) -> AutoBrief | None:
    """--auto-brief-pipeline: start the brief in the background; None when every row already has its brief (nothing to wait for)."""
    plan = autobrief_plan(S, a)
    return AutoBrief(S, a, say, *plan) if plan else None


def container_name(run_id: str, tag: str | None = None) -> str:
    """The --agent-docker container name of a batch started by this ladder process (agent_docker's --name). tag (--async-ladder: the
    row's index, s<NN>) keeps the names of one round's concurrent single-row sessions apart; never a row name (sealed sets)."""
    return f"lra-ag-{re.sub(r'[^A-Za-z0-9_.-]', '_', run_id)}-{tag + '-' if tag else ''}{os.getpid()}"


# 2026-10-26 (b64-brief): the ladder's environment variables a container gets (as -e NAME=value; DOCKER_PASS_ENV): the memory gate's knobs
# (scorer/memgate.py: LRA_MEMGATE_CLAIM_MB / _RESERVE_MB / _RELAX_S / _MAX_WAIT_S; the router unit's claim 4000 / reserve 4000 never reached
# the brief, which then admitted ~3 compiles at once in its 48g container) and hb_tool's compile slots per scratch (harness/hb_tool_eval.py).
# LRA_MEMGATE_DIR is NOT passed: it names a host directory the container does not mount, and the gate's ledger (pids) must stay the
# container's own (its /tmp). Nothing else of the ladder's environment reaches a container (never a key).
DOCKER_PASS_PREFIXES = ("LRA_MEMGATE_",)
# 2026-10-27 (b66 closed package): + LRA_SELFTEST_PRESET_URL, the $0 rehearsal's fake OpenRouter (infra/closed_package/fake_openrouter.py):
# agent.py then sends every preset call there and reads no key (agent.main); unset in every real run, so nothing is passed there
# b71 R1 (docs/b71_final.md): + LRA_FORCE_WARN_SORRY, the sorry guard (scorer.compile.force_warn_sorry: warn.sorry forced on where a pin's
# lakefile turns it off, PhysLib), so agent.py's compiles inside the container reject a proof that depends on sorryAx exactly as the host's
DOCKER_PASS_NAMES = ("LRA_HBTOOL_SLOTS", "LRA_SELFTEST_PRESET_URL", "LRA_FORCE_WARN_SORRY")
DOCKER_PASS_SKIP = ("LRA_MEMGATE_DIR",)


def docker_pass_env(environ=None) -> list:
    """-e NAME=value for every DOCKER_PASS_* variable present in `environ` (default: this process's), in name order; [] when none."""
    environ = os.environ if environ is None else environ
    out = []
    for k in sorted(environ):
        if (k in DOCKER_PASS_NAMES or k.startswith(DOCKER_PASS_PREFIXES)) and k not in DOCKER_PASS_SKIP:
            out += ["-e", f"{k}={environ[k]}"]
    return out


def agent_docker(a, run_id: str, inner: list, tag: str | None = None, memory: str | None = None) -> list:
    """--agent-docker (2026-10-12 launch review: agent.py's shell tool is host bash, so on the host a sealed line could read other lines'
    files and compile scratch): the agent.py batch runs in a container holding only this line's worktree (read-only), its work roots and
    records (read-write), the envs (read-only) with a private compile scratch, the Lean toolchains (read-only) and the preset's one key file
    (read-only, at the container's HOME=/tmp). --init forwards a unit stop to agent.py, so no container outlives its ladder.
    2026-10-26 (b64-brief): plus docker_pass_env() (the ladder's memgate / hb_tool slot variables; none set = the command line before it);
    `memory` (the brief's --auto-brief-docker-memory) replaces --agent-docker-memory for this container only."""
    sys.path.insert(0, str(MAIN))
    from harness.agent import MODEL_PRESETS   # noqa: E402  (the key path of the preset; the worktree's copy runs inside)
    home, wt = pathlib.Path.home(), a.wt
    key = pathlib.Path(MODEL_PRESETS[a.preset]["key"]).expanduser().resolve()
    for d in ("harness/hwork", "probe/runs"):
        (wt / d).mkdir(parents=True, exist_ok=True)
    targets = sorted({str(e.resolve().parent) for e in (wt / "envs").iterdir() if e.is_symlink() and e.resolve().exists()})
    vols = ["-v", f"{wt}:{wt}:ro", "-v", f"{wt / 'harness/hwork'}:{wt / 'harness/hwork'}:rw", "-v", f"{wt / 'probe/runs'}:{wt / 'probe/runs'}:rw"]
    for t in targets:
        vols += ["-v", f"{t}:{t}:ro"]
    vols += scratch_binds(a.agent_private_scratch)
    if getattr(a, "agent_mask_strays", False):
        vols += stray_masks(a.agent_private_scratch)
    vols += ["-v", f"{home / '.elan'}:{home / '.elan'}:ro", "-v", f"{key}:/tmp/{key.relative_to(home)}:ro"]
    if ".azure.com" in MODEL_PRESETS[a.preset].get("base_url", ""):   # 2026-10-14: the Azure presets are built from this config inside too
        from harness.agent import AZURE_CONFIG   # noqa: E402
        vols += ["-v", f"{AZURE_CONFIG.resolve()}:/tmp/{AZURE_CONFIG.resolve().relative_to(home)}:ro"]
    name = container_name(run_id, tag)
    mem = memory or a.agent_docker_memory
    return ["docker", "run", "--rm", "--init", "--name", name, "--memory", mem, "--memory-swap", mem,
            "--user", f"{os.getuid()}:{os.getgid()}", "-w", str(wt), *vols, "-e", "HOME=/tmp", "-e", f"ELAN_HOME={home / '.elan'}",
            "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", f"PATH={home / '.elan/bin'}:/usr/local/bin:/usr/bin:/bin", *docker_pass_env(),
            a.agent_docker, *inner]


def fresh_round(S: Set, names: list[str], rung: float, run_id: str, effort: str, restructure: bool, extra: list, a,
                workers: int, say, froot: pathlib.Path | None = None, tag: str | None = None, log_path: pathlib.Path | None = None) -> None:
    """One session per problem in an EMPTY workspace (2026-10-11: a rescue does not resume from the current checkpoint): its
    state.json holds no proof, notes or variants, only the problem's spend so far, so the agent's hard cap at `rung` covers the main and
    the fresh lineage together. Afterwards the spend carries back, the fresh best replaces the main best only if higher, and the fresh
    workspace is archived (never resumed). --async-ladder: froot = the row's own fresh root (<root>-fresh.<tag>, one row), only that root
    is recovered first (other rows' fresh lineages may be in flight), archived as <root>-fresh.done-<run id>.<tag>; log_path = the session's
    own log."""
    own = froot is not None
    froot = froot if own else S.wt / f"{S.root}-fresh"
    recover_fresh(S, say, froot if own else None)   # a fresh lineage an earlier ladder left unmerged is merged first (its spend), never overwritten
    main = {}
    for p in (S.wt / S.root).glob("*/state.json"):
        try:
            main[json.loads(p.read_text()).get("problem")] = p
        except (OSError, ValueError):   # --async-ladder: another row's session may be rewriting its state.json right now (not this row's)
            if not own:
                raise
    rows = {r["name"]: r for r in S.rows}
    facts = a.driver == "claude" and getattr(a, "claude_fresh_facts", False)
    for n in names:
        d = froot / safe(n); d.mkdir(parents=True, exist_ok=True)
        m0 = json.loads(main[n].read_text()) if n in main else {}
        spend = float(m0.get("api_spend") or 0)
        # b64 planner: a row whose first session ran at a cap price carries its cap_extra into the fresh state too (the fresh session's gate
        # counts it, agent.py _gate_spend); no key without one (the fresh state as before)
        capx = {"cap_extra": float(m0["cap_extra"])} if m0.get("cap_extra") else {}
        (d / "state.json").write_text(json.dumps({"problem": n, "best": {"score": 33.33, "proof": None, "tokens": rows[n]["proof_length"], "heartbeats": None},
                                                  "attempts": [], "runs": [], "api_spend": spend, "lineage": "fresh", **capx}, ensure_ascii=False, indent=1))
        (d / "notes.md").write_text("# Notes (yours to keep; persisted across runs)\n")
        if facts and n in main:   # --claude-fresh-facts (§11): the main lineage's facts sheet (numbers, failed checks, notes' Failed / Next; no proof)
            try:
                (d / "lineage_facts.md").write_text(lineage_facts(S, main[n]) + "\n")
            except Exception as e:  # noqa: BLE001  (review 2026-10-12: a failed sheet costs the fresh lineage its facts, never the ladder)
                say(f"  lineage facts for {n} failed ({type(e).__name__}: {e}); the fresh lineage starts without them")
    tf = S.wt / S.root / "_run_techniques.json"
    if tf.exists():   # round 2: v2 sessions of a fresh lineage are the same line, so they see its run techniques (built in-run only)
        shutil.copyfile(tf, froot / "_run_techniques.json")
    cmd = session_cmd(a, rung, str(froot.relative_to(S.wt)), run_id, names, workers, effort, restructure, extra, tag)
    with (log_path or S.out / f"{run_id}.log").open("a") as f:
        subprocess.run(cmd, cwd=S.wt, stdout=f, stderr=subprocess.STDOUT)
    for n in names:
        fs = froot / safe(n) / "state.json"
        if not fs.exists() or n not in main:
            continue
        merge_fresh_state(fs, main[n], run_id, restructure, say)
    froot.rename(S.wt / (f"{S.root}-fresh.done-{run_id}.{tag}" if own else f"{S.root}-fresh.done-{run_id}"))


_REF_LEVERS: dict = {}   # worktree cc_levers.py -> its module, loaded once per ladder


def lineage_facts(S: Set, mp: pathlib.Path) -> str:
    """--claude-fresh-facts: the facts sheet of the main lineage's state (mp) and notes for a fresh lineage of the same row: the best's numbers,
    failed checks by error class, the notes' Failed / Next lines, Lean blocks over 2 lines removed; never the proof (harness/cc_levers.py).
    Review 2026-10-12: cc_levers comes from the line's worktree (S.wt, checked out at --ref, as every session and post-batch step), never from
    the main checkout, which may have moved on by the first fresh restart (hours into a long ladder)."""
    src = S.wt / "harness/cc_levers.py"
    if src not in _REF_LEVERS:
        import importlib.util
        spec = importlib.util.spec_from_file_location(f"lra_ref_cc_levers_{len(_REF_LEVERS)}", src)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); _REF_LEVERS[src] = mod
    LV = _REF_LEVERS[src]
    try:
        notes = (mp.parent / "notes.md").read_text()
    except OSError:
        notes = ""
    return LV.facts_sheet(json.loads(mp.read_text()), notes, head=LV.FRESH_FACTS_HEAD)


def merge_fresh_state(fs: pathlib.Path, mp: pathlib.Path, run_id: str, restructure, say, recovered: bool = False) -> None:
    """One fresh lineage's state into the main state: spend (max: the fresh state was seeded with main's), milestones, the best if higher."""
    r = json.loads(fs.read_text()); m = json.loads(mp.read_text())
    added = float(r.get("api_spend") or 0) - float(m.get("api_spend") or 0)
    gain = (r["best"].get("score") or 0) > (m["best"].get("score") or 0)
    m["api_spend"] = max(float(m.get("api_spend") or 0), float(r.get("api_spend") or 0))   # seeded with main's spend: fresh = main + new
    if r.get("cap_extra") or m.get("cap_extra"):   # b64 planner: seeded with main's too (fresh_round)
        m["cap_extra"] = max(float(m.get("cap_extra") or 0), float(r.get("cap_extra") or 0))
    if gain:
        m["best"] = r["best"]
    if r.get("budget_milestones"):
        m.setdefault("budget_milestones", {}).update({k: v for k, v in r["budget_milestones"].items() if k not in m.get("budget_milestones", {})})
    m.setdefault("fresh_lineages", []).append({"run_id": run_id, "spend": round(added, 6), "score": r["best"].get("score"), "adopted": gain,
                                               "restructure": restructure, "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                               **({"recovered": True} if recovered else {})})
    mp.write_text(json.dumps(m, ensure_ascii=False, indent=1))
    say(f"  fresh lineage ({'restructure' if restructure else 'restart' if restructure is not None else 'recovered'}): +${added:.3f}, "
        f"{r['best'].get('score')} -> {'ADOPTED' if gain else 'main best kept'}")


def recover_fresh(S: Set, say, froot: pathlib.Path | None = None) -> int:
    """Round-2 review (2026-10-12): a ladder that died during a fresh lineage (unit stop, OOM, an arm timeout) never merged it, and a restart
    read only the main root, so those sessions' spend (their pre-charges included) was missing from the main ledger and the problem could pass
    its rung. At start-up and before every fresh lineage, a leftover <root>-fresh is merged exactly as after its run, then archived.
    2026-10-26 (--async-ladder): with froot=None also every per-row root <root>-fresh.s<NN> an async ladder left (archived with its suffix);
    with froot given, only that root (an async ladder's other rows may have theirs in flight)."""
    base = pathlib.PurePath(S.root).name   # <root> = harness/hwork/<base>; its fresh roots are siblings
    if froot is None:
        roots = [S.wt / f"{S.root}-fresh", *sorted((S.wt / S.root).parent.glob(f"{base}-fresh.s*"))]
        return sum(recover_fresh(S, say, p) for p in roots if p.is_dir())
    suffix = froot.name[len(f"{base}-fresh"):]   # "" or ".s<NN>"
    if not froot.is_dir():
        return 0
    main = {}
    for p in (S.wt / S.root).glob("*/state.json"):
        try:
            main[json.loads(p.read_text()).get("problem")] = p
        except (OSError, ValueError):
            pass
    k = 0
    for fs in sorted(froot.glob("*/state.json")):
        try:
            d = json.loads(fs.read_text())
        except (OSError, ValueError):
            continue
        n = d.get("problem"); rid = next((x.get("run_id") for x in reversed(d.get("runs") or []) if x.get("run_id")), None) or "unknown"
        if n in main:
            merge_fresh_state(fs, main[n], rid, None, say, recovered=True); k += 1
    tag = f"recovered-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}{suffix}"
    froot.rename(S.wt / f"{S.root}-fresh.done-{tag}")
    say(f"RECOVERY: a fresh lineage left unmerged by an earlier ladder: {k} state(s) merged into the main ledger (spend kept, best if higher); "
        f"archived as {S.root}-fresh.done-{tag}")
    return k


def _own(S: Set, kind: str) -> list[pathlib.Path]:
    """This arm's runs of one kind (r / f / p) by exact name <prefix>-hx-<arm>-<kind><n> (round-2 review 2026-10-12: the prefix glob also
    matched other arms whose name extends this one, e.g. arm `opus` took opus-rerun-r1, opus-fast-r1 and opus-pass2-r1, and the in-run
    learning then mined another line's proofs into this line's ledgers)."""
    rx = re.compile(re.escape(S.run_prefix[:-1]) + kind + r"\d+")
    return [p for p in S.wt.glob(f"probe/runs/{S.run_prefix[:-1]}{kind}*") if rx.fullmatch(p.name)]


def rounds(S: Set) -> list[pathlib.Path]:
    return sorted(_own(S, "r"), key=lambda p: int(re.search(r"-r(\d+)$", p.name).group(1)))


def fresh_rounds(S: Set) -> list[pathlib.Path]:
    return sorted(_own(S, "f"))


def polish_rounds(S: Set) -> list[pathlib.Path]:
    return sorted(_own(S, "p"))


def review_rounds(S: Set) -> list[pathlib.Path]:
    """--claude-review batches (<prefix>-hx-<arm>-v<round>): no checks, no verified records; their spend is in the curve."""
    return sorted(_own(S, "v"))


def line_runs(S: Set) -> list[pathlib.Path]:
    """This line's runs in check order: by round, then resume (r) / fresh (f) / polish (p) of that round."""
    def key(p: pathlib.Path):
        m = re.search(r"-([rfp])(\d+)$", p.name)
        return (int(m.group(2)), "rfp".index(m.group(1))) if m else (10 ** 9, 0)
    return sorted(rounds(S) + fresh_rounds(S) + polish_rounds(S), key=key)


def inrun_on(a) -> bool:
    """--claude-inrun, by default on exactly when the sessions run prompt v2 (a v1 arm's next prompt would otherwise change: its digest shows
    the ledger)."""
    return a.claude_inrun if getattr(a, "claude_inrun", None) is not None else getattr(a, "claude_prompt", "v1") == "v2"


def _kill_marked(marker: str) -> int:
    """SIGKILL every process whose environment carries marker (the post-pass's compiles run in sessions of their own: scorer/memgate.py)."""
    n, mk = 0, marker.encode()
    for d in os.listdir("/proc") if os.path.isdir("/proc") else []:
        if d.isdigit() and int(d) != os.getpid():
            try:
                with open(f"/proc/{d}/environ", "rb") as f:
                    if mk in f.read().split(b"\0"):
                        os.kill(int(d), signal.SIGKILL); n += 1
            except (OSError, ProcessLookupError):
                pass
    return n


_LINE = [None]   # this line's work root (main): every post-pass carries it as LRA_POSTPASS_LINE, so a restarted ladder can stop a dead one's


def _bounded(cmd: list, cwd, timeout: int, say, tag: str) -> int:
    """Run a post-batch step with a hard timeout (2026-10-11: every wait bounded): own session, killed whole (group + every process
    carrying its marker) on timeout; its last output lines (counts only by design) go to the ladder log. Round-2 review (2026-10-12): a
    SIGTERM / SIGINT / SIGHUP of the ladder while the step runs kills the step first (in its own session it outlived the ladder, and a relaunched
    ladder's pre-charge could then be overwritten by its stale state write), then takes the signal's previous action."""
    mk = f"lra-postpass-{os.getpid()}-{time.time_ns()}"
    env = dict(os.environ, LRA_POSTPASS=mk, **({"LRA_POSTPASS_LINE": _LINE[0]} if _LINE[0] else {}))
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)

    def kill_step() -> int:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return _kill_marked(f"LRA_POSTPASS={mk}")
    prev: dict = {}

    def on_signal(signum, frame):
        kill_step()
        h = prev.get(signum, signal.SIG_DFL)
        for s, ph in prev.items():
            signal.signal(s, ph)
        if callable(h):
            h(signum, frame)
        elif h == signal.SIG_DFL:
            os.kill(os.getpid(), signum)
    if threading.current_thread() is threading.main_thread():
        for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            if signal.getsignal(s) != signal.SIG_IGN:   # an ignored signal (nohup) stays ignored
                prev[s] = signal.signal(s, on_signal)
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        k = kill_step()
        try:
            out = p.communicate(timeout=60)[0] or ""
        except subprocess.TimeoutExpired:
            out = ""
        say(f"  {tag}: timed out after {timeout} s; killed ({k} marked process(es))")
    finally:
        for s, h in prev.items():
            signal.signal(s, h)
    for line in (out or "").strip().splitlines()[-6:]:
        say(f"  {tag}: {line[:400]}")
    return p.returncode if p.returncode is not None else -9


def exemplars_cmd(S: Set, a) -> list:
    """--claude-exemplars (docs/cc_driver_v2.md §13): harness/exemplars.py over this line's work root with its runs that have verified records
    (round order r/f/p), and each --claude-exemplars-extra ROOT RUNSDIR pair grouped by ROOT (RUNSDIR may be a glob, expanded by the builder
    in the same round order)."""
    extras: dict = {}
    for root, rd in getattr(a, "claude_exemplars_extra", None) or []:
        extras.setdefault(root, []).append(rd)
    dirs = [f"probe/runs/{p.name}" for p in line_runs(S) if (p / "verified.jsonl").exists()]
    return ["python3", "harness/exemplars.py", "--work-root", S.root, "--target", f"{getattr(a, 'claude_exemplars_target', 90.0):g}",
            *(["--runs-dir", *dirs] if dirs else []), *[x for root, rds in extras.items() for x in ("--extra-root", root, *rds)]]


def exemplars_check(S: Set, a) -> str | None:
    """--claude-exemplars at launch (review 2026-10-13: a bad extra made every after-batch build exit 2, so a whole ladder ran without
    exemplars): every --claude-exemplars-extra ROOT, resolved against the ladder's worktree as the builder resolves it, is a directory, and no
    ROOT or RUNSDIR belongs to another sealed set or the A/B pool (transfer.set_tag); the reason otherwise."""
    sys.path.insert(0, str(MAIN))
    from harness.transfer import set_tag
    tag = set_tag(S.wt / S.root)
    for root, rd in getattr(a, "claude_exemplars_extra", None) or []:
        if not (S.wt / root).is_dir():
            return f"--claude-exemplars-extra root {root} is not a directory in {S.wt}"
        for x in (root, rd):
            if set_tag(S.wt / x) and set_tag(S.wt / x) != tag:
                return f"--claude-exemplars-extra {x} belongs to {set_tag(S.wt / x)}, not to this line's set"
    return None


def exemplars_start(S: Set, a, say, run=_bounded) -> int:
    """--claude-exemplars before the first round (review 2026-10-13: built only after a batch, the first batch never had a block): the launch
    check, then one build. 2 = refused (nothing built), else 0."""
    err = exemplars_check(S, a)
    if err:
        say(f"refused: {err}"); return 2
    run(exemplars_cmd(S, a), S.wt, 600, say, "exemplars (ladder start)")
    return 0


def cc_after_batch(S: Set, a, r: int, names: list[str], say, run=_bounded) -> list[list]:
    """--driver claude, after every batch (round 2, 2026-10-12): [--claude-polish] hb_polish over the batch's stored bests, banked as run
    <prefix>-hx-<arm>-p<r>; [in-run learning] discover --ledger-only over this line's runs that have verified records (--allow-mixed when a
    polish run is among them: its provenance is hb-polish@cpu), then the run techniques file; [--claude-exemplars, §13] the exemplars of every
    row below the target. Returns the commands run."""
    done = []
    if getattr(a, "claude_polish", False) and names:
        pt = int(getattr(a, "post_timeout", 3600))
        cmd = ["python3", "harness/hb_polish.py", "--work-root", S.root, "--run-id", f"{S.run_prefix[:-1]}p{r}", "--deadline-s", str(max(60, pt - 300)),
               "--problems", *names]
        run(cmd, S.wt, pt, say, "hb_polish"); done.append(cmd)
    if inrun_on(a):
        runs = line_runs(S); led = [p.name for p in runs if (p / "verified.jsonl").exists()]
        if led:
            cmd = ["python3", "harness/discover.py", "--ledger-only", "--runs", ",".join(led), "--work-root", S.root,
                   *(["--allow-mixed"] if any(re.search(r"-p\d+$", x) for x in led) else [])]
            run(cmd, S.wt, 600, say, "discover --ledger-only"); done.append(cmd)
        cmd = ["python3", "harness/inrun.py", "--work-root", S.root, "--runs", ",".join(p.name for p in runs)]
        run(cmd, S.wt, 600, say, "run techniques"); done.append(cmd)
    if getattr(a, "claude_exemplars", False):   # §13: after the ledgers, so the next batch's prompts read exemplars of the bests it resumes
        cmd = exemplars_cmd(S, a)
        run(cmd, S.wt, 600, say, "exemplars"); done.append(cmd)
    return done


def next_plan(S: Set, a, rungs: list[float], rung: float, r: int, wants_fresh) -> tuple[float, list[str]] | None:
    """The round main() runs after round r, as (its rung, the rows it resumes), or None when r is the last round: --max-rounds reached, no rung
    with a row left, or the --stop-at rule ending the ladder at this milestone. --claude-review reviews exactly those rows (a fresh lineage
    starts in an empty workspace and never sees review.md). Not modelled: a rescue between rungs (an adopted rescue changes the best's sha, and
    the review is then not shown) and a rung that turns out full (every session skipped)."""
    if r >= a.max_rounds:
        return None
    st = states(S)
    for rg in rungs:
        if rg < rung - 1e-9 or (getattr(a, "round_per_rung", False) and rg <= rung + 1e-9):
            continue
        todo = focus([n for n in S.names if st.get(n, {"spend": 0.0})["spend"] + SESSION_FLOOR < rg], st, a)
        if not todo:
            continue
        if rg > rung + 1e-9 and a.stop_at is not None and abs(rung - a.stop_rung) < 1e-9 \
                and statistics.mean(st.get(n, {"score": 33.33})["score"] for n in S.names) >= a.stop_at:
            return None
        return rg, [n for n in todo if not (a.lineage_rule and wants_fresh(n, st.get(n, {"score": 33.33})["score"]))]
    return None


def cc_review(S: Set, a, nxt: int, rung: float, names: list[str], say) -> list | None:
    """--claude-review (docs/cc_driver_v2.md §11): before round nxt (rung `rung`), one reviewer session per row it resumes, as ONE Claude batch
    (<= --workers sessions), run <prefix>-hx-<arm>-v<nxt>. The spend is charged to each row's ledger, so it counts toward the rung; a row with less
    than the review budget + SESSION_FLOOR left on that rung is skipped (its executor session keeps its floor). Counts only reach the log."""
    st = states(S)
    ok = [n for n in names if n in st and st[n]["spend"] + a.claude_review_budget + SESSION_FLOOR <= rung + 1e-9]
    if not ok:
        say(f"review before round {nxt}: no row (none of {len(names)} has ${a.claude_review_budget:.2f} + ${SESSION_FLOOR:.2f} left on ${rung:.2f})")
        return None
    run_id = f"{S.run_prefix[:-1]}v{nxt}"
    cmd = review_cmd(a, rung, S.root, run_id, ok, max(1, min(a.workers, len(ok))))
    say(f"review before round {nxt} (rung ${rung:.2f}): {len(ok)} row(s), {len(names) - len(ok)} skipped (less than the review budget "
        f"${a.claude_review_budget:.2f} + floor left)")
    with (S.out / f"{run_id}.log").open("a") as f:
        subprocess.run(cmd, cwd=S.wt, stdout=f, stderr=subprocess.STDOUT)
    if S.prefix.startswith("sealed"):
        cc_spill(S, say)
    st2 = states(S); saved = 0
    try:
        for line in (S.wt / "probe/runs" / run_id / "summary.jsonl").read_text().splitlines():
            saved += bool((json.loads(line).get("review") or {}).get("saved"))
    except (OSError, ValueError):
        pass
    say(f"  review: {saved} of {len(ok)} saved review.md; spend ${sum(st2.get(n, st[n])['spend'] - st[n]['spend'] for n in ok):.2f}")
    return cmd


def _events(f: pathlib.Path):
    op = gzip.open if f.suffix == ".gz" else open
    with op(f, "rt") as h:
        for line in h:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "turn":
                yield e


def _session_cap_table(f: pathlib.Path) -> tuple | None:
    """b64 planner (--first-preset): the cap price table (agent.cap_prices) of a session whose trajectory header names another agent.py preset
    than the line's (a first session), so curve() counts its turns as the gates do; None for the line's own sessions (priced as before) and
    whenever LINE_PRESET is unset (no --first-preset: curve() unchanged)."""
    if not LINE_PRESET:
        return None
    try:
        with (gzip.open if f.suffix == ".gz" else open)(f, "rt", errors="replace") as h:
            head = json.loads(h.readline() or "{}")
    except (OSError, EOFError, ValueError):
        return None
    m = head.get("model") if isinstance(head, dict) and head.get("type") == "header" else None
    if not m or m == LINE_PRESET:
        return None
    from harness.agent import MODEL_PRESETS, cap_prices   # noqa: E402
    return tuple(cap_prices(m)) if m in MODEL_PRESETS else None


def _cap_turn_cost(e: dict, tab: tuple) -> float:
    """One turn event at a cap price table (agent.table_cost's formula), never below its reported cost (agent.py b64 L0's cap meter)."""
    pi, po, pr, pw = tab
    cr, cw = int(e.get("cache_read") or 0), int(e.get("cache_write") or 0)
    t = (max(0, int(e.get("input_tokens") or 0) - cr - cw) * pi + int(e.get("output_tokens") or 0) * po + cr * pr + cw * pw) / 1e6
    return max(t, float(e.get("cost") or 0.0))


def curve(S: Set, marks: list[float]) -> dict:
    """Best score reached by cumulative spend <= mark, per problem (numbers from turn events only). b64 planner: with --first-preset, a first
    session's turns at their preset's cap price (_session_cap_table), as the rungs count them."""
    out = {}
    for n in S.names:
        spent, best, pts = 0.0, 33.33, []
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", n)   # agent.py's trajectory file name for problem n
        # §11: the reviews' spend too. 2026-10-14: in round order (round number, then resume / fresh / review), not by directory mtime,
        # which moves when later files land (the same $1.00 point read 82.15 and later 86.41 on one run)
        def _rk(p):
            m = re.search(r"-([rfv])(\d+)$", p.name)
            return (int(m.group(2)), "rfv".index(m.group(1))) if m else (10 ** 9, 0)
        for rd in sorted(rounds(S) + fresh_rounds(S) + review_rounds(S), key=_rk):
            for f in (rd / "trajectories" / f"{safe}.jsonl.gz", rd / "trajectories" / f"{safe}.jsonl"):
                if f.exists():
                    _tab = _session_cap_table(f)
                    for e in _events(f):
                        if _tab is not None and "input_tokens" in e:   # b64 planner: a first session's turn at its cap price
                            spent += _cap_turn_cost(e, _tab)
                            best = max(best, e.get("best_so_far") or 33.33)
                            pts.append((spent, best))
                            continue
                        # list-price presets (DeepSeek via ClinePass, which reports half of list): price the turn's tokens, as the spend meter does
                        # 2026-10-14: cached input at the cache-read price, as the spend meter (agent.py) prices it; pricing every input
                        # token at the full rate overstated a cache-heavy Sol run 3-5x (curve "$1.00 61.82" against a $1.00 milestone of 82.17)
                        _cr = min(e.get("cache_read") or 0, e.get("input_tokens") or 0)
                        spent += (((e.get("input_tokens") or 0) - _cr) * LIST_PRICES[0] + _cr * (LIST_PRICES[2] if len(LIST_PRICES) > 2 else LIST_PRICES[0])
                                  + (e.get("output_tokens") or 0) * LIST_PRICES[1]) / 1e6 \
                            if LIST_PRICES and "input_tokens" in e else (e.get("cost") or 0.0)
                        best = max(best, e.get("best_so_far") or 33.33)
                        pts.append((spent, best))
        out[n] = {m: max([b for s, b in pts if s <= m] or [33.33]) for m in marks}
    return out


def ref_scores(S: Set) -> dict | None:
    if not S.ref_log:
        return None
    ref = {}
    for line in (MAIN / S.ref_log).read_text().splitlines():
        m = re.search(r"done  (\S+) rc=\d+ best=([0-9.]+)", line)
        if m:
            ref[m.group(1)] = float(m.group(2))
    return {n: ref.get(n, 33.33) for n in S.names}


def report(S: Set, arm: str, rung: float, say, title: str = "REPORT") -> None:
    st, F = states(S), ref_scores(S)
    marks = sorted({0.5, 1.0, 1.5, 2.0, 2.5, rung} | {m for m in (2.85,) if m <= rung})
    C = curve(S, [m for m in marks if m <= rung + 1e-9])
    sc = {n: st.get(n, {"score": 33.33})["score"] for n in S.names}
    sp = [st[n].get("billed", st[n]["spend"]) for n in S.names if n in st]   # billed (api_spend); b64 planner: the cap price below
    spc = [st[n]["spend"] for n in S.names if n in st]
    ref = (f" (Flash cold 1-pass ref {statistics.mean(F.values()):.2f}; wins {sum(sc[n] > F[n] for n in S.names)}/{len(S.names)})" if F else "")
    say(f"{title} {S.prefix} arm {arm}, rung ${rung:.2f}: mean {statistics.mean(sc.values()):.2f} over {len(S.names)}{ref}")
    by = lambda key: {k: [sc[r['name']] for r in S.rows if str(key(r)) == k] for k in sorted({str(key(r)) for r in S.rows})}
    say("  " + "; ".join(f"{k} n={len(v)} {statistics.mean(v):.2f}" for k, v in {**by(lambda r: r.get('stratum')), **by(lambda r: r['source'])}.items() if v))
    if sp:
        say(f"  spend: total ${sum(sp):.2f}, mean ${statistics.mean(sp):.3f}, MAX ${max(sp):.3f} per problem (rung ${rung:.2f}; past $2: {sum(x >= 2.0 for x in sp)})"
            + (f"; at the cap price: total ${sum(spc):.2f}, MAX ${max(spc):.3f}" if any(abs(x - y) > 1e-9 for x, y in zip(sp, spc)) else ""))
    say("  score at budget: " + " · ".join(f"${m:.2f} {statistics.mean(C[n][m] for n in S.names):.2f}" for m in sorted(next(iter(C.values())))))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="heldout2", choices=sorted(SETS)); ap.add_argument("--arm", required=True)
    ap.add_argument("--preset", default="gpt-6.1-sol"); ap.add_argument("--effort", default="medium")
    ap.add_argument("--rungs", default="2.0,2.85", help="budget ladder: every problem is filled to a rung before any goes past it")
    ap.add_argument("--max-rounds", type=int, default=14)
    ap.add_argument("--workers", type=_workers_arg, default=3, help="sessions at once (agent.py --workers of a round's batch; the pool of "
                    "--async-ladder); auto (2026-10-26) = min(rows, $LRA_OR_MAX_CONCURRENCY or 15)")
    ap.add_argument("--async-ladder", action="store_true", help="2026-10-26 (probe/b63/fast_iteration.md): no synchronized rounds; --workers "
                    "workers each start the next session of any row below the rung and not in flight (one agent.py process per session; "
                    "rungs, run ids, lineage, MILESTONE lines and spend accounting as the round ladder). --driver agent only. Off by default")
    ap.add_argument("--ref", default="HEAD"); ap.add_argument("--report", action="store_true")
    ap.add_argument("--agent-pattern-cards", action="store_true", help="2026-10-13: pass --pattern-cards to agent.py (general, pattern-keyed knowledge from harness/pattern_cards.py; the clean replacement for --brief-dir)")
    ap.add_argument("--agent-leads-count", action="store_true", help="b64 F1 (docs/first_half_gap.md §4): every agent.py session runs with "
                    "--leads-count (the library-lead probes on a count budget, independent of the host's speed). Needs a --ref whose agent.py "
                    "has it. Off by default")
    ap.add_argument("--agent-compact-tool-json", action="store_true", help="b65: pass --compact-tool-json to every agent.py session (compact tool-result JSON)")
    ap.add_argument("--agent-notes-view", choices=["head", "tail", "headtail"], default=None, help="b64 F2: pass --notes-view VIEW to every "
                    "agent.py session (which part of a long notes.md the opening shows). Needs a --ref whose agent.py has it. Off by default")
    ap.add_argument("--agent-heartbeat-first", action="store_true", help="2026-10-15 (next-steps step 3): pass --heartbeat-first to every "
                    "agent.py session (the heartbeat-first card)")
    ap.add_argument("--agent-brief", default=None, choices=["automation", "direct", "restructure"], help="2026-10-14 (depth probe): pass "
                    "--brief NAME to every agent.py session (the scout strategy brief appended to the opening)")
    ap.add_argument("--agent-auto-brief", action="store_true", help="2026-10-14 (docs/auto_brief_plan.md): before round 1, harness/autobrief.py "
                    "measures every row's seed (CPU only; in the line's container when --agent-docker) into <work root>/_autobrief, and every "
                    "session gets --auto-brief")
    ap.add_argument("--auto-brief-budget", type=int, default=80, help="--agent-auto-brief: single-edit compiles per row")
    ap.add_argument("--auto-brief-timeout", type=int, default=14400, help="--agent-auto-brief: seconds for all rows (then rows go on without)")
    ap.add_argument("--auto-brief-row-workers", type=int, default=2, help="--agent-auto-brief: autobrief.py --row-workers, rows measured at "
                    "once (2026-10-22, docs/speed_review.md item 6; default 2 as before)")
    ap.add_argument("--auto-brief-compile-workers", type=int, default=3, help="--agent-auto-brief: autobrief.py --workers, the sweep's "
                    "compiles per row at once (2026-10-26, b64-brief; default 3, the value it replaces)")
    ap.add_argument("--auto-brief-docker-memory", default=None, help="--agent-auto-brief with --agent-docker: the brief container's --memory "
                    "(2026-10-26, b64-brief; default: --agent-docker-memory). Its compiles are admitted by the memory gate against this cap "
                    "and the host's MemAvailable")
    ap.add_argument("--auto-brief-longest-first", action="store_true", help="--agent-auto-brief: autobrief.py --longest-first (the longest "
                    "seeds start first, so the slowest rows do not form the tail; 2026-10-22, item 6)")
    ap.add_argument("--auto-brief-pipeline", action="store_true", help="--agent-auto-brief (2026-10-22, docs/speed_review.md item 7): run the "
                    "brief in the BACKGROUND and start round 1 at once; each row's first session starts when its own brief exists, or when "
                    "the brief process has ended (finished, timed out or stopped); later rounds start after the brief, as before. Needs a "
                    "--ref whose agent.py has --auto-brief-wait")
    ap.add_argument("--agent-mask-strays", action="store_true", help="2026-10-13: cover untracked files of the envs mount (envs/notes.md, "
                    "probes and scratch inside env checkouts) with empty ones in the agent container (needed on a '-clean' set)")
    ap.add_argument("--brief-dir", default=None, help="facts-only knowledge briefs (knowledge, never proofs), passed to every session")
    ap.add_argument("--agent-artifact", default=None, metavar="DIR", help="b63 item 16 (ARTIFACT-SESSION, docs/adaptive_plan_93.md §1.4): DIR "
                    "holds <ws>.artifact.json records (harness/artifacts.write_record); the set's rows' records are copied into the line's work "
                    "root (<root>/_artifacts, visible in the container) and every session runs agent.py --artifact on it (a row without a record "
                    "runs a plain session). Off by default")
    ap.add_argument("--stop-at", type=float, default=None, help="stop after the --stop-rung milestone if its mean is >= this")
    ap.add_argument("--stop-rung", type=float, default=2.0)
    ap.add_argument("--rescue", type=int, default=0, help="after the --rescue-rung milestone, one FRESH restructure session (empty work root: "
                    "no stored best, notes or variants; knowledge and tools only) for the K problems furthest below their target")
    ap.add_argument("--rescue-rung", type=float, default=2.0); ap.add_argument("--rescue-effort", default="high")
    ap.add_argument("--lineage-rule", action=argparse.BooleanOptionalAction, default=True, help="restart stuck or badly-drawn problems fresh")
    ap.add_argument("--max-fresh", type=int, default=2)
    ap.add_argument("--driver", choices=["agent", "codex", "claude"], default="agent", help="agent: harness/agent.py with --preset; codex: "
                    "harness/agent_codex.py; claude: harness/agent_claude_code.py (driver v2 gate; --claude-* options)")
    ap.add_argument("--claude-prompt", choices=["v1", "v2"], default="v1", help="--driver claude: agent_claude_code.py --prompt")
    ap.add_argument("--claude-effort", choices=["low", "medium", "high", "xhigh", "max"], default="xhigh",
                    help="--driver claude: claude --effort of every session (a rescue uses --rescue-effort)")
    ap.add_argument("--claude-cache", choices=["1h", "5m"], default="1h", help="--driver claude: prompt-cache TTL (5m: FORCE_PROMPT_CACHING_5M=1)")
    ap.add_argument("--claude-model", default="claude-opus-5-5")
    ap.add_argument("--claude-gate-cap", type=float, default=None, help="--driver claude: agent_claude_code.py --gate-cap (default $2.85; "
                    "raise only for feasibility runs that are not closed-track compliant)")
    ap.add_argument("--claude-sealed", action="store_true", help="--driver claude on a sealed set: agent_claude_code.py --sealed (required there)")
    ap.add_argument("--codex-model", default="gpt-6.1-sol"); ap.add_argument("--codex-docker", default="lra-codex:1")
    ap.add_argument("--codex-docker-memory", default="24g", help="per-container cap (containers sit outside systemd unit caps)")
    ap.add_argument("--max-usd-per-min", type=float, default=None, help="codex time gate rate (default: agent_codex.py's calibrated value)")
    ap.add_argument("--problems", nargs="*", default=None, help="run only these rows of the set")
    ap.add_argument("--agent-docker", default=None, help="run each agent.py batch in this image (lra-agent:1, infra/agent/Dockerfile); required on sealed sets")
    ap.add_argument("--agent-docker-memory", default="48g"); ap.add_argument("--agent-private-scratch", default=None,
                                                                             help="this line's own compile scratch root (required with --agent-docker)")
    ap.add_argument("--codex-sealed", action="store_true", help="agent_codex.py --sealed with --private-scratch (sealed sets)")
    ap.add_argument("--codex-private-scratch", default=None, help="this line's own compile scratch root (required with --codex-sealed)")
    # round 2 (2026-10-12, docs/cc_driver_v2.md §9): post-batch steps of --driver claude, all bounded, counts-only output
    ap.add_argument("--claude-inrun", action=argparse.BooleanOptionalAction, default=None, help="--driver claude: after every batch, discover.py "
                    "--ledger-only over this line's runs and the run techniques file (harness/inrun.py); default on with --claude-prompt v2")
    ap.add_argument("--claude-polish", action="store_true", help="--driver claude: harness/hb_polish.py over the batch's stored bests after every "
                    "batch ($0 CPU; strictly better with Z unchanged; banked as run <prefix>-hx-<arm>-p<round>)")
    ap.add_argument("--post-timeout", type=int, default=3600, help="seconds the --claude-polish step may take per batch")
    # reviewer, A4 and ceiling (2026-10-12, docs/cc_driver_v2.md §11)
    ap.add_argument("--claude-review", action="store_true", help="--driver claude --claude-prompt v2: after every batch but the last round, the "
                    "reviewer (agent_claude_code.py --review: Read only, no proof file, its own gate charged to the row's ledger) for the rows the "
                    "next round resumes, one Claude batch; a row with less than --claude-review-budget + SESSION_FLOOR left is not reviewed")
    ap.add_argument("--claude-review-budget", type=float, default=0.30, help="--claude-review: the reviewer's gate per row (USD list)")
    ap.add_argument("--claude-review-effort", choices=["low", "medium", "high", "xhigh", "max"], default="high")
    ap.add_argument("--claude-ceiling", action="store_true", help="--driver claude: agent_claude_code.py --ceiling (the per-problem cap is the rung, "
                    "not $2.85): a ceiling measurement, never a submission")
    ap.add_argument("--claude-fresh-facts", action="store_true", help="--driver claude --claude-prompt v2: each fresh lineage (lineage rule or "
                    "rescue) gets the main lineage's facts sheet as lineage_facts.md (numbers, failed checks, notes' Failed / Next; no proof)")
    ap.add_argument("--session-floor", type=float, default=None, help="no session starts with less than this left on the rung (default "
                    "$0.30, or the reclaim floor with --agent-budget-reclaim; 2026-10-13: a Fable session's first call alone is ~$1.5, so a "
                    "Fable line needs ~$3)")
    ap.add_argument("--agent-budget-reclaim", action="store_true", help="2026-10-22 (lever 5): every agent.py session runs with "
                    "--budget-reclaim (the last turns' output cap shrinks to what the rung can still pay for in the worst case instead of "
                    "ending the session), and the session floor drops to the first turn's worst case at the reclaim floor when that fits "
                    "(reclaim_session_floor: $0.20 for Sol); --session-floor still overrides. Needs a --ref whose agent.py has --budget-reclaim. "
                    "Off by default")
    ap.add_argument("--agent-name-neighbors", action="store_true", help="2026-10-23 (L1, harness/name_neighbors.py): every agent.py session "
                    "runs with --name-neighbors (an unknown-identifier error gets up to 8 real constants near the name, listed by Lean from the "
                    "row's own environment; the opening lists the names earlier sessions found missing). Needs a --ref whose agent.py has "
                    "--name-neighbors. Off by default (not adopted: held-out A/B first)")
    ap.add_argument("--agent-skeleton-fix", action="store_true", help="2026-10-26 (b64 L1, docs/plateau_levers.md L1): every agent.py session "
                    "runs with --skeleton-path-first --skeleton-salvage --skeleton-combinator-holes --junk-billing-reconcile (lean_skeleton "
                    "schema with path first; a junk lean_skeleton call is run on its salvaged draft; `all_goals sorry`-style holes read as tactic "
                    "holes; a worst-case junk-cut charge is replaced by OpenRouter's billed record once it arrives). Needs a --ref whose agent.py "
                    "has those flags. Off by default")
    ap.add_argument("--agent-c0", nargs="?", const="probe/b63/c0_config.json", default=None, metavar="CONFIG",
                    help="2026-10-25 (b63 launch set item 6, docs/adaptive_plan_93.md §1.1 C0): after the auto-brief and before round 1, "
                    "harness/cpu_pass.py runs the frozen end stage CONFIG (default probe/b63/c0_config.json: the r5 families on a C0 budget) on every "
                    "row's seed in the line's container; its verified output B0 goes to the row's bank.jsonl and cpu_pass.json and, as the SHOWN "
                    "block (compiled diff + numbers + family labels), into the row's auto-brief, from which the first session starts (agent.py "
                    "--auto-brief). Needs --agent-auto-brief (not pipelined) and a --ref whose harness has cpu_pass.py. Off by default")
    ap.add_argument("--c0-timeout", type=int, default=5400, help="--agent-c0: seconds for all rows (then rows without a C0 record go on without one)")
    ap.add_argument("--agent-pool", action="store_true", help="2026-10-25 (b63 launch set item 1, docs/adaptive_plan_93.md §4.1): every agent.py "
                    "session runs with --pool: each compiling candidate goes to <work root>/<row>/pool.jsonl and to the row's bank.jsonl "
                    "(harness/bank.py; the end stage, the crossover and the SHOWN block read the bank). Needs a --ref whose agent.py has --pool. "
                    "Off by default (the v2 ladder ran without it; the v3 arm passes it)")
    # exemplar transfer from the strongest rows (2026-10-13; docs/cc_driver_v2.md §13)
    ap.add_argument("--claude-exemplars", action="store_true", help="--driver claude --claude-prompt v2: at ladder start and after every batch "
                    "harness/exemplars.py writes <work root>/_exemplars/<ws>.md for every row below --claude-exemplars-target (the strongest "
                    "rows' style, retrieved transformations of other problems; never proofs), and every session gets --exemplars")
    ap.add_argument("--claude-exemplars-extra", nargs=2, action="append", default=None, metavar=("ROOT", "RUNSDIR"), help="--claude-exemplars: "
                    "another line on the same set, its work root and one of its run dirs (a glob allowed: hx run ids in round order), both "
                    "relative to the ladder's worktree or absolute (checked at launch); repeat for more run dirs or lines")
    ap.add_argument("--claude-exemplars-target", type=float, default=90.0, help="--claude-exemplars: the strongest rows are those at or above this "
                    "score; rows at or above it get no exemplars")
    ap.add_argument("--skip-above", type=float, default=None, help="leave rows whose stored best is >= this out of every round (2026-10-13)")
    ap.add_argument("--low-first", action="store_true", help="order each round's rows from the lowest stored best up")
    ap.add_argument("--round-per-rung", action="store_true", help="one round per rung: every round climbs to the next rung (a row that stopped "
                    "under a rung is not refilled at it), so every row with room gets exactly one session per rung (Phase A arm A4)")
    # b64 planner (T2, docs/first_half_gap.md section 6.2): the first-session preset; off by default
    ap.add_argument("--first-preset", default=None, metavar="PRESET", help="b64 planner (--driver agent): a row's FIRST ladder session (session "
                    "index 1 on the row: nothing spent on it yet; also under --async-ladder and on a resume, never a second time) runs agent.py "
                    "--model-preset PRESET with --budget-usd min(--first-budget, the rung), gated at PRESET's cap price (Gemini 4 Argon: its "
                    "announced $4 / $20); every later session is --preset; the rungs count the first session at the cap price, the reports also "
                    "give the billed spend. Needs --first-budget and a --ref whose agent.py has cap prices (b64 L0). Off by default")
    ap.add_argument("--first-effort", default=None, help="--first-preset: the first session's --reasoning-effort (default: --effort)")
    ap.add_argument("--first-budget", type=float, default=None, metavar="USD", help="--first-preset: the first session's budget at the cap "
                    "price (its --budget-usd is min(USD, the rung))")
    # b65 steps (T3-T5, probe/b65/steps_tests.md): a session preset per budget step; off by default
    ap.add_argument("--preset-by-rung", default=None, metavar="R:P[@E],...", help="b65 steps (--driver agent): a session working toward "
                    "ladder rung R (the lowest rung above the row's spend) runs agent.py --model-preset P [--reasoning-effort E], gated at "
                    "P's cap price; a rung not listed runs --preset / --effort (a first session keeps --first-preset), e.g. "
                    "1.25:gpt-6.1-terra-main or 1.90:opus-5.5@medium. A listed rung at or below the last --rungs must be one of them (a higher "
                    "one belongs to a later phase, e.g. a router's next checkpoint). Frozen in <out>/presets.json (a resume that changes it "
                    "is refused). Off by default")
    # b66 (retro A3, docs/b66_robust.md): the router's preset fallback after a CONFIRMED max_price pin; off by default
    ap.add_argument("--preset-fallback", default=None, metavar="X:Y,...", help="b66 (--driver agent; the router passes it after a CONFIRMED "
                    "max_price pin of preset X): every session that would run X (--preset, a --preset-by-rung rung, --first-preset) runs Y, "
                    "gated at Y's cap price (agent.py) with Y's session floor; not frozen (not part of presets.json: a runtime substitution the "
                    "router records in its run dir). Y must be an agent.py session preset on X's OpenRouter key")
    # b68 (docs/b68_tail.md): the router's tail stage; off by default (no --tail: every path as before)
    ap.add_argument("--tail", default=None, metavar="FILE", help="b68 (--driver agent; the router writes FILE): TAIL mode instead of the "
                    "ladder: FILE = {\"tops\": {row: USD}}; each listed row runs agent.py sessions of --tail-preset in its own work root (its "
                    "stored best, notes, pool and bank), one in flight per row, --workers at once, each with --budget-usd = the row's top (its "
                    "spend at the cap price plus the room the router left it under the cap), while spend + the preset's session floor stays "
                    "below that top, at most --tail-max-sessions per row; run ids <prefix>-hx-<arm>-t<k>; every session in <out>/tail_sessions.jsonl. "
                    "No lineage rule, rescue, first session, brief or MILESTONE; a CONFIRMED pin exits as the ladder does (--preset-fallback applies)")
    ap.add_argument("--tail-preset", default=None, help="--tail: the sessions' agent.py preset (an OpenRouter session preset, or a "
                    "list-priced Azure one for a dev run)")
    ap.add_argument("--tail-effort", default=None, help="--tail: the sessions' --reasoning-effort (default: --effort)")
    ap.add_argument("--tail-max-sessions", type=int, default=3, help="--tail: sessions per row at most, over every invocation (default 3)")
    return ap


OR_MAX_CONCURRENCY = 15   # --workers auto: the OpenRouter concurrency limit per ladder unless $LRA_OR_MAX_CONCURRENCY says otherwise


def _workers_arg(v: str):
    """--workers: a positive integer, or auto (resolved in main() once the rows are known: workers_auto)."""
    if str(v).strip().lower() == "auto":
        return "auto"
    try:
        n = int(v)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--workers: a positive integer or auto, not {v!r}")
    if n < 1:
        raise argparse.ArgumentTypeError("--workers: 1 or more, or auto")
    return n


def workers_auto(rows: int, env=None) -> int:
    """--workers auto: one worker per row up to the OpenRouter concurrency limit ($LRA_OR_MAX_CONCURRENCY, default OR_MAX_CONCURRENCY)."""
    env = os.environ if env is None else env
    try:
        cap = int(env.get("LRA_OR_MAX_CONCURRENCY") or OR_MAX_CONCURRENCY)
    except ValueError:
        cap = OR_MAX_CONCURRENCY
    return max(1, min(int(rows), max(1, cap)))


def check_args(ap: argparse.ArgumentParser, a) -> None:
    """The option checks of main() (ap.error, exit 2, on a refused combination); harness/selftest_cc.py runs them on the runners' argv."""
    if getattr(a, "async_ladder", False) and a.driver != "agent":
        ap.error("--async-ladder is a --driver agent option (one agent.py process per session; the codex / claude drivers run one batch at a time)")
    if a.codex_sealed and not a.codex_private_scratch:
        ap.error("--codex-sealed needs --codex-private-scratch")
    if a.driver == "codex" and SETS[a.set][2].startswith("sealed") and not a.codex_sealed:
        ap.error("a sealed set with the Codex driver needs --codex-sealed (its container must not see other runs' compile scratch)")
    if a.driver == "codex" and SETS[a.set][2].startswith("sealed") and not a.set.endswith("-cx"):
        ap.error("the Codex driver on a sealed set needs its own worktree set (e.g. heldout3-cx): its container mounts the worktree")
    if a.set.endswith("-clean") and not (a.driver == "agent" and a.agent_docker and a.agent_private_scratch and a.agent_mask_strays):
        ap.error("a '-clean' set runs agent.py only, with --agent-docker, --agent-private-scratch and --agent-mask-strays (its shell tool must "
                 "see nothing but the whitelist worktree and the envs)")
    if a.set.endswith("-clean") and ((a.brief_dir and a.set not in NONROW_SETS) or a.stop_at is not None):
        ap.error("a '-clean' set takes no --brief-dir (theorem-keyed; allowed only on a non-row set: " + ", ".join(NONROW_SETS) + ") and no "
                 "--stop-at (its target is an earlier score of these rows)")
    if getattr(a, "agent_artifact", None) and a.driver != "agent":
        ap.error("--agent-artifact is a --driver agent option (agent.py --artifact)")
    if a.driver == "agent" and SETS[a.set][2].startswith("sealed") and not (a.agent_docker and a.agent_private_scratch):
        ap.error("an agent.py line on a sealed set needs --agent-docker and --agent-private-scratch (its shell tool must not see other lines' files)")
    if a.driver == "claude" and SETS[a.set][2].startswith("sealed") and not a.claude_sealed:
        ap.error("the Claude Code driver on a sealed set needs --claude-sealed (agent_claude_code.py --sealed: no transcripts, MCP, user settings or memory)")
    if a.driver == "claude" and SETS[a.set][2].startswith("sealed") and not a.set.endswith("-cc"):
        ap.error("the Claude Code driver on a sealed set needs its own worktree set (e.g. heldout3-cc): it runs on the host, and the shared "
                 "worktree holds other lines' work roots with best proofs of the same rows")
    if a.claude_sealed and [k for k in os.environ if k.startswith(("ANTHROPIC_", "AWS_BEARER_TOKEN_BEDROCK")) or k in ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")]:
        ap.error("API/provider env present: --claude-sealed runs on the subscription only (as probe/heldout/run_sealed3_opus.sh)")
    if a.claude_sealed and a.driver != "claude":
        ap.error("--claude-sealed is a --driver claude option")
    if a.driver == "claude" and a.brief_dir and a.claude_sealed:
        ap.error("--brief-dir with --claude-sealed: agent_claude_code.py --sealed refuses briefs")
    if a.driver != "claude" and (a.claude_polish or a.claude_inrun or a.claude_ceiling):
        ap.error("--claude-polish, --claude-inrun and --claude-ceiling are --driver claude options")
    if (a.claude_review or a.claude_fresh_facts) and (a.driver != "claude" or a.claude_prompt != "v2"):
        ap.error("--claude-review and --claude-fresh-facts need --driver claude --claude-prompt v2")
    if a.claude_review_budget <= 0:
        ap.error("--claude-review-budget must be positive")
    if (a.claude_exemplars or a.claude_exemplars_extra) and (a.driver != "claude" or a.claude_prompt != "v2"):
        ap.error("--claude-exemplars and --claude-exemplars-extra need --driver claude --claude-prompt v2")
    if a.claude_exemplars_extra and not a.claude_exemplars:
        ap.error("--claude-exemplars-extra needs --claude-exemplars")
    if (a.auto_brief_pipeline or a.auto_brief_longest_first or a.auto_brief_row_workers != 2) and not (a.agent_auto_brief and a.driver == "agent"):
        ap.error("--auto-brief-pipeline, --auto-brief-longest-first and --auto-brief-row-workers are --agent-auto-brief options (--driver agent)")
    if a.auto_brief_row_workers < 1:
        ap.error("--auto-brief-row-workers must be at least 1")
    if (a.auto_brief_compile_workers != 3 or a.auto_brief_docker_memory) and not (a.agent_auto_brief and a.driver == "agent"):
        ap.error("--auto-brief-compile-workers and --auto-brief-docker-memory are --agent-auto-brief options (--driver agent)")
    if a.auto_brief_compile_workers < 1:
        ap.error("--auto-brief-compile-workers must be at least 1")
    if a.auto_brief_docker_memory and not a.agent_docker:
        ap.error("--auto-brief-docker-memory needs --agent-docker (it is the brief container's --memory)")
    if getattr(a, "agent_budget_reclaim", False) and a.driver != "agent":
        ap.error("--agent-budget-reclaim is a --driver agent option (agent.py --budget-reclaim)")
    if getattr(a, "agent_name_neighbors", False) and a.driver != "agent":
        ap.error("--agent-name-neighbors is a --driver agent option (agent.py --name-neighbors)")
    if getattr(a, "agent_pool", False) and a.driver != "agent":
        ap.error("--agent-pool is a --driver agent option (agent.py --pool)")
    if getattr(a, "agent_skeleton_fix", False) and a.driver != "agent":
        ap.error("--agent-skeleton-fix is a --driver agent option (agent.py " + " ".join(SKELETON_FIX_FLAGS) + ")")
    if getattr(a, "agent_c0", None) and not (a.driver == "agent" and a.agent_auto_brief and not a.auto_brief_pipeline):
        ap.error("--agent-c0 needs --driver agent --agent-auto-brief without --auto-brief-pipeline (the C0 pass extends the brief before round 1)")
    # b64 planner: --first-preset / --first-effort / --first-budget
    if (getattr(a, "first_preset", None) or getattr(a, "first_effort", None) or getattr(a, "first_budget", None) is not None) and not (
            a.driver == "agent" and getattr(a, "first_preset", None) and getattr(a, "first_budget", None) is not None):
        ap.error("--first-preset, --first-effort and --first-budget go together: --driver agent with --first-preset and --first-budget")
    if getattr(a, "first_budget", None) is not None and not a.first_budget > 0:
        ap.error("--first-budget must be positive")
    # b65 steps: --preset-by-rung
    a.rung_map = {}
    if getattr(a, "preset_by_rung", None) is not None:
        if a.driver != "agent":
            ap.error("--preset-by-rung is a --driver agent option")
        try:
            a.rung_map = rung_presets(a.preset_by_rung)
            rr = [float(x) for x in a.rungs.split(",") if x.strip()]
        except ValueError as e:
            ap.error(f"--preset-by-rung: {e}")
        if not a.rung_map:
            ap.error("--preset-by-rung: no entry")
        bad = [R for R in a.rung_map if R <= max(rr) + 1e-9 and not any(abs(R - x) < 1e-6 for x in rr)]
        if bad:
            ap.error(f"--preset-by-rung: {', '.join(f'{R:.2f}' for R in bad)} not one of --rungs {a.rungs} (a listed rung up to the last "
                     "rung must be a rung)")
    # b66 (A3): --preset-fallback (the router's, after a CONFIRMED pin)
    a.fallback = {}
    if getattr(a, "preset_fallback", None):
        if a.driver != "agent":
            ap.error("--preset-fallback is a --driver agent option")
        try:
            a.fallback = fallback_map(a.preset_fallback)
        except ValueError as e:
            ap.error(f"--preset-fallback: {e}")
    # b68: --tail (the router's tail stage)
    if getattr(a, "tail", None):
        if a.driver != "agent" or not getattr(a, "tail_preset", None):
            ap.error("--tail is a --driver agent option and needs --tail-preset")
        if a.tail_max_sessions < 1:
            ap.error("--tail-max-sessions must be at least 1")
    elif getattr(a, "tail_preset", None) or getattr(a, "tail_effort", None):
        ap.error("--tail-preset and --tail-effort are --tail options")


def main() -> int:
    global SESSION_FLOOR
    ap = build_parser()
    a = ap.parse_args()
    if getattr(a, "session_floor", None) is not None:
        SESSION_FLOOR = a.session_floor
    check_args(ap, a)
    PIN_GONE.clear(); PIN_GONE.update(getattr(a, "fallback", None) or {})   # b66 (A3): this invocation's (an in-process caller runs main again)
    if a.driver == "claude":
        a.effort = a.claude_effort   # every session (rounds and fresh lineages) runs at the Claude effort; a rescue keeps --rescue-effort
    if a.codex_private_scratch:
        a.codex_private_scratch = str(pathlib.Path(a.codex_private_scratch).resolve())
    global LIST_PRICES
    if a.driver == "agent":
        sys.path.insert(0, str(MAIN))
        from harness.agent import MODEL_PRESETS   # noqa: E402
        p = MODEL_PRESETS.get(a.preset) or {}
        LIST_PRICES = p.get("prices") if p.get("list_price") else None
    S = Set(a.set, a.arm); S.out.mkdir(parents=True, exist_ok=True); a.wt = S.wt
    if a.problems:
        keep = set(a.problems); S.rows = [r for r in S.rows if r["name"] in keep]; S.names = [r["name"] for r in S.rows]
        assert S.names, "no row of the set matches --problems"
    workers_given = a.workers
    if a.workers == "auto":   # 2026-10-26: one worker per row, up to the OpenRouter concurrency limit
        a.workers = workers_auto(len(S.names))
    rungs = [float(x) for x in a.rungs.split(",") if x.strip()]
    # a "-clean" set's worktree is sparse and its container sees only the worktree: a (non-row) brief dir is staged into the work root
    extra = (["--brief-dir", f"{S.root}/_brief" if S.clean else a.brief_dir]) if a.brief_dir else []
    if getattr(a, "agent_artifact", None) and a.driver == "agent":   # b63 item 16: ARTIFACT-SESSION records, staged into the work root
        extra = extra + ["--artifact", f"{S.root}/_artifacts"]
    if getattr(a, "agent_pattern_cards", False) and a.driver == "agent":   # 2026-10-13: general pattern cards (harness/pattern_cards.py)
        extra = extra + ["--pattern-cards"]
    if getattr(a, "agent_leads_count", False) and a.driver == "agent":   # b64 F1: count-budget library leads in every session
        extra = extra + ["--leads-count"]
    if getattr(a, "agent_compact_tool_json", False) and a.driver == "agent":   # b65: compact tool-result JSON in every session
        extra = extra + ["--compact-tool-json"]
    if getattr(a, "agent_notes_view", None) and a.driver == "agent":   # b64 F2: the notes view of every session
        extra = extra + ["--notes-view", a.agent_notes_view]
    if getattr(a, "agent_brief", None) and a.driver == "agent":   # 2026-10-14 depth probe: a scout brief for every session
        extra = extra + ["--brief", a.agent_brief]
    if getattr(a, "agent_heartbeat_first", False) and a.driver == "agent":   # 2026-10-15 step 3: agent.py --heartbeat-first (A/B)
        extra = extra + ["--heartbeat-first"]
    if getattr(a, "agent_auto_brief", False) and a.driver == "agent":   # 2026-10-14: seed-measured auto-brief (harness/autobrief.py)
        extra = extra + ["--auto-brief", f"{S.root}/_autobrief"]
    if getattr(a, "agent_budget_reclaim", False) and a.driver == "agent":   # 2026-10-22 lever 5: every session (rounds, fresh lineages, rescue)
        extra = extra + ["--budget-reclaim"]
        if a.session_floor is None:   # an adaptive-cap preset (Kimi) already sizes every turn; its smallest turn is its adaptive_min
            from harness.agent import RECLAIM_FLOOR, cap_prices
            _pp = MODEL_PRESETS[a.preset]
            # b65 steps: a --preset-by-rung rung's floor is its own preset's (rung_floor; the formula below)
            a.rung_floor = {R: reclaim_session_floor(cap_prices(MODEL_PRESETS[P]), int(MODEL_PRESETS[P].get("adaptive_min", 6000))
                                                     if MODEL_PRESETS[P].get("adaptive_cap") else RECLAIM_FLOOR, SESSION_FLOOR)
                            for R, (P, _e) in (getattr(a, "rung_map", None) or {}).items() if P in MODEL_PRESETS}
            # b66 (A3): a --preset-fallback target's own floor (floor_at), the same formula and base as rung_floor
            a.fallback_floor = {Y: reclaim_session_floor(cap_prices(MODEL_PRESETS[Y]), int(MODEL_PRESETS[Y].get("adaptive_min", 6000))
                                                         if MODEL_PRESETS[Y].get("adaptive_cap") else RECLAIM_FLOOR, SESSION_FLOOR)
                                for Y in (getattr(a, "fallback", None) or {}).values() if Y in MODEL_PRESETS}
            if getattr(a, "tail", None) and a.tail_preset in MODEL_PRESETS:   # b68: the tail preset's own floor, the same formula and base
                _tp = MODEL_PRESETS[a.tail_preset]
                a.tail_floor = reclaim_session_floor(cap_prices(_tp), int(_tp.get("adaptive_min", 6000)) if _tp.get("adaptive_cap")
                                                     else RECLAIM_FLOOR, SESSION_FLOOR)
            # b64 L0: the session's gate prices its turns at the preset's cap prices (agent.cap_prices; = its table for every Sol preset)
            SESSION_FLOOR = reclaim_session_floor(cap_prices(_pp), int(_pp.get("adaptive_min", 6000)) if _pp.get("adaptive_cap") else RECLAIM_FLOOR,
                                                  SESSION_FLOOR)
    if getattr(a, "agent_name_neighbors", False) and a.driver == "agent":   # 2026-10-23 L1: every session (rounds, fresh lineages, rescue)
        extra = extra + ["--name-neighbors"]
    if getattr(a, "agent_pool", False) and a.driver == "agent":   # 2026-10-25 b63 item 1: every session banks its compiling candidates
        extra = extra + ["--pool"]
    if getattr(a, "agent_skeleton_fix", False) and a.driver == "agent":   # 2026-10-26 b64 L1: every session (rounds, fresh lineages, rescue)
        extra = extra + SKELETON_FIX_FLAGS
    def say(msg: str) -> None:
        line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime())}] {msg}"
        print(line, flush=True); (S.out / "jobs.log").open("a").write(line + "\n")
    if a.report:
        report(S, a.arm, rungs[-1], say); return 0
    setup_worktree(S, subprocess.run(["git", "rev-parse", a.ref], cwd=MAIN, capture_output=True, text=True).stdout.strip(), say)
    _miss = missing_envs(S)
    if _miss:   # 2026-10-25 (LeanPool; v3 launch incident class): before any spend, not after a round of failed compiles
        say(f"refused: no built environment in the worktree for {', '.join(_miss)} (envs/ of {S.wt} -> {_env_src() / 'envs'}); "
            f"build it (envs/build_*.sh) or link it, then relaunch"); return 2
    if a.driver == "claude":   # round-2 review (2026-10-12): a post-pass left running by a ladder that died (SIGKILL, OOM) is stopped first
        _LINE[0] = str(S.wt / S.root)
        k = _kill_marked(f"LRA_POSTPASS_LINE={_LINE[0]}")
        if k:
            say(f"stopped {k} process(es) of a post-batch step left running by an earlier ladder of this line")
    recover_fresh(S, say)   # round-2 review: a fresh lineage an earlier ladder left unmerged (its spend) goes into the main ledger first
    if getattr(a, "agent_budget_reclaim", False) and a.driver == "agent":
        try:
            known = '"--budget-reclaim"' in (S.wt / "harness/agent.py").read_text()
        except OSError:
            known = False
        if not known:   # before any spend: every session at this --ref would refuse the flag (argparse) and the round record no spend
            say(f"refused: --agent-budget-reclaim: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) has no --budget-reclaim"); return 2
        say(f"budget reclaim: agent.py --budget-reclaim in every session; session floor ${SESSION_FLOOR:.2f}")
    if getattr(a, "agent_name_neighbors", False) and a.driver == "agent":
        try:
            known = '"--name-neighbors"' in (S.wt / "harness/agent.py").read_text()
        except OSError:
            known = False
        if not known:   # before any spend: every session at this --ref would refuse the flag (argparse)
            say(f"refused: --agent-name-neighbors: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) has no --name-neighbors"); return 2
        say("name neighbours: agent.py --name-neighbors in every session")
    if getattr(a, "agent_skeleton_fix", False) and a.driver == "agent":
        try:
            _src = (S.wt / "harness/agent.py").read_text()
            known = all(f'"{f_}"' in _src for f_ in SKELETON_FIX_FLAGS)
        except OSError:
            known = False
        if not known:   # before any spend: every session at this --ref would refuse the flags (argparse)
            say(f"refused: --agent-skeleton-fix: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) lacks {' / '.join(SKELETON_FIX_FLAGS)}"); return 2
        say("skeleton fix: agent.py " + " ".join(SKELETON_FIX_FLAGS) + " in every session")
    if getattr(a, "agent_pool", False) and a.driver == "agent":
        try:
            known = '"--pool"' in (S.wt / "harness/agent.py").read_text()
        except OSError:
            known = False
        if not known:   # before any spend: every session at this --ref would refuse the flag (argparse)
            say(f"refused: --agent-pool: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) has no --pool"); return 2
        say("bank: agent.py --pool in every session (pool.jsonl + bank.jsonl per row)")
    if getattr(a, "agent_artifact", None) and a.driver == "agent":
        try:
            known = '"--artifact"' in (S.wt / "harness/agent.py").read_text()
        except OSError:
            known = False
        if not known:   # before any spend: every session at this --ref would refuse the flag (argparse)
            say(f"refused: --agent-artifact: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) has no --artifact"); return 2
    if getattr(a, "tail", None):   # b68 (docs/b68_tail.md): the router's tail stage instead of the ladder; checked before any spend
        err = tail_check(S, a) or (fallback_check(S, a) if getattr(a, "fallback", None) else None)
        if err:
            say(f"refused: {err}"); return 2
        if getattr(a, "fallback", None):
            say("preset fallback: " + "; ".join(f"sessions configured for {X} run {Y}" for X, Y in sorted(a.fallback.items()))
                + " (a CONFIRMED max_price pin of the first; each gated at its own cap price)")
        return tail_ladder(S, a, extra, say)
    if first_on(a):   # b64 planner: before the brief and any spend
        err = first_check(S, a, rungs)
        if err:
            say(f"refused: {err}"); return 2
        global LINE_PRESET
        LINE_PRESET = a.preset
        say(f"first session: a row's first ladder session runs {a.first_preset} (effort {a.first_effort or a.effort}, budget "
            f"min(${a.first_budget:.2f}, the rung) at its cap price); every later session {a.preset}")
    if a.driver == "agent":   # b65 steps: --preset-by-rung (checked and frozen before the brief and any spend; no file without it)
        err = (rung_check(S, a) if getattr(a, "rung_map", None) else None) or presets_freeze(S, a) \
            or (fallback_check(S, a) if getattr(a, "fallback", None) else None)   # b66 (A3)
        if err:
            say(f"refused: {err}"); return 2
        if getattr(a, "fallback", None):   # b66 (A3): the router's preset fallback after a CONFIRMED pin (not frozen; the router records it)
            LINE_PRESET = a.preset   # curve(): a stand-in's sessions at their own cap price (reports)
            say("preset fallback: " + "; ".join(f"sessions configured for {X} run {Y}" for X, Y in sorted(a.fallback.items()))
                + " (a CONFIRMED max_price pin of the first; each gated at its own cap price)")
        if a.rung_map:
            LINE_PRESET = a.preset
            say("presets by rung: " + "; ".join(f"sessions toward ${R:.2f} run {P} (effort {E or a.effort}"
                                                  + (f", floor ${floor_at(a, R):.2f}" if getattr(a, "rung_floor", None) else "") + ")"
                                                  for R, (P, E) in sorted(a.rung_map.items())) + f"; every other rung {a.preset}")
    if (a.brief_dir and S.clean) or getattr(a, "agent_artifact", None):
        n_b, n_a = stage_inputs(S, a)
        if a.brief_dir and S.clean:
            say(f"brief: {n_b} of {len(S.names)} row brief(s) staged into {S.root}/_brief (non-row set)")
        if getattr(a, "agent_artifact", None):
            say(f"artifact: {n_a} of {len(S.names)} row record(s) staged into {S.root}/_artifacts (agent.py --artifact; rows without one run a plain session)")
    ab = None
    if getattr(a, "agent_auto_brief", False) and a.driver == "agent":
        err = autobrief_ref_check(S, a)
        if err:   # before any spend: the worktree at --ref would refuse the new options (every row would go on without a brief)
            say(f"refused: {err}"); return 2
        if getattr(a, "auto_brief_pipeline", False):
            ab = autobrief_launch(S, a, say)
        else:
            autobrief_start(S, a, say)
            if getattr(a, "agent_c0", None):   # b63 item 6: the C0 pass extends the briefs before round 1
                if not (S.wt / "harness/cpu_pass.py").exists() or not (S.wt / a.agent_c0).exists():
                    say(f"refused: --agent-c0: the worktree ({S.wt}, --ref {a.ref}) has no harness/cpu_pass.py or no {a.agent_c0}"); return 2
                c0_start(S, a, say)
    if workers_given == "auto":
        say(f"workers auto: {a.workers} (rows {len(S.names)}, OpenRouter limit {workers_auto(10 ** 6)})")
    try:
        return (async_ladder if getattr(a, "async_ladder", False) else ladder)(S, a, rungs, extra, say, ab)
    finally:
        if ab is not None:   # a no-op once the ladder waited for it; otherwise (early return, exception) the container is stopped
            ab.stop("the ladder ended")


def autobrief_ref_check(S: Set, a) -> str | None:
    """2026-10-22: the brief and the sessions run the worktree's code (at --ref): --auto-brief-longest-first needs its autobrief.py to know
    --longest-first, --auto-brief-pipeline its agent.py to know --auto-brief-wait (and harness/brief_gate.py); the reason otherwise."""
    def has(rel: str, flag: str) -> bool:
        try:
            return flag in (S.wt / rel).read_text()
        except OSError:
            return False
    if getattr(a, "auto_brief_longest_first", False) and not has("harness/autobrief.py", '"--longest-first"'):
        return f"--auto-brief-longest-first: the worktree's harness/autobrief.py ({S.wt}, --ref {a.ref}) has no --longest-first"
    if getattr(a, "auto_brief_pipeline", False) and not (has("harness/agent.py", '"--auto-brief-wait"') and (S.wt / "harness/brief_gate.py").exists()):
        return f"--auto-brief-pipeline: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) has no --auto-brief-wait"
    return None


def ladder(S: Set, a, rungs: list[float], extra: list, say, ab: AutoBrief | None = None) -> int:
    """The budget ladder after main's start-up steps. ab (--auto-brief-pipeline): the brief still running in the background; the first
    round's batches get its gate (agent.py --auto-brief-wait), and the ladder waits for its end (bounded) after that round and before a
    rescue or the end, so everything after round 1 starts as it did when the brief ran first."""
    if a.driver == "claude" and getattr(a, "claude_exemplars", False) and exemplars_start(S, a, say):
        return 2   # §13: the first batch reads exemplars of the bests it resumes; a bad extra refuses the ladder before any spend
    # Lineage rule (2026-10-11: after a very poor start point, another fresh start may beat a resume;
    # data: a resumed 2nd session gains +0.89 on average and ~0.1-0.6 on stuck problems, while two independent first sessions
    # differ by ~2-4 points, so a second draw beats another resume on a stuck problem): after every round, a problem below its target by
    # >= 3 points restarts FRESH (empty workspace, max of the lineages kept) when its last session gained < 0.5 (stuck) or its first
    # session landed >= 4 below its typical first session (bad draw); at most 2 fresh restarts per problem, otherwise it resumes.
    T, T1 = targets(S), typical_first(S)
    lin_path = S.out / "lineage.json"
    lin = json.loads(lin_path.read_text()) if lin_path.exists() else {}
    def wants_fresh(n: str, best: float) -> bool:
        L = lin.get(n) or {}
        if not L.get("sessions") or L.get("fresh", 0) >= a.max_fresh or T[n] - best < 3.0:
            return False
        if L["sessions"] == 1 and n in T1 and best < T1[n] - 4.0:
            return True
        return L.get("last_gain") is not None and L["last_gain"] < 0.5
    r = len(rounds(S)) + len(fresh_rounds(S))
    for rung in rungs:
        while True:
            st = states(S)
            todo = focus([n for n in S.names if st.get(n, {"spend": 0.0})["spend"] + floor_at(a, rung) < rung], st, a)
            if not todo:
                break
            if r >= a.max_rounds:
                say(f"max rounds ({a.max_rounds}) reached on rung ${rung:.2f}; stopping"); report(S, a.arm, rung, say); return 1
            r += 1
            score = lambda n: st.get(n, {"score": 33.33})["score"]
            fresh = [n for n in todo if wants_fresh(n, score(n))] if a.lineage_rule else []
            resume = [n for n in todo if n not in fresh]
            first = [n for n in resume if first_due(a, n, st, lin)]   # b64 planner: rows whose first session runs now, on --first-preset
            resume = [n for n in resume if n not in first]
            ar = at_rung(a, rung)   # b65 steps: the rung's preset (--preset-by-rung), else the line
            say(f"round {r} (rung ${rung:.2f}): {len(resume)} resume, {len(fresh)} fresh restart"
                + (f", {len(first)} first session(s) on {a.first_preset}" if first_on(a) else "")
                + (f"; the rung's sessions on {ar.preset} (effort {ar.effort})" if ar is not a else "")
                + f" (spent so far ${sum(v['spend'] for v in st.values()):.2f})")
            if ab is not None and sum(map(bool, (resume, fresh, first))) > 1:   # review 2026-10-22: brief + resume + fresh = 3 x 48g of caps on the 121 GB host; only
                say(f"round {r}: {' and '.join(k for k, v in (('resume', resume), ('fresh', fresh), ('first-session', first)) if v)} batches together; "
                    "the auto-brief finishes first (at most 2 containers at once)")
                ab.finish(); ab = None                 # a resumed ladder's first round has a fresh batch, so the pipeline rarely loses anything
            rextra = extra + ab.gate_args() if ab is not None else extra   # pipelined auto-brief: each row waits for its own brief
            if ab is not None:
                say(f"round {r}: sessions start as their rows' briefs arrive (auto-brief pipeline)")
            jobs = []; t_round = time.time()
            if resume:
                run_id = f"{S.run_prefix}{r}"
                cmd = session_cmd(ar, rung, S.root, run_id, resume, a.workers, ar.effort, False, rextra)
                def run_resume(cmd=cmd, run_id=run_id):
                    with (S.out / f"{run_id}.log").open("a") as f:
                        subprocess.run(cmd, cwd=S.wt, stdout=f, stderr=subprocess.STDOUT)
                jobs.append(run_resume)
            if fresh:
                fid = f"{S.run_prefix[:-1]}f{r}"
                jobs.append(lambda fid=fid: fresh_round(S, fresh, rung, fid, ar.effort, False, rextra, ar, max(1, min(a.workers, len(fresh))), say))
            if first:   # b64 planner: one batch on --first-preset under the round's run id (its own container, tag "first"; its own log)
                run_id = f"{S.run_prefix}{r}"
                cmd = session_cmd(a, rung, S.root, run_id, first, max(1, min(a.workers, len(first))), a.first_effort or a.effort, False, rextra,
                                  "first", preset=a.first_preset, budget=first_budget(a, rung))
                def run_first(cmd=cmd, run_id=run_id):
                    with (S.out / f"{run_id}.first.log").open("a") as f:
                        subprocess.run(cmd, cwd=S.wt, stdout=f, stderr=subprocess.STDOUT)
                jobs.append(run_first)
            if a.driver in ("codex", "claude"):   # one batch at a time: <= 3 containers (codex); <= --workers Claude sessions and host
                for j in jobs:                    # compile streams on the shared subscription (claude, 2026-10-12 review)
                    j()
            else:
                with ThreadPoolExecutor(len(jobs)) as ex:
                    list(ex.map(lambda j: j(), jobs))
            if ab is not None:   # pipelined auto-brief: the next round (and any rescue) starts after the brief, as before
                ab.finish(); ab = None
            # b66 (A3): the round's preset names a confirmation whose marker names none (agent.py's marker names its own)
            pin = pin_stop(S, [f"{S.run_prefix}{r}", f"{S.run_prefix[:-1]}f{r}"], t_round, preset=None if first else eff_preset(a, ar.preset))
            if pin:   # b65 pin, CONFIRMED: no further round
                return pin_out(S, pin, say, f"round {r}")
            if a.driver == "claude" and S.prefix.startswith("sealed"):
                cc_spill(S, say)
            if a.driver == "claude":   # round 2: [polish], ledgers and run techniques before the next batch reads them
                cc_after_batch(S, a, r, todo, say)
            st2 = states(S)
            if first:   # b64 planner: two agent.py processes wrote the run's summary.json (each its own rows): rebuild it from the trajectories
                merge_summary(S, f"{S.run_prefix}{r}")
            for n in first:   # the first session ran once it spent anything: recorded, never run again on this row (a resume included)
                if st2.get(n, {"spend": 0.0})["spend"] > st.get(n, {"spend": 0.0})["spend"] + 1e-9:
                    lin.setdefault(n, {"sessions": 0, "fresh": 0, "last_gain": None})["first"] = first_record(
                        a, f"{S.run_prefix}{r}", rung, st.get(n, {"spend": 0.0}), st2[n])
            for n in todo:
                if st2.get(n, {"spend": 0.0})["spend"] - st.get(n, {"spend": 0.0})["spend"] < 0.05:
                    continue   # 2026-10-12 review: a skipped, one-call or failed session is no evidence that the problem is stuck
                L = lin.setdefault(n, {"sessions": 0, "fresh": 0, "last_gain": None})
                L["sessions"] += 1; L["last_gain"] = round(st2.get(n, {"score": 33.33})["score"] - score(n), 3)
                L["fresh"] += n in fresh
                L.setdefault("gains", []).append([rung, L["last_gain"]])   # per-rung gain history for the rescue's stuck test
            lin_path.write_text(json.dumps(lin, indent=1))
            if sum(v["spend"] for v in st2.values()) <= sum(v["spend"] for v in st.values()) + 1e-6:
                logs = "".join((S.out / f).read_text() for f in [f"{S.run_prefix}{r}.log", f"{S.run_prefix[:-1]}f{r}.log"] if (S.out / f).exists())
                if logs.count("budget reached") >= len(todo):   # every session stopped before its first turn: the rung is full
                    say(f"round {r}: rung ${rung:.2f} full (every remaining session's first-turn worst case exceeds what is left)"); break
                say(f"round {r}: no spend recorded (API or key problem?); stopping"); return 1
            if a.driver == "claude" and a.claude_review:   # §11: the reviewer for the rows the next round resumes (after polish and in-run steps)
                plan = next_plan(S, a, rungs, rung, r, wants_fresh)
                if plan:
                    cc_review(S, a, r + 1, plan[0], plan[1], say)
                else:
                    say(f"round {r}: the last round, no review")
            say(f"round {r} done: mean so far {statistics.mean(st2.get(n, {'score': 33.33})['score'] for n in S.names):.2f}")
            if a.round_per_rung:   # one round per rung: the next round climbs (A4)
                break
        report(S, a.arm, rung, say, title=f"MILESTONE ${rung:.2f}")
        st = states(S)
        mean = statistics.mean(st.get(n, {"score": 33.33})["score"] for n in S.names)
        if a.stop_at is not None and abs(rung - a.stop_rung) < 1e-9 and mean >= a.stop_at:
            say(f"STOP RULE: mean {mean:.2f} >= {a.stop_at} at the ${rung:.2f} milestone; not climbing further"); break
        nxt = next((x for x in rungs if x > rung + 1e-9), None)
        if a.rescue and abs(rung - a.rescue_rung) < 1e-9 and nxt and not (S.out / "rescue.done").exists():
            if ab is not None:   # (a resumed ladder whose first action is the rescue)
                ab.finish(); ab = None
            cands = [n for n in S.names if nxt - st.get(n, {"spend": 0.0})["spend"] >= floor_at(a, nxt)]
            # 2026-10-11 (warm-up: Electromagnetism climbed 33.33 -> 73.89 on this rung, yet was still furthest below target): a rescue is a
            # fresh draw for STUCK problems; one still climbing keeps resuming. Stuck = gained < 0.5 over the whole rung, not the last session:
            # a rung's trailing session is often a few turns long (the turn reserve fills what is left) and gains ~0 even on a climbing problem.
            rung_gain = lambda n: sum(g for rg, g in (lin.get(n) or {}).get("gains", []) if abs(rg - rung) < 1e-9 and g is not None)
            climbing = [n for n in cands if not (lin.get(n) or {}).get("gains") or rung_gain(n) >= 0.5]
            cands = [n for n in cands if n not in climbing]
            if climbing:
                say(f"RESCUE: {len(climbing)} candidate(s) skipped as not stuck (gained >= 0.5 on this rung, or no session yet)"
                    + (f": {', '.join(climbing)}" if S.prefix == "wu" else ""))
            pick = sorted(cands, key=lambda n: st.get(n, {"score": 33.33})["score"] - T[n])[: a.rescue]
            if pick:
                r += 1
                say(f"RESCUE: one fresh RESTRUCTURE session (empty workspace, effort {a.rescue_effort}) for {len(pick)} problems furthest below target")
                t_resc = time.time()
                fresh_round(S, pick, nxt, f"{S.run_prefix[:-1]}f{r}", a.rescue_effort, True, extra, at_rung(a, nxt),
                            max(1, min(a.workers, len(pick))) if a.driver == "claude" else len(pick), say)   # claude: <= --workers sessions
                pin = pin_stop(S, [f"{S.run_prefix[:-1]}f{r}"], t_resc, preset=eff_preset(a, at_rung(a, nxt).preset))
                if pin:   # b65 pin, CONFIRMED
                    return pin_out(S, pin, say, "RESCUE")
                if a.driver == "claude" and S.prefix.startswith("sealed"):
                    cc_spill(S, say)
                if a.driver == "claude":
                    cc_after_batch(S, a, r, pick, say)
                report(S, a.arm, rung, say, title="AFTER RESCUE")
            (S.out / "rescue.done").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    if ab is not None:   # no round ran in this invocation: the brief still completes, as when it ran first
        ab.finish()
    say("HELDOUT DONE")
    return 0


# ---------------------------------------------------------------------------------------------------------------------------------------
# --async-ladder (2026-10-26): no synchronized rounds (module docstring "Async ladder")
ASYNC_POLL_S = 5.0     # scheduler wake-up while it waits for a brief (sessions in flight wake it when they end)
ASYNC_IDLE_S = 60.0    # wake-up with sessions in flight and nothing else to wait for (each end wakes it at once)
ASYNC_MAX_DRY = 3      # sessions in a row without spend (and without "budget reached") after which a row is parked on this rung
_RUN_K = re.compile(r"-[rf](\d+)$")


def _traj_stem(fname: str) -> str | None:
    for ext in (".jsonl.gz", ".jsonl"):
        if fname.endswith(ext):
            return fname[: -len(ext)]
    return None


def row_rounds(S: Set) -> dict:
    """{row: the highest round number of this line's r / f runs that hold its trajectory} (0: none yet). The async ladder runs a row's
    next session as round row_rounds + 1, so a row's k-th session is round k, as in a round ladder where every row takes one session per
    round; a round ladder's rounds a row sat out (it was full, or not active in a router phase) are skipped, never reused for that row."""
    ws = {safe(n): n for n in S.names}
    out = {n: 0 for n in S.names}
    for p in rounds(S) + fresh_rounds(S):
        m = _RUN_K.search(p.name); td = p / "trajectories"
        if not m or not td.is_dir():
            continue
        for f in td.iterdir():
            n = ws.get(_traj_stem(f.name) or "")
            if n is not None:
                out[n] = max(out[n], int(m.group(1)))
    return out


def _end_event(f: pathlib.Path) -> dict | None:
    """The last `end` event of a trajectory file (agent.py writes {"type": "end", **summary, "finished": ...} as a session's last line)."""
    end = None
    try:
        op = gzip.open if f.suffix == ".gz" else open
        with op(f, "rt", errors="replace") as h:
            for line in h:
                if '"end"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if isinstance(e, dict) and e.get("type") == "end":
                    end = e
    except (OSError, EOFError, ValueError):
        return end
    return end


def merge_summary(S: Set, run_id: str) -> int:
    """--async-ladder: probe/runs/<run_id>/summary.json rebuilt from the end events of ALL the run's finished trajectories (also rows outside
    this invocation's --problems: a router phase runs a subset, and a round's dir may hold earlier phases' rows): the entry agent.py returns
    for a row (run_problem's summary) is its end event without t / type / finished. The one-row agent.py processes of a round each write
    summary.json with only their own row; the ladder rewrites it after every session of the run ends, so the last write is always the merged
    list. Order: this invocation's rows in set order, then the others by file name. Returns the entries written."""
    rd = S.wt / "probe/runs" / run_id; td = rd / "trajectories"
    if not td.is_dir():
        return 0
    order = {n: i for i, n in enumerate(S.names)}
    stems = sorted({st for st in (_traj_stem(f.name) for f in td.iterdir()) if st})
    res = []
    for stem in stems:
        for f in (td / f"{stem}.jsonl.gz", td / f"{stem}.jsonl"):
            if f.exists():
                e = _end_event(f)
                if e:
                    res.append({k: v for k, v in e.items() if k not in ("t", "type", "finished")})
                break
    res.sort(key=lambda e: (order.get(e.get("problem"), len(order)), safe(str(e.get("problem") or ""))))
    tmp = rd / f".summary.json.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(res, indent=1))
    os.replace(tmp, rd / "summary.json")
    return len(res)


def summary_stale(S: Set, rd: pathlib.Path) -> bool:
    """A run dir (this line's own) whose summary.json does not list exactly the rows with a finished (gzipped) trajectory there: a ladder
    killed between a session's end and its summary rewrite (one-row agent.py processes overwrite each other's summary.json), or a round
    ladder's round that died before agent.py wrote it."""
    td = rd / "trajectories"
    if not td.is_dir():
        return False
    done = {f.name[: -len(".jsonl.gz")] for f in td.glob("*.jsonl.gz")}
    try:
        listed = {safe(e.get("problem") or "") for e in json.loads((rd / "summary.json").read_text())}
    except (OSError, ValueError, AttributeError):
        return bool(done)
    return listed != done


def states_live(S: Set, cache: dict) -> dict:
    """states() while sessions run: agent.py rewrites state.json in place (Workspace.save: not atomic), so a read can catch a partial file.
    A failed read is retried and else the path's last good reading is used; only in-flight rows can be mid-write, and the ladder never
    decides on an in-flight row (a finished session's process has exited before its numbers are read)."""
    res = {}
    for p in (S.wt / S.root).glob("*/state.json"):
        d = None
        for i in range(3):
            try:
                d = json.loads(p.read_text())
                break
            except (OSError, ValueError):
                time.sleep(0.05 * (i + 1))
        if d is None:
            d = cache.get(p)
            if d is None:
                continue
        else:
            d = {"problem": d.get("problem"), "best": {"score": (d.get("best") or {}).get("score")}, "api_spend": d.get("api_spend"),
                 **({"cap_extra": d["cap_extra"]} if d.get("cap_extra") else {})}   # b64 planner (row_spend)
            cache[p] = d
        if d.get("problem") in S.names:
            res[d["problem"]] = row_spend(d, {"score": d["best"].get("score") or 33.33})
    return res


def wants_fresh_rule(lin: dict, T: dict, T1: dict, a, n: str, best: float) -> bool:
    """The lineage rule of ladder() (its wants_fresh), for the async ladder: a row below its target by >= 3 restarts fresh when its last
    session gained < 0.5 or its first session landed >= 4 below the typical first session; at most --max-fresh restarts per row."""
    L = lin.get(n) or {}
    if not L.get("sessions") or L.get("fresh", 0) >= a.max_fresh or T[n] - best < 3.0:
        return False
    if L["sessions"] == 1 and n in T1 and best < T1[n] - 4.0:
        return True
    return L.get("last_gain") is not None and L["last_gain"] < 0.5


def _write_json(p: pathlib.Path, d) -> None:
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(d, indent=1))
    os.replace(tmp, p)


def pin_stop(S: Set, run_ids: list, since: float, rc=None, live=(), preset: str | None = None) -> str | None:
    """b65 pin (harness/pinwatch.py): the message of a CONFIRMED max_price pin, else None. Confirmed = a session that ended exited
    PIN_FATAL_RC, or left PIN_MARKER in one of these runs' directories at or after `since` (an async round's run id is shared by rows and
    reused after a restart: an older marker is not this session's), or (b65-final, across sessions: one agent.py process confirms only its
    own threads' errors) the pin_events.jsonl lines of these runs at or after `since` show the same preset's pin error on PIN_ROWS rows within
    PIN_WINDOW_S and after its last answer. Every confirmation is written as PIN_MARKER into the `live` runs' directories (a cross-session one
    into these runs' too), so the sessions in flight end at their next turn or backoff poll ($0) instead of each confirming on its own.
    b66 (A3): the message is a pinwatch.PinMsg carrying the confirmed preset (the marker's, the 2-row rule's, else `preset`: the session's
    own) into every marker and the ladder's out-dir marker (pin_out), where the router reads which preset to fall back from. A marker or an
    event of a preset this ladder fell back from (PIN_GONE) is not a stop of this invocation (a reused async run dir may hold one)."""
    hint = preset or ""
    dirs = [S.wt / "probe/runs" / rid for rid in dict.fromkeys(run_ids)]
    msg, preset, into = None, "", [S.wt / "probe/runs" / rid for rid in dict.fromkeys(live)]
    for d in dirs:
        mk = d / PIN_MARKER
        try:
            if mk.exists() and mk.stat().st_mtime >= since - 1.0:
                j = json.loads(mk.read_text())
                mp = j.get("preset") or ""
                if mp and mp in PIN_GONE:   # b66 (A3): the marker of a preset this ladder fell back from (a reused async run dir)
                    continue
                msg, preset = j.get("message") or str(mk), mp or hint
                break
        except (OSError, ValueError):
            msg = str(mk); break
    if msg is None and rc == PIN_FATAL_RC:
        msg, preset = f"FATAL: a session exited {rc} (agent.py: a CONFIRMED max_price pin)", hint
    if msg is None:
        hit = PW.rows_rule([e for e in PW.read_events(dirs, since) if e.get("preset") not in PIN_GONE])   # b66: not a fallen-back preset's
        if not hit:
            return None
        msg, preset, into = f"CONFIRMED ({hit['why']}, across sessions): {hit['message']}", hit["preset"], dirs + into
    preset = preset or hint
    for d in dict.fromkeys(into):
        PW.write_marker(d, preset, msg)
    return PW.pin_msg(msg, preset)


def pin_out(S: Set, msg: str, say, where: str) -> int:
    """b65-final: a CONFIRMED pin ends the ladder: loud, PIN_MARKER in the ladder's out dir (the router reads the reason there), exit
    PIN_FATAL_RC. The router then finishes the run on its $0 path (no new paid session; finals.json and the submission file complete)."""
    say(f"{where}: FATAL (max_price pin): {msg}")
    say(f"{where}: STOPPED on a CONFIRMED max_price pin (exit {PIN_FATAL_RC}); no further paid session starts")
    PW.write_marker(S.out, getattr(msg, "preset", "") or "", msg)   # b66 (A3): the preset, for the router's fallback
    return PIN_FATAL_RC


def _run_logged(cmd: list, cwd, log_path: pathlib.Path) -> int:
    with log_path.open("a") as f:
        return subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT).returncode


def async_ladder(S: Set, a, rungs: list[float], extra: list, say, ab: AutoBrief | None = None) -> int:
    """--async-ladder: the budget ladder without synchronized rounds (module docstring "Async ladder"). Same rungs (barriers), run ids,
    budgets, lineage rule and lineage.json, MILESTONE / stop rule / rescue and exit codes as ladder(); returns 0 (HELDOUT DONE), 1 (max
    rounds, no spend, a parked row), 2 (refused) or PIN_FATAL_RC (b65: a session's preset has no endpoint under its max_price pin, CONFIRMED
    (b65-final, harness/pinwatch.py; a single pin error is retried by the session after a backoff, $0); no session starts after it, the ones
    in flight end; pin_stop)."""
    T, T1 = targets(S), typical_first(S)
    lin_path = S.out / "lineage.json"
    lin = json.loads(lin_path.read_text()) if lin_path.exists() else {}
    idx = {n: i for i, n in enumerate(S.names)}
    tag = lambda n: f"s{idx[n]:02d}"   # noqa: E731  container names, logs and fresh roots carry the row's index, never its name
    used: dict = {}      # row -> the last round this invocation gave it (a session that left no trajectory still advances the row)
    cache: dict = {}     # state.json path -> last good reading (states_live)
    # round numbers as the round ladder gives them: it starts at the count of this line's r / f runs and a row's j-th session on a rung is
    # round (the rounds before the rung) + j, because every row below the rung takes one session in every round of the rung
    r_cur = max([len(rounds(S)) + len(fresh_rounds(S))] + [int(m.group(1)) for p in rounds(S) + fresh_rounds(S) for m in [_RUN_K.search(p.name)] if m])
    for rd in rounds(S) + fresh_rounds(S):   # a dead async ladder's last summary rewrite may be missing: repair what it left
        if summary_stale(S, rd):
            merge_summary(S, rd.name)
    t_inv, pin_runs = time.time(), set()   # b65-final: this invocation's sessions' run dirs (pin_events.jsonl, cross-session confirmation)
    say(f"async ladder: {a.workers} worker(s) over {len(S.names)} row(s), rungs {', '.join(f'${x:.2f}' for x in rungs)}: a row's next session "
        f"starts when its last one ends (one session in flight per row; every row reaches a rung before any row passes it)")
    for rung in rungs:
        full, parked, dry_rows, started = set(), set(), {}, {}   # started: sessions launched on this rung per row
        base = r_cur          # the rounds before this rung
        inflight: dict = {}   # future -> job
        stop, spent_any, pin = None, False, None   # pin: b65 fatal pin, no session starts after it
        st = states_live(S, cache)
        say(f"async rung ${rung:.2f}: {sum(1 for n in S.names if st.get(n, {'spend': 0.0})['spend'] + floor_at(a, rung) < rung)} row(s) below it "
            f"(spent so far ${sum(v['spend'] for v in st.values()):.2f})")
        ex = ThreadPoolExecutor(max(1, a.workers), thread_name_prefix="lra-async")
        try:
            while True:
                if pin is None and inflight:   # b65-final: a pin error on 2 rows' sessions (2 processes) within the window confirms it
                    pin = pin_stop(S, sorted(pin_runs), t_inv, live=[j["run_id"] for j in inflight.values()])
                    if pin:
                        say(f"async: {pin}; no further session starts, the {len(inflight)} in flight end at their next turn ($0)")
                elif pin is not None and inflight:   # b65-final: the markers stay fresh (they expire after PIN_WINDOW_S) until the last ends
                    for rid in dict.fromkeys(j["run_id"] for j in inflight.values()):
                        PW.write_marker(S.wt / "probe/runs" / rid, getattr(pin, "preset", "") or "", pin)   # b66: the pinned preset only
                if pin is not None and not inflight:   # b65 pin, CONFIRMED: every session in flight has ended (each fails fast, $0)
                    return pin_out(S, pin, say, "async")
                st = states_live(S, cache)
                busy = {j["n"] for j in inflight.values()}
                below = [n for n in S.names if st.get(n, {"spend": 0.0})["spend"] + floor_at(a, rung) < rung]
                need = [n for n in focus(below, st, a) if n not in full and n not in parked
                        and not (a.round_per_rung and started.get(n) and n not in busy)]
                if not need and not inflight:
                    break
                rr = row_rounds(S)   # (a guard: a row's round never goes back, whatever ran in between)
                nxt = {n: max(base + started.get(n, 0), rr.get(n, 0), used.get(n, 0)) + 1 for n in need}
                idle = [n for n in need if n not in busy]
                capped = [n for n in idle if nxt[n] > a.max_rounds]
                ab_live = ab is not None and ab.watcher.is_alive() and time.time() - ab.t0 < ab.timeout + 2 * AB_GRACE
                brief_ok = lambda n: (not ab_live or (S.wt / ab.od / f"{safe(n)}.json").exists() or ab.marker.exists())   # noqa: E731
                ready = [n for n in idle if n not in capped and brief_ok(n)]
                if stop is None and not inflight and need and all(dry_rows.get(n, 0) >= 1 for n in need):
                    stop = "no spend recorded (API or key problem?)"   # as a round ladder's round in which no session spent anything
                if stop is None and pin is None:
                    ready.sort(key=lambda n: (nxt[n], st.get(n, {}).get("score", 33.33) if a.low_first else 0.0,
                                              st.get(n, {"spend": 0.0})["spend"], idx[n]))
                    for n in ready[: max(0, a.workers - len(inflight))]:
                        k = nxt[n]; used[n] = k; started[n] = started.get(n, 0) + 1; r_cur = max(r_cur, k)
                        b0 = dict(st.get(n, {"spend": 0.0, "score": 33.33}))
                        first = first_due(a, n, st, lin)   # b64 planner: the row's first session, on --first-preset
                        ar = at_rung(a, rung)   # b65 steps: every other session on the rung's preset (--preset-by-rung), else the line
                        fresh = bool(not first and a.lineage_rule and wants_fresh_rule(lin, T, T1, a, n, b0["score"]))
                        run_id = f"{S.run_prefix[:-1]}f{k}" if fresh else f"{S.run_prefix}{k}"
                        logp = S.out / f"{run_id}.{tag(n)}.log"
                        rextra = extra + ab.gate_args() if ab_live else extra   # pipelined auto-brief: the gate, as round 1's batch has it
                        if fresh:
                            fu = ex.submit(fresh_round, S, [n], rung, run_id, ar.effort, False, rextra, ar, 1, say,
                                           froot=S.wt / f"{S.root}-fresh.{tag(n)}", tag=tag(n), log_path=logp)
                        elif first:
                            fu = ex.submit(_run_logged, session_cmd(a, rung, S.root, run_id, [n], 1, a.first_effort or a.effort, False, rextra, tag(n),
                                                                    preset=a.first_preset, budget=first_budget(a, rung)), S.wt, logp)
                        else:
                            fu = ex.submit(_run_logged, session_cmd(ar, rung, S.root, run_id, [n], 1, ar.effort, False, rextra, tag(n)), S.wt, logp)
                        pin_runs.add(run_id)
                        inflight[fu] = {"n": n, "k": k, "kind": "fresh" if fresh else "resume", "run_id": run_id, "log": logp, "t0": time.time(),
                                        "b0": b0, "first": first, "preset": eff_preset(a, a.first_preset if first else ar.preset)}
                        say(f"async: row#{idx[n]:02d} round {k} (rung ${rung:.2f}) starts ({'fresh restart' if fresh else 'resume'}, spent "
                            f"${b0['spend']:.2f}; {len(inflight)} in flight"
                            + (f"; first session on {a.first_preset}, budget ${first_budget(a, rung):.2f}" if first else "")
                            + (f"; on {ar.preset}" if ar is not a and not first else "")
                            + (f"; on {eff_preset(a, a.first_preset if first else ar.preset)} (preset fallback)"
                               if eff_preset(a, a.first_preset if first else ar.preset) != (a.first_preset if first else ar.preset) else "")
                            + ")")   # "round K (rung $X)": the round ladder's form (g8_pilot reads it)
                if not inflight:
                    if stop is not None:
                        say(f"async: {stop}; stopping"); return 1
                    if capped and len(capped) == len(idle):
                        say(f"max rounds ({a.max_rounds}) reached on rung ${rung:.2f}; stopping"); report(S, a.arm, rung, say); return 1
                    time.sleep(ASYNC_POLL_S)   # rows wait for their briefs (bounded: the brief's marker, or its timeout + grace)
                    continue
                done, _ = fwait(list(inflight), timeout=ASYNC_POLL_S if (ab_live or capped) else ASYNC_IDLE_S, return_when=FIRST_COMPLETED)
                for fu in done:
                    j = inflight.pop(fu); n = j["n"]
                    try:
                        rc = fu.result()
                    except Exception as e:  # noqa: BLE001  (a session runner that raised: its row's numbers are read as for any end)
                        rc = None; say(f"async: row#{idx[n]:02d} round {j['k']}: session runner raised {type(e).__name__}: {e}")
                    if pin is None:   # b65-final: a confirmation ends the sessions in flight too (PIN_MARKER in their run dirs)
                        pin = pin_stop(S, [j["run_id"]], j["t0"], rc, live=[x["run_id"] for x in inflight.values()], preset=j.get("preset"))
                        if pin and inflight:
                            say(f"async: {pin}; no further session starts, the {len(inflight)} in flight end at their next turn ($0)")
                    if j["kind"] == "fresh" and (S.wt / f"{S.root}-fresh.{tag(n)}").is_dir():
                        # review 2026-10-26: a fresh runner that raised before its merge (or its archive rename) left the row's spend in its
                        # own fresh root; a resume would read the main state without it and could pass the rung. Merge it now (spend = max,
                        # idempotent); if that fails too, the row is parked (the ladder exits 1; start-up recovery retries it)
                        try:
                            recover_fresh(S, say, S.wt / f"{S.root}-fresh.{tag(n)}")
                        except Exception as e:  # noqa: BLE001
                            parked.add(n); say(f"async: row#{idx[n]:02d}: its fresh root could not be merged ({type(e).__name__}: {e}); parked")
                    st2 = states_live(S, cache)
                    s0, c0 = j["b0"].get("spend", 0.0), j["b0"].get("score", 33.33)
                    s1, c1 = st2.get(n, {"spend": s0})["spend"], st2.get(n, {"score": c0})["score"]
                    secs = time.time() - j["t0"]
                    try:
                        merge_summary(S, j["run_id"])
                        # b64 planner (--first-preset): the session's preset and the billed spend (spend_* are at the cap price)
                        fx = {"preset": j["preset"], "billed_before": round(j["b0"].get("billed", s0), 6),   # b65 steps: or the rung's preset
                              "billed_after": round(st2.get(n, {}).get("billed", s1), 6)} if first_on(a) or getattr(a, "rung_map", None) else {}
                        with (S.wt / "probe/runs" / j["run_id"] / "async_sessions.jsonl").open("a") as f:
                            f.write(json.dumps({"problem": n, "row": idx[n], "round": j["k"], "kind": j["kind"], "rung": rung, "rc": rc,
                                                "start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(j["t0"])),
                                                "end": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seconds": round(secs, 1),
                                                "spend_before": round(s0, 6), "spend_after": round(s1, 6), "score_before": c0, "score_after": c1, **fx},
                                               ensure_ascii=False) + "\n")
                    except OSError as e:   # a session that never created its run dir (e.g. docker failed to start): nothing to merge
                        say(f"async: row#{idx[n]:02d} round {j['k']}: no run record ({type(e).__name__})")
                    if j.get("first") and s1 - s0 > 1e-9:   # b64 planner: the first session ran (as ladder(): never again on this row)
                        lin.setdefault(n, {"sessions": 0, "fresh": 0, "last_gain": None})["first"] = first_record(a, j["run_id"], rung, j["b0"], st2[n])
                    if s1 - s0 >= 0.05:   # as ladder(): a skipped, one-call or failed session is no evidence that the row is stuck
                        L = lin.setdefault(n, {"sessions": 0, "fresh": 0, "last_gain": None})
                        L["sessions"] += 1; L["last_gain"] = round(c1 - c0, 3)
                        L["fresh"] += j["kind"] == "fresh"
                        L.setdefault("gains", []).append([rung, L["last_gain"]])
                    if (j.get("first") and s1 - s0 > 1e-9) or s1 - s0 >= 0.05:
                        _write_json(lin_path, lin)
                    note = ""
                    if s1 - s0 <= 1e-6:
                        try:
                            # b64 planner: a first session that ended before any spend never marks the row full (it is retried, parked
                            # after ASYNC_MAX_DRY like any session without spend; first_check makes its budget cover the first turn)
                            reached = "budget reached" in j["log"].read_text(errors="replace") and not j.get("first")
                        except OSError:
                            reached = False
                        if reached:   # its first turn's worst case exceeds what is left: full on this rung (a round ladder's "rung full")
                            full.add(n); note = "; full on this rung (budget reached before any spend)"
                        else:
                            dry_rows[n] = dry_rows.get(n, 0) + 1
                            note = f"; no spend ({dry_rows[n]} in a row)"
                            if dry_rows[n] >= ASYNC_MAX_DRY:
                                parked.add(n); note += f"; parked on this rung after {ASYNC_MAX_DRY} sessions without spend"
                    else:
                        dry_rows[n] = 0; spent_any = True
                    mean = statistics.mean(st2.get(x, {"score": 33.33})["score"] for x in S.names)
                    say(f"async: row#{idx[n]:02d} round {j['k']} done ({j['kind']}, rc {rc}): ${s0:.2f} -> ${s1:.2f}, {c0:.2f} -> {c1:.2f} in "
                        f"{secs:.0f} s; {len(inflight)} in flight; mean so far {mean:.2f}{note}")
        finally:
            ex.shutdown(wait=True)   # an exception in the scheduler: the sessions in flight still end (and their spend is on disk)
        if parked and not spent_any:   # every session of the rung ended without spend: the round ladder's message
            say(f"async: no spend recorded (API or key problem?); stopping ({len(parked)} row(s) parked after {ASYNC_MAX_DRY} sessions each)")
            return 1
        if parked:
            say(f"async: {len(parked)} row(s) parked on rung ${rung:.2f} after {ASYNC_MAX_DRY} sessions without spend each; stopping "
                f"(a restart retries them)"); report(S, a.arm, rung, say); return 1
        if ab is not None:   # pipelined auto-brief: the brief has ended before anything after the first rung (as after a round ladder's round 1)
            ab.finish(); ab = None
        # MILESTONE, stop rule and rescue: ladder()'s code path at the rung's end
        report(S, a.arm, rung, say, title=f"MILESTONE ${rung:.2f}")
        st = states(S)
        mean = statistics.mean(st.get(n, {"score": 33.33})["score"] for n in S.names)
        if a.stop_at is not None and abs(rung - a.stop_rung) < 1e-9 and mean >= a.stop_at:
            say(f"STOP RULE: mean {mean:.2f} >= {a.stop_at} at the ${rung:.2f} milestone; not climbing further"); break
        nxt_rung = next((x for x in rungs if x > rung + 1e-9), None)
        if a.rescue and abs(rung - a.rescue_rung) < 1e-9 and nxt_rung and not (S.out / "rescue.done").exists():
            cands = [n for n in S.names if nxt_rung - st.get(n, {"spend": 0.0})["spend"] >= floor_at(a, nxt_rung)]
            rung_gain = lambda n: sum(g for rg, g in (lin.get(n) or {}).get("gains", []) if abs(rg - rung) < 1e-9 and g is not None)   # noqa: E731
            climbing = [n for n in cands if not (lin.get(n) or {}).get("gains") or rung_gain(n) >= 0.5]
            cands = [n for n in cands if n not in climbing]
            if climbing:
                say(f"RESCUE: {len(climbing)} candidate(s) skipped as not stuck (gained >= 0.5 on this rung, or no session yet)"
                    + (f": {', '.join(climbing)}" if S.prefix == "wu" else ""))
            pick = sorted(cands, key=lambda n: st.get(n, {"score": 33.33})["score"] - T[n])[: a.rescue]
            if pick:
                rr = row_rounds(S)
                k = max([r_cur] + [max(rr.get(n, 0), used.get(n, 0)) for n in pick]) + 1   # the round ladder's r += 1 for the rescue
                r_cur = k
                for n in pick:
                    used[n] = k
                say(f"RESCUE: one fresh RESTRUCTURE session (empty workspace, effort {a.rescue_effort}) for {len(pick)} problems furthest below target")
                fid = f"{S.run_prefix[:-1]}f{k}"
                t_resc = time.time()
                fresh_round(S, pick, nxt_rung, fid, a.rescue_effort, True, extra, at_rung(a, nxt_rung), len(pick), say)
                pin = pin_stop(S, [fid], t_resc, preset=eff_preset(a, at_rung(a, nxt_rung).preset))
                if pin:   # b65 pin, CONFIRMED
                    return pin_out(S, pin, say, "RESCUE")
                merge_summary(S, fid)   # the batch's own summary.json may have replaced async rows' entries of the same round
                report(S, a.arm, rung, say, title="AFTER RESCUE")
            (S.out / "rescue.done").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    if ab is not None:   # no session ran in this invocation: the brief still completes, as when it ran first
        ab.finish()
    say("HELDOUT DONE")
    return 0



# ------------------------------------------------------------------------------------------------------------------------ b68 tail stage
# docs/b68_tail.md. The router runs
# this mode after the review and before the end stage, once per run, over the rows whose room under the cap is at least its --tail-min-room.
# Each row's sessions are the ladder's own agent.py sessions (session_cmd: the line's agent flags, container, key) of --tail-preset in the
# row's own work root, so they resume from its stored best (the router wrote its current best back first) with its notes, pool and bank. The
# cap holds by the existing gate alone: --budget-usd is the row's TOP = (state api_spend + cap_extra when the router planned the tail) +
# (cap - the row's metered spend at the cap price - margin), and agent.py never sends a call whose worst case does not fit under it. The
# session floor is the preset's own (the reclaim formula with --agent-budget-reclaim, as a --preset-by-rung rung's), so a row whose top is
# within a floor of its spend runs nothing.
TAIL_LOG = "tail_sessions.jsonl"   # <out>/tail_sessions.jsonl: one line per tail session (the router reads its rows' lines)
_TAIL_K = re.compile(r"-t(\d+)$")


def tail_tops(path) -> dict:
    """--tail FILE -> {row: top USD}; ValueError on a malformed file."""
    d = json.loads(pathlib.Path(path).read_text())
    tops = d.get("tops") if isinstance(d, dict) else None
    if not isinstance(tops, dict) or not tops:
        raise ValueError(f"{path}: no \"tops\" object")
    out = {}
    for n, v in tops.items():
        x = float(v)
        if not (math.isfinite(x) and x > 0):
            raise ValueError(f"{path}: top {v!r} is not a positive number")
        out[str(n)] = x
    return out


def tail_check(S: "Set", a) -> str | None:
    """--tail at start-up, before any spend: the tops file parses and names rows of this run; --tail-preset is an OpenRouter agent.py session
    preset here and in the worktree's agent.py (at --ref), whose gate counts cap_extra (as rung_check). The reason otherwise."""
    try:
        tops = tail_tops(a.tail)
    except (OSError, ValueError) as e:
        return f"--tail: {e}"
    if not [n for n in tops if n in S.names]:
        return "--tail: no row of this run (--problems) in the tops file"
    sys.path.insert(0, str(MAIN))
    from harness.agent import MODEL_PRESETS   # noqa: E402
    pp = MODEL_PRESETS.get(a.tail_preset) or {}
    url = pp.get("base_url") or ""
    azure = ".azure.com" in url
    # b68 review (2026-10-28: the dev probe on Azure): or an Azure preset metered at its list table (as the router's tail_preset_ok)
    if not pp or pp.get("anthropic_vertex") or not ("openrouter.ai" in url or (azure and pp.get("list_price"))):
        return f"--tail-preset {a.tail_preset}: not an OpenRouter agent.py session preset (nor a list-priced Azure one)"
    try:
        src = (S.wt / "harness/agent.py").read_text()
    except OSError:
        src = ""
    # an Azure preset <alias>-azure is built in agent.py from AZURE_TEMPLATES["<alias>"] (_azure_presets): the worktree's needs that template
    mark = f'"{a.tail_preset[:-len("-azure")]}": dict(' if azure and a.tail_preset.endswith("-azure") else f'"{a.tail_preset}"'
    if mark not in src:
        return f"--tail-preset: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) has no preset {a.tail_preset}"
    gate = re.search(r"def _gate_spend\(\)[^\n]*\n(?:[ \t]*#[^\n]*\n)*[ \t]*return ([^\n]+)", src)
    if not gate or "cap_extra" not in gate.group(1) or "_cap_diff" in gate.group(1):
        return f"--tail-preset: the worktree's harness/agent.py ({S.wt}, --ref {a.ref}) does not count cap_extra in every session's gate"
    return None


def tail_floor(a) -> float:
    """A tail session's floor: the preset its sessions run (--preset-fallback applies) at its own floor (a.tail_floor / a.fallback_floor, set
    with --agent-budget-reclaim: reclaim_session_floor), else SESSION_FLOOR."""
    P = eff_preset(a, a.tail_preset)
    if P != a.tail_preset:
        return (getattr(a, "fallback_floor", None) or {}).get(P, SESSION_FLOOR)
    return getattr(a, "tail_floor", None) or SESSION_FLOOR


def tail_runs(S: "Set") -> list[pathlib.Path]:
    return sorted(_own(S, "t"), key=lambda p: int(_TAIL_K.search(p.name).group(1)))


def tail_prior(S: "Set") -> dict:
    """{row: tail sessions recorded by earlier invocations} from <out>/tail_sessions.jsonl."""
    out: dict = {}
    try:
        for l in (S.out / TAIL_LOG).read_text().splitlines():
            try:
                n = json.loads(l).get("problem")
            except ValueError:
                continue
            if n:
                out[n] = out.get(n, 0) + 1
    except OSError:
        pass
    return out


def _session_turns(S: "Set", run_id: str, n: str):
    try:
        return next((e.get("turns") for e in json.loads((S.wt / "probe/runs" / run_id / "summary.json").read_text()) if e.get("problem") == n), None)
    except (OSError, ValueError, AttributeError):
        return None


def tail_ladder(S: "Set", a, extra: list, say) -> int:
    """--tail: the tail sessions (module notes above). A row's i-th session of this invocation runs as <prefix>-hx-<arm>-t<k + i> (k: the
    highest tail run of the arm so far, so a restart never reuses the run dir of a session it killed), --workers 1 --problems ROW, budget =
    its top. A row gets a session while spend + floor < top and it has had fewer than --tail-max-sessions; a session that spent nothing ends
    the row when its log says "budget reached" (its first call's worst case does not fit), else after ASYNC_MAX_DRY such sessions. Returns 0,
    1 (a row parked after sessions without spend) or PIN_FATAL_RC (a CONFIRMED pin: no session starts after it, the ones in flight end;
    pin_out's marker names the preset for the router's fallback)."""
    tops = tail_tops(a.tail)
    names = [n for n in S.names if n in tops]
    idx = {n: i for i, n in enumerate(S.names)}
    tag = lambda n: f"s{idx[n]:02d}"   # noqa: E731  container names, logs: the row's index, never its name
    ar = argparse.Namespace(**dict(vars(a), preset=a.tail_preset, effort=a.tail_effort or a.effort))
    floor = tail_floor(a)
    workers = max(1, int(a.workers))
    prior = tail_prior(S)
    k_base = max([int(_TAIL_K.search(p.name).group(1)) for p in tail_runs(S)] or [0])
    started: dict = {n: 0 for n in names}
    full, parked, dry, cache = set(), set(), {}, {}
    inflight: dict = {}
    t_inv, pin_runs, pin = time.time(), set(), None
    P = eff_preset(a, a.tail_preset)
    say(f"tail: {len(names)} row(s), preset {a.tail_preset}" + (f" (runs {P}: preset fallback)" if P != a.tail_preset else "")
        + f", effort {ar.effort}, floor ${floor:.2f}, at most {a.tail_max_sessions} session(s) per row, {workers} at once; each session's "
        "budget = the row's top (the router's room under the cap)")
    ex = ThreadPoolExecutor(workers, thread_name_prefix="lra-tail")
    try:
        while True:
            if pin is None and inflight:   # as async_ladder: a pin error on 2 rows' sessions within the window confirms it
                pin = pin_stop(S, sorted(pin_runs), t_inv, live=[j["run_id"] for j in inflight.values()])
                if pin:
                    say(f"tail: {pin}; no further session starts, the {len(inflight)} in flight end at their next turn ($0)")
            elif pin is not None and inflight:
                for rid in dict.fromkeys(j["run_id"] for j in inflight.values()):
                    PW.write_marker(S.wt / "probe/runs" / rid, getattr(pin, "preset", "") or "", pin)
            if pin is not None and not inflight:
                return pin_out(S, pin, say, "tail")
            st = states_live(S, cache)
            for n in names:   # cap safety: a row whose state cannot be read never gets a session (a fresh state would start at $0 under its top)
                if n not in st and n not in parked:
                    parked.add(n); say(f"tail: row#{idx[n]:02d}: no readable state.json in the work root: no tail session ($0)")
            busy = {j["n"] for j in inflight.values()}
            need = [n for n in names if n not in full and n not in parked and prior.get(n, 0) + started[n] < a.tail_max_sessions
                    and st[n]["spend"] + floor < tops[n] - 1e-9]
            if not need and not inflight:
                break
            if pin is None:
                ready = [n for n in need if n not in busy]
                ready.sort(key=lambda n: (started[n], idx[n]))
                for n in ready[: max(0, workers - len(inflight))]:
                    started[n] += 1
                    k = k_base + started[n]
                    run_id = f"{S.run_prefix[:-1]}t{k}"
                    logp = S.out / f"{run_id}.{tag(n)}.log"
                    b0 = dict(st.get(n, {"spend": 0.0, "score": 33.33}))
                    fu = ex.submit(_run_logged, session_cmd(ar, tops[n], S.root, run_id, [n], 1, ar.effort, False, extra, tag(n), budget=tops[n]),
                                   S.wt, logp)
                    pin_runs.add(run_id)
                    inflight[fu] = {"n": n, "k": k, "run_id": run_id, "log": logp, "t0": time.time(), "b0": b0, "preset": eff_preset(a, a.tail_preset)}
                    say(f"tail: row#{idx[n]:02d} session {prior.get(n, 0) + started[n]} starts ({run_id[len(S.run_prefix) - 1:]}, spent "
                        f"${b0['spend']:.4f}, top ${tops[n]:.4f}; {len(inflight)} in flight; on {inflight[fu]['preset']})")
            if not inflight:
                continue
            done, _ = fwait(list(inflight), timeout=ASYNC_IDLE_S, return_when=FIRST_COMPLETED)
            for fu in done:
                j = inflight.pop(fu); n = j["n"]
                try:
                    rc = fu.result()
                except Exception as e:  # noqa: BLE001  (a runner that raised: the row's numbers are read as for any end)
                    rc = None; say(f"tail: row#{idx[n]:02d}: session runner raised {type(e).__name__}: {e}")
                if pin is None:
                    pin = pin_stop(S, [j["run_id"]], j["t0"], rc, live=[x["run_id"] for x in inflight.values()], preset=j.get("preset"))
                    if pin and inflight:
                        say(f"tail: {pin}; no further session starts, the {len(inflight)} in flight end at their next turn ($0)")
                st2 = states_live(S, cache)
                s0, c0 = j["b0"].get("spend", 0.0), j["b0"].get("score", 33.33)
                s1, c1 = st2.get(n, {"spend": s0})["spend"], st2.get(n, {"score": c0})["score"]
                turns = None
                try:
                    merge_summary(S, j["run_id"]); turns = _session_turns(S, j["run_id"], n)
                except OSError:
                    pass
                note = ""
                if s1 - s0 <= 1e-6:
                    try:
                        reached = "budget reached" in j["log"].read_text(errors="replace")
                    except OSError:
                        reached = False
                    if reached:
                        full.add(n); note = "budget reached before any spend: the row's tail is done"
                    else:
                        dry[n] = dry.get(n, 0) + 1; note = f"no spend ({dry[n]} in a row)"
                        if dry[n] >= ASYNC_MAX_DRY:
                            parked.add(n); note += f"; parked after {ASYNC_MAX_DRY} sessions without spend"
                else:
                    dry[n] = 0
                rec = {"problem": n, "row": idx[n], "run_id": j["run_id"], "preset": j["preset"], "top": round(tops[n], 6), "rc": rc,
                       "start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(j["t0"])), "end": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "seconds": round(time.time() - j["t0"], 1), "spend_before": round(s0, 6), "spend_after": round(s1, 6),
                       "score_before": c0, "score_after": c1, "turns": turns, **({"note": note} if note else {})}
                try:
                    with (S.out / TAIL_LOG).open("a") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                except OSError as e:
                    say(f"tail: row#{idx[n]:02d}: {TAIL_LOG} not written ({type(e).__name__})")
                say(f"tail: row#{idx[n]:02d} session done (rc {rc}): ${s0:.4f} -> ${s1:.4f} of top ${tops[n]:.4f}, {c0:.2f} -> {c1:.2f}, "
                    f"{turns if turns is not None else '?'} turn(s) in {time.time() - j['t0']:.0f} s; {len(inflight)} in flight" + (f"; {note}" if note else ""))
    finally:
        ex.shutdown(wait=True)   # an exception in the scheduler: the sessions in flight still end (their spend is on disk)
    say(f"TAIL DONE: {sum(started.values())} session(s) over {sum(1 for n in names if started[n])} row(s)"
        + (f"; {len(parked)} row(s) parked after sessions without spend" if parked else ""))
    return 1 if parked else 0

if __name__ == "__main__":
    raise SystemExit(main())
