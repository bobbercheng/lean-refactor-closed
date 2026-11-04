#!/usr/bin/env python3
"""Checkpoint starts (2026-10-26 ~02:30 UTC: fast e2e iterations that START FROM A CHECKPOINT instead of from seed, for changes that
act after the $1.25 checkpoint: later session shape, restart policy, $0 checkpoint passes, crossover, review, end stage).

`router.py --start-from <source router run dir> --start-at <checkpoint>` seeds the new arm's hx work root from the source run's state at
that checkpoint, so the router then behaves as if its own ladder had just reached it: the checkpoint's $0 step, the gate, the next rungs,
cross@pre, the review and the end stage as configured. The source run's own final from the same state is the paired control per row
(probe/b63/ckpt_readout.py). Nothing of the source is ever written (its run dir, its hx worktree, its heldout dir are only read).

  item      --start-item input (default): the source row's `input@k` (what the source's ladder left at the checkpoint, before the source's own
            checkpoint cleanup); the new run runs ITS checkpoint $0 step (cleanup / C1 per its config), writes the gain back and gates, as
            its own ladder would have it. --start-item clean: `clean@k` (the source's cleaned checkpoint best, as the G3/G8 pilots used);
            the new run's cleanup then runs on top of it (a $0 checkpoint pass under test would see an already cleaned proof).
            Spend = the source row's spend at the checkpoint (state.json api_spend as recorded with input@k): it becomes the new work root's
            api_spend, so the hx ladder's absolute rungs, every agent.py --budget-usd, the router's row ledger, decide() and the review
            budget all count it, and the cap holds for inherited + new spend.
  history   --start-history restore (default): the source arm's work root cut back to the checkpoint. state.json: the runs, attempts and
            winning edits of the rounds at or below the checkpoint rung (the source's jobs.log maps rounds to rungs), the budget milestones
            and router write-backs before it, the last profiled floor before it (from those rounds' trajectories); notes.md as the first
            session after the checkpoint was shown it (its trajectory's opening digest; the final notes.md when no session followed); the
            sessions' scratch files last written before the checkpoint. Checked: agent.py's opening digest is rebuilt from the restored
            state and compared with the opening of the source's first post-checkpoint session (`digest_match`; the best line is left out:
            it shows the checkpoint cleanup's output). Attempts that agent.py's 200-record cap dropped from the source's final state.json
            come back as placeholders (one OK record per lost run at that run's end best, from its summary.json, the rest failed records),
            and winning edits that its 30-record cap dropped come back from that opening, so the attempt count and the older-best inputs
            of agent.py's structural / two-strikes rules are what the source's next session saw.
            --start-history none: postpass.seed_workspace's shape (best + spend, no history), as the G3/G8 pilots seeded.
  lineage   the source arm's lineage.json entry cut to the sessions at or below the checkpoint rung (gains[-1] / gains[-2] for decide(), the
            session count for c6_of).
  briefs    the source arm's _autobrief JSONs (the same briefs: a paired start; hx_heldout's auto-brief skips rows that have one).
Refusals, before any spend: a row without the checkpoint item; an inherited spend above the cap; the source's own work root as the target;
a target work dir with a state.json this start did not seed; a new worktree with fewer than MIN_ENVS env links or a missing compile env.
"""
from __future__ import annotations

import copy, gzip, hashlib, json, math, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(1, str(ROOT / "harness"))

ITEM_KEYS = ("proof", "score", "tokens", "heartbeats", "L", "H", "Z", "compat")
MIN_ENVS = 20            # the empty-envs incident (2026-10-25): an hx worktree carries 21-24 links; below 20 the worktree is not usable
SEED_MARK = "start_seed.json"
NOTES_HEAD = "# Notes (yours to keep; persisted across runs)\n"
ATTEMPT_CAP = 200        # agent.py Workspace keeps the last 200 attempts
_ROUND = re.compile(r"round (\d+) \(rung \$([0-9.]+)\)")
_RUNNO = re.compile(r"-([rfpv])(\d+)$")
# the opening digest (agent.py Workspace.digest; identical at the v2 commit and here)
D_HEAD = "Prior work on this problem:"
D_ENDS = ("\n\nContinue from candidate.lean", "\n\nBoth original.lean and candidate.lean")
D_WINS = "WINNING EDITS from earlier runs"
D_DEAD = "NAMES THAT DO NOT EXIST in this environment"
D_NOTES = "Your notes.md from earlier runs:\n"
D_CLAIMS = "\nUNVERIFIED CLAIMS in these notes"
_FIRST = re.compile(r"^Prior work on this problem: (\d+) checked attempts over (\d+) earlier run\(s\)\. Best so far: (.*)$")
_WIN = re.compile(r"^  \[(\S+) check (\S+): ([+-][0-9.eE+-]+) score, ([+-]?-?\d+) tokens, ([+-]?-?\d+) hb\]$")
# files of a work dir the restore writes itself, or agent.py rewrites at every session start
OWN_FILES = {"state.json", "best.lean", "candidate.lean", "notes.md", "original.lean", "context.lean", SEED_MARK}


def safe(n: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", n)


def sha12(text) -> str | None:
    return hashlib.sha256((text or "").rstrip().encode()).hexdigest()[:12] if text else None


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ts(s) -> float | None:
    """An ISO-8601 UTC stamp (the router's / agent.py's `...Z` or hx_heldout's `+00:00`) as epoch seconds; None if unreadable."""
    if not isinstance(s, str) or not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    try:
        from datetime import datetime
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def _write_json(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp"); tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1)); tmp.replace(p)


class Refused(Exception):
    """A checkpoint start that must not begin (raised before any spend)."""


# ------------------------------------------------------------------------------------------------------------------------- the source
class Source:
    """The source router run (read-only): its run dir (config.json, rows/<ws>.json, finals.json), its arm's hx worktree + work root
    (state.json, notes.md, scratch files, probe/runs/<run>/{trajectories,summary.json}) and its heldout dir (lineage.json, jobs.log)."""

    def __init__(self, run_dir, hx=None, heldout=None):
        self.run_dir = Path(run_dir).expanduser().resolve()
        cfgp = self.run_dir / "config.json"
        if not cfgp.is_file():
            raise Refused(f"--start-from {self.run_dir}: no config.json (not a router run dir)")
        self.cfg = json.loads(cfgp.read_text())
        self.set, self.arm = self.cfg.get("set"), self.cfg.get("arm")
        if not self.set or not self.arm:
            raise Refused(f"--start-from {self.run_dir}: a generic-mode (--input) run; a checkpoint start needs a --set/--arm source")
        self.checkpoints = [float(x) for x in str(self.cfg.get("checkpoints") or "").split(",") if x.strip()]
        import hx_heldout as H
        if self.set not in H.SETS:
            raise Refused(f"--start-from: unknown set {self.set!r}")
        _p, _h, self.prefix, _r = H.SETS[self.set]
        clean = self.set.endswith("-clean")
        self.hx = Path(hx).expanduser().resolve() if hx else H.HX_BASE / (f"{self.prefix}-{self.arm}-hx" if clean else f"{self.prefix}-hx")   # b66: $LRA_HX_BASE
        self.root = f"harness/hwork/{self.prefix}-{self.arm}"
        self.run_prefix = f"{self.prefix}-hx-{self.arm}-"
        repo = subprocess.run(["git", "-C", str(self.run_dir), "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
        repo = Path(repo) if repo else self.run_dir.parents[2]
        self.heldout = Path(heldout).expanduser().resolve() if heldout else repo / f"probe/heldout/{self.prefix}-hx-{self.arm}"
        self._rungs = None
        self._lineage = None

    @property
    def work(self) -> Path:
        return self.hx / self.root

    def row(self, name: str) -> dict | None:
        try:
            return json.loads((self.run_dir / "rows" / f"{safe(name)}.json").read_text())
        except (OSError, ValueError):
            return None

    def finals(self) -> dict:
        try:
            return json.loads((self.run_dir / "finals.json").read_text())
        except (OSError, ValueError):
            return {}

    def run_rungs(self) -> dict:
        """{run id: rung} of the source arm's ladder runs: `round k (rung $X)` lines of jobs.log give r<k> / f<k> (and p<k>, v<k>) rung X;
        a run whose round has no such line (a rescue) is unknown (None): never counted as before a checkpoint."""
        if self._rungs is None:
            rr = {}
            try:
                for l in (self.heldout / "jobs.log").read_text().splitlines():
                    m = _ROUND.search(l)
                    if m:
                        rr[int(m.group(1))] = float(m.group(2))
            except OSError:
                pass
            self._rungs = rr
        return self._rungs

    def rung_of(self, run_id: str):
        if not isinstance(run_id, str) or not run_id.startswith(self.run_prefix):
            return None
        m = _RUNNO.search(run_id)
        return self.run_rungs().get(int(m.group(2))) if m else None

    def lineage(self) -> dict:
        if self._lineage is None:
            try:
                self._lineage = json.loads((self.heldout / "lineage.json").read_text())
            except (OSError, ValueError):
                self._lineage = {}
        return self._lineage


def checkpoint_index(cps: list, x: float) -> int | None:
    return next((i for i, c in enumerate(cps) if abs(float(c) - float(x)) < 1e-9), None)


def checkpoint_item(src: Source, name: str, start_at: float, kind: str = "input") -> dict:
    """The row's item at the checkpoint: {"item": ITEM_KEYS subset, "spend", "at" (the input@k record time), "step", "sha", "score"}.
    Raises Refused when the source has no such item."""
    ks = checkpoint_index(src.checkpoints, start_at)
    if ks is None:
        raise Refused(f"checkpoint ${start_at:.2f} is not one of the source's checkpoints {src.checkpoints}")
    d = src.row(name)
    steps = (d or {}).get("steps") or {}
    inp, cln = steps.get(f"input@{ks}"), steps.get(f"clean@{ks}")
    st = inp if kind == "input" else cln
    if not st or not (st.get("item") or {}).get("proof") or inp is None:
        raise Refused(f"no {('input' if kind == 'input' else 'clean')}@{ks} item with a proof")
    it = st["item"]
    spends = [float(x["item"].get("spend")) for x in (inp, cln) if x and (x.get("item") or {}).get("spend") is not None]
    spend = float(inp["item"].get("spend")) if inp["item"].get("spend") is not None else (max(spends) if spends else None)
    if spend is None:
        raise Refused(f"input@{ks} carries no spend")
    item = {k: it[k] for k in ITEM_KEYS if it.get(k) is not None}
    if it.get("measured_score") is not None:
        item["measured_score"] = it["measured_score"]
    return {"item": item, "spend": round(spend, 6), "at": inp.get("at"), "step": f"{kind}@{ks}", "sha": sha12(item["proof"]),
            "score": item.get("score"), "index": ks}


def lineage_cut(entry: dict | None, start_at: float) -> dict:
    """The source lineage entry cut to the sessions at or below the checkpoint rung (hx_heldout: one [rung, gain] per session that spent
    >= $0.05; `sessions` counts exactly those)."""
    g = [list(x) for x in ((entry or {}).get("gains") or []) if x and float(x[0]) <= start_at + 1e-9]
    out = {"sessions": len(g), "fresh": 0, "last_gain": g[-1][1] if g else None, "gains": g}
    if (entry or {}).get("fresh") and len(g) == len((entry or {}).get("gains") or []):
        out["fresh"] = entry["fresh"]   # every session of the source was before the checkpoint: its fresh count stands
    return out


# ------------------------------------------------------------------------------------------------------------------- the opening digest
def first_user_text(traj: Path) -> str | None:
    """The first user message of a session trajectory (<run>/trajectories/<ws>.jsonl[.gz]): agent.py's opening, holding the digest."""
    for p in (traj, traj.with_suffix("") if traj.suffix == ".gz" else Path(str(traj) + ".gz")):
        if not p.is_file():
            continue
        try:
            op = gzip.open if p.suffix == ".gz" else open
            with op(p, "rt") as fh:
                for l in fh:
                    try:
                        d = json.loads(l)
                    except ValueError:
                        continue
                    if d.get("type") == "message" and d.get("role") == "user" and isinstance(d.get("content"), str):
                        return d["content"]
        except (OSError, EOFError):
            return None
    return None


def opening_digest(text: str | None) -> str | None:
    if not text or D_HEAD not in text:
        return None
    s = text[text.index(D_HEAD):]
    ends = [s.find(e) for e in D_ENDS if s.find(e) >= 0]
    return s[:min(ends)] if ends else s


def parse_digest(dg: str) -> dict:
    """The opening digest's parts: attempts / runs counts, the best line, the winning edits shown (records), the dead names, the notes."""
    out = {"attempts": None, "runs": None, "best_line": None, "wins": [], "dead": [], "notes": None, "notes_truncated": False}
    lines = dg.split("\n")
    m = _FIRST.match(lines[0]) if lines else None
    if m:
        out["attempts"], out["runs"], out["best_line"] = int(m.group(1)), int(m.group(2)), m.group(3)
    if D_NOTES in dg:
        rest = dg[dg.index(D_NOTES) + len(D_NOTES):]
        cut = rest.find(D_CLAIMS)
        notes = rest if cut < 0 else rest[:cut]
        out["notes"] = notes
        out["notes_truncated"] = len(notes) >= 3000
    head = dg[:dg.index(D_NOTES)] if D_NOTES in dg else dg
    if D_WINS in head:
        cur = None
        for l in head[head.index(D_WINS):].split("\n")[1:]:
            w = _WIN.match(l)
            if w:
                cur = {"run_id": w.group(1), "check": _num(w.group(2)), "d_score": _num(w.group(3)), "d_tokens": int(w.group(4)),
                       "d_heartbeats": int(w.group(5)), "diff": ""}
                out["wins"].append(cur)
            elif cur is not None and l.startswith("    "):
                cur["diff"] = (cur["diff"] + "\n" if cur["diff"] else "") + l[4:]
            else:
                cur = None
                if not l.startswith("  "):
                    break
    if D_DEAD in head:
        seg = head[head.index(D_DEAD):].split("\n")[0]
        out["dead"] = re.findall(r"`([^`]+)`", seg)
    return out


def _num(s):
    try:
        f = float(s)
    except ValueError:
        return s
    return int(f) if re.fullmatch(r"[+-]?\d+", s) else f


def digest_of(state: dict, notes: str, current_run: str | None) -> str:
    """agent.py's Workspace.digest of a restored state (the current run appended first, as agent.py does before the opening)."""
    from harness import agent as AG
    ws = object.__new__(AG.Workspace)
    st = copy.deepcopy(state)
    st.setdefault("runs", []).append({"run_id": current_run or "next"})
    st.setdefault("best", {}).setdefault("score", 33.33)
    ws.state = st
    with tempfile.TemporaryDirectory() as td:
        ws.root = Path(td)
        (ws.root / "notes.md").write_text(notes)
        return ws.digest()


def _drop_best(dg: str) -> str:
    l0, _, rest = dg.partition("\n")
    return l0.split(" Best so far:")[0] + "\n" + rest


# ------------------------------------------------------------------------------------------------------------------- notes.md replay
# The sessions write notes.md through tools only: write_file (overwrite), shell heredocs (`cat >> notes.md <<'EOF'`, `cat > notes.md`,
# `cat <<'EOF' | tee -a notes.md`) and Python heredocs (`open('notes.md','a').write('...')`, `with open(...) as f: f.write(...)`). Replaying
# them in order from agent.py's fresh header gives notes.md at every session boundary. The replay is trusted only when replaying EVERY
# session of the row reproduces the source's final notes.md byte for byte (or, failing that, when no pre-checkpoint write was left
# unparsed and the replay's first 3000 characters equal what the first post-checkpoint session was shown).
_HD = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
_TGT = re.compile(r"(>>|>)\s*(['\"]?)((?:\S*/)?notes\.md)\2(?=\s|$|;|&|\||\))")
_TEE = re.compile(r"\btee\s+(-a\s+)?(['\"]?)((?:\S*/)?notes\.md)\2")
_PYW = re.compile(r"notes\.md")


def _is_notes(path: str, ws: str) -> bool:
    p = str(path or "").strip()
    return p in ("notes.md", "./notes.md") or p.endswith(f"/{ws}/notes.md")


def _py_str(node):
    import ast
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = _py_str(node.left), _py_str(node.right)
        return a + b if a is not None and b is not None else None
    return None


def _py_ops(src: str, ws: str):
    """[(mode, text)] of a Python program's writes to notes.md, in source order; `unsupported` when it writes notes.md otherwise."""
    import ast
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return [], bool(_PYW.search(src))
    ops, uns, alias = [], False, {}

    def open_mode(call):
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "open" and call.args:
            p = _py_str(call.args[0])
            if p is not None and _is_notes(p, ws):
                m = _py_str(call.args[1]) if len(call.args) > 1 else next((_py_str(k.value) for k in call.keywords if k.arg == "mode"), "r")
                return m or "r"
        return None
    nodes = sorted((n for n in ast.walk(tree) if hasattr(n, "lineno")), key=lambda n: (n.lineno, n.col_offset))
    for n in nodes:
        if isinstance(n, ast.With):
            for it in n.items:
                m = open_mode(it.context_expr)
                if m and isinstance(it.optional_vars, ast.Name):
                    alias[it.optional_vars.id] = m
                    if "w" in m:
                        ops.append((">", ""))   # opened for writing: truncated at once
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("write", "write_text"):
            tgt = n.func.value
            m = open_mode(tgt) if n.func.attr == "write" else None
            if n.func.attr == "write_text":
                if isinstance(tgt, ast.Call) and getattr(tgt.func, "attr", getattr(tgt.func, "id", "")) in ("Path",) and tgt.args \
                        and _py_str(tgt.args[0]) is not None and _is_notes(_py_str(tgt.args[0]), ws):
                    m = "w"
            if m is None and isinstance(tgt, ast.Name) and tgt.id in alias:
                m = alias[tgt.id]
                if "w" in m:
                    m = "a"   # the with-block's truncation is already recorded; later writes append
            if m is None:
                continue
            s = _py_str(n.args[0]) if n.args else None
            if s is None or not ({"a", "w"} & set(m)):
                uns = True; continue
            ops.append((">>" if "a" in m else ">", s))
    if not ops and re.search(r"open\([^)]*notes\.md[^)]*['\"][wa+]", src):
        uns = True
    return ops, uns


def _shell_ops(cmd: str, ws: str):
    """[(mode, text)] of one shell command's writes to notes.md, in order; `unsupported` when it writes notes.md some other way."""
    ops, uns = [], False
    lines = cmd.split("\n"); i = 0
    while i < len(lines):
        ln = lines[i]
        m = _HD.search(ln)
        if m:
            dash, quoted, delim = m.group(1), m.group(2), m.group(3)
            j, body = i + 1, []
            while j < len(lines) and (lines[j].lstrip("\t") if dash else lines[j]) != delim:
                body.append(lines[j].lstrip("\t") if dash else lines[j]); j += 1
            text = "\n".join(body) + ("\n" if body else "")
            t, te = _TGT.search(ln), _TEE.search(ln)
            if (t and _is_notes(t.group(3), ws)) or (te and _is_notes(te.group(3), ws)):
                if not quoted and re.search(r"[$`\\]", text):
                    uns = True   # an unquoted heredoc expands: the literal text may not be what the shell wrote
                ops.append((">>" if (t and t.group(1) == ">>") or (te and te.group(1)) else ">", text))
            elif re.search(r"\bpython3?\b", ln[:m.start()]):
                o, u = _py_ops(text, ws); ops += o; uns |= u
            i = j + 1; continue
        if any(_is_notes(t.group(3), ws) for t in _TGT.finditer(ln)) or any(_is_notes(t.group(3), ws) for t in _TEE.finditer(ln)) \
                or re.search(r"\b(sed|perl)\s+-i\S*\s[^\n]*notes\.md|\bmv\s+\S+\s+(\./)?notes\.md\b|\bcp\s+\S+\s+(\./)?notes\.md\b", ln):
            uns = True
        i += 1
    return ops, uns


def session_notes_ops(traj: Path, ws: str):
    """(ops, unsupported, found) of one session trajectory."""
    p = traj if traj.exists() else (traj.with_suffix("") if traj.suffix == ".gz" else traj)
    if not p.exists():
        return [], False, False
    ops, uns = [], False
    try:
        op = gzip.open if p.suffix == ".gz" else open
        with op(p, "rt") as fh:
            for l in fh:
                try:
                    d = json.loads(l)
                except ValueError:
                    continue
                c = d.get("content")
                if d.get("role") != "assistant" or not isinstance(c, list):
                    continue
                for b in c:
                    if not isinstance(b, dict) or b.get("type") != "tool_use":
                        continue
                    inp = b.get("input") or {}
                    if b.get("name") == "write_file" and _is_notes(inp.get("path"), ws):
                        ops.append((">", str(inp.get("content") or "")))
                    elif b.get("name") == "shell":
                        o, u = _shell_ops(str(inp.get("command") or ""), ws); ops += o; uns |= u
    except (OSError, EOFError):
        return ops, True, False
    return ops, uns, True


def notes_replay(src: "Source", name: str, runs: list) -> dict:
    """notes.md after each of `runs` (in order) from agent.py's fresh header: {"text", "unsupported": [runs], "missing": [runs]}."""
    ws = safe(name)
    text, uns, miss = NOTES_HEAD, [], []
    for r in runs:
        ops, u, found = session_notes_ops(src.hx / "probe/runs" / r / "trajectories" / f"{ws}.jsonl.gz", ws)
        if not found:
            miss.append(r)
        if u:
            uns.append(r)
        for mode, t in ops:
            text = text + t if mode == ">>" else t
    return {"text": text, "unsupported": uns, "missing": miss}


# ------------------------------------------------------------------------------------------------------------------------ the restore
def _profile_floor(src: Source, ws: str, pre_runs: list) -> float | None:
    """The floor of the last lean_profile result before the checkpoint (agent.py sets state.json hb_floor from every profile)."""
    for run in reversed(pre_runs):
        p = src.hx / "probe/runs" / run / "trajectories" / f"{ws}.jsonl.gz"
        if not p.exists():
            p = p.with_suffix("")
        if not p.exists():
            continue
        ids, floor = set(), None
        try:
            op = gzip.open if p.suffix == ".gz" else open
            with op(p, "rt") as fh:
                for l in fh:
                    try:
                        d = json.loads(l)
                    except ValueError:
                        continue
                    c = d.get("content")
                    if not isinstance(c, list):
                        continue
                    for b in c:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "tool_use" and b.get("name") == "lean_profile":
                            ids.add(b.get("id"))
                        elif b.get("type") == "tool_result" and b.get("tool_use_id") in ids:
                            try:
                                r = json.loads(b.get("content") if isinstance(b.get("content"), str) else "")
                            except ValueError:
                                continue
                            if isinstance(r, dict) and r.get("floor"):
                                floor = r["floor"]
        except (OSError, EOFError):
            continue
        if floor is not None:
            return floor
    return None


def _run_best(src: Source, run: str, name: str):
    try:
        for e in json.loads((src.hx / "probe/runs" / run / "summary.json").read_text()):
            if e.get("problem") == name and e.get("best_score") is not None:
                return float(e["best_score"])
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def restore(src: Source, name: str, ck: dict, start_at: float, history: str = "restore") -> dict:
    """The new work dir's content for one row: {"state", "notes", "files": [(source path, name, kind)], "report"}. Pure read of the source."""
    item, spend = ck["item"], ck["spend"]
    best = {k: item[k] for k in ITEM_KEYS if item.get(k) is not None}
    best["proof"] = best["proof"].rstrip() + "\n"
    best["score"] = float(best.get("score") if best.get("score") is not None else 33.33)
    rep = {"history": history}
    if history == "none":
        return {"state": {"problem": name, "best": best, "attempts": [], "runs": [], "api_spend": spend}, "notes": NOTES_HEAD, "files": [],
                "report": rep}
    ws = safe(name)
    d = src.work / ws
    try:
        final = json.loads((d / "state.json").read_text())
    except (OSError, ValueError):
        raise Refused(f"history restore: the source work root ({d.parent.name}) has no state.json for this row")   # no name fragment (anon)
    at = _ts(ck.get("at"))
    runs_all = [r for r in final.get("runs") or [] if isinstance(r, dict)]
    pre = [r for r in runs_all if (src.rung_of(r.get("run_id")) or math.inf) <= start_at + 1e-9]
    pre_ids = {r.get("run_id") for r in pre}
    post = [r.get("run_id") for r in runs_all if r.get("run_id") not in pre_ids]
    unknown = [r.get("run_id") for r in runs_all if src.rung_of(r.get("run_id")) is None]
    rep.update(pre_runs=len(pre), post_runs=len(post), unknown_runs=len(unknown))
    # the opening of the first session after the checkpoint (what it saw of this state)
    dg = None
    if post:
        dg = opening_digest(first_user_text(src.hx / "probe/runs" / post[0] / "trajectories" / f"{ws}.jsonl.gz"))
    pd = parse_digest(dg) if dg else None
    rep["opening"] = post[0] if post else None
    rep["opening_found"] = dg is not None
    # attempts: the pre-checkpoint records the final state kept, plus placeholders for what the 200-cap dropped
    at_all = [a for a in final.get("attempts") or [] if isinstance(a, dict)]
    kept = [dict(a) for a in at_all if a.get("run_id") in pre_ids]
    pads = []
    want = pd["attempts"] if pd and pd.get("attempts") is not None else None
    if want is not None and want > len(kept) and len(at_all) >= ATTEMPT_CAP:
        # the cap keeps the newest 200 by time: every dropped record is older than the oldest kept one, so only the runs that started
        # before it can have lost records (a later run without a kept record made no check)
        first_kept = min((a.get("t") or "" for a in at_all), default="")
        lost = [r for r in pre if (r.get("started") or "") <= first_kept]
        for r in lost:
            b = _run_best(src, r.get("run_id"), name)
            if b is not None and len(kept) + len(pads) < want:
                pads.append({"sha": None, "tokens": None, "heartbeats": None, "ok": True, "error": None, "run_id": r.get("run_id"),
                             "t": r.get("started") or "", "score": b, "restored": "placeholder: the run's end best (summary.json); the 200-record cap dropped its attempts"})
        r0 = (lost or pre or [{}])[0]
        while len(kept) + len(pads) < want:
            pads.append({"sha": None, "tokens": None, "heartbeats": None, "ok": False, "error": "(record dropped by the 200-attempt cap)",
                         "run_id": r0.get("run_id"), "t": r0.get("started") or "", "restored": "placeholder"})
    attempts = sorted(kept + pads, key=lambda a: a.get("t") or "")[-ATTEMPT_CAP:]
    rep.update(attempts_kept=len(kept), attempts_placeholders=len(pads), attempts_final_capped=len(at_all) >= ATTEMPT_CAP)
    # winning edits: the final state's pre-checkpoint wins, plus those the opening shows that its 30-cap dropped
    led = final.get("ledger") or {}
    wins = [dict(w) for w in led.get("wins") or [] if isinstance(w, dict) and w.get("run_id") in pre_ids]
    have = {(w.get("run_id"), w.get("check")) for w in wins}
    added = [w for w in (pd or {}).get("wins") or [] if (w["run_id"], w["check"]) not in have and w["run_id"] in pre_ids]
    order = {r.get("run_id"): i for i, r in enumerate(pre)}
    wins = sorted(wins + added, key=lambda w: (order.get(w.get("run_id"), 1 << 30), float(w.get("check") or 0)))[-30:]
    rep.update(wins_kept=len(wins) - len(added), wins_from_opening=len(added))
    state = {"problem": name, "best": best, "attempts": attempts, "runs": [dict(r) for r in pre], "api_spend": spend}
    ledger = {"wins": wins} if wins else {}
    if pd and pd.get("dead"):
        ledger["dead_names"] = list(pd["dead"])
    if ledger:
        state["ledger"] = ledger
    bm = {k: v for k, v in (final.get("budget_milestones") or {}).items() if isinstance(v, dict) and float(v.get("spend") or 0) <= spend + 1e-9}
    if bm:
        state["budget_milestones"] = bm
    rt = [r for r in final.get("router") or [] if at is not None and (_ts(r.get("at")) or math.inf) < at]
    if rt:
        state["router"] = rt
    fl = _profile_floor(src, ws, [r.get("run_id") for r in pre])
    if fl is not None:
        state["hb_floor"] = fl
    rep["dropped_keys"] = sorted(k for k in final if k not in state and k not in ("profile_cache",))
    # notes.md: the replay of the sessions' writes when it is verified; else as the first post-checkpoint session was shown it (its first
    # 3000 characters); the final file when no session followed
    seen = (pd or {}).get("notes")
    shown = lambda t: t.strip()[:3000] if len(t.strip().splitlines()) > 1 else None   # noqa: E731  (what agent.py's digest shows of notes.md)
    full = notes_replay(src, name, [r.get("run_id") for r in runs_all])
    exact_final = False
    try:
        exact_final = full["text"] == (d / "notes.md").read_text()
    except OSError:
        pass
    pre_rep = notes_replay(src, name, [r.get("run_id") for r in pre])
    pre_clean = not pre_rep["unsupported"] and not pre_rep["missing"]
    rep["notes_replay"] = {"final_exact": exact_final, "pre_unsupported": len(pre_rep["unsupported"]), "pre_missing": len(pre_rep["missing"]),
                           "prefix_match": (shown(pre_rep["text"]) == seen) if pd is not None else None}
    if (pd is not None and (exact_final or pre_clean) and shown(pre_rep["text"]) == seen) or (pd is None and post and exact_final):
        notes = pre_rep["text"]
        rep["notes"] = "replay (" + ("verified: every session replayed gives the final notes.md" if exact_final
                                     else "pre-checkpoint writes all parsed; the opening's 3000 characters match") + ")"
        rep["notes_truncated"] = False
    elif pd is not None:
        notes = (seen.strip() + "\n") if seen else NOTES_HEAD
        rep["notes"] = "opening" + (" (truncated at 3000 chars)" if pd.get("notes_truncated") else "")
        rep["notes_truncated"] = bool(pd.get("notes_truncated"))
    elif not post:
        try:
            notes = (d / "notes.md").read_text()
        except OSError:
            notes = NOTES_HEAD
        rep["notes"] = "final (no session after the checkpoint)"
    else:
        notes = NOTES_HEAD
        rep["notes"] = "unknown (the first post-checkpoint session's opening was not found): empty notes"
    # scratch files last written before the checkpoint (their content then is their content now)
    files, skipped = [], 0
    if at is not None and d.is_dir():
        for f in sorted(d.iterdir()):
            if not f.is_file() or f.name in OWN_FILES or f.name.endswith(".tmp"):
                continue
            if f.stat().st_mtime < at:
                files.append((str(f), f.name, "file"))
            elif f.suffix == ".jsonl":
                files.append((str(f), f.name, "jsonl-before"))   # lines stamped before the checkpoint only
            else:
                skipped += 1
    rep.update(scratch_files=len(files), scratch_skipped=skipped)
    # the check: the restored digest against the opening the source's next session got (best line excluded)
    if dg is not None:
        mine = digest_of(state, notes, post[0])
        same = _drop_best(mine) == _drop_best(dg)
        rep["digest_match"] = same
        if not same:
            a_, b_ = _drop_best(mine).split("\n"), _drop_best(dg).split("\n")
            rep["digest_diff_lines"] = sum(1 for x, y in zip(a_, b_) if x != y) + abs(len(a_) - len(b_))
            rep["digest_first_diff"] = next((i for i, (x, y) in enumerate(zip(a_, b_)) if x != y), min(len(a_), len(b_)))
    else:
        rep["digest_match"] = None
    return {"state": state, "notes": notes, "files": files, "report": rep, "at": at}


def _jsonl_before(src_path: str, at: float) -> str:
    out = []
    for l in Path(src_path).read_text().splitlines():
        try:
            d = json.loads(l)
        except ValueError:
            continue
        t = _ts(d.get("t") or d.get("at")) if isinstance(d, dict) else None
        if t is not None and t < at:
            out.append(l)
    return "\n".join(out) + ("\n" if out else "")


# ---------------------------------------------------------------------------------------------------------------------------- the plan
def plan(src: Source, names: list, start_at: float, kind: str, cap: float, top: float, history: str = "restore", check: bool = True) -> dict:
    """Every row's checkpoint item, inherited spend and remaining budget (no write). Rows without an item, or above the cap, are listed
    under `refused`. With `check` and history restore, each row's restore is computed in memory and its digest check reported."""
    rows, refused = {}, {}
    for n in names:
        try:
            ck = checkpoint_item(src, n, start_at, kind)
        except Refused as e:
            refused[n] = str(e); continue
        if ck["spend"] > cap + 1e-9:
            refused[n] = f"inherited spend ${ck['spend']:.4f} > cap ${cap:.2f}"; continue
        r = {"step": ck["step"], "score": ck["score"], "sha": ck["sha"], "at": ck["at"], "inherited": ck["spend"],
             "to_top": round(max(0.0, top - ck["spend"]), 4), "to_cap": round(cap - ck["spend"], 4),
             "lineage": lineage_cut((src.lineage() or {}).get(n), start_at)}
        if check and history == "restore":
            try:
                r["restore"] = restore(src, n, ck, start_at, history)["report"]
            except Refused as e:
                refused[n] = str(e); continue
        rows[n] = r
    worst = round(sum(r["to_cap"] for r in rows.values()), 4)
    dm = [r.get("restore", {}).get("digest_match") for r in rows.values()]
    return {"source": str(src.run_dir), "source_set": src.set, "source_arm": src.arm, "start_at": start_at, "item": kind, "history": history,
            "cap": cap, "top": top, "rows": rows, "refused": refused, "worst_case_usd": worst,
            "inherited_usd": round(sum(r["inherited"] for r in rows.values()), 4),
            "digest_match": {"yes": sum(1 for x in dm if x is True), "no": sum(1 for x in dm if x is False), "n/a": sum(1 for x in dm if x is None)}}


def items_sha(p: dict) -> str:
    """One hash over the rows' checkpoint items (step, proof sha, spend): frozen with the run, so a resume never mixes sources."""
    h = hashlib.sha256()
    for n in sorted(p["rows"]):
        r = p["rows"][n]
        h.update(f"{n}\0{r['step']}\0{r['sha']}\0{r['inherited']:.6f}\n".encode())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------------------------------------------------------- seeding
def _setup_worktree(S, ref: str, say) -> None:
    """The new arm's worktree at the router's frozen --ref, as hx_heldout.main sets it up before every ladder (full sha, env links)."""
    import hx_heldout as H
    full = subprocess.run(["git", "rev-parse", ref], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if not full:
        raise Refused(f"--ref {ref}: not a commit of this checkout")
    H.setup_worktree(S, full, say)


def _env_problems(S) -> list:
    """Why the new worktree cannot compile (the empty-envs incident): fewer than MIN_ENVS entries in envs/, or a pin without its env."""
    import hx_heldout as H
    n = len(list((S.wt / "envs").iterdir())) if (S.wt / "envs").is_dir() else 0
    out = [f"{S.wt}/envs holds {n} link(s) (< {MIN_ENVS})"] if n < MIN_ENVS else []
    if hasattr(S, "rows"):
        miss = H.missing_envs(S)
        if miss:
            out.append(f"no built environment for {', '.join(miss)}")
    return out


SETUP = _setup_worktree       # tests inject a no-op (no git worktree)
ENV_CHECK = _env_problems     # tests inject lambda S: []


def seed_all(src: Source, S, names: list, p: dict, A, say, rowstore, ledger) -> dict:
    """Seed the new arm's work root (once per row; a resume finds each row's SEED_MARK and leaves the row alone). `rowstore(name)` and
    `ledger(name)` are the router's RowStore / RowLedger factories. Returns {"seeded": [...], "kept": [...]}. Raises Refused."""
    if (Path(S.wt) / S.root).resolve() == src.work.resolve():
        raise Refused("the target work root is the source's own work root: a checkpoint start never writes into its source")
    SETUP(S, A.ref, say)
    bad = ENV_CHECK(S)
    if bad:
        raise Refused("; ".join(bad))
    work = Path(S.wt) / S.root
    # review 2026-10-26: refusals name rows as row#k (set order, the router's --anon tags); the masker only catches 16-character prefixes
    order = list(getattr(S, "names", None) or names)
    tag = lambda n: f"row#{order.index(n):02d}" if n in order else "row#?"   # noqa: E731
    seeded, kept = [], []
    todo = []
    for n in names:
        r = p["rows"][n]
        d = work / safe(n)
        mark = d / SEED_MARK
        if (d / "state.json").exists():
            try:
                m = json.loads(mark.read_text())
            except (OSError, ValueError):
                m = None
            if not m or m.get("source") != p["source"] or m.get("step") != r["step"] or m.get("sha") != r["sha"]:
                raise Refused(f"{d.parent.name} {tag(n)}: a work dir with a state.json this start did not seed (another run of "
                              "this arm?): use a new --arm")
            kept.append(n); continue
        todo.append(n)
    ready = {}
    for n in todo:   # review 2026-10-26: every row's restore before the first write (a refusal on a later row leaves nothing half seeded)
        try:
            ck = checkpoint_item(src, n, p["start_at"], p["item"])
            ready[n] = restore(src, n, ck, p["start_at"], p["history"])
        except Refused as e:
            raise Refused(f"{tag(n)}: {e}") from None
    for n in todo:   # all checks passed: write
        r, res = p["rows"][n], ready[n]
        d = work / safe(n); d.mkdir(parents=True, exist_ok=True)
        for sp, fname, kind in res["files"]:
            if kind == "jsonl-before":
                (d / fname).write_text(_jsonl_before(sp, res["at"]))
            else:
                shutil.copy2(sp, d / fname)
        (d / "notes.md").write_text(res["notes"])
        (d / "best.lean").write_text(res["state"]["best"]["proof"]); (d / "candidate.lean").write_text(res["state"]["best"]["proof"])
        prov = {"source": p["source"], "source_arm": src.arm, "start_at": p["start_at"], "step": r["step"], "sha": r["sha"], "score": r["score"],
                "inherited": r["inherited"], "history": p["history"], "restore": res["report"], "at": now()}
        _write_json(d / SEED_MARK, prov)
        _write_json(d / "state.json", res["state"])   # last: a seeded row is one whose state.json exists next to a matching mark
        seeded.append(n)
    # the rows' briefs (the source arm's auto-brief: the same brief per row), never overwriting one
    ab_src, ab_dst = src.work / "_autobrief", work / "_autobrief"
    nb = 0
    if ab_src.is_dir():
        ab_dst.mkdir(parents=True, exist_ok=True)
        for n in names:
            f = ab_src / f"{safe(n)}.json"
            if f.is_file() and not (ab_dst / f.name).exists():
                shutil.copy2(f, ab_dst / f.name); nb += 1
    # the lineage (hx_heldout reads <out>/lineage.json): rows not there yet get the source's entry cut at the checkpoint
    lp = Path(S.out) / "lineage.json"
    lin = json.loads(lp.read_text()) if lp.exists() else {}
    for n in names:
        if n not in lin:
            lin[n] = p["rows"][n]["lineage"]
    Path(S.out).mkdir(parents=True, exist_ok=True)
    _write_json(lp, lin)
    # the router's per-row records: provenance (with the restore report) on the row store, the inherited spend on the row ledger
    for n in names:
        r = p["rows"][n]
        rs = rowstore(n)
        if "start_from" not in rs.d:
            try:
                mark = json.loads((work / safe(n) / SEED_MARK).read_text())
            except (OSError, ValueError):
                mark = {}
            rs.d["start_from"] = {"source": p["source"], "source_arm": src.arm, "start_at": p["start_at"], "step": r["step"], "sha": r["sha"],
                                  "score": r["score"], "inherited": r["inherited"], "history": p["history"], "restore": mark.get("restore")}
            _write_json(rs.path, rs.d)
        led = ledger(n)
        if "inherited" not in led.d:
            led.d["inherited"] = {"usd": r["inherited"], "source": p["source"], "start_at": p["start_at"]}
            led.set("sessions", r["inherited"])   # the ladder label carries state.json api_spend, which starts at the inherited spend
    return {"seeded": seeded, "kept": kept, "briefs": nb}
