"""The same agent loop driven by the Codex CLI in headless mode (`codex exec --json`, the user's ChatGPT login; first-party software, no
API key), for the closed-model comparison line Codex + GPT Astra (2026-10-09: two new lines, Claude Code + Opus 5.5 and Codex +
GPT Astra, each with its own knowledge graph and trajectory log). Workspace, task prompt, tools and recording are those of
harness/agent_claude_code.py: the instructions go into the workspace's AGENTS.md (Codex reads it), the task into the prompt, and the same two
Lean tool scripts check candidates. Codex runs in its workspace-write sandbox WITHOUT network; writable: the workspace, this run's record
directory, and envs/ (compiles write LRAScratch there). The tools read their settings from the workspace's .lra_env.json because the
sandbox filters the environment. Results are tagged closed-dev-only (model <m>@codex, mode agent-codex) and never enter the bank.

Spend (2026-10-12, OpenRouter off): the plan bills nothing per call, so every session is priced at the
model's LIST prices from Codex's own token counts and added to state.json api_spend, with a per-session record in the run entry and the
$2 budget milestone, as agent.py does. With --budget-usd CAP the session is bounded twice:
  1. time gate: it starts only if spend + RATE x minutes fits under CAP, and its timeout is floor((CAP - spend) / RATE) minutes (RATE =
     --max-usd-per-min, default 2x the worst $/min seen in 115 Codex sessions priced at Sol list prices: $0.079/min);
  2. call gate: Codex writes a rollout file with a token_count event after every model call (in 8,228 past `codex exec` sessions every
     multi-call burst sat at the start of the file, i.e. inherited history; mid-session, calls are written one by one, >= 0.5 s apart). A
     watchdog reads it every 0.25 s and stops the container as soon as spend + TWICE the next call's worst case R (its context uncached +
     16k output, or 1.25x the session's costliest call) would exceed CAP: Codex starts the next call the moment one ends, so one call may
     be in flight when the container stops, and it is charged R; a session starts only if spend + 2R fits. In 646,811 past Codex calls
     0.035% produced more than 16k output tokens and 0.0006% more than 32k; with a $2.85 cap the $0.15 left under the $3 rule covers
     another 15k output tokens.
A session that ends with no usage at all is charged RATE x minutes (flagged)."""
from __future__ import annotations

import argparse, gzip, hashlib, json, math, os, re, shutil, signal, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.agent import Workspace  # noqa: E402
from harness.agent_claude_code import SYSTEM, TOOLS_DIR, task_prompt, with_extras  # noqa: E402
from harness.leantools import HBS, ROWS  # noqa: E402
from probe.verify_candidates import newest_first  # noqa: E402

SAFE = re.compile(r"[^A-Za-z0-9_.-]")
# $ per 1M tokens at the provider's public LIST prices: (uncached input, cached input, output incl. reasoning); same table as agent.py's preset
PRICES = {"gpt-6.1-sol": (2.50, 0.10, 10.0)}
WORST_RATE = 0.0788   # $/min, worst of 115 Codex sessions (cxsol-ab-a + cxline-astra-*) priced at Sol list prices (2026-10-12)
def _gib(s: str) -> float:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kmgt]?)b?", s.strip().lower())
    return float(m.group(1)) * {"": 2**-30, "k": 2**-20, "m": 2**-10, "g": 1, "t": 1024}[m.group(2)] if m else 0.0


SEALED_OFF = ("plugins", "apps", "browser_use", "browser_use_external", "in_app_browser", "computer_use", "memories")   # codex features list (0.162.1)


def list_cost(model: str, u: dict) -> float:
    pi, pc, po = PRICES[model]
    inp, cached = int(u.get("input_tokens") or 0), int(u.get("cached_input_tokens") or 0)
    return ((inp - cached) * pi + cached * pc + int(u.get("output_tokens") or 0) * po) / 1e6


def call_reserve(model: str, ctx_tokens: int, out_tokens: int, sess_call_max: float) -> float:
    """Worst case of the NEXT model call: its whole context uncached (+20k for what the call appends) and out_tokens of output."""
    pi, _pc, po = PRICES[model]
    return max(((ctx_tokens + 20000) * pi + out_tokens * po) / 1e6, 1.25 * sess_call_max)


def session_plan(spend: float, cap: float | None, rate: float, timeout_s: int, opening_ctx: int, model: str, out_tokens: int) -> tuple[bool, int, float]:
    """(start?, timeout in seconds, opening reserve). Without a cap: always start with the plain timeout."""
    if cap is None:
        return True, timeout_s, 0.0
    res = call_reserve(model, opening_ctx, out_tokens, 0.0)
    minutes = min(math.floor((cap - spend) / rate), timeout_s // 60) if rate > 0 else timeout_s // 60
    return (spend + 2 * res <= cap and minutes >= 1), max(0, minutes) * 60, res   # room for the first call and the one in flight at a stop


class Meter:
    """Cumulative list-price cost of one Codex session from its rollout token_count events (pure: fed lines, no I/O)."""
    def __init__(self, model: str, out_tokens: int):
        self.model, self.out_tokens = model, out_tokens
        self.total: dict = {}; self.cost = 0.0; self.call_max = 0.0; self.last_ctx = 0; self.points: list = []   # (t, cumulative cost)

    def feed(self, line: str) -> bool:
        try:
            d = json.loads(line)
        except ValueError:
            return False
        p = d.get("payload") or {}
        if p.get("type") != "token_count" or not p.get("info"):
            return False
        tot, last = p["info"].get("total_token_usage") or {}, p["info"].get("last_token_usage") or {}
        self.total = tot; self.cost = list_cost(self.model, tot)
        self.call_max = max(self.call_max, list_cost(self.model, last)); self.last_ctx = int(last.get("input_tokens") or 0)
        self.points.append((d.get("timestamp"), self.cost))
        return True

    def reserve(self) -> float:
        return call_reserve(self.model, self.last_ctx, self.out_tokens, self.call_max)


def find_rollout(codex_home: Path, thread_id: str | None, cwd: str, t0: float) -> Path | None:
    def mtime(f: Path) -> float:   # another worker may move its rollout between the glob and the stat (sealed runs, 2026-10-12)
        try:
            return f.stat().st_mtime
        except OSError:
            return 0.0
    files = [f for f in (codex_home / "sessions").glob("*/*/*/rollout-*.jsonl") if mtime(f) >= t0 - 5]
    if thread_id:
        for f in files:
            if f.name.endswith(f"{thread_id}.jsonl"):
                return f
    for f in sorted(files, key=mtime, reverse=True):
        try:
            meta = json.loads(f.open().readline()).get("payload") or {}
        except (ValueError, OSError):
            continue
        if meta.get("cwd") == cwd:
            return f
    return None


def best_at(attempts: list, run_id: str, t_iso: str | None, floor: float) -> float:
    sc = [a.get("score") or 0 for a in attempts if a.get("run_id") == run_id and a.get("ok") and (t_iso is None or (a.get("t") or "") <= t_iso[:19] + "Z")]
    return max([floor] + sc)


def codex_prompt(name: str, row: dict, primary: str, ws, args) -> tuple[str, bool]:
    """The task message and whether --heartbeat-first's gate passed (2026-10-13, review finding 7; off by default: the prompt is then
    with_extras(task_prompt(..)) byte for byte). v1 has no card slot and no `axis` in lean_check.py, so the card (cards.HEARTBEAT_FIRST_V1,
    rule (7) priced from the task's reference numbers) goes after the task and before the relay / brief extras, under the same gate as the
    other drivers (cards.gate: H points left >= L points left of the stored best, always before a measured best)."""
    p = task_prompt(name, row, primary, ws, args.turns); on = False
    if getattr(args, "heartbeat_first", False):
        from harness import cards
        on = cards.gate(name, row, ws.state, HBS.get(name), log=lambda s: print(f"{name[:18]:18s} {s}", flush=True))
        if on:
            p += "\n\n" + cards.HEARTBEAT_FIRST_V1
    return with_extras(p, name, ws, args), on


def run_problem(name: str, args, out_dir: Path) -> dict:
    row = ROWS[name]; primary = newest_first(row["version_info"])[0]
    ws = Workspace(ROOT / args.work_root / SAFE.sub("_", name), row, primary, fresh=args.fresh)
    spend0 = float(ws.state.get("api_spend") or 0); best0 = float(ws.state["best"].get("score") or 33.33)
    (ws.root / "AGENTS.md").write_text(SYSTEM.format(tools=TOOLS_DIR) + "\n")
    (ws.root / ".lra_env.json").write_text(json.dumps({"LRA_PROBLEM": name, "LRA_RUN_ID": args.run_id, "LRA_MODEL": args.model, "LRA_WORKSPACE": str(ws.root),
                                                        "LRA_AGENT_TAG": "codex", "LRA_MODE": "agent-codex"}))
    prompt, hbf = codex_prompt(name, row, primary, ws, args)
    priced = args.model in PRICES
    go, timeout_s, res0 = session_plan(spend0, args.budget_usd, args.max_usd_per_min, args.timeout, (len(prompt) + len(SYSTEM)) // 2,
                                       args.model, args.reserve_out_tokens) if priced else (True, args.timeout, 0.0)
    if not go:
        print(f"{name[:18]:18s} budget reached: ${spend0:.3f} + 2 x reserve ${res0:.3f} (or < 1 min at ${args.max_usd_per_min:.3f}/min) > ${args.budget_usd:.2f}; session ends",
              flush=True)
        print(f"{name[:18]:18s} DONE best={best0} checks=0 tool_calls=0 turns=0 out_tok=0 0s", flush=True)
        return {"problem": name, "model": args.model, "best_score": best0, "skipped": "budget"}
    ws.state["runs"].append({"run_id": args.run_id, "model": args.model + "@codex", "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                             **({"heartbeat_first": hbf} if getattr(args, "heartbeat_first", False) else {})}); ws.save()   # A/B audit (2026-10-13)
    cname = f"lra-cx-{SAFE.sub('_', args.run_id)}-{SAFE.sub('_', name)[:40]}-{hashlib.sha1(name.encode()).hexdigest()[:8]}-{os.getpid()}"
    # --sealed (2026-10-12, sealed set #3): no plugins, apps, browser or computer use, memories or prompt history in ~/.codex
    sealed_c = [x for f in SEALED_OFF for x in ("-c", f"features.{f}=false")] + ["-c", 'history.persistence="none"'] if args.sealed else []
    cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "-m", args.model, "-C", str(ws.root), "-s", "workspace-write",
           "-c", f"model_reasoning_effort={args.effort}", *sealed_c, "-c", "sandbox_workspace_write.network_access=false",
           "-c", "sandbox_workspace_write.writable_roots=" + json.dumps([str(out_dir), str(ROOT / "envs")]), prompt]
    env = dict(os.environ); env["PATH"] = f"{Path.home()}/.elan/bin:{env.get('PATH', '')}"
    home = Path.home(); codex_home = Path(os.environ.get("CODEX_HOME") or home / ".codex"); shared_home = codex_home
    if args.sealed:   # 2026-10-12 review: Codex indexes every rollout in CODEX_HOME/sessions into its thread databases (and the user's Codex
        # app indexes ~/.codex/sessions too), so a sealed line keeps its own CODEX_HOME: its sessions, thread state and logs never reach ~/.codex.
        # Only the login is shared, read-only, plus the codex release dir (read-only).
        # Each session is a new container, so it mounts the login as it is at that moment.
        codex_home = Path(args.private_scratch) / "codex_home"; codex_home.mkdir(parents=True, exist_ok=True)
        (codex_home / "auth.json").touch(exist_ok=True)   # mount point for the user's auth.json
    if args.docker:   # the container is the sandbox (Codex's bubblewrap cannot run on the GB10): only these paths exist inside, no host keys
        codex_bin = Path(shutil.which("codex") or home / ".local/bin/codex").resolve()
        vols = ["-v", f"{ROOT}:{ROOT}:ro"]
        env_mode = "ro" if args.private_scratch else "rw"   # with a private scratch, compiles write only there: the shared envs stay read-only
        for w, mode in ((ws.root, "rw"), (out_dir, "rw"), (ROOT / "envs", env_mode)):   # the workspace, this run's records, the env dirs
            vols += ["-v", f"{w}:{w}:{mode}"]
        # env entries symlinked from another checkout (a ladder worktree links the main repo's built envs): mount their targets too
        targets = sorted({str(e.resolve().parent) for e in (ROOT / "envs").iterdir() if e.is_symlink() and e.resolve().exists()} - {str(ROOT / "envs")})
        for t in targets:
            vols += ["-v", f"{t}:{t}:{env_mode}"]
        if args.private_scratch:   # nested binds (docker mounts parents first): inside the container every env's LRAScratch is this line's own
            for e in sorted((ROOT / "envs").iterdir()):
                real = e.resolve()
                if (real.is_dir() and not real.name.endswith(".git-main") and real.name != "mathlib4"   # compile envs only
                        and any((real / f).exists() for f in ("lakefile.lean", "lakefile.toml"))):
                    (real / "LRAScratch").mkdir(exist_ok=True)
                    mine = Path(args.private_scratch) / real.name; mine.mkdir(parents=True, exist_ok=True)
                    vols += ["-v", f"{mine}:{real / 'LRAScratch'}:rw"]
        vols += ["-v", f"{home / '.elan'}:{home / '.elan'}:ro", "-v", f"{codex_home}:{codex_home}:rw"]   # the release dir under ~/.codex
        if args.sealed:   # private CODEX_HOME: the user's login (same file) and the codex release dir (read-only)
            vols += ["-v", f"{shared_home / 'auth.json'}:{codex_home / 'auth.json'}:ro", "-v", f"{shared_home / 'packages'}:{shared_home / 'packages'}:ro"]
        # holds codex and its helper codex-code-mode-host (commands fail without it), so it goes on PATH rather than mounting one binary
        inner = [c for c in cmd if c not in ("-s", "workspace-write")]
        inner = [c for i, c in enumerate(inner) if not c.startswith("sandbox_workspace_write.") and not (c == "-c" and i + 1 < len(inner) and inner[i + 1].startswith("sandbox_workspace_write."))]
        inner.insert(2, "--dangerously-bypass-approvals-and-sandbox")
        dmem = args.docker_memory
        if dmem and args.sealed and _gib(dmem) < 20:   # memgate in the container needs ~16 GB free per compile (2026-10-12 review: 16g left 244 MB)
            dmem = "20g"
        mem = ["--memory", dmem, "--memory-swap", dmem] if dmem else []   # 2026-10-11 OOMs: containers sit outside systemd unit caps
        cmd = ["docker", "run", "--rm", "--name", cname, *mem, "--user", f"{os.getuid()}:{os.getgid()}", "-w", str(ws.root), *vols,
               "-e", "HOME=/tmp", "-e", f"CODEX_HOME={codex_home}", "-e", f"ELAN_HOME={home / '.elan'}",
               *(["-e", "GIT_ALLOW_PROTOCOL=file"] if args.sealed else []),   # sealed: git cannot fetch over the network
               "-e", f"PATH={codex_bin.parent}:{home / '.elan/bin'}:/usr/local/bin:/usr/bin:/bin", args.docker, *inner]
    t0 = time.time(); lines: list = []; thread: dict = {}
    p = subprocess.Popen(cmd, cwd=ws.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
                         start_new_session=True)   # stdin closed: codex exec reads extra input from a non-TTY stdin and waits forever on an open pipe
    def pump():
        for line in p.stdout:
            lines.append(line.rstrip("\n"))
            if '"thread.started"' in line:
                try:
                    thread["id"] = json.loads(line).get("thread_id")
                except ValueError:
                    pass
    errbuf: list = []
    tr = threading.Thread(target=pump, daemon=True); tr.start()
    te = threading.Thread(target=lambda: errbuf.extend(p.stderr), daemon=True); te.start()
    meter = Meter(args.model, args.reserve_out_tokens) if priced else None
    rollout = None; pos = 0; killed = None
    def stop():
        if args.docker:
            subprocess.run(["docker", "kill", cname], capture_output=True)
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:   # a failure in the poll loop must never leave a container unsupervised (2026-10-12 review)
        while p.poll() is None:
            time.sleep(0.25)
            if meter is not None:
                rollout = rollout or find_rollout(codex_home, thread.get("id"), str(ws.root), t0)
                if rollout is not None:
                    with rollout.open() as fh:
                        fh.seek(pos); chunk = fh.read(); pos = fh.tell()
                    for ln in chunk.splitlines():
                        meter.feed(ln)
                if args.budget_usd is not None and meter.points and spend0 + meter.cost + 2 * meter.reserve() > args.budget_usd:
                    killed = "budget"; stop(); break
            if time.time() - t0 > timeout_s:
                killed = "timeout"; stop(); break
    except BaseException:
        stop(); raise
    try:
        p.wait(timeout=60)
    except subprocess.TimeoutExpired:
        stop()
    tr.join(timeout=10); te.join(timeout=10)
    if meter is not None and rollout is not None:   # read the rollout to its end: the last token_count may land after the poll
        with rollout.open() as fh:
            fh.seek(pos)
            for ln in fh.read().splitlines():
                meter.feed(ln)
    if args.sealed:   # sealed: the session's rollout leaves ~/.codex/sessions for this run's record directory (proofs stay in the run)
        rollout = rollout or find_rollout(codex_home, thread.get("id"), str(ws.root), t0)
        if rollout is not None and rollout.exists():
            (out_dir / "rollouts").mkdir(exist_ok=True)
            rollout = Path(shutil.move(str(rollout), str(out_dir / "rollouts" / rollout.name)))
    usage: dict = {}; items: dict = {}; errors = []
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "item.completed":
            k = (d.get("item") or {}).get("type", "?"); items[k] = items.get(k, 0) + 1
        elif d.get("type") == "turn.completed":
            for k, v in (d.get("usage") or {}).items():
                usage[k] = usage.get(k, 0) + (v or 0)
        elif d.get("type") in ("error", "turn.failed"):
            errors.append(str(d)[:200])
    minutes = (time.time() - t0) / 60; flags = []; cost = 0.0; inflight = 0.0
    if priced:
        cost = max(meter.cost, list_cost(args.model, usage) if usage else 0.0)
        if killed:   # the call in flight when the container was stopped may still be billed: charge its worst case
            inflight = meter.reserve() if meter.points else call_reserve(args.model, (len(prompt) + len(SYSTEM)) // 2, args.reserve_out_tokens, 0.0)
            flags.append(f"stopped:{killed}")
        if not meter.points and not usage:
            cost = args.max_usd_per_min * minutes; flags.append("no-usage-seen:charged-rate-x-minutes")
    session_cost = round(cost + inflight, 6)
    st = json.loads(ws.state_path.read_text())   # the tools updated best/attempts on disk during the session
    new_spend = round(spend0 + session_cost, 6)
    if priced:
        st["api_spend"] = new_spend
        for ms in (float(x) for x in args.budget_milestones.split(",") if x.strip()):
            if spend0 < ms <= new_spend and f"{ms:g}" not in st.get("budget_milestones", {}):
                t_cross = next((t for t, c in meter.points if spend0 + c >= ms), None)
                snap = {"spend": new_spend, "best": best_at(st.get("attempts", []), args.run_id, t_cross, best0), "run_id": args.run_id, "turn": None,
                        "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                st.setdefault("budget_milestones", {})[f"{ms:g}"] = snap
                cap_txt = f"cap ${args.budget_usd:.2f}" if args.budget_usd is not None else "no cap"
                print(f"{name[:18]:18s} budget milestone ${ms:g} crossed: spend ${new_spend:.3f}, best {snap['best']} ({cap_txt})", flush=True)
        for r in reversed(st.get("runs", [])):
            if r.get("run_id") == args.run_id:
                r.update({"spend_usd_list": session_cost, "usage": meter.total or usage, "minutes": round(minutes, 1), "flags": flags,
                          "ended": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}); break
    ws.state_path.write_text(json.dumps(st, ensure_ascii=False, indent=1))
    traj_dir = out_dir / "trajectories"; traj_dir.mkdir(exist_ok=True)   # the full event stream is the trajectory
    out = "\n".join(lines); err = "".join(errbuf)[-2000:]
    with gzip.open(traj_dir / (SAFE.sub("_", name) + ".jsonl.gz"), "at") as tf:
        tf.write(json.dumps({"type": "header", "run_id": args.run_id, "problem": name, "model": args.model, "cmd": cmd[:-1] + ["<prompt>"], "prompt": prompt,
                             "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)), "rollout": str(rollout) if rollout else None}, ensure_ascii=False) + "\n")
        tf.write(out + "\n" if out else "")
        if err:
            tf.write(json.dumps({"type": "stderr_tail", "text": err}) + "\n")
        # per-call spend in agent.py's "turn" event shape, so hx_heldout.curve() reads Codex sessions like agent.py ones
        prev = 0.0
        for t, c in (meter.points if priced else []):
            tf.write(json.dumps({"type": "turn", "t": t, "cost": round(c - prev, 6), "price_basis": "list",
                                 "best_so_far": best_at(st.get("attempts", []), args.run_id, t, best0)}) + "\n"); prev = c
        if priced and session_cost > prev + 1e-9:
            tf.write(json.dumps({"type": "turn", "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cost": round(session_cost - prev, 6), "price_basis": "list",
                                 "estimate": flags, "best_so_far": float(st["best"].get("score") or best0)}) + "\n")
        tf.write(json.dumps({"type": "end", "problem": name, "best_score": st["best"].get("score"), "spend_usd_list": session_cost, "flags": flags,
                             "seconds": round(time.time() - t0)}) + "\n")
    summary = {"problem": name, "model": args.model, "best_score": st["best"].get("score"), "checks": sum(1 for a in st["attempts"] if a.get("run_id") == args.run_id),
               "seconds": round(time.time() - t0), "items": items, "usage": usage, "spend_usd_list": session_cost, "flags": flags, "errors": errors[-3:],
               "stderr_tail": err[-300:] if err else ""}
    with (out_dir / "summary.jsonl").open("a") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")
    print(f"{name[:18]:18s} [{args.model}] spend ${session_cost:.3f} list (total ${new_spend:.3f}{', ' + ','.join(flags) if flags else ''})", flush=True)
    print(f"{name[:18]:18s} DONE best={summary['best_score']} checks={summary['checks']} tool_calls={items.get('command_execution', 0)} turns=0 "
          f"out_tok={(meter.total if priced else usage).get('output_tokens')} {summary['seconds']}s {('ERROR ' + errors[-1][:120]) if errors else ''}", flush=True)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--problems", nargs="*", default=None)
    ap.add_argument("--model", default="gpt-6-astra")
    ap.add_argument("--effort", default="high", help="Codex model_reasoning_effort")
    ap.add_argument("--turns", type=int, default=40, help="the tool-turn budget stated in the task (Codex has no hard cap; --timeout bounds the run)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--seed-dir", default=None, help="relay: start each problem from <dir>/<problem>.lean, append <dir>/<problem>.md")
    ap.add_argument("--brief-dir", default=None, help="append <dir>/<problem>.md to the task, as agent.py --brief-dir does (knowledge brief)")
    ap.add_argument("--work-root", required=True, help="per-problem state root of this line, e.g. harness/work_cxline-astra")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--budget-usd", type=float, default=None, help="per-problem cap on LIST-price spend (state.json api_spend); requires a priced --model")
    ap.add_argument("--max-usd-per-min", type=float, default=round(2 * WORST_RATE, 3), help="time gate: the session timeout is (cap - spend) / this rate")
    ap.add_argument("--reserve-out-tokens", type=int, default=16000, help="call gate: output tokens assumed for the next model call")
    ap.add_argument("--budget-milestones", default="2.0", help="spend levels whose crossing is recorded in state.json budget_milestones")
    ap.add_argument("--docker-memory", default=None, help="per-container memory cap, e.g. 24g (docker --memory); memgate inside the container sees it as its cgroup limit")
    ap.add_argument("--docker", default=os.environ.get("LRA_CODEX_DOCKER"),
                    help="run each codex exec in this image (e.g. lra-codex:1, infra/codex/Dockerfile) instead of Codex's own sandbox; default $LRA_CODEX_DOCKER")
    ap.add_argument("--sealed", action="store_true", help="2026-10-12, sealed set #3: requires --docker and --private-scratch; no plugins, apps, "
                    "browser/computer use, memories or prompt history; git network transports off; each rollout moved into this run's records")
    ap.add_argument("--private-scratch", default=None, help="with --docker: mount <dir>/<env> over every env's LRAScratch, so this line's compiles "
                    "write there and its agent never sees another run's compile scratch (nor they its)")
    ap.add_argument("--heartbeat-first", action="store_true", help="2026-10-13: append harness/cards.py's HEARTBEAT_FIRST card (v1 wording: "
                    "HEARTBEAT_FIRST_V1) to the task when the stored best has H points left >= L points left (always before a measured best); "
                    "AGENTS.md (v1 SYSTEM) unchanged; runs[] entry `heartbeat_first`; off until an A/B")
    args = ap.parse_args()
    if args.sealed and not (args.docker and args.private_scratch):
        ap.error("--sealed needs --docker and --private-scratch")
    if args.private_scratch and not args.docker:
        ap.error("--private-scratch needs --docker")
    if args.private_scratch:
        args.private_scratch = str(Path(args.private_scratch).resolve())   # a relative path is not a docker volume source
    if args.budget_usd is not None and args.model not in PRICES:
        ap.error(f"--budget-usd needs list prices for {args.model} (known: {sorted(PRICES)})")
    out_dir = ROOT / "probe/runs" / args.run_id; out_dir.mkdir(parents=True, exist_ok=True)
    names = args.problems or list(ROWS)
    print(f"run {args.run_id}: {len(names)} problems via Codex, model={args.model} effort={args.effort}, work root {args.work_root}"
          + (f", cap ${args.budget_usd:.2f} list (time gate ${args.max_usd_per_min:.3f}/min, call reserve {args.reserve_out_tokens} out tokens)" if args.budget_usd is not None else ""),
          flush=True)
    with ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(lambda n: run_problem(n, args, out_dir), names))
    print("done", flush=True)


if __name__ == "__main__":
    main()
