#!/usr/bin/env python3
"""Tests of --heartbeat-first (2026-10-13; harness/cards.py HEARTBEAT_FIRST + HB_REWRITES, agent.py, agent_claude_code.py --prompt v2,
agent_codex.py), plain asserts, no Lean, no model, no git. Flag OFF must leave every prompt byte-identical; flag ON must show the card and drop
the contradictory guidance. Review 2026-10-13 (finding 1): the flag-off guarantee is structural (the rewrite functions patched to raise, the
call sites checked in agent.py's AST), never a comparison with a pinned commit, so later prompt edits and clones without that commit pass.
  rewrites_live    every HB_REWRITES `old` occurs in a live prompt source (agent.py literals and tool descriptions, cards, prompt_v2), no `new`
                   holds an `old` or a contradictory marker, heartbeat_aware is idempotent; R1's length branch keeps the old closer list
  gate             heartbeat_first_on: no axis -> on; H points left >= L points left -> on; H < L -> off; best_axis from a state; the floor
                   counts; cards.gate logs and treats an axis error as no axis
  cards            cards_for(default) is the ALWAYS + pattern-card block; heartbeat_first=True adds HEARTBEAT_FIRST after ALWAYS and rewrites
                   the inductive card's items (2) and (4)
  off_never_rewrites with heartbeat_aware / best_axis / heartbeat_first_on / gate patched to raise: cards_for, system_v2, build_prompt_v2
                   (fresh, resume + repo card + lever review, from-reference), agent_claude_code's system prompt and agent_codex's task all
                   build; v2 with the flag on and the gate off equals the default byte for byte
  agent_structure  agent.py: every heartbeat_aware call sits under the flag (main) or behind `_hbf` (run_problem's _hbw / closed-lessons
                   splice), _hbw is the identity otherwise, the 6 _hbw sites; module constants are not rewritten at import; the rewritten
                   briefs, lessons, lever review, system prompts and lean_mine description lose every marker; main() declares the flag
  v2_on            build_prompt_v2(heartbeat_first=True) with the gate on (no axis; H >= L): section 'heartbeat_first' right after 'cards',
                   the card in the card block, the restructure brief and lever review rewritten; system_v2(heartbeat_first=True) has no marker
  cc_driver        build_cmd_env passes system_v2(.., heartbeat_first) (default unchanged); --heartbeat-first refused under v1; --help lists it
  codex            agent_codex.codex_prompt: default (attribute missing / False) and gate off equal with_extras(task_prompt(..)); gate on appends
                   HEARTBEAT_FIRST_V1 (no `axis`, which v1's lean_check.py lacks); --help lists the flag
    python3 harness/test_heartbeat_first.py"""
from __future__ import annotations

import ast, pathlib, subprocess, sys, tempfile, traceback, types

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PROBLEM = "putnam_1964_b2"
# what must be gone wherever the flag is on and the gate passes (the cards / briefs) or the flag is on (system prompts)
MARKERS = ("AUTOMATION FIRST", "`solve_by_elim [C.c1, C.c2]` or", "term-mode `exact`/anonymous constructors over tactic blocks",
           "Avoid tactic blocks except a single closer", "one shared AUTOMATION closer", "fewest tokens, then cut heartbeats",
           "The big wins are still whole blocks", "LENGTH IS THE MISSING AXIS", "Use it after every new compiling skeleton, then golf",
           "`case'` to send sub-goals to `first |", "is shorter as `any_goals A`", "(as `any_goals A` then `all_goals B`)",
           "structural goals → `simp_all`/`aesop`.", "prefer `simp_all`/`simp only [...]` over")
OLD_CLOSERS = ("(`grind` with lemma hints, forward hints `grind [→ lemma]` for lemmas concluding ∃ or a constructor, `simp`, `omega`, `aesop`, "
               "`solve_by_elim`, `linear_combination`)")
AGENT_SRC = (ROOT / "harness/agent.py").read_text()
AGENT_AST = ast.parse(AGENT_SRC)


def _str_consts(tree) -> list[str]:
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _fn(name: str):
    return next(n for n in AGENT_AST.body if isinstance(n, ast.FunctionDef) and n.name == name)


def _ws(tmp: pathlib.Path, attempts: list, runs: int, best: dict | None = None):
    from harness.agent import Workspace
    from harness.leantools import ROWS
    from probe.verify_candidates import newest_first
    row = ROWS[PROBLEM]; primary = newest_first(row["version_info"])[0]
    ws = Workspace(tmp / PROBLEM, row, primary, fresh=True)   # putnambench: no Lean environment is touched
    ws.state["attempts"] = attempts; ws.state["runs"] = [{"run_id": f"r{i}"} for i in range(runs)]
    ws.state["best"] = best or {"score": 61.5, "proof": row["src"], "tokens": 300, "heartbeats": 9000}
    return ws, row, primary


def _gate_states(row):
    """best dicts for: H >= L (gate on), H < L (gate off), no measured heartbeats (no axis: on)."""
    pl = int(row["proof_length"])
    return ({"score": 50.0, "proof": row["src"], "tokens": 1, "heartbeats": 10 ** 8},
            {"score": 50.0, "proof": row["src"], "tokens": 3 * pl, "heartbeats": 0},
            {"score": 33.33, "proof": None, "tokens": pl, "heartbeats": None})


def _live() -> list[str]:
    from harness import cards, prompt_v2 as pv
    from harness import agent
    return (_str_consts(AGENT_AST) + [agent.SYSTEM, agent.SYSTEM_BASE, agent.TOKEN_RULES, agent.LEVER_REVIEW, pv.SYSTEM_V2, pv.CLOSED_LESSONS]
            + [t["description"] for t in agent.TOOLS] + list(cards.CARDS.values()) + list(pv.SCOUT_BRIEFS.values()) + list(pv.REPO_BRIEFS.values()))


def test_rewrites_live():
    from harness import cards
    live = _live()
    for old, new in cards.HB_REWRITES:
        assert any(old in s for s in live), f"rewrite target not in any live prompt (reworded source?): {old[:80]}"
        assert not any(o in new for o, _n in cards.HB_REWRITES), new[:80]
        assert not any(m in new for m in MARKERS), new[:80]
    for s in live:
        once = cards.heartbeat_aware(s)
        assert cards.heartbeat_aware(once) == once
    for s in live[len(_str_consts(AGENT_AST)):]:   # the assembled prompts (agent.py's literals include help strings that name the old text)
        once = cards.heartbeat_aware(s)
        assert not any(m in once for m in MARKERS), [m for m in MARKERS if m in once]
    assert cards.heartbeat_aware("no target here") == "no target here"
    assert OLD_CLOSERS in cards.HB_REWRITES[0][0] and OLD_CLOSERS in cards.HB_REWRITES[0][1]   # finding 5: length branch word for word


def test_gate():
    from harness import cards
    from harness.leantools import ROWS, HBS
    assert cards.heartbeat_first_on(None) is True
    assert cards.heartbeat_first_on({"points_left_heartbeats": 5.0, "points_left_length": 4.0}) is True
    assert cards.heartbeat_first_on({"points_left_heartbeats": 4.0, "points_left_length": 4.0}) is True
    assert cards.heartbeat_first_on({"points_left_heartbeats": 1.0, "points_left_length": 4.0}) is False
    row = ROWS[PROBLEM]; on, off, none = _gate_states(row)
    assert cards.heartbeat_first_on(cards.best_axis(PROBLEM, row, {"best": on}, HBS.get(PROBLEM)))
    assert not cards.heartbeat_first_on(cards.best_axis(PROBLEM, row, {"best": off}, HBS.get(PROBLEM)))
    assert cards.best_axis(PROBLEM, row, {"best": none}, HBS.get(PROBLEM)) is None
    # the profile floor counts: a floor at the best's heartbeats leaves 0 H points
    ax = cards.best_axis(PROBLEM, row, {"best": dict(on, tokens=int(row["proof_length"])), "hb_floor": 10 ** 8}, HBS.get(PROBLEM))
    assert ax["points_left_heartbeats"] == 0 and not cards.heartbeat_first_on(ax)
    logs: list = []
    assert cards.gate(PROBLEM, row, {"best": on}, HBS.get(PROBLEM), log=logs.append) and "heartbeat-first ON (H " in logs[-1]
    assert not cards.gate(PROBLEM, row, {"best": off}, HBS.get(PROBLEM), log=logs.append) and "heartbeat-first off" in logs[-1]
    assert cards.gate(PROBLEM, row, {"best": "broken"}, HBS.get(PROBLEM), log=logs.append) and "no axis yet" in logs[-1]   # error -> on
    assert any("axis failed" in x for x in logs)


def test_cards():
    from harness import cards
    stmts = ["theorem t (h : Typing Γ e τ) : Red e e' := by induction h <;> simp", "theorem c : ∫ x in a..b, f x = 0 := by calc _ = _ := rfl",
             "theorem n (p : ℕ) (hp : Nat.Prime p) : p ∣ p ^ 2 := by ring", "theorem s : (Finset.range n).card = n := by simp [Finset.card_range]"]
    ctx = "\n".join(f"theorem lem{i} (h : Typing Γ e τ) (k : Red e e') : Typing Γ e' τ := by sorry" for i in range(6))
    head = "TECHNIQUE CARDS (measured on other problems; patterns, not answers):"
    for s in stmts:
        for c in ("", ctx):
            want = "\n\n".join([head, cards.ALWAYS] + [cards.CARDS[k] for k in cards.select(s, s, c)])
            assert cards.cards_for(s, s, c) == want == cards.cards_for(s, s, c, heartbeat_first=False), s
            assert cards.HEARTBEAT_FIRST not in want
    on = cards.cards_for(stmts[0], stmts[0], heartbeat_first=True)
    assert cards.HEARTBEAT_FIRST in on and on.index(cards.ALWAYS) < on.index(cards.HEARTBEAT_FIRST) < on.index("INDUCTIVE RELATIONS")
    assert "explicit constructor terms" in on and "not into a `first | …` retry chain" in on and not any(m in on for m in MARKERS)


class _Raise:
    """Patches the rewrite entry points of harness.cards to raise: any default path that reaches them fails the test."""
    NAMES = ("heartbeat_aware", "best_axis", "heartbeat_first_on", "gate")

    def __enter__(self):
        from harness import cards
        self.saved = {n: getattr(cards, n) for n in self.NAMES}

        def boom(*a, **k):
            raise AssertionError("a flag-off path reached the heartbeat-first rewrite")
        for n in self.NAMES:
            setattr(cards, n, boom)
        return self

    def __exit__(self, *exc):
        from harness import cards
        for n, f in self.saved.items():
            setattr(cards, n, f)
        return False


def _v2_cases(pv, td: pathlib.Path, **kw) -> list:
    """build_prompt_v2 over the selftest shapes (fresh with leads/upstream/extras; resume + repo card + lever review; from-reference with a
    blind target), paths normalised."""
    leads = lambda n, d: [{"name": "Foo.bar_baz", "source": "mathlib", "line": 12, "signature": "Foo.bar_baz : a = b", "why": "matches goal"}]
    up = lambda r, p: "UPSTREAM (precomputed): unchanged"
    out = []
    for i, (att, runs, extra) in enumerate((([], 0, dict(leads=leads, upstream=up, gate_usd=2.85, extras="\n\nEXTRAS")),
                                            ([{"ok": True}], 2, dict(leads=None, upstream=up, upstream_history=False, repo_cards=True, lever_review=True)),
                                            ([{"ok": True}], 2, dict(leads=None, upstream=None, from_reference=True, lever_review=True)))):
        ws, row, primary = _ws(td / f"c{i}", att, runs, kw.get("best"))
        args = {k: v for k, v in kw.items() if k != "best"}
        p, sec = pv.build_prompt_v2(PROBLEM, row, primary, ws, **extra, **args)
        out.append((p.replace(str(td), "<TMP>"), sec))
    return out


def _cc_sysp(row, primary, **kw) -> str:
    from harness import agent_claude_code as cc
    with tempfile.TemporaryDirectory() as td:
        ws = types.SimpleNamespace(root=pathlib.Path(td) / PROBLEM); ws.root.mkdir()
        a = types.SimpleNamespace(prompt="v2", upstream_history=True, sealed=False, model="claude-opus-5-5", run_id="t-hbf", max_turns_flag=False,
                                  turns=40, effort=None, cache_ttl="1h", max_output_tokens=None, **kw)
        c = cc.build_cmd_env(PROBLEM, row, primary, ws, "P", a)[0]
        return c[c.index("--system-prompt") + 1]


def test_off_never_rewrites():
    from harness import cards, prompt_v2 as pv, agent_codex as cx
    from harness.agent_claude_code import task_prompt, with_extras
    from harness.leantools import ROWS
    from probe.verify_candidates import newest_first
    row = ROWS[PROBLEM]; primary = newest_first(row["version_info"])[0]
    _on, off, _none = _gate_states(row)
    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2, tempfile.TemporaryDirectory() as t3:
        with _Raise():
            for s in ("theorem t (h : Typing Γ e τ) : Red e e' := by induction h <;> simp", "theorem s : x = x := rfl"):
                assert cards.HEARTBEAT_FIRST not in cards.cards_for(s, s) and cards.cards_for(s, s) == cards.cards_for(s, s, heartbeat_first=False)
            for uh in (True, False):
                assert pv.system_v2(uh) == pv.system_v2(uh, False)
            assert pv.system_v2(True) == pv.SYSTEM_V2
            default = _v2_cases(pv, pathlib.Path(t1))
            assert default == _v2_cases(pv, pathlib.Path(t2), heartbeat_first=False)
            for p, sec in default:
                assert "heartbeat_first" not in sec and cards.HEARTBEAT_FIRST not in p
            assert _cc_sysp(row, primary) == _cc_sysp(row, primary, heartbeat_first=False) == pv.SYSTEM_V2
            ws, _r, _p = _ws(pathlib.Path(t3), [], 0)
            for a in (types.SimpleNamespace(turns=40), types.SimpleNamespace(turns=40, heartbeat_first=False)):
                assert cx.codex_prompt(PROBLEM, row, primary, ws, a) == (with_extras(task_prompt(PROBLEM, row, primary, ws, 40), PROBLEM, ws, a), False)
        # flag on, gate off: the user prompt is the default byte for byte (only the system prompt differs, by design)
        with tempfile.TemporaryDirectory() as t4, tempfile.TemporaryDirectory() as t5:
            logs: list = []
            assert _v2_cases(pv, pathlib.Path(t4), best=off) == _v2_cases(pv, pathlib.Path(t5), heartbeat_first=True, best=off, log=logs.append)
            assert any("heartbeat-first off" in x for x in logs), logs


def _ancestors(tree) -> dict:
    par = {}
    for n in ast.walk(tree):
        for ch in ast.iter_child_nodes(n):
            par[ch] = n
    return par


def _mentions(node, word: str) -> bool:
    return word in ast.unparse(node)


def test_agent_structure():
    from harness import cards, prompt_v2 as pv
    from harness import agent
    par = _ancestors(AGENT_AST)
    # every rewrite call is under the flag (main) or behind the gate (_hbf in run_problem)
    calls = [n for n in ast.walk(AGENT_AST) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "heartbeat_aware"]
    assert calls
    for c in calls:
        node, ok = c, False
        while node in par:
            child, node = node, par[node]
            if isinstance(node, ast.If) and _mentions(node.test, "heartbeat_first") and child in node.body:
                ok = True; break
            if isinstance(node, ast.IfExp) and isinstance(node.test, ast.Name) and node.test.id == "_hbf" and child is node.body:
                ok = True; break
        assert ok, ast.unparse(c)
    rp = _fn("run_problem")
    hbf = [n for n in ast.walk(rp) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_hbf" for t in n.targets)]
    assert len(hbf) == 2 and isinstance(hbf[0].value, ast.Constant) and hbf[0].value.value is False
    assert isinstance(par[hbf[1]], ast.If) and ast.unparse(par[hbf[1]].test) == "getattr(args, 'heartbeat_first', False)"
    hbw = next(n for n in ast.walk(rp) if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "_hbw")
    ie = hbw.value
    assert isinstance(ie, ast.IfExp) and ast.unparse(ie.test) == "_hbf" and ast.unparse(ie.orelse) == "lambda s: s"
    # _hbw sites: repo brief, scout brief, structural pass, heartbeat-first brief, lever review, closed-lessons splice (under `if _hbf:`)
    wrapped = [c for c in ast.walk(rp) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "_hbw"]
    assert len(wrapped) == 6, len(wrapped)
    splice = [c for c in wrapped if "_cl0" in ast.unparse(c)]
    assert len(splice) == 1 and any(isinstance(a, ast.If) and ast.unparse(a.test) == "_hbf" for a in _chain(par, splice[0]))
    cf = [c for c in ast.walk(rp) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "cards_for"]
    assert len(cf) == 1 and [ast.unparse(k.value) for k in cf[0].keywords if k.arg == "heartbeat_first"] == ["_hbf"]
    # nothing is rewritten at import: the module constants still hold the old wording
    assert "AUTOMATION FIRST" in agent.SYSTEM and "LENGTH IS THE MISSING AXIS" in agent.SYSTEM and "AUTOMATION FIRST" in agent.SYSTEM_BASE
    mine = next(t for t in agent.TOOLS if t["name"] == "lean_mine")["description"]
    assert "Use it after every new compiling skeleton, then golf" in mine
    # the rewritten pieces lose every marker
    lits = [c.args[0].value for c in wrapped if isinstance(c.args[0], ast.Constant)]
    assert len(lits) == 2 and any("STRUCTURAL PASS" in s for s in lits) and any("HEARTBEAT FIRST:" in s for s in lits)
    lessons = pv.drift_nodes(AGENT_SRC)
    briefs = lessons["SCOUT_BRIEFS"]
    for s in lits + [briefs["automation"], briefs["direct"], briefs["restructure"], lessons["CLOSED_LESSONS"], agent.LEVER_REVIEW,
                     lessons["REPO_BRIEFS"]["arklib"], lessons["REPO_BRIEFS"]["physlib"], mine]:
        assert any(m in s for m in MARKERS) and not any(m in cards.heartbeat_aware(s) for m in MARKERS), s[:60]
    assert "pin it to `grind only [...]`" in cards.heartbeat_aware(lessons["REPO_BRIEFS"]["cslib"])   # R9 adds to, keeps, the cslib advice
    for s in (agent.SYSTEM, agent.SYSTEM_BASE, agent.SYSTEM_BASE + agent.TOKEN_RULES):
        h = cards.heartbeat_aware(s)
        assert "AUTOMATION FIRST" in s and not any(m in h for m in MARKERS) and "CLOSERS BY THE AXIS" in h and OLD_CLOSERS in h
    assert "LENGTH (while `axis.work_on` in lean_check is tokens" in cards.heartbeat_aware(agent.SYSTEM)
    # main(): the flag (store_true) and its rewrite of SYSTEM, SYSTEM_BASE and the tool descriptions, all inside `if args.heartbeat_first:`
    mn = _fn("main")
    decl = [c for c in ast.walk(mn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "add_argument"
            and c.args and isinstance(c.args[0], ast.Constant) and c.args[0].value == "--heartbeat-first"]
    assert len(decl) == 1 and any(k.arg == "action" and k.value.value == "store_true" for k in decl[0].keywords)
    blk = next(n for n in ast.walk(mn) if isinstance(n, ast.If) and ast.unparse(n.test) == "args.heartbeat_first")
    body = "\n".join(ast.unparse(b) for b in blk.body)
    assert "globals()['SYSTEM'] = " in body and "globals()['SYSTEM_BASE'] = " in body and "for _t in TOOLS" in body
    p = subprocess.run([sys.executable, str(ROOT / "harness/agent.py"), "--help"], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0 and "--heartbeat-first" in p.stdout, p.stderr[-400:]   # the --lean-io help's `113%%` fix (2026-10-13)


def _chain(par: dict, node):
    while node in par:
        node = par[node]
        yield node


def test_v2_on():
    from harness import cards, prompt_v2 as pv
    from harness.leantools import ROWS
    on, _off, none = _gate_states(ROWS[PROBLEM])
    for best in (on, none):
        with tempfile.TemporaryDirectory() as td:
            logs = []
            cases = _v2_cases(pv, pathlib.Path(td), heartbeat_first=True, best=best, log=logs.append)
            for p, sec in cases:
                assert "heartbeat_first" in sec and sec[sec.index("cards") + 1] == "heartbeat_first", sec
                assert cards.HEARTBEAT_FIRST in p and p.index("TECHNIQUE CARDS") < p.index("HEARTBEAT-FIRST RULES"), sec
                assert not any(m in p for m in MARKERS), [m for m in MARKERS if m in p]
            assert "lever_review" in cases[1][1] and "on heartbeats one routed closer per goal" in cases[1][0]
            assert "keep the one with the highest score (`axis` says which axis holds the points)" in cases[2][0]
            assert any("heartbeat-first ON" in x for x in logs), logs
    for uh in (True, False):
        s = pv.system_v2(uh, heartbeat_first=True)
        assert s != pv.system_v2(uh) and s == cards.heartbeat_aware(pv.system_v2(uh)) and not any(m in s for m in MARKERS)
        assert "On the length axis the big wins" in s and "when `axis.work_on` is heartbeats, pin that closer" in s
        assert "On the length axis, `any_goals A` then `all_goals B` is 2 tokens shorter" in s
        assert ("git log" in s) == uh


def test_cc_driver():
    from harness import prompt_v2 as pv
    from harness.leantools import ROWS
    from probe.verify_candidates import newest_first
    row = ROWS[PROBLEM]; primary = newest_first(row["version_info"])[0]
    assert _cc_sysp(row, primary) == pv.system_v2(True)                     # attribute missing (older callers)
    assert _cc_sysp(row, primary, heartbeat_first=False) == pv.system_v2(True)
    assert _cc_sysp(row, primary, heartbeat_first=True) == pv.system_v2(True, True) != pv.system_v2(True)
    p = subprocess.run([sys.executable, str(ROOT / "harness/agent_claude_code.py"), "--heartbeat-first", "--problems", PROBLEM],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 2 and "--heartbeat-first need --prompt v2" in p.stderr, (p.returncode, p.stderr[-400:])
    p = subprocess.run([sys.executable, str(ROOT / "harness/agent_claude_code.py"), "--help"], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0 and "--heartbeat-first" in p.stdout


def test_codex():
    from harness import cards, agent_codex as cx
    from harness.agent_claude_code import task_prompt, with_extras
    from harness.leantools import ROWS
    from probe.verify_candidates import newest_first
    row = ROWS[PROBLEM]; primary = newest_first(row["version_info"])[0]
    on, off, none = _gate_states(row)
    v1 = cards.HEARTBEAT_FIRST_V1
    assert v1 != cards.HEARTBEAT_FIRST and "`axis`" not in v1 and "task message" in v1 and v1.startswith("HEARTBEAT-FIRST RULES")
    for best, want in ((on, True), (none, True), (off, False)):
        with tempfile.TemporaryDirectory() as td:
            ws, _r, _p = _ws(pathlib.Path(td), [], 0, best)
            base = with_extras(task_prompt(PROBLEM, row, primary, ws, 40), PROBLEM, ws, types.SimpleNamespace())
            p, hbf = cx.codex_prompt(PROBLEM, row, primary, ws, types.SimpleNamespace(turns=40, heartbeat_first=True))
            assert hbf is want and (p == base + "\n\n" + v1 if want else p == base), (want, p[-200:])
    p = subprocess.run([sys.executable, str(ROOT / "harness/agent_codex.py"), "--help"], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0 and "--heartbeat-first" in p.stdout, p.stderr[-400:]


def main() -> int:
    tests = [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]
    bad = 0
    for k, fn in tests:
        try:
            fn(); print(f"PASS {k}")
        except Exception:  # noqa: BLE001
            bad += 1; print(f"FAIL {k}"); traceback.print_exc()
    print(f"{len(tests) - bad}/{len(tests)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
