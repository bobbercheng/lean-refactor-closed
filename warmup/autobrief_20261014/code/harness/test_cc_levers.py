#!/usr/bin/env python3
"""Unit tests of harness/cc_levers.py (driver v2 round 2, docs/cc_driver_v2.md §9), plain asserts, no Lean, no git, no model.
  axis           R1 math: points left on L and H (floor-based), exchange rate, heartbeat-first at >= 2 H points, agent.py's formula
  progress       R2 counters and the stop rule (8 checks without a new best, none while >= 2 H points are left)
  heartbeat_map  R1 block: shown with >= 2 H points left, from points_left or total/floor/reference, blocks capped
  claims         R5 claim filter: optimal|optimum|near.optimal|as short as; limit claims need a COMPILED [tested: ...]; v1 words unchanged
  notes_digest   R5 head + newest tail within the cap
  lean_blocks    the facts-sheet / leak-lint Lean block rule (fenced and unfenced runs; prose bullets are not code)
  escalate       R3 rule: previous session gain < 0.5 over >= 4 checks, never after a scout, never without best_before/after
  review_*       (2026-10-12, §11) the reviewer's lint (Lean blocks over 2 lines and optimality claims removed, formatting kept, capped),
                 review.md header round trip and proof_sha, the reviewer's facts, the facts sheet's fresh-lineage head
    python3 harness/test_cc_levers.py"""
from __future__ import annotations

import pathlib, sys, traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import cc_levers as LV  # noqa: E402


def test_axis_math():
    a = LV.axis(300, 9000, 150, 4500, floor=900)
    assert a["points_left_length"] == round(150 / 300 * 100 / 3, 2) == 16.67
    assert a["points_left_heartbeats"] == round((4500 - 900) / 9000 * 100 / 3, 2) == 13.33
    assert a["one_token_equals_heartbeats"] == 30.0 and a["points_per_token"] == round(100 / 900, 4) and a["points_per_1k_heartbeats"] == round(100000 / 27000, 3)
    assert a["work_on"] == "heartbeats" and a["heartbeat_floor"] == 900 and "measured against the floor" in a["note"]
    # agent.py:930-934 on the same numbers (the formula is a copy, so the two agree)
    lp = round(150 / 300 * 100 / 3, 2); hp = round(max(0, 4500 - 900) / 9000 * 100 / 3, 2)
    assert (a["points_left_length"], a["points_left_heartbeats"]) == (lp, hp)
    b = LV.axis(300, 9000, 150, 1400, floor=1000)   # 400 hb above the floor: 1.48 points -> tokens
    assert b["points_left_heartbeats"] == 1.48 and b["work_on"] == "tokens" and "heartbeats first" not in b["note"]
    c = LV.axis(300, 9000, 150, 4500)               # no floor: an upper bound, and the note asks for the profiler
    assert c["points_left_heartbeats"] == 16.67 and "heartbeat_profile.py" in c["note"] and c["heartbeat_floor"] is None
    assert LV.axis(300, 9000, 150, 500, floor=900)["points_left_heartbeats"] == 0.0   # below the floor (measurement noise): 0, not negative
    assert LV.axis(0, 9000, 1, 1) is None and LV.axis(300, None, 1, 1) is None and LV.axis(300, 9000, 150, None) is None


def test_progress_stop_rule():
    att = [{"run_id": "old", "ok": True, "score": 50}] + [{"run_id": "r", "ok": True, "score": 55}] + [{"run_id": "r", "ok": k % 2 == 0} for k in range(5)]
    p = LV.progress(att, "r", h_left=0.5)
    assert p["checks_this_session"] == 6 and p["checks_since_new_best"] == 5 and not p["may_finish"] and "5 of 8" in p["stop_rule"]
    att += [{"run_id": "r", "ok": False}] * 3
    p = LV.progress(att, "r", h_left=0.5)
    assert p["checks_since_new_best"] == 8 and p["may_finish"] and "normalize_check" in p["stop_rule"]
    p = LV.progress(att, "r", h_left=2.0)
    assert not p["may_finish"] and "2.0 H points are left" in p["stop_rule"]
    p = LV.progress(att, "r", h_left=None)   # no stored best yet: the 8-check rule alone
    assert p["may_finish"]
    assert LV.progress([], "r")["checks_this_session"] == 0


def test_heartbeat_map():
    prof = {"ok": True, "total": 3000, "floor": 900, "reference": 6000, "blocks": [{"lines": f"{k}-{k}", "heartbeats": 100 * k, "text": "grind"} for k in range(1, 12)]}
    m = LV.heartbeat_map(prof)   # (3000 - 900) / 6000 * 33.3 = 11.67 from total / floor / reference
    assert m.startswith("HEARTBEAT MAP") and "about 11.67 H points left" in m and m.count("\n  lines ") == 8
    assert LV.heartbeat_map(dict(prof, points_left_heartbeats=1.99)) == "" and LV.heartbeat_map(dict(prof, ok=False)) == "" and LV.heartbeat_map(None) == ""
    assert "no block costs measured" in LV.heartbeat_map(dict(prof, blocks=[]))


def test_claim_filter():
    notes = "\n".join([
        "- The proof is optimal at 41 tokens (counted)",                                        # v2 word, untested -> flagged
        "- near-optimal now: 41 tokens [tested: counted on paper -> 41]",                      # limit claim, uncompiled tag -> flagged
        "- this is as short as possible [tested: lean_check variant v3 -> FAIL unknown id]",   # limit claim, compiled tag -> not flagged
        "- grind cannot close the step case [tested: tried it -> unsolved goals]",             # v1 word, any tag -> not flagged (v1 rule)
        "- grind cannot close the step case here at all",                                      # v1 word, untested -> flagged
        "- the statement must stay byte-for-byte identical always",                            # a rule, not a claim
        "- optimum",                                                                           # too short
        "- simp only closes the goal fast and well [tested: lean_check -> OK]"])               # no claim word
    c = LV.unverified_claims_v2(notes)
    assert c == ["The proof is optimal at 41 tokens (counted)", "near-optimal now: 41 tokens [tested: counted on paper -> 41]",
                 "grind cannot close the step case here at all"], c
    from harness.agent import unverified_claims   # v1 misses the optimality claim (deep dive: 0 of 6 flagged)
    assert "The proof is optimal at 41 tokens (counted)" not in unverified_claims(notes)


def test_notes_digest_head_and_tail():
    assert LV.notes_digest("short notes") == "short notes"
    notes = "# Notes\n" + "".join(f"- entry {k:03d} " + "x" * 60 + "\n" for k in range(80)) + "- NEWEST ENTRY: try fun_induction"
    d = LV.notes_digest(notes)
    assert len(d) <= LV.NOTES_CAP and d.startswith("# Notes\n- entry 000") and d.endswith("- NEWEST ENTRY: try fun_induction")
    assert "chars of older notes omitted here" in d and "entry 040" not in d
    assert notes[:3000] != d and "NEWEST" not in notes[:3000]   # v1's notes[:3000] lost the newest entry


def test_lean_blocks():
    fenced = "a note\n```lean\n  simp at h\n  exact h\n  omega\n```\nmore"
    assert LV.lean_block_lines(fenced) == 3 and "[Lean block of 3 lines omitted]" in LV.strip_lean_blocks(fenced)
    two = "```lean\n  simp at h\n  exact h\n```"
    assert LV.lean_block_lines(two) == 2 and LV.strip_lean_blocks(two) == two
    raw = "Failed:\n  rcases h with ⟨a, b⟩\n  · simp_all\n  · exact foo a b\nthen prose"
    assert LV.lean_block_lines(raw) == 3 and "rcases" not in LV.strip_lean_blocks(raw) and "then prose" in LV.strip_lean_blocks(raw)
    prose = "- tried grind -> fails\n  - simp_all is slower here\n  - omega closes the arithmetic"
    assert LV.lean_block_lines(prose) == 0   # nested bullets are prose
    assert LV.lean_block_lines("theorem foo : True := by\n  trivial") == 2
    # round-2 review (2026-10-12): tactics the first list missed, `intros` (no longer cut by \b), and flush-left code once re-indented
    casts = "  intros x y\n  push_cast\n  simp_rw [two_mul]\n  exact_mod_cast hxy\n  norm_cast"
    assert LV.lean_block_lines(casts) == 5 and "[Lean block of 5 lines omitted]" in LV.strip_lean_blocks(casts)
    flush = "this closes it:\nrcases h with ⟨x, hx⟩\nrefine ⟨x, ?_⟩\nsimp at hx\nexact hx.symm"
    assert LV.lean_block_lines(flush) == 0 and LV.lean_block_lines(LV.reindent(flush)) == 4 and LV.lean_lines(LV.reindent(flush)) == 4
    assert LV.lean_lines("  simp at h\nprose in between\n  omega\nmore prose\n  exact h") == 3 and LV.lean_block_lines("  simp at h\nx\n  omega") == 1
    assert not LV.leanish("  rightmost case was slow") and not LV.leanish("  introduce a have first") and LV.leanish("  right")


def test_facts_sheet_cap_and_fences():
    """Round-2 review: over the cap the oldest Failed lines go first, the Next ideas survive, nothing points to notes.md; a fence cut by the
    section slice can no longer swallow the rest of the sheet; flush-left code in the notes is stripped too."""
    st = {"best": {"score": 80.0, "proof": "x", "tokens": 50, "heartbeats": 900, "L": 80, "H": 70, "Z": 100},
          "attempts": [{"ok": False, "error": e} for e in ["unknown identifier 'Foo.bar_baz_qux_long_name_here'", "unsolved goals x y z w",
                                                            "type mismatch h has type", "linarith failed to find a contradiction",
                                                            "unexpected token 'at'; expected command"] * 4]}
    notes = ("## Failed\n" + "\n".join(f"- attempt {k}: replacing the step-case closer by a long chain of rewrites failed because the motive is "
                                       "not type correct [tested: lean_check -> FAIL]" for k in range(14))
             + "\n## Next\n" + "\n".join(f"- idea {k}: try a different induction variable and merge the symmetric cases" for k in range(8)))
    fs = LV.facts_sheet(st, notes)
    assert len(fs) <= LV.FACTS_CAP and "notes, Next ideas" in fs and "idea 7:" in fs and "attempt 13:" in fs and "notes.md for the rest" not in fs, fs[-400:]
    assert "attempt 0:" not in fs   # the oldest Failed lines went first
    # the newest-14 slice starts inside this fence: before the fix its orphan closing ``` ran to the end and swallowed the Next ideas
    cut = "## Failed\n```lean\n  have h := 1\n  simp at h\n```\n" + "".join(f"- f{k} [tested: x -> FAIL]\n" for k in range(13)) + "## Next\n- try fun_induction\n"
    fs = LV.facts_sheet({"best": {}, "attempts": []}, cut)
    assert "try fun_induction" in fs and "- f12" in fs and "```" not in fs and "Lean block" not in fs, fs   # a 2-line fence stays as plain lines
    flush = "## Failed\n- this failed:\nrcases h with ⟨x, hx⟩\nrefine ⟨x, ?_⟩\nsimp at hx\n## Next\n- idea\n"
    fs = LV.facts_sheet({"best": {}, "attempts": []}, flush)
    assert "rcases" not in fs and "[Lean block of 3 lines omitted]" in fs and "- idea" in fs, fs


def test_escalate():
    att = lambda rid, n: [{"run_id": rid}] * n
    r = [{"run_id": "a", "best_before": 50, "best_after": 60}, {"run_id": "b", "best_before": 60, "best_after": 60.3}]
    assert LV.escalate(r, att("b", 6)) and not LV.escalate(r, att("b", 3))   # < 4 checks: no evidence of a plateau
    assert LV.escalate(r) and not LV.escalate(r[:1])
    assert not LV.escalate(r[:1] + [dict(r[1], mode="escalated")]) and not LV.escalate(r[:1] + [dict(r[1], mode="scout")])
    assert not LV.escalate([{"run_id": "v1"}]) and not LV.escalate([])
    assert LV.escalate(r + [{"run_id": "c", "skipped": "budget"}])   # a skipped entry is not a session
    # round-2 review: never on a trailing gate (a from-reference session on ~$0.85 cannot rebuild an L 80+ best); ungated (None) as before
    assert not LV.escalate(r, att("b", 6), gate=0.85) and LV.escalate(r, att("b", 6), gate=LV.ESCALATE_MIN_GATE) and LV.escalate(r, att("b", 6), gate=None)
    # ... and never right after a fresh lineage / rescue (merged into the main state without a runs[] entry); an older one does not count
    rb = r[:1] + [dict(r[1], started="2026-10-12T01:00:00Z", ended="2026-10-12T01:30:00Z")]
    assert not LV.escalate(rb, att("b", 6), fresh=[{"t": "2026-10-12T02:00:00Z", "adopted": True}])
    assert LV.escalate(rb, att("b", 6), fresh=[{"t": "2026-10-12T00:30:00Z"}]) and LV.escalate(rb, att("b", 6), fresh=[])


def test_error_class():
    assert LV.error_class("3:4: unknown identifier 'Foo.bar'") == "unknown name"
    assert LV.error_class("Tactic `rewrite` failed: Did not find an occurrence of the pattern") == "rewrite failed"
    assert LV.error_class("unsolved goals ⊢ a = b") == "unsolved goals" and LV.error_class(None) == "other"
    assert LV.error_class("linarith failed to find a contradiction") == "arith closer failed"


# the reviewer (2026-10-12, docs/cc_driver_v2.md §11)
REVIEW_RAW = ("Here are the levers.\n\n"
              "1. Replace the step-case closer (expected: ~+1.2 score; tokens -3, heartbeats -900)\n"
              "   - location: best.lean lines 4-6 (`simp_all`)\n   - change: `simp only [h, Nat.succ_le]`\n   - why: simp_all costs ~1.4k hb here\n"
              "   - risk: the side goal may stay open\n\n"
              "2. Merge the cases (expected: ~+0.8; tokens -6)\n   - location: lines 7-12\n   - change:\n```lean\n  all_goals omega\n  exact h\n```\n"
              "   - why: the same run twice\n   - risk: none\n\n"
              "3. Full rewrite (expected: ~+3)\n```lean\n  intro x\n  induction x\n  · simp\n  · omega\n```\n"
              "   - risk: low; the risk is minimal\nflush:\nrcases h with ⟨x, hx⟩\nrefine ⟨x, ?_⟩\nsimp at hx\n"
              "The current best is already near-optimal on tokens.\nThis lever is not optimal but cheap, a minimal edit.\n")


def test_review_lint():
    """The saved review: Lean blocks over 2 lines (fenced, indented or flush-left) and optimality claims replaced by markers; a 2-line block,
    inline code, 'not optimal' and 'the risk is minimal' kept; levers counted; capped at a line boundary."""
    body, st = LV.lint_review(REVIEW_RAW)
    assert st == {"levers": 3, "blocks_removed": 2, "claims_removed": 1, "truncated": False}, st
    assert "[Lean block of 4 lines omitted]" in body and "[Lean block of 3 lines omitted]" in body and "induction x" not in body and "rcases" not in body
    assert "  all_goals omega\n  exact h" in body and "`simp only [h, Nat.succ_le]`" in body and LV.CLAIM_MARK in body
    assert "near-optimal" not in body and "This lever is not optimal but cheap, a minimal edit." in body and "the risk is minimal" in body
    assert LV.lean_block_lines(body) <= 2 and LV.lean_block_lines(LV.reindent(body)) <= 2
    assert "   - location: best.lean lines 4-6" in body   # the formatting is kept (no re-indent of the saved text)
    long, st = LV.lint_review("\n".join(f"{k}. lever {k} " + "x" * 80 for k in range(1, 80)))
    assert st["truncated"] and len(long) <= LV.REVIEW_CAP and long.endswith("(review truncated)") and st["levers"] < 79
    for claim in ("it is optimal now", "This proof cannot be shortened further", "as short as possible", "no further gains", "the proof is minimal",
                  # review 2026-10-12: claims about a part of the proof or one axis (any subject before the copula, the LIMIT_RE words)
                  "- note: the token count is essentially optimal; only H can move", "- risk: lines 3-5 are already optimal, leave them",
                  "- why: the simp only list is already minimal", "- why: the heartbeat count is at its floor elsewhere",
                  "- risk: none; everything else is already tight", "it's optimal", "the heartbeats are already at the floor"):
        assert LV.lint_review(f"1. x\n{claim}")[1]["claims_removed"] == 1, claim
    for keep in ("the change is minimal", "this is a minimal edit", "the proof is not optimal yet", "the best is far from optimal",
                 "the bound is tight, so nlinarith needs the hint", "the gain is at minimum 2 points", "   - risk: the side goal may stay open"):
        assert LV.lint_review(f"1. x\n{keep}")[1]["claims_removed"] == 0, keep
    # review 2026-10-12: a Lean block written one inline-code span per bullet or per line counts as a block; one or two such lines stay
    for raw in ("1. x\n   - change:\n     - `induction n with`\n     - `| zero => simp`\n     - `| succ n ih => simp [pow_succ] at *`\n     - `omega`",
                "1. x\n`intro x`\n`simp only [foo] at h`\n`exact h`\n`omega`"):
        body, st = LV.lint_review(raw)
        assert st["blocks_removed"] == 1 and "[Lean block of 4 lines omitted]" in body and "omega" not in body, (st, body)
    body, st = LV.lint_review("1. x\n- `simp only [h]`\n- `omega`\nprose")
    assert st["blocks_removed"] == 0 and "- `omega`" in body, body
    assert LV.lint_review("") == ("", {"levers": 0, "blocks_removed": 0, "claims_removed": 0, "truncated": False})


def test_review_header_and_sha():
    st = {"levers": 3, "blocks_removed": 2, "claims_removed": 1}
    h = LV.review_header("abc123def456", "ab-hx-x-v2", "2026-10-12T22:00:00Z", st)
    meta, body = LV.parse_review(h + "\n1. lever\n")
    assert meta == {"best_sha": "abc123def456", "run": "ab-hx-x-v2", "t": "2026-10-12T22:00:00Z", "levers": "3", "blocks_removed": "2",
                    "claims_removed": "1", "partial": "0"} and body == "1. lever", meta
    assert LV.parse_review("1. a review without its header") is None and LV.parse_review("") is None
    import hashlib
    assert LV.proof_sha("theorem x := by\n  simp\n\n") == LV.proof_sha("theorem x := by\n  simp") == hashlib.sha256(b"theorem x := by\n  simp").hexdigest()[:12]
    assert LV.proof_sha(None) == LV.proof_sha("")


def test_review_facts_and_fresh_head():
    """The reviewer's facts: error classes, last attempts, winning-edit numbers, notes' Failed / Next and unverified claims, executor sessions
    only (reviews not counted), no Lean block over 2 lines, capped; the facts sheet with the fresh-lineage head, otherwise unchanged."""
    st = {"best": {"score": 70.0, "proof": "p", "tokens": 40, "heartbeats": 900},
          "attempts": [{"ok": False, "error": "4:2: unsolved goals ⊢ x", "tokens": 9, "heartbeats": None}] * 2
          + [{"ok": True, "score": 70.0, "tokens": 40, "heartbeats": 900}],
          "runs": [{"run_id": "r1"}, {"run_id": "v2", "kind": "review"}, {"run_id": "r2", "skipped": "budget"}],
          "ledger": {"wins": [{"d_score": 2.0, "d_tokens": -5, "d_heartbeats": -100, "diff": "-  nlinarith\n+  omega"}]}}
    notes = ("# Notes\n## Failed\n- grind in the step case [tested: lean_check -> FAIL]\n```lean\n  have h := 1\n  simp at h\n  exact h\n```\n"
             "## Next\n- try fun_induction\n## Worked\n- The proof is optimal at 40 tokens, counted by hand\n")
    f = LV.review_facts(st, notes)
    assert f.startswith("FACTS from this problem's records (3 checks kept, 1 compiled, 2 failed, over 1 executor session(s))"), f[:200]
    assert "unsolved goals: 2" in f and "tok=40 hb=900 OK score=70.0" in f and "+2.0 / -5 / -100" in f and "nlinarith" not in f
    assert "notes, Failed" in f and "grind in the step case" in f and "notes, Next ideas" in f and "try fun_induction" in f
    assert "UNVERIFIED CLAIMS" in f and "The proof is optimal at 40 tokens" in f and "have h := 1" not in f and LV.lean_block_lines(f) <= 2
    assert len(LV.review_facts(st, notes * 40)) <= LV.REVIEW_FACTS_CAP
    fs = LV.facts_sheet(st, notes, head=LV.FRESH_FACTS_HEAD)
    assert fs.startswith("FACTS SHEET (the MAIN lineage") and fs.split("\n", 1)[1] == LV.facts_sheet(st, notes).split("\n", 1)[1]
    assert LV.facts_sheet(st, notes).startswith(LV.FACTS_HEAD)


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
