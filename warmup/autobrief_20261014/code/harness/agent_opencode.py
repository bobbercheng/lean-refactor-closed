"""Same agent harness, driven by opencode (v1.18.35 pinned) over OpenRouter (docs/sonnet_haiku_transfer_plan.md;
2026-10-10). Three roles in configs/opencode/opencode.json: scout (Haiku 5.5, resumed polish),
architect (Sonnet 5.5, fresh start from a facts-not-proofs brief), reviewer (Sonnet 5.5, lever review + batch compile).
Workspace, task prompt, seeds/briefs and summary recording are shared with harness/agent_claude_code.py. Success is judged
from on-disk artifacts only (opencode run mode can exit 0 on an auto-rejected permission), the per-problem spend is metered
against --budget (the OpenRouter sub-key credit limit is the hard cap once provisioned), and the full JSON event stream is
kept as the trajectory (house rule). Results are tagged closed-dev-only and never enter the bank."""
from __future__ import annotations

import argparse, json, os, re, sqlite3, subprocess, sys, time, gzip
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.agent import Workspace  # noqa: E402
from harness.leantools import ROWS  # noqa: E402
from harness.agent_claude_code import task_prompt, with_extras  # noqa: E402
from probe.verify_candidates import newest_first  # noqa: E402

OPENCODE = os.environ.get("OPENCODE_BIN", str(Path.home() / ".opencode/bin/opencode"))
CONFIG_DIR = ROOT / "configs" / "opencode"
MAIN_KEY = Path.home() / ".config/vexorium/openrouter_api_key"
# expected spend per session, used only to decide whether the NEXT session fits in the budget (the db total is the truth)
EST_COST = {"scout": 0.05, "architect": 0.90, "reviewer": 0.90, "sol_scout": 0.55, "sol_architect": 0.90, "ds_scout": 0.10, "ds_architect": 0.15}   # Sol prices = Sonnet's ($2/$10 per M)
DEFAULT_MODEL = {"scout": "openrouter/anthropic/claude-haiku-5.5", "architect": "openrouter/anthropic/claude-sonnet-5.5",
                 "reviewer": "openrouter/anthropic/claude-sonnet-5.5",
                 "sol_scout": "openrouter/openai/gpt-6.1-sol", "sol_architect": "openrouter/openai/gpt-6.1-sol",
                 "ds_scout": "clinepass/cline-pass/deepseek-v4.1-flash", "ds_architect": "clinepass/cline-pass/deepseek-v4.1-flash"}   # 2026-10-10: DeepSeek V4.1 Flash via ClinePass   # 2026-10-10: add GPT-6.1 Sol, $3/problem


def session_cost(db: Path) -> dict:
    """Total cost and tokens of the run's sessions from opencode's own SQLite (research: session table columns)."""
    out = {"cost": 0.0, "tokens_input": 0, "tokens_output": 0, "tokens_reasoning": 0, "tokens_cache_read": 0, "tokens_cache_write": 0, "sessions": 0}
    if not db.exists():
        return out
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        for row in con.execute("SELECT cost, tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write FROM session"):
            out["cost"] += row[0] or 0.0
            for k, v in zip(("tokens_input", "tokens_output", "tokens_reasoning", "tokens_cache_read", "tokens_cache_write"), row[1:]):
                out[k] += v or 0
            out["sessions"] += 1
        con.close()
    except sqlite3.Error:
        pass
    return out


def run_problem(name: str, args, out_dir: Path) -> dict:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    row = ROWS[name]; primary = newest_first(row["version_info"])[0]
    root = ROOT / (args.work_root or "harness/work_oline")
    ws = Workspace(root / safe, row, primary, fresh=args.fresh)
    st = json.loads(ws.state_path.read_text())
    spent = float(st.get("oline_spend") or 0.0)
    if spent + EST_COST[args.role] > args.budget:
        msg = f"budget: ${spent:.2f} spent, ${EST_COST[args.role]:.2f} more would pass ${args.budget:.2f}; session refused"
        print(f"{name[:18]:18s} SKIP {msg}", flush=True)
        (out_dir / "summary.jsonl").open("a").write(json.dumps({"problem": name, "role": args.role, "refused": msg}, ensure_ascii=False) + "\n")
        return {"problem": name, "refused": msg}
    ws.state["runs"].append({"run_id": args.run_id, "model": DEFAULT_MODEL[args.role] + "@opencode", "role": args.role,
                             "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}); ws.save()
    if not (ws.root / ".git").exists():   # opencode resolves the project root by walking up to the nearest git root
        subprocess.run(["git", "init", "-q"], cwd=ws.root, check=True)   # (smoke1: it read the REPO root otherwise)
    prompt = with_extras(task_prompt(name, row, primary, ws, args.turns), name, ws, args)
    kd = Path(args.key_dir) if args.key_dir else None
    model_key = kd / (DEFAULT_MODEL[args.role].replace("/", "_") + ".key") if kd else None
    cands = [kd / f"{safe}.key", model_key, kd / f"{args.role}.key", kd / "default.key"] if kd else []
    key_file = next((f for f in cands if f and f.exists()), MAIN_KEY)
    api_key = key_file.read_text().strip()
    db = out_dir / f"oline-{safe}.db"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OPENCODE", "CLAUDE"))}
    _ck = Path.home() / ".config/vexorium/cline_api_key"   # ClinePass (OpenAI-compatible gateway) for the ds_* roles
    if _ck.exists(): env["CLINE_API_KEY"] = _ck.read_text().strip()
    env.update({"OPENROUTER_API_KEY": api_key, "OPENCODE_CONFIG_DIR": str(CONFIG_DIR), "OPENCODE_DB": str(db),
                "OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_DISABLE_MODELS_FETCH": "1",
                "OPENCODE_MODELS_PATH": str(CONFIG_DIR / "models.json"),
                "LRA_PROBLEM": name, "LRA_RUN_ID": args.run_id, "LRA_MODEL": DEFAULT_MODEL[args.role],
                "LRA_WORKSPACE": str(ws.root), "PATH": f"{env.get('PATH','')}:{Path.home()}/.opencode/bin:{Path.home()}/.elan/bin"})
    # --dir pins the project root to the workspace: telemetry (docs/sol_deep_dive.md) showed all 35 pilot sessions
    # started at the REPO root despite cwd (opencode resolves its own root), letting models wander into other
    # lines' workspaces — haiku even copied a foreign candidate over work_fresh-or. Pinned, everything outside the
    # workspace is 'external' and the config's external_directory: deny keeps it that way.
    prompt = f"WORKSPACE (your only permitted directory; everything else is off-limits): {ws.root}\n\n" + prompt
    cmd = [OPENCODE, "run", "--dir", str(ws.root), "--agent", args.role, "--format", "json", prompt]
    t0 = time.time()
    timed_out = False
    p = subprocess.Popen(cmd, cwd=ws.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, start_new_session=True)
    try:   # opencode hang classes (#38723, #43519, #40747): the wall-clock timeout kills the whole process GROUP
        out, err = p.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(os.getpgid(p.pid), 9)
        out, err = p.communicate()
    traj_dir = out_dir / "trajectories"; traj_dir.mkdir(exist_ok=True)
    with gzip.open(traj_dir / f"{safe}.jsonl.gz", "at") as tf:
        tf.write(json.dumps({"type": "header", "run_id": args.run_id, "problem": name, "role": args.role, "model": DEFAULT_MODEL[args.role],
                             "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)), "timed_out": timed_out}, ensure_ascii=False) + "\n")
        tf.write(out if out.endswith("\n") else out + "\n")
        if err:
            tf.write(json.dumps({"type": "stderr_tail", "text": err[-2000:]}) + "\n")
    cost = session_cost(db)
    st = json.loads(ws.state_path.read_text())
    st["oline_spend"] = round(spent + cost["cost"], 4); ws.state_path.write_text(json.dumps(st, ensure_ascii=False))
    # post-passes (cycle 92): record the session best as a closed-dev-only verified row, then the lexer normalizer
    # (harness/normalize.py — confirmed +0.26 on a line) through the standard checker, exactly like agent.py --normalize
    try:
        if st.get("best", {}).get("proof"):
            import hashlib
            prov = {"kind": "closed-dev-only", "model": DEFAULT_MODEL[args.role], "run_id": args.run_id, "mode": "agent", "driver": "opencode"}
            _b = st["best"]
            (out_dir / "verified.jsonl").open("a").write(json.dumps({
                "problem": name, "sha256": hashlib.sha256(_b["proof"].encode()).hexdigest()[:12], "proof": _b["proof"],
                "tokens": _b.get("tokens"), "heartbeats": _b.get("heartbeats"), "score": _b.get("score"),
                "primary_ok": _b.get("score") is not None, "provenance": prov}, ensure_ascii=False) + "\n")
            from harness.normalize import normalize as _norm
            from harness.leantools import lean_check as _lc
            _nr = _norm(name, _b["proof"])
            if _nr.get("status") == "improved":
                _lc(name, _nr["proof"], st, dict(prov, normalized=_nr.get("applied")), out_dir / "verified.jsonl")
                st = json.loads(ws.state_path.read_text())
                if st.get("best", {}).get("proof"):
                    (ws.root / "best.lean").write_text(st["best"]["proof"].rstrip() + "\n")
                print(f"{name[:18]:18s} normalized: {_nr['before']['tokens']} -> {_nr['after']['tokens']} tokens, "
                      f"score {_nr['before']['score']} -> {_nr['after']['score']}", flush=True)
    except Exception as _e:  # noqa: BLE001
        print(f"{name[:18]:18s} post-pass failed: {type(_e).__name__}: {_e}", flush=True)
    summary = {"problem": name, "role": args.role, "model": DEFAULT_MODEL[args.role], "best_score": st["best"].get("score"),
               "checks": sum(1 for a in st["attempts"] if a.get("run_id") == args.run_id), "seconds": round(time.time() - t0),
               "timed_out": timed_out, "exit": p.returncode, **cost}
    (out_dir / "summary.jsonl").open("a").write(json.dumps(summary, ensure_ascii=False) + "\n")
    print(f"{name[:18]:18s} [{args.role}] best={summary['best_score']} checks={summary['checks']} cost=${cost['cost']:.3f} "
          f"sessions={cost['sessions']} {summary['seconds']}s {'TIMEOUT' if timed_out else ''}{'' if p.returncode == 0 else ' rc=' + str(p.returncode)}", flush=True)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--problems", nargs="*", default=None)
    ap.add_argument("--role", choices=["scout", "architect", "reviewer", "sol_scout", "sol_architect", "ds_scout", "ds_architect"], default="scout")
    ap.add_argument("--turns", type=int, default=40, help="the tool-turn budget stated in the task (opencode's own cap is the agent's steps)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--work-root", default="harness/owork", help="per-problem state root of this line")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--seed-dir", default=None)
    ap.add_argument("--brief-dir", default=None)
    ap.add_argument("--budget", type=float, default=2.84, help="per-problem spend cap in USD (the plan's $3 minus the top-up fee)")
    ap.add_argument("--key-dir", default=None, help="dir of per-problem OpenRouter sub-keys <problem>.key (fallback: the main vexorium key)")
    args = ap.parse_args()
    args.run_id = args.run_id or f"oline-{args.role}-{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir = ROOT / "probe/runs" / args.run_id; out_dir.mkdir(parents=True, exist_ok=True)
    names = args.problems or list(ROWS)
    print(f"run {args.run_id}: {len(names)} problems via opencode, role={args.role}, budget=${args.budget:.2f}/problem", flush=True)
    with ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(lambda n: run_problem(n, args, out_dir), names))
    print("done", flush=True)


if __name__ == "__main__":
    main()
