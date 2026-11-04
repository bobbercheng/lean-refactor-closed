"""Driver v2 behaviour of the Claude Code tool scripts (docs/cc_driver_v2.md §4). Active only when LRA_CHECK_V2=1, which only
`harness/agent_claude_code.py --prompt v2` sets: without it every tool script runs its unchanged v1 code (v1 and Codex output byte-identical).

The 2026-10-12 warm-up review: tools beyond lean_check / lean_run / lean_check_variants were never used (not advertised; positional PROBLEM
arguments with primes and unicode in the name). In v2 every tool takes workspace FILES only and reads the problem from LRA_PROBLEM /
.lra_env.json; every state.json read-modify-write holds the workspace's fcntl lock (harness/statelock.py), so parallel Bash tool calls never
lose an attempt or a best. Behaviour beyond v1: lean_check_variants copies the winner (a new best) to candidate.lean; lean_mine banks
mined.lean through the normal lean_check path and copies it on a new best; heartbeat_profile defaults to candidate.lean; lemma_search_cli
runs no exact? probes unless --probes; tok_count counts proof-BODY tokens (what the scorer counts).
Round 2 (2026-10-12, docs/cc_driver_v2.md §9): every check goes through harness/inrun.locked_check, which also writes the winning edit into
state.json ledger.wins (in-run learning (a)) and adds `axis` (R1: L / H points left against the floor, the token<->heartbeat exchange rate) and
`progress` (R2: checks since the last new best, the stop rule) to the result; heartbeat_profile caches its result per proof sha in state.json
(profile_cache, hb_floor: later checks measure H against the floor); normalize_check runs the lexer normalizer and the heartbeat polish
(harness/normalize.py, harness/hb_polish.py), strictly-better only, and banks the result through the same check."""
from __future__ import annotations

import argparse, hashlib, json, os, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "harness"))
LOCK_WAIT = 1700.0   # s; under BASH_MAX_TIMEOUT_MS (30 min), so a blocked tool reports instead of being killed silently


def _cfg() -> dict:
    f = Path.cwd() / ".lra_env.json"
    try:
        return json.loads(f.read_text()) if f.exists() else {}
    except ValueError:
        return {}


def get(k: str, d=None):
    return os.environ.get(k) or _cfg().get(k) or d


def ws() -> Path:
    return Path(get("LRA_WORKSPACE", os.getcwd()))


def problem() -> str:
    name = get("LRA_PROBLEM")
    if not name:
        _out({"ok": False, "errors": ["LRA_PROBLEM is not set (no .lra_env.json in the workspace): run the tool from the problem workspace"]}); sys.exit(2)
    return name


def _out(d, indent=None) -> None:
    print(json.dumps(d, ensure_ascii=False, indent=indent))


def wfile(arg: str | None, default: str = "candidate.lean") -> Path:
    """A workspace file by name (basename only, as v1's lean_check.py). Missing -> a JSON error naming the files-only rule, exit 2."""
    p = ws() / Path(arg or default).name
    if not p.exists():
        _out({"ok": False, "errors": [f"no such file in the workspace: {Path(arg or default).name} (v2 tools take workspace file names only; "
                                      "the problem is read from the environment)"]}); sys.exit(2)
    return p


def provenance() -> dict:
    return {"kind": "closed-dev-only", "model": get("LRA_MODEL", "claude") + "@" + get("LRA_AGENT_TAG", "claude-code"),
            "run_id": get("LRA_RUN_ID", "cc-adhoc"), "mode": get("LRA_MODE", "agent-cc-v2")}


def check(path: Path, text: str | None = None) -> dict:
    """One file through the normal lean_check path (scored, recorded in state.json, a verified record on a new best, best.lean), holding the
    state lock for the whole read-compile-write; plus the ledger win, `axis` and `progress` (harness/inrun.locked_check)."""
    from harness.inrun import locked_check
    name, w = problem(), ws(); prov = provenance()
    return locked_check(w, name, path.read_text() if text is None else text, prov, ROOT / "probe/runs" / prov["run_id"] / "verified.jsonl", LOCK_WAIT)


def _state() -> dict:
    try:
        return json.loads((ws() / "state.json").read_text())
    except (OSError, ValueError):
        return {}


def _best_score() -> float:
    sp = ws() / "state.json"
    try:
        return float((json.loads(sp.read_text()).get("best") or {}).get("score") or 33.33)
    except (OSError, ValueError):
        return 33.33


# ---- tools --------------------------------------------------------------------------------------------------------------------------
def t_lean_check(argv) -> int:
    path = wfile(argv[0] if argv else None)
    _out(check(path), indent=1); return 0


def t_lean_check_variants(argv) -> int:
    files = [f for f in argv if not f.startswith("-")]
    if not files:
        print("usage: lean_check_variants.py a.lean b.lean ...  (up to 6 workspace files)"); return 2
    if len(files) > 6:
        print(f"WARNING: {len(files)} files given; only the first 6 run (tool cap) — split the rest into a second call")
    before = _best_score(); rows = []; winner = None; last = {}
    for fn in files[:6]:
        path = ws() / Path(fn).name
        if not path.exists():
            rows.append({"file": fn, "ok": False, "error": "no such file in the workspace"}); continue
        res = last = check(path)
        if res.get("fixed_decl"):   # an auto-fix compiled: keep it in the variant file, so a copy to candidate.lean carries it
            path.write_text(res["fixed_decl"].rstrip() + "\n")
        rows.append({"file": fn, "ok": res.get("ok"), "tokens": res.get("tokens"), "heartbeats": res.get("heartbeats"),
                     "predicted": res.get("predicted_score_if_compatible"), "score": res.get("score"), "new_best": bool(res.get("new_best")),
                     "error": (res.get("errors") or [None])[0], "auto_fixed": res.get("auto_fixed")})
        if res.get("new_best"):
            winner = path   # checked one after another: the last new best beats every earlier one
    rows.sort(key=lambda r: (not r.get("ok"), -(r.get("score") or r.get("predicted") or 0)))
    sp = ws() / "state.json"
    best = json.loads(sp.read_text())["best"] if sp.exists() else {}
    out = {"variants": rows, "best_after": {k: best.get(k) for k in ("score", "tokens", "heartbeats")}}
    if winner is not None:
        if winner.resolve() != (ws() / "candidate.lean").resolve():   # candidate.lean itself may be a variant (SameFileError, review 2026-10-12)
            shutil.copyfile(winner, ws() / "candidate.lean")
        out["note"] = f"{winner.name} ({best.get('score')}) beats the previous best ({before}); " + (
            "copied to candidate.lean" if winner.name != "candidate.lean" else "kept in candidate.lean")
    else:
        out["note"] = f"no variant beat the stored best ({before}); candidate.lean unchanged"
    ax = best_axis(json.loads(sp.read_text()) if sp.exists() else {})
    if ax:   # R1 / R2 (round 2): the stored best's axis and this session's progress after the batch
        out["axis_of_best"] = ax
    if last.get("progress"):
        out["progress"] = last["progress"]
    _out(out, indent=1); return 0


def best_axis(state: dict) -> dict | None:
    """`axis` (harness/cc_levers.axis) of the stored best."""
    from harness import cc_levers
    from harness.leantools import ROWS, HBS
    from scorer.score import local_reference_heartbeats
    b = state.get("best") or {}; name = problem()
    if not b.get("proof") or name not in ROWS:
        return None
    return cc_levers.axis(ROWS[name]["proof_length"], local_reference_heartbeats(name) or HBS.get(name), b.get("tokens"), b.get("heartbeats"),
                          state.get("hb_floor"))


def t_lean_mine(argv) -> int:
    ap = argparse.ArgumentParser(prog="lean_mine.py"); ap.add_argument("file", nargs="?"); ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args(argv)
    src = wfile(a.file); name = problem()
    from mine import mine
    res = mine(name, src.read_text(), jobs=a.jobs, log=lambda *_: None)
    if res.get("error"):
        _out({"ok": False, "errors": [res["error"]]}); return 0
    out = {"base_tokens": res.get("base_tokens"), "blocks": res.get("blocks"),
           "block_hits": {f"block {int(k) + 1}": {"closer": v[0], "tokens_saved": v[1]} for k, v in (res.get("block_hits") or {}).items()},
           "tail_cuts": [{"from_body_line": k + 1, "tokens_saved": s} for k, s in (res.get("suffix_ok") or [])], "whole_proof_closers": res.get("whole_ok")}
    if res.get("best"):
        mined = ws() / "mined.lean"; mined.write_text(res["best"]["proof"].rstrip() + "\n")
        chk = check(mined)
        out["mined"] = {"how": res["best"].get("how"), "tokens": chk.get("tokens"), "score": chk.get("score") or chk.get("predicted_score_if_compatible"),
                        "ok": chk.get("ok"), "new_best": bool(chk.get("new_best"))}
        if chk.get("new_best"):
            shutil.copyfile(mined, ws() / "candidate.lean")
            out["note"] = "mined.lean beats the stored best; banked and copied to candidate.lean"
        else:
            out["note"] = "mined.lean banked (checked), not above the stored best; candidate.lean unchanged"
    else:
        out["note"] = "no compiling cut found; the remaining length needs a different proof shape"
    _out(out); return 0


def t_goal_map(argv) -> int:
    ap = argparse.ArgumentParser(prog="goal_map.py"); ap.add_argument("file", nargs="?"); ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--from-line", type=int, default=0)
    a = ap.parse_args(argv)
    src = wfile(a.file); name = problem()
    from goals import goal_map
    _out(goal_map(name, src.read_text(), depth=2 if a.depth >= 2 else 1, from_line=a.from_line)); return 0


def t_skeleton_check(argv) -> int:
    ap = argparse.ArgumentParser(prog="skeleton_check.py"); ap.add_argument("file", nargs="?")
    a = ap.parse_args(argv)
    src = wfile(a.file); name = problem()
    from harness.leantools import ROWS
    from scorer.tokenize import split_declaration
    draft = src.read_text().rstrip()
    if split_declaration(draft, ROWS[name]["statement"]) is None:
        _out({"ok": False, "errors": ["statement differs from the reference statement (must be byte-for-byte identical, followed by :=)"]}); return 0
    from goals import skeleton_check
    _out(skeleton_check(name, draft)); return 0


def t_heartbeat_profile(argv) -> int:
    # review 2026-10-12: 8 cuts as the session-start HEARTBEAT MAP (12 meant ~14 compiles: past the 5 m cache on the 5 m arms)
    ap = argparse.ArgumentParser(prog="heartbeat_profile.py"); ap.add_argument("file", nargs="?"); ap.add_argument("--max-cuts", type=int, default=8)
    a = ap.parse_args(argv)
    src = wfile(a.file, "candidate.lean"); name = problem()
    decl = src.read_text().rstrip(); sha = hashlib.sha256(decl.encode()).hexdigest()[:12]
    res = (_state().get("profile_cache") or {}).get(sha)
    if res is not None:   # round 2 (R1): cached per proof sha, as agent.py's lean_profile; the same cache feeds the HEARTBEAT MAP
        _out(dict(res, cached=True)); return 0
    from profile import profile
    res = profile(name, decl, max_cuts=a.max_cuts)
    save_profile(sha, res)
    _out(res); return 0


def save_profile(sha: str, res: dict) -> None:
    """profile_cache[sha] (<= 6 entries) and hb_floor in state.json, under the state lock (the profile itself ran outside it)."""
    from harness.statelock import state_lock
    with state_lock(ws(), timeout=LOCK_WAIT):
        sp = ws() / "state.json"
        try:
            st = json.loads(sp.read_text())
        except (OSError, ValueError):
            return
        cache = st.setdefault("profile_cache", {}); cache[sha] = res
        while len(cache) > 6:
            cache.pop(next(iter(cache)))
        if res.get("floor"):
            st["hb_floor"] = res["floor"]   # every later check reports H points left against the real floor
        sp.write_text(json.dumps(st, ensure_ascii=False, indent=1))


def t_normalize_check(argv) -> int:
    """Lexer normalizer, then the heartbeat polish, each strictly-better only (both re-check Z on every toolchain); a changed proof is written
    to normalized.lean and checked through the normal path (state, ledger, verified record); candidate.lean takes it on a new best."""
    ap = argparse.ArgumentParser(prog="normalize_check.py"); ap.add_argument("file", nargs="?")
    ap.add_argument("--no-polish", action="store_true", help="the lexer normalizer only (no heartbeat polish)")
    ap.add_argument("--no-normalize", action="store_true", help="the heartbeat polish only")
    a = ap.parse_args(argv)
    src = wfile(a.file); name = problem(); decl = src.read_text().rstrip(); cur = decl; out = {}; base = None
    keys = ("status", "before", "after", "applied", "gain", "compiles")
    if not a.no_normalize:
        import normalize as _norm
        r1 = _norm.normalize(name, decl, log=lambda *_: None)
        out["normalize"] = {k: r1.get(k) for k in keys if k in r1}
        if r1.get("status") == "improved":
            cur = r1["proof"].rstrip(); base = r1.get("after")
        else:
            base = r1.get("before")
    if not a.no_polish and (base is None or base.get("ok")):
        import hb_polish as _pol
        r2 = _pol.polish(name, cur, base=base)
        out["hb_polish"] = {k: r2.get(k) for k in keys if k in r2}
        if r2.get("status") == "improved":
            cur = r2["proof"].rstrip()
    if cur == decl:
        out["note"] = ("no strictly-better rewrite (each pass keeps a rewrite only if the whole proof scores higher with Z unchanged); "
                       "nothing banked, candidate.lean unchanged")
        _out(out, indent=1); return 0
    nf = ws() / "normalized.lean"; nf.write_text(cur + "\n")
    chk = check(nf)
    if chk.get("fixed_decl"):   # an auto-fix compiled: keep it in the file, so a copy to candidate.lean carries it (as variants)
        nf.write_text(chk["fixed_decl"].rstrip() + "\n")
    out["checked"] = {k: chk.get(k) for k in ("ok", "tokens", "heartbeats", "score", "predicted_score_if_compatible", "new_best", "errors", "axis", "progress")
                      if chk.get(k) is not None}
    if chk.get("new_best"):
        shutil.copyfile(nf, ws() / "candidate.lean")
        out["note"] = "normalized.lean beats the stored best: banked and copied to candidate.lean"
    else:
        out["note"] = "normalized.lean checked and recorded, not above the stored best; candidate.lean unchanged"
    _out(out, indent=1); return 0


def t_lemma_search_cli(argv) -> int:
    ap = argparse.ArgumentParser(prog="lemma_search_cli.py"); ap.add_argument("file", nargs="?"); ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--budget", type=float, default=120.0); ap.add_argument("--probes", action="store_true", help="also run exact? at each step (slower)")
    a = ap.parse_args(argv)
    src = wfile(a.file); name = problem()
    from lemma_search import search
    r = search(name, src.read_text().rstrip(), top=a.top, probes=a.probes, budget=a.budget)
    print(json.dumps({"suggestions": [{k: s.get(k) for k in ("name", "signature", "source", "line", "why")} for s in (r.get("suggestions") or [])[:a.top]],
                      "runtime_s": r.get("runtime_s"), "probes": a.probes}, ensure_ascii=False)[:9000]); return 0


def t_tok_count(argv) -> int:
    files = argv or ["candidate.lean", "best.lean"]
    name = problem()
    from harness.leantools import ROWS
    from scorer.tokenize import split_declaration, count_tokens
    out = {}
    for f in files:
        p = ws() / Path(f).name
        if not p.exists():
            continue
        body = split_declaration(p.read_text().rstrip(), ROWS[name]["statement"])
        out[f] = count_tokens(body) if body is not None else {"error": "statement differs from the reference statement: no proof body found",
                                                              "whole_file_tokens": count_tokens(p.read_text())}
    _out(out); return 0


TOOLS = {"lean_check": t_lean_check, "lean_check_variants": t_lean_check_variants, "lean_mine": t_lean_mine, "goal_map": t_goal_map,
         "skeleton_check": t_skeleton_check, "heartbeat_profile": t_heartbeat_profile, "lemma_search_cli": t_lemma_search_cli, "tok_count": t_tok_count,
         "normalize_check": t_normalize_check}


def main(tool: str, argv: list[str] | None = None) -> int:
    try:
        return TOOLS[tool](sys.argv[1:] if argv is None else argv)
    except TimeoutError as e:
        _out({"ok": False, "errors": [f"{e}: another tool call is still compiling in this workspace; retry after it"]}); return 3
