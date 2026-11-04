#!/usr/bin/env python3
"""Closed-track pipeline check on a SEALED held-out set (2026-10-11: a $3-compliant held-out check, first at a $2 cap,
then decide whether to go up; a $2 warning milestone per problem). One hosted model, the current harness, every
problem in its own work root (so state.json api_spend is that problem's whole spend).

BUDGET LADDER (default rungs $2.00, $2.85): rounds of 40-turn sessions fill EVERY problem up to a rung before any problem may pass it
(breadth-first). Each finished rung writes a MILESTONE report (mean score, spend, per-repo means, score at budget) over all problems,
so the $2 snapshot is complete and uncensored before any money goes past $2. The agent's gate is a hard bound (it reserves each
turn's worst case), so no problem's spend ever crosses the current rung; agent.py also records the moment a problem's spend crosses
$2 (state.json budget_milestones). Resumable: rerunning continues at the next round and rung.

Sets: heldout2 (sealed set #2, 22 rows; Flash cold 1-pass reference 66.45), heldout3 (sealed set #3, frame-matched), abpool (the
frame A/B pool). Run ids start with sealed2- / sealed3- / abpool-, which every mining tool skips. Only scores, spend and the per-turn
cost/best numbers are read, never proof, trajectory text or errors.
    python3 harness/hx_heldout.py --set heldout2 --arm sol [--rungs 2.0,2.85] [--report]
Claude Code (2026-10-12, docs/cc_driver_v2.md §5): --driver claude --claude-prompt v1|v2 --claude-effort E --claude-cache 1h|5m; Phase A runs
one gated session per row: --rungs 2.85 --max-rounds 1 --no-lineage-rule (probe/abpool/run_phase_a.sh). Sealed sets need --claude-sealed and
an own-worktree set (heldout3-cc); Claude batches run one at a time (<= --workers sessions) and spill folders are moved after each batch.
Round 2 (2026-10-12, docs/cc_driver_v2.md §9): after every Claude batch, in-run learning (rule, data/heldout3/SEALED.md 19:35Z:
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
"""
from __future__ import annotations

import argparse, gzip, json, os, pathlib, re, shutil, signal, statistics, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

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
        "warmup-clean": ("data/benchmark_warmup.jsonl", "data/benchmark_heartbeats.jsonl", "wuclean", None)}
# the only paths a "-clean" set's worktree checks out (git sparse-checkout, non-cone patterns)
CLEAN_PATHS = ["/harness/*.py", "/harness/tools/*.py", "/scorer/*.py", "/llm/*.py", "/bank/*.py", "/probe/verify_candidates.py",
               "/data/benchmark_warmup.jsonl", "/data/benchmark_heartbeats.jsonl", "/data/reference_heartbeats_local.json",
               "/envs/manifest.json", "/envs/manifest.py"]
LIST_PRICES = None     # (input, output, ...) $/1M of a list-price agent.py preset, for curve(); set in main
SESSION_FLOOR = 0.30   # no session starts with less left: the first turn's worst case (opening context uncached + 12k output) is ~$0.15-0.27


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
        self.wt = pathlib.Path.home() / (f"source/lra-ab/{self.prefix}-{arm}-hx" if self.clean else f"source/lra-ab/{self.prefix}-hx")
        self.root = f"harness/hwork/{self.prefix}-{arm}"
        self.run_prefix = f"{self.prefix}-hx-{arm}-r"
        self.out = MAIN / f"probe/heldout/{self.prefix}-hx-{arm}"


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
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=MAIN, capture_output=True, text=True).stdout.strip()
    env_src = pathlib.Path(common).parent if common else MAIN
    ign = subprocess.run(["git", "status", "--ignored", "--porcelain", "envs"], cwd=env_src, capture_output=True, text=True).stdout
    for d in [l[3:].rstrip("/") for l in ign.splitlines() if l.startswith("!!")]:
        if not (S.wt / d).exists() and not (S.wt / d).is_symlink():
            (S.wt / d).symlink_to(env_src / d)
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
    """Keyed by the problem name stored IN each state.json: work-dir names are sanitized and differ for some problems (2 of set #2's
    22 on 2026-10-11, which the first version counted as unstarted: 33.33 and $0)."""
    res = {}
    for st in (S.wt / S.root).glob("*/state.json"):
        d = json.loads(st.read_text())
        if d.get("problem") in S.names:
            res[d["problem"]] = {"score": d["best"].get("score") or 33.33, "spend": float(d.get("api_spend") or 0)}
    return res


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


def session_cmd(a, rung: float, root: str, run_id: str, names: list[str], workers: int, effort: str, restructure: bool, extra: list) -> list:
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
    inner = ["python3", "harness/agent.py", "--model-preset", a.preset, "--reasoning-effort", effort, "--turns", "40", "--no-adaptive-turns",
             "--max-tokens", "4000", "--budget-usd", str(rung), "--budget-milestones", "2.0", "--workers", str(workers),
             "--work-root", root, "--run-id", run_id, *(["--from-reference", "--brief", "restructure"] if restructure else []),
             *extra, "--problems", *names]
    return agent_docker(a, run_id, inner) if a.agent_docker else inner


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


def scratch_binds(private_root: str) -> list:
    """Nested binds that give a container its own compile scratch: <private_root>/<env> over every compile env's LRAScratch (docker mounts
    parents first). Compile envs only: a lakefile, not the *.git-main upstream clones or the mathlib4 source checkout."""
    vols = []
    for e in sorted((MAIN / "envs").iterdir()):
        real = e.resolve()
        if (real.is_dir() and not real.name.endswith(".git-main") and real.name != "mathlib4"
                and any((real / f).exists() for f in ("lakefile.lean", "lakefile.toml"))):
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
        hits = untracked(MAIN, "envs")
        for e in sorted((MAIN / "envs").iterdir()):
            real = e.resolve()
            if real.is_dir() and (real / ".git").exists():
                hits += [h for h in untracked(real) if h.name not in ("LRAScratch", ".lake")]
        _STRAYS.extend((h, h.is_dir()) for h in hits)
    m = pathlib.Path(private_root).resolve() / "_mask"; (m / "dir").mkdir(parents=True, exist_ok=True); (m / "file").touch()
    vols = []
    for h, isdir in _STRAYS:
        vols += ["-v", f"{m / ('dir' if isdir else 'file')}:{h}:ro"]
    return vols


def autobrief_start(S: Set, a, say) -> None:
    """--agent-auto-brief: harness/autobrief.py over the rows without a brief yet, CPU only, before any session; in the line's container
    (its private scratch, its view) when --agent-docker. Bounded by --auto-brief-timeout: on expiry the container is stopped and the rows
    without a brief go on without one (agent.py says so per row)."""
    od = f"{S.root}/_autobrief"
    todo = [n for n in S.names if not (S.wt / od / f"{safe(n)}.json").exists()]
    if not todo:
        return
    (S.wt / od).mkdir(parents=True, exist_ok=True)
    inner = ["python3", "-u", "harness/autobrief.py", "--out-dir", od, "--budget", str(a.auto_brief_budget), "--workers", "3",
             "--row-workers", "2", "--problems", *todo]
    rid = f"{S.run_prefix[:-1]}ab"
    cmd = agent_docker(a, rid, inner) if a.agent_docker else inner
    say(f"auto-brief: measuring {len(todo)} seed(s) (budget {a.auto_brief_budget} compiles per row, timeout {a.auto_brief_timeout}s)")
    t0 = time.time()
    with (S.out / "autobrief.log").open("a") as f:
        try:
            subprocess.run(cmd, cwd=S.wt, stdout=f, stderr=subprocess.STDOUT, timeout=a.auto_brief_timeout)
        except subprocess.TimeoutExpired:
            if a.agent_docker:
                subprocess.run(["docker", "stop", f"lra-ag-{re.sub(r'[^A-Za-z0-9_.-]', '_', rid)}-{os.getpid()}"], capture_output=True)
            say("auto-brief: timeout; the remaining rows go on without a brief")
    done = sum((S.wt / od / f"{safe(n)}.json").exists() for n in todo)
    say(f"auto-brief: {done}/{len(todo)} rows measured in {time.time() - t0:.0f}s")


def agent_docker(a, run_id: str, inner: list) -> list:
    """--agent-docker (2026-10-12 launch review: agent.py's shell tool is host bash, so on the host a sealed line could read other lines'
    files and compile scratch): the agent.py batch runs in a container holding only this line's worktree (read-only), its work roots and
    records (read-write), the envs (read-only) with a private compile scratch, the Lean toolchains (read-only) and the preset's one key file
    (read-only, at the container's HOME=/tmp). --init forwards a unit stop to agent.py, so no container outlives its ladder."""
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
    name = f"lra-ag-{re.sub(r'[^A-Za-z0-9_.-]', '_', run_id)}-{os.getpid()}"
    return ["docker", "run", "--rm", "--init", "--name", name, "--memory", a.agent_docker_memory, "--memory-swap", a.agent_docker_memory,
            "--user", f"{os.getuid()}:{os.getgid()}", "-w", str(wt), *vols, "-e", "HOME=/tmp", "-e", f"ELAN_HOME={home / '.elan'}",
            "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", f"PATH={home / '.elan/bin'}:/usr/local/bin:/usr/bin:/bin", a.agent_docker, *inner]


def fresh_round(S: Set, names: list[str], rung: float, run_id: str, effort: str, restructure: bool, extra: list, a,
                workers: int, say) -> None:
    """One session per problem in an EMPTY workspace (2026-10-11: a rescue does not resume from the current checkpoint): its
    state.json holds no proof, notes or variants, only the problem's spend so far, so the agent's hard cap at `rung` covers the main and
    the fresh lineage together. Afterwards the spend carries back, the fresh best replaces the main best only if higher, and the fresh
    workspace is archived (never resumed)."""
    recover_fresh(S, say)   # a fresh lineage an earlier ladder left unmerged is merged first (its spend), never overwritten
    froot = S.wt / f"{S.root}-fresh"
    main = {json.loads(p.read_text()).get("problem"): p for p in (S.wt / S.root).glob("*/state.json")}
    rows = {r["name"]: r for r in S.rows}
    facts = a.driver == "claude" and getattr(a, "claude_fresh_facts", False)
    for n in names:
        d = froot / safe(n); d.mkdir(parents=True, exist_ok=True)
        spend = float(json.loads(main[n].read_text()).get("api_spend") or 0) if n in main else 0.0
        (d / "state.json").write_text(json.dumps({"problem": n, "best": {"score": 33.33, "proof": None, "tokens": rows[n]["proof_length"], "heartbeats": None},
                                                  "attempts": [], "runs": [], "api_spend": spend, "lineage": "fresh"}, ensure_ascii=False, indent=1))
        (d / "notes.md").write_text("# Notes (yours to keep; persisted across runs)\n")
        if facts and n in main:   # --claude-fresh-facts (§11): the main lineage's facts sheet (numbers, failed checks, notes' Failed / Next; no proof)
            try:
                (d / "lineage_facts.md").write_text(lineage_facts(S, main[n]) + "\n")
            except Exception as e:  # noqa: BLE001  (review 2026-10-12: a failed sheet costs the fresh lineage its facts, never the ladder)
                say(f"  lineage facts for {n} failed ({type(e).__name__}: {e}); the fresh lineage starts without them")
    tf = S.wt / S.root / "_run_techniques.json"
    if tf.exists():   # round 2: v2 sessions of a fresh lineage are the same line, so they see its run techniques (built in-run only)
        shutil.copyfile(tf, froot / "_run_techniques.json")
    cmd = session_cmd(a, rung, f"{S.root}-fresh", run_id, names, workers, effort, restructure, extra)
    with (S.out / f"{run_id}.log").open("a") as f:
        subprocess.run(cmd, cwd=S.wt, stdout=f, stderr=subprocess.STDOUT)
    for n in names:
        fs = froot / safe(n) / "state.json"
        if not fs.exists() or n not in main:
            continue
        merge_fresh_state(fs, main[n], run_id, restructure, say)
    froot.rename(S.wt / f"{S.root}-fresh.done-{run_id}")


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


def recover_fresh(S: Set, say) -> int:
    """Round-2 review (2026-10-12): a ladder that died during a fresh lineage (unit stop, OOM, an arm timeout) never merged it, and a restart
    read only the main root, so those sessions' spend (their pre-charges included) was missing from the main ledger and the problem could pass
    its rung. At start-up and before every fresh lineage, a leftover <root>-fresh is merged exactly as after its run, then archived."""
    froot = S.wt / f"{S.root}-fresh"
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
    tag = f"recovered-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}"
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


def curve(S: Set, marks: list[float]) -> dict:
    """Best score reached by cumulative spend <= mark, per problem (numbers from turn events only)."""
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
                    for e in _events(f):
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
    sp = [st[n]["spend"] for n in S.names if n in st]
    ref = (f" (Flash cold 1-pass ref {statistics.mean(F.values()):.2f}; wins {sum(sc[n] > F[n] for n in S.names)}/{len(S.names)})" if F else "")
    say(f"{title} {S.prefix} arm {arm}, rung ${rung:.2f}: mean {statistics.mean(sc.values()):.2f} over {len(S.names)}{ref}")
    by = lambda key: {k: [sc[r['name']] for r in S.rows if str(key(r)) == k] for k in sorted({str(key(r)) for r in S.rows})}
    say("  " + "; ".join(f"{k} n={len(v)} {statistics.mean(v):.2f}" for k, v in {**by(lambda r: r.get('stratum')), **by(lambda r: r['source'])}.items() if v))
    if sp:
        say(f"  spend: total ${sum(sp):.2f}, mean ${statistics.mean(sp):.3f}, MAX ${max(sp):.3f} per problem (rung ${rung:.2f}; past $2: {sum(x >= 2.0 for x in sp)})")
    say("  score at budget: " + " · ".join(f"${m:.2f} {statistics.mean(C[n][m] for n in S.names):.2f}" for m in sorted(next(iter(C.values())))))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="heldout2", choices=sorted(SETS)); ap.add_argument("--arm", required=True)
    ap.add_argument("--preset", default="gpt-6.1-sol"); ap.add_argument("--effort", default="medium")
    ap.add_argument("--rungs", default="2.0,2.85", help="budget ladder: every problem is filled to a rung before any goes past it")
    ap.add_argument("--max-rounds", type=int, default=14); ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--ref", default="HEAD"); ap.add_argument("--report", action="store_true")
    ap.add_argument("--agent-pattern-cards", action="store_true", help="2026-10-13: pass --pattern-cards to agent.py (general, pattern-keyed knowledge from harness/pattern_cards.py; the clean replacement for --brief-dir)")
    ap.add_argument("--agent-auto-brief", action="store_true", help="2026-10-14 (docs/auto_brief_plan.md): before round 1, harness/autobrief.py "
                    "measures every row's seed (CPU only; in the line's container when --agent-docker) into <work root>/_autobrief, and every "
                    "session gets --auto-brief")
    ap.add_argument("--auto-brief-budget", type=int, default=80, help="--agent-auto-brief: single-edit compiles per row")
    ap.add_argument("--auto-brief-timeout", type=int, default=14400, help="--agent-auto-brief: seconds for all rows (then rows go on without)")
    ap.add_argument("--agent-mask-strays", action="store_true", help="2026-10-13: cover untracked files of the envs mount (envs/notes.md, "
                    "probes and scratch inside env checkouts) with empty ones in the agent container (needed on a '-clean' set)")
    ap.add_argument("--brief-dir", default=None, help="facts-only knowledge briefs (knowledge, never proofs), passed to every session")
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
                    "$0.30; 2026-10-13: a Fable session's first call alone is ~$1.5, so a Fable line needs ~$3)")
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
    return ap


def check_args(ap: argparse.ArgumentParser, a) -> None:
    """The option checks of main() (ap.error, exit 2, on a refused combination); harness/selftest_cc.py runs them on the runners' argv."""
    if a.codex_sealed and not a.codex_private_scratch:
        ap.error("--codex-sealed needs --codex-private-scratch")
    if a.driver == "codex" and SETS[a.set][2].startswith("sealed") and not a.codex_sealed:
        ap.error("a sealed set with the Codex driver needs --codex-sealed (its container must not see other runs' compile scratch)")
    if a.driver == "codex" and SETS[a.set][2].startswith("sealed") and not a.set.endswith("-cx"):
        ap.error("the Codex driver on a sealed set needs its own worktree set (e.g. heldout3-cx): its container mounts the worktree")
    if a.set.endswith("-clean") and not (a.driver == "agent" and a.agent_docker and a.agent_private_scratch and a.agent_mask_strays):
        ap.error("a '-clean' set runs agent.py only, with --agent-docker, --agent-private-scratch and --agent-mask-strays (its shell tool must "
                 "see nothing but the whitelist worktree and the envs)")
    if a.set.endswith("-clean") and (a.brief_dir or a.stop_at is not None):
        ap.error("a '-clean' set takes no --brief-dir (theorem-keyed) and no --stop-at (its target is an earlier score of these rows)")
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


def main() -> int:
    ap = build_parser()
    a = ap.parse_args()
    if getattr(a, "session_floor", None) is not None:
        global SESSION_FLOOR
        SESSION_FLOOR = a.session_floor
    check_args(ap, a)
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
    rungs = [float(x) for x in a.rungs.split(",") if x.strip()]
    extra = ["--brief-dir", a.brief_dir] if a.brief_dir else []
    if getattr(a, "agent_pattern_cards", False) and a.driver == "agent":   # 2026-10-13: general pattern cards (harness/pattern_cards.py)
        extra = extra + ["--pattern-cards"]
    if getattr(a, "agent_auto_brief", False) and a.driver == "agent":   # 2026-10-14: seed-measured auto-brief (harness/autobrief.py)
        extra = extra + ["--auto-brief", f"{S.root}/_autobrief"]
    def say(msg: str) -> None:
        line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime())}] {msg}"
        print(line, flush=True); (S.out / "jobs.log").open("a").write(line + "\n")
    if a.report:
        report(S, a.arm, rungs[-1], say); return 0
    setup_worktree(S, subprocess.run(["git", "rev-parse", a.ref], cwd=MAIN, capture_output=True, text=True).stdout.strip(), say)
    if a.driver == "claude":   # round-2 review (2026-10-12): a post-pass left running by a ladder that died (SIGKILL, OOM) is stopped first
        _LINE[0] = str(S.wt / S.root)
        k = _kill_marked(f"LRA_POSTPASS_LINE={_LINE[0]}")
        if k:
            say(f"stopped {k} process(es) of a post-batch step left running by an earlier ladder of this line")
    recover_fresh(S, say)   # round-2 review: a fresh lineage an earlier ladder left unmerged (its spend) goes into the main ledger first
    if getattr(a, "agent_auto_brief", False) and a.driver == "agent":
        autobrief_start(S, a, say)
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
            todo = focus([n for n in S.names if st.get(n, {"spend": 0.0})["spend"] + SESSION_FLOOR < rung], st, a)
            if not todo:
                break
            if r >= a.max_rounds:
                say(f"max rounds ({a.max_rounds}) reached on rung ${rung:.2f}; stopping"); report(S, a.arm, rung, say); return 1
            r += 1
            score = lambda n: st.get(n, {"score": 33.33})["score"]
            fresh = [n for n in todo if wants_fresh(n, score(n))] if a.lineage_rule else []
            resume = [n for n in todo if n not in fresh]
            say(f"round {r} (rung ${rung:.2f}): {len(resume)} resume, {len(fresh)} fresh restart (spent so far ${sum(v['spend'] for v in st.values()):.2f})")
            jobs = []
            if resume:
                run_id = f"{S.run_prefix}{r}"
                cmd = session_cmd(a, rung, S.root, run_id, resume, a.workers, a.effort, False, extra)
                def run_resume(cmd=cmd, run_id=run_id):
                    with (S.out / f"{run_id}.log").open("a") as f:
                        subprocess.run(cmd, cwd=S.wt, stdout=f, stderr=subprocess.STDOUT)
                jobs.append(run_resume)
            if fresh:
                fid = f"{S.run_prefix[:-1]}f{r}"
                jobs.append(lambda fid=fid: fresh_round(S, fresh, rung, fid, a.effort, False, extra, a, max(1, min(a.workers, len(fresh))), say))
            if a.driver in ("codex", "claude"):   # one batch at a time: <= 3 containers (codex); <= --workers Claude sessions and host
                for j in jobs:                    # compile streams on the shared subscription (claude, 2026-10-12 review)
                    j()
            else:
                with ThreadPoolExecutor(len(jobs)) as ex:
                    list(ex.map(lambda j: j(), jobs))
            if a.driver == "claude" and S.prefix.startswith("sealed"):
                cc_spill(S, say)
            if a.driver == "claude":   # round 2: [polish], ledgers and run techniques before the next batch reads them
                cc_after_batch(S, a, r, todo, say)
            st2 = states(S)
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
            cands = [n for n in S.names if nxt - st.get(n, {"spend": 0.0})["spend"] >= SESSION_FLOOR]
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
                fresh_round(S, pick, nxt, f"{S.run_prefix[:-1]}f{r}", a.rescue_effort, True, extra, a,
                            max(1, min(a.workers, len(pick))) if a.driver == "claude" else len(pick), say)   # claude: <= --workers sessions
                if a.driver == "claude" and S.prefix.startswith("sealed"):
                    cc_spill(S, say)
                if a.driver == "claude":
                    cc_after_batch(S, a, r, pick, say)
                report(S, a.arm, rung, say, title="AFTER RESCUE")
            (S.out / "rescue.done").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    say("HELDOUT DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
