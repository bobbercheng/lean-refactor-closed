#!/usr/bin/env python3
"""Drift and golden tests of the Claude Code prompts (docs/cc_driver_v2.md §3), plain asserts, no Lean, no git, no model.
  v1_golden      SYSTEM (formatted with the main checkout's tools path, and raw), task_prompt and with_extras outputs are byte-identical to
                 the pre-v2 code (sha256 prefixes recorded 2026-10-12 from commit ad8cd6ff; checkout paths normalised to <ROOT>)
  prompt_drift   CLOSED_LESSONS, REPO_BRIEFS and SCOUT_BRIEFS['restructure'] equal agent.py's literals (ast.literal_eval of run_problem)
  system_v2      SYSTEM_V2 = v1 core + TOOL MAP + BATCH + TOKEN_RULES + CLOSED_LESSONS + LENGTH + HEARTBEAT + STOP RULE + NOTES + never-cd,
                 static, file-only tool map naming every tool (normalize_check.py included) with when-to-use guidance
  user_prompt_v2 the section order of build_prompt_v2 (agent.py's order), injected leads/upstream (no Lean), flags on/off
  round2_*       (2026-10-12) the stop / resume assembly: lever review + heartbeat levers on a resume, the facts sheet replacing notes and
                 diffs in a from-reference session, the HEARTBEAT MAP (injected profile, cached per sha, only with >= 2 H points left), the
                 RUN TECHNIQUES block (capped), the v2 digest (head + tail notes, v2 claims, earlier-run count without the current run)
  review_*       (2026-10-12, §11) REVIEW_SYSTEM, the reviewer's task message, review_for() (best sha, next session only), the REVIEW block,
                 lineage_facts.md
    python3 harness/test_prompt_v2.py"""
from __future__ import annotations

import hashlib, json, pathlib, sys, tempfile, traceback, types

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MAIN_TOOLS = "/home/user/source/lean-refactor/harness/tools"   # the golden hash was taken on the main checkout
GOLD = {"system_main": "b9c13f412ba498b5", "system_raw": "7e5dad794b160b0a",   # recorded 2026-10-12 on ad8cd6ff (`--fingerprint`)
        "task_prompt": "7afeafad454d07bf", "with_extras": "c466189270bafe63"}


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


class _WS:
    def __init__(self, root: pathlib.Path, attempts: list):
        self.root = root; self.state = {"attempts": attempts, "runs": [], "best": {"score": 33.33}}

    def digest(self) -> str:
        return f"DIGEST attempts={len(self.state['attempts'])}"


def v1_fingerprints(mod) -> dict:
    """task_prompt / with_extras outputs of a module exposing them (the current driver, or the pre-v2 source exec'd by selftest_cc),
    over two warm-up rows, fresh and resumed, and a relay seed + brief; checkout paths normalised."""
    from harness.leantools import ROWS
    from probe.verify_candidates import newest_first
    norm = lambda s, tmp: s.replace(str(tmp), "<TMP>").replace(str(ROOT), "<ROOT>")
    tp, wx = [], []
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        for name in ("putnam_1964_b2", "Core.InitsUpdatesComm"):
            row = ROWS[name]; primary = newest_first(row["version_info"])[0]
            for att in ([], [{"ok": True}]):
                ws = _WS(tmp, att)
                tp.append(norm(mod.task_prompt(name, row, primary, ws, 40), tmp))
        (tmp / "seed").mkdir(); (tmp / "brief").mkdir(); (tmp / "ws").mkdir()
        (tmp / "seed" / "putnam_1964_b2.lean").write_text("SEED PROOF\n"); (tmp / "seed" / "putnam_1964_b2.md").write_text("SEED DIGEST\n")
        (tmp / "brief" / "putnam_1964_b2.md").write_text("BRIEF TEXT\n")
        ws = _WS(tmp / "ws", [])
        for sd, bd in ((None, None), (str(tmp / "seed"), None), (None, str(tmp / "brief")), (str(tmp / "seed"), str(tmp / "brief"))):
            a = types.SimpleNamespace(seed_dir=sd, brief_dir=bd)
            wx.append(norm(mod.with_extras("PROMPT", "putnam_1964_b2", ws, a), tmp))
            wx.append((ws.root / "candidate.lean").read_text() if (ws.root / "candidate.lean").exists() else "<none>")
    return {"task_prompt": _h("\x00".join(tp)), "with_extras": _h("\x00".join(wx))}


def test_v1_golden():
    from harness import agent_claude_code as cc
    assert _h(cc.SYSTEM.format(tools=MAIN_TOOLS)) == GOLD["system_main"], _h(cc.SYSTEM.format(tools=MAIN_TOOLS))
    assert _h(cc.SYSTEM) == GOLD["system_raw"]
    fp = v1_fingerprints(cc)
    assert fp == {"task_prompt": GOLD["task_prompt"], "with_extras": GOLD["with_extras"]}, fp


def test_prompt_drift():
    from harness import prompt_v2 as pv
    lit = pv.drift_nodes((ROOT / "harness/agent.py").read_text())
    assert lit["CLOSED_LESSONS"] == pv.CLOSED_LESSONS, "CLOSED_LESSONS drifted from agent.py"
    assert lit["REPO_BRIEFS"] == pv.REPO_BRIEFS, "REPO_BRIEFS drifted from agent.py"
    assert lit["SCOUT_BRIEFS"]["restructure"] == pv.SCOUT_BRIEFS["restructure"], "SCOUT_BRIEFS['restructure'] drifted from agent.py"


def test_system_v2():
    from harness import prompt_v2 as pv
    from harness.agent import TOKEN_RULES
    from harness.agent_claude_code import SYSTEM, TOOLS_DIR
    s = pv.SYSTEM_V2
    core = SYSTEM.format(tools=TOOLS_DIR)
    assert s.startswith(core) and "{tools}" not in s and "{" + "tools" not in s
    parts = [pv._t(pv.TOOL_MAP), pv._t(pv.BATCH_CC), TOKEN_RULES, pv.CLOSED_LESSONS, pv._t(pv.LENGTH_CC), pv.HEARTBEAT_CC, pv.STOP_RULE,
             pv.NOTES_RULE, pv.NO_CD]
    assert s == core + "".join(parts)
    pos = [s.index(x) for x in parts]
    assert pos == sorted(pos)
    from harness.agent_claude_code import V2_TOOLS
    for tool in ("lean_check.py", "lean_check_variants.py", "lean_run.py", "lean_mine.py", "goal_map.py", "skeleton_check.py",
                 "heartbeat_profile.py", "lemma_search_cli.py", "tok_count.py", "normalize_check.py"):
        assert f"python3 {TOOLS_DIR}/{tool}" in s and tool in V2_TOOLS, tool   # every advertised tool has its permission rule (round 2)
    assert "PROBLEM" not in pv._t(pv.TOOL_MAP) and "never the problem name" in s and "never `cd`" in s and "[tested:" in s
    # round 2: when-to-use guidance, heartbeat prices + small-reference rule (R1), stop rule (R2), GENERAL tag + limit claims (R5/R7)
    tm = pv._t(pv.TOOL_MAP)
    assert "WHEN TO USE WHICH" in tm and tm.index("heartbeat_profile.py first") < tm.index("goal_map.py on the costliest block")
    assert all(x in s for x in ("~231 hb", "~1.4k", "~165", "302 vs 46", "SMALL-REFERENCE RULE", "3-4k heartbeats", "`axis`"))
    assert "STOP RULE" in s and "8 consecutive checks without a new best" in s and "2 or more" in s and "progress.may_finish" in s
    assert "`GENERAL:`" in s and "optimal" in pv.NOTES_RULE
    # round-2 review (2026-10-12): no "length is the missing axis" framing (R1), the small-reference rule overrides TOKEN COUNTING's closer
    # advice, normalize_check once before stopping (not after every best), and Edit needs a Read first (Claude Code refuses otherwise)
    assert "LENGTH IS THE MISSING AXIS" not in s and "when `axis.work_on` is tokens" in s and "overrides the one-closer advice of TOKEN COUNTING" in s
    assert "Once, before you stop: normalize_check.py" in tm and "After every new best" not in tm and "up to ~20 compiles" in tm
    assert "Read each vK.lean, then Edit it" in s and "a new file needs no Read" in s
    assert "SHELL RULE" in s and "variants.py N" in s   # 2026-10-12 G0b smoke: compound shell commands are refused under dontAsk
    s2 = pv.system_v2(upstream_history=False)
    assert "git log" not in s2 and "git history" not in s2 and s2 != s and pv.system_v2(True) == s


def _ws(tmp: pathlib.Path, name: str, attempts: list, runs: int):
    from harness.agent import Workspace
    from harness.leantools import ROWS
    from probe.verify_candidates import newest_first
    row = ROWS[name]; primary = newest_first(row["version_info"])[0]
    ws = Workspace(tmp / name, row, primary, fresh=True)   # putnambench: no Lean environment is touched
    ws.state["attempts"] = attempts; ws.state["runs"] = [{"run_id": f"r{i}"} for i in range(runs)]
    ws.state["best"] = {"score": 61.5, "proof": row["src"], "tokens": 300, "heartbeats": 9000}
    return ws, row, primary


def test_user_prompt_v2():
    from harness import prompt_v2 as pv
    from harness.agent import LEVER_REVIEW
    leads = lambda n, d: [{"name": "Foo.bar_baz", "source": "mathlib", "line": 12, "signature": "Foo.bar_baz : a = b", "why": "matches goal"}]
    up = lambda r, p: "UPSTREAM (precomputed): unchanged"
    with tempfile.TemporaryDirectory() as td:
        ws, row, primary = _ws(pathlib.Path(td), "putnam_1964_b2", [], 0)
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws, leads=leads, upstream=up, gate_usd=2.85, extras="\n\nEXTRAS")
        assert sec == ["header", "original.lean", "candidate.lean", "upstream", "cards", "leads", "extras"], sec
        order = ["Problem `putnam_1964_b2`", "original.lean (the REFERENCE proof)", "candidate.lean (your current best)", "UPSTREAM (precomputed)",
                 "TECHNIQUE CARDS", "LIBRARY LEADS", "Foo.bar_baz [mathlib, line 12]", "EXTRAS"]
        pos = [p.index(x) for x in order]
        assert pos == sorted(pos), pos
        assert "about $2.85 for this session" in p and "Both original.lean and candidate.lean are shown below" in p and p.endswith("EXTRAS")
        assert "Read candidate.lean once before your first Edit" in p and "no need to Read" not in p   # round-2 review: Edit needs a Read
        assert "REPO AUTOMATION" not in p and "SCOUT RUN" not in p and LEVER_REVIEW not in p
        # the technique cards name the v2 scripts, never agent.py's in-process tools (review 2026-10-12); round 2: the v2 lean_check.py
        # result carries `axis` now, so the card names it on that script
        assert "heartbeat_profile.py" in p and "goal_map.py" in p and not any(x in p for x in ("lean_goals", "lean_profile")), p
        assert "read `axis` in the lean_check.py result" in p
        from harness import cards as _cards
        every = "\n".join([_cards.ALWAYS, *_cards.CARDS.values()])
        assert not any(x in pv.cards_v2(every) for x in ("lean_goals", "lean_profile", "`axis` in lean_check ("))
        # flags: repo card, from-reference (scout + blind target + restructure), lever review only on a resume, upstream off, leads off
        ws2, row, primary = _ws(pathlib.Path(td) / "b", "putnam_1964_b2", [{"ok": True}], 2)
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws2, leads=None, upstream=up, upstream_history=False, repo_cards=True,
                                    lever_review=True)
        assert sec == ["header", "original.lean", "candidate.lean", "cards", "repo_card", "lever_review", "hb_levers"], sec
        assert pv.REPO_BRIEFS["putnambench"] in p and p.endswith(LEVER_REVIEW + pv.LEVER_HB) and "UPSTREAM" not in p and "Continue from candidate.lean" in p
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws2, leads=None, upstream=None, from_reference=True, lever_review=True)
        assert sec == ["header", "original.lean", "candidate.lean", "cards", "blind_target", "scout", "restructure"], sec
        assert "BLIND TARGET: the stored best has 300 tokens and 9000 heartbeats (score 61.5)" in p and p.endswith(pv.SCOUT_BRIEFS["restructure"])
        assert "candidate.lean (reset to the reference for this run)" in p and LEVER_REVIEW not in p
        # a failing lead search never breaks the prompt
        def boom(*_a):
            raise RuntimeError("no lean here")
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws2, leads=boom, upstream=boom)
        assert "leads" not in sec and "upstream" not in sec


NOTES_R2 = ("# Notes\n## What worked\n- grind closes the base case [tested: lean_check -> OK 61.5]\n- The proof is optimal at 300 tokens, counted by hand\n"
            "- this is as short as it gets [tested: counted tokens on paper -> 300]\n"
            "## Failed\n- `simp_all` in the step case [tested: lean_check -> FAIL unsolved goals]\n```lean\n  have h1 := foo\n  simp at h1\n  exact h1\n```\n"
            "## Next\n- try `simp only [Finset.card_le]` in the step case\n")


def _ws_r2(tmp: pathlib.Path):
    ws, row, primary = _ws(tmp, "putnam_1964_b2", [{"ok": False, "error": "12:4: unsolved goals ⊢ x = y", "run_id": "r1", "tokens": 9, "heartbeats": None},
                                                   {"ok": False, "error": "13:2: unknown identifier 'Foo.bar'", "run_id": "r1"},
                                                   {"ok": True, "score": 61.5, "run_id": "r1", "tokens": 300, "heartbeats": 9000}], 2)
    ws.state["ledger"] = {"wins": [{"run_id": "r1", "check": 3, "d_score": 2.0, "d_tokens": -5, "d_heartbeats": -100, "diff": "-  nlinarith\n+  omega"}]}
    (ws.root / "notes.md").write_text(NOTES_R2)
    return ws, row, primary


def test_round2_resume_and_escalation_assembly():
    """R3: a plain resume carries LEVER_REVIEW + the heartbeat levers; an escalated (from-reference) session carries the facts sheet instead
    of the notes and diffs, no lever review, the scout brief, and no Lean block over 2 lines from the notes."""
    from harness import prompt_v2 as pv
    with tempfile.TemporaryDirectory() as td:
        ws, row, primary = _ws_r2(pathlib.Path(td))
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws, leads=None, upstream=None, lever_review=True, current_run="r1")
        assert sec[-2:] == ["lever_review", "hb_levers"] and p.endswith(pv.LEVER_REVIEW + pv.LEVER_HB), sec
        assert "WINNING EDITS from earlier runs" in p and "+  omega" in p and "Your notes.md from earlier runs" in p and "FACTS SHEET" not in p
        assert "over 1 earlier run(s)" in p   # the current run (r1) left out of the count (v1 counted it: off by one)
        assert "UNVERIFIED CLAIMS" in p and "The proof is optimal at 300 tokens" in p and "as short as it gets" in p, "v2 claim filter"
        assert "? grind closes" not in p and "grind closes the base case" in p   # no claim word: in the notes, not in the claims
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws, leads=None, upstream=None, lever_review=True, from_reference=True,
                                    facts=True, current_run="r1")
        assert sec == ["header", "facts", "original.lean", "candidate.lean", "cards", "blind_target", "scout", "restructure"], sec
        assert "FACTS SHEET" in p and "stored best, kept unless you beat it: score 61.5" in p and "unsolved goals: 1" in p and "unknown name: 1" in p
        assert "notes, Failed" in p and "notes, Next ideas" in p and "simp only [Finset.card_le]" in p
        assert "[Lean block of 3 lines omitted]" in p and "have h1 := foo" not in p
        assert "+  omega" not in p and "WINNING EDITS: 1 recorded" in p and "Your notes.md" not in p and "LEVER REVIEW" not in p
        assert "Start from candidate.lean (the reference" in p and "it is stored, NOT in candidate.lean" in p


def test_round2_heartbeat_map():
    """R1: the HEARTBEAT MAP from an injected profile (no Lean), placed after candidate.lean, cached per sha with the floor; not shown with < 2 H
    points left; a failing profile never breaks the prompt."""
    from harness import prompt_v2 as pv
    calls = []
    prof = {"ok": True, "total": 9000, "floor": 1000, "reference": 9000, "points_left_heartbeats": 29.63,
            "blocks": [{"lines": "3-3", "heartbeats": 5000, "text": "nlinarith [sq_nonneg x]"}, {"lines": "4-6", "heartbeats": 900, "text": "simp_all"}]}
    hb = lambda n, d: (calls.append(d), prof)[1]
    with tempfile.TemporaryDirectory() as td:
        ws, row, primary = _ws(pathlib.Path(td), "putnam_1964_b2", [], 0)
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws, leads=None, upstream=None, hbmap=hb)
        assert sec[:4] == ["header", "original.lean", "candidate.lean", "heartbeat_map"] and len(calls) == 1, sec
        assert "HEARTBEAT MAP of candidate.lean" in p and "lines 3-3: 5000 hb  nlinarith" in p and "29.63 H points left" in p
        sha = hashlib.sha256((ws.root / "candidate.lean").read_text().rstrip().encode()).hexdigest()[:12]
        assert ws.state["profile_cache"][sha] == prof and ws.state["hb_floor"] == 1000
        assert json.loads((ws.root / "state.json").read_text())["hb_floor"] == 1000   # saved
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws, leads=None, upstream=None, hbmap=hb)
        assert len(calls) == 1 and "heartbeat_map" in sec   # cached per sha: no second profile
        ws.state["profile_cache"] = {}; low = dict(prof, points_left_heartbeats=1.2)
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws, leads=None, upstream=None, hbmap=lambda n, d: low)
        assert "heartbeat_map" not in sec and "HEARTBEAT MAP" not in p
        def boom(*_a):
            raise RuntimeError("no lean here")
        ws.state["profile_cache"] = {}
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws, leads=None, upstream=None, hbmap=boom)
        assert "heartbeat_map" not in sec


def test_round2_run_techniques_block():
    """(c): the RUN TECHNIQUES block from <work root>/_run_techniques.json ("default") or a callable, capped at 1.5k chars, after the leads."""
    from harness import prompt_v2 as pv
    leads = lambda n, d: [{"name": "Foo.bar", "source": "mathlib", "signature": "Foo.bar : True", "why": "x"}]
    with tempfile.TemporaryDirectory() as td:
        ws, row, primary = _ws(pathlib.Path(td), "putnam_1964_b2", [], 0)
        tech = {"patterns": [{"pattern": "simp -> simp only", "problems": 3, "wins": 4, "d_score": 0.8, "d_tokens": 5.0, "d_heartbeats": -310,
                              "example": "- simp / + simp only [_]"}],
                "closer_prices": {"v4.26.0": {"grind": {"median_hb": 231, "n": 5}}}, "ops": [], "notes": ["x" * 290] * 12}
        (pathlib.Path(td) / "_run_techniques.json").write_text(json.dumps(tech))
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws, leads=leads, upstream=None, techniques="default")
        assert sec[-2:] == ["leads", "techniques"] and "RUN TECHNIQUES" in p and "simp -> simp only: 3 problems" in p and "`grind` 231 (n=5)" in p
        block = p[p.index("RUN TECHNIQUES"):]
        assert len(block) <= 1500 and block.endswith("(truncated)"), len(block)
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws, leads=None, upstream=None, techniques=lambda w: "RUN TECHNIQUES\n" + "y" * 4000)
        assert "techniques" in sec and len(p[p.index("RUN TECHNIQUES"):]) == 1500
        (pathlib.Path(td) / "_run_techniques.json").unlink()
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws, leads=None, upstream=None, techniques="default")
        assert "techniques" not in sec


def test_review_prompt_and_block():
    """§11 (2026-10-12): REVIEW_SYSTEM is static (scoring, the lever checklist, token rules, closed lessons, heartbeat prices, the review rules;
    no tool map); the reviewer's task message (the reference, the line-numbered best with its numbers and sha, the axis, the cached heartbeat map
    of the best, the facts, a heartbeat-first or token-first task); review_for() only for the stored best's sha and only for the next executor
    session; the REVIEW block after the lever review, never in a from-reference session; lineage_facts.md right after the digest."""
    from harness import prompt_v2 as pv, cc_levers as LV
    from harness.agent_claude_code import TOOLS_DIR
    from scorer.score import local_reference_heartbeats
    from harness.leantools import HBS
    s = pv.REVIEW_SYSTEM
    assert all(x in s for x in ("fresh-eyes REVIEWER", "a hypothesis the goal never uses", "TOKEN COUNTING", "FIVE HABITS", "HEARTBEAT PRICES",
                                "SMALL-REFERENCE RULE", "REVIEW RULES", "never write that the proof is optimal", "no Lean block longer than 2 lines"))
    assert "TOOL MAP" not in s and "lean_check_variants" not in s and "{" + "tools" not in s and "(2) Test ALL" not in s
    with tempfile.TemporaryDirectory() as td:
        ws, row, primary = _ws_r2(pathlib.Path(td))
        rh = local_reference_heartbeats("putnam_1964_b2") or HBS["putnam_1964_b2"]
        ws.state["best"]["heartbeats"] = rh // 2; ws.state["hb_floor"] = 100   # about 16.6 H points left: heartbeats first
        sha = LV.proof_sha(ws.state["best"]["proof"])
        ws.state["profile_cache"] = {sha: {"ok": True, "total": rh // 2, "floor": 100, "reference": rh, "points_left_heartbeats": 16.6,
                                           "blocks": [{"lines": "3-3", "heartbeats": 5000, "text": "nlinarith [sq_nonneg x]"}]}}
        p, sec, got = pv.build_review_prompt("putnam_1964_b2", row, primary, ws.root, ws.state, gate_usd=0.3)
        assert got == sha and sec == ["header", "best.lean", "axis", "heartbeat_map", "facts", "task"], sec
        assert "about $0.30" in p and "ONE message without tool calls" in p and "original.lean (the REFERENCE proof)" in p
        assert f"sha {sha}" in p and "\n  1| " in p and "HEARTBEAT MAP of best.lean (heartbeat_profile, cached" in p and "lines 3-3: 5000 hb" in p
        assert "AXIS of the best" in p and "against the measured floor 100 hb" in p and "HEARTBEATS FIRST" in p and "work on: heartbeats" in p
        assert "FACTS from this problem's records" in p and "have h1 := foo" not in p and p.rstrip().endswith("Output only the numbered levers.")
        assert "candidate.lean lines" not in p and pv.REVIEW_FORMAT in p
        # review 2026-10-12: heartbeats first without a measured map: the task does not point to a map
        ws.state["profile_cache"] = {}
        p, sec, _ = pv.build_review_prompt("putnam_1964_b2", row, primary, ws.root, ws.state)
        assert "heartbeat_map" not in sec and "HEARTBEATS FIRST" in p and "blocks of the map" not in p and "no map was measured" in p, sec
        # ... and with ws + hbmap the best is profiled first (once), cached under its sha (the next session's map of it), the map shown
        ws.state.pop("hb_floor")   # the profile measures it
        prof = {"ok": True, "total": rh // 2, "floor": 100, "reference": rh, "points_left_heartbeats": 16.6,
                "blocks": [{"lines": "3-3", "heartbeats": 5000, "text": "nlinarith [sq_nonneg x]"}]}
        seen: list = []
        stub = lambda n, d: (seen.append(d), prof)[1]
        p, sec, _ = pv.build_review_prompt("putnam_1964_b2", row, primary, ws.root, ws.state, ws=ws, hbmap=stub)
        assert seen == [ws.state["best"]["proof"].rstrip()] and ws.state["profile_cache"].get(sha) == prof and ws.state.get("hb_floor") == 100
        assert "heartbeat_map" in sec and "blocks of the map" in p and "against the measured floor 100 hb" in p and "lines 3-3: 5000 hb" in p, sec
        pv.build_review_prompt("putnam_1964_b2", row, primary, ws.root, ws.state, ws=ws, hbmap=stub)
        assert len(seen) == 1   # cached: no second profile
        ws.state["best"]["heartbeats"] = 150; ws.state["profile_cache"] = {}   # < 2 H points left: token levers first, no map, no profile
        p, sec, _ = pv.build_review_prompt("putnam_1964_b2", row, primary, ws.root, ws.state, ws=ws, hbmap=stub)
        assert "heartbeat_map" not in sec and "token levers come first" in p and "metered" not in p and len(seen) == 1
        # review_for: the stored best's sha, the next executor session only (the session itself excluded, reviews and skipped entries ignored)
        (ws.root / "review.md").write_text(LV.review_header(sha, "x-v2", "2026-10-12T22:00:00Z", {"levers": 1}) + "\n1. a lever\n")
        ws.state["runs"] = [{"run_id": "x-r1", "started": "2026-10-12T21:00:00Z"}, {"run_id": "x-v2", "kind": "review", "started": "2026-10-12T21:59:00Z"}]
        assert pv.review_for(ws.root, ws.state) == ("1. a lever", sha)
        ws.state["runs"].append({"run_id": "x-r2", "started": "2026-10-12T22:00:05Z"})
        assert pv.review_for(ws.root, ws.state, current_run="x-r2") == ("1. a lever", sha) and pv.review_for(ws.root, ws.state, current_run="x-r3") is None
        ws.state["runs"][-1]["skipped"] = "budget"
        assert pv.review_for(ws.root, ws.state, current_run="x-r3") == ("1. a lever", sha)
        ws.state["runs"][-1].pop("skipped")
        # the order of runs[], not the clock: a session started in the review's last second but listed before it did not use it
        ws.state["runs"][0]["started"] = "2026-10-12T22:00:00Z"
        assert pv.review_for(ws.root, ws.state, current_run="x-r2") == ("1. a lever", sha)
        # without the review's own entry (a review.md from elsewhere): sessions started after it was written
        ws.state["runs"] = [r for r in ws.state["runs"] if r.get("kind") != "review"]
        assert pv.review_for(ws.root, ws.state, current_run="x-r3") is None and pv.review_for(ws.root, ws.state, current_run="x-r2") == ("1. a lever", sha)
        ws.state["runs"] = ws.state["runs"][:1]
        assert pv.review_for(ws.root, dict(ws.state, best=dict(ws.state["best"], proof=ws.state["best"]["proof"] + "\n  -- other"))) is None
        # the REVIEW block: after the lever review and before the extras; never in a from-reference session
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws, leads=None, upstream=None, lever_review=True, review="1. a lever",
                                    review_sha=sha, extras="\n\nEXTRAS")
        assert sec[-4:] == ["lever_review", "hb_levers", "review", "extras"], sec
        assert p.index("HEARTBEAT LEVERS") < p.index("REVIEW (fresh eyes)") < p.index("1. a lever") < p.index("EXTRAS")
        assert f"sha {sha}" in p and "ONE lean_check_variants.py call" in p and f"{TOOLS_DIR}/variants.py N" in p and "{tools}" not in p
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws, leads=None, upstream=None, from_reference=True, review="1. a lever", review_sha=sha)
        assert "review" not in sec and "REVIEW (fresh eyes)" not in p
        (ws.root / "review.md").write_text("1. a review without its header\n")
        assert pv.review_for(ws.root, ws.state) is None
        # hx --claude-fresh-facts: lineage_facts.md right after the digest
        (ws.root / "lineage_facts.md").write_text(LV.FRESH_FACTS_HEAD + "\n- stored best, kept unless you beat it: score 70.0\n")
        p, sec = pv.build_prompt_v2("putnam_1964_b2", row, primary, ws, leads=None, upstream=None)
        assert sec[:2] == ["header", "lineage_facts"] and p.index("the MAIN lineage") < p.index("original.lean (the REFERENCE"), sec


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
    if sys.argv[1:] == ["--fingerprint"]:   # print the v1 fingerprints of the current code (used once to record GOLD)
        from harness import agent_claude_code as _cc
        print(json.dumps(v1_fingerprints(_cc))); raise SystemExit(0)
    raise SystemExit(main())
