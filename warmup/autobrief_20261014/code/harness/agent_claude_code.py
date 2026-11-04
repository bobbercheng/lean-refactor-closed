"""Same agent harness, driven by Claude Code in headless mode (uses the Claude
Code subscription; first-party software, no API key). Workspace, system prompt,
tool semantics and recording are the same as harness/agent.py: Read/Write for
the workspace files, Bash restricted to the two Lean tool scripts. Results are
tagged closed-dev-only and never enter the submittable bank.

Driver v2 (docs/cc_driver_v2.md; 2026-10-12: the subscription is the closed-final engine, list-metered with a hard per-problem gate),
every part behind a flag so a plain invocation stays byte-identical (prompt, flags, env; harness/selftest_cc.py checks it):
  --budget-usd R  (any prompt) live list-price meter and gate (harness/cc_meter.py) on --include-partial-messages; claude's whole process
                  tree (the detached Bash commands and their compiles included: kill_tree) is killed at the gate, the timeout or a SIGTERM;
                  ledger in state.json (api_spend pre-charged with the whole gate at the start and replaced by the charge at the end,
                  runs[] entry, budget_milestones + workspace snapshots) and per-call trajectory `turn` events; backstops --max-budget-usd
                  and CLAUDE_CODE_MAX_OUTPUT_TOKENS=32000; no non-streaming fallback, no fast mode
  --prompt v2     prompt v2 (harness/prompt_v2.py), Read/Edit/Write/Bash with dontAsk and exact per-script rules, the v2 tool behaviour
                  (LRA_CHECK_V2=1, harness/tools/_lra_v2.py), --from-reference, --repo-cards
                  round 2 (2026-10-12, docs/cc_driver_v2.md §9): normalize_check.py allowed; the HEARTBEAT MAP at session start
                  (--no-heartbeat-map), RUN TECHNIQUES from <work root>/_run_techniques.json (--no-run-techniques), escalation of a resume
                  whose previous session gained < 0.5 to a from-reference session with a facts sheet (--no-escalate); every v2 runs[] entry
                  carries best_before / best_after
  --cache-ttl 5m  FORCE_PROMPT_CACHING_5M=1
  --review        (v2; 2026-10-12, docs/cc_driver_v2.md §11) the REVIEWER: per problem one short fresh-context session that
                  writes no proof file (tools: Read on the workspace only; no Bash, Edit or Write; the workspace is not rewritten either), gated at
                  --review-budget ($0.30, capped by what the rung leaves), metered and charged to the problem's ledger like any session (runs[]
                  entry kind 'review'); its answer, linted (no Lean block over 2 lines, no optimality claim), is saved as <ws>/review.md with
                  the best sha it reviewed, and the NEXT executor session of that best shows it as REVIEW (fresh eyes) and does not escalate;
                  every v2 executor session moves review.md out of its workspace (into its run's reviews/), so it reaches a session by prompt only
  --ceiling       a ceiling measurement (never a submission): the per-problem cap is the --budget-usd rung, not $2.85
  --exemplars     (v2; 2026-10-13, docs/cc_driver_v2.md §13) the executor prompt shows <work root>/_exemplars/<ws>.md (harness/exemplars.py,
                  built by hx --claude-exemplars at ladder start and after every batch; outside the workspace, Read denied: it reaches a session
                  through its prompt only) as WHAT WORKED ON THE STRONGEST ROWS after the REVIEW block, with this best's hot families from the
                  profile cached now, while the best is below the file's target and never in a from-reference session; the runs[] entry
                  records `exemplars_seen` (the sha the file was built for) and `exemplars_stale` (built for an earlier best)
  --heartbeat-first (v2 executor; 2026-10-13) harness/cards.py's HEARTBEAT_FIRST card with the technique cards and the heartbeat-aware
                  rewrites (cards.HB_REWRITES) of the cards, repo card, restructure brief and lever review while the stored best's H points
                  left >= its L points left (always before a measured best; section 'heartbeat_first', runs[] entry `heartbeat_first`); the
                  system prompt's TOKEN COUNTING closer line and closed-lessons habit 2 axis-conditional for the whole run, so the A/B unit is
                  the flag, not the gate. v1 refuses it (its prompt has no card slot; harness/agent_codex.py, which runs v1's SYSTEM and
                  task_prompt, has its own --heartbeat-first that appends cards.HEARTBEAT_FIRST_V1 to the task)
  --failed-moves  (v2 executor; 2026-10-13, docs/opus_pass2_deep_dive.md §3: repeats of an already-seen error rose to 56% of failing checks
                  by pass 5) the REFUTED MOVES block (harness/cc_levers.failed_moves_block) after the inline files, section 'failed_moves',
                  runs[] entry `failed_moves` (rows shown); LRA_FAILED_MOVES=1 (env and .lra_env.json) asks the check path to record each
                  failed check's move (cc_levers.attach_move); without that hook the block lists only UNKNOWN NAMES (text-less failures of the
                  unknown-name class since the last new best; review 2026-10-13: a generic error head merged unrelated edits)"""
from __future__ import annotations

import argparse, json, os, queue, re, signal, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import cc_meter  # noqa: E402
from harness.agent import Workspace  # noqa: E402
from harness.leantools import ROWS, HBS  # noqa: E402
from probe.verify_candidates import newest_first  # noqa: E402

TOOLS_DIR = ROOT / "harness/tools"
SYSTEM = """You are a Lean 4 proof engineer working in a small workspace. Goal: produce a proof of the SAME theorem that scores higher than the reference on
  score = mean(length_reduction%, heartbeat_reduction%, compatibility%),
where length = token count of the proof body (every bracket/operator is a token, dotted names are one token, comments don't count), heartbeats = elaboration cost, compatibility = fraction of listed toolchains on which it compiles unchanged.

Files: original.lean (reference declaration, compiles), context.lean (imports/header or the surrounding file prefix; large, read ranges), candidate.lean (your attempt), notes.md (your durable notes, persisted across runs).
Tools (use Bash exactly like this, from the workspace directory):
  python3 {tools}/lean_check.py            -> compiles candidate.lean in the real project environment; returns JSON with ok, errors (line:col relative to the declaration), linter_hints, heartbeats, tokens, predicted score, and compatibility when it improves
  python3 {tools}/lean_run.py snippet.lean -> runs a scratch snippet after the problem's imports/context and prints compiler messages; use it for `#check`, `example : goal := by exact?`, `simp?`; `sorry` IS allowed here
  grep/rg/git log/git show/ls/cat/head/sed -n (read-only) over the project sources and git history listed in the task message — e.g. `git -C <clone> log -p --follow -- <file> | head -400` to see how upstream later simplified this very proof

Workflow: read original.lean, then improve INCREMENTALLY: change one thing (delete a step, inline a `have`, replace one tactic), write candidate.lean (statement byte-for-byte identical, then `:=` and your proof), run lean_check, keep going from whatever compiles. The harness remembers the best compiling candidate; a failed check costs nothing but a turn, so check early and often. Do NOT rewrite the whole proof in one go unless it is short. linter_hints (tactics that do nothing, unused simp args) are free deletions — do those first. Never put sorry/admit/axiom/native_decide in candidate.lean; never add auxiliary declarations, `open`, or `set_option` outside the proof. Heartbeats matter as much as tokens: replacing simp/simp_all/aesop/omega/nlinarith with targeted `simp only [...]`, `rw`, or `exact` usually gives the biggest gains. Before you stop, write notes.md (what worked, what failed, confirmed lemma names, next idea)."""


def task_prompt(name: str, row: dict, primary: str, ws, turns: int) -> str:
    """The task message (shared with harness/agent_codex.py)."""
    src_note = (f"Project sources (read-only) for grep/git: {ROOT / 'envs' / (row['source'] + '-' + primary)} ; the problem's file is {row['file_path']} ; full git history incl. newer commits: {ROOT / 'envs' / (row['source'] + '.git-main')}. "
                if row['source'] != 'putnambench' else f"Mathlib sources (read-only) for grep: {ROOT / 'envs' / ('mathlib-' + primary) / 'Mathlib'}. ")
    return (f"Problem `{name}` ({row['source']}). Reference: {row['proof_length']} tokens, {HBS.get(name)} heartbeats. Toolchains: {', '.join(newest_first(row['version_info']))}. " + src_note +
            f"You have about {turns} tool turns.\n\n" + ws.digest() + ("\n\nStart by reading original.lean." if not ws.state["attempts"] else "\n\nContinue from candidate.lean (your best so far); read notes.md if useful."))


def with_extras(prompt: str, name: str, ws, args) -> str:
    """Relay seed and strategy brief (docs/break_90_panel.md items 3-4, 2026-10-10), shared with harness/agent_codex.py.
    --seed-dir D: D/<problem>.lean (the union best) replaces candidate.lean and D/<problem>.md (a cross-line digest) is appended;
    --brief-dir D: D/<problem>.md (a strategy brief and a blind target) is appended."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    sd = getattr(args, "seed_dir", None)
    if sd and (ROOT / sd / f"{safe}.lean").exists():
        (ws.root / "candidate.lean").write_text((ROOT / sd / f"{safe}.lean").read_text())
        dg = ROOT / sd / f"{safe}.md"
        prompt += ("\n\nRELAY: candidate.lean now holds the CURRENT UNION BEST for this problem, the best compiling proof any line has found "
                   "(possibly another line's; details below). Your own best is kept unless you beat it. Start from candidate.lean, not from "
                   "your notes' proof. Compile several alternatives per call with "
                   f"`python3 {TOOLS_DIR}/lean_check_variants.py v1.lean v2.lean ...` (each scored and recorded like lean_check), and make "
                   "at least 8 checks before you stop.\n\n" + (dg.read_text() if dg.exists() else ""))
    bd = getattr(args, "brief_dir", None)
    if bd and (ROOT / bd / f"{safe}.md").exists():
        prompt += "\n\n" + (ROOT / bd / f"{safe}.md").read_text()
    return prompt

# ---- driver v2 (docs/cc_driver_v2.md; 2026-10-12) ------------------------------------------------------------------------
SEALED_FIND = ["Bash(find * -delete*)", "Bash(find * -exec*)", "Bash(find * -ok*)", "Bash(find * -fprint*)"]
V2_TOOLS = ("lean_check.py", "lean_check_variants.py", "lean_run.py", "lean_mine.py", "goal_map.py", "skeleton_check.py", "heartbeat_profile.py",
            "lemma_search_cli.py", "tok_count.py", "normalize_check.py", "variants.py")   # + variants.py (G0b smoke: shell loops are refused)   # round 2: + the normalizer
V2_SHELL = ("grep", "rg", "ls", "cat", "head", "tail", "sed -n", "wc", "cp", "diff")   # read-only shell, plus cp for variant files
# 2026-10-12 warm-up review: Bash calls > 120 s were backgrounded (a compile is up to 15 min); 25% of Bash calls were permission denials
V2_ENV = {"BASH_DEFAULT_TIMEOUT_MS": "900000", "BASH_MAX_TIMEOUT_MS": "1800000", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
          "LRA_AGENT_TAG": "claude-code", "LRA_MODE": "agent-cc-v2", "LRA_CHECK_V2": "1"}
SNAP_FILES = ("candidate.lean", "best.lean", "notes.md")


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def gate_cap(args) -> float:
    """The per-problem cap of a gated run: an explicit --gate-cap, else the --budget-usd rung itself in a --ceiling measurement, else
    cc_meter.CAP ($2.85, the closed-track gate)."""
    if getattr(args, "gate_cap", None) is not None:
        return args.gate_cap
    return args.budget_usd if getattr(args, "ceiling", False) else cc_meter.CAP


class ReviewView:
    """--review (docs/cc_driver_v2.md §11): a problem's workspace without Workspace(), which would rewrite candidate.lean, best.lean and the
    context files; the reviewer writes no proof file. state.json is read as it is (None when missing or torn) and save() writes it atomically
    (no tool runs during a review)."""

    def __init__(self, root: Path):
        self.root = root; self.state_path = root / "state.json"
        try:
            self.state = json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            self.state = None

    def save(self) -> None:
        from harness.inrun import write_state
        write_state(self.state_path, self.state)


def review_text(out: str, result: dict | None) -> tuple[str, bool]:
    """The reviewer's answer: the result event's text, else (a session stopped by its gate or without a result) the complete text blocks of the
    last assistant message, flagged partial. ("", ...) when there is none, and for a session that ended in an error (never saved as a review)."""
    if result is not None:
        return ("", False) if result.get("is_error") else (str(result.get("result") or ""), False)
    blocks: dict = {}; last = None
    for line in out.splitlines():
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        m = d.get("message") or {}
        if d.get("type") == "assistant" and isinstance(m.get("content"), list) and not d.get("isApiErrorMessage"):
            for c in m["content"]:
                if c.get("type") == "text" and str(c.get("text") or "").strip():
                    b = blocks.setdefault(m.get("id"), [])
                    if not b or b[-1] != c["text"]:
                        b.append(c["text"])
                    last = m.get("id")
    return ("\n".join(blocks[last]), True) if last is not None else ("", True)


def _rules(tool: str, p) -> list[str]:
    """Permission rule(s) for everything under p: `//abs` is an absolute path in Claude Code rules; the symlink target too (ladder worktrees
    link envs/ from the main checkout)."""
    p = Path(p); ps = [p] + ([p.resolve()] if p.resolve() != p else [])
    return [f"{tool}(/{q}/**)" for q in ps]


def v2_permissions(ws_root: Path, row: dict, primary: str, upstream_history: bool, sealed: bool) -> tuple[list, list, list]:
    """(--allowedTools, --disallowedTools, --add-dir) of prompt v2 (spec §4): Read/Edit/Write scoped to the workspace (Read also on the
    read-only source trees), exact per-script Bash rules for the advertised tools (no tools/* glob), read-only shell, `git -C <clone> log|show`
    only; deny Read of bank/, probe/ and every LRAScratch; --add-dir for the source trees only, never an env root (env roots hold every run's
    compile scratch). Permission semantics are confirmed by the paid smoke (G0b), not by the fake-claude selftest."""
    from harness.prompt_v2 import source_trees, git_main
    trees = [t for t in source_trees(row, primary) if t.exists()]
    gm = git_main(row); git_ok = upstream_history and row["source"] != "putnambench" and gm.exists()
    allow = [*_rules("Read", ws_root), *_rules("Edit", ws_root), *_rules("Write", ws_root), *[r for t in trees for r in _rules("Read", t)],
             *[f"Bash(python3 {TOOLS_DIR}/{t}*)" for t in V2_TOOLS], *[f"Bash({c}*)" for c in V2_SHELL],
             *([f"Bash(git -C {gm} log*)", f"Bash(git -C {gm} show*)"] if git_ok else [])]
    envs = ROOT / "envs"
    roots = [envs] + (sorted({e.resolve().parent for e in envs.iterdir() if e.is_symlink() and e.resolve().exists()} - {envs}) if envs.is_dir() else [])
    from harness.exemplars import XDIR   # §13 review 2026-10-13: the exemplars reach a session through its prompt only
    deny = [*_rules("Read", ROOT / "bank"), *_rules("Read", ROOT / "probe"), *[f"Read(/{r}/**/LRAScratch*/**)" for r in roots],
            *_rules("Read", Path(ws_root).parent / XDIR), *(SEALED_FIND if sealed else [])]
    return allow, deny, [str(t) for t in trees] + ([str(gm)] if git_ok else [])


def build_cmd_env(name: str, row: dict, primary: str, ws, prompt: str, args, gate: float | None = None) -> tuple[list, dict]:
    """claude argv and environment. v1 without --budget-usd is byte-identical to the pre-v2 driver (harness/selftest_cc.py v1_identity runs
    both against a recording fake claude). The gate (--budget-usd, any prompt) adds --include-partial-messages, --max-budget-usd G (the CLI's
    own backstop; it injects a model-visible "USD budget" line, so every arm of an A/B carries it), CLAUDE_CODE_MAX_OUTPUT_TOKENS (32000:
    one call's output <= $0.64), CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK and CLAUDE_CODE_DISABLE_FAST_MODE (every call metered live at the
    list price); --cache-ttl 5m sets FORCE_PROMPT_CACHING_5M; --prompt v2 swaps tools, permissions and the env."""
    v2 = getattr(args, "prompt", "v1") == "v2"
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    env.update({"LRA_PROBLEM": name, "LRA_RUN_ID": args.run_id, "LRA_MODEL": args.model, "LRA_WORKSPACE": str(ws.root), "PATH": f"{Path.home()}/.elan/bin:{env.get('PATH','')}"})
    if not v2:
        git_c = ["Bash(git -C * log*)", "Bash(git -C * show*)"] if args.sealed else ["Bash(git -C *)"]
        cmd = ["claude", "-p", prompt, "--model", args.model, "--system-prompt", SYSTEM.format(tools=TOOLS_DIR), "--output-format", "stream-json", "--verbose",   # every event (assistant/user/tool) streams out: that is the trajectory
               *(["--max-turns", str(args.turns)] if args.max_turns_flag else []), "--tools", "Read,Write,Bash", "--allowedTools", "Read", "Write", f"Bash(python3 {TOOLS_DIR}/*)", "Bash(grep*)", "Bash(rg*)", "Bash(git log*)", "Bash(git show*)", *git_c, "Bash(ls*)", "Bash(cat*)", "Bash(head*)", "Bash(tail*)", "Bash(sed -n*)", "Bash(wc*)", "Bash(find*)",
               "--permission-mode", "acceptEdits", *(["--effort", args.effort] if args.effort else [])]
    elif getattr(args, "review", False):   # the reviewer (§11): Read on the workspace only (no Bash, Edit or Write; no --add-dir), the v2 denies
        from harness.prompt_v2 import REVIEW_SYSTEM
        _allow, deny, _dirs = v2_permissions(ws.root, row, primary, False, args.sealed)
        cmd = ["claude", "-p", prompt, "--model", args.model, "--system-prompt", REVIEW_SYSTEM, "--output-format", "stream-json", "--verbose",
               *(["--max-turns", str(args.turns)] if args.max_turns_flag else []), "--tools", "Read", "--allowedTools", *_rules("Read", ws.root),
               "--disallowedTools", *deny, "--permission-mode", "dontAsk", *(["--effort", args.effort] if args.effort else [])]
        env.update({"LRA_AGENT_TAG": V2_ENV["LRA_AGENT_TAG"], "LRA_MODE": "agent-cc-v2-review"})
    else:
        from harness.prompt_v2 import system_v2
        allow, deny, add_dirs = v2_permissions(ws.root, row, primary, args.upstream_history, args.sealed)
        cmd = ["claude", "-p", prompt, "--model", args.model, "--system-prompt", system_v2(args.upstream_history, getattr(args, "heartbeat_first", False)), "--output-format", "stream-json", "--verbose",
               *(["--max-turns", str(args.turns)] if args.max_turns_flag else []), "--tools", "Read,Edit,Write,Bash", "--allowedTools", *allow,
               "--disallowedTools", *deny, *(["--add-dir", *add_dirs] if add_dirs else []), "--permission-mode", "dontAsk",
               *(["--effort", args.effort] if args.effort else [])]
        env.update(V2_ENV)
        if getattr(args, "failed_moves", False):   # 2026-10-13: tells the v2 check path to record each failed check's move (off: env unchanged)
            env["LRA_FAILED_MOVES"] = "1"
    if args.sealed:
        # Sealed-set hardening (2026-10-12, set #3 Opus line; pre-launch review): no transcript under ~/.claude/projects (folders there are
        # named after the problem), no MCP servers or claude.ai connectors (the warm-up line never called one in 2,717 tool calls), no user
        # settings, hooks or auto-memory (pin --effort to keep the user setting's effort), read-only git, no deleting/exec'ing find, and only
        # the subscription (no API-key or Bedrock/Vertex env). Claude and its Lean tool children run in their own process group, killed whole
        # on timeout. v2 carries the find denies in its one --disallowedTools list.
        cmd += ["--no-session-persistence", "--strict-mcp-config", "--setting-sources", "project,local", *([] if v2 else ["--disallowedTools", *SEALED_FIND])]
        for k in [k for k in env if k.startswith(("ANTHROPIC_", "AWS_BEARER_TOKEN_BEDROCK", "CLOUD_ML_", "VERTEX_"))]:
            env.pop(k)
        env.update({"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "ENABLE_CLAUDEAI_MCP_SERVERS": "false"})
    if gate is not None:
        cmd += ["--include-partial-messages", "--max-budget-usd", f"{gate:.4f}"]
        # 2026-10-12 review (CLI 2.1.296): a stream error retries the request NON-streaming, which emits no message_start or deltas, so
        # rules (a)/(b) never see it; fast mode is billed at a multiple of the list price the meter uses. Both off in every gated session.
        env.update({"CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK": "1", "CLAUDE_CODE_DISABLE_FAST_MODE": "1"})
    mot = getattr(args, "max_output_tokens", None) or (32000 if gate is not None else None)
    if mot:
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(mot)
    if getattr(args, "cache_ttl", "1h") == "5m":
        env["FORCE_PROMPT_CACHING_5M"] = "1"   # survives the CLAUDE* filter above (the subscription default is 1 h)
    return cmd, env


def _read_state(ws) -> dict:
    """state.json without the lock (the meter loop must never wait on a compile): a v1 tool rewrites it whole, so retry a torn read."""
    for _ in range(10):
        try:
            return json.loads(ws.state_path.read_text())
        except (OSError, ValueError):
            time.sleep(0.05)
    return {}


def best_at(attempts: list, run_id: str, t_iso: str, floor: float) -> float:
    sc = [a.get("score") or 0 for a in attempts if a.get("run_id") == run_id and a.get("ok") and (a.get("t") or "") <= t_iso[:19] + "Z"]
    return max([floor] + sc)


def snapshot(ws, ms: float, rec: dict) -> str:
    """Budget-milestone fork point for Phase B (spec §2): candidate.lean, best.lean, notes.md and state.json (its api_spend set to the spend at
    the crossing, plus the record) into <ws>/snapshots/<ms>/."""
    d = ws.root / "snapshots" / f"{ms:g}"; d.mkdir(parents=True, exist_ok=True)
    for f in SNAP_FILES:
        if (ws.root / f).exists():
            (d / f).write_bytes((ws.root / f).read_bytes())
    st = _read_state(ws)
    if st:
        st["api_spend"] = rec["spend"]; st["snapshot"] = rec
        for r in st.get("runs", []):   # the live session's pre-charge marker: a fork resumes from the spend at the crossing, not "driver-died"
            if r.pop("pending", None):
                r["forked_live"] = rec["t"]
        (d / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1))
    return str(d.relative_to(ws.root))


# ---- whole-tree kill (2026-10-12 review): CLI 2.1.296 spawns every Bash command with child_process.spawn({detached: true}), i.e. in its
# OWN session, and the Lean compiles below it run in yet another (scorer/memgate.py start_new_session). killpg(claude) therefore never
# reached a running lean_check, which outlived the gate kill and rewrote state.json from its stale copy AFTER the ledger (api_spend and the
# runs entry rolled back). The kill now freezes claude, collects its whole tree, and also sweeps every process that left the tree: the
# sessions seen below claude while it ran, and any process whose environment carries the session's LRA_WORKSPACE (inherited by every tool
# and compile; it survives reparenting). Never the driver, its session, or the driver's other children (another worker's claude).
_SHUTDOWN = threading.Event(); _SIGNUM = [0]   # SIGTERM/SIGINT/SIGHUP of a gated run: every live session is killed and charged (main())


def _proc_table() -> dict:
    """pid -> (ppid, pgid, sid) of every visible process (Linux /proc; {} elsewhere)."""
    t = {}
    try:
        names = os.listdir("/proc")
    except OSError:
        return t
    for d in names:
        if d.isdigit():
            try:
                with open(f"/proc/{d}/stat", "rb") as f:
                    s = f.read().decode("latin1")
                x = s[s.rindex(")") + 2:].split()
                t[int(d)] = (int(x[1]), int(x[2]), int(x[3]))
            except (OSError, ValueError, IndexError):
                pass
    return t


def _descendants(pid: int, t: dict) -> set:
    kids: dict = {}
    for c, (pp, _g, _s) in t.items():
        kids.setdefault(pp, []).append(c)
    out, todo = set(), [pid]
    while todo:
        for c in kids.get(todo.pop(), []):
            if c not in out:
                out.add(c); todo.append(c)
    return out


def _marked(pid: int, marker: bytes) -> bool:
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            return marker in f.read().split(b"\0")
    except OSError:
        return False


def track_sids(pid: int, seen: set) -> None:
    """Add the session ids of everything below pid (the detached Bash commands, the compiles) to seen."""
    t = _proc_table(); me = os.getsid(0)
    seen |= {t[c][2] for c in _descendants(pid, t)} - {me, 0, 1}


def kill_tree(pid: int | None, marker: str, seen: set) -> int:
    """SIGKILL claude (pid, None when it is already reaped), its whole tree and every process that left it (session id in `seen`, or the
    environment entry `marker`). Three rounds, so a compile spawned while the tree was collected goes too. Returns the processes signalled."""
    me, my_sid, mk, n = os.getpid(), os.getsid(0), marker.encode(), 0
    if pid is not None:
        try:
            os.killpg(pid, signal.SIGSTOP)   # freeze claude's group first: no new Bash command starts while the tree is collected
        except (ProcessLookupError, PermissionError):
            pass
    for rnd in range(3):
        t = _proc_table()
        tree = _descendants(pid, t) if pid is not None and pid in t else set()
        seen |= {t[c][2] for c in tree} - {my_sid, 0, 1}
        spare = (_descendants(me, t) - tree - {pid}) | {me}   # the driver's other children: another worker's session, lemma-search compiles
        hit = {c for c, (_pp, _g, sid) in t.items() if c > 1 and c not in spare and sid != my_sid
               and (c in tree or c == pid or sid in seen or _marked(c, mk))}
        for c in hit:
            try:
                os.kill(c, signal.SIGKILL); n += 1
            except (ProcessLookupError, PermissionError):
                pass
        if pid is not None and rnd == 0:
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        if not hit:
            break
        time.sleep(0.1)
    return n


def stream_session(cmd: list, ws, env: dict, timeout: float, meter, on_close=lambda: None, log=lambda m: None) -> tuple[str, str, str | None]:
    """Run claude with the live meter: every stdout line is fed with its receipt time; the first gate verdict, the timeout or a shutdown
    signal (_SHUTDOWN) kills claude's whole tree (kill_tree: the detached Bash commands and their compiles too). Returns (stdout, stderr
    tail, kill reason or None). Every wait is bounded."""
    p = subprocess.Popen(cmd, cwd=ws.root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         errors="replace", start_new_session=True)
    q: queue.Queue = queue.Queue(); errbuf: list = []; sids: set = set(); marker = f"LRA_WORKSPACE={env.get('LRA_WORKSPACE', ws.root)}"

    def pump():
        try:
            for line in p.stdout:
                q.put((time.time(), line))
        finally:
            q.put(None)

    def stop():
        k = kill_tree(p.pid if p.poll() is None else None, marker, sids)   # poll() None: not reaped, so the pid cannot be reused yet
        if k > 1:
            log(f"killed {k} process(es) of the session tree (claude, detached Bash commands, compiles)")
    tr = threading.Thread(target=pump, daemon=True); tr.start()
    te = threading.Thread(target=lambda: errbuf.extend(p.stderr), daemon=True); te.start()
    lines: list = []; killed = None; t0 = time.time(); t_kill = None; t_track = 0.0
    try:
        while True:
            try:
                item = q.get(timeout=0.25)
            except queue.Empty:
                item = False
            if item is None:
                break
            if item:
                t, line = item; lines.append(line.rstrip("\n")); n = len(meter.points)
                r = meter.feed(line, t)
                if len(meter.points) > n:
                    on_close()
                if r and killed is None:
                    killed = f"gate:{r}"; t_kill = time.time(); stop()
                    log(f"GATE {r}: killed at metered ${meter.exposure():.3f} of ${meter.G:.3f} ({meter.kill_detail})")
            now = time.time()
            if killed is None and now - t0 > timeout:
                killed = "timeout"; t_kill = now; stop(); log(f"timeout after {timeout:.0f} s: killed")
            if killed is None and _SHUTDOWN.is_set():
                killed = "signal"; t_kill = now; stop(); log(f"signal {_SIGNUM[0]}: session killed, charging it")
            if killed is None and now - t_track > 2.0:   # sessions below claude, swept even if claude dies first
                t_track = now; track_sids(p.pid, sids)
            if t_kill is not None and now - t_kill > 30:
                break   # bounded drain after a kill
    except BaseException:
        stop(); raise
    try:
        p.wait(timeout=60)
    except subprocess.TimeoutExpired:
        pass
    stop()   # stray children (a background Bash task, a compile) must not outlive the session: they would write state.json after the ledger
    tr.join(timeout=10); te.join(timeout=10)
    return ("\n".join(lines) + "\n") if lines else "", "".join(errbuf)[-2000:], killed


def _skip(name: str, args, spend0: float, best0: float, need: float) -> dict:
    print(f"{name[:18]:18s} budget reached: ${spend0:.3f} + opening reserve ${need:.3f} + margin ${cc_meter.MARGIN:.2f} > "
          f"${min(args.budget_usd, gate_cap(args)):.2f}" + (f" (or the review gate ${args.review_budget:.2f})" if getattr(args, "review", False) else "")
          + "; session ends", flush=True)
    print(f"{name[:18]:18s} DONE best={best0} checks=0 tool_calls=0 turns=0 out_tok=0 0s", flush=True)
    return {"problem": name, "model": args.model, "best_score": best0, "skipped": "budget"}


def _ledger_write(ws, run_id: str, fn) -> bool:
    """state.json read-modify-write of the ledger under the state lock (bounded 120 s; False = written unlocked): fn(state, run entry, locked)."""
    from harness.statelock import state_lock
    try:   # the session's tree is dead (kill_tree), so the lock is free; bounded anyway
        lock = state_lock(ws.root, timeout=120); lock.__enter__()
    except TimeoutError:
        lock = None
    try:
        st = _read_state(ws) or json.loads(ws.state_path.read_text())
        fn(st, next((r for r in reversed(st.get("runs", [])) if r.get("run_id") == run_id), {}), lock is not None)
        ws.state_path.write_text(json.dumps(st, ensure_ascii=False, indent=1))
    finally:
        if lock is not None:
            lock.__exit__(None, None, None)
    return lock is not None


def run_problem(name: str, args, out_dir: Path) -> dict:
    if _SHUTDOWN.is_set():   # a shutdown signal arrived (gated runs, main()): nothing new starts
        print(f"{name[:18]:18s} not started: shutdown signal {_SIGNUM[0]}", flush=True)
        return {"problem": name, "model": args.model, "skipped": "signal"}
    row = ROWS[name]; primary = newest_first(row["version_info"])[0]
    root = ROOT / args.work_root if args.work_root else ROOT / "harness/work_cc" / re.sub(r"[^A-Za-z0-9_.-]", "_", args.model)   # --work-root: an isolated line (2026-10-09)
    review = getattr(args, "review", False)
    if review:   # the reviewer (§11): the workspace as it is (Workspace() would rewrite candidate.lean / best.lean); nothing to review without a best
        ws = ReviewView(root / re.sub(r"[^A-Za-z0-9_.-]", "_", name))
        if not ws.state or not (ws.state.get("best") or {}).get("proof"):
            print(f"{name[:18]:18s} review skipped: no stored best to review", flush=True)
            return {"problem": name, "model": args.model, "skipped": "no-best"}
    else:
        ws = Workspace(root / re.sub(r"[^A-Za-z0-9_.-]", "_", name), row, primary, fresh=args.fresh)
    v2 = getattr(args, "prompt", "v1") == "v2"; gated = getattr(args, "budget_usd", None) is not None
    say = lambda m: print(f"{name[:18]:18s} {m}", flush=True)
    dead = [r for r in ws.state["runs"] if r.get("pending")] if gated else []
    if dead:   # a gated session whose driver died (SIGKILL, OOM, reboot): its pre-charge (spend before + its whole gate) stays in api_spend
        for r in dead:
            r.update({"pending": False, "spend_usd_list": r.get("gate_usd"), "flags": (r.get("flags") or []) + ["driver-died"]})
        k = kill_tree(None, f"LRA_WORKSPACE={ws.root}", set())   # its claude or tools may still run and would write state.json
        say(f"{len(dead)} earlier session(s) without an end (driver died): charged their whole gate (kept in api_spend); {k} stray process(es) killed")
        ws.save()
    spend0 = float(ws.state.get("api_spend") or 0); best0 = float(ws.state["best"].get("score") or 33.33)
    G = round(min(args.budget_usd, gate_cap(args)) - spend0, 6) if gated else None   # this session's gate: the rung minus the problem's ledger
    if review:   # the reviewer's own small gate, within what the rung leaves
        G = round(min(G, args.review_budget), 6)
    if gated and G - cc_meter.MARGIN < cc_meter.R_MIN:
        return _skip(name, args, spend0, best0, cc_meter.R_MIN)
    ws.state["runs"].append({"run_id": args.run_id, "model": args.model + "@claude-code", "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                             **({"kind": "review"} if review else {})}); ws.save()
    sections = None; esc = False; rv = None; rv_sha = None
    if review:   # §11: everything precomputed before the session; one message, no tool calls. Review 2026-10-12: a best with >= 2 H points
        # left is profiled first (cached under its sha, so the next executor session's map of it costs no compile), unless --no-heartbeat-map
        from harness import prompt_v2 as pv, cc_levers
        prompt, sections, rv_sha = pv.build_review_prompt(name, row, primary, ws.root, ws.state, gate_usd=G, ws=ws,
                                                          hbmap="default" if args.heartbeat_map else None, log=say)
        ws.state["runs"][-1].update({"review_of": rv_sha, "best_before": best0}); ws.save()
        say(f"review prompt: {', '.join(sections)} (best sha {rv_sha}, gate ${G:.2f})")
    elif v2:
        from harness import prompt_v2 as pv, cc_levers
        prior = [r for r in ws.state["runs"][:-1] if not r.get("skipped") and r.get("kind") != "review"]   # a review is no executor session
        rv = pv.review_for(ws.root, ws.state, current_run=args.run_id)   # §11: a review of this very best, not used yet
        # round 2 (R3, docs/opus_pass2_deep_dive.md): a resume whose previous session gained < 0.5 (over >= 4 checks, not itself a scout)
        # restarts from the reference with a facts sheet; the stored best is kept
        fl = ws.state.get("fresh_lineages")   # review 2026-10-12: never right after a fresh lineage / rescue (merged without a runs[] entry)
        plateau = bool(args.escalate and not args.from_reference and cc_levers.escalate(prior, ws.state["attempts"], fresh=fl))
        esc_rule = plateau and cc_levers.escalate(prior, ws.state["attempts"], gate=G, fresh=fl)   # review 2026-10-12: not on a trailing gate
        esc = esc_rule and rv is None   # §11: a fresh review of the best is the plateau breaker this session tests instead
        if plateau and not esc_rule:
            say(f"no escalation: the previous session gained < 0.5, but this session's gate ${G:.2f} is under ${cc_levers.ESCALATE_MIN_GATE:.2f} "
                "(too little to rebuild from the reference); resuming with the lever review")
        elif esc_rule and not esc:
            say(f"no escalation: the previous session gained < 0.5, but a fresh review of the stored best is waiting (review.md, sha {rv[1]}); "
                "this session tests its levers first")
        from_ref = args.from_reference or esc
        if rv and not from_ref:
            ws.state["runs"][-1]["review_seen"] = rv[1]
        ws.state["runs"][-1]["best_before"] = best0
        if from_ref:   # a restart from the reference: stored best, notes, attempts and spend kept
            ws.state["runs"][-1]["mode"] = "escalated" if esc else "scout"
            (ws.root / "candidate.lean").write_text(row["src"].rstrip() + "\n")
        ws.save()
        if esc:
            say("escalation: the previous session gained < 0.5, so this one starts from the reference with a facts sheet (stored best kept)")
        extras = with_extras("", name, ws, args)   # first: a relay seed replaces candidate.lean before it is shown inline
        if getattr(args, "failed_moves", False):   # review 2026-10-13: moves the stored best has lost (a best adopted between sessions) stay open
            try:
                cc_levers.void_stale(ws.state, ws.state["best"].get("proof"))
            except Exception as e:  # noqa: BLE001
                say(f"refuted moves void failed: {e}")
        prompt, sections = pv.build_prompt_v2(name, row, primary, ws, upstream_history=args.upstream_history, repo_cards=args.repo_cards,
                                              from_reference=from_ref, lever_review=len(prior) >= 1, gate_usd=G,
                                              leads="default" if args.library_leads else None, extras=extras,
                                              facts=from_ref and bool(ws.state["attempts"]), hbmap="default" if args.heartbeat_map else None,
                                              techniques="default" if args.run_techniques else None, current_run=args.run_id,
                                              review=rv[0] if rv and not from_ref else None, review_sha=rv[1] if rv else None,
                                              exemplars="default" if getattr(args, "exemplars", False) else None,
                                              heartbeat_first=getattr(args, "heartbeat_first", False),
                                              failed_moves=getattr(args, "failed_moves", False), log=say)
        say(f"prompt v2: {', '.join(sections)}")
        if getattr(args, "failed_moves", False):   # 2026-10-13: how many refuted moves this session was shown (A/B audit; 0 = the block was empty)
            try:
                _fmb = ((ws.root / "candidate.lean").read_text() if (ws.root / "candidate.lean").exists()   # review: prompt_v2's base, rows shown
                        else (ws.state["best"].get("proof") or row["src"]))
                ws.state["runs"][-1]["failed_moves"] = cc_levers.failed_moves_render(ws.state, base=_fmb)[1] if "failed_moves" in sections else 0; ws.save()
            except Exception as e:  # noqa: BLE001
                say(f"refuted moves count failed: {e}")
        if getattr(args, "heartbeat_first", False):   # 2026-10-13: whether this session's gate passed (A/B audit)
            ws.state["runs"][-1]["heartbeat_first"] = "heartbeat_first" in sections; ws.save()
        if "exemplars" in sections:   # §13: the sha the shown exemplars were built for (A/B audit); stale = built for an earlier best
            from harness import exemplars as EX
            ex = EX.exemplars_for(ws.root, ws.state)
            ws.state["runs"][-1].update({"exemplars_seen": ex[1] if ex else cc_levers.proof_sha(ws.state["best"].get("proof")),
                                         **({"exemplars_stale": True} if ex and ex[2] else {})}); ws.save()
        rp = ws.root / "review.md"
        if rp.exists():   # review 2026-10-12: a review reaches the next executor session through its prompt only; it leaves the workspace now
            # (a later session would find one written for an older best) and is kept with this run's outputs
            (out_dir / "reviews").mkdir(exist_ok=True)
            (out_dir / "reviews" / (re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".md")).write_bytes(rp.read_bytes()); rp.unlink()
    else:
        prompt = with_extras(task_prompt(name, row, primary, ws, args.turns), name, ws, args)
    cmd, env = build_cmd_env(name, row, primary, ws, prompt, args, G)
    if gated:   # the opening call's worst case: CLI scaffolding (~12k tokens in the warm-up streams) + system + prompt, all written at 1 h, US geo
        opening = max(cc_meter.R_MIN, 1.1 * cc_meter.P_CW1H * (12000 + (len(cmd[cmd.index("--system-prompt") + 1]) + len(prompt)) / 3))
        if G - cc_meter.MARGIN < opening:
            st = _read_state(ws)
            for r in reversed(st.get("runs", [])):
                if r.get("run_id") == args.run_id:
                    r.update({"skipped": "budget", "spend_usd_list": 0.0}); break
            ws.state_path.write_text(json.dumps(st, ensure_ascii=False, indent=1))
            return _skip(name, args, spend0, best0, opening)
    if _SHUTDOWN.is_set():   # the signal came while the prompt was built (lemma search): no session, nothing spent
        _ledger_write(ws, args.run_id, lambda st, r, _l: r.update({"skipped": "signal", "spend_usd_list": 0.0}))
        print(f"{name[:18]:18s} not started: shutdown signal {_SIGNUM[0]}", flush=True)
        return {"problem": name, "model": args.model, "best_score": best0, "skipped": "signal"}
    if gated:   # pre-charge (review 2026-10-12): the ledger holds spend0 + G (the whole gate) until this session's charge replaces it, so a
        # driver that dies mid-session leaves the gate booked, never $0; the next session flags the pending entry "driver-died"
        _ledger_write(ws, args.run_id, lambda st, r, _l: (st.update({"api_spend": round(spend0 + G, 6)}), r.update({"pending": True, "gate_usd": G})))
    if v2 and not review:   # the tools read the problem here when a sandbox filters the environment; removed after the session (no stale v2 settings)
        (ws.root / ".lra_env.json").write_text(json.dumps({"LRA_PROBLEM": name, "LRA_RUN_ID": args.run_id, "LRA_MODEL": args.model,
                                                            "LRA_WORKSPACE": str(ws.root), "LRA_AGENT_TAG": V2_ENV["LRA_AGENT_TAG"], "LRA_MODE": V2_ENV["LRA_MODE"],
                                                            **({"LRA_FAILED_MOVES": "1"} if getattr(args, "failed_moves", False) else {})}))
    ms_all = [float(x) for x in args.budget_milestones.split(",") if x.strip()] if gated else []
    ms_done = set((ws.state.get("budget_milestones") or {}).keys()); ms_new: dict = {}
    meter = cc_meter.Meter(G, ttl=args.cache_ttl) if gated else None   # priced at args.model (cc_meter.set_model in main)
    live: list = []   # the stored best at each call's close (review 2026-10-12: attempts are capped at 200, so rebuilding it later can miss it)

    def on_close() -> None:   # per-call live best; live milestone crossings: record + workspace snapshot at the call that crosses
        sp = round(spend0 + meter.S, 6); b = float((_read_state(ws).get("best") or {}).get("score") or best0)
        live.extend([max(b, live[-1] if live else best0)] * (len(meter.points) - len(live)))
        for ms in ms_all:
            if spend0 < ms <= sp and f"{ms:g}" not in ms_done and f"{ms:g}" not in ms_new:
                rec = {"spend": sp, "best": b, "run_id": args.run_id, "turn": len(meter.points) - 1, "t": _iso(time.time())}
                rec["snapshot"] = snapshot(ws, ms, rec); ms_new[f"{ms:g}"] = rec
                say(f"budget milestone ${ms:g} crossed: spend ${sp:.3f}, best {rec['best']} (cap ${args.budget_usd:.2f}); snapshot {rec['snapshot']}")
    t0 = time.time(); killed = None
    try:
        if gated:
            out, err, killed = stream_session(cmd, ws, env, args.timeout, meter, on_close, say)
        elif args.sealed:
            p = subprocess.Popen(cmd, cwd=ws.root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 errors="replace", start_new_session=True)
            try:
                out, err = p.communicate(timeout=args.timeout); err = err[-2000:]
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                out = p.communicate()[0] or ""; err = "timeout"
        else:
            try:
                p = subprocess.run(cmd, cwd=ws.root, env=env, capture_output=True, text=True, timeout=args.timeout)
                out = p.stdout; err = p.stderr[-2000:]
            except subprocess.TimeoutExpired as e:
                out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""); err = "timeout"
    finally:
        if v2 and not review:
            (ws.root / ".lra_env.json").unlink(missing_ok=True)
    t_end = time.time()
    charge = meter.charge() if gated else None
    rv_body, rv_stats, rv_partial = None, None, False
    if review:   # §11: the answer (result text, else the last complete text blocks), linted: no Lean block over 2 lines, no optimality claim;
        txt, rv_partial = review_text(out, meter.result)   # saved only with at least one numbered lever
        if txt.strip():
            body, rv_stats = cc_levers.lint_review(txt)
            rv_body = body if rv_stats["levers"] else None
    flags = ([f"stopped:{killed}"] if killed else []) + (["no-result"] if gated and meter.result is None else []) + (list(meter.flags) if gated else [])
    if gated:   # usage / rate limit evidence in the ledger (2026-10-12 review: Phase A stops between arms on it, probe/abpool/phase_a_audit.py)
        res0 = meter.result or {}
        flags += (["usage-limit"] if res0.get("is_error") and re.search(r"usage limit|rate limit|hit your limit", str(res0.get("result") or ""), re.I) else []) \
            + (["rate-limit-rejected"] if (meter.rate_limit or {}).get("status") == "rejected" else [])
    new_spend = round(spend0 + charge, 6) if gated else None
    for ms in ms_all:   # crossings only the final charge makes (a result total above the meter, the open call of a killed session)
        if spend0 < ms <= new_spend and f"{ms:g}" not in ms_done and f"{ms:g}" not in ms_new:
            rec = {"spend": new_spend, "best": float((_read_state(ws).get("best") or {}).get("score") or best0), "run_id": args.run_id, "turn": None, "t": _iso(t_end)}
            rec["snapshot"] = snapshot(ws, ms, rec); ms_new[f"{ms:g}"] = rec
            say(f"budget milestone ${ms:g} crossed: spend ${new_spend:.3f}, best {rec['best']} (cap ${args.budget_usd:.2f}); snapshot {rec['snapshot']}")
    if gated:   # the ledger (spec §2), written FIRST (review 2026-10-12): api_spend at list price replaces the pre-charge, the run entry ends,
        # milestone crossings; under the state lock
        res = meter.result or {}

        def led(st: dict, r: dict, locked: bool) -> None:
            if not locked:
                flags.append("ledger-unlocked")
            st["api_spend"] = new_spend
            if ms_new:
                st.setdefault("budget_milestones", {}).update({k: v for k, v in ms_new.items() if k not in st.get("budget_milestones", {})})
            r.pop("pending", None)
            r.update({"spend_usd_list": round(charge, 6), "usage": res.get("usage") or meter.totals(), "modelUsage": res.get("modelUsage"),
                      "flags": flags, "minutes": round((t_end - t0) / 60, 1), "ended": _iso(t_end),
                      "meter": {"calls": len(meter.points), "metered_usd": round(meter.S, 6), "kill": meter.kill_detail or None,
                                "total_cost_usd": res.get("total_cost_usd"), "terminal_reason": res.get("terminal_reason")},
                      "driver": {"prompt": args.prompt, "effort": args.effort, "cache_ttl": args.cache_ttl, "gate_usd": G,
                                 "max_output_tokens": env.get("CLAUDE_CODE_MAX_OUTPUT_TOKENS")},
                      "rate_limit": meter.rate_limit})
            if v2:   # round 2 (R3): the session's gain, read by the next session's escalation rule
                r["best_after"] = float((st.get("best") or {}).get("score") or best0)
            if review:
                r.update({"review_saved": rv_body is not None, "review_lint": rv_stats, "review_partial": rv_partial})
            if getattr(args, "ceiling", False):
                r["driver"]["ceiling"] = True
        _ledger_write(ws, args.run_id, led)
        if review and rv_body is not None:   # after the ledger: review.md, bound to the best sha it reviewed (prompt_v2.review_for)
            (ws.root / "review.md").write_text(cc_levers.review_header(rv_sha, args.run_id, _iso(t_end), rv_stats, rv_partial) + "\n" + rv_body + "\n")
            say(f"review saved: {rv_stats['levers']} lever(s), {rv_stats['blocks_removed']} Lean block(s) and {rv_stats['claims_removed']} "
                f"optimality claim(s) removed{', partial (no result event)' if rv_partial else ''} (best sha {rv_sha})")
        elif review:
            say("review: no answer with a numbered lever (stopped before its message, an error, or no lever); review.md not written")
    elif v2:
        _ledger_write(ws, args.run_id, lambda st, r, _l: r.update({"best_after": float((st.get("best") or {}).get("score") or best0)}))
    # Full trajectory (2026-10-06): the stream-json events, gzipped, next to the run's other outputs.
    import gzip
    traj_dir = out_dir / "trajectories"; traj_dir.mkdir(exist_ok=True)
    head = {"type": "header", "run_id": args.run_id, "problem": name, "model": args.model, "cmd": cmd[:1] + ["<prompt>"] + cmd[3:], "prompt": prompt,
            "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0))}
    if v2 or gated:
        head.update({"prompt_version": args.prompt, "sections": sections, "effort": args.effort, "cache_ttl": args.cache_ttl, "gate_usd": G, "spend_before": spend0})
    if v2:
        head["escalated"] = esc
    if review:
        head.update({"kind": "review", "review_of": rv_sha})
    with gzip.open(traj_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".jsonl.gz"), "at") as tf:
        tf.write(json.dumps(head, ensure_ascii=False) + "\n")
        tf.write(out if out.endswith("\n") else out + "\n")
        if err:
            tf.write(json.dumps({"type": "stderr_tail", "text": err}) + "\n")
        if gated:   # per-call list-price spend in agent.py's "turn" shape, so hx_heldout.curve() reads these sessions like agent.py ones
            st_end = _read_state(ws); att = st_end.get("attempts", []); fin = float((st_end.get("best") or {}).get("score") or best0)
            costs = [round(c, 6) for _t, c, _m in meter.points]
            rest = round(round(charge, 6) - sum(costs), 6)
            if costs and abs(rest) < 1e-5:   # rounding only: folded into the last call, so the turn costs sum to the charge exactly
                costs[-1] = round(costs[-1] + rest, 6); rest = 0.0
            for k, (t, _c, mid) in enumerate(meter.points):   # best_so_far: the live best at the call's close, or the attempts rebuild
                cl = meter.calls[mid]; i_, w5, w1, r_ = cc_meter.split(cl.usage)
                bsf = max(best_at(att, args.run_id, _iso(t), best0), live[k] if k < len(live) else best0)
                tf.write(json.dumps({"type": "turn", "turn": k, "t": _iso(t), "cost": costs[k], "price_basis": "list", "best_so_far": bsf,
                                     "msg_id": mid, "in": i_, "cw5": w5, "cw1h": w1, "cr": r_, "out": cl.out, "fallback": cl.fallback}) + "\n")
            if abs(rest) > 1e-9:   # result total vs the sum of calls (side models), or the open call of a killed / result-less session
                tf.write(json.dumps({"type": "turn", "turn": len(meter.points), "t": _iso(t_end), "cost": rest, "price_basis": "list",
                                     "adjust": "result total_cost_usd" if meter.result is not None else
                                     "rule (c) reserve booked (the kill may race the next request)" if meter.race_reserve() else
                                     "open call charged (killed / no result)",
                                     "estimate": flags, "best_so_far": max(best_at(att, args.run_id, _iso(t_end), best0), fin)}) + "\n")
            for k, rec in ms_new.items():
                tf.write(json.dumps({"type": "budget_milestone", "usd": float(k), **rec}) + "\n")
            tf.write(json.dumps({"type": "end", "problem": name, "spend_usd_list": round(charge, 6), "meter_usd": round(meter.S, 6), "flags": flags,
                                 "kill": meter.kill_detail or None, "seconds": round(t_end - t0)}) + "\n")
    info = {}
    try:
        j = None; init = None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    d = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if d.get("type") == "result":
                    j = d
                elif args.sealed and d.get("type") == "system" and d.get("subtype") == "init":   # audit what the session actually had
                    init = {"apiKeySource": d.get("apiKeySource"), "n_mcp": len(d.get("mcp_servers") or []), "n_tools": len(d.get("tools") or []),
                            "memory": bool(d.get("memory_paths")), "cc_version": d.get("claude_code_version")}
        if j is None:
            raise ValueError("no result event")
        info = {k: j.get(k) for k in ("num_turns", "duration_ms", "total_cost_usd", "usage", "is_error", "subtype") if k in j}
        info["result_tail"] = (j.get("result") or "")[-300:]
        if args.sealed:
            info["init"] = init
    except Exception:  # noqa: BLE001
        info = {"raw_tail": out[-500:], "stderr": err}
    if gated:
        info.update({"spend_usd_list": round(charge, 6), "api_spend": new_spend, "flags": flags})
    if review:   # counts only
        info["review"] = {"saved": rv_body is not None, "partial": rv_partial, "best_sha": rv_sha, **(rv_stats or {})}
    st = json.loads(ws.state_path.read_text())
    summary = {"problem": name, "model": args.model, "best_score": st["best"].get("score"), "checks": sum(1 for a in st["attempts"] if a.get("run_id") == args.run_id),
               "seconds": round(time.time() - t0), **info}
    (out_dir / "summary.jsonl").open("a").write(json.dumps(summary, ensure_ascii=False) + "\n")
    if gated:
        print(f"{name[:18]:18s} [{args.model}] spend ${charge:.3f} list (total ${spend0 + charge:.3f}{', ' + ','.join(flags) if flags else ''})", flush=True)
    print(f"{name[:18]:18s} [{args.model}] best={summary['best_score']} checks={summary['checks']} turns={info.get('num_turns')} cost=${info.get('total_cost_usd')} {summary['seconds']}s {'' if not info.get('is_error') else 'ERROR ' + str(info.get('result_tail'))[:120]}", flush=True)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--problems", nargs="*", default=None)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--turns", type=int, default=40)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--work-root", default=None, help="per-problem state root of an isolated line (default harness/work_cc/<model>)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--seed-dir", default=None, help="relay: start each problem from <dir>/<problem>.lean, append <dir>/<problem>.md")
    ap.add_argument("--brief-dir", default=None, help="census: append <dir>/<problem>.md (strategy brief and blind target)")
    ap.add_argument("--max-turns-flag", action="store_true", help="pass --max-turns to claude (only if this CLI version supports it)")
    ap.add_argument("--effort", default=None, choices=["low", "medium", "high", "xhigh", "max"], help="pin claude's effort (default: the user setting)")
    ap.add_argument("--sealed", action="store_true", help="sealed-set hardening (2026-10-12): no transcripts in ~/.claude, no MCP, no user "
                    "settings or memory, read-only git, subscription only, process-group kill on timeout; see build_cmd_env")
    # driver v2 (docs/cc_driver_v2.md, 2026-10-12): every new flag is off by default, so a plain v1 invocation is byte-identical
    ap.add_argument("--prompt", choices=["v1", "v2"], default="v1", help="v2: prompt v2 (harness/prompt_v2.py), Edit tool, dontAsk permissions with "
                    "exact per-script rules, the v2 tool behaviour (LRA_CHECK_V2=1)")
    ap.add_argument("--gate-cap", type=float, default=None, help="per-problem gate ceiling (default cc_meter.CAP = $2.85, the closed-track "
                    "gate). Raise it ONLY for feasibility runs that are not closed-track compliant (2026-10-12: set #3 Fable push)")
    ap.add_argument("--budget-usd", type=float, default=None, help="hard per-problem gate at LIST price (harness/cc_meter.py): this session's gate is "
                    "min(this, $2.85) minus the problem's state.json api_spend; partial-message streaming, process-group kill, ledger in state.json")
    ap.add_argument("--budget-milestones", default="1.0,1.4,1.7,2.0", help="with --budget-usd: spend levels whose crossing is recorded "
                    "(state.json budget_milestones) and snapshots the workspace into <ws>/snapshots/<ms>/ (Phase B fork points)")
    ap.add_argument("--cache-ttl", choices=["1h", "5m"], default="1h", help="prompt-cache TTL: 5m sets FORCE_PROMPT_CACHING_5M=1 (subscription default 1 h)")
    ap.add_argument("--max-output-tokens", type=int, default=None, help="CLAUDE_CODE_MAX_OUTPUT_TOKENS (default 32000 whenever --budget-usd is set)")
    ap.add_argument("--from-reference", action="store_true", help="v2: reset candidate.lean to the reference (state, best, notes and spend kept) "
                    "with the scout / blind-target / restructure brief")
    ap.add_argument("--repo-cards", action="store_true", help="v2: add the per-repository automation card (agent.py REPO_BRIEFS)")
    ap.add_argument("--no-upstream-history", dest="upstream_history", action="store_false", default=True, help="v2: no upstream digest, git hint or "
                    "git rules (the R2 compliance switch)")
    ap.add_argument("--library-leads", action=argparse.BooleanOptionalAction, default=True, help="v2: LIBRARY LEADS from the lemma search at "
                    "session start (compiles; $0 model spend)")
    # round 2 (2026-10-12, docs/cc_driver_v2.md §9): on by default under --prompt v2, never under v1
    ap.add_argument("--heartbeat-map", action=argparse.BooleanOptionalAction, default=True, help="v2: HEARTBEAT MAP of candidate.lean at session "
                    "start when >= 2 H points are left (heartbeat_profile, cached per proof sha in state.json; compiles on a cache miss)")
    ap.add_argument("--run-techniques", action=argparse.BooleanOptionalAction, default=True, help="v2: show <work root>/_run_techniques.json "
                    "(in-run learning, harness/inrun.py; capped at 1.5k chars)")
    ap.add_argument("--escalate", action=argparse.BooleanOptionalAction, default=True, help="v2: a resume whose previous session gained < 0.5 "
                    "(over >= 4 checks, not a scout) starts from the reference with a facts sheet, stored best kept (R3); never on a gate under "
                    "cc_levers.ESCALATE_MIN_GATE ($1.40), never while a fresh review of the stored best is waiting (§11)")
    # reviewer and ceiling (2026-10-12, docs/cc_driver_v2.md §11)
    ap.add_argument("--review", action="store_true", help="v2: the REVIEWER: per problem one short fresh-context session that writes no proof "
                    "file (Read on the workspace only; no Bash, Edit or Write) and names 3-6 levers for the stored best, saved as <ws>/review.md "
                    "with the best's sha; gated at --review-budget, metered and charged to the problem's ledger (runs[] kind review); effort high "
                    "unless --effort is given; the cap is --budget-usd (default $2.85)")
    ap.add_argument("--review-budget", type=float, default=0.30, help="--review: the reviewer's gate in USD at list price (within what the rung leaves)")
    ap.add_argument("--ceiling", action="store_true", help="a CEILING measurement (never a submission): the per-problem cap is --budget-usd itself, "
                    "not $2.85")
    ap.add_argument("--exemplars", action="store_true", help="v2: show <work root>/_exemplars/<ws>.md (harness/exemplars.py: the strongest rows' "
                    "style, retrieved transformations of other problems; docs/cc_driver_v2.md §13) with this best's hot families as WHAT WORKED ON "
                    "THE STRONGEST ROWS, while the stored best is below the file's target")
    ap.add_argument("--heartbeat-first", action="store_true", help="v2 executor (2026-10-13): the HEARTBEAT_FIRST card "
                    "with the technique cards and heartbeat-aware cards / repo card / restructure brief / lever review when the stored best has H "
                    "points left >= L points left (always before a measured best); TOKEN COUNTING's one-closer line and closed-lessons habit 2 "
                    "axis-conditional in the system prompt for every row (A/B unit: the flag) (harness/cards.py HB_REWRITES); the reviewer "
                    "ignores it; off until an A/B")
    ap.add_argument("--failed-moves", action="store_true", help="v2 executor (2026-10-13, docs/opus_pass2_deep_dive.md §3): the REFUTED MOVES "
                    "block after the inline files (harness/cc_levers.failed_moves_block: state.json attempts grouped by edit signature and first "
                    "error class, >= 2 real compile refutations from separate tool calls, reopened when the best changes in the lines they "
                    "touch; text-less failures only as UNKNOWN NAMES; <= 1,200 chars) and "
                    "LRA_FAILED_MOVES=1 for the check path (moves are recorded where the check path calls cc_levers.attach_move); runs[] entry "
                    "`failed_moves`; off until an A/B")
    args = ap.parse_args()
    if args.failed_moves and (args.prompt != "v2" or args.review):   # 2026-10-13: separate refusal, the v2-only message above is unchanged
        ap.error("--failed-moves needs --prompt v2 and an executor session (not --review)")
    if args.sealed and (args.seed_dir or args.brief_dir):
        ap.error("--sealed refuses --seed-dir / --brief-dir (no relay seed or brief on a sealed set)")
    if args.prompt != "v2" and (args.from_reference or args.repo_cards or not args.upstream_history or not args.library_leads
                                or not args.heartbeat_map or not args.run_techniques or not args.escalate or args.exemplars
                                or args.heartbeat_first):
        ap.error("--from-reference, --repo-cards, --no-upstream-history, --no-library-leads, --no-heartbeat-map, --no-run-techniques, "
                 "--no-escalate, --exemplars and --heartbeat-first need --prompt v2 (v1 stays byte-identical)")
    if args.budget_usd is not None and args.budget_usd <= 0:
        ap.error("--budget-usd must be positive")
    if args.review and args.prompt != "v2":
        ap.error("--review needs --prompt v2")
    if args.review and (args.from_reference or args.seed_dir or args.brief_dir or args.fresh):
        ap.error("--review refuses --from-reference, --seed-dir, --brief-dir and --fresh (the reviewer writes no proof file)")
    if args.review_budget <= 0:
        ap.error("--review-budget must be positive")
    if args.ceiling and args.budget_usd is None:
        ap.error("--ceiling needs --budget-usd (the uncapped rung)")
    if args.review:   # always gated: the cap is the rung (default $2.85), the gate the review budget within it
        args.effort = args.effort or "high"
        args.budget_usd = cc_meter.CAP if args.budget_usd is None else args.budget_usd
    if args.budget_usd is not None:   # 2026-10-12: meter and gate at THIS model's list prices (Opus 5.5 or Fable 5.1; others refused)
        try:
            cc_meter.set_model(args.model)
        except ValueError as e:
            ap.error(str(e))
    args.run_id = args.run_id or f"cc-{args.model}-{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir = ROOT / "probe/runs" / args.run_id; out_dir.mkdir(parents=True, exist_ok=True)
    names = args.problems or list(ROWS)
    print(f"run {args.run_id}: {len(names)} problems via Claude Code, model={args.model}, turns≤{args.turns}", flush=True)
    if args.budget_usd is not None or args.prompt == "v2":
        print(f"  driver v2: prompt {args.prompt}, effort {args.effort}, cache {args.cache_ttl}"
              + (f", gate ${min(args.budget_usd, gate_cap(args)):.2f} list per problem (milestones {args.budget_milestones})" if args.budget_usd is not None else "")
              + (f", REVIEWER (gate ${args.review_budget:.2f} per problem, Read only, no proof file)" if args.review else "")
              + (", CEILING measurement (uncapped: the rung is the cap; never a submission)" if args.ceiling else ""), flush=True)
    if args.budget_usd is not None:   # 2026-10-12 review: a gated run never dies uncharged. SIGTERM (an arm `timeout`, which signals its whole
        # process group but not claude's own session; a unit stop), SIGINT or SIGHUP: every live session's tree is killed and charged, its
        # ledger written, nothing new starts; exit 128 + signal. Ungated (v1) runs keep the default handlers.
        def _on_signal(signum, _frame):
            _SIGNUM[0] = signum; _SHUTDOWN.set()
        for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(s, _on_signal)
    with ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(lambda n: run_problem(n, args, out_dir), names))
    if _SHUTDOWN.is_set():
        print(f"stopped by signal {_SIGNUM[0]}: live sessions killed and charged, later problems not started", flush=True)
        raise SystemExit(128 + _SIGNUM[0])
    print("done", flush=True)


if __name__ == "__main__":
    main()
