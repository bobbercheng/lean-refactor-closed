"""Agentic refactoring harness: the model gets a workspace and tools
(read_file, write_file, lean_check, finish) and iterates until its turn
budget runs out. Every compiling lean_check result is scored and recorded, so
the harness keeps the best candidate even if the model never calls finish.

Runs against the z.ai Anthropic-compatible endpoint (dev-only) or any
Anthropic-compatible server (self-served vLLM with an Anthropic shim later).
"""
from __future__ import annotations

import argparse, json, math, os, re, sys, time, hashlib, pathlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:   # the Anthropic SDK serves only the z.ai / OpenRouter / self-test endpoints; replication runs --endpoint openai without it
    import anthropic  # noqa: E402
    from llm.zai_client import _key, BASE_URL  # noqa: E402
except ImportError:   # 2026-10-09: the organizers replicate on their own server, so everything not essential is optional
    import types

    def _no_sdk(*_a, **_k):
        raise SystemExit("the anthropic package is needed only for --endpoint zai/openrouter: pip install anthropic, or use --endpoint openai")
    anthropic = types.SimpleNamespace(Anthropic=_no_sdk, RateLimitError=type("RateLimitError", (Exception,), {}),
                                      APIStatusError=type("APIStatusError", (Exception,), {}))   # `except anthropic.X` clauses still evaluate
    _key, BASE_URL = _no_sdk, None
from scorer.tokenize import split_declaration, count_tokens  # noqa: E402
from scorer.forbidden import check_forbidden  # noqa: E402
from scorer.compile import compile_putnam, compile_project, file_prefix  # noqa: E402
from scorer.score import len_pct, hb_pct_local, compat_pct, problem_score  # noqa: E402
from probe.verify_candidates import newest_first  # noqa: E402
from harness.leantools import digest_error  # noqa: E402
from harness import golf as G  # noqa: E402  (B62c --mode golf; inert in the default mode)
from scorer.accept import decide as _decide, exact_score as _exact  # noqa: E402

TOOLS = [
    {"name": "read_file", "description": "Read a file in the workspace. Files: original.lean (the reference declaration, compiles), context.lean (imports/header or the surrounding file prefix the declaration lives in — large, read ranges), candidate.lean (your current attempt). Optional start/end line numbers (1-based, inclusive).",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write a file in the workspace (normally candidate.lean with the COMPLETE declaration: the statement byte-for-byte as in original.lean, then `:=` and your proof). Writing candidate.lean also runs lean_check on it and returns the result, so no separate lean_check is needed.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "lean_check", "description": "Compile the full declaration in a workspace file (default candidate.lean) inside the real project environment on the primary toolchain. Returns ok, errors (line:col relative to the declaration), warnings, heartbeats, token count, and the predicted score vs the reference. If it compiles and improves, also reports compatibility on the other toolchains. Each call costs a few seconds; use it often.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "lean_run", "description": "Run a scratch Lean snippet in the problem's real environment (same imports/context as the declaration) and return the compiler messages. Use it to discover lemma names and tactics: e.g. `#check @SomeLemma`, `example : <goal> := by exact?`, `example ... := by simp?`, `#print axioms`. The snippet is appended after the context; do not repeat the imports. Each run costs a few seconds.",
     "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
    {"name": "shell", "description": "Run a shell command (bash) in the workspace for exploration: grep/rg the project's Lean sources and Mathlib for lemma names and proof idioms, `git log -p`/`git show` on the problem's file in the project clone to find how the same proof was later simplified upstream, ls/cat/head/sed -n to read other files, or `lake env lean` on a scratch file. Timeout 120 s, output truncated. No network, no writes outside the workspace, no rm/mv/git checkout/lake build.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "finish", "description": "Stop when you believe the best candidate has been checked (the harness keeps the best compiling candidate it has seen). Accepted only after at least 5 lean_checks in this run or in the last 3 turns; earlier calls are rejected with guidance.",
     "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}}},
]

SYSTEM = """You are a Lean 4 proof engineer working in a small workspace with tools. Goal: produce a proof of the SAME theorem that scores higher than the reference on
  score = mean(length_reduction%, heartbeat_reduction%, compatibility%),
where length = token count of the proof body (every bracket/operator is a token, dotted names are one token, comments don't count), heartbeats = elaboration cost, compatibility = fraction of listed toolchains on which it compiles unchanged.

Workflow (R3, operator 2026-10-08): REWRITE FIRST. Read original.lean (and context.lean if you need surrounding definitions) for its mathematical plan, then write your own proof of that plan top-down: outline it with `sorry` holes, check the outline with lean_skeleton (it returns each hole's goal), fill one hole at a time, then lean_check the complete candidate. EDIT incrementally (change one thing, lean_check, keep what compiles) only when the problem is too hard to write fresh, or to polish a proof that already compiles; if edits stall (about 8 checks without a new best), start a NEW rewrite with a different architecture instead of more edits. The harness remembers the best compiling candidate; a failed check costs nothing but a turn, so check early and often (every 1–2 turns). A rewrite built hole by hole does not fail all at once; never write a large proof blind and check it only at the end. lean_check returns linter_hints: tactics that do nothing and unused simp arguments are free deletions — do those first. Use lean_run to find lemma names and closing tactics (`example : <goal> := by exact?`, `simp?`, `#check`), and shell (grep/rg over the sources, `git log -p` on the file to see how upstream later simplified this proof) when you need real names or idioms rather than guesses; inside lean_run snippets `sorry` IS allowed, so you can test a proof skeleton with `sorry` placeholders and read the remaining goals. Never put sorry/admit/axiom/native_decide in candidate.lean, never add auxiliary declarations, `open`, or `set_option` outside the proof. CLOSERS: AUTOMATION FIRST (`grind` with lemma hints, forward hints `grind [→ lemma]` for lemmas concluding ∃ or a constructor, `simp`, `omega`, `aesop`, `solve_by_elim`, `linear_combination`): it is robust, while hand-written terms are the most common failure (wrong hypothesis, argument order). Once the proof compiles, replace an automation call by an explicit term only where the `axis` in lean_check says the heartbeats saved are worth more than the tokens added, and keep the swap only if it compiles and scores higher; on small proofs each `grind` call is a large share of the heartbeats, so count calls. When out of ideas or budget, call finish."""


_CLAIM_RE = re.compile(r"\b(unavoidable|impossible|cannot|can't|does not exist|doesn't exist|never|not needed|no longer needed|floor|minimal|tight|must|required|only way|no way|dead end|confirmed negative)\b", re.I)


from llm.junk import degenerate_tail, junk_reason   # noqa: E402  (2026-10-14: one detector for the stream guard and the history guard)

# b65 (2026-10-27): tool results as compact JSON with unicode kept (--compact-tool-json). Measured on
# it2a's tool results (o200k): -13% of the JSON tool-result tokens, more on lean_check (-20%, its goal states were \u-escaped). Off by default:
# the default output is byte-identical to before.
_TOOL_JSON_COMPACT = False


def _tool_json(obj, ensure_ascii: bool = True) -> str:
    """A tool result for the model: compact (no spaces, unicode kept) under --compact-tool-json, else json.dumps as before."""
    if _TOOL_JSON_COMPACT:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(obj, ensure_ascii=ensure_ascii)


def unverified_claims(notes: str, limit: int = 8) -> list[str]:
    """Negative / absolute claims in notes.md without a `[tested: …]` tag (cycle 36). Section headers ("What FAILED (do not retry)") and hard
    submission rules (statement byte-identical, forbidden constructs) are skipped: those are not hypotheses."""
    out = []
    for line in notes.splitlines():
        s = line.strip(" -*#>\t")
        if not (30 <= len(s) <= 220) or not _CLAIM_RE.search(s) or re.search(r"\[tested", s, re.I):
            continue
        if re.search(r"statement|byte-for-byte|forbidden|sorry|axiom|native_decide", s, re.I):
            continue
        if s not in out:
            out.append(s)
    return out[:limit]


NOTES_VIEW_CAP = 3000   # characters of notes.md the opening shows (every view)


def notes_view_text(notes: str, view: str = "head", cap: int = NOTES_VIEW_CAP) -> str:
    """b64 F2 (--notes-view; docs/first_half_gap.md §3i): the part of notes.md (append-only, so the newest entries are last) the opening shows.
    head (the default): notes[:cap], as before. tail: the newest part, cut at a line start, under a marker naming the omitted older span
    (from round 3, 9-15 of 15 sessions per arm had their newest notes cut by head). headtail: the first ~1,000 characters (the plan) and the
    newest part (harness/cc_levers.notes_digest). Notes within the cap are shown whole by every view."""
    if view == "head" or len(notes) <= cap:
        return notes[:cap]
    if view == "headtail":
        from harness.cc_levers import notes_digest
        return notes_digest(notes, cap)
    if view != "tail":
        raise ValueError(f"notes view {view!r}: one of head, tail, headtail")
    t = notes[len(notes) - (cap - 120):]   # the marker below is under 120 characters: the view stays within cap
    t = t[t.find("\n") + 1:] if "\n" in t else t
    return f"[... the oldest {len(notes) - len(t)} chars of notes.md omitted here (read_file notes.md for them); the newest part follows ...]\n{t}"


def best_so_far(b: dict, holder: str = "candidate.lean") -> str:
    """The opening's best-so-far sentence (Workspace.digest; b92: re-rendered when the auto-brief installs its start, docs/b92_opening_fix.md)."""
    return f"Best so far: score {b['score']} (tokens {b.get('tokens')}, heartbeats {b.get('heartbeats')}); {holder} holds it."


def respan(text: str, edits: list) -> str | None:
    """b92 (docs/b92_opening_fix.md): replace recorded spans of the opening message. edits = [(start, end, old, new)], spans of `text` that do
    not overlap; every span must still hold `old`, else None (the caller leaves the opening as it is). Applied from the last span back."""
    eds = sorted(edits, key=lambda x: (x[0], x[1]))
    for i, (s_, e_, old, _new) in enumerate(eds):
        if not (0 <= s_ <= e_ <= len(text)) or text[s_:e_] != old or (i and eds[i - 1][1] > s_):
            return None
    for s_, e_, _old, new in reversed(eds):
        text = text[:s_] + new + text[e_:]
    return text


_REF_HBS: dict | None = None
RESCORE_H_TOL = 0.5


def rescore_best(row: dict, b: dict) -> dict:
    """2026-11-01 (closed run 2): the stored best's score on the CURRENT reference heartbeats. A best recorded on another reference (a
    reference corrected after sessions had banked bests on a placeholder) kept its old, higher score, so every correctly scored candidate
    lost against it. Only a REFERENCE change triggers it: the record's own stored H must differ from H on the current reference by more
    than RESCORE_H_TOL points (a record's rounding: 0.01). Then the score is
    recomputed from the record's tokens, heartbeats and Z with the formula lean_check uses. A record without tokens, heartbeats or H,
    or whose H matches the current reference, is returned as is (other writers' scores, e.g. a paired exact read, are never touched)."""
    global _REF_HBS
    if not b or not b.get("proof") or b.get("tokens") is None or b.get("heartbeats") is None or b.get("H") is None \
            or not row.get("proof_length"):
        return b
    if _REF_HBS is None:
        f = ROOT / "data/benchmark_heartbeats.jsonl"
        _REF_HBS = {json.loads(l)["name"]: json.loads(l)["heartbeat"] for l in f.open() if l.strip()} if f.exists() else {}
    try:
        H = hb_pct_local(row["name"], int(b["heartbeats"]), _REF_HBS.get(row["name"]))
        if abs(H - float(b["H"])) <= RESCORE_H_TOL:
            return b
        L = len_pct(row["proof_length"], int(b["tokens"]))
        sc = problem_score(True, L, H, float(b.get("Z", 100.0)))
    except (TypeError, ValueError, KeyError):
        return b
    return dict(b, score=sc, L=round(L, 2), H=round(H, 2), rescored_from=b.get("score"))


class Workspace:
    """Per-problem persistent workspace (keyed by problem, not by run):
    original.lean, context.lean, candidate.lean (working copy), best.lean,
    notes.md (model-owned memory), state.json (best record + attempt history)."""

    def __init__(self, root: Path, row: dict, version: str, fresh: bool = False):
        self.root = root; self.row = row; self.version = version
        root.mkdir(parents=True, exist_ok=True)
        (root / "original.lean").write_text(row["src"].rstrip() + "\n")
        ctx = row["header"] if row["source"] == "putnambench" else file_prefix(row, version)
        (root / "context.lean").write_text(ctx)
        self.state_path = root / "state.json"
        if fresh or not self.state_path.exists():
            if fresh and self.state_path.exists():
                self.state_path.unlink()   # otherwise save()'s merge-with-disk resurrects the old runs/attempts (A100 POC: aborted runs gave fresh problems 6-turn budgets)
            self.state = {"problem": row["name"], "best": {"score": 33.33, "proof": None, "tokens": row["proof_length"], "heartbeats": None}, "attempts": [], "runs": []}
            (root / "candidate.lean").write_text(row["src"].rstrip() + "\n")
            if not (root / "notes.md").exists() or fresh:
                (root / "notes.md").write_text("# Notes (yours to keep; persisted across runs)\n")
        else:
            self.state = json.loads(self.state_path.read_text())
            _cur = self.state.get("best") or {}
            _b = rescore_best(row, _cur)
            if _b is not _cur:
                print(f"{row['name'][:18]:18s} stored best rescored on the current reference: {_b.get('rescored_from')} -> {_b['score']}", flush=True)
                self.state["best"] = _b
            best = self.state["best"].get("proof")
            (root / "candidate.lean").write_text((best or row["src"]).rstrip() + "\n")
        self.save()

    def save(self) -> None:
        # merge with whatever another concurrent run wrote: keep the higher best, union attempts by sha
        try:
            disk = json.loads(self.state_path.read_text())
            _db = rescore_best(self.row, disk.get("best") or {})   # a disk best on an older reference never wins on its old score
            if _db is not disk.get("best") and _db:
                disk["best"] = _db
            _own = getattr(self, "own_shas", None)   # B62c golf: a best of this session's own lineage is replaced by a paired exact comparison,
            if _db.get("score", 0) > (self.state.get("best") or {}).get("score", 0) and not (   # not by its older rounded stored score
                    _own is not None and hashlib.sha256((_db.get("proof") or "").rstrip().encode()).hexdigest()[:12] in _own):
                self.state["best"] = disk["best"]
            seen = {(a.get("sha"), a.get("run_id")) for a in self.state.get("attempts", [])}
            for a in disk.get("attempts", []):
                if (a.get("sha"), a.get("run_id")) not in seen:
                    self.state.setdefault("attempts", []).append(a)
            self.state["attempts"] = sorted(self.state["attempts"], key=lambda a: a.get("t", ""))[-200:]
            known = {r.get("run_id") for r in self.state.get("runs", [])}
            self.state.setdefault("runs", []).extend(r for r in disk.get("runs", []) if r.get("run_id") not in known)
        except Exception:  # noqa: BLE001
            pass
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=1))
        if self.state["best"].get("proof"):
            (self.root / "best.lean").write_text(self.state["best"]["proof"].rstrip() + "\n")

    def record_attempt(self, rec: dict) -> None:
        rec["t"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.state["attempts"].append(rec)
        self.state["attempts"] = self.state["attempts"][-200:]
        self.save()

    def digest(self, n: int = 8, notes_view: str = "head") -> str:
        b = self.state["best"]; at = self.state["attempts"]
        lines = [f"Prior work on this problem: {len(at)} checked attempts over {len(self.state['runs'])} earlier run(s). " + best_so_far(b)]
        if at:
            lines.append("Most recent attempts (tokens, heartbeats, outcome):")
            for a in at[-n:]:
                lines.append(f"  - tok={a.get('tokens')} hb={a.get('heartbeats')} {'OK score=' + str(a.get('score')) if a.get('ok') else 'FAIL: ' + str(a.get('error', ''))[:140]}")
        wins = sorted((self.state.get("ledger") or {}).get("wins", []), key=lambda w: -w.get("d_score", 0))[:6]
        if wins:
            lines.append("WINNING EDITS from earlier runs (harness log, verbatim; the current best may have lost some after a restructure: "
                         "check each and re-apply what still fits):")
            for w in wins:
                lines.append(f"  [{w.get('run_id')} check {w.get('check')}: {w.get('d_score'):+} score, {w.get('d_tokens'):+} tokens, {w.get('d_heartbeats'):+} hb]\n"
                             + "\n".join("    " + l for l in (w.get("diff") or "").splitlines()[:12]))
        dead = (self.state.get("ledger") or {}).get("dead_names") or []
        if dead:   # harness/discover.py: unknown in this line's earlier compiles and never in one of its compiling proofs
            lines.append("NAMES THAT DO NOT EXIST in this environment (unknown in earlier runs' compiles; do not use them): "
                         + ", ".join(f"`{n}`" for n in dead[:15]))
        notes = (self.root / "notes.md").read_text().strip()
        if len(notes.splitlines()) > 1:
            lines.append("Your notes.md from earlier runs:\n" + notes_view_text(notes, notes_view))   # b64 F2 (--notes-view; head: notes[:3000])
            claims = unverified_claims(notes)
            if claims:
                lines.append("UNVERIFIED CLAIMS in these notes (cycle 36: the panel review found claims of this kind wrong on six problems: "
                             "'unavoidable', 'is the floor', 'never fires', 'needed', 'tight'; each "
                             "blocked the move that later won). Treat them as hypotheses, not facts: if one blocks your most promising idea, test it with "
                             "one cheap check first, and write the result back as `[tested: <what you ran> -> <result>]`:\n"
                             + "\n".join("  ? " + c for c in claims))
        return "\n".join(lines)

    def path(self, p: str) -> Path:
        return self.root / Path(p).name


def run_problem(name: str, args, rows, hbs, out_dir: Path) -> dict:
    row = rows[name]; versions = newest_first(row["version_info"]); primary = versions[0]
    ws = Workspace(ROOT / args.work_root / re.sub(r"[^A-Za-z0-9_.-]", "_", name), row, primary, fresh=args.fresh)
    golf = getattr(args, "mode", "default") == "golf"   # B62c (harness/golf.py): every golf branch below is off in the default mode
    ws.own_shas = set() if golf else None   # B62c: shas of the proofs this golf session started from or banked (Workspace.save)
    ws.state["runs"].append({"run_id": args.run_id, "model": args.model, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}); ws.save()
    artifact = None   # b63 item 16 (--artifact): the compiled artifact this session starts from; None in every other mode
    if getattr(args, "artifact", None) and not golf:
        try:
            from harness.artifacts import load_record as _load_art
            _apath = Path(args.artifact)   # relative to this checkout, as --brief-dir (hx_heldout stages it under the work root)
            artifact = _load_art(_apath if _apath.is_absolute() else ROOT / _apath, name, row["statement"])
            if artifact:
                (ws.root / "candidate.lean").write_text(artifact["text"].rstrip() + "\n")
                ws.state["runs"][-1]["mode"] = "artifact"; ws.state["runs"][-1]["artifact"] = {k_: artifact.get(k_) for k_ in ("sha", "kind", "source")}; ws.save()
                print(f"{name[:18]:18s} artifact session: {artifact.get('kind')} {artifact.get('sha')} with {len(artifact.get('holes') or [])} hole(s) from {artifact.get('source')}", flush=True)
            else:
                print(f"{name[:18]:18s} artifact: none for this row in {args.artifact}; plain session", flush=True)
        except Exception as _e:  # noqa: BLE001
            artifact = None; print(f"{name[:18]:18s} artifact load failed: {type(_e).__name__}: {_e}", flush=True)
    if args.endpoint == "openrouter":
        # Replication rung 2 (2026-10-06): same harness, GLM-5.3-Flash served by OpenRouter providers pinned to a
        # quantization (nvfp4 = Modal/CoreWeave). OpenRouter exposes an Anthropic-compatible Messages endpoint, so only the
        # base URL, key, model id and routing body differ.
        cl = anthropic.Anthropic(api_key=Path("~/.config/vexorium/openrouter_api_key").expanduser().read_text().strip(),
                                 base_url="https://openrouter.ai/api", timeout=1800, max_retries=0)  # SDK appends /v1/messages
        api_model = args.model if "/" in args.model else "z-ai/" + args.model
        extra_body = {"reasoning_effort": args.reasoning_effort, "reasoning": {"effort": args.reasoning_effort},
                      "provider": {"quantizations": [args.quant], "allow_fallbacks": False}}
        prov_model = f"{args.model}-{args.quant}@openrouter"
    elif args.endpoint == "openai":
        # Self-hosted rung (vLLM / SGLang OpenAI-compatible server, or any /chat/completions endpoint): llm/openai_compat.py
        # converts the Anthropic-shaped history + tools and returns a Message-like object; provenance names the serving.
        from llm import openai_compat as _oai
        cl = None
        _kp = Path(args.api_key_file).expanduser() if args.api_key_file else None
        _oai_key = _kp.read_text().strip() if _kp and _kp.exists() else "EMPTY"
        api_model = args.api_model or args.model
        # "default" sends no effort field: GLM's chat template maps only low/high and treats anything else (or nothing) as
        # max; z.ai/OpenRouter at "low" think ~3k chars per turn, this server at template "Low" thinks ~0-300, so "default"
        # is the comparable setting for self-hosted runs.
        # Same field as z.ai: vLLM's chat completions forward the top-level `reasoning_effort` into the chat-template kwargs
        # (build_chat_params in vllm-backport v0.13.1 and upstream), so the GLM template renders "Reasoning Effort: Low/High/Max"
        # from it. (An earlier claim that it was ignored came from /tokenize, which uses a different request class.)
        extra_body = {} if args.reasoning_effort == "default" else {"reasoning_effort": args.reasoning_effort}
        if args.extra_body_json:
            extra_body.update(json.loads(args.extra_body_json))
        prov_model = f"{args.model}-{args.serving_tag}@openai" if args.serving_tag else f"{args.model}@openai"
        if args.model_preset:
            _pr = MODEL_PRESETS[args.model_preset]
            extra_body = {"usage": {"include": True}}
            if args.model_preset != "deepseek-v4.1-flash" and args.reasoning_effort != "default" and not _pr.get("no_effort"):
                extra_body["reasoning"] = {"effort": args.reasoning_effort}
            extra_body.update(_pr.get("extra_body") or {})   # 2026-10-14: per-preset routing (kimi-k3-or pins tools-capable providers)
            prov_model = f"{args.model_preset}@{'clinepass' if 'cline' in _pr['base_url'] else 'azure' if '.azure.com' in _pr['base_url'] else 'openrouter'}"
    else:
        # LRA_SELFTEST_ANTHROPIC_URL: harness/selftest.py points the z.ai code path at its scripted fake server (never set in real runs)
        cl = anthropic.Anthropic(api_key=_key() if not os.environ.get("LRA_SELFTEST_ANTHROPIC_URL") else "selftest",
                                 base_url=os.environ.get("LRA_SELFTEST_ANTHROPIC_URL") or BASE_URL, timeout=1800, max_retries=0)
        api_model = args.model
        extra_body = {"reasoning_effort": args.reasoning_effort}
        prov_model = args.model + "@z.ai"
    # Bank sync (cycle 12): other runs of the SAME model/serving (e.g. the fresh z.ai control) can hold a better compiling
    # candidate than this state's best — Electromagnetism 61.6 fresh vs 57.4 resumed. Main line only (harness/work), never the
    # replication roots (their measurement must stay independent), and only records with this run's exact provenance model,
    # so OpenRouter proofs never seed the z.ai line.
    synced_note = ""
    if args.bank_sync and args.work_root.rstrip("/") == "harness/work":
        try:
            from bank.store import load_all as _bank_all
            _c = [r for r in _bank_all(name) if (r.get("provenance") or {}).get("model") == prov_model and (r.get("provenance") or {}).get("mode") == "agent" and r.get("score") and r.get("proof")]
            if _c:
                _top = max(_c, key=lambda r: float(r["score"]))
                if float(_top["score"]) > float(ws.state["best"].get("score") or 33.33) + 1e-9:
                    ws.state["best"] = {"score": float(_top["score"]), "proof": _top["proof"], "tokens": _top.get("tokens"), "heartbeats": _top.get("heartbeats"), "L": _top.get("L"), "H": _top.get("H"), "Z": _top.get("Z"), "compat": _top.get("compat")}
                    (ws.root / "candidate.lean").write_text(_top["proof"].rstrip() + "\n"); ws.save()
                    synced_note = (f"\n\nNOTE: another run of this same model ({(_top.get('provenance') or {}).get('run_id')}) found a better compiling candidate "
                                   f"(score {_top['score']}, {_top.get('tokens')} tokens, {_top.get('heartbeats')} heartbeats); candidate.lean now holds it. Continue from it.")
                    print(f"{name[:18]:18s} bank-sync: best {_top['score']} from {(_top.get('provenance') or {}).get('run_id')}", flush=True)
        except Exception as _e:  # noqa: BLE001
            print(f"{name[:18]:18s} bank-sync skipped: {_e}", flush=True)
    ver_f = (out_dir / "verified.jsonl").open("a"); log_f = (out_dir / "turns.jsonl").open("a")
    # Full trajectory (2026-10-06): every message exactly as sent/received — opening prompt, nudges,
    # assistant thinking/text/tool_use inputs, and the tool results the model saw — one JSON line per message, plus
    # per-turn meta lines (cap, stop reason, usage). probe/runs/<run>/trajectories/<problem>.jsonl ; replayable.
    traj_dir = out_dir / "trajectories"; traj_dir.mkdir(exist_ok=True)
    traj_f = (traj_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".jsonl")).open("a")
    traj_logged = 0

    def flush_traj(extra: dict | None = None) -> None:
        nonlocal traj_logged
        for i in range(traj_logged, len(msgs)):
            traj_f.write(json.dumps({"type": "message", "i": i, "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **msgs[i]}, ensure_ascii=False) + "\n")
        traj_logged = len(msgs)
        if extra:
            traj_f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **extra}, ensure_ascii=False) + "\n")
        traj_f.flush()
    # adaptive budget: spend turns where headroom is (near-ceiling problems get a short pass, hard ones a long one)
    fresh_start = False; heartbeat_first = False
    if args.adaptive_turns and not args.from_reference:   # a restart from the reference takes --turns as given (no polish cut, no second fresh start)
        b0 = float(ws.state["best"].get("score") or 33.33)
        # Cycle 10: budget follows headroom and stagnation. Near-ceiling problems that did not move in their last two
        # runs get a 10-turn polish; mid problems (45-70)
        # get 50 instead of 40.
        runs_prev = [r.get("run_id") for r in ws.state.get("runs", [])[:-1] if not _is_scout(r)]   # runs before this one, scouts excluded (cycle 27)
        recent = set(runs_prev[-2:])
        older_best = max([float(a.get("score") or 0) for a in ws.state.get("attempts", []) if a.get("ok") and a.get("run_id") not in recent] or [33.33])
        stagnant = len(runs_prev) >= 2 and (b0 - older_best) < 0.5
        args_turns = (10 if stagnant else 20) if b0 >= 80 else (60 if b0 < 45 else (50 if b0 < 70 else 40))
        # Cycle 14 "two strikes": a problem whose last two runs each gained < 0.5 (a dev row: 80 structural turns for +0.01;
        # another: 19 turns, 2 failed checks) gets a 6-turn polish this pass, whatever its score. Pass 10 spent
        # ~120 of ~450 turns on such problems. The bank sync keeps lifting them from the control line meanwhile.
        if len(runs_prev) >= 2:
            def _best_excl(excl):
                return max([float(a.get("score") or 0) for a in ws.state.get("attempts", []) if a.get("ok") and a.get("run_id") not in excl] or [33.33])
            _r1, _r2 = runs_prev[-1], runs_prev[-2]
            _b_before_r1 = _best_excl({_r1, args.run_id}); _b_before_r2 = _best_excl({_r1, _r2, args.run_id})
            if (b0 - _b_before_r1) < 0.5 and (_b_before_r1 - _b_before_r2) < 0.5:
                _fresh_prev = sum(1 for r in ws.state.get("runs", [])[:-1] if r.get("mode") == "fresh")   # scouts are tagged scout, never fresh
                if b0 < 85 and _fresh_prev >= 2:
                    # Cycle 22: two fresh starts already missed on this problem (a dev row: 3 fresh starts, 30 checks, 0 compiled;
                    # two others: 2 each, compiled but never beat the best). A third restart is waste; go structural on the stored best
                    # with a heartbeat-first brief (policy order: direct shape > search burden > clarity > brevity).
                    args_turns = 40; heartbeat_first = True
                    print(f"{name[:18]:18s} two flat runs and {_fresh_prev} fresh starts missed: structural on the best, heartbeat-first, 40 turns", flush=True)
                elif b0 < 85:
                    ws.state["runs"][-1]["mode"] = "fresh"; ws.save()
                    # Cycle 18 anchoring escape: pass 13 gave 8 such problems a 6-turn high-effort polish and every one gained 0
                    # (most never reached a check). Fresh runs found better skeletons than the resumed line (on three dev rows and
                    # three endpoints). Restart from
                    # the reference with a full budget; the stored best is kept unless beaten.
                    fresh_start = True; args_turns = 40
                    print(f"{name[:18]:18s} two flat runs ({_b_before_r2:.2f} -> {_b_before_r1:.2f} -> {b0:.2f}): FRESH START from the reference, 40 turns", flush=True)
                else:
                    args_turns = min(args_turns, 6)
                    print(f"{name[:18]:18s} two flat runs ({_b_before_r2:.2f} -> {_b_before_r1:.2f} -> {b0:.2f}): 6-turn polish", flush=True)
    else:
        args_turns = args.turns
    if artifact:
        args_turns = min(args_turns, ARTIFACT_MAX_TURNS)   # plan §1.1 P: <= 12-16 turns, <= $0.50 (the caller's --budget-usd)
    if not args.upstream_history:   # R2 compliance switch: no hint to read later upstream versions of the proof
        for _n in ("SYSTEM", "SYSTEM_BASE"):
            globals()[_n] = re.sub(r",?\s*`git log -p` on the file[^,;)]*", "", globals()[_n])
    toolchains = ", ".join(versions)
    _open_spans: dict = {}   # b92: where the opening shows the best so far and candidate.lean (re-rendered when the auto-brief installs its start)
    msgs = [{"role": "user", "content": f"Problem `{name}` from the {row['source']} corpus. Reference proof body: {row['proof_length']} tokens, {hbs.get(name)} heartbeats. Toolchains: {toolchains}. "
                                         f"Workspace files: original.lean, context.lean ({'imports/header' if row['source']=='putnambench' else 'surrounding file prefix, ' + str((ws.root/'context.lean').read_text().count(chr(10))) + ' lines'}), candidate.lean. "
                                         + (f"Project sources (read-only) for grep/git: {ROOT / 'envs' / (row['source'] + '-' + primary)} ; the problem's file is {row['file_path']} ; "
                                            + (f"full git history of the project (newer commits may contain a simplified version of this very proof — `git -C {ROOT / 'envs' / (row['source'] + '.git-main')} log -p --follow -- {row['file_path']} | head -400`) is in {ROOT / 'envs' / (row['source'] + '.git-main')}. "
                                               if args.upstream_history else "")   # review 2026-10-21: --no-upstream-history drops this hint too
                                            if row['source'] != 'putnambench' else f"Mathlib sources (read-only) for grep: {ROOT / 'envs' / ('mathlib-' + primary) / 'Mathlib'}. ")
                                         + f"You have {args_turns} tool turns. Keep durable insights (what worked, what failed and why, lemma names that exist) in notes.md so later runs can continue.\n\n" + ws.digest(notes_view=getattr(args, "notes_view", "head"))
                                         + ("\n\nBoth original.lean and candidate.lean are shown below: no need to read_file them, start working." if not ws.state["attempts"] else "\n\nContinue from candidate.lean (your best so far, shown below; no need to read_file it); notes.md is summarised above.")}]
    _bl0 = best_so_far(ws.state["best"]); _i0 = msgs[0]["content"].find(_bl0)   # b92: the digest's sentence (its first line)
    if _i0 >= 0:
        _open_spans["best"] = (_i0, _i0 + len(_bl0), _bl0)

    def _file_block(_fn: str, _lbl: str) -> str:   # the opening's block for one workspace file (b92: also re-rendered for an installed start)
        _txt = (ws.root / _fn).read_text().rstrip()
        if args.lean_io and _fn == "candidate.lean" and _txt == (ws.root / "original.lean").read_text().rstrip():
            return "\n\ncandidate.lean: identical to original.lean (the reference above)."   # --lean-io: no second copy
        if _txt:
            return f"\n\n{_lbl}:\n```lean\n{_txt[:12000]}\n```" + ("\n(truncated: read_file for the rest)" if len(_txt) > 12000 else "")
        return ""
    # Cycle 40: in 97 of 105 main-line runs (92%) turn 0 only read_file'd candidate.lean / original.lean. Show both up front instead.
    for _fn, _lbl in (("original.lean", "original.lean (the REFERENCE proof)"),
                      ("candidate.lean", "candidate.lean (the ARTIFACT this session starts from; best.lean holds your current best)" if artifact else "candidate.lean (your current best)")):
        _s0 = len(msgs[0]["content"])
        try:
            msgs[0]["content"] += _file_block(_fn, _lbl)
        except OSError:
            pass
        if _fn == "candidate.lean":
            _open_spans["cand"] = (_s0, len(msgs[0]["content"]), msgs[0]["content"][_s0:], _lbl)
    if args.upstream_history:   # cycle 57: the git-history lookup done once by the harness (798 model git calls in 568 trajectories)
        try:
            from harness.leantools import upstream_digest as _ud
            _up = _ud(row, primary)
            if _up:
                msgs[0]["content"] += "\n\n" + _up
        except Exception:  # noqa: BLE001
            pass
    _nn = None   # L1 (--name-neighbors; harness/name_neighbors.py): one Session per agent session (Lean query budget, disk cache, missing names)
    if getattr(args, "name_neighbors", False):
        try:
            from harness import name_neighbors as _NN
            _nn = _NN.Session(ROOT / args.work_root, row, primary, ws_root=ws.root, max_queries=args.name_neighbors_queries,
                              log=lambda m_: print(f"{name[:18]:18s} {m_}", flush=True))
            _mb = _NN.missing_block(ws.root, _nn.key())
            if _mb:
                msgs[0]["content"] += "\n\n" + _mb
        except Exception as _e:  # noqa: BLE001
            _nn = None; print(f"{name[:18]:18s} name neighbors off: {type(_e).__name__}: {_e}", flush=True)
    best = dict(ws.state["best"])
    if synced_note:
        msgs[0]["content"] += synced_note
    # 2026-10-13 --heartbeat-first (off by default; harness/cards.py HB_REWRITES): the HEARTBEAT_FIRST card with the technique cards and the
    # heartbeat-aware wording of the cards / scout / structural / heartbeat briefs, while the stored best's H points left >= its L points left
    # (always before a measured best). The system prompt's axis-conditional closer wording is set once in main().
    _hbf = False
    if getattr(args, "heartbeat_first", False):
        from harness import cards as _cards
        _hbf = _cards.gate(name, row, ws.state, hbs.get(name), log=lambda s: print(f"{name[:18]:18s} {s}", flush=True))
        ws.state["runs"][-1]["heartbeat_first"] = _hbf; ws.save()
    _hbw = (lambda s: _cards.heartbeat_aware(s)) if _hbf else (lambda s: s)
    # Per-repo automation briefs (research 2026-10-07, counts from our local envs): what each target repository's own automation
    # supports, so closers and hints match the project instead of generic Mathlib habits. Length experiment only (--length-tools).
    try:   # Tier 2 technique cards (panel R1): playbook v1 rules for the proof patterns detected in this problem
        from harness import cards as _cards
        _ctx = (ws.root / "context.lean").read_text() if (ws.root / "context.lean").exists() else ""
        _cur = (ws.root / "candidate.lean").read_text() if (ws.root / "candidate.lean").exists() else (ws.state["best"].get("proof") or row["src"])
        msgs[0]["content"] += "\n\n" + _cards.cards_for(row["statement"], _cur, _ctx, heartbeat_first=_hbf)
        print(f"{name[:18]:18s} technique cards: {', '.join(_cards.select(row['statement'], _cur, _ctx)) or 'token rules only'}", flush=True)
    except Exception as _e:  # noqa: BLE001
        print(f"{name[:18]:18s} technique cards failed: {_e}", flush=True)
    if getattr(args, "pattern_cards", False):   # 2026-10-13 (harness/pattern_cards.py; off by default): general knowledge by proof shape, never by name
        try:
            from harness.pattern_cards import pattern_cards_for as _pcf
            _pc = _pcf(row["statement"], (ws.root / "candidate.lean").read_text() if (ws.root / "candidate.lean").exists() else (ws.state["best"].get("proof") or row["src"]))
            if _pc:
                msgs[0]["content"] += "\n\n" + _pc
            ws.state["runs"][-1]["pattern_cards"] = _pc.count("PATTERN:"); ws.save()
        except Exception as _e:  # noqa: BLE001
            print(f"{name[:18]:18s} pattern cards failed: {_e}", flush=True)
    _cl0 = len(msgs[0]["content"])   # 2026-10-13 --heartbeat-first: the closed-lessons literal stays as prompt_v2.drift_nodes reads it; spliced below
    if args.closed_lessons:   # cycle 80: general habits mined from the Opus 5.5 / GPT Astra lines (docs/closed_line_lessons.md); off until a z.ai A/B
        msgs[0]["content"] += ("\n\nA HABIT OF THE STRONGEST PROVERS (general, not about this problem):\n"
            "Write each piece once: when cases or steps repeat the same tactic run, close them together (`all_goals`, `<;>`, `case A | B => tac`) "
            "instead of repeating it. `<;> first | A | B` is shorter as `any_goals A` then `all_goals B` (fewer tokens).")
    if _hbf:   # review 2026-10-13: habit 2's `any_goals A` advice made axis-conditional (cards.HB_REWRITES R13); only the text appended just above
        msgs[0]["content"] = msgs[0]["content"][:_cl0] + _hbw(msgs[0]["content"][_cl0:])
    try:   # Tier 1 lemma search pre-pass (panel R1; insight-recall benchmark 9/12 at top 10): library leads for the current proof
        from harness import lemma_search as _ls
        _cur2 = (ws.root / "candidate.lean").read_text() if (ws.root / "candidate.lean").exists() else (ws.state["best"].get("proof") or row["src"])
        _lc = bool(getattr(args, "leads_count", False))   # b64 F1 --leads-count: count budget, the wall only a backstop
        _lr = (_ls.search(name, _cur2.rstrip(), top=10, probes=True, budget=_ls.COUNT_BACKSTOP_S if _lc else 120.0, **({"count": True} if _lc else {}))
               if not golf else {})
        _sg = _lr.get("suggestions") or []
        if _sg:
            msgs[0]["content"] += ("\n\nLIBRARY LEADS for the current proof (lemma search: exact? at each goal, names ranked by match with the goal and statement, "
                                   "same-file lemmas the reference does not use, @[simp]/@[grind]/@[to_fun] lemmas, induction principles). Leads, not answers: "
                                   "check a lead's signature against the goal (lean_goals) before building on it; lean_search re-runs it after a restructure.\n"
                                   + "\n".join(f"  - {s_.get('name')} [{s_.get('source')}{', line ' + str(s_['line']) if s_.get('line') else ''}]: "
                                                f"{(s_.get('signature') or '')[:180]}  -- {(s_.get('why') or '')[:140]}" for s_ in _sg[:10]))
        print(f"{name[:18]:18s} library leads: {len(_sg)} ({_lr.get('runtime_s')} s, {_lr.get('compiles')} compiles)"
              + (f"; count budget: {_lr['count']['probes']} probes, {_lr['count']['skipped']} past the backstop, {_lr['count']['timeouts']} "
                 "compile backstop(s)" if _lr.get("count") else ""), flush=True)
    except Exception as _e:  # noqa: BLE001
        print(f"{name[:18]:18s} lemma search failed: {_e}", flush=True)
    REPO_BRIEFS = {
        "strata": "REPO AUTOMATION (Strata): NO Mathlib, NO Batteries, NO Aesop — only core tactics (grind, simp, omega, decide, cases/induction, "
                  "rfl, exact?) plus Strata's own macros (elim_err, split_contra, solve_beq, term_by_mem). Never write aesop/linarith/positivity/fun_prop/norm_num here.",
        "cslib": "REPO AUTOMATION (CSLib): built around grind — 583 `@[grind]` annotations, ~2,200 grind uses. First try `grind` with the "
                 "constructors/lemmas your proof already names as hints, e.g. `grind [→ Foo.bar, Baz.qux]`; `all_goals grind [...]` after induction/cases.",
        "physlib": "REPO AUTOMATION (PhysLib): built around simp and fun_prop (211 `@[fun_prop]` lemmas; no grind annotations). Differentiability/"
                   "continuity side goals → `fun_prop`; algebra → `simp [defs]`/`ring`; prefer `simp_all`/`simp only [...]` over long rw chains.",
        "arklib": "REPO AUTOMATION (ArkLib): omega-heavy (~1,600 uses), plus simp and aesop. Index/arithmetic side goals → `omega`; "
                  "structural goals → `simp_all`/`aesop`.",
        "leanpool": "REPO AUTOMATION (LeanPool): Mathlib-style, 289 independent projects on the newest Mathlib (counts over the pool: simp ~259k, "
                    "norm_num ~159k, simp only ~125k, simpa ~114k, omega ~96k, linarith ~78k, positivity ~34k, bound ~32k, nlinarith ~17k, "
                    "field_simp ~10k; grind rare, ~2k uses / 67 `@[grind]`; aesop ~3k; fun_prop ~5.6k). Arithmetic → `omega`/`linarith`/`nlinarith`/"
                    "`positivity`/`bound`; algebra → `simp`/`norm_num`/`field_simp`/`ring`; `grind` only with explicit hints.",
        "putnambench": "REPO AUTOMATION (PutnamBench): full Mathlib + Aesop; nlinarith/positivity/norm_num/field_simp/ring for real-analysis "
                       "inequalities, `decide`/`omega` for finite/integer facts, `exact?` for library lemmas.",
    }
    if args.length_tools and row["source"] in REPO_BRIEFS:
        msgs[0]["content"] += "\n\n" + _hbw(REPO_BRIEFS[row["source"]])
    SCOUT_BRIEFS = {
        "automation": ("SCOUT A — AUTOMATION FIRST. Aim for the shortest proof by delegating to decision procedures: `simp_all`, `simp only [...] at *`, `grind`, `omega`, "
                       "`decide`, `aesop`, `norm_num`, `positivity`, `linarith`/`nlinarith`, `fun_prop`, `ext <;> simp`. Try `by grind` / `by simp_all` / `by omega` on the whole goal "
                       "first, then on each case after ONE `cases`/`induction` with `<;>` or `all_goals`. Batch the closers with lean_check_variants. `simp only` beats `simp` on heartbeats when both compile."),
        "direct": ("SCOUT B — DIRECT / TERM MODE. Find the library lemma that closes the goal (`exact?`, `apply?`, `rw?` through lean_run; grep the project sources), then write the proof "
                   "as a term: `exact lemma a b`, anonymous constructors `⟨_, _⟩`, `fun` abstractions, `‹_›` for hypotheses, `.symm`/`.trans`/`.mp` chains, `by simpa using`. "
                   "Avoid tactic blocks except a single closer. Batch alternative lemma applications with lean_check_variants."),
        "restructure": ("SCOUT C — RESTRUCTURE. Change the proof architecture, not the spelling: a different induction/cases variable or order, symmetric cases merged, a stronger "
                        "intermediate statement via `suffices`/`have` so the cases collapse, `match`/`nomatch`/`nofun` for impossible cases, `obtain`/`rcases` patterns instead of nested "
                        "cases, `calc` collapsed to `_` steps. Batch 2-4 architectures with lean_check_variants and keep the one with the fewest tokens, then cut heartbeats."),
    }
    if args.from_reference:
        ws.state["runs"][-1]["mode"] = "scout"; ws.save()
        (ws.root / "candidate.lean").write_text(row["src"].rstrip() + "\n")
        msgs[0]["content"] += ("\n\nSCOUT RUN: candidate.lean holds the ORIGINAL reference proof. Produce a compiling candidate of your own architecture early (within 4 checks), "
                               "then shorten it; everything that compiles is scored and banked, and the stored best is kept unless you beat it.")
        # 2026-10-10 (GPT Astra's fresh starts: 4 of 5 beat the union with the best proof hidden but its size given): a blind target
        if float(best.get("score") or 33.33) > 33.34 and best.get("tokens"):
            msgs[0]["content"] += (f" BLIND TARGET: the stored best has {best.get('tokens')} tokens and {best.get('heartbeats') or '?'} heartbeats "
                                   f"(score {best.get('score')}); a structurally different proof that beats it is the goal.")
    if args.term_card:   # 2026-10-11 (a cross-model lesson: a term-mode finish was shorter and cheaper than the tactic one on a dev row)
        msgs[0]["content"] += ("\n\nTERM-MODE FINISH AND PROBE-BEFORE-COMMIT (general practices, measured on another model):\n"
            "1. Search the library for a theorem matching the WHOLE statement first (lean_search; `exact?` in lean_run): a single library "
            "lemma often closes the problem outright.\n"
            "2. Once a tactic proof compiles, try ONE variant that collapses it into a single term: chain with `.elim`, `.trans`, `.trans_eq`, "
            "`.trans_lt`, `.imp`, anonymous `fun … =>`; drop `unfold`/`dsimp`/`classical` and `simp … at` on hypotheses (let definitional "
            "unfolding happen inside the term). On algebraic/inequality chains a term proof often cuts BOTH tokens and heartbeats.\n"
            "3. Probe before you commit: test sub-terms and lemma fits in lean_run (`example : <goal> := <term>`; sorry allowed, no check "
            "spent) and only then write the full candidate.")
        print(f"{name[:18]:18s} term-mode card", flush=True)
    if args.brief_dir:   # 2026-10-10: per-problem facts-only KNOWLEDGE BRIEF (landmarks, levers, failed lists — never proofs)
        _bf = ROOT / args.brief_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".md")
        if _bf.exists():
            msgs[0]["content"] += "\n\n" + _bf.read_text()
            print(f"{name[:18]:18s} knowledge brief: {_bf.name}", flush=True)
    if args.brief != "none":
        msgs[0]["content"] += "\n\n" + _hbw(SCOUT_BRIEFS[args.brief])
        print(f"{name[:18]:18s} scout brief: {args.brief}", flush=True)
    if args_turns <= 10:   # cycle 38: short polish runs must check, not bookkeep
        msgs[0]["content"] += (f"\n\nSHORT POLISH RUN: only {args_turns} turns. Spend them on checks. Your FIRST action: one lean_check_variants call with 3-6 "
                               "independent single-edit variants of candidate.lean (re-apply WINNING EDITS the best lost, try LIBRARY LEADS, delete a `have`/`set`, "
                               "swap a closer, token micro-rules). Do not re-read notes or reorganise them; write notes.md only in your final turn.")
    hardtail_target = None
    hardtail_batches = 0   # lean_check_variants calls with >= 3 full variants (protocol step 4)
    forced_turns = 0       # turns on which the hard-tail run was restricted to the step-4 tools
    if args.strategy == "hardtail":
        # 2026-10-07: the hard tail (worst for every model, flat after many passes) needs a different strategy, not more passes.
        # Protocol: see the goals, search the library for the routine steps, then change the ARCHITECTURE under a numeric token target.
        _bt = int(ws.state["best"].get("tokens") or row["proof_length"])
        hardtail_target = max(10, int(_bt * 0.7))
        msgs[0]["content"] += (
            f"\n\nHARD-TAIL STRATEGY RUN. This problem has stayed near its current best ({ws.state['best'].get('score')}, {_bt} tokens) for many passes: "   # leak-ok: the 70% token target below is this OFF strategy's own parameter
            "local edits of the current proof are exhausted. Do NOT polish it. Follow this protocol:\n"
            "1. MAP: the goal before every step of candidate.lean is listed below (GOAL MAP); call lean_goals for more (other files, from_line).\n"
            "2. PLAN in notes.md (short): for each step, its goal in a few words and whether it is the essential idea or routine (a case that "
            "follows from a constructor, a library lemma, or simplification). Note cases that look alike: they can share one tactic.\n"
            "3. LEMMA SEARCH for the 2-3 most expensive routine steps: with lean_run, state the goal as `example (hyps…) : goal := by exact?` "
            "(also `apply?`, `rw?`, `simp?`, `grind`) and keep the lemma names / closers that work.\n"
            f"4. RESTRUCTURE: write 3-5 FULL candidates with a DIFFERENT architecture, each at most {hardtail_target} tokens (70% of the current best), "
            "and send them in ONE lean_check_variants call. Architectures to try: one `induction`/`cases` with `<;>` and a shared closer "
            "(`<;> grind [lemmas]`, `<;> simp_all`, `<;> aesop`, `<;> first | exact … | …`); a helper `have` that generalises the repeated case; "
            "a term-mode proof from the lemmas found in step 3; a different induction variable or `generalizing` set.\n"
            "5. Iterate on the best NEW architecture (errors → fix with lean_goals/lean_run). Polish only once a new architecture compiles.")
        print(f"{name[:18]:18s} hard-tail strategy: target <= {hardtail_target} tokens (best {_bt})", flush=True)
        try:   # protocol step 1 done by the harness: the model sees the goals before its first turn
            from harness import goals as _goals
            _cand = (ws.root / "candidate.lean").read_text() if (ws.root / "candidate.lean").exists() else ws.state["best"].get("proof") or ""
            _gm = _goals.goal_map(name, _cand, depth=2, total=7000)
            if not _gm.get("steps") or "Showing steps" in (_gm.get("note") or ""):
                _gm = _goals.goal_map(name, _cand, depth=1, total=7000) if not _gm.get("steps") else _gm
            if _gm.get("steps"):
                msgs[0]["content"] += ("\n\nGOAL MAP of candidate.lean (step 1 already done; lean_goals gives more, e.g. from_line=…):\n"
                                       + "\n".join(f"line {s_['line']} `{s_['tactic']}` [{s_['n_goals']} goal(s)]\n{s_['goals']}" for s_ in _gm["steps"])
                                       + (f"\n({_gm['note']})" if _gm.get("note") else ""))
                print(f"{name[:18]:18s} hard-tail goal map: {len(_gm['steps'])} steps in the opening message", flush=True)
        except Exception as _e:  # noqa: BLE001
            print(f"{name[:18]:18s} hard-tail goal map failed: {_e}", flush=True)
    if fresh_start:
        (ws.root / "candidate.lean").write_text(row["src"].rstrip() + "\n")
        msgs[0]["content"] += (f"\n\nFRESH START: the last two runs could not improve the stored best (score {best['score']}; {best.get('tokens')} tokens, "
                               f"{best.get('heartbeats') or '?'} heartbeats: the target to beat); it is anchored to one proof "
                               "skeleton. candidate.lean now holds the ORIGINAL reference proof, not the best. Ignore the old approach: read the statement, "
                               "think about the shortest overall proof strategy (induction + `simp only [defs] at *` + `grind`/`omega`, a direct lemma via "
                               "`exact?`, a different case split), write it, lean_check, iterate. The stored best is kept unless you beat it, so bold "
                               "rewrites cost nothing. notes.md still has the lemma names and pitfalls from earlier runs. "
                               "Build the new proof IN STAGES: the reference compiles, so replace one block at a time and lean_check after each, keeping a "
                               "compiling candidate in hand at all times (a whole new proof written in one shot took 10-25 turns to compile in earlier runs "
                               "and left no time to shorten it). Aim for a first compiling check within your first 6 checks.")
    # stuck-problem strategy switch: ≥2 earlier runs and still at the reference → local edits have failed; prescribe a different approach
    if len([r for r in ws.state.get("runs", []) if not _is_scout(r)]) >= 3 and float(ws.state["best"].get("score") or 33.33) < 50:
        msgs[0]["content"] += ("\n\nSTRATEGY CHANGE: earlier runs made local edits to this proof and gained little or nothing. Do not repeat that. Instead: "
                               "(1) read the whole proof and list its 3–4 most expensive or longest steps (big `simp`/`simp_all`/`omega`/`nlinarith`/`norm_num` calls, long `have` chains); "
                               "(2) for each, state the exact goal at that point with lean_run (copy the surrounding context, put `sorry` after it, read the goal from the error), then ask `exact?`, `apply?`, `simp?` or `rw?` on that goal to find a direct closer; "
                               "(3) replace one step at a time with the closer found, lean_check after each. If a `have` is only used once, inline it. "
                               "Also check the project's git history for a later simplification of this very declaration (see the shell hint above). Aim for a compiling candidate within your first 8 turns.")
    # Structural pass (cycle 11, from docs/gap_analysis_opus_vs_flash.md): the Opus/Fable lead is proof LENGTH, won by deleting
    # scaffolding and collapsing calc chains — exactly what the incremental policy discourages. Once local edits slow down
    # (gain over the last two runs < 3 points) on a problem in [50, 85), prescribe structural cuts from the current best.
    _runs_prev = [r.get("run_id") for r in ws.state.get("runs", [])[:-1] if not _is_scout(r)]
    _b = float(ws.state["best"].get("score") or 33.33)
    _older = max([float(a.get("score") or 0) for a in ws.state.get("attempts", []) if a.get("ok") and a.get("run_id") not in set(_runs_prev[-2:])] or [33.33])
    # Cycle 13: keep structural mode on while it pays. Pass 9 gained +3..+6.5 on six problems under the recipe, but the
    # plateau trigger alone would hand them back to micro-edits next pass. If the previous run was structural and gained
    # >= 1 point, stay structural.
    _nonscout = [r for r in ws.state["runs"][:-1] if not _is_scout(r)]
    _last = _nonscout[-1] if _nonscout else {}
    _before_last = max([float(a.get("score") or 0) for a in ws.state.get("attempts", []) if a.get("ok") and a.get("run_id") not in (_last.get("run_id"), args.run_id)] or [33.33])
    _keep = _last.get("mode") == "structural" and (_b - _before_last) >= 1.0
    # 2026-10-09 BFS deep dive: a --from-reference restart on a workspace with history (the variant test copies the A100 line) would
    # otherwise also get the structural brief ("cut from the current best") and the effort raise, contradicting its own restart.
    if not golf and args.strategy != "hardtail" and not fresh_start and not args.from_reference and len(_runs_prev) >= 2 and 50 <= _b < 85 and ((_b - _older) < 3.0 or _keep or heartbeat_first):   # a fresh start gets its own brief, not the structural one; hard-tail runs have their own protocol (smoke 2026-10-07: the structural brief's one-cut-at-a-time advice won, and its effort raise cost an 8k-token no-tool turn)
        ws.state["runs"][-1]["mode"] = "structural"; ws.save()
        # Cycle 17: structural rewrites need more thinking. The self-hosted A100 run at the template's max effort found a
        # much shorter structural proof of a dev row on its
        # first pass, where three structural passes at low effort left the main line at 164 tokens. Hosted endpoints
        # take the effort label, so raise it to "high" for structural-mode problems only (the escalating cap absorbs it).
        # Same logic on every endpoint (2026-10-07): the label travels in the same field everywhere. The A100's response
        # to "high" is unmeasured at scale (n=2-4 per label, spread 0-3.7k chars within one label) — open item, not a code branch.
        if args.reasoning_effort == "low":
            extra_body["reasoning_effort"] = "high"
        print(f"{name[:18]:18s} structural mode ({'kept: last run gained %.2f' % (_b - _before_last) if _keep else 'plateau'}; effort {(extra_body.get('chat_template_kwargs') or {}).get('reasoning_effort') or extra_body.get('reasoning_effort') or args.reasoning_effort})", flush=True)
        msgs[0]["content"] += _hbw("\n\nSTRUCTURAL PASS (aligned with R3, cycle 39): editing has stalled on this proof (little gain over the last two runs), so the next "
                               "gain needs a NEW ARCHITECTURE, not more edits of the current one. Rewrite top-down: outline the proof with `sorry` holes, check it with "
                               "lean_skeleton, fill one hole at a time, then lean_check. Aim the new outline at what the old one wastes: "
                               "(1) no scaffolding: no `let`/`set`/`have` used once or not at all (`set` does extra work); destructure directly; "
                               "(2) no long `calc`: rewrite the goal directly or use `_` for intermediate right-hand sides, pass side goals inline as arguments; "
                               "(3) one shared AUTOMATION closer for alike cases (`induction x <;> grind [hints]`, `all_goals simp only [...]`, `case'` + `first | …`) "
                               "instead of a hand-written term per case; "
                               "(4) LIBRARY LEADS first: a lemma that matches a block's conclusion replaces the block; "
                               "(5) no `show`/`change`/`unfold`/`dsimp` lines that only restate the goal. Keep every compiling improvement; several attempts will fail.")
    if heartbeat_first:
        msgs[0]["content"] += _hbw("\n\nHEARTBEAT FIRST: on this proof the length axis has stalled; the heartbeat axis is where points remain. Prefer, in order: "
                               "a more direct proof shape (term-mode `exact`/anonymous constructors over tactic blocks), lower search burden (`simp only [...]`/"
                               "`rw` over `simp`/`omega`/`grind`/`aesop` where both compile, `exact lemma args` over `apply`+goals), then clarity, then brevity. "
                               "Keep the candidate compiling after every edit; lean_check reports heartbeats — a cut that raises heartbeats is not a win.")
    # 2026-10-10 union push (docs/break_90_results.md): on problems where both closed lines' resumed passes had stalled, a review that named
    # concrete levers, then one budgeted batch of compiles, beat their bests on 10 of 15. Same trigger as structural mode (gain over the last two
    # runs < 3), any score band; off until a z.ai A/B.
    if args.lever_review and args.strategy != "hardtail" and not fresh_start and not args.from_reference and len(_runs_prev) >= 2 and (_b - _older) < 3.0:
        msgs[0]["content"] += _hbw(LEVER_REVIEW)   # 2026-10-13: identity unless --heartbeat-first's gate passed (HB_REWRITES R14)
        print(f"{name[:18]:18s} lever review first (gain over the last two runs {_b - _older:.2f})", flush=True)
    THINK_NUDGE = ("THINK LONGER before each tool call: in your thinking, enumerate at least three distinct proof strategies for the current goal, "
                   "estimate the token/heartbeat payoff and the risk of each, and only then choose one. A short think here wastes a check.")
    _is_structural = (ws.state["runs"][-1].get("mode") == "structural")
    think_prompt_on = args.think_prompt == "all" or (args.think_prompt == "structural" and (_is_structural or fresh_start))
    if think_prompt_on:
        msgs[0]["content"] += "\n\n" + THINK_NUDGE
        print(f"{name[:18]:18s} think-prompt on ({args.think_prompt})", flush=True)
    if getattr(args, "failed_moves", False):   # 2026-10-13 --failed-moves (off by default; docs/opus_pass2_deep_dive.md §3): REFUTED MOVES from
        # state.json attempts, against candidate.lean as this session starts (after a from-reference / fresh-start reset, so a move on lines the
        # reset removed is not listed); the runs[] entry records how many were shown (A/B audit)
        try:
            from harness import cc_levers as _LVfm
            _fm_base = (ws.root / "candidate.lean").read_text() if (ws.root / "candidate.lean").exists() else (ws.state["best"].get("proof") or row["src"])
            _LVfm.void_stale(ws.state, ws.state["best"].get("proof"))   # review 2026-10-13: a best seen only at a session start also voids
            _fm, ws.state["runs"][-1]["failed_moves"] = _LVfm.failed_moves_render(ws.state, base=_fm_base); ws.save()   # review: rows shown
            if _fm:
                msgs[0]["content"] += "\n\n" + _fm
                print(f"{name[:18]:18s} refuted moves: {ws.state['runs'][-1]['failed_moves']}", flush=True)
        except Exception as _e:  # noqa: BLE001
            print(f"{name[:18]:18s} refuted moves failed: {_e}", flush=True)
    _pre = None

    def _lint_block(_h: list) -> str:   # b92: also re-rendered from the installed start's own check
        return ("\n\nLinter hints on the current candidate (free deletions, do these first):\n" + "\n".join("  - " + h for h in _h)) if _h else ""
    _s0 = len(msgs[0]["content"])
    try:  # free deletions first: compile the current candidate once and surface the linter's hints up front
        from harness.leantools import lean_check as _lc
        _state_probe = {"best": {"score": 33.33, "proof": None}, "attempts": []}
        _pre = _lc(name, (ws.root / "candidate.lean").read_text(), _state_probe, {"run_id": args.run_id, "kind": "probe"}, None)
        if _pre.get("linter_hints"):
            msgs[0]["content"] += _lint_block(_pre["linter_hints"])
    except Exception as _e:  # noqa: BLE001
        pass
    _open_spans["lint"] = (_s0, len(msgs[0]["content"]), msgs[0]["content"][_s0:])
    checks = 0; tool_calls = 0; total_out = 0
    sig_cache = {}   # cycle 28: #check signatures looked up this run

    def comp(decl, version, count=True):
        return compile_putnam(row["header"], decl, version, count=count, timeout=900) if row["source"] == "putnambench" else compile_project(row, decl, version, count=count, timeout=900)

    def lean_mine(path: str) -> str:
        from harness import mine as _mine
        src = ws.path(path or "candidate.lean")
        if not src.exists():
            return _tool_json({"ok": False, "errors": [f"{src.name} not found"]})
        decl = src.read_text()
        res = _mine.mine(name, decl, jobs=4, log=lambda *_: None)
        if res.get("error"):
            return _tool_json({"ok": False, "errors": [res["error"]]})
        out = {"base_tokens": res["base_tokens"], "blocks": res["blocks"],
               "block_hits": {f"block {int(k) + 1}": {"closer": v[0], "tokens_saved": v[1]} for k, v in res["block_hits"].items()},
               "tail_cuts": [{"from_body_line": k + 1, "tokens_saved": s} for k, s in res["suffix_ok"]], "whole_proof_closers": res["whole_ok"]}
        if res.get("best"):
            (ws.root / "mined.lean").write_text(res["best"]["proof"].rstrip() + "\n")
            chk = json.loads(lean_check("mined.lean"))
            out["mined"] = {"how": res["best"]["how"], "tokens": chk.get("tokens"), "score": chk.get("score") or chk.get("predicted_score_if_compatible"), "ok": chk.get("ok")}
            if chk.get("new_best"):
                (ws.root / "candidate.lean").write_text(res["best"]["proof"].rstrip() + "\n")
                out["note"] = "mined.lean beats the stored best; copied to candidate.lean"
        else:
            out["note"] = "no compiling cut found; the remaining length needs a different proof shape"
        return _tool_json(out, ensure_ascii=False)

    def lean_check_variants(variants) -> str:
        nonlocal hardtail_batches
        variants = [v for v in (variants or []) if isinstance(v, dict) and (v.get("content") or "").strip()][:6]
        over = {}
        if hardtail_target:
            # Cycle 35 (hard-tail smoke 3): the forced batch held 4 local edits of the old proof (263-277 tokens vs target 203), all compiled
            # and failed. Reject variants > 115% of the target before compiling: they are not new architectures.
            for k, v in enumerate(variants):
                _b = split_declaration(v["content"].rstrip(), row["statement"])
                _n = count_tokens(_b) if _b is not None else None
                if _n is not None and _n > hardtail_target * 1.15:
                    over[k] = _n
        if len(variants) - len(over) >= 3:
            hardtail_batches += 1
        if not variants:
            return _tool_json({"ok": False, "errors": ["give 1-6 variants, each {label, content} with the FULL candidate text (statement + proof)"]})
        before = float(ws.state["best"].get("score") or 33.33)
        rows = []; best_k = None; best_s = -1.0; sigs_all = {}; dym_all: dict = {}; cf_all: dict = {}; nn_all: dict = {}
        for k, v in enumerate(variants):  # sequential: lean_check mutates shared state; the saving is in LLM turns, not compile time
            p = ws.root / f"variant_{k + 1}.lean"; p.write_text(v["content"].rstrip() + "\n")   # workspace root: ws.path() resolves basenames only
            if k in over:
                rows.append({"label": v.get("label") or f"v{k + 1}", "ok": False, "score": None, "tokens": over[k], "heartbeats": None,
                             "error": f"not compiled: {over[k]} tokens is over the hard-tail target ({hardtail_target}); this is an edit of the old proof, not a new architecture",
                             "note": None})
                continue
            _b0 = float(ws.state["best"].get("score") or 33.33)   # the best just before this variant's check (cycle 78 vs_best)
            try:
                r = json.loads(lean_check(p.name))
            except Exception as e:  # noqa: BLE001
                r = {"ok": False, "errors": [str(e)[:200]]}
            s = r.get("score")
            _vs = {}
            if args.variant_scores:   # cycle 78: compiling rows carried score null unless they beat the best (106 of 137 in A100 p6-p7),
                # so the model recomputed L/H by hand and the "not above the stored best" note never fired; give each compiling row its
                # provisional score (local heartbeats, compatibility assumed) and its distance to the best, and fill duplicates from prior
                if r.get("unchanged") and isinstance(r.get("prior"), dict):
                    r = {**r, **{k_: r["prior"].get(k_) for k_ in ("tokens", "heartbeats") if r.get(k_) is None}}
                    s = r["prior"].get("score")
                elif s is None and r.get("ok") and r.get("predicted_score_if_compatible") is not None:
                    s = r["predicted_score_if_compatible"]; _vs["score_kind"] = "provisional (compatibility not checked: not above the best)"
                if isinstance(s, (int, float)):
                    _vs["vs_best"] = round(float(s) - _b0, 2)
            rows.append({"label": v.get("label") or f"v{k + 1}", "ok": bool(r.get("ok")), "score": s, "tokens": r.get("tokens"), "heartbeats": r.get("heartbeats"),
                         "error": ((r.get("errors") or [None])[0] or None), "note": r.get("note") or r.get("auto_fixed"), **_vs})
            for c_, sig_ in (r.get("signatures") or {}).items():   # cycle 30: the assist was dropped here (0 of 17 mismatches surfaced in pass 1)
                sigs_all.setdefault(c_, sig_)
            for n_, c_ in (r.get("did_you_mean") or {}).items():
                dym_all.setdefault(n_, c_)
            for n_, c_ in (r.get("name_neighbors") or {}).items():
                nn_all.setdefault(n_, c_)
            if r.get("compat_failures") and len(cf_all) < 2:   # cycle 56: variant rows carried no compatibility result at all
                cf_all[rows[-1]["label"]] = {"compat": r.get("compat"), "failures": r["compat_failures"], "note": r.get("compat_note")}
            if r.get("ok") and isinstance(s, (int, float)) and s > best_s:
                best_s, best_k = float(s), k
        out = {"variants": rows, "best_variant": rows[best_k]["label"] if best_k is not None else None}
        _rep = next((r_["note"] for r_ in rows if r_.get("note") and "same error has now failed" in r_["note"]), None)
        if _rep:   # cycle 33: the repeated-error nudge sat inside a variant row; lean_check_variants is the most used check tool
            out["repeated_error"] = _rep
        if dym_all:
            out["did_you_mean"] = dict(list(dym_all.items())[:4])
        if nn_all:   # L1: one MAX_LINES bound over the whole batch
            out["name_neighbors"] = _nn.cap(nn_all); out["name_neighbors_note"] = _nn.note
        if cf_all:
            out["compat_failures"] = cf_all
        if sigs_all:
            out["signatures"] = dict(list(sigs_all.items())[:3])
            out["signature_note"] = "application/type mismatch in some variants: `signatures` holds the exact signature of each applied constant — match its argument order before retrying"
        if best_k is not None and best_s > before:
            (ws.root / "candidate.lean").write_text((ws.root / f"variant_{best_k + 1}.lean").read_text().rstrip() + "\n")   # cycle 49: the file holds any auto-fix
            out["note"] = f"best variant {rows[best_k]['label']} ({best_s}) beats the previous best ({before}); copied to candidate.lean"
        elif best_k is not None:
            out["note"] = f"best compiling variant {rows[best_k]['label']} scores {best_s}, not above the stored best {before}; candidate.lean unchanged"
        return _tool_json(out, ensure_ascii=False)

    def lean_search(path: str, probes: bool = False) -> str:
        from harness import lemma_search as _ls
        src = ws.path(path or "candidate.lean")
        if not src.exists():
            return _tool_json({"ok": False, "errors": [f"{src.name} not found"]})
        _lc_ = bool(probes) and bool(getattr(args, "leads_count", False))   # b64 F1 --leads-count: the tool's probes on the count budget too
        r_ = _ls.search(name, src.read_text().rstrip(), top=10, probes=bool(probes), budget=_ls.COUNT_BACKSTOP_S if _lc_ else 150.0,
                        **({"count": True} if _lc_ else {}))
        return _tool_json({"suggestions": [{k: s_.get(k) for k in ("name", "signature", "source", "line", "why")} for s_ in (r_.get("suggestions") or [])[:10]],
                           "runtime_s": r_.get("runtime_s")}, ensure_ascii=False)[:9000]

    def lean_skeleton(path: str = "", content: str = "") -> str:
        from harness import goals as _goals
        draft = content or (ws.path(path).read_text() if path and ws.path(path).exists() else "")
        if not draft.strip():
            return _tool_json({"ok": False, "errors": ["give `content` (the draft with sorry holes) or a `path` to it"]})
        if split_declaration(draft.rstrip(), row["statement"]) is None:
            return _tool_json({"ok": False, "errors": ["statement differs from the reference statement (must be byte-for-byte identical, followed by :=)"]})
        _skr = _goals.skeleton_check(name, draft.rstrip(), **({"combinators": True} if getattr(args, "skeleton_combinator_holes", False) else {}))
        if _skr.get("ok") and _skr.get("holes"):   # b63 item 16: a draft that elaborates with holes is a skeleton artifact for the C1 pass
            _skeleton_add(draft, _skr["holes"])
        return _tool_json(_skr, ensure_ascii=False)

    def lean_profile(path: str) -> str:
        from harness import profile as _prof
        src = ws.path(path or "candidate.lean")
        if not src.exists():
            return _tool_json({"ok": False, "errors": [f"{src.name} not found"]})
        decl = src.read_text().rstrip()
        sha = hashlib.sha256(decl.encode()).hexdigest()[:12]
        cache = ws.state.setdefault("profile_cache", {})
        if sha not in cache:
            cache[sha] = _prof.profile(name, decl, max_cuts=12)
            if len(cache) > 6:
                cache.pop(next(iter(cache)))
        res = cache[sha]
        if res.get("floor"):
            ws.state["hb_floor"] = res["floor"]   # every later lean_check reports heartbeat points left against the real floor
        ws.save()
        return _tool_json(res, ensure_ascii=False)

    def lean_goals(path: str, depth: int = 1, from_line: int = 0) -> str:
        from harness import goals as _goals
        src = ws.path(path or "candidate.lean")
        if not src.exists():
            return _tool_json({"ok": False, "errors": [f"{src.name} not found"]})
        return _tool_json(_goals.goal_map(name, src.read_text(), depth=2 if int(depth or 1) >= 2 else 1, from_line=int(from_line or 0)), ensure_ascii=False)

    def lean_run(code: str, neighbors: bool = True) -> str:
        import os, subprocess, uuid
        from scorer.compile import ELAN_BIN, env_dir, project_env_dir
        if row["source"] == "putnambench":
            wd = env_dir(primary); head = row["header"].rstrip() + "\n\n"
        else:
            wd = project_env_dir(row["source"], primary); head = file_prefix(row, primary).rstrip("\n") + "\n\n"
        scratch = wd / "LRAScratch"; scratch.mkdir(exist_ok=True)
        f = scratch / f"s_{uuid.uuid4().hex[:10]}.lean"; f.write_text(head + code.rstrip() + "\n")
        env = dict(os.environ, PATH=f"{ELAN_BIN}:{os.environ.get('PATH','')}")
        try:
            from scorer.memgate import run_lean
            pr = run_lean(["lake", "env", "lean", "--json", f"-M{os.environ.get('LRA_LEAN_MEMORY_MB', '16000')}", str(f.relative_to(wd))], cwd=wd, env=env, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            f.unlink(missing_ok=True); return "error: timed out after 300s"
        f.unlink(missing_ok=True)
        off = head.count("\n")
        out = []
        for line in pr.stdout.splitlines():
            if not line.startswith("{"):
                continue
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            ln = (m.get("pos") or {}).get("line", 0) - off
            if ln < 1:
                continue  # messages from the context itself
            out.append(f"[{m.get('severity')}] line {ln}: {m.get('data','')}")
        _txt = ("\n".join(out) if out else f"(no messages; exit {pr.returncode})")[:12000]
        if neighbors and _nn is not None and out:   # L1: real constants near each unknown name in the snippet's errors
            _blk = _nn.text("\n".join(out))
            if _blk:
                _txt += "\n\n" + _blk
        return _txt

    _DENY = re.compile(r"(^|[;&|]\s*)(rm|mv|chmod|chown|sudo|pip|pip3|curl|wget|ssh|scp|nc|ncat|lake\s+build|lake\s+update|lake\s+exe\s+cache|git\s+(checkout|reset|clean|commit|push|pull|stash|rebase|merge|worktree))\b")

    _LEMMA_GREP = re.compile(r"\b(grep|rg)\b.*(\b(theorem|lemma)\b|\.lake/packages|Mathlib/)")

    def shell(command: str) -> str:
        import os, subprocess
        if not args.upstream_history and re.search(r"\bgit\s+(log|show|diff|blame)\b", command):
            return "error: repository history is not available in this run (--no-upstream-history)"
        if _DENY.search(command) or re.search(r"https?://", command):
            return "error: command not permitted (no network, no writes outside the workspace, no rm/mv/git checkout/lake build)"
        for m in re.finditer(r">\s*([^\s;&|]+)", command):  # redirects must stay inside the workspace
            if m.group(1).strip("'\"") in ("/dev/null", "/dev/stdout", "/dev/stderr"):
                continue   # cycle 41: `2>/dev/null` was rejected 21-26 times per pass (a wasted turn each)
            target = Path(m.group(1)).expanduser()
            if (target.is_absolute() and not str(target.resolve()).startswith(str(ws.root.resolve()))) or (not target.is_absolute() and ".." in target.parts):
                return (f"error: redirect target {m.group(1)} is outside the workspace (only workspace files and /dev/null are allowed; "
                        "grep/sed/git output needs no redirect, it is returned to you)")
        env = dict(os.environ, PATH=f"{Path.home()}/.elan/bin:{os.environ.get('PATH','')}")
        try:
            pr = subprocess.run(["bash", "-lc", command], cwd=ws.root, env=env, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return "error: command timed out after 120s"
        out = (pr.stdout or "") + (("\n[stderr]\n" + pr.stderr) if pr.stderr else "")
        return f"exit code: {pr.returncode}\n{out}"[:12000]

    def _cand_sha() -> str | None:
        try:
            return hashlib.sha256(ws.path("candidate.lean").read_text().rstrip().encode()).hexdigest()[:12]
        except OSError:
            return None

    # Cycle 76 (--relative-error-lines, off by default): compile errors carried the scratch file's line numbers (context prefix, the
    # 9-line measure block, then the declaration) though the lean_check description promises declaration-relative ones. In A100
    # passes 5-7 all 465 failing compiles showed shifted positions and the model chased wrong lines (several dev rows). Relabel
    # `N:C:` as `line n `<that line>`, col C:` of the compiled declaration (candidate or variant), quoting the line so it can be found
    # without counting. Applied after digest_error, which cuts its head at the first `name : `. Compat compiles have no measure block.
    _rel_on = bool(getattr(args, "relative_error_lines", False))
    if _rel_on:
        from harness.leantools import head_line_count as _hlc_rel
        from scorer.compile import MEASURE_ELAB as _ME_rel
        _rel_meas = (_ME_rel + "set_option Elab.async false in\narena_measure\n").count("\n")
        _rel_head = _hlc_rel(row, primary)

    def _rel(e, text, head=None):
        if not _rel_on or not e:
            return e
        m_ = re.match(r"(\d+):(\d+):\s*", e); hd = _rel_head if head is None else head
        if not m_ or int(m_.group(1)) <= hd:
            return e
        n_ = int(m_.group(1)) - hd; ln_ = (text or "").split("\n")
        src_ = ln_[n_ - 1].strip()[:60] if 0 < n_ <= len(ln_) else ""
        return f"line {n_}" + (f" `{src_}`" if src_ else "") + f", col {m_.group(2)}: " + e[m_.end():]

    def _dup_note() -> str:
        """Cycle 34: the duplicate guard in lean_check fired 34 times in POC 2 pass 1, each a wasted turn, mostly right after the model
        rewrote (11) or shell-restored (8) candidate.lean to text it had already checked. Say so at write time, with the earlier
        result, so the model does not spend the next turn re-checking it."""
        sha = _cand_sha()
        if sha is None:
            return ""
        prior = next((a for a in reversed(ws.state["attempts"]) if a.get("sha") == sha), None)
        if prior is None:
            return ""
        _ct = (ws.root / "candidate.lean").read_text().rstrip() if _rel_on and (ws.root / "candidate.lean").exists() else ""
        res = f"compiled, score {prior.get('score')}" if prior.get("ok") else f"failed: {_rel(prior.get('error') or '', _ct)[:120]}"
        return (f"\nNOTE: candidate.lean is now byte-identical to an attempt already checked ({res}). Do not lean_check it again; "
                "edit it first (or move on to a new idea).")

    # ---- B62c golf mode (harness/golf.py; docs/scaffold_panel.md): paired exact acceptance, batched edits, the run's own pool ------------
    golf_inc = None; golf_evals = 0; golf_since_gain = 0; golf_gains = 0; golf_seen: dict = {}; golf_profiles: dict = {}
    _pool_f = ws.root / "pool.jsonl"
    _pool_shas = set()

    def _pool_entries(this_run: bool = True) -> list[dict]:
        """pool.jsonl entries (this run's only by default: the golf tools show the run's own candidates), unreadable lines skipped."""
        try:
            text = _pool_f.read_text() if _pool_f.exists() else ""
        except OSError:
            return []
        out = []
        for _l in text.splitlines():
            try:
                e_ = json.loads(_l)
            except Exception:  # noqa: BLE001
                continue
            if not this_run or e_.get("run_id") == args.run_id:
                out.append(e_)
        return out
    _pool_shas.update(e_.get("sha") for e_ in _pool_entries(this_run=True))

    def _sha12(decl: str) -> str:
        return hashlib.sha256(decl.rstrip().encode()).hexdigest()[:12]

    def _shown_adopted(decl: str) -> None:
        """b63 item 6 (contract §2): a compiling candidate whose text is a shown candidate's text counts as an adoption in shown.json."""
        shas = getattr(ws, "shown_shas", None)
        if not shas:
            return
        try:
            from harness import bank as _BK
            h = _BK.sha(decl)
            if h not in shas:
                return
            _shown_f = ws.root / "shown.json"
            _sj = json.loads(_shown_f.read_text())
            for s_ in _sj["sessions"]:
                if s_.get("run_id") == args.run_id and h not in s_["adopted_shas"]:
                    s_["adopted_shas"].append(h); s_["adopted"] = len(s_["adopted_shas"])
            _shown_f.write_text(json.dumps(_sj, ensure_ascii=False, indent=1))
        except Exception:  # noqa: BLE001
            pass

    def _bank_add(decl: str, sha: str, toks, hb, score_exact, compat=None) -> None:
        """b63 item 1 (docs/b63_logging_contract.md §2): the row's bank.jsonl, one line per compiling candidate of any session (source
        session:<run id>, parent = the stored best it was derived from, compat per pin when this check read the other pins)."""
        try:
            from harness import bank as _BK
            _par = (ws.state.get("best") or {}).get("proof")
            _BK.add(ws.root, _BK.entry(decl, f"session:{args.run_id}", tokens=toks, heartbeats=hb, score=float(score_exact), compat=compat,
                                       parent=_BK.sha(_par) if _par and _BK.sha(_par) != _BK.sha(decl) else None, run_id=args.run_id, statement=row["statement"]))
        except Exception:  # noqa: BLE001  (the bank is a ledger, never the session's failure)
            pass

    _art_lines = {l.strip() for l in (artifact["text"].split("\n")[1:] if artifact else []) if l.strip() and "sorry" not in l}
    artifact_done = [False]   # b63 item 16: a compiling candidate derived from the shown artifact has been checked in this session

    def _artifact_overlap(decl: str) -> bool:
        """A compiling candidate counts as derived from the artifact when it holds at least ARTIFACT_OVERLAP of the artifact's non-hole body
        lines verbatim (stripped), or is the artifact's own text."""
        if not _art_lines:
            return False
        ls = {l.strip() for l in decl.split("\n")[1:] if l.strip()}
        return len(_art_lines & ls) >= max(1, math.ceil(ARTIFACT_OVERLAP * len(_art_lines)))

    def _ledger_line(fn: str, rec: dict, cap: int = 40) -> None:
        """b63 item 16 (harness/artifacts.py): <ws>/skeletons.jsonl and <ws>/near_misses.jsonl, the C1 pass's sources of artifacts (--pool, the
        bank plumbing switch); the newest `cap` lines are kept, a sha is written once per session."""
        if not getattr(args, "pool", False):
            return
        try:
            f_ = ws.root / fn
            lines_ = f_.read_text().splitlines() if f_.exists() else []
            if any(f'"sha": "{rec["sha"]}"' in l and f'"run_id": "{args.run_id}"' in l for l in lines_):
                return
            lines_ = (lines_ + [json.dumps(dict(rec, run_id=args.run_id, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())), ensure_ascii=False)])[-cap:]
            f_.write_text("\n".join(lines_) + "\n")
        except Exception:  # noqa: BLE001  (a ledger, never the session's failure)
            pass

    def _skeleton_add(draft: str, holes: list) -> None:
        _b = split_declaration(draft.rstrip(), row["statement"])
        _par = (ws.state.get("best") or {}).get("proof")
        _ledger_line("skeletons.jsonl", {"sha": hashlib.sha256(draft.rstrip().encode()).hexdigest()[:12], "text": draft.rstrip(), "holes": holes, "kind": "draft",
                                         "tokens_est": count_tokens(_b) if _b is not None else None,
                                         "parent": hashlib.sha256(_par.rstrip().encode()).hexdigest()[:12] if _par else None})

    def _near_miss_add(decl: str, errors: list) -> None:
        if not errors:
            return
        _par = (ws.state.get("best") or {}).get("proof")
        _ledger_line("near_misses.jsonl", {"sha": hashlib.sha256(decl.rstrip().encode()).hexdigest()[:12], "text": decl.rstrip(),
                                           "first_error": digest_error(errors[0], 400), "parent": hashlib.sha256(_par.rstrip().encode()).hexdigest()[:12] if _par else None})

    def _pool_add(decl: str, sha: str, toks, hb, score_exact, compat=None) -> None:
        """B62a: every compiling candidate of the run, for golf's pool tool and the end stage (--pool; golf turns it on). b63: the same
        candidate goes to the row's bank.jsonl (harness/bank.py); a later call with `compat` adds the per-pin reading."""
        if compat is None:
            _shown_adopted(decl)
            if artifact and not artifact_done[0] and _artifact_overlap(decl):
                artifact_done[0] = True
                try:   # contract §2: the artifact's adoption (a compiling candidate derived from it) in shown.json
                    _shown_f = ws.root / "shown.json"; _sj = json.loads(_shown_f.read_text())
                    _sess = next((s_ for s_ in reversed(_sj.get("sessions") or []) if s_.get("run_id") == args.run_id), None)
                    if _sess is not None and artifact["sha"] not in (_sess.get("adopted_shas") or []):
                        _sess["adopted"] = int(_sess.get("adopted") or 0) + 1; _sess.setdefault("adopted_shas", []).append(artifact["sha"])
                        _shown_f.write_text(json.dumps(_sj, ensure_ascii=False, indent=1))
                except Exception:  # noqa: BLE001
                    pass
        if not getattr(args, "pool", False):
            return
        if compat is not None or sha not in _pool_shas:
            _bank_add(decl, sha, toks, hb, score_exact, compat)
        if sha in _pool_shas:
            return
        _pool_shas.add(sha)
        with _pool_f.open("a") as f_:
            f_.write(json.dumps({"sha": sha, "tokens": toks, "heartbeats": hb, "score_exact": round(float(score_exact), 6), "run_id": args.run_id,
                                 "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "proof": decl.rstrip()}, ensure_ascii=False) + "\n")

    def golf_budget_low() -> bool:
        return bool(args.model_preset) and float(ws.state.get("api_spend") or 0) >= 0.85 * args.budget_usd

    def golf_eval(decl: str) -> dict:
        """Compile and measure one candidate on the primary toolchain (no state change: safe in threads)."""
        body = split_declaration(decl, row["statement"])
        if body is None:
            return {"ok": False, "error": "statement differs from the reference statement (must be byte-for-byte identical, followed by :=)"}
        bad = check_forbidden(decl)
        if bad:
            return {"ok": False, "error": f"forbidden construct: {bad}"}
        toks = count_tokens(body)
        try:
            r = comp(decl, primary)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "tokens": toks, "error": f"compile error: {type(e).__name__}: {e}"[:300]}
        if not r.ok or r.heartbeats is None:
            return {"ok": False, "tokens": toks,
                    "error": (_rel(digest_error(r.errors[0], 300), decl) if r.errors else "compiled without a heartbeat reading")}
        return {"ok": True, "tokens": toks, "heartbeats": r.heartbeats, "L": len_pct(row["proof_length"], toks),
                "H": hb_pct_local(name, r.heartbeats, hbs.get(name))}

    def golf_consider(decl: str, ev: dict) -> tuple[bool, str, float, bool]:
        """scorer/accept.decide against this session's incumbent; a passing candidate is compiled on every pin and once more on the primary
        (the worse heartbeat reading counts), decided again, and banked. Returns (banked, reason, exact score, transient): transient = a pin
        or the confirmation compile timed out, so the verdict is not final (the caller does not cache it)."""
        nonlocal best, golf_inc, golf_since_gain, golf_gains
        # screening: the candidate's own pins are unknown yet; an incumbent below Z 100 is screened against Z 100 (the pins then decide)
        z_scr = golf_inc["Z"] if golf_inc["Z"] >= 100.0 else 100.0
        sx = _exact(ev["L"], ev["H"], golf_inc["Z"])
        ok_, why = _decide(golf_inc, {"score": _exact(ev["L"], ev["H"], z_scr), "tokens": ev["tokens"], "heartbeats": ev["heartbeats"], "Z": z_scr})
        if not ok_:
            return False, why, sx, False
        compat = {primary: True}; _to = False
        for v in versions[1:]:
            _rv = comp(decl, v, count=False); compat[v] = _rv.ok; _to = _to or bool(getattr(_rv, "timed_out", False))
        Z = compat_pct(compat)
        r2 = comp(decl, primary)
        if not r2.ok or r2.heartbeats is None:
            return False, "the confirmation compile failed", sx, bool(getattr(r2, "timed_out", False)) or _to
        hb = max(int(ev["heartbeats"]), int(r2.heartbeats))
        H = hb_pct_local(name, hb, hbs.get(name)); sx = _exact(ev["L"], H, Z)
        cand = {"score": sx, "tokens": ev["tokens"], "heartbeats": hb, "Z": Z}
        ok_, why = _decide(golf_inc, cand)
        if not ok_:
            return False, "after the confirmation compile and the pins: " + why, sx, _to
        sc = problem_score(True, ev["L"], H, Z)
        try:
            import difflib as _dl
            _d = [l for l in _dl.unified_diff((golf_inc.get("proof") or "").splitlines(), decl.splitlines(), lineterm="", n=0)
                  if l[:1] in "+-" and not l.startswith(("+++", "---"))]
            _led = ws.state.setdefault("ledger", {}).setdefault("wins", [])
            _led.append({"run_id": args.run_id, "check": checks, "d_score": round(sx - golf_inc["score"], 4), "d_tokens": ev["tokens"] - golf_inc["tokens"],
                         "d_heartbeats": hb - golf_inc["heartbeats"], "diff": "\n".join(_d)[:700]})
            ws.state["ledger"]["wins"] = _led[-30:]
        except Exception:  # noqa: BLE001
            pass
        best = {"score": sc, "score_exact": round(sx, 6), "proof": decl, "tokens": ev["tokens"], "heartbeats": hb, "L": round(ev["L"], 2),
                "H": round(H, 2), "Z": Z, "compat": compat}
        ws.state["best"] = best; ws.save()
        ver_f.write(json.dumps({"problem": name, "sha256": hashlib.sha256(decl.encode()).hexdigest()[:16], "proof": decl, "tokens": ev["tokens"],
                                "ref_tokens": row["proof_length"], "heartbeats": hb, "primary": primary, "primary_ok": True, "compat": compat,
                                "L": round(ev["L"], 2), "H": round(H, 2), "Z": Z, "score": sc, "score_exact": round(sx, 6),
                                "provenance": {"kind": ("closed-dev-only" if args.model_preset else "api-dev-only"), "model": prov_model,
                                               "run_id": args.run_id, "mode": "golf", "check": checks}}, ensure_ascii=False) + "\n"); ver_f.flush()
        print(f"{name[:18]:18s} golf eval {golf_evals}: NEW BEST {golf_inc['score']:.4f} -> {sx:.4f} tok={ev['tokens']} hb={hb} Z={Z:.0f} ({why})", flush=True)
        golf_inc = {**cand, "proof": decl}; golf_since_gain = 0; golf_gains += 1
        ws.own_shas.add(_sha12(decl))
        (ws.root / "candidate.lean").write_text(decl.rstrip() + "\n")   # lean_goals / lean_check default to candidate.lean: keep it the best
        return True, why, sx, False

    def lean_batch(inp: dict) -> str:
        nonlocal golf_evals, golf_since_gain, checks
        items = [it for it in (inp.get("items") or []) if isinstance(it, dict)][:args.golf_batch_max]
        if not items:
            return G.dumps({"ok": False, "errors": [f"give 1-{args.golf_batch_max} items, each {{label, edits: [{{find, replace}}]}} or {{label, content}}"]})
        bk = str(inp.get("base") or "best").strip()
        base_score = golf_inc["score"]   # vs_base: each item against the text it was made from, as at the start of this batch
        if bk in ("", "best"):
            base_text = golf_inc["proof"]
        else:
            ent = next((e_ for e_ in _pool_entries() if str(e_.get("sha", "")).startswith(bk)), None)
            if ent is None:
                return G.dumps({"ok": False, "errors": [f"no pool entry with sha prefix {bk!r} (see the pool tool)"]})
            base_text, base_score = ent["proof"], float(ent.get("score_exact") or golf_inc["score"])
        rows_, todo = [], {}
        for k, it in enumerate(items):
            lab = str(it.get("label") or f"v{k + 1}")[:40]
            if isinstance(it.get("content"), str) and it["content"].strip():
                decl, err = it["content"].rstrip(), None
            else:
                decl, err = G.apply_edits(base_text, it.get("edits"))
            if err:
                rows_.append({"label": lab, "ok": False, "error": err, "compiled": False}); continue
            decl = decl.rstrip(); sh = _sha12(decl)
            if sh in golf_seen:
                _c = dict(golf_seen[sh])
                if _c.get("score") is not None:
                    _c["vs_best"] = round(float(_c["score"]) - golf_inc["score"], 4); _c["is_best"] = sh == _sha12(golf_inc["proof"])
                _c.pop("decision", None); _c.pop("vs_base", None)
                rows_.append({"label": lab, **_c, "compiled": False, "note": "already evaluated in this session (not compiled again)"}); continue
            if sh in todo:
                rows_.append({"label": lab, "same_as": sh, "compiled": False, "note": "the same text as another item of this batch"}); continue
            todo[sh] = decl; rows_.append({"label": lab, "sha": sh})
        evs = {}
        if todo:
            with ThreadPoolExecutor(max(1, min(args.golf_jobs, len(todo)))) as ex_:
                evs = dict(zip(todo, ex_.map(golf_eval, todo.values())))
        res_ = {}
        for sh in sorted(evs, key=lambda h: -(_exact(evs[h]["L"], evs[h]["H"], golf_inc["Z"]) if evs[h].get("ok") else -1e9)):
            ev, decl = evs[sh], todo[sh]
            golf_evals += 1; golf_since_gain += 1; checks += 1
            rec = {"sha": sh, "tokens": ev.get("tokens"), "heartbeats": ev.get("heartbeats"), "ok": bool(ev.get("ok")),
                   "error": (ev.get("error") or None) if not ev.get("ok") else None, "run_id": args.run_id}
            transient = False
            if ev.get("ok"):
                _pool_add(decl, sh, ev["tokens"], ev["heartbeats"], _exact(ev["L"], ev["H"], golf_inc["Z"]))
                banked, why, sx, transient = golf_consider(decl, ev)
                rec["score"] = round(sx, 4)
                res_[sh] = {"ok": True, "tokens": ev["tokens"], "heartbeats": ev["heartbeats"], "score": round(sx, 4),
                            "vs_base": round(sx - base_score, 4), "banked": banked, "decision": why}
            else:
                transient = "timeout" in str(ev.get("error") or "")
                res_[sh] = {"ok": False, "tokens": ev.get("tokens"), "error": (ev.get("error") or "")[:300]}
            ws.record_attempt(rec)
            if not transient:   # a verdict from a timed-out compile is not final: the same text may be sent again
                golf_seen[sh] = res_[sh]
        for r_ in rows_:
            if "sha" in r_ and r_["sha"] in res_:
                r_.update(res_[r_.pop("sha")])
            elif "same_as" in r_:
                r_.update({k_: v_ for k_, v_ in res_.get(r_.pop("same_as"), {}).items() if k_ != "banked"})
            if r_.get("score") is not None:   # against the best as it stands after this batch (an earlier item may have been banked)
                r_["vs_best"] = round(float(r_["score"]) - golf_inc["score"], 4)
        return G.dumps({"items": rows_, "note": "vs_base: against the text the item was made from (the best at the start of this batch, or the "
                                                "pool entry); vs_best: against the best after this batch; items that beat the base but were not "
                                                "banked after another item was are worth combining",
                        "best": {"score": round(golf_inc["score"], 4), "tokens": golf_inc["tokens"], "heartbeats": golf_inc["heartbeats"]},
                        "evaluations": golf_evals, "since_last_gain": golf_since_gain,
                        "stop_rule_met": G.stop_ok(golf_evals, golf_since_gain, args.golf_min_evals, args.golf_flat_evals)})

    def golf_check(path: str) -> str:
        return lean_batch({"items": [{"label": Path(path or "candidate.lean").name, "content": ws.path(path or "candidate.lean").read_text()}]})

    def hb_profile_tool(inp: dict) -> str:
        decl = (inp.get("content") or golf_inc["proof"]).rstrip()
        sh = _sha12(decl)
        if sh not in golf_profiles:
            golf_profiles[sh] = G.profile(row, decl, primary)
        return G.dumps(golf_profiles[sh])

    def pool_tool(inp: dict) -> str:
        ents = _pool_entries()
        return G.dumps({"pool": G.pool_rows(ents, golf_inc["proof"], max(1, min(int(inp.get("k") or 8), 20))), "size": len(ents)})

    hardtail_local = 0   # consecutive hard-tail checks that are still local edits (>= 90% of the starting best's tokens)
    stall_checks = 0     # R3: consecutive checks without a new best in this run
    forced_turns_bf = 0  # budget-forcing rescues in this run

    def lean_check(path: str) -> str:
        nonlocal checks, best, hardtail_local, stall_checks
        if golf and golf_inc is not None:
            return golf_check(path)
        decl = ws.path(path or "candidate.lean").read_text().rstrip()
        # Duplicate guard: 24 of 134 compiles in pass 5 re-checked a byte-identical candidate (often the inherited best).
        # Return the earlier result instead of compiling, and do not count it as a check.
        sha = hashlib.sha256(decl.encode()).hexdigest()[:12]
        prior = next((a for a in reversed(ws.state["attempts"]) if a.get("sha") == sha), None)
        if prior is not None:
            return _tool_json({"ok": bool(prior.get("ok")), "unchanged": True,
                               "note": "candidate.lean is byte-identical to an attempt already checked (result below); nothing was compiled and this does not count as a check. Edit the candidate before checking again.",
                               "prior": {k: (_rel(prior.get(k), decl) if k == "error" else prior.get(k)) for k in ("tokens", "heartbeats", "ok", "error", "score", "run_id") if prior.get(k) is not None}})
        checks += 1
        body = split_declaration(decl, row["statement"])
        if body is None:
            return _tool_json({"ok": False, "errors": ["statement differs from the reference statement (must be byte-for-byte identical, followed by :=)"]})
        bad = check_forbidden(decl)
        if bad:
            return _tool_json({"ok": False, "errors": [f"forbidden construct: {bad}"]})
        toks = count_tokens(body); r = comp(decl, primary); _autofix = None
        if not r.ok:   # cycle 49: drop local hypotheses from grind lists (newer Lean rejects them) and recompile once
            from harness.leantools import fix_redundant_grind as _frg
            _fixed, _names = _frg(decl, r.errors)
            if _fixed:
                _r2 = comp(_fixed, primary)
                if _r2.ok:
                    decl, r = _fixed, _r2; body = split_declaration(decl, row["statement"]) or body; toks = count_tokens(body)
                    sha = hashlib.sha256(decl.encode()).hexdigest()[:12]
                    ws.path(path or "candidate.lean").write_text(decl + "\n")
                    _autofix = f"removed redundant grind parameter(s) {', '.join(_names)} from candidate.lean (grind uses local hypotheses automatically)"
        if not r.ok and not _autofix:   # cycle 54: delete no-op lines ("made no progress" / "No goals"), up to 3 rounds
            from harness.leantools import noop_line_deletion as _nld, head_line_count as _hlc0
            _cur, _done, _errs = decl, [], r.errors
            for _round in range(3):
                _d = _nld(_cur, _errs, _hlc0(row, primary))
                if not _d:
                    break
                _cur = _d[1]; _done.append(_d[0]); _r2 = comp(_cur, primary); _errs = _r2.errors
                if _r2.ok:
                    decl, r = _cur, _r2; body = split_declaration(decl, row["statement"]) or body; toks = count_tokens(body)
                    sha = hashlib.sha256(decl.encode()).hexdigest()[:12]
                    ws.path(path or "candidate.lean").write_text(decl + "\n")
                    _autofix = "; ".join(_done) + " (in candidate.lean)"
                    break
        if not r.ok and not _autofix:   # cycle 53: failed rewrite -> reversed rule / simp_rw / erw / simp only, first that compiles
            from harness.leantools import rw_alternatives as _rwa, head_line_count as _hlc
            for _how, _cand in _rwa(decl, r.errors, _hlc(row, primary)):
                _r2 = comp(_cand, primary)
                if _r2.ok:
                    decl, r = _cand, _r2; body = split_declaration(decl, row["statement"]) or body; toks = count_tokens(body)
                    sha = hashlib.sha256(decl.encode()).hexdigest()[:12]
                    ws.path(path or "candidate.lean").write_text(decl + "\n")
                    _autofix = f"failed rewrite repaired in candidate.lean: {_how}"
                    break
        _rec = {"sha": sha, "tokens": toks, "heartbeats": r.heartbeats, "ok": r.ok,
                "error": (digest_error(r.errors[0], 300) if r.errors else None), "run_id": args.run_id}
        if not r.ok and getattr(args, "failed_moves", False):   # 2026-10-13 --failed-moves: the failed edit against the closer of best / reference
            try:                                                 # ({} = a rewrite, no move); off: the record is byte-identical to before
                from harness import cc_levers as _LVfm         # review 2026-10-13: the tool call (one batch = one refutation), the error's
                from harness.leantools import head_line_count as _hlcfm   # line relative to the declaration (< 1: environment), stale moves voided
                _rec["move"] = _LVfm.record_move(ws.state, [("best", best.get("proof")), ("ref", row["src"])], decl, call=f"{args.run_id}:{tool_calls}",
                                                 eline=_LVfm.error_line(r.errors[0] if r.errors else None, _hlcfm(row, primary)))
            except Exception:  # noqa: BLE001
                pass
        ws.record_attempt(_rec)
        # linter hints relative to the declaration: unused tactics / simp args are direct deletion targets
        from scorer.compile import file_prefix as _fp, split_modifiers as _sm, MEASURE_ELAB as _ME
        if row["source"] == "putnambench":
            head_lines = (row["header"].rstrip() + "\n\n" + _ME + "set_option Elab.async false in\narena_measure\n").count("\n")
        else:
            core, mods = _sm(_fp(row, primary)); head_lines = (core.rstrip("\n") + "\n\n" + _ME + "set_option Elab.async false in\narena_measure\n" + mods).count("\n")
        hints = []
        for m in r.messages:
            if m.get("severity") != "warning":
                continue
            d = str(m.get("data", "")); ln = (m.get("pos") or {}).get("line", 0) - head_lines
            if ln < 1:
                continue
            if "does nothing" in d or "unused" in d.lower() or "would suffice" in d:
                hints.append(f"line {ln}: " + re.sub(r"\s+", " ", d.split("Note:")[0]).strip()[:140])
        hints = list(dict.fromkeys(hints))[:12]
        res = {"ok": r.ok, "tokens": toks, "ref_tokens": row["proof_length"], "heartbeats": r.heartbeats, "ref_heartbeats": hbs.get(name), "warnings": r.warnings,
               "errors": [_rel(digest_error(e), decl) for e in r.errors[:5]], "linter_hints": hints}
        if _autofix:
            res["auto_fixed"] = _autofix
        if not r.ok:   # cycle 50: closest real declaration names for unknown identifiers / missing fields
            from harness.leantools import suggest_names as _sn
            _sug = _sn(row, primary, r.errors)
            if _sug:
                res["did_you_mean"] = _sug
        if not r.ok and _nn is not None:   # L1 (--name-neighbors): real constants near each unknown name, listed by Lean from this environment
            _nb = _nn.lookup(r.errors)
            if _nb:
                res["name_neighbors"] = _nb; res["name_neighbors_note"] = _nn.note
                _dym = {k_: v_ for k_, v_ in (res.get("did_you_mean") or {}).items() if k_ not in _nb}
                if _dym:
                    res["did_you_mean"] = _dym
                else:
                    res.pop("did_you_mean", None)
        _best_before = float(best.get("score") or 33.33)
        if hardtail_target:   # hard-tail runs: steer away from polishing the old architecture
            hardtail_local = hardtail_local + 1 if toks > hardtail_target / 0.7 * 0.9 else 0
            if hardtail_local >= 4:
                res["strategy_note"] = (f"{hardtail_local} checks in a row are still local edits of the old proof ({toks} tokens; target <= {hardtail_target}). "
                                        "Stop polishing: go back to the protocol (lean_goals map, lemma search, 3-5 different architectures in one lean_check_variants).")
        # Cycle 28 signature assist: "Application type mismatch … in the application <const> …" was the top failure class in scout C
        # (23 of ~94 failed candidates) — the model guesses a library lemma's argument order/implicitness and retries blind.
        # Look the constant's signature up once (#check @const via lean_run; library names only, locals like `ih`/`h3` skipped)
        # and attach it to the result, saving the model a turn and a repeat guess.
        try:
            _heads = []
            for e_ in r.errors[:5]:
                m_ = re.search(r"in the application\s+\(?@?([A-Za-z_][\w.'!?]*)", re.sub(r"\s+", " ", str(e_)))
                if m_ and ("." in m_.group(1) or m_.group(1)[0].isupper()) and m_.group(1) not in _heads:
                    _heads.append(m_.group(1))
            if _heads:
                sigs = {}
                for h_ in _heads[:2]:
                    if h_ not in sig_cache:
                        sig_cache[h_] = lean_run(f"#check @{h_}", neighbors=False)[:400]
                    sigs[h_] = sig_cache[h_]
                res["signatures"] = sigs
                res["signature_note"] = "application/type mismatch: `signatures` holds the exact signature of the applied constant — match its implicit/explicit argument order before retrying"
        except Exception:  # noqa: BLE001
            pass
        try:  # POC 2 token map: where the length axis is (proof-body line numbers)
            _off = decl[:len(decl) - len(body)].count("\n") if _rel_on and decl.endswith(body) else 0   # cycle 76: declaration lines under the flag
            _lt = [(i + 1 + _off, count_tokens(l), l.strip()[:70]) for i, l in enumerate(body.split("\n")) if l.strip()]
            _lt.sort(key=lambda x: -x[1])
            res["costliest_lines"] = [{"line": i, "tokens": n, "text": s} for i, n, s in _lt[:6]]
        except Exception:  # noqa: BLE001
            pass
        # Cycle 19 repeated-error nudge: pass 14 spent 7 of 12 checks on the variational problem re-trying `linarith` at the same
        # position (134:4) with slightly different surrounding text, each failing the same way. When the same error head
        # (position + first words) has failed >= 3 times in this run, say so and demand a different route.
        if not r.ok and r.errors:
            # cycle 33: build the head exactly as the attempt was recorded (digest_error). The raw form keeps the hypotheses of an
            # `unsolved goals` error while the stored digest elides them, so the two never matched: in POC 2, 31 error heads failed
            # >= 3 times within one run (up to 7) and the nudge fired in 1 trajectory.
            _head = digest_error(r.errors[0], 300)[:60]
            _same = sum(1 for a in ws.state.get("attempts", []) if a.get("run_id") == args.run_id and not a.get("ok") and (a.get("error") or "")[:60] == _head)
            if _same >= 3:
                res["note"] = (f"This same error has now failed {_same} times in this run ({_rel(_head, decl)!r}). Retrying variants of the same tactic at the same spot is not "
                               "working: prove that step by a different route (another tactic family, an explicit `have` with the needed inequality/equality, "
                               "a library lemma via `exact?`), or restore the last compiling candidate and cut elsewhere.")
        # Cycle 16 auto-variant: the top failed-check class is `rw` "Did not find an occurrence of the pattern" (9 of 51 failures in
        # pass 11). When that is the only error, compile the same line once as `simp only [...]`; if it compiles, save it as
        # candidate_autofix.lean and tell the model (it scores/records it via lean_check, so provenance stays the model's run).
        if not r.ok and len(r.errors) == 1 and "Did not find an occurrence of the pattern" in r.errors[0]:
            _m = re.match(r"\s*(\d+):\d+:", r.errors[0])
            if _m:
                _ln = int(_m.group(1)) - head_lines; _lines = decl.split("\n")
                if 1 <= _ln <= len(_lines) and re.search(r"\brw\s*\[", _lines[_ln - 1]):
                    _lines[_ln - 1] = re.sub(r"\brw\s*\[", "simp only [", _lines[_ln - 1], count=1)
                    _variant = "\n".join(_lines)
                    try:
                        _rv = comp(_variant, primary)
                    except Exception:  # noqa: BLE001
                        _rv = None
                    if _rv is not None and _rv.ok:
                        ws.path("candidate_autofix.lean").write_text(_variant + "\n")
                        _vb = split_declaration(_variant, row["statement"]) or ""
                        res["autofix"] = (f"the failing `rw` at candidate line {_ln} compiles as `simp only [...]` ({count_tokens(_vb)} tokens, {_rv.heartbeats} heartbeats); "
                                          "saved as candidate_autofix.lean: lean_check that path to score and record it, or copy it into candidate.lean and continue.")
        if not r.ok:
            _near_miss_add(decl, r.errors)   # b63 item 16: a full candidate that failed is a near-miss (first error kept) for the C1 pass
        if r.ok:
            L = len_pct(row["proof_length"], toks); H = hb_pct_local(name, r.heartbeats, hbs.get(name))
            provisional = problem_score(True, L, H, 100.0)
            try:
                _pool_add(decl, sha, toks, r.heartbeats, _exact(L, H, 100.0))
            except Exception:  # noqa: BLE001
                pass
            res.update({"length_reduction_pct": round(L, 2), "heartbeat_reduction_pct": round(H, 2), "predicted_score_if_compatible": provisional, "reference_score": 33.33})
            try:   # Tier 1 axis signal (panel R1): which axis still has points, and the exchange rate between them
                from scorer.score import local_reference_heartbeats as _lrh
                _rt = int(row["proof_length"]); _rh = int(_lrh(name) or hbs.get(name) or 0); _fl = ws.state.get("hb_floor")
                if _rt and _rh and r.heartbeats is not None:
                    _lp = round(toks / _rt * 100 / 3, 2); _hp = round(max(0, r.heartbeats - (_fl or 0)) / _rh * 100 / 3, 2)
                    res["axis"] = {"points_per_token": round(100 / (3 * _rt), 4), "points_per_1k_heartbeats": round(100000 / (3 * _rh), 3),
                                   "one_token_equals_heartbeats": round(_rh / _rt, 1), "points_left_length": _lp,
                                   "points_left_heartbeats": _hp, "heartbeat_floor": _fl,
                                   "work_on": "tokens" if _lp >= _hp else "heartbeats",
                                   "note": ("points left are upper bounds (a proof cannot reach zero tokens); " +
                                            ("heartbeat floor measured by lean_profile" if _fl else "heartbeat floor not measured yet: call lean_profile"))}
            except Exception:  # noqa: BLE001
                pass
            if args.simp_prune and provisional > best["score"]:   # cycle 58: one simp? compile prunes unused lemmas from `only` lists
                try:
                    from harness.leantools import simp_prune as _sp
                    _pp = _sp(decl, lambda d: comp(d, primary), head_lines)
                    if _pp:
                        _rp = comp(_pp[0], primary)
                        _tp = count_tokens(split_declaration(_pp[0], row["statement"]) or "")
                        if _rp.ok and _tp:
                            _Lp = len_pct(row["proof_length"], _tp); _Hp = hb_pct_local(name, _rp.heartbeats, hbs.get(name))
                            _sc = problem_score(True, _Lp, _Hp, 100.0)
                            if _sc > provisional:
                                decl, r, toks, L, H, provisional = _pp[0], _rp, _tp, _Lp, _Hp, _sc
                                ws.path(path or "candidate.lean").write_text(decl + "\n")
                                res.update({"tokens": toks, "heartbeats": r.heartbeats, "length_reduction_pct": round(L, 2), "heartbeat_reduction_pct": round(H, 2),
                                            "predicted_score_if_compatible": provisional,
                                            "auto_pruned": f"simp? dropped {_pp[1]} unused lemma(s) from `only` lists; candidate.lean updated"})
                except Exception:  # noqa: BLE001
                    pass
            if provisional > best["score"]:
                compat = {primary: True}; _cfail = {}
                for v in versions[1:]:
                    _rv = comp(decl, v, count=False); compat[v] = _rv.ok
                    if not _rv.ok:   # cycle 56: say why (errors at that toolchain, names that exist there)
                        from harness.leantools import compat_failure as _cf
                        _cfail[v] = _cf(row, v, [_rel(e, decl, _hlc_rel(row, v) - _rel_meas) for e in _rv.errors] if _rel_on else _rv.errors)
                Z = compat_pct(compat); sc = problem_score(True, L, H, Z)
                res.update({"compat": compat, "score": sc})
                try:   # b63 bank: the per-pin reading of this candidate (its provisional line was written at the compile)
                    _pool_add(decl, sha, toks, r.heartbeats, _exact(L, H, Z), compat=compat)
                except Exception:  # noqa: BLE001
                    pass
                if _cfail:
                    from harness.leantools import compat_note as _cn
                    res.update({"compat_failures": _cfail, "compat_note": _cn(primary, _cfail, Z, sc, provisional)})
                if sc > best["score"]:
                    try:   # Tier 1 ledger: record the winning edit as a diff so a later run can re-apply it (panel: tricks lost between passes)
                        import difflib as _dl
                        _prev = best.get("proof") or ""
                        _d = [l for l in _dl.unified_diff(_prev.splitlines(), decl.splitlines(), lineterm="", n=0) if l[:1] in "+-" and not l.startswith(("+++", "---"))]
                        _led = ws.state.setdefault("ledger", {}).setdefault("wins", [])
                        _led.append({"run_id": args.run_id, "check": checks, "d_score": round(sc - float(best.get("score") or 33.33), 2),
                                     "d_tokens": toks - int(best.get("tokens") or row["proof_length"]), "d_heartbeats": (r.heartbeats or 0) - int(best.get("heartbeats") or 0),
                                     "diff": "\n".join(_d)[:700]})
                        ws.state["ledger"]["wins"] = _led[-30:]
                    except Exception:  # noqa: BLE001
                        pass
                    best = {"score": sc, "proof": decl, "tokens": toks, "heartbeats": r.heartbeats, "L": round(L, 2), "H": round(H, 2), "Z": Z, "compat": compat}
                    ws.state["best"] = best; ws.state["attempts"][-1]["score"] = sc; ws.save()
                    ver_f.write(json.dumps({"problem": name, "sha256": hashlib.sha256(decl.encode()).hexdigest()[:16], "proof": decl, "tokens": toks, "ref_tokens": row["proof_length"],
                                            "heartbeats": r.heartbeats, "primary": primary, "primary_ok": True, "compat": compat, "L": round(L, 2), "H": round(H, 2), "Z": Z, "score": sc,
                                            "provenance": {"kind": ("closed-dev-only" if args.model_preset else "api-dev-only"), "model": prov_model, "run_id": args.run_id, "mode": "agent", "check": checks}}, ensure_ascii=False) + "\n"); ver_f.flush()
                    print(f"{name[:18]:18s} check {checks}: NEW BEST tok={toks} ({L:+.1f}%) hb={r.heartbeats} ({H:+.1f}%) Z={Z:.0f} score={sc}", flush=True)
        # R3: 8 checks in a row without a new best -> ask for a new rewrite
        stall_checks = 0 if float(best.get("score") or 33.33) > _best_before else stall_checks + 1
        if stall_checks >= 8 and stall_checks % 8 == 0:
            res["rewrite_note"] = (f"{stall_checks} checks in a row without a new best: editing has stalled. Start a NEW rewrite with a different architecture "
                                   "(outline with sorry holes -> lean_skeleton -> fill one hole at a time), using the goal map, LIBRARY LEADS and technique cards.")
        return _tool_json(res, ensure_ascii=not _rel_on)

    t_start = time.time()
    traj_f.write(json.dumps({"type": "header", "run_id": args.run_id, "problem": name, "model": args.model, "api_model": api_model, "endpoint": args.endpoint,
                             "quant": args.quant if args.endpoint == "openrouter" else None, "reasoning_effort": args.reasoning_effort, "turn_budget": args_turns,
                             "max_tokens": args.max_tokens, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "system": SYSTEM,
                             "tools": [t["name"] for t in TOOLS], "best_at_start": ws.state["best"].get("score")}, ensure_ascii=False) + "\n"); traj_f.flush()
    notes_written = False
    turns_since_check = 0
    finish_rejections = 0
    shell_calls = 0
    lemma_greps = 0; searched = False   # cycle 42: 57 lemma-hunting greps and 0 lean_search calls in the measurement pass
    last_truncated = False   # after a truncated turn, give the next one double room so the pending tool call can complete
    trunc_count = 0   # pass 7: keep a raised cap for the rest of the run after a truncation; cycle 15: ~60% of remaining truncations hit the doubled 8k cap, so escalate 8k -> 12k -> 16k on repeats
    # Cycle 51 tested running this on every cold start (first improvement comes only at turn 6-26 in the held-out A/B): on four references
    # it gained 0, 0, +1.86, +0.55 for 1.5-4 min each, floors the agent passes in its first turns anyway. Generic closers raise heartbeats
    # above cheap references and H is not floored at 0. Kept behind --length-tools.
    if args.length_tools and (ws.root / "candidate.lean").exists() and not args.from_reference:
        # Mechanical pass before the first model turn (research integration list, 2026-10-07): Mathlib TacticAnalysis linters +
        # lemma-hinted block/tail probes on the starting candidate; an improvement is scored/banked through lean_check and becomes
        # the candidate the model starts from. Costs 1-3 min of Lean (memory-gated), no model tokens.
        try:
            _pre_res = json.loads(lean_mine("candidate.lean"))
            if _pre_res.get("mined"):
                msgs[0]["content"] += (f"\n\nMECHANICAL PRE-PASS: the harness already shortened candidate.lean mechanically "
                                       f"({_pre_res['mined'].get('how', '')[:200]}); score {_pre_res['mined'].get('score')}. Continue from it.")
            print(f"{name[:18]:18s} pre-pass: {(_pre_res.get('mined') or {}).get('score', 'no improvement')}", flush=True)
        except Exception as _e:  # noqa: BLE001
            print(f"{name[:18]:18s} pre-pass failed: {_e}", flush=True)
    def _start_check_block(_r0: dict) -> str:   # b92: also re-rendered from the installed start's own check
        return ("\n\nSTART CHECK: the harness compiled candidate.lean before your first turn. " +
                (f"It compiles: score {_r0.get('score')} ({_r0.get('tokens')} tokens, {_r0.get('heartbeats')} heartbeats). It is "
                 "your current best and the starting point: improve it, do not start over from original.lean."
                 if _r0.get("ok") else "It does NOT compile: " + "; ".join((_r0.get("errors") or [str(_r0.get("error") or "?")])[:2])[:400]))

    # 2026-10-15 start check: a skeleton-seeded workspace (probe/heldout/seed_from_ab.py --skeletons: best.score 0 with a proof) is measured
    # before the first turn. Without it the opening looks like a fresh problem ("REWRITE FIRST"), and in the Azure A/B one session never
    # compiled its seed (the row's 88.07 current best): it batch-tested its own rewrites first and polished a 73-74 proof for the whole run.
    if not golf and ws.state["best"].get("proof") and not float(ws.state["best"].get("score") or 0) and (ws.root / "candidate.lean").exists() \
            and not args.from_reference:
        try:
            _r0 = json.loads(lean_check("candidate.lean"))
            if isinstance(msgs[0]["content"], str):
                _s0 = len(msgs[0]["content"])
                msgs[0]["content"] += _start_check_block(_r0)
                _open_spans["start_check"] = (_s0, len(msgs[0]["content"]), msgs[0]["content"][_s0:])
            print(f"{name[:18]:18s} start check: {_r0.get('score') if _r0.get('ok') else 'does not compile'}", flush=True)
        except Exception as _e:  # noqa: BLE001  (the start check never fails the session)
            print(f"{name[:18]:18s} start check failed: {type(_e).__name__}: {_e}", flush=True)
    def _reopen_start(_r: dict) -> None:
        """b92 (2026-10-31, docs/b92_opening_fix.md): the auto-brief below installs its start candidate AFTER the opening was rendered, which
        showed the seed as "candidate.lean (your current best)" and its score as the best so far while the appended brief says the workspace
        starts from the start. Re-render, from the installed candidate.lean and this session's own check of it (_r), the opening's parts that
        show candidate.lean and the best so far: the best-so-far sentence, the candidate.lean block, the linter hints on the current candidate
        and a start check's block, as they read had the start been in the workspace when the opening was built. Nothing else changes (the
        turn budget and every other session parameter were set before; cards, leads and the brief stay as rendered). A span that no longer
        holds what was rendered leaves the opening as it is; never fails the session."""
        try:
            _c = msgs[0]["content"]
            if not isinstance(_c, str):
                return
            _cand = (ws.root / "candidate.lean").read_text().rstrip(); _b = ws.state["best"]
            _is_best = (_b.get("proof") or "").rstrip() == _cand   # the check made it the best (else: compiled, not better on this meter)
            _eds = []
            if "best" in _open_spans:
                _eds.append((*_open_spans["best"], best_so_far(_b) if _is_best else best_so_far(_b, "best.lean" if _b.get("proof") else "original.lean")))
            if "cand" in _open_spans:
                _s, _e, _old, _lbl = _open_spans["cand"]
                _eds.append((_s, _e, _old, _file_block("candidate.lean", _lbl if _is_best else
                                                       f"candidate.lean (the auto-brief start: {_r.get('tokens')} tokens, {_r.get('heartbeats')} heartbeats; not your best so far)")))
            if "lint" in _open_spans and "linter_hints" in _r:   # a duplicate-guard answer carries no hints: the block stays
                _eds.append((*_open_spans["lint"], _lint_block(_r.get("linter_hints") or [])))
            if "start_check" in _open_spans:
                _eds.append((*_open_spans["start_check"], _start_check_block(_r) if _is_best else ""))
            _new = respan(_c, _eds)
            if _new is None:
                print(f"{name[:18]:18s} auto-brief opening: left as rendered (a recorded span moved)", flush=True)
                return
            msgs[0]["content"] = _new
            print(f"{name[:18]:18s} auto-brief opening: candidate.lean shown as the installed start ("
                  + (f"best so far {_b.get('score')}" if _is_best else "not the best so far") + ")", flush=True)
        except Exception as _e2:  # noqa: BLE001
            print(f"{name[:18]:18s} auto-brief opening failed: {type(_e2).__name__}: {_e2}", flush=True)
    # 2026-10-14 --auto-brief DIR (docs/auto_brief_plan.md; off by default): the brief harness/autobrief.py measured on THIS seed in this run
    # (CPU only, the same code for every row): appended to the opening; on a workspace whose best is below the measured start, the start
    # candidate goes through this session's own lean_check (scored, recorded and verified like any candidate) and becomes candidate.lean.
    if getattr(args, "auto_brief", None):
        try:
            _abf = ROOT / args.auto_brief / (re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".json")
            _ab = json.loads(_abf.read_text()) if _abf.exists() else None
            if _ab and _ab.get("brief") and isinstance(msgs[0]["content"], str):
                msgs[0]["content"] += "\n\n" + _ab["brief"]
                _sp = (_ab.get("s1") or {}).get("proof") or (_ab.get("s0") if _ab.get("free_applied") else None)
                _ss = float(((_ab.get("s1") or {}).get("full") or _ab.get("start") or {}).get("score") or 0)
                _c0 = _ab.get("c0") or {}   # b63 item 6 (harness/cpu_pass.py): the C0 pass's B0 beats the brief's start -> the session starts from it
                if _c0.get("changed") and _c0.get("proof") and float((_c0.get("full") or {}).get("score") or 0) > _ss:
                    _sp, _ss = _c0["proof"], float(_c0["full"]["score"])
                if _ab.get("shown"):   # contract §2 shown.json: what the SHOWN block held; adoption counted at each compiling check
                    try:
                        _shown_f = ws.root / "shown.json"
                        _sj = json.loads(_shown_f.read_text()) if _shown_f.exists() else {"sessions": []}
                        _sj["sessions"].append({"run_id": args.run_id, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                                "shown": [{k_: v_ for k_, v_ in it.items() if k_ != "diff"} for it in _ab["shown"]], "adopted": 0, "adopted_shas": []})
                        _shown_f.write_text(json.dumps(_sj, ensure_ascii=False, indent=1))
                        ws.shown_shas = {it.get("sha") for it in _ab["shown"] if it.get("sha")}
                    except Exception:  # noqa: BLE001
                        pass
                if _sp and _ss > float(ws.state["best"].get("score") or 0) + 0.05:
                    (ws.root / "autobrief_start.lean").write_text(_sp.rstrip() + "\n")
                    _r = json.loads(lean_check("autobrief_start.lean"))
                    if _r.get("ok"):
                        (ws.root / "candidate.lean").write_text(_sp.rstrip() + "\n")
                        _reopen_start(_r)   # b92: the opening shows the installed start (docs/b92_opening_fix.md)
                    print(f"{name[:18]:18s} auto-brief start: {_r.get('score')} (measured {_ss})", flush=True)
            ws.state["runs"][-1]["auto_brief"] = bool(_ab and _ab.get("brief")); ws.save()
            print(f"{name[:18]:18s} auto-brief: {'appended' if _ab and _ab.get('brief') else 'none for this row'}", flush=True)
        except Exception as _e:  # noqa: BLE001  (a missing or broken brief never fails the session)
            print(f"{name[:18]:18s} auto-brief failed: {type(_e).__name__}: {_e}", flush=True)
    if artifact and isinstance(msgs[0]["content"], str):   # b63 item 16: the SHOWN block of the artifact (plan §1.1 L / P; contract §2 shown.json)
        try:
            from harness.cpu_pass import render_artifact_shown as _ras
            _bst = dict(ws.state.get("best") or {})
            msgs[0]["content"] += "\n\n" + _ras(artifact, _bst, args_turns)
            _shown_f = ws.root / "shown.json"
            _sj = json.loads(_shown_f.read_text()) if _shown_f.exists() else {"sessions": []}
            _sj["sessions"].append({"run_id": args.run_id, "kind": "artifact", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                    "shown": [{k_: artifact.get(k_) for k_ in ("sha", "kind", "source", "tokens_est", "structural")} | {"holes": len(artifact.get("holes") or []),
                                              "best_sha": hashlib.sha256((_bst.get("proof") or "").rstrip().encode()).hexdigest()[:12] if _bst.get("proof") else None,
                                              "best_score": _bst.get("score")}], "adopted": 0, "adopted_shas": []})
            _shown_f.write_text(json.dumps(_sj, ensure_ascii=False, indent=1))
            ws.shown_shas = (getattr(ws, "shown_shas", None) or set()) | {artifact["sha"]}
        except Exception as _e:  # noqa: BLE001  (the block never fails the session)
            print(f"{name[:18]:18s} artifact SHOWN block failed: {type(_e).__name__}: {_e}", flush=True)
    # Cycle 45: turn 0 hit the output cap in 16% of recent runs (5 of 31) against 2.4% for later turns: the model plans the whole run in
    # its head from the long opening message. Ask for an early first action, last in the message where it is read last.
    if golf:   # B62c: measure the incumbent in this session (the paired baseline), profile it, and open with the golf brief only
        _g0 = (best.get("proof") or row["src"]).rstrip()
        _e0 = golf_eval(_g0)
        if not _e0.get("ok"):   # review 2026-10-21: one retry (a timeout or a memgate give-up is transient); never fall back to the reference
            _e0 = golf_eval(_g0)   # while a stored best exists (that would bank gains over the reference against a better stored best)
        if not _e0.get("ok"):
            print(f"{name[:18]:18s} golf: the start proof does not compile ({str(_e0.get('error'))[:160]}); session ends", flush=True)
            args_turns = 0
        else:
            _z0 = best.get("Z") if best.get("proof") and best["proof"].rstrip() == _g0 and best.get("Z") is not None else None
            if _z0 is None:
                _c0 = {primary: True}
                for v in versions[1:]:
                    _c0[v] = comp(_g0, v, count=False).ok
                _z0 = compat_pct(_c0)
            golf_inc = {"score": _exact(_e0["L"], _e0["H"], _z0), "tokens": _e0["tokens"], "heartbeats": _e0["heartbeats"], "Z": float(_z0), "proof": _g0}
            _sh0 = _sha12(_g0); ws.own_shas.add(_sh0)
            golf_seen[_sh0] = {"ok": True, "tokens": _e0["tokens"], "heartbeats": _e0["heartbeats"], "score": round(golf_inc["score"], 4)}
            _pool_add(_g0, _sh0, _e0["tokens"], _e0["heartbeats"], golf_inc["score"])
            for _fn in ("best.lean", "candidate.lean"):
                (ws.root / _fn).write_text(_g0 + "\n")
            golf_profiles[_sh0] = _prof0 = G.profile(row, _g0, primary)
            from scorer.score import local_reference_heartbeats as _lrh_g
            msgs[0] = {"role": "user", "content": G.opening(name, row, versions, int(_lrh_g(name) or hbs.get(name) or 0), golf_inc, _g0, _prof0,
                                                            (_pre or {}).get("linter_hints") or [], args.budget_usd, args.golf_min_evals, args.golf_flat_evals)}
            ws.state["runs"][-1]["mode"] = "golf"; ws.save()
            print(f"{name[:18]:18s} golf: start {golf_inc['score']:.4f} ({_e0['tokens']} tok, {_e0['heartbeats']} hb, Z {_z0:.0f}); profile "
                  + ("ok" if _prof0.get("ok") else str(_prof0.get("error"))[:100]), flush=True)
    if not golf and isinstance(msgs[0]["content"], str) and "SHORT POLISH RUN" not in msgs[0]["content"]:
        msgs[0]["content"] += ("\n\nOPENING MOVE: keep this first turn short. Pick the single most promising idea from the material above and act on it "
                               "with ONE tool call now (a lean_check_variants batch, lean_profile, lean_goals or lean_search). You will see results "
                               "and plan the next step from them; do not plan the whole run before acting.")
    turn = -1; extra_turns = 0; _sess_turn_max = 0.0; _last_in_tokens = 0; cut_continuations = 0; adaptive_cap_now = 0
    _prov_lk: dict = {}   # b64 F4: the session's one OpenRouter /generation provider lookup (when the stream names no provider)
    # 2026-10-23 (b62-v2 review; --budget-reclaim): every attempt is charged its worst case (the gate's: context uncached + its output cap)
    # in state.json api_spend BEFORE it is sent, and settled to the metered cost when it returns, so a session killed while a call is in
    # flight (unit stop, OOM, container stop) leaves a spend that covers the call for every reader of api_spend (this gate, hx_heldout's
    # rungs, the router's review budget): at router --target-frac 1.0 no headroom under the cap absorbs an unrecorded call. The record a
    # killed session leaves ("inflight") stays charged: the next session moves it to assumed_spend. Off without --budget-reclaim (no key).
    _pc_on = bool(args.model_preset and getattr(args, "budget_reclaim", False) and not MODEL_PRESETS[args.model_preset].get("adaptive_cap"))

    def _pin_dead() -> str | None:   # b65-final: a CONFIRMED pin of this session's preset: this process's, or a fresh marker in the run dir
        # b66 (A3): only a marker of THIS preset (or one naming none): a reused run dir may hold the marker of a preset the router fell back from
        return PINS.dead(args.model_preset) or PW.marker_fresh(out_dir, preset=args.model_preset) if args.model_preset else None
    # b64 L0 (cap safety): every gate below budgets at the preset's CAP prices (cap_prices: an announced price rise, e.g. Argon's $4 / $20) and
    # counts the turns already metered at those prices too: api_spend stays the metered (reported, list) spend, state.json cap_extra holds the
    # difference (written only for a preset whose cap prices differ from its table), and the gate's spend is their sum. Same prices: unchanged.
    _cap_tab = cap_prices(args.model_preset) if args.model_preset else None
    _cap_diff = bool(args.model_preset) and tuple(_cap_tab) != tuple(MODEL_PRESETS[args.model_preset]["prices"])

    def _gate_spend() -> float:
        # b64 planner (T2, hx_heldout --first-preset): cap_extra counts whatever THIS session's preset is, so a Sol session after an Argon first
        # session gates the row at Argon's cap price too (state.json holds cap_extra only after a cap-priced session: an all-Sol row is unchanged)
        return float(ws.state.get("api_spend") or 0) + float(ws.state.get("cap_extra") or 0)

    def _inflight_keep(why: str) -> None:
        inf = ws.state.pop("inflight", None)
        if isinstance(inf, dict):   # api_spend already holds it: it stays spent (it may have been billed)
            usd = float(inf.get("usd") or 0)
            ws.state["assumed_spend"] = round(float(ws.state.get("assumed_spend") or 0) + usd, 6); ws.save()
            flush_traj({"type": "assumed_spend", "turn": inf.get("turn"), "usd": round(usd, 6), "inflight": why, "of_run": inf.get("run_id")})
            print(f"{name[:18]:18s} in-flight call ({inf.get('run_id')} turn {inf.get('turn')}) kept as spent: ${usd:.3f} ({why})", flush=True)

    def _inflight_open(usd: float) -> None:
        _inflight_keep("an earlier attempt's record was still open")
        base = float(ws.state.get("api_spend") or 0)
        ws.state["inflight"] = {"base": base, "usd": round(usd, 6), "run_id": args.run_id, "turn": turn}
        ws.state["api_spend"] = round(base + usd, 6); ws.save()

    def _inflight_close() -> None:   # the attempt returned (its cost is metered next) or failed (charged below when it may have been billed)
        inf = ws.state.pop("inflight", None)
        if isinstance(inf, dict):
            ws.state["api_spend"] = float(inf["base"])
    if isinstance(ws.state.get("inflight"), dict):
        _inflight_keep("a session ended while its call was in flight")
    # b64 L1 (c) --junk-billing-reconcile: OpenRouter only (its generation records); LRA_SELFTEST_GENERATION lets the selftest's fake answer
    _rec_on = bool(args.model_preset and getattr(args, "junk_billing_reconcile", False)
                   and ("openrouter.ai" in (args.base_url or "") or os.environ.get("LRA_SELFTEST_GENERATION")))
    # b65 (2): on OpenRouter (the final's path) a call whose bill stays unknown (unknown_bill) is charged at least the worst case the gate
    # reserved for it (turn_charge). Azure's Responses estimates (dev only; 0 under-counts on 166 cuts) are kept.
    _or_billed = bool(args.model_preset and ("openrouter.ai" in (args.base_url or "") or os.environ.get("LRA_SELFTEST_GENERATION")))

    _sess_costs: list[float] = []   # b64 L1 (c): this session's metered turn costs (filled only with --junk-billing-reconcile)

    def _reconcile(tries: int, wait: float) -> None:
        nonlocal _sess_turn_max
        if not (_rec_on and ws.state.get("billing_pending")):
            return
        try:
            # metered at the prices of the preset that charged the turn (an entry may come from an earlier session of another preset)
            # b64-it3 (L0 x L1): cap_meter adds the record at the gate's cap prices ("billed_cap") for a preset whose cap prices differ (Argon)
            _evs = reconcile_billing(ws.state, lambda gid: _oai.generation_usage(args.base_url, _oai_key, gid, tries=tries, wait=wait),
                                     lambda u_, p_: metered_usd(MODEL_PRESETS.get(p_.get("preset")) or MODEL_PRESETS[args.model_preset], u_),
                                     cap_meter=lambda u_, p_: cap_metered_usd(p_.get("preset") if p_.get("preset") in MODEL_PRESETS
                                                                               else args.model_preset, u_))
        except Exception as _e:  # noqa: BLE001  (reconciliation never fails a session; the worst-case charge stays)
            print(f"{name[:18]:18s} billing reconcile failed: {type(_e).__name__}: {str(_e)[:160]}", flush=True); return
        ws.save()
        for _ev in _evs:
            flush_traj({**_ev, "turn": turn})
            _ix = _ev.get("sess_idx")
            if (_ev.get("of_run") == args.run_id and _ev.get("billed_metered") is not None and isinstance(_ix, int)
                    and 0 <= _ix < len(_sess_costs)):   # the worst case no longer sets this session's reserve floor (1.25x its costliest turn);
                # every other turn of the session, before and after the junk turn, still counts. b64-it3: _sess_costs holds the gate's cap-price
                # costs (L0), so a preset whose cap prices differ takes the record at its cap prices; cap_extra keeps the junk turn's worst-case
                # difference (the gate stays above the cap-price bill: conservative)
                _sess_costs[_ix] = float(_ev.get("billed_cap", _ev["billed_metered"]))
                _sess_turn_max = max(_sess_costs)
            print(f"{name[:18]:18s} billing reconcile: junk turn {_ev.get('of_turn')} charged ${float(_ev['charged']):.4f}, "
                  + (f"billed ${_ev['billed_metered']:.4f}: spend {_ev['adjust']:+.4f}" if _ev.get("billed_metered") is not None
                     else "no record after the last lookup: the charge stays"), flush=True)

    def _salvage_skeleton(u, raw_args, salvaged_: dict) -> None:
        """b64 L1 (b) --skeleton-salvage: run a junk lean_skeleton call on its draft when a usable one is present (harness/skeleton_salvage.py);
        the call's input becomes exactly that draft (nothing else from the junk call is used)."""
        if not (getattr(args, "skeleton_salvage", False) and u.name == "lean_skeleton"):
            return
        try:
            from harness.skeleton_salvage import salvage as _salv
            sv = _salv(raw_args, row["statement"])
        except Exception as _e:  # noqa: BLE001  (a failed salvage leaves the call dropped, as without the flag)
            sv = {"draft": None, "why": f"salvage failed: {type(_e).__name__}: {_e}"}
        flush_traj({"type": "skeleton_salvage", "turn": turn, "ok": bool(sv.get("draft")), "why": sv.get("why"), "closed": sv.get("closed"),
                    "dropped_chars": sv.get("dropped_chars"), "draft_chars": len(sv.get("draft") or "")})
        if sv.get("draft"):
            u.input = ({"path": "", "content": sv["draft"]} if args.skeleton_path_first else {"content": sv["draft"], "path": ""})
            salvaged_[u.id] = sv
            print(f"{name[:18]:18s} turn {turn}: junk lean_skeleton call salvaged ({len(sv['draft'])} chars of draft; {sv.get('why')})", flush=True)
        else:
            print(f"{name[:18]:18s} turn {turn}: junk lean_skeleton call not salvaged ({sv.get('why')})", flush=True)
    while turn + 1 < args_turns:   # cycle 24: a while-loop so scout turns spent only on rejected shell calls can be refunded
        _reconcile(1, 0.0)
        if args.model_preset and _pin_dead():   # b65-final: a CONFIRMED pin (this process, or hx_heldout's marker); no request is sent
            print(f"{name[:18]:18s} session ends: {args.model_preset} has no endpoint under its max_price pin (confirmed; the FATAL line)", flush=True)
            flush_traj({"type": "pin_stop", "turn": turn, "preset": args.model_preset}); PINS.skip(args.model_preset, name)
            break
        # 2026-10-11 (the closed-track audit checks the MAX per problem):
        # stop BEFORE a turn that could cross the cap. Reserve = the WORST CASE of the next turn: its whole context billed uncached
        # (caching is best effort; one Sol turn carried 301k tokens) plus its full output cap, at the list prices; never less than 1.25x
        # this session's costliest turn. The provider cannot bill more output than max_tokens, so spend + reserve <= cap is a hard bound.
        _turn_reserve = 0.0; _reclaim_cap = None
        if args.model_preset:
            _pi, _po, _pr_, _pw = _cap_tab   # b64 L0: the cap prices (= the table for every preset without cap_prices)
            _cap_next = max(args.max_tokens * min(4, 3 + trunc_count), MODEL_PRESETS[args.model_preset].get("min_cap", 0))
            _ctx = max(_last_in_tokens, (len(SYSTEM) + len(json.dumps(msgs, ensure_ascii=False, default=str))) // 2) + 20000
            # 2026-10-22 (lever 5; docs/speed_review.md item 14: at 156 budget-gate stops of earlier Sol dev runs the full-cap reserve
            # left ~63% of the session's budget unused): --budget-reclaim shrinks the next turn's output cap to what the budget can still pay
            # for in the same worst case instead of ending the session (preset_gate; off by default: the reserve is the old rule, byte for byte)
            _turn_reserve, _reclaim_cap = preset_gate(_gate_spend(), args.budget_usd, _ctx,
                                                      _cap_tab, _cap_next, _sess_turn_max,
                                                      reclaim=args.budget_reclaim and not MODEL_PRESETS[args.model_preset].get("adaptive_cap"),
                                                      floor=args.reclaim_floor)
            _acap = MODEL_PRESETS[args.model_preset].get("adaptive_cap")
            if _acap:
                # 2026-10-14 (Kimi K3 as in the IMO 2026 setup; docs/kimi_k3_plan.md): a deep reasoner gets the output cap the remaining
                # budget can pay for (worst-case context included), up to adaptive_cap, instead of a fixed cap whose full price is held in reserve
                # (that reserve held Opus to 4-9 turns and left a third of every Kimi budget unused). spend + context + cap x output price <= budget
                # still holds by construction: a provider cannot bill past max_tokens. Below adaptive_min tokens of room the session ends.
                _room = int((args.budget_usd - _gate_spend() - _ctx * max(_pi, _pw) / 1e6) * 1e6 / _po)
                adaptive_cap_now = min(int(_acap), _room)
                _turn_reserve = (_ctx * max(_pi, _pw) + max(adaptive_cap_now, 0) * _po) / 1e6
                if adaptive_cap_now < int(MODEL_PRESETS[args.model_preset].get("adaptive_min", 6000)):
                    _turn_reserve = args.budget_usd + 1   # not enough room for a useful turn: end below
        if args.model_preset and _gate_spend() + _turn_reserve > args.budget_usd:
            print(f"{name[:18]:18s} budget reached: ${_gate_spend():.3f} + reserve ${_turn_reserve:.3f} > ${args.budget_usd:.2f}; session ends", flush=True)
            break
        turn += 1
        if turns_since_check >= 4:
            msgs.append({"role": "user", "content": f"You have not run lean_check for {turns_since_check} turns. Exploration is fine, but convert it now: write candidate.lean with your best complete attempt (even if imperfect) and call lean_check, then continue from the errors."})
            turns_since_check = 0
        # Cycle 21 fresh-start fallback: a new approach that has produced no compiling candidate by turn 20 is not going to
        # (a dev row: two fresh starts, 21 checks, zero compiled). Restore the stored best and spend the rest on it.
        if fresh_start and turn == 20 and (ws.root / "best.lean").exists() and not any(a.get("ok") for a in ws.state.get("attempts", []) if a.get("run_id") == args.run_id):
            (ws.root / "candidate.lean").write_text((ws.root / "best.lean").read_text())
            msgs.append({"role": "user", "content": f"FRESH START FALLBACK: 20 turns and no compiling candidate from the new approach. candidate.lean has been restored to the "
                                                    f"stored best (score {ws.state['best'].get('score')}). Spend the remaining {args_turns - turn} turns on THAT proof: structural cuts one at a "
                                                    "time, lean_check after each. First, add one line to notes.md on why the new approach did not compile, so later runs do not repeat it."})
            print(f"{name[:18]:18s} fresh start produced nothing compiling by turn 20: restored best.lean", flush=True)
            fresh_start = False
        if think_prompt_on and turn > 0 and turn % 6 == 0:
            msgs.append({"role": "user", "content": THINK_NUDGE})
        # Cycle 38: in 6-turn polish runs 73% (24/33) made ZERO checks: this wrap-up message fired at turn 3, after a reading turn, and the model
        # wrote notes and finished. Short runs (<= 10 turns) get it on the final turn only.
        if not golf and turn == args_turns - (1 if args_turns <= 10 else 3) and not notes_written:
            msgs.append({"role": "user", "content": "Budget nearly over (3 turns left). Write notes.md now (write_file): what worked, what failed and why, lemma names you confirmed exist or do not exist, and the most promising next idea. Tag every negative claim with the check that showed it, `[tested: <what> -> <result>]`; untagged claims are shown to later runs as unverified. Then make sure candidate.lean holds your best compiling candidate and call finish."})
        # Cycle 26: scouts kept calling shell when the scout rule would reject it (48 rejected calls over scouts A+B, ~22 s each);
        # withhold the tool from the API call instead of refunding the wasted turn.
        tools_now = [t_ for t_ in TOOLS if t_["name"] != "shell"] if (args.from_reference and (checks == 0 or shell_calls >= 3)) else TOOLS
        if not args.length_tools:
            tools_now = [t_ for t_ in tools_now if t_["name"] != "lean_mine"]
        if args.strategy == "hardtail" and hardtail_batches == 0 and turn >= 2 and forced_turns < 3:
            # Smoke 2026-10-07 (8 turns): the model wrote one candidate of its own, never batched architectures, then finished. From turn 2,
            # until a >= 3-variant batch exists, offer only the step-4 tools and say what this turn must produce.
            if forced_turns == 0:
                msgs.append({"role": "user", "content": (f"PROTOCOL STEP 4 NOW: call lean_check_variants with 3-5 FULL candidates of DIFFERENT architecture, each at most "
                                                         f"{hardtail_target} tokens, built from the goal map (shared `<;>` closer over the case split, a generalised helper `have`, "
                                                         "term mode from library lemmas, a different induction/cases variable). lean_run is available for a quick lemma check first. "
                                                         "Other tools return after this batch.")})
            forced_turns += 1
            tools_now = [t_ for t_ in tools_now if t_["name"] in ("lean_check_variants", "lean_run", "lean_goals", "read_file")]
        m = None
        # Cycle 23: truncation rate by cap over passes 15-16 was 21% at 4k, 10% at 8k, 2% at 12k, 1% at 16k; each truncation wastes the
        # turn and the first one only unlocks the next step. Start one step up (8k) and keep the 16k ceiling.
        # Cycle 25: large reference proofs (> 1500 Lean tokens: the Putnam rows, fold_advances) truncate 13-18% of turns even at 8k,
        # because writing the candidate alone costs several thousand tokens; start them at 12k.
        # Cycle 37 (Tier 4 hygiene): over passes 12-16 + POC 2 (2442 turns) truncation was 25.4% at 4k, 8.8% at 8k, 3.2% at 12k, 1.2% at 16k, and
        # 83% of truncations ended with no tool call (a wasted turn). Start every turn at 12k (was 8k; 12k only for references > 1500 tokens).
        cap = args.max_tokens * min(4, 3 + trunc_count)
        if args.model_preset:
            cap = max(cap, MODEL_PRESETS[args.model_preset].get("min_cap", 0))
            if MODEL_PRESETS[args.model_preset].get("adaptive_cap"):
                cap = adaptive_cap_now
            elif _reclaim_cap is not None:   # --budget-reclaim: the full cap's worst case does not fit; this one does (preset_gate)
                cap = _reclaim_cap
                print(f"{name[:18]:18s} turn {turn}: budget reclaim: output cap {cap} (full {_cap_next}); spend ${_gate_spend():.3f} "
                      f"+ worst case ${_turn_reserve:.3f} <= ${args.budget_usd:.2f}", flush=True)
        t_call = time.time()
        # 2026-10-20 (B34: Sol on Azure, 250k tokens/min for about two live sessions): a 429 waits on its own budget (--rate-limit-budget s of
        # wall time from the first rejection, the server's retry-after honoured; llm/openai_compat.with_rate_limit_retry), shared by this
        # turn's transport attempts; once it is used the session ends as after the transport retries
        _rl: dict = {}
        def _rl_log(s_: str) -> None:
            print(f"{name[:18]:18s} turn {turn}: {s_}", flush=True); flush_traj({"type": "rate_limit", "turn": turn, "note": s_})
        # b66 (A4): a connect failure (DNS, refused, connect timeout, TLS handshake: never sent, $0) waits for the network on its own wall-clock
        # budget (llm/openai_compat.with_connect_retry, LRA_CONNECT_BUDGET_S), shared by this turn's attempts; it never uses up an attempt
        _cn: dict = {}
        def _cn_log(s_: str) -> None:
            print(f"{name[:18]:18s} turn {turn}: {s_}", flush=True); flush_traj({"type": "connect_retry", "turn": turn, "note": s_})
        def _cn_pause() -> None:   # nothing is in flight while it waits: --budget-reclaim's pre-charge comes off (a kill then books nothing)
            if _pc_on:
                _inflight_close(); ws.save()
        def _cn_resume() -> None:
            if _pc_on:
                _inflight_open(_ctx * max(_pi, _pw) / 1e6 + cap * _po / 1e6)
        attempt = -1   # b65-final: a while loop, so a pin error ($0, retried after PIN_BACKOFF_S) does not use up a transport attempt
        while attempt + 1 < args.max_api_retries:   # interruptible instances pause when outbid: raise this (e.g. 20) to ride it out
            attempt += 1
            if _pc_on:   # --budget-reclaim: charged before it is sent (see _inflight_open); cap <= the cap the gate fitted, so spend stays <= budget
                _inflight_open(_ctx * max(_pi, _pw) / 1e6 + cap * _po / 1e6)
            try:
                if args.endpoint == "openai":
                    m = _oai.with_rate_limit_retry(lambda: _oai.with_connect_retry(lambda: _oai.create(
                                    base_url=args.base_url, api_key=_oai_key, model=api_model, max_tokens=cap, system=(SYSTEM if args.length_tools else SYSTEM_BASE), tools=tools_now, messages=msgs, extra_body=extra_body,
                                    **({"think_mode": MODEL_PRESETS[args.model_preset]["think_mode"], "cache": MODEL_PRESETS[args.model_preset]["cache"],
                                       "stream": MODEL_PRESETS[args.model_preset].get("stream", False),
                                       "guard": MODEL_PRESETS[args.model_preset].get("stream_guard", False)} if args.model_preset else {})),
                                    state=_cn, log=_cn_log, pause=_cn_pause, resume=_cn_resume),
                                    budget_s=args.rate_limit_budget, state=_rl, log=_rl_log)
                else:
                    with cl.messages.stream(model=api_model, max_tokens=cap, system=(SYSTEM if args.length_tools else SYSTEM_BASE), tools=tools_now, messages=msgs,
                                            extra_body=extra_body) as s:
                        m = s.get_final_message()
                break
            except anthropic.RateLimitError:
                time.sleep(min(30 * 2 ** attempt, 300))
            except anthropic.APIStatusError as e:
                if e.status_code in (529, 503, 500) or "overloaded" in str(e).lower():
                    time.sleep(min(30 * 2 ** attempt, 300)); continue
                if attempt >= 2:
                    log_f.write(json.dumps({"problem": name, "turn": turn, "status": f"api_error:{str(e)[:200]}"}) + "\n"); log_f.flush(); flush_traj({"type": "api_error", "turn": turn, "error": str(e)[:500]}); print(f"{name[:18]} turn {turn}: api error {str(e)[:120]}", flush=True); m = None; break
                time.sleep(10)
            except Exception as e:  # noqa: BLE001  (connection resets, timeouts, decode errors: retry with backoff, give up only after 6 tries)
                # 2026-10-20 price-trace audit: every failed attempt is in the trajectory (a 429 is not billed; a read timeout or a stream that
                # broke after the provider accepted the request may be, and the meter cannot see it), so a provider bill can be reconciled per call
                flush_traj({"type": "api_retry", "turn": turn, "attempt": attempt, "max_tokens": cap, "status": getattr(e, "status_code", None),
                            "error": f"{type(e).__name__}: {str(e)[:300]}", "seconds": round(time.time() - t_call, 1),
                            **({"before_data": True} if getattr(e, "before_data", False) else {}),   # b64 F3: returned before any stream data
                            **({"not_sent": True} if getattr(e, "not_sent", False) else {}),   # b66 (A4): a connect failure past its budget ($0)
                            **({"gen_id": e.gen_id} if getattr(e, "gen_id", None) else {})})
                if _pc_on:   # the pre-charge comes off; an attempt that may have been billed is charged its worst case just below
                    _inflight_close()
                _pin = pin_unservable(e, args.model_preset) if args.model_preset else None
                if _pin:   # b65-final: a pin error, refused before any data ($0: maybe_billed is False): retried after a backoff until it
                    # is answered or CONFIRMED (harness/pinwatch.py); a confirmed pin ends the session (and exits PIN_FATAL_RC at the end)
                    PW.append_event(out_dir, args.model_preset, name, getattr(e, "status_code", None), _pin)
                    _conf = (PINS.observe(args.model_preset, name, _pin, status=getattr(e, "status_code", None))   # review: a 503 = streak only
                             or (_pin_dead() and f"CONFIRMED elsewhere: {_pin_dead()}"))
                    flush_traj({"type": "pin_unservable", "turn": turn, "preset": args.model_preset, "pin": max_price_of(args.model_preset),
                                "status": getattr(e, "status_code", None), "error": str(e)[:500], "confirmed": bool(_conf)})
                    if _conf:
                        _c = PINS.confirmed.get(args.model_preset) or {}
                        write_pin_marker(out_dir, args.model_preset, _conf, why=_c.get("why"), rows=len(_c.get("rows") or []) or None)
                        log_f.write(json.dumps({"problem": name, "turn": turn, "status": f"pin_unservable:{str(e)[:200]}"}) + "\n"); log_f.flush()
                        print(f"{name[:18]:18s} turn {turn}: {pin_fatal_line(args.model_preset, _conf)}", flush=True)
                        PINS.skip(args.model_preset, name)
                        m = None; break
                    print(f"{name[:18]:18s} turn {turn}: pin error (not confirmed; retry in {PW.PIN_BACKOFF_S:.0f} s, $0): {_pin[:160]}", flush=True)
                    if PW.wait_backoff(PW.PIN_BACKOFF_S, _pin_dead):   # a confirmation from elsewhere ends the wait (and the session)
                        print(f"{name[:18]:18s} turn {turn}: {pin_fatal_line(args.model_preset, _pin_dead() or _pin)}", flush=True)
                        PINS.skip(args.model_preset, name)
                        m = None; break
                    attempt -= 1; continue
                if args.budget_reclaim and args.model_preset and maybe_billed(e) and not MODEL_PRESETS[args.model_preset].get("adaptive_cap"):
                    # 2026-10-22 (lever 5): a reclaim session runs up to the budget edge, so an attempt the provider may have billed (13 transport
                    # errors / 5xx in 21,784 Sol turns) is charged its worst case before the retry, and the retry must fit what is left
                    _wc = _ctx * max(_pi, _pw) / 1e6 + cap * _po / 1e6
                    if getattr(e, "gen_id", None):   # b64 F3: a started stream is priced from its generation record (OpenRouter), not assumed
                        # (the junk-cut path's bound, 8 x 3 s, before data too: a record that is late must not read as no record, i.e. $0)
                        _lk = ((lambda g_: _oai.generation_usage(args.base_url, _oai_key, g_))
                               if "openrouter.ai" in (args.base_url or "") or os.environ.get("LRA_SELFTEST_GENERATION") else None)
                        _wc, _fa = failed_attempt_charge(e, _wc, _lk, lambda u_: attempt_meter_usd(MODEL_PRESETS[args.model_preset], u_))
                        flush_traj({"type": "failed_attempt_billing", "turn": turn, "attempt": attempt, "usd": round(_wc, 6), **_fa})
                    ws.state["api_spend"] = round(float(ws.state.get("api_spend") or 0) + _wc, 6)
                    ws.state["assumed_spend"] = round(float(ws.state.get("assumed_spend") or 0) + _wc, 6); ws.save()
                    flush_traj({"type": "assumed_spend", "turn": turn, "attempt": attempt, "usd": round(_wc, 6), "max_tokens": cap})
                    _rc, _rr = fit_output_cap(args.budget_usd, _gate_spend(), _ctx * max(_pi, _pw) / 1e6, _po, cap,
                                              args.reclaim_floor, 1.25 * _sess_turn_max)
                    if _rc is None:
                        print(f"{name[:18]:18s} budget reached: ${_gate_spend():.3f} after a failed attempt charged ${_wc:.3f} "
                              f"(may have been billed); no retry fits ${args.budget_usd:.2f}; session ends", flush=True)
                        flush_traj({"type": "budget_stop", "turn": turn, "error": f"{type(e).__name__}: {str(e)[:400]}"})
                        m = None; break
                    cap, _reclaim_cap, _turn_reserve = _rc, _rc, _rr
                if attempt >= args.max_api_retries - 1 or getattr(e, "rate_limit_exhausted", False) or getattr(e, "connect_exhausted", False):
                    log_f.write(json.dumps({"problem": name, "turn": turn, "status": f"api_error:{str(e)[:200]}"}) + "\n"); log_f.flush(); flush_traj({"type": "api_error", "turn": turn, "error": str(e)[:500]}); print(f"{name[:18]} turn {turn}: api error {str(e)[:120]}", flush=True); m = None; break
                time.sleep(min(10 * 2 ** attempt, 300))
        if m is None:
            break
        if args.model_preset and max_price_of(args.model_preset) and PINS.answered(args.model_preset, name, out_dir):
            # b65-final: answered after pin errors: the pin serves (its earlier errors, every row's, stop counting; harness/pinwatch.py)
            flush_traj({"type": "pin_cleared", "turn": turn, "preset": args.model_preset})
            print(f"{name[:18]:18s} turn {turn}: answered after pin error(s): the pin serves (not confirmed)", flush=True)
        if _pc_on:   # answered: back to the spend before the attempt; the meter below adds what it cost
            _inflight_close()
        # Budget forcing (2026-10-08; self-hosted endpoint only, where we control the chat template): a turn that hit its cap while still
        # thinking (no tool call, no text) is not thrown away. Its thinking is sent back closed with </think> and the SAME assistant turn continues
        # (vLLM continue_final_message), so the model must act now. Unbiased LR-eval: 61% of A100 high-effort answers hit 32k while thinking.
        if (args.endpoint == "openai" and args.budget_forcing and m.stop_reason == "max_tokens"
                and not any(b.type == "tool_use" for b in m.content) and not any(b.type == "text" and (b.text or "").strip() for b in m.content)):
            _think = "".join(b.thinking or "" for b in m.content if b.type == "thinking")
            if _think:
                try:
                    _forced = msgs + [{"role": "assistant", "content": [{"type": "thinking", "thinking": _think + "\n(Thinking budget reached: act now with one tool call.)"}]}]
                    _m2 = _oai.create(base_url=args.base_url, api_key=_oai_key, model=api_model, max_tokens=args.max_tokens,
                                      system=(SYSTEM if args.length_tools else SYSTEM_BASE), tools=tools_now, messages=_forced,
                                      extra_body={**extra_body, "continue_final_message": True, "add_generation_prompt": False})
                    if not any(b.type in ("tool_use", "text") for b in _m2.content):
                        # the continuation arrives labelled as reasoning (no </think> in the output): read it as the answer, parse tool calls here
                        _txt = "".join(b.thinking or "" for b in _m2.content if b.type == "thinking")
                        _rest, _calls = _oai.parse_glm_tool_calls(_txt)
                        if _calls:
                            _m2.content = ([_oai.Block(type="text", text=_rest)] if _rest else []) + _calls
                            _m2.stop_reason = "tool_use"
                        elif _txt.strip():
                            _m2.content = [_oai.Block(type="text", text=_txt)]
                    if any(b.type in ("tool_use", "text") for b in _m2.content):
                        _m2.content = [b for b in m.content if b.type == "thinking"] + [b for b in _m2.content if b.type != "thinking"]
                        _m2.usage = type(m.usage)(m.usage.input_tokens + _m2.usage.input_tokens, m.usage.output_tokens + _m2.usage.output_tokens)
                        m = _m2; forced_turns_bf += 1
                        print(f"{name[:18]:18s} turn {turn}: budget forcing rescued a capped turn ({m.stop_reason}, {[b.name for b in m.content if b.type == 'tool_use']})", flush=True)
                        flush_traj({"type": "budget_forcing", "turn": turn, "stop": str(m.stop_reason), "tools": [b.name for b in m.content if b.type == "tool_use"]})
                except Exception as _e:  # noqa: BLE001
                    print(f"{name[:18]:18s} turn {turn}: budget forcing failed: {str(_e)[:160]}", flush=True)
        # Cycle 47: the same rescue on z.ai, where the template trick is unavailable. A turn capped while still thinking (7% of turns, 16% of
        # opening turns, 12-16k tokens each) is re-asked once with thinking DISABLED (z.ai accepts {"thinking": {"type": "disabled"}}: an
        # immediate tool call in ~5 s) and the tail of the cut reasoning appended to the last user message, so the turn ends in an action.
        if (args.endpoint != "openai" and m.stop_reason == "max_tokens" and not any(b.type == "tool_use" for b in m.content)
                and not any(b.type == "text" and (b.text or "").strip() for b in m.content)):
            _tail = "".join(getattr(b, "thinking", "") or "" for b in m.content if b.type == "thinking")[-2500:].strip()
            _note = ("[harness] Your previous reply hit the output limit while still thinking and was discarded. "
                     + (f"The end of that reasoning was:\n<<<\n{_tail}\n>>>\n" if _tail else "")
                     + ("Act on it now with ONE tool call and minimal text (a lean_batch of the edits you planned); do not resend the "
                        "current best unchanged." if golf else
                        "Act on it now with ONE tool call and minimal text (a lean_check_variants batch of the edits you planned, or "
                        "write_file of a NEW candidate); do not rewrite the current best unchanged."))
            _last = msgs[-1]
            _content = ([*_last["content"], {"type": "text", "text": _note}] if isinstance(_last["content"], list) else _last["content"] + "\n\n" + _note)
            _forced = msgs[:-1] + [{**_last, "content": _content}]
            try:
                _eb = {k: v for k, v in extra_body.items() if k not in ("reasoning_effort", "reasoning")}
                _eb["thinking"] = {"type": "disabled"}
                _m2 = cl.messages.create(model=api_model, max_tokens=args.max_tokens, system=(SYSTEM if args.length_tools else SYSTEM_BASE),
                                         tools=tools_now, messages=_forced, extra_body=_eb)
                if not any(b.type == "tool_use" for b in _m2.content):
                    # cycle 48: in the held-out A/B a real rescue left no trace; with thinking off GLM may write its call as template
                    # markup in the text (<tool_call>name<arg_key>…) instead of a tool_use block: parse it like the budget-forced path
                    from llm import openai_compat as _oaic
                    _rest, _calls = _oaic.parse_glm_tool_calls("".join(b.text or "" for b in _m2.content if b.type == "text"))
                    if _calls:
                        _m2.content = ([_oaic.Block(type="text", text=_rest)] if _rest else []) + _calls; _m2.stop_reason = "tool_use"
                _rtools = [b.name for b in _m2.content if b.type == "tool_use"]
                _rtext = "".join(getattr(b, "text", "") or "" for b in _m2.content if b.type == "text")
                flush_traj({"type": "nothink_rescue", "turn": turn, "ok": bool(_rtools), "stop": str(_m2.stop_reason), "tools": _rtools,
                            "text": _rtext[:400], "output_tokens": _m2.usage.output_tokens})
                if not _rtools:
                    print(f"{name[:18]:18s} turn {turn}: no-thinking retry gave no tool call (stop {_m2.stop_reason}, text {_rtext[:100]!r})", flush=True)
                if _rtools:
                    msgs[-1] = _forced[-1]   # keep what the model actually saw
                    _m2.usage.output_tokens += m.usage.output_tokens
                    m = _m2; forced_turns_bf += 1
                    print(f"{name[:18]:18s} turn {turn}: no-thinking retry rescued a capped turn ({_rtools})", flush=True)
            except Exception as _e:  # noqa: BLE001
                print(f"{name[:18]:18s} turn {turn}: no-thinking retry failed: {str(_e)[:160]}", flush=True)
        total_out += m.usage.output_tokens
        _unk = bool(args.model_preset) and _or_billed and unknown_bill(m)   # b65 (2): charged the call's worst case below
        if args.model_preset:   # per-problem spend meter (cap $3/problem): provider cost when reported, else the price table
            _u = m.usage
            # list_price presets ignore the provider-reported cost: ClinePass reports exactly half of DeepSeek's standard list price
            # (off-peak rate), and the closed track is audited at the public list price (2026-10-11)
            # B34 patch review: a list_price preset meters at its table, but never below a reported cost, so a provider price rise (Argon's
            # $2/$10 is introductory) cannot under-count against the $3 cap; ClinePass's half-price report and OpenRouter's 0.99x keep the table
            # b65 (3): a meter_billed preset (Sol on OpenRouter, pinned at list) meters the billed cost; (2) an unknown bill counts its worst case
            _c, _cc = turn_charge(args.model_preset, m, _ctx, cap, unknown_worst=_or_billed)   # (metered, at the cap prices: b64 L0)
            _sp0 = float(ws.state.get("api_spend") or 0)
            ws.state["api_spend"] = round(_sp0 + _c, 6)
            if _rec_on and getattr(m, "raw_finish_reason", None) == "junk_abort" and getattr(_u, "cost", None) is None and getattr(m, "gen_id", None):
                # b64 L1 (c): charged its worst case (no generation record yet); reconciled once the record arrives (_reconcile)
                ws.state.setdefault("billing_pending", []).append({"gen_id": m.gen_id, "charged": round(_c, 6), "run_id": args.run_id, "turn": turn,
                                                                   "turn_max_before": round(_sess_turn_max, 6), "preset": args.model_preset,
                                                                   "sess_idx": len(_sess_costs)})
            # budget milestones: the turn whose spend crosses one records a
            # snapshot (spend, best so far, run, turn) in state.json and the trajectory, once per problem and milestone
            for _ms in (float(x) for x in args.budget_milestones.split(",") if x.strip()):
                if _sp0 < _ms <= ws.state["api_spend"] and f"{_ms:g}" not in ws.state.get("budget_milestones", {}):
                    _snap = {"spend": ws.state["api_spend"], "best": best["score"], "run_id": args.run_id, "turn": turn,
                             "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                    ws.state.setdefault("budget_milestones", {})[f"{_ms:g}"] = _snap
                    print(f"{name[:18]:18s} budget milestone ${_ms:g} crossed: spend ${_snap['spend']:.3f}, best {_snap['best']} (cap ${args.budget_usd:.2f})", flush=True)
                    flush_traj({"type": "budget_milestone", "usd": _ms, **_snap})
            if _cap_diff:   # b64 L0: the same turn at the cap prices (never below a reported cost); the gate counts the difference too
                ws.state["cap_extra"] = round(float(ws.state.get("cap_extra") or 0) + max(0.0, _cc - _c), 6)
            ws.save()
            _sess_turn_max = max(_sess_turn_max, _cc); _last_in_tokens = _u.input_tokens
            if _rec_on:   # b64-it3 (L0 x L1): at the gate's cap prices, as _sess_turn_max (= _c for every preset without cap_prices)
                _sess_costs.append(_cc)
        # 2026-10-14 (warm-up clean recheck): OpenRouter + Sol can report finish_reason "tool_calls" on a turn cut at the output cap (a 394k-char
        # runaway lean_skeleton call at exactly 12,000 output tokens, stop "tool_use"), so the stop reason alone missed it: the junk call stayed in
        # the history (+156k input tokens, $0.39 on the next turn) and was executed. A turn that used the whole cap counts as truncated.
        last_truncated = (m.stop_reason == "max_tokens") or (m.usage.output_tokens or 0) >= cap
        uses = [b for b in m.content if b.type == "tool_use"]
        # 2026-10-11 (warm-up Sol run: 20 of 54 sessions had a turn cut at the 12k output cap, 22% of the run's spend): Sol degenerates
        # inside a tool-call argument (an endless `\t\t\t \n` tail) until the cap. The unparseable call ({"_raw_arguments": 40k-450k chars})
        # stayed in the conversation and was re-sent every later turn (+65k input tokens on Electromagnetism), inflating the budget gate's
        # reserve. Drop any truncated unparseable call from the history (it cannot execute; the full text goes to the trajectory) and say
        # so in its tool result; when its tail is degenerate repetition, also do not escalate the output cap: more room only buys more junk.
        runaway = [u for u in uses if last_truncated and isinstance(u.input, dict) and "_raw_arguments" in u.input]
        runaway_junk = False
        salvaged = {}   # b64 L1 (b) --skeleton-salvage: tool_use id -> salvage record of a junk lean_skeleton call run on its draft
        for u in runaway:
            _raw = str(u.input.get("_raw_arguments") or "")
            _junk = degenerate_tail(_raw) or "_junk" in u.input   # a stream the guard cut (llm/junk.py) is junk by definition
            flush_traj({"type": "runaway_tool_call", "turn": turn, "tool": u.name, "chars": len(_raw), "degenerate": _junk, "raw": _raw})
            u.input = {"_dropped": f"cut at the output cap after {len(_raw)} chars of arguments"
                                   + (", ending in the same few characters repeated over and over" if _junk else "")}
            runaway_junk = runaway_junk or _junk
            print(f"{name[:18]:18s} turn {turn}: runaway {u.name} call cut at the output cap ({len(_raw)} chars) dropped from the history", flush=True)
            if _junk:
                _salvage_skeleton(u, _raw, salvaged)
        # 2026-10-14: junk inside a call whose JSON parsed (a write_file of quote
        # characters repeated thousands of times that still closed its string) and junk reply text are rejected the same way: never executed,
        # never re-sent (llm/junk.py).
        try:
            for u in uses:
                if isinstance(u.input, dict) and "_dropped" not in u.input and "_raw_arguments" not in u.input and u.id not in salvaged:
                    _why = junk_reason(json.dumps(u.input, ensure_ascii=False))
                    if _why:
                        flush_traj({"type": "junk_tool_call", "turn": turn, "tool": u.name, "reason": _why, "raw": u.input})
                        _orig = u.input
                        u.input = {"_dropped": f"rejected as junk ({_why[:120]})"}
                        runaway_junk = True
                        print(f"{name[:18]:18s} turn {turn}: junk {u.name} call rejected ({_why[:80]})", flush=True)
                        _salvage_skeleton(u, _orig, salvaged)
            for b in m.content:
                if b.type == "text" and b.text and junk_reason(b.text):
                    flush_traj({"type": "junk_text", "turn": turn, "reason": junk_reason(b.text), "chars": len(b.text)})
                    b.text = b.text[:1500] + "\n[the rest of this reply was degenerate repetition; cut by the harness]"
                    runaway_junk = True
            if getattr(m, "raw_finish_reason", None) == "junk_abort":
                flush_traj({"type": "junk_abort", "turn": turn, "output_tokens": m.usage.output_tokens, "cost": getattr(m.usage, "cost", None)})
                print(f"{name[:18]:18s} turn {turn}: junk stream cut after {m.usage.output_tokens} output tokens", flush=True)
        except Exception as _e:  # noqa: BLE001  (the junk checks never fail a session)
            print(f"{name[:18]:18s} turn {turn}: junk check failed: {type(_e).__name__}: {_e}", flush=True)
        trunc_count += 1 if last_truncated and not runaway_junk else 0   # a cut legitimate long write still escalates as before
        texts = [b.text for b in m.content if b.type == "text"]
        log_f.write(json.dumps({"problem": name, "turn": turn, "out_tok": m.usage.output_tokens, "stop": str(m.stop_reason), "tools": [u.name for u in uses], "text": "".join(texts)[:300]}) + "\n"); log_f.flush()
        # b64 F4 (docs/first_half_gap.md §4): the turn's OpenRouter generation id and provider (as the stream names it; else one GET /generation
        # per session, for the first such turn's id at the next turn, when its record exists: provider_lookup). Logging only.
        _f4 = {k_: v_ for k_, v_ in (("gen_id", getattr(m, "gen_id", None)), ("provider", getattr(m, "provider", None))) if v_}
        if _prov_lk.get("gen_id") and "provider" not in _prov_lk:
            _prov_lk["provider"] = _oai.generation_provider(args.base_url, _oai_key, _prov_lk["gen_id"])
            _f4["provider_lookup"] = dict(_prov_lk)
        elif (_f4.get("gen_id") and not _f4.get("provider") and not _prov_lk and args.model_preset
              and ("openrouter.ai" in (args.base_url or "") or os.environ.get("LRA_SELFTEST_GENERATION"))):
            _prov_lk["gen_id"] = _f4["gen_id"]
        flush_traj({"type": "turn", "turn": turn, "max_tokens": cap, "stop": str(m.stop_reason), "input_tokens": m.usage.input_tokens, "output_tokens": m.usage.output_tokens,
                    "cache_read": getattr(m.usage, "cache_read", None), "cost": getattr(m.usage, "cost", None),
                    # 2026-10-20: Azure reports tokens but no cost; keep the cache writes and
                    # the metered dollars per turn so the spend meter can be audited against the provider's usage
                    "cache_write": getattr(m.usage, "cache_write", None), "metered_usd": round(_c, 6) if args.model_preset else None,
                    **({"unknown_bill": "worst_case"} if _unk else {}),   # b65 (2): the estimate was raised to the call's worst case
                    # 2026-10-20 price-trace audit: reasoning tokens (already inside output_tokens, priced as output), whether the usage is an
                    # estimate (a junk-cut stream: llm/openai_compat Message.usage_estimated) and the attempts this turn's call took
                    "reasoning_tokens": getattr(m.usage, "reasoning", None), "usage_estimated": getattr(m, "usage_estimated", None),
                    "api_attempts": attempt + 1,
                    **({"budget_reclaim": {"full_cap": _cap_next, "worst_usd": round(_turn_reserve, 6)}} if _reclaim_cap is not None else {}),
                    "seconds": round(time.time() - t_call, 1), "tools": [u.name for u in uses], "checks_so_far": checks, "best_so_far": best["score"],
                    **({"rate_limit_hits": _rl["hits"], "rate_limit_wait_s": round(_rl["waited"], 1)} if _rl.get("hits") else {}), **_f4})
        if not uses:
            if (m.stop_reason == "max_tokens" and args.model_preset and MODEL_PRESETS[args.model_preset].get("continue_on_length")
                    and cut_continuations < 1 and not runaway_junk):
                # the IMO-setup length guard (2026-10-14): a deep reasoner cut while thinking continues from its replayed reasoning
                # once; a second consecutive cut gets the act-now message below
                cut_continuations += 1
                msgs += [{"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in m.content] or [{"type": "text", "text": "(truncated)"}]},
                         {"role": "user", "content": "Your output was cut by the length limit while you were reasoning. Continue from where your "
                          "reasoning stopped, then act with a tool call."}]
                flush_traj({"type": "length_continuation", "turn": turn, "output_tokens": m.usage.output_tokens})
                continue
            if m.stop_reason == "max_tokens":
                # Cycle 43: the old "write_file your current best candidate" made 5 of 14 post-truncation writes byte-identical to the best (a
                # wasted turn after the wasted 12k-token one). Hand back the tail of the cut reasoning (thinking from earlier turns may not be kept
                # in context) and ask for the planned edits as variants.
                _tail = "".join(getattr(b, "thinking", "") or "" for b in m.content if b.type == "thinking")[-2500:].strip()
                msgs += [{"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in m.content] or [{"type": "text", "text": "(truncated)"}]},
                         {"role": "user", "content": "You ran out of output budget without calling a tool. "
                          + (f"The end of your cut reasoning was:\n<<<\n{_tail}\n>>>\n" if _tail else "")
                          + ("Act on it now with ONE tool call and minimal text: send the edits you were planning as one lean_batch (find/replace "
                             "items). Do not resend the current best unchanged." if golf else
                             "Act on it now with ONE tool call and minimal text: send the edits you were planning as one lean_check_variants call "
                             "(3-6 FULL variants of candidate.lean), or write_file a NEW candidate. Do not rewrite the current best unchanged (it is already "
                             "checked and banked).")}]
                continue
            # Cycle 52: ending a turn with text only is an implicit finish and bypassed the finish guard: gpt-oss-120b (second-model
            # screen) stopped a 40-turn run after 4 turns this way. Apply the same rule as `finish`: refuse while a third of the budget
            # remains (at most 2 refusals per run). Flash never ended a held-out run this way.
            _left = args_turns - turn - 1
            if golf and not (G.stop_ok(golf_evals, golf_since_gain, args.golf_min_evals, args.golf_flat_evals) or golf_budget_low()) and finish_rejections < 6:
                finish_rejections += 1
                msgs += [{"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in m.content] or [{"type": "text", "text": "(no reply)"}]},
                         {"role": "user", "content": "You ended your turn without a tool call. " + G.refusal(golf_evals, golf_since_gain, args.golf_min_evals,
                                                                                                              args.golf_flat_evals)}]
                continue
            if not golf and (_left >= max(4, args_turns // 3) or (artifact and artifact.get("holes") and not artifact_done[0] and _left >= max(2, args_turns // 3))) and finish_rejections < 2:
                finish_rejections += 1
                msgs += [{"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in m.content] or [{"type": "text", "text": "(no reply)"}]},
                         {"role": "user", "content": f"You ended your turn without a tool call, but {_left} turns remain and the run continues. "
                          f"Best so far {best['score']} (reference 33.33). Work on the proof now with a tool call: a lean_check_variants batch of "
                          "3-6 different candidates (a new architecture if local edits are exhausted), lean_profile, lean_goals or lean_search. "
                          "Call finish only in the last third of the budget."}]
                continue
            break  # finished talking without tools
        cut_continuations = 0
        results = []
        done = False
        turns_since_check += 1
        n_rejected = 0
        for u in uses:
            tool_calls += 1; inp = u.input or {}
            if u.name in ("lean_check", "lean_check_variants", "lean_mine", "lean_batch") and "_dropped" not in inp:
                turns_since_check = 0
            try:
                if golf and u.name not in {t_["name"] for t_ in TOOLS}:   # B62c: only the golf tools are offered; refuse the rest
                    out = f"unknown tool {u.name} in this session (tools: {', '.join(t_['name'] for t_ in TOOLS)})"
                elif "_dropped" in inp:   # a runaway call cut at the output cap (above): nothing is executed
                    out = (f"Your {u.name} call was {inp['_dropped']}; it was dropped and nothing was executed. Write compactly and in smaller "
                           "pieces: one candidate per write_file without padding or trailing whitespace, at most 3 variants per "
                           "lean_check_variants, then continue.")
                elif u.name == "read_file":
                    txt = ws.path(inp["path"]).read_text(); lines = txt.split("\n")
                    s0 = max(1, int(inp.get("start") or 1)); e0 = min(len(lines), int(inp.get("end") or min(len(lines), s0 + 199)))
                    out = "\n".join(f"{i:5d}| {lines[i-1]}" for i in range(s0, e0 + 1)) + (f"\n... ({len(lines)} lines total)" if e0 < len(lines) else "")
                elif u.name == "write_file":
                    ws.path(inp["path"]).write_text(inp["content"]); out = f"wrote {Path(inp['path']).name} ({len(inp['content'])} chars)"
                    if Path(inp["path"]).name == "candidate.lean":
                        _dn = _dup_note(); out += _dn
                        # Cycle 44: 26 of 405 turns in the measurement + top-up runs were a bare lean_check right after a write_file turn.
                        # Check the new candidate in the same tool result (not for drafts with sorry holes: those go to lean_skeleton).
                        if not _dn and "sorry" not in inp["content"]:
                            out += "\n[auto lean_check of candidate.lean — do not check it again]\n" + lean_check("candidate.lean"); turns_since_check = 0
                    if Path(inp["path"]).name == "notes.md":
                        notes_written = True
                elif u.name == "lean_check":
                    out = lean_check(inp.get("path") or "candidate.lean")
                elif u.name == "shell":
                    # POC 2 scout rule (enforced, not just prompted): a 12-turn scout spent 7 turns on grep and never checked a candidate.
                    if args.from_reference and (checks == 0 or shell_calls >= 3):
                        n_rejected += 1
                        out = ("scout rule: " + ("no shell exploration before your first lean_check / lean_check_variants — write a candidate of your own architecture now and check it"
                                                 if checks == 0 else "shell budget (3 calls) exhausted for this scout run — write and check candidates instead"))
                    else:
                        shell_calls += 1; _h0 = _cand_sha(); out = shell(inp.get("command") or "")
                        if not searched and _LEMMA_GREP.search(inp.get("command") or ""):
                            lemma_greps += 1
                            if lemma_greps in (2, 5):
                                out += ("\n\n[harness] You are hunting library lemmas by hand. lean_search does this in one call: it ranks lemmas by match with the "
                                        "goals of candidate.lean (exact? at each goal with probes=true, unused same-file lemmas, simp/grind attributes) and returns "
                                        "signatures. Try it before the next grep.")
                        if _cand_sha() != _h0:   # only when the command changed candidate.lean (read-only greps stay silent)
                            out += _dup_note()
                elif u.name == "lean_run":
                    out = lean_run(inp.get("code") or "")
                elif u.name == "lean_check_variants":
                    out = lean_check_variants(inp.get("variants"))
                elif u.name == "lean_search":
                    searched = True
                    out = lean_search(inp.get("path") or "candidate.lean", bool(inp.get("probes")))
                elif u.name == "lean_skeleton":
                    out = lean_skeleton(inp.get("path") or "", inp.get("content") or "")
                    if u.id in salvaged:   # b64 L1 (b): the junk call's draft, salvaged (the call in the history now shows exactly what ran)
                        out = (f"[harness] Your lean_skeleton call ran into repeated filler after the draft ({salvaged[u.id]['dropped_chars']} "
                               "characters dropped). The draft before the filler was salvaged and checked; your call above now shows it. "
                               "End each call right after the draft.\n" + out)
                elif u.name == "lean_profile":
                    out = lean_profile(inp.get("path") or "candidate.lean")
                elif u.name == "lean_goals":
                    out = lean_goals(inp.get("path") or "candidate.lean", inp.get("depth") or 1, inp.get("from_line") or 0)
                elif u.name == "lean_mine":
                    out = lean_mine(inp.get("path") or "candidate.lean")
                elif u.name == "lean_batch" and golf_inc is not None:
                    out = lean_batch(inp)
                elif u.name == "hb_profile" and golf_inc is not None:
                    out = hb_profile_tool(inp)
                elif u.name == "pool" and golf_inc is not None:
                    out = pool_tool(inp)
                elif u.name == "finish":
                    # Premature finish guard: pass 5 lost a whole 40-turn budget on a dev row (finish at turn 5 after one
                    # re-check of the existing best). Accept finish only near the end of the budget or after real work.
                    remaining = args_turns - turn - 1
                    if golf:   # B62c: the harness stop rule, not the turn count (a session that stops early loses)
                        if G.stop_ok(golf_evals, golf_since_gain, args.golf_min_evals, args.golf_flat_evals) or golf_budget_low() or finish_rejections >= 6:
                            out = "ok"; done = True
                        else:
                            finish_rejections += 1
                            out = G.refusal(golf_evals, golf_since_gain, args.golf_min_evals, args.golf_flat_evals)
                    elif hardtail_target and hardtail_batches == 0 and remaining > 1 and finish_rejections < 3:
                        # smoke test 2026-10-07: the model finished at turn 2 without trying a single new architecture
                        finish_rejections += 1
                        out = (f"finish rejected: this is a hard-tail strategy run and no new architecture has been tried yet. The goal map is in the "
                               f"opening message. Do steps 2-4 now: plan in notes.md, lemma-search 2-3 routine steps with lean_run, then send 3-5 FULL "
                               f"candidates of different architecture (each <= {hardtail_target} tokens) in ONE lean_check_variants call.")
                    elif args_turns <= 10 and checks == 0 and remaining > 0 and finish_rejections < 2:
                        finish_rejections += 1   # cycle 38: short runs ended with zero checks
                        out = ("finish rejected: this short polish run has made no check yet. Send one lean_check_variants call with 3-6 single-edit "
                               "variants of candidate.lean now; finish after that.")
                    elif artifact and artifact.get("holes") and not artifact_done[0] and remaining >= max(2, args_turns // 3) and finish_rejections < 3:
                        # b63 item 16: a shown skeleton with open holes counts as unfinished while a third of the budget remains
                        finish_rejections += 1
                        out = (f"finish rejected: the shown ARTIFACT (candidate.lean at the start) has {len(artifact['holes'])} open hole(s) and no compiling "
                               f"candidate derived from it has been checked yet; {remaining} turns remain. Fill the holes (lean_skeleton returns each hole's "
                               "goal), lean_check the full text, then finish. finish is accepted in the last third of the budget.")
                    elif remaining >= max(4, args_turns // 3) and finish_rejections < 2:
                        # Cycle 41 (measurement pass, a dev row): finished at turn 21/40 right after a new best, "local attack exhausted". Under R3 that is the
                        # moment for a NEW architecture, not for stopping: refuse finish while a third of the budget remains.
                        finish_rejections += 1
                        out = (f"finish rejected: {remaining} turns remain (a third or more of the budget). If local edits are exhausted, that is the signal for "
                               "a NEW rewrite with a different architecture (R3): outline it with sorry holes, check with lean_skeleton, use the LIBRARY LEADS, "
                               "the WINNING EDITS and the technique cards. finish is accepted in the last third of the budget.")
                    elif remaining > 3 and (checks < 5 or turn < args_turns // 2) and finish_rejections < 2:
                        finish_rejections += 1
                        out = (f"finish rejected: {remaining} turns remain and this run has done only {checks} lean_check(s) "
                               f"(best so far {best['score']}, reference 33.33). Re-checking the existing best is pointless. "
                               "Take the first untried item under 'Next ideas' in notes.md (or profile the costliest steps with lean_run), "
                               "edit candidate.lean, lean_check, and keep going. finish is accepted after 5 checks or in the last 3 turns.")
                    else:
                        out = "ok"; done = True
                else:
                    out = f"unknown tool {u.name}"
            except Exception as e:  # noqa: BLE001
                out = f"tool error: {e}"
            if args.lean_io and u.name in ("shell", "lean_run", "read_file") and len(out) > 1500:   # --lean-io output cap
                out = out[:1500] + f"\n... [truncated: {len(out) - 1500} more chars; narrow the command, or read_file with start/end]"
            results.append({"type": "tool_result", "tool_use_id": u.id, "content": out[:12000]})
        if args.from_reference and uses and n_rejected == len(uses) and extra_turns < 6:
            args_turns += 1; extra_turns += 1   # cycle 24: scout A lost ~4 of 12 turns to rejected shell calls; refund them (max 6)
        msgs += [{"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in m.content]}, {"role": "user", "content": results}]
        if done:
            break
    _reconcile(3, 5.0)   # b64 L1 (c): bounded (3 lookups, 5 s apart); a record still missing is looked up again by the next session
    if args.normalize and ws.state["best"].get("proof"):
        # 2026-10-10 (docs/break_90_panel.md item 1): a model-free lexer post-pass on the session's best
        # (harness/normalize.py: λx, $, bare trailing fun, <|, ;). Every rewrite is compiled on every toolchain; an improvement is scored
        # and recorded through the standard checker with this run's provenance, marked normalized. It never fails the session.
        try:
            from harness.normalize import normalize as _norm
            from harness.leantools import lean_check as _lc
            _nr = _norm(name, ws.state["best"]["proof"])
            if _nr.get("status") == "improved":
                _lc(name, _nr["proof"], ws.state, {"kind": ("closed-dev-only" if args.model_preset else "api-dev-only"), "model": prov_model, "run_id": args.run_id, "mode": "agent",
                                                   "check": checks + 1, "normalized": _nr.get("applied")}, out_dir / "verified.jsonl")
                ws.save(); best = dict(ws.state["best"])
                if best.get("proof"):
                    (ws.root / "best.lean").write_text(best["proof"].rstrip() + "\n")
                print(f"{name[:18]:18s} normalized: {_nr['before']['tokens']} -> {_nr['after']['tokens']} tokens, score {_nr['before']['score']} -> "
                      f"{_nr['after']['score']} ({_nr.get('applied')}, {_nr.get('compiles')} compiles)", flush=True)
            else:
                print(f"{name[:18]:18s} normalizer: {_nr.get('status')}", flush=True)
        except Exception as _e:  # noqa: BLE001
            print(f"{name[:18]:18s} normalizer failed: {type(_e).__name__}: {_e}", flush=True)
    summary = {"problem": name, "best_score": best["score"], "checks": checks, "tool_calls": tool_calls, "turns": turn + 1, "out_tokens": total_out, "seconds": round(time.time() - t_start)}
    if golf:
        summary.update({"mode": "golf", "golf_evaluations": golf_evals, "golf_gains": golf_gains, "golf_since_gain": golf_since_gain,
                        "golf_best_exact": round(golf_inc["score"], 6) if golf_inc else None, "spend": round(float(ws.state.get("api_spend") or 0), 4)})
    if _nn is not None:   # L1: lookups, answered results, lines shown, Lean queries and seconds, cache answers
        summary["name_neighbors"] = {k_: (round(v_, 1) if isinstance(v_, float) else v_) for k_, v_ in _nn.stats.items()}
    flush_traj({"type": "end", **summary, "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}); traj_f.close()
    # finished trajectories are committed gzipped (5-10x smaller); the plain file stays only while a run is in progress
    import gzip, shutil
    plain = pathlib.Path(traj_f.name); gz = plain.with_name(plain.name + ".gz")
    with plain.open("rb") as fi, gzip.open(gz, "ab") as fo:
        shutil.copyfileobj(fi, fo)
    plain.unlink()
    print(f"{name[:18]:18s} DONE best={best['score']} checks={checks} tool_calls={tool_calls} turns={turn+1} out_tok={total_out} {summary['seconds']}s", flush=True)
    return summary


# POC 2 (2026-10-07): multi-variant check — up to six full candidates scored in one call (like the lean_multi_attempt tool of public Lean tooling).
TOOLS.append({"name": "lean_check_variants",
              "description": "Compile, score and bank up to 6 FULL candidate variants in one call (each = complete declaration text, statement byte-identical to the reference). "
                             "Use it at a decision point instead of checking alternatives one per turn: e.g. the same proof with {simp_all | grind | omega | aesop} as the closer, "
                             "or three different case structures. Returns a table (ok, score, tokens, heartbeats, first error) and copies the best compiling variant to candidate.lean when it beats the current best.",
              "input_schema": {"type": "object", "properties": {"variants": {"type": "array", "minItems": 1, "maxItems": 6, "items": {"type": "object", "properties": {
                               "label": {"type": "string"}, "content": {"type": "string", "description": "full candidate text"}}, "required": ["content"]}}}, "required": ["variants"]}})
TOOLS.append({"name": "lean_mine",
              "description": "Mechanical length cutter for a COMPILING candidate (no thinking needed): replaces every `case`/typed `have`/bullet block by a "
                             "single closer (grind, simp_all, aesop, omega, fun_prop, norm_num, linarith, positivity, tauto, exact?), tries replacing each "
                             "tail of the proof by `all_goals first | grind | simp_all | aesop | omega | fun_prop`, and the whole proof by one closer; "
                             "combines what compiles, scores and banks it, and writes it to mined.lean (copied to candidate.lean if it beats the best). "
                             "Takes 1-3 minutes. Use it after every new compiling skeleton, then golf what it returns.",
              "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "candidate file (default candidate.lean)"}}}})
TOOLS.append({"name": "lean_search",
              "description": "Library lemma search for a candidate: lemmas whose name and conclusion match the goals, same-file lemmas the reference does not use, "
                             "@[simp]/@[grind]/@[to_fun] lemmas for the goal's symbols, induction principles; with probes=true it also runs exact? in place at each "
                             "step (slower, 1-2 min). Returns up to 10 ranked leads with signatures and why. Use it after a restructure, or when a block looks like "
                             "it should be one library lemma. Leads are not answers: check the signature against the goal.",
              "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "candidate file (default candidate.lean)"},
                                                                "probes": {"type": "boolean", "description": "also run exact? probes (default false: 2-25 s)"}}}})
TOOLS.append({"name": "lean_skeleton",
              "description": "Top-down development: check a DRAFT proof whose unfinished parts are `sorry` (as a tactic or as a term argument) and get the goal at "
                             "every hole plus any real errors. Use it to build a new architecture piece by piece: write the outline with holes, read each hole's goal, "
                             "fill one hole, re-run. Nothing is scored or banked; when no sorry remains, lean_check the candidate (sorry is forbidden there).",
              "input_schema": {"type": "object", "properties": {"content": {"type": "string", "description": "full draft declaration with sorry holes"},
                                                                "path": {"type": "string", "description": "or a workspace file holding the draft"}}}})


def skeleton_path_first(tools: list[dict]) -> None:
    """b64 L1 (a) (--skeleton-path-first; docs/plateau_levers.md L1): lean_skeleton's schema with `path` first and `content` last. In
    it1b/it2a/ck1a/ck1b, 151 of 961 lean_skeleton calls were junk (121 of them the session's first call), 99 of the 151 closed the draft
    string and then degenerated into whitespace exactly where `,"path": ""` would follow; write_file (path first, content last) had none.
    Both properties stay optional (many good calls send a path with empty content)."""
    for t in tools:
        if t["name"] == "lean_skeleton":
            p = t["input_schema"]["properties"]
            t["input_schema"]["properties"] = {"path": {"type": "string", "description": "a workspace file holding the draft (empty when you give content)"},
                                               "content": p["content"]}


def reconcile_billing(state: dict, lookup, meter, max_tries: int = 20, cap_meter=None) -> list[dict]:
    """b64 L1 (c) (--junk-billing-reconcile): each state["billing_pending"] entry is a junk-cut turn charged its worst case because its
    OpenRouter generation record was not available yet (24 of 124 junk turns in it1b..ck1b: $0.17 charged on average against about $0.04
    billed). `lookup(gen_id)` returns the record's Usage or None; once it arrives, api_spend gets (meter(usage, entry) - charged): the metered
    billed usage replaces the worst case (a credit; a debit if the record is higher). An entry still missing after `max_tries` lookups keeps
    its charge. A lookup or meter that raises counts as a missing record for that entry only, so each entry is credited at most once (review
    2026-10-26: an exception mid-list used to leave entries already credited in billing_pending). Returns the trajectory events.
    b64-it3 (L0 x L1): `cap_meter(usage, entry)` (optional) prices the record at the gate's cap prices; when it returns a number the event
    carries it as "billed_cap" (the session's reserve floor counts turns at the cap prices). api_spend always moves by the metered amount."""
    events, keep = [], []
    for p in state.get("billing_pending") or []:
        try:
            u = lookup(p["gen_id"])
            billed = float(meter(u, p)) if u is not None else None
            billed_cap = cap_meter(u, p) if (u is not None and cap_meter is not None) else None
        except Exception:  # noqa: BLE001
            u = billed = billed_cap = None
        p["tries"] = int(p.get("tries") or 0) + 1
        if u is None:
            if p["tries"] < max_tries:
                keep.append(p)
            else:
                events.append({"type": "billing_reconcile", "gen_id": p["gen_id"], "of_run": p.get("run_id"), "of_turn": p.get("turn"),
                               "charged": p["charged"], "billed_metered": None, "adjust": 0.0, "gave_up": True})
            continue
        adj = round(billed - float(p["charged"]), 6)
        state["api_spend"] = round(float(state.get("api_spend") or 0) + adj, 6)
        state["billing_adjust"] = round(float(state.get("billing_adjust") or 0) + adj, 6)
        events.append({"type": "billing_reconcile", "gen_id": p["gen_id"], "of_run": p.get("run_id"), "of_turn": p.get("turn"),
                       "charged": p["charged"], "billed_metered": round(billed, 6), "provider_cost": getattr(u, "cost", None), "adjust": adj,
                       "turn_max_before": p.get("turn_max_before"), "sess_idx": p.get("sess_idx"), "preset": p.get("preset")})
        if billed_cap is not None:
            events[-1]["billed_cap"] = round(float(billed_cap), 6)
    if keep:
        state["billing_pending"] = keep
    else:
        state.pop("billing_pending", None)
    return events


def metered_usd(preset: dict, u) -> float:
    """The spend meter of one call (--model-preset; run_problem's per-turn meter, failed attempts, the junk-cut reconcile, review.PricedCaller):
    the provider-reported cost when reported, else the price table; a list_price preset meters at its table but never below a reported cost.
    b65 (3) (2026-10-26: no 1.25x input margin): a meter_billed preset (Sol on OpenRouter, routed at its list price by its max_price
    pin) meters the billed cost OpenRouter reports for the call; its table only when no cost is reported. 2026-10-27 (Sol metered at
    the higher of billed cost and list price; the organizers may recompute cost from token counts at the public list price, and a row
    metered at a billed $3.00 is ~$3.03 at list): never below the call at its list table (list_floor_usd)."""
    _tab = table_cost(u, preset["prices"])
    cost = getattr(u, "cost", None)
    if cost is not None and preset.get("meter_billed"):
        return max(float(cost), list_floor_usd(preset, u))
    if cost is None:   # b65-final: at the cap prices when the pin admits endpoints above the table (meter_table)
        return table_cost(u, meter_table(preset))
    return cost if not preset.get("list_price") else max(_tab, float(cost))


def list_floor_usd(preset: dict, u) -> float:
    """b65 (2026-10-27): one call at the preset's public LIST table (list_prices: input, output, cache read, cache write per 1M), each
    token class priced once, as an audit recomputes it from the token counts. OpenRouter's streamed Sol usage reports cache writes apart
    (14,537 of 14,537 streamed turns with a cost in the warm-up clean runs: billed = 0.99 x this table, exactly); a /generation record has
    no cache-write count (openai_compat Usage.cw_reported False), so its uncached input is priced at the higher of the input and cache-write
    prices."""
    pi, po, pr, pw = preset["list_prices"]
    return table_cost(u, (pi if getattr(u, "cw_reported", True) else max(pi, pw), po, pr, pw))


def call_worst_usd(ctx_tokens: int, max_tokens: int, prices: tuple) -> float:
    """b65 (2): one call's worst case at a price table: its whole context billed uncached (at the higher of the input and cache-write
    prices) plus its whole output cap: what the pre-call gate reserves before the call is sent, and what a call whose bill stays unknown is
    charged."""
    pi, po, _pr, pw = prices
    return (ctx_tokens * max(pi, pw) + max_tokens * po) / 1e6


def unknown_bill(m) -> bool:
    """b65 (2): the call's bill is not known: its usage is an estimate (a junk-cut or usage-less stream without a generation record, the
    Responses path's estimates; openai_compat Message.usage_estimated) and no cost was reported."""
    return bool(getattr(m, "usage_estimated", None)) and getattr(getattr(m, "usage", None), "cost", None) is None


def turn_charge(preset: str, m, ctx_tokens: int, max_tokens: int, unknown_worst: bool = False) -> tuple[float, float]:
    """(metered, gate) USD of one answered call of a --model-preset session (run_problem's per-turn meter): the meter (metered_usd) and the
    same call at the cap prices (b64 L0: the table at cap_prices, never below a reported cost; = the meter for a preset without cap_prices).
    b65 (2): with unknown_worst (OpenRouter) a call whose bill is unknown (unknown_bill) counts at least the worst case the gate reserved
    for it (ctx_tokens uncached + its max_tokens), at each table, not the estimate (prompt chars / 3, or streamed chars / 3 + the ~2k-token
    reasoning allowance of llm/openai_compat), so the meter never under-counts a bill."""
    p = MODEL_PRESETS[preset]; u = m.usage; ct = cap_prices(preset)
    c = metered_usd(p, u)
    unk = unknown_worst and unknown_bill(m)
    if unk:
        c = max(c, call_worst_usd(ctx_tokens, max_tokens, meter_table(p)))
    if tuple(ct) == tuple(p["prices"]):
        return c, c
    cc = max(table_cost(u, ct), float(u.cost)) if getattr(u, "cost", None) is not None else table_cost(u, ct)
    return c, (max(cc, call_worst_usd(ctx_tokens, max_tokens, ct)) if unk else cc)


TOOLS.append({"name": "lean_profile",
              "description": "Heartbeat profile of a COMPILING tactic proof (Tier 1): where the heartbeats go, block by block (each block's cost, nested "
                             "blocks under the costliest step), the floor (the statement with a `sorry` body: H can never pass it) and the heartbeat points really "
                             "left. Costs include elaborating terms: notation such as `•` in a lambda or a `set` can cost more than a tactic. Use it before working on "
                             "heartbeats, and to decide between the token and heartbeat axes (see `axis` in lean_check). Takes 1-3 minutes; cached per proof.",
              "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "candidate file (default candidate.lean)"}}}})
TOOLS.append({"name": "lean_goals",
              "description": "Goal map of a tactic proof: compiles the candidate once with Lean's `trace_state` before every top-level step (depth 1) or also "
                             "before every step one level down inside bullets / `=>` arms / `by` blocks (depth 2), and returns, keyed by the file's line numbers, "
                             "the goal(s) each step faces (first goal with hypotheses, every further goal as `case <name>: ⊢ <target>`). Use it to see which "
                             "steps are routine, which cases look alike, and to copy exact goals into `example … := by exact?` lemma searches. ~5-10 s.",
              "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "candidate file (default candidate.lean)"},
                                                                "depth": {"type": "integer", "enum": [1, 2]},
                                                                "from_line": {"type": "integer", "description": "start at this line (paging for long proofs)"}}}})
SYSTEM += ("\n\nBATCH YOUR ALTERNATIVES: when you can think of 2-6 plausible rewrites of the same spot (different closers, different case structures, with/without a `have`), "
           "send them all in ONE lean_check_variants call rather than one lean_check per turn; every compiling variant is scored and banked, and the best one lands in candidate.lean. "
           "Each lean_check result also lists the costliest proof-body lines by token count: that is where the length axis is.")
SYSTEM_BASE = SYSTEM   # without the length experiment line (prompt text before it is shared)
# Cycle 83: the lexer rules as a constant, so --token-rules can give them to runs without --length-tools. The A100 and default Flash
# lines send SYSTEM_BASE and never saw them; the closed-line union review (2026-10-09) found no best proof using `f $ x`, 1 token
# less than `f (x)`.
# 2026-10-10 (hosted models on this harness, not opencode: Haiku 5.5, Sonnet 5.5, GPT-6.1 Sol, DeepSeek V4.1
# Flash): closed / hosted models run through THIS harness's own loop via the OpenAI-compatible path. Prices are USD per 1M tokens
# (input, output, cache read, cache write) and only back up a missing provider-reported cost. Results are closed-dev-only (never banked).
# They also price the worst-case turn for the cap gate, so they must not be below the real list price: on 2026-10-11 a fit over
# 1,493 Sol and 415 Sonnet billed turns gave exactly 0.99 x ($2.50 in, $10 out, $0.10 cache read) per 1M; Haiku 0.124 / 0.495.
# b64 L0 (cap safety; docs/plateau_levers.md section 2, docs/argon_eval.md): Gemini 4 Argon's $2 / $10 per 1M is an introductory price; Google
# announced $4 / $20 (no end date; one secondhand report says Nov 30) and no cached-input price, so the cached input is budgeted at 2x today's
# $0.10 and a cache write at the input price. The organizers rerun the final after the deadline, possibly at the announced price.
ARGON_ANNOUNCED = (4.00, 20.0, 0.20, 4.00)
# b65 (1) (2026-10-26: the whole $3.00 cap, made safe by mechanisms, not margins): OpenRouter routes a request to
# any endpoint of the model, at that endpoint's price. Public endpoint listing (GET /api/v1/models/<model>/endpoints, 2026-10-27), $ per 1M
# prompt / completion: openai/gpt-6.1-sol: OpenAI flex 1 / 5, OpenAI and Azure 2 / 10 (cache read 0.10, cache write 2.50), Bedrock and Azure
# eu / us 2.2 / 11, OpenAI fast 4 / 20, ultrafast 12 / 60; google/gemini-4-argon: AI Studio flex 1 / 5, AI Studio and Vertex global 2 / 10,
# Vertex us 2.2 / 11, priority tiers 3.6 / 18. provider.max_price (OpenRouter provider routing, $ per 1M) pins every request of a pinned
# preset to the endpoints at or below its LIST price (OpenAI's / Google's own price), so no endpoint can bill a token above the preset's
# table (the meter's fallback) or its cap prices (the gate; _check_max_price). Measured: OpenRouter bills 0.99 x the endpoint price (Sol:
# 0.99 x $2.50 per cache-written token; Argon: 37 review calls, fit $1.98 / $9.90). When NO endpoint satisfies the pin, OpenRouter does not run
# the request ("max_price ... will prevent your request from running if the price is not available", docs/features/provider-routing). Live
# check 2026-10-27 (Sol pinned at $1.99 / $9.99): HTTP 404 "No endpoints found that satisfy the max price for this request" (the API docs
# name a 503 "No allowed providers" for routing requirements no provider meets): an error before any stream data, which agent.maybe_billed /
# failed_attempt_charge (b64 F3) neither bill nor charge. b65-final (audit C3; pin_unservable and harness/pinwatch.py, below): such a pin
# ERROR is $0 and retried after a backoff; only a CONFIRMED pin (2 rows, or 3 tries over 10 min) stops paid work, and the run still finishes
# on its $0 path with complete outputs (a Sol pin: no new paid session; an Argon pin: that row's review skipped at $0). So a price rise above
# the pin stops spending instead of billing more. A pin may sit anywhere up to the preset's CAP prices (_check_max_price; e.g. Argon at its
# announced $4 / $20 = ARGON_ANNOUNCED, its table unchanged): a call without a reported cost is then metered at the cap prices (meter_table).
def max_price_pin(prompt: float, completion: float) -> dict:
    """b65 (1): the OpenRouter request field that pins routing to endpoints at or below these prices ($ per 1M prompt / completion tokens)."""
    return {"provider": {"max_price": {"prompt": prompt, "completion": completion}}}


SOL_LIST, ARGON_LIST = (2.00, 10.0), (2.00, 10.0)   # list price, $ per 1M prompt / completion (the endpoint listing above)
# b65 (2026-10-27: Sol metered at the higher of billed and list): Sol's whole public list table, $ per 1M input / output / cache read /
# cache write (OpenAI's and Azure's endpoints in the listing above); the meter's floor (list_floor_usd). Live pin check 2026-10-27 03:25 UTC
# (~$0.0003): max_price is inclusive and in $ per 1M: {2, 10} -> 200 from OpenAI, usage.cost 6.93e-05 for 10 in / 5 out (= 0.99 x list);
# {1.99, 9.99} -> HTTP 404 "No endpoints found that satisfy the max price for this request" (not the 503 the docs suggested)
SOL_LIST_PRICES = (*SOL_LIST, 0.10, 2.50)
# b65-final: GPT-6.1 Terra's public list (OpenRouter catalog, checked in probe/b65/steps_tests.md): $1 / $5 per 1M, cached $0.05; a cache write
# assumed at 1.25x the prompt price like Sol's
TERRA_LIST = (1.00, 5.0)
TERRA_LIST_PRICES = (*TERRA_LIST, 0.05, 1.25)
MODEL_PRESETS = {
    "haiku-5.5": dict(base_url="https://openrouter.ai/api/v1", key="~/.config/vexorium/oline-keys/openrouter_anthropic_claude-haiku-5.5.key",
                      api_model="anthropic/claude-haiku-5.5", cache=True, think_mode="details", prices=(0.125, 0.50, 0.01, 0.15625)),
    "sonnet-5.5": dict(base_url="https://openrouter.ai/api/v1", key="~/.config/vexorium/oline-keys/openrouter_anthropic_claude-sonnet-5.5.key",
                       api_model="anthropic/claude-sonnet-5.5", cache=True, think_mode="details", prices=(2.50, 10.0, 0.10, 3.125),
                       list_price=True),
    # 2026-10-12 (P0-5): the closed track audits spend at LIST price, while OpenRouter bills exactly 0.99 x this table, so the meter
    # and the hard cap gate price every turn from the table (list_price) instead of the reported (billed) cost. The table's input
    # price is 1.25x the catalog's ($2.50 vs $2.00 per 1M for Sol and Sonnet), so table-priced spend is an upper bound on list spend.
    "gpt-6.1-sol": dict(base_url="https://openrouter.ai/api/v1", key="~/.config/vexorium/oline-keys/openrouter_openai_gpt-6.1-sol.key",
                        api_model="openai/gpt-6.1-sol", cache=False, think_mode="details", prices=(2.50, 10.0, 0.10, 2.50),
                        list_price=True, stream_guard=True),   # 2026-10-14: streamed, junk cut mid-generation (llm/junk.py)
    # 2026-10-14: DeepSeek V4.1 Flash on
    # OpenRouter at list $0.02 in / $0.891 out / $0.005 cached per 1M (about 11x cheaper output than Sol), 201 tok/s measured; reasoning
    # is not replayed (think_mode none), turns streamed with the junk guard, a 40k output cap for its long reasoning.
    "deepseek-v4.1-flash-or": dict(base_url="https://openrouter.ai/api/v1", key="~/.config/vexorium/openrouter_api_key",
                                   api_model="deepseek/deepseek-v4.1-flash", cache=False, think_mode="none", prices=(0.02, 0.891, 0.005, 0.02),
                                   list_price=True, stream_guard=True, min_cap=40000),
    # 2026-10-14 depth probe (docs/retro_gap_rows.md): Opus 5.5 at list price
    # ($4 / $20, cached input $0.20, cache write $5), configured like sonnet-5.5 (explicit cache markers, not streamed); and Sol on the main key.
    "opus-5.5": dict(base_url="https://openrouter.ai/api/v1", key="~/.config/vexorium/openrouter_api_key",
                     api_model="anthropic/claude-opus-5.5", cache=True, think_mode="details", prices=(4.00, 20.0, 0.20, 5.00),
                     list_price=True),
    # b65 (1) + (3): routed at the list price (max_price_pin) and metered at the BILLED cost OpenRouter reports per call (meter_billed:
    # usage.cost, 0.99 x list), never below the call at its list table (list_prices; 2026-10-27), the table only when no cost is
    # reported; its $2.50 input (the cache-write price) still prices every gate
    "gpt-6.1-sol-main": dict(base_url="https://openrouter.ai/api/v1", key="~/.config/vexorium/openrouter_api_key",
                             api_model="openai/gpt-6.1-sol", cache=False, think_mode="details", prices=(2.50, 10.0, 0.10, 2.50),
                             list_price=True, stream_guard=True, meter_billed=True, list_prices=SOL_LIST_PRICES,
                             extra_body=max_price_pin(*SOL_LIST)),
    # b65 steps (T3-T5, probe/b65/steps_tests.md; 2026-10-27): GPT-6.1 Terra on OpenRouter (released 2026-10-26, tools + reasoning) at
    # list $1 / $5 per 1M, cached $0.05, on the main key, configured as gpt-6.1-sol-main. The table mirrors Sol's: input 1.25x the catalog
    # (Sol's billed cache writes run 1.25x its prompt price; assumed the same for Terra), so the meter and every cap gate price a Terra turn
    # at or above its list price. No cap_prices: its table is its cap price.
    # b65-final (merge of b65-cap + b65-steps): the same mechanisms as Sol-main at Terra's list (TERRA_LIST_PRICES): pinned at list, metered
    # at max(billed, list table); the conservative table above stays the gate's prices.
    "gpt-6.1-terra-main": dict(base_url="https://openrouter.ai/api/v1", key="~/.config/vexorium/openrouter_api_key",
                               api_model="openai/gpt-6.1-terra", cache=False, think_mode="details", prices=(1.25, 5.0, 0.05, 1.25),
                               list_price=True, stream_guard=True, meter_billed=True, list_prices=TERRA_LIST_PRICES,
                               extra_body=max_price_pin(*TERRA_LIST)),
    # 2026-10-14: OpenRouter google/gemini-4-argon at the
    # INTRODUCTORY list price $2 / $10 per 1M (cached input $0.10; implicit caching measured: 10,460 of 12,551 input tokens cached on turn 2).
    # Google announced a later price of $4 / $20 (end date unconfirmed): a final pipeline must budget it at that price.
    # b64 L0 (docs/plateau_levers.md section 2): every CAP GATE prices it at ARGON_ANNOUNCED (cap_prices); spend is still metered (reported)
    # at the list table above, so the $3 audit and the run summaries keep the billed / list numbers.
    "gemini-4-argon": dict(base_url="https://openrouter.ai/api/v1", key="~/.config/vexorium/openrouter_api_key",   # 2026-10-14: the main key
                           api_model="google/gemini-4-argon", cache=False, think_mode="details", prices=(2.00, 10.0, 0.10, 2.00),
                           list_price=True, stream_guard=True, cap_prices=ARGON_ANNOUNCED,
                           extra_body=max_price_pin(*ARGON_LIST)),   # b65 (1): routed at the list price; metered and gated as before (L0)
    # 2026-10-14 (docs/kimi_k3_plan.md): Moonshot Kimi K3 on OpenRouter,
    # pinned to the cheapest tools-capable providers (FP4; no fallback outside the list, every request parameter supported). Spend is the
    # provider-reported (billed) cost; the cap gate prices the worst case at the highest price in the list ($0.84 in, $15 out, $0.30 cached).
    # Reasoning (reasoning.text) is replayed, as Moonshot recommends for interleaved thinking with tools.
    "kimi-k3-or": dict(base_url="https://openrouter.ai/api/v1", key="~/.config/vexorium/openrouter_api_key",
                       api_model="moonshotai/kimi-k3", cache=False, think_mode="details", prices=(0.84, 15.0, 0.30, 0.84),
                       stream_guard=True,
                       extra_body={"provider": {"order": ["inference-net/fp4", "relace/fp4", "wafer", "sail-research/fp4"],
                                                "allow_fallbacks": False, "require_parameters": True}}),
    # 2026-10-14 (Kimi K3 as it solved IMO 2026: effort max, no small output cap, cut reasoning continued; the Moonshot
    # endpoint only if there is no other choice): third-party FP4 hosts, Sail first (lowest output price; right at both efforts in the
    # 2026-10-14 effort test). Adaptive output cap up to 64k per turn (what the remaining budget can pay for), one continuation of a turn
    # cut while reasoning. Run with --reasoning-effort max.
    "kimi-k3-max": dict(base_url="https://openrouter.ai/api/v1", key="~/.config/vexorium/openrouter_api_key",
                        api_model="moonshotai/kimi-k3", cache=False, think_mode="details", prices=(0.84, 15.0, 0.30, 0.84),
                        stream_guard=True, adaptive_cap=64000, adaptive_min=6000, continue_on_length=True,
                        extra_body={"provider": {"order": ["sail-research/fp4", "relace/fp4", "wafer", "inference-net/fp4"],
                                                 "allow_fallbacks": False, "require_parameters": True}}),
    "deepseek-v4.1-flash": dict(base_url="https://api.cline.bot/api/v1", key="~/.config/vexorium/cline_api_key",
                                api_model="cline-pass/deepseek-v4.1-flash", cache=False, think_mode="none", prices=(0.30, 1.20, 0.006, 0.30),
                                stream=True, min_cap=40000, list_price=True),   # reasons ~35k tokens before its first action (2026-10-10 probe)
}


# 2026-10-14 (Azure AI for development, OpenRouter for reproduction):
# Azure presets built from ~/.config/vexorium/azure_ai.json = {"endpoint": "https://<resource>.openai.azure.com", "deployments":
# {"sol": "<deployment>", "deepseek-flash": "<deployment>", "opus": "<deployment>"}} (not a secret, kept out of the repo) and the key in
# ~/.config/vexorium/azure_ai_api_key (mode 600). Requests go to the Azure OpenAI v1 API (llm/openai_compat.py
# detects *.azure.com: api-key header, max_completion_tokens, reasoning_effort). Prices are the OPENROUTER list prices of the same models,
# so dev runs meter exactly like the final ($3 per problem at OpenRouter list); Azure reports no cost, so the table is used (list_price).
# Azure chat completions return no replayable reasoning for OpenAI models; 2026-10-20: Sol on Azure uses the Responses API instead (think_mode
# "responses": Chat Completions has no function calling for GPT-6.1 Sol at any effort, and "none" is not an effort Sol accepts), which replays
# its encrypted reasoning like OpenRouter.
AZURE_CONFIG = Path("~/.config/vexorium/azure_ai.json").expanduser()
AZURE_TEMPLATES = {
    "sol": dict(cache=False, think_mode="responses", prices=(2.50, 10.0, 0.10, 2.50), list_price=True, stream_guard=True),
    # b68 review (2026-10-28: Terra on Azure for the dev probe, deployment gpt-6.1-terra, Responses API with tool calls): metered at
    # gpt-6.1-terra-main's gate table (TERRA_LIST_PRICES' cache write, input at 1.25x the catalog), as the "sol" entry mirrors Sol's
    "terra": dict(cache=False, think_mode="responses", prices=(1.25, 5.0, 0.05, 1.25), list_price=True, stream_guard=True),
    # min_cap 24k (not 40k as on OpenRouter): Azure counts the requested output cap against the deployment's tokens-per-minute quota
    # (500k on this deployment, 2026-10-15); DeepSeek reasons about 11k tokens per turn on the gap rows
    "deepseek-flash": dict(cache=False, think_mode="none", prices=(0.02, 0.891, 0.005, 0.02), list_price=True, stream_guard=True,
                           min_cap=24000, no_effort=True),
    "opus": dict(cache=True, think_mode="details", prices=(4.00, 20.0, 0.20, 5.00), list_price=True),
    # 2026-10-15: Kimi K3 deployed on our Azure resource as FW-Kimi-K3 (its own resource and key); reasoning arrives as reasoning_content and is
    # not replayed; metered at the kimi-k3-max (OpenRouter third-party host) prices
    "kimi": dict(cache=False, think_mode="none", prices=(0.84, 15.0, 0.30, 0.84), list_price=True, stream_guard=True),
    # 2026-10-15: GLM-5.3 deployed on our Azure resource as FW-GLM-5.3 (same resource and key as FW-Kimi-K3); reasoning not replayed; metered at
    # the OpenRouter z-ai/glm-5.3 output list price ($4.80/M) with a conservative $0.60/M input (the listed $0.039 is one host's floor)
    "glm": dict(cache=False, think_mode="none", prices=(0.60, 4.80, 0.11, 0.60), list_price=True, stream_guard=True),
    # 2026-10-15: DeepSeek V4 Pro deployed on our Azure resource (the Kimi key). Unlike Flash it does NOT reason unless
    # reasoning_effort is sent (measured: no effort 0 reasoning chars; low 3.1k; high 4.6k on a counting question), so the effort is
    # passed; ~150 tok/s; metered at the OpenRouter deepseek/deepseek-v4-pro list price ($0.9553 in / $1.9105 out / $0.0796 cached)
    "deepseek-pro": dict(cache=False, think_mode="none", prices=(0.9553, 1.9105, 0.0796, 0.9553), list_price=True, stream_guard=True,
                         min_cap=24000),
}

# 2026-10-15: Gemini 4 Argon (and Claude Opus 5.5) on Vertex AI; the GCP project comes from LRA_GCP_PROJECT. Development only, until Sol
# was available on Azure: Vertex AI's OpenAI-compatible endpoint (global location; us-central1
# has no Argon) through harness/vertex_proxy.py on the docker bridge: the proxy holds the OAuth token on the host (no Google token enters
# an agent container; the org policy forbids a narrower service account) and forwards only chat completions of allow-listed models. The
# key file is a non-secret placeholder (the proxy replaces the header). Tool calls carry Gemini thought signatures (extra_content), passed
# back by llm/openai_compat; reasoning is billed as output but reported outside completion_tokens (openai_compat.output_tokens adds it).
# Metered at the OpenRouter list price of the gemini-4-argon preset.
VERTEX_PROXY = "http://172.17.0.1:18190/v1/projects/" + os.environ.get("LRA_GCP_PROJECT", "your-gcp-project") + "/locations/global/endpoints/openapi"
MODEL_PRESETS["gemini-4-argon-vertex"] = dict(base_url=VERTEX_PROXY, key="~/.config/vexorium/vertex/proxy_key", api_model="google/gemini-4-argon",
                                              cache=False, think_mode="none", prices=(2.00, 10.0, 0.10, 2.00), list_price=True, stream_guard=True,
                                              cap_prices=ARGON_ANNOUNCED)   # b64 L0: gated at the announced price, as the OpenRouter preset
# 2026-10-15 (Opus on Vertex as the review loop's reviewer): Claude Opus 5.5 through the same proxy (Anthropic rawPredict),
# called by harness/architect.call via llm/anthropic_vertex (official SDK, AnthropicVertex). Reviewer only: agent sessions are not wired.
MODEL_PRESETS["opus-5.5-vertex"] = dict(base_url="http://172.17.0.1:18190/v1", key="~/.config/vexorium/vertex/proxy_key", api_model="claude-opus-5-5",
                                        cache=False, think_mode="none", prices=(4.00, 20.0, 0.20, 5.00), list_price=True, anthropic_vertex="global")


def _azure_presets() -> dict:
    try:
        c = json.loads(AZURE_CONFIG.read_text())
    except Exception:  # noqa: BLE001  (no config: no Azure presets)
        return {}
    def _base(ep: str) -> str:
        ep = ep.rstrip("/")
        return ep if ep.endswith("/openai/v1") else ep + "/openai/v1"
    out = {}
    for alias, dep in (c.get("deployments") or {}).items():
        if alias not in AZURE_TEMPLATES or not dep:
            continue
        # a deployment is a name (the shared endpoint and key) or {"name", "endpoint", "key"} (its own resource, 2026-10-15)
        d = dep if isinstance(dep, dict) else {"name": dep}
        out[f"{alias}-azure"] = dict(AZURE_TEMPLATES[alias], base_url=_base(d.get("endpoint") or c["endpoint"]),
                                     key=d.get("key") or "~/.config/vexorium/azure_ai_api_key", api_model=d["name"])
    return out


MODEL_PRESETS.update(_azure_presets())

CAP_PRICE_MODES = ("announced", "list")


def cap_prices(preset, mode: str = "announced") -> tuple | None:
    """b64 L0: the price table every CAP GATE budgets a preset's calls at (agent.py --budget-usd, the review and REPAIR calls through
    harness/review.PricedCaller, the router's startup check, hx_heldout's reclaim session floor). mode "announced" (the default): the preset's
    `cap_prices` (a price the provider has announced, e.g. ARGON_ANNOUNCED), else its `prices`; mode "list": `prices` (the pre-L0 gates).
    The spend meter (what is reported and audited) always uses `prices`, never this. `preset` is a MODEL_PRESETS name or entry."""
    if mode not in CAP_PRICE_MODES:
        raise ValueError(f"cap price mode {mode!r}: one of {CAP_PRICE_MODES}")
    p = (MODEL_PRESETS.get(preset) if isinstance(preset, str) else preset) or {}
    return tuple(p["cap_prices"]) if mode == "announced" and p.get("cap_prices") else p.get("prices")


def cap_metered_usd(preset: str, u) -> float | None:
    """b64-it3 (L0 x L1): one call at the preset's CAP prices as run_problem's gate counts a turn (`_cc`): its table at cap_prices, never
    below a reported cost. None for a preset whose cap prices are its table (the gate then counts the metered cost, metered_usd)."""
    p = MODEL_PRESETS.get(preset) or {}
    ct = cap_prices(preset)
    if not p or ct is None or tuple(ct) == tuple(p["prices"]):
        return None
    tc = table_cost(u, ct)
    cost = getattr(u, "cost", None)
    return max(tc, float(cost)) if cost is not None else tc


def table_cost(usage, prices: tuple) -> float:
    """One call's cost at a price table: uncached input, output, cache read and cache write tokens (agent.py's meter formula)."""
    pi, po, pr, pw = prices
    cr, cw = int(getattr(usage, "cache_read", 0) or 0), int(getattr(usage, "cache_write", 0) or 0)
    return (max(0, usage.input_tokens - cr - cw) * pi + usage.output_tokens * po + cr * pr + cw * pw) / 1e6


def _check_cap_prices() -> None:   # a cap gate is never below the metered table (else the gate could under-count the reported spend)
    for k, p in MODEL_PRESETS.items():
        if p.get("cap_prices") is not None:
            assert len(p["cap_prices"]) == 4 and all(c >= l for c, l in zip(p["cap_prices"], p["prices"])), k


_check_cap_prices()


def max_price_of(preset) -> dict | None:
    """b65 (1): a preset's OpenRouter max_price pin ({"prompt", "completion"}, $ per 1M) or None. `preset` is a MODEL_PRESETS name or entry."""
    p = (MODEL_PRESETS.get(preset) if isinstance(preset, str) else preset) or {}
    return ((p.get("extra_body") or {}).get("provider") or {}).get("max_price")


def _check_max_price() -> None:   # b65 (1): a pinned endpoint never bills a prompt or completion token above the gate's prices
    # b65-final (audit C3): compared with the CAP prices (cap_prices; = prices for a preset without them), so Argon can be pinned at its
    # announced $4 / $20 (ARGON_ANNOUNCED) without moving its list table; a call without a reported cost is then metered at the cap prices
    # (meter_table), a reported one at max(table, billed) as before, so the meter never reads below the bill
    for k, p in MODEL_PRESETS.items():
        mp = max_price_of(p)
        if mp:
            ci, co, _cr, cw = cap_prices(p)
            assert mp["prompt"] <= min(ci, cw) and mp["completion"] <= co, k   # cap_prices >= prices (_check_cap_prices)


def meter_table(preset: dict) -> tuple:
    """b65-final: the table a call WITHOUT a reported cost is metered at: the preset's prices, or its cap prices when its max_price pin is
    above them (an endpoint there may bill above the list table; _check_max_price keeps every pin within the cap prices)."""
    pr = preset["prices"]; mp = max_price_of(preset)
    if mp and preset.get("cap_prices") and (mp["prompt"] > min(pr[0], pr[3]) or mp["completion"] > pr[1]):
        return tuple(preset["cap_prices"])
    return tuple(pr)


_check_max_price()


def _check_list_prices() -> None:   # b65 (2026-10-27): a meter_billed preset has a list table; the gate's table bounds it per class
    for k, p in MODEL_PRESETS.items():
        if p.get("meter_billed"):
            lp = p.get("list_prices")
            assert lp and len(lp) == 4 and all(l <= c for l, c in zip(lp, p["prices"])) and lp[2] <= max(lp[0], lp[3]), k
            mp = max_price_of(p)
            assert not mp or (mp["prompt"] <= lp[0] and mp["completion"] <= lp[1]), k   # the pin admits no endpoint above list


_check_list_prices()


# b65 pin error (2026-10-27; live check: a pin below every endpoint answers HTTP 404 "No endpoints found that satisfy the max price for this
# request"; the provider-routing docs name a 503 "No allowed providers"): it arrives before any stream data (never billed: $0, maybe_billed
# False). b65-final (audit C3, decided 2026-10-27 under the no-harm rule; was b65-cap's fatal stop on first sight, which turned one
# transient error into a run-wide stop with no output): NOT fatal on first sight. harness/pinwatch.py confirms it (the same pin error on 2 rows
# within 10 min, or 3 tries on one row over >= 10 min, 5 min apart, each $0); this process's sessions share PINS. agent.py retries a pin
# error after PIN_BACKOFF_S without using up a transport attempt, writes every one to <run dir>/pin_events.jsonl (hx_heldout confirms
# across the async ladder's processes from those files), and on a CONFIRMED pin (its own, or a fresh PIN_MARKER hx_heldout wrote into its
# run dir) ends the session at $0 and exits PIN_FATAL_RC; hx_heldout then starts no new paid session and the router finishes the run on the
# $0 path (finals.json and the submission file complete). review.PricedCaller: a confirmed pin skips that row's review at $0.
from harness import pinwatch as PW  # noqa: E402
PIN_FATAL_RC = PW.PIN_FATAL_RC   # sysexits EX_CONFIG
PIN_MARKER = PW.PIN_MARKER
PINS = PW.PinWatch()   # this process's pin errors and confirmations (sessions' threads; the router's review calls)


def pin_unservable(e: BaseException, preset: str | None) -> str | None:
    """b65: the description when `e` is OpenRouter's no-endpoint-under-the-pin answer for a pinned preset, sent before any data ($0), else
    None. b65-final: a pin ERROR, not yet a confirmed pin (PINS.observe decides; harness/pinwatch.py)."""
    mp = max_price_of(preset) if preset else None
    st = getattr(e, "status_code", None)
    txt = f"{getattr(e, 'body', '') or ''} {e}".lower()
    if not mp or not ((st == 404 and "no endpoints found" in txt and "max price" in txt) or (st == 503 and "no allowed providers" in txt)):
        return None
    if maybe_billed(e):   # review 2026-10-27: the pin path charges $0 and skips the failed-attempt charge, so it takes only an answer
        return None       # never billed (a status before any data); a stream that had started keeps the old path (charged, retried)
    return (f"OpenRouter serves no endpoint of preset {preset} ({MODEL_PRESETS[preset]['api_model']}) under its max_price pin "
            f"${mp['prompt']:g} prompt / ${mp['completion']:g} completion per 1M (HTTP {st}: {' '.join(str(getattr(e, 'body', '') or e).split())[:200]}); "
            "$0 (refused before any data). Once CONFIRMED (harness/pinwatch.py) no new paid session starts and the run ends on its $0 path; "
            "to fix it check the endpoint listing, move the pin (agent.max_price_pin) only to a price the cap gate covers (cap_prices; "
            "_check_max_price), then restart")


def pin_fatal_line(preset: str, msg: str) -> str:
    """b65-final: the loud line of a CONFIRMED pin (agent.py, hx_heldout and the router print it)."""
    return f"FATAL (max_price pin of {preset}): {msg}"


def write_pin_marker(out_dir: Path, preset: str, msg: str, why: str | None = None, rows=None) -> None:
    """b65: PIN_MARKER (a CONFIRMED pin) in the run's directory (probe/runs/<run id>/, writable from the ladder's containers): what
    hx_heldout stops on and what this run dir's other sessions end on (pinwatch.marker_fresh; it expires after PIN_WINDOW_S)."""
    PW.write_marker(out_dir, preset, msg, pin=max_price_of(preset), why=why, rows=rows)


ARTIFACT_MAX_TURNS = 16     # b63 item 16 (--artifact): plan §1.1 P, <= 12-16 turns
ARTIFACT_OVERLAP = 0.5      # share of the artifact's non-hole body lines a compiling candidate must hold to count as derived from it
RECLAIM_FLOOR = 2000   # --reclaim-floor default: the smallest output cap a budget-reclaim turn is shrunk to (below it the session ends)


def fit_output_cap(budget: float, spend: float, fixed_usd: float, out_price: float, cap: int, floor: int,
                   min_reserve: float = 0.0) -> tuple[int | None, float | None]:
    """2026-10-22 (lever 5, budget reclaim; also the review's pre-call gate): the largest output cap n <= cap whose worst case fits,
    spend + max(fixed_usd + n x out_price / 1e6, min_reserve) <= budget, checked in floating point exactly as written (never assumed from
    the division); fixed_usd is the part of the call billed whatever it outputs (its whole input uncached at list price). Returns (n, that
    reserve), or (None, None) when the largest fitting n is below min(floor, cap). A provider cannot bill more output than max_tokens, so a
    call sent with max_tokens = n spends at most the reserve: spend + reserve <= budget holds by construction."""
    cap, floor = int(cap), int(floor)
    if not spend + min_reserve <= budget or not spend + fixed_usd <= budget:   # (also False for a NaN)
        return None, None
    n = cap if out_price <= 0 else min(cap, int((budget - spend - fixed_usd) * 1e6 / out_price))
    for _ in range(8):   # the division may round up by an ulp: step down until the bound holds as the gate computes it
        if n < 0:
            break
        r = max(fixed_usd + n * out_price / 1e6, min_reserve)
        if spend + r <= budget:
            return (n, r) if n >= max(1, min(floor, cap)) else (None, None)
        n -= 1
    return None, None


def preset_gate(spend: float, budget: float, ctx_tokens: int, prices: tuple, cap_full: int, turn_max: float, reclaim: bool = False,
                floor: int = RECLAIM_FLOOR) -> tuple[float, int | None]:
    """The per-turn hard cap gate of a fixed-cap preset session, as one pure function (run_problem's gate; harness/test_budget_cap.py).
    The reserve is the WORST CASE of the next turn: its whole context billed uncached plus its full output cap at the list prices, never less
    than 1.25x this session's costliest turn (the old rule, byte for byte). The session ends when spend + reserve > budget, except with
    reclaim (--budget-reclaim): then the next turn's output cap is shrunk to what the budget can still pay for in the same worst case
    (fit_output_cap, the 1.25x rule kept as a lower bound) and the session ends only below `floor` tokens. Returns (reserve, shrunk cap or
    None); the caller ends the session when spend + reserve > budget."""
    pi, po, _pr, pw = prices
    reserve = max((ctx_tokens * max(pi, pw) + cap_full * po) / 1e6, 1.25 * turn_max)
    if reclaim and spend + reserve > budget:
        n, r = fit_output_cap(budget, spend, ctx_tokens * max(pi, pw) / 1e6, po, cap_full, floor, 1.25 * turn_max)
        if n is not None:
            return r, n
    return reserve, None


def maybe_billed(e: BaseException) -> bool:
    """A failed API attempt the provider may still have billed: a transport error (read timeout, a stream that broke after the request was
    accepted) or a 5xx. A 4xx (a 429 rate limit included) is rejected before any generation and is not billed. b64 F3 (docs/first_half_gap.md
    §3j): neither is an error the server returned before any stream data (llm/openai_compat OpenAIChatError.before_data: an HTTP error status
    on a streamed request, or an SSE error chunk ahead of every data chunk) unless it names a generation (failed_attempt_charge looks that up):
    in it2a, 22 OpenRouter 502s "Our servers are currently overloaded" were charged $6.29 of worst-case spend and ended 8 sessions."""
    st = getattr(e, "status_code", None)
    if getattr(e, "not_sent", False) or _connect_failure(e):   # b66 (A4): never reached the server (DNS, refused, connect timeout, TLS handshake)
        return False
    return (not getattr(e, "rate_limit_exhausted", False) and not (isinstance(st, int) and 400 <= st < 500)
            and not (getattr(e, "before_data", False) and not getattr(e, "gen_id", None)))


def _connect_failure(e: BaseException) -> bool:
    """b66 (A4): llm/openai_compat.connect_failure (imported lazily: agent.py's other endpoints do not load the module)."""
    try:
        from llm.openai_compat import connect_failure
    except ImportError:
        return False
    try:
        return connect_failure(e)
    except Exception:  # noqa: BLE001  (a classifier failure keeps the conservative answer: possibly billed)
        return False


def failed_attempt_charge(e: BaseException, worst_usd: float, lookup=None, meter=None) -> tuple[float, dict]:
    """b64 F3: what a failed attempt maybe_billed() lets through is charged against the budget, and why (a trajectory record). A stream that
    had started carries its generation id (OpenAIChatError.gen_id, or e.gen_id on a transport error raised mid-stream): lookup(gen_id) -> its
    Usage or None (OpenRouter GET /generation, as the junk-cut path) and meter(usage) -> USD replace the worst case. Without a record: 0 for
    an error returned before any stream data, else worst_usd (data had streamed or nothing is known: the cap stays safe)."""
    gid = getattr(e, "gen_id", None)
    info = {"gen_id": gid, "before_data": bool(getattr(e, "before_data", False)), "worst_usd": round(float(worst_usd), 6)}
    if gid and lookup is not None and meter is not None:
        try:
            u = lookup(gid)
            usd = float(meter(u)) if u is not None else None
        except Exception:  # noqa: BLE001  (a failed lookup or meter leaves the charge below)
            usd = None
        if usd is not None:
            return usd, dict(info, basis="generation")
    if info["before_data"]:
        return 0.0, dict(info, basis="before_data")
    return float(worst_usd), dict(info, basis="worst_case")


def attempt_meter_usd(preset: dict, u) -> float:
    """b64 F3: one call's metered USD, the per-turn meter's rule (metered_usd; b65: one rule for every meter)."""
    return metered_usd(preset, u)


TOKEN_RULES = ("\n\nTOKEN COUNTING (the scorer's lexer: every bracket, comma, paren and operator is a token; a dotted name like Foo.bar_baz is ONE token). "
           "Measured: `⟨a, b⟩` 5 vs `And.intro a b` 3; `exact ⟨_, h⟩` 6 vs `exact .intro _ h` 4; `obtain ⟨a, b⟩ := h` 8 vs using `h.1`/`h.2`; "
           "`refine ⟨?_, ?_⟩` 6 vs `constructor` 1; `fun x => h x` 5 vs `h` 1; `intro x; exact h x` 6 vs `exact h` 2; `by exact h` 3 vs `h` 1; "
           "`rw [h]; exact h2` 7 vs `rwa [h]` 4; `simp at h; exact h` 6 vs `simpa using h` 3; `apply foo; exact bar` 5 vs `exact foo bar` 3; "
           "`simp only [a, b] at h ⊢` 10 vs `simp_all [a, b]` 6; `f (g x)` vs `f $ g x` saves 1 (`<|` saves 0); `fun x => e` vs `λx => e` saves 1 (write `λx` with no space: Lean reads it as `λ x`, the lexer counts `λx` as one token; also `λ_ =>`, `λx y =>`); each lemma in a hint list costs ~2. "
           "The big wins are still whole blocks replaced by one closer (`grind [lemmas]`, `simp_all`, `omega`, `fun_prop`, `aesop`) — most of a block's tokens.")
SYSTEM += TOKEN_RULES
LEVER_REVIEW = ("\n\nLEVER REVIEW FIRST (what broke the closed lines' plateau: a review that names exact edits, then one batch of compiles). Before "
                "any rewrite: (1) read best.lean line by line against this checklist and write up to 6 LEVERS in notes.md, each an exact edit with "
                "its expected effect on tokens and heartbeats: a hypothesis the goal never uses (drop it before an induction, so the induction "
                "hypotheses stay simple); the same tactic run repeated across cases (`all_goals`/`any_goals`, `<;>`); `<;> first | A | B` "
                "(as `any_goals A` then `all_goals B`); hand-written side conditions (into the `simp only` list or a discharger); an expensive "
                "closer tried on goals a cheap one closes (`assumption` or `exact h` first); `show`/`change`/`unfold` lines that only restate the "
                "goal. (2) Test ALL levers in ONE lean_check_variants call, one lever per "
                "variant, each applied to the best. (3) Combine the winners in a second batch. Only when the levers are spent, go on with the plan above.")
SYSTEM += ("\n\nLENGTH IS OFTEN THE MISSING AXIS. After any new "
           "compiling skeleton, call lean_mine once: it finds which blocks a single automation call closes. Then rewrite the remaining long blocks.")

def _is_scout(r: dict) -> bool:
    """POC 2 scout runs (short, from the reference) are exploration, not resumed history: adaptive budgets, plateau and fresh-start
    logic must ignore them. Tagged mode=scout from cycle 27; earlier scouts recognised by run-id suffix -sA/-sB/-sC."""
    import re as _re
    return r.get("mode") == "scout" or bool(_re.search(r"-s[A-Z]$", r.get("run_id") or ""))

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--problems", nargs="*", default=None)
    ap.add_argument("--turns", type=int, default=40)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--model", default="glm-5.3-flash")
    ap.add_argument("--reasoning-effort", default="low")
    ap.add_argument("--no-bank-sync", dest="bank_sync", action="store_false", default=True, help="do not adopt a better same-model candidate from the bank at run start (main work root only; replication roots never sync)")
    ap.add_argument("--endpoint", choices=["zai", "openrouter", "openai"], default="zai", help="zai = z.ai Anthropic-compatible endpoint (dev probe); openrouter = OpenRouter Messages endpoint pinned to --quant providers; openai = any OpenAI-compatible /chat/completions server (self-hosted vLLM/SGLang)")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000/v1", help="--endpoint openai: server base URL (…/v1)")
    ap.add_argument("--api-key-file", default=None, help="--endpoint openai: file holding the bearer token (omit for a local vLLM without auth)")
    ap.add_argument("--api-model", default=None, help="--endpoint openai: model id as the server names it (default: --model)")
    ap.add_argument("--serving-tag", default=None, help="--endpoint openai: provenance tag, e.g. vllm-h100-w4a16 -> model glm-5.3-flash-vllm-h100-w4a16@openai")
    ap.add_argument("--length-tools", action="store_true", help="2026-10-07 length experiment: expose the lean_mine tool and the LENGTH brief (off by default so POC 2 stays comparable)")
    ap.add_argument("--from-reference", action="store_true", help="POC 2 scouts: start candidate.lean from the reference proof (stored best is kept unless beaten)")
    ap.add_argument("--term-card", action="store_true", help="2026-10-11: add the TERM-MODE FINISH / PROBE-BEFORE-COMMIT card (DeepSeek→Sol lesson); off until an A/B")
    ap.add_argument("--brief-dir", default=None, help="append <dir>/<problem>.md (a facts-only knowledge brief) to the opening message")
    ap.add_argument("--brief", choices=["none", "automation", "direct", "restructure"], default="none", help="POC 2 scout strategy brief appended to the opening message")
    ap.add_argument("--closed-lessons", action=argparse.BooleanOptionalAction, default=True, help="cycle 80, DEFAULT ON since cycle 89 (held-out "
                    "flagab-1010-1014: +2.76 paired, 7/10 better, new-file +4.19): the general habits mined from the Opus 5.5 / GPT Astra lines "
                    "(simp dischargers, write each piece once, fun_induction, reducible pre-pass, syntactic closers) in the first message; "
                    "--no-closed-lessons turns them off")
    ap.add_argument("--variant-scores", action="store_true", help="cycle 78: lean_check_variants rows show each compiling variant's provisional score "
                    "and vs_best (duplicates filled from their earlier result), so the 'not above the stored best' note can fire")
    ap.add_argument("--relative-error-lines", action="store_true", help="cycle 76: lean_check-family errors (incl. compat failures) give positions as "
                    "`line n `<text>`, col C` of the compiled declaration instead of the scratch file's line; costliest_lines in declaration lines")
    ap.add_argument("--simp-prune", action="store_true", help="cycle 58: on a would-be new best, one simp? compile drops unused lemmas from `only` lists "
                    "(kept when it compiles and scores higher). Off by default while the A100-80 run uses the tagged harness.")
    ap.add_argument("--upstream-history", dest="upstream_history", action=argparse.BooleanOptionalAction, default=False,
                    help="compliance switch (R2). OFF by default since 2026-10-21 (off for the smoke, the A/B and the final): without it "
                         "no upstream digest, no git-history hint in the prompt or the shell tool description, and git log/show blocked in the shell "
                         "tool; --upstream-history restores the old behaviour (--no-upstream-history still accepted)")
    ap.add_argument("--no-budget-forcing", dest="budget_forcing", action="store_false", default=True, help="self-hosted endpoint: do not rescue turns that hit the cap while thinking (budget forcing, on by default)")
    ap.add_argument("--strategy", choices=["none", "hardtail"], default="none", help="hardtail: goal map tool (lean_goals) + map/lemma-search/restructure protocol with a 70%% token target, for problems flat after many passes")
    ap.add_argument("--think-prompt", choices=["off", "structural", "all"], default="off",
                    help="prompt-based thinking budget (self-hosted servings ignore the effort label): append a THINK LONGER instruction to the "
                         "opening message and re-inject it every 6 turns — in structural/fresh-start runs ('structural') or every run ('all')")
    ap.add_argument("--max-api-retries", type=int, default=6, help="attempts per API call on transport errors, backoff 10 s doubling to 300 s (20 ≈ 1.5 h tolerance for a paused interruptible instance)")
    ap.add_argument("--rate-limit-budget", type=float, default=float(os.environ.get("LRA_RATE_LIMIT_BUDGET_S", "1800")), help="--endpoint openai: seconds of wall time one call may spend on HTTP 429 "
                    "rate-limit / capacity rejections (server retry-after honoured, else 15 s doubling to 120 s), separate from the transport "
                    "retries; then the session ends (default $LRA_RATE_LIMIT_BUDGET_S or 1800)")
    ap.add_argument("--extra-body-json", default=None, help="--endpoint openai: JSON merged into the request body (e.g. provider pins, chat_template_kwargs)")
    ap.add_argument("--quant", default="nvfp4", help="OpenRouter provider quantization to pin (nvfp4 | fp4 | fp8); only with --endpoint openrouter")
    ap.add_argument("--run-id", default=time.strftime("agent-%Y%m%d-%H%M%S"))
    ap.add_argument("--fresh", action="store_true", help="discard the per-problem persistent state and start from the reference")
    ap.add_argument("--work-root", default="harness/work", help="per-problem state root (use a separate root for model comparisons)")
    ap.add_argument("--adaptive-turns", action="store_true", default=True, help="20 turns if best>=80, 60 if best<45, else 40 (default on)")
    ap.add_argument("--no-adaptive-turns", dest="adaptive_turns", action="store_false")
    ap.add_argument("--normalize", action="store_true", help="2026-10-10: after each session, run the lexer normalizer (harness/normalize.py) on the "
                    "best and record a compile-verified improvement; off until the arena accepts the $/λ style warnings (an upload check)")
    ap.add_argument("--token-rules", action="store_true", help="cycle 83: add the TOKEN COUNTING lexer rules (`f $ x`, projections, "
                    "constructor vs ⟨?_, ?_⟩, ...) to the system prompt of runs without --length-tools, which already have them; off until a z.ai A/B")
    ap.add_argument("--model-preset", choices=list(MODEL_PRESETS), default=None, help="2026-10-10: run a hosted model through this harness "
                    "(OpenRouter: haiku-5.5, sonnet-5.5, gpt-6.1-sol; ClinePass: deepseek-v4.1-flash). Sets endpoint/base-url/key/api-model, "
                    "prompt caching, reasoning passback; records are closed-dev-only (never banked); --budget-usd caps spend per problem")
    ap.add_argument("--lean-io", action=argparse.BooleanOptionalAction, default=None, help="2026-10-11 (docs/lean_io_proposal.md, simpler "
                    "version): no duplicate reference proof in the opening; shell/lean_run/read_file results capped at 1,500 chars. "
                    "Default off: the 2026-10-11 A/B rejected it (cost 113%%, score -3.29)")   # %% (2026-10-13): a bare % broke --help
    ap.add_argument("--budget-usd", type=float, default=3.00, help="with --model-preset: per-problem spend cap, a hard bound (b65, "
                    "2026-10-26: the whole $3.00, made safe by the gate's worst-case reserve, not by a margin; was $2.85)")
    ap.add_argument("--budget-reclaim", action="store_true", help="2026-10-22 (lever 5): with --model-preset (fixed output cap), when the "
                    "next turn's worst case at the full cap no longer fits the budget, shrink its output cap to what the budget can pay for "
                    "in the same worst case (context uncached at list price + the shrunk cap) instead of ending the session; it ends only "
                    "below --reclaim-floor tokens. A failed attempt that may have been billed is charged its worst case before the retry. "
                    "spend + worst case <= budget still holds by construction. Off by default")
    ap.add_argument("--reclaim-floor", type=int, default=RECLAIM_FLOOR, help="--budget-reclaim: the smallest output cap a turn is shrunk "
                    "to (tokens)")
    ap.add_argument("--budget-milestones", default="2.0", help="with --model-preset: comma-separated spend levels whose crossing is recorded per problem (state.json budget_milestones, trajectory event, warning line)")
    ap.add_argument("--lever-review", action="store_true", help="cycle 88: on a problem whose last two runs gained < 3, open with a LEVER REVIEW "
                    "(a checklist of general edits -> up to 6 levers -> one lean_check_variants batch -> combine); off until a z.ai A/B")
    ap.add_argument("--auto-brief", default=None, metavar="DIR", help="2026-10-14 (harness/autobrief.py; docs/auto_brief_plan.md): DIR/<ws>.json "
                    "measured on this row's seed in this run (CPU only): its brief goes into the opening and its start candidate is checked "
                    "and adopted when better than the workspace best; off by default")
    ap.add_argument("--auto-brief-wait", type=float, default=None, metavar="SECONDS", help="2026-10-22 (hx_heldout --auto-brief-pipeline; "
                    "harness/brief_gate.py): with --auto-brief, the brief is still being made in the background: a row's session starts only "
                    "when DIR/<ws>.json exists, or the brief process has ended (DIR/.brief_ended), or SECONDS after this batch started; rows "
                    "whose brief is ready first, in --problems order, at most --workers at once; off by default")
    ap.add_argument("--pattern-cards", action="store_true", help="2026-10-13 (harness/pattern_cards.py): general, pattern-keyed knowledge distilled from the theorem-keyed briefs (no problem names, no problem-local identifiers), selected by the shape of the statement and proof; off by default")
    ap.add_argument("--compact-tool-json", action="store_true", help="b65: tool results as compact JSON with unicode kept (fewer input tokens); off = byte-identical to before")
    ap.add_argument("--notes-view", choices=["head", "tail", "headtail"], default="head", help="b64 F2 (docs/first_half_gap.md §3i): which "
                    "part of a notes.md longer than 3,000 characters the opening shows: head (the default, as before: its first 3,000), tail (the "
                    "newest entries, under a marker for the omitted older part) or headtail (the first ~1,000 and the newest)")
    ap.add_argument("--leads-count", action="store_true", help="b64 F1 (docs/first_half_gap.md §3d): the library-lead probes on a count "
                    "budget (harness/lemma_search.search count=True: every planned probe compiled, each at the heartbeat limit, with "
                    "lemma_search.COUNT_COMPILE_S / COUNT_BACKSTOP_S as wall backstops for runaways only) instead of the 120 s wall budget of "
                    "the opening's LIBRARY LEADS (and the 150 s of a lean_search call with probes), so the leads do not depend on the host's "
                    "speed. Off by default")
    ap.add_argument("--heartbeat-first", action="store_true", help="2026-10-13: the HEARTBEAT_FIRST card with the "
                    "technique cards and heartbeat-aware cards / scout / structural / heartbeat briefs / closed lessons / lever review on problems "
                    "whose stored best has H points left >= L points left (always before a measured best); the system prompt's AUTOMATION FIRST "
                    "closers, LENGTH paragraph and lean_mine description become axis-conditional for the whole run (harness/cards.py HB_REWRITES), "
                    "so the A/B unit is the flag, not the gate; off until an A/B")
    ap.add_argument("--failed-moves", action="store_true", help="2026-10-13 (docs/opus_pass2_deep_dive.md §3: repeats of an already-seen error "
                    "rose to 56%% of failing checks by pass 5): every failed check records its edit against the closer of best / reference as a "
                    "move (state.json attempts[].move), and the opening message lists the REFUTED MOVES (harness/cc_levers.failed_moves_block: "
                    ">= 2 real compile refutations from separate tool calls, reopened when the best changes in the lines they touch); off until an A/B")
    ap.add_argument("--mode", choices=["default", "golf"], default="default", help="B62c (harness/golf.py, docs/scaffold_panel.md): golf = start from "
                    "the stored best measured in this session, the golf prompt and tools (lean_batch, hb_profile, pool), paired exact acceptance "
                    "(scorer/accept.py) and the harness stop rule; the knowledge sections of the default opening are not used. Off by default")
    ap.add_argument("--golf-min-evals", type=int, default=90, help="golf stop rule: finish is refused before this many evaluations")
    ap.add_argument("--golf-flat-evals", type=int, default=40, help="golf stop rule: ... and before this many evaluations without a banked gain")
    ap.add_argument("--golf-jobs", type=int, default=3, help="golf: concurrent compiles in one lean_batch (memgate still gates each)")
    ap.add_argument("--golf-batch-max", type=int, default=12, help="golf: items per lean_batch call")
    ap.add_argument("--pool", action="store_true", help="B62a: append every compiling candidate (full text, exact provisional score) to "
                    "<work root>/<problem>/pool.jsonl for the end stage; golf turns it on")
    ap.add_argument("--name-neighbors", action="store_true", help="L1 (2026-10-22; harness/name_neighbors.py): an `unknown identifier` / "
                    "`unknown constant` error in a lean_check / lean_run / lean_check_variants result gets up to 8 real constants near the name "
                    "from the row's own environment (listed by Lean at run time, one-line signatures, cached under <work root>/.name_neighbors), "
                    "and the opening lists the names earlier sessions found missing (<workspace>/missing_names.json); off until a held-out A/B")
    ap.add_argument("--name-neighbors-queries", type=int, default=10, help="--name-neighbors: Lean processes per session (each about one "
                    "compile; the disk cache answers repeats without one)")
    ap.add_argument("--artifact", default=None, metavar="PATH", help="b63 item 16 (docs/adaptive_plan_93.md §1.1 P, §1.4 ARTIFACT-SESSION; "
                    "harness/artifacts.py): PATH is a JSON artifact record, a JSON {problem: record} map, or a directory of <ws>.artifact.json "
                    "files (hx_heldout passes a directory). candidate.lean starts as the artifact (a compiled skeleton with sorry holes, a "
                    "transpiled proof, a fold skeleton ...; best.lean keeps the row's best), the opening carries the SHOWN block (the artifact's "
                    "diff against the best with tokens / heartbeats / score and the holes' goals), the turn budget is capped at 16, and finish "
                    "is refused while the shown skeleton has open holes and a third of the budget remains. Off by default; v3 ladders unaffected")
    ap.add_argument("--skeleton-path-first", action="store_true", help="b64 L1 (a) (docs/plateau_levers.md L1): lean_skeleton's input schema "
                    "lists `path` first and `content` last (both still optional). Sol's junk sits exactly where `,\"path\"` follows the draft "
                    "(15.7%% of skeleton calls, 31%% of first calls, 0 of 11,227 calls to other tools in it1b/it2a/ck1); write_file (path "
                    "first) has none. Off by default")
    ap.add_argument("--skeleton-salvage", action="store_true", help="b64 L1 (b) (harness/skeleton_salvage.py): a lean_skeleton call the junk "
                    "guard drops is run on its draft when a usable one is present (the statement byte-identical, the filler after the draft cut, "
                    "a sorry hole, no junk left); nothing else from the call is used, and the call in the history becomes the salvaged draft. "
                    "Off by default")
    ap.add_argument("--skeleton-combinator-holes", action="store_true", help="b64 L1 (harness/goals.py _TACTIC_CTX_COMB): lean_skeleton "
                    "reads a `sorry` after a tactic combinator (all_goals, any_goals, try, repeat, iterate n, focus, first | ...) as a tactic "
                    "hole; the default wraps it as a term, which does not parse (the first error of 142 of 234 no-goal skeleton results in "
                    "it1b/it2a/ck1). Off by default")
    ap.add_argument("--junk-billing-reconcile", action="store_true", help="b64 L1 (c): with --model-preset on OpenRouter, a junk-cut turn "
                    "whose generation record was not available yet is still charged its worst case, and its generation id is kept "
                    "(state.json billing_pending); each later turn (and the session end) looks the record up again and replaces the worst case "
                    "by the metered billed usage in api_spend (trajectory event billing_reconcile). Off by default")
    args = ap.parse_args()
    global _TOOL_JSON_COMPACT
    _TOOL_JSON_COMPACT = bool(getattr(args, "compact_tool_json", False))
    if args.skeleton_path_first:
        skeleton_path_first(TOOLS)
    if args.lean_io is None:   # A/B 2026-10-11 (probe/hx-leanio-ab.log): lean-io + effort low cost 113% of base at -3.29 score -> off by default
        args.lean_io = False
    if args.model_preset:   # hosted closed/open models through this harness (2026-10-10)
        _pr = MODEL_PRESETS[args.model_preset]
        if _pr.get("anthropic_vertex"):
            raise SystemExit(f"{args.model_preset} is a reviewer preset (harness/architect.call); agent sessions on it are not wired")
        args.endpoint, args.base_url, args.api_model = "openai", _pr["base_url"], _pr["api_model"]
        args.api_key_file = _pr["key"]
        if os.environ.get("LRA_SELFTEST_PRESET_URL"):   # harness/selftest.py budget_gate: the scripted fake server, no real key sent
            args.base_url, args.api_key_file = os.environ["LRA_SELFTEST_PRESET_URL"], None
        args.budget_forcing = False          # continue_final_message is a vLLM feature
        if args.model == "glm-5.3-flash":
            args.model = args.model_preset
        if args.work_root == "harness/work":
            raise SystemExit("--model-preset needs its own --work-root (never the Flash main line's harness/work)")
    if args.token_rules:
        globals()["SYSTEM_BASE"] = SYSTEM_BASE + TOKEN_RULES
    if args.heartbeat_first:   # 2026-10-13: one static system prompt per run, so its wording is axis-conditional (the per-problem gate is in run_problem)
        from harness import cards as _cards
        globals()["SYSTEM"] = _cards.heartbeat_aware(SYSTEM); globals()["SYSTEM_BASE"] = _cards.heartbeat_aware(SYSTEM_BASE)
        for _t in TOOLS:   # review 2026-10-13: lean_mine's "after every new compiling skeleton" (HB_REWRITES R11)
            _t["description"] = _cards.heartbeat_aware(_t["description"])
    if not args.upstream_history:   # review 2026-10-21: the compliance switch also drops the git hint from the shell tool description
        for _t in TOOLS:
            if _t["name"] == "shell":
                _t["description"] = _t["description"].replace(", `git log -p`/`git show` on the problem's file in the project clone to find how the "
                                                               "same proof was later simplified upstream", "")
    if args.mode == "golf":   # B62c: the golf session uses none of the default knowledge sections or strategies
        for _f in ("closed_lessons", "pattern_cards", "heartbeat_first", "term_card", "length_tools", "lever_review", "failed_moves", "from_reference",
                   "adaptive_turns", "normalize", "simp_prune", "variant_scores", "name_neighbors"):
            setattr(args, _f, False)
        args.auto_brief, args.brief, args.brief_dir, args.strategy, args.relative_error_lines, args.pool = None, "none", None, "none", True, True
        globals()["SYSTEM"] = globals()["SYSTEM_BASE"] = G.system_prompt(args.golf_batch_max, args.golf_min_evals, args.golf_flat_evals)
        _keep = ("read_file", "write_file", "lean_check", "lean_run", "lean_goals", "shell")
        TOOLS[:] = [t for t in TOOLS if t["name"] in _keep] + G.tools(args.golf_batch_max) + [
            {"name": "finish", "description": "End the session. Refused until the stop rule in the system prompt is met or the budget is nearly spent.",
             "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}}}]
    rows = {json.loads(l)["name"]: json.loads(l) for l in (ROOT / "data/benchmark_warmup.jsonl").open() if l.strip()}
    hbs = {json.loads(l)["name"]: json.loads(l)["heartbeat"] for l in (ROOT / "data/benchmark_heartbeats.jsonl").open() if l.strip()}
    out_dir = ROOT / "probe/runs" / args.run_id; out_dir.mkdir(parents=True, exist_ok=True)
    names = args.problems or list(rows)
    print(f"run {args.run_id}: {len(names)} problems, model={args.model}, turns≤{args.turns}", flush=True)
    if args.auto_brief and args.auto_brief_wait is not None:   # 2026-10-22 pipelined auto-brief: each row waits for its own brief (bounded)
        from harness.brief_gate import run_gated
        res = run_gated(names, args.workers, lambda n: run_problem(n, args, rows, hbs, out_dir), ROOT / args.auto_brief, args.auto_brief_wait)
    else:
        with ThreadPoolExecutor(args.workers) as ex:
            res = list(ex.map(lambda n: run_problem(n, args, rows, hbs, out_dir), names))
    (out_dir / "summary.json").write_text(json.dumps(res, indent=1))
    print("done", flush=True)
    if PINS.skipped:   # b65-final: a session ended on a CONFIRMED pin (its own, or hx_heldout's marker): loud; hx_heldout and the router stop paid work
        for _pr in PINS.skipped:
            _msg = pin_fatal_line(_pr, PINS.dead(_pr) or PW.marker_fresh(out_dir, preset=_pr) or (PINS.confirmed.get(_pr) or {}).get("message") or "confirmed")
            print(_msg, flush=True); print(_msg, file=sys.stderr, flush=True)
        raise SystemExit(PIN_FATAL_RC)


if __name__ == "__main__":
    main()
