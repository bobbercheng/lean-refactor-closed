#!/usr/bin/env python3
"""Unit tests of the failed-move registry (harness/cc_levers.py, 2026-10-13; agent.py / agent_claude_code.py --failed-moves), plain asserts on
synthetic state.json attempts: no Lean, no git, no model.
  abstract       a move's line: identifiers kept (h₁, x.1, Nat.succ_le), string / number literals and whitespace normalized, comments dropped
  move_of        the changed lines against the closer parent (best / reference), signature stable under literal and whitespace changes,
                 different under identifier changes; a pure insertion keyed by its neighbours; no move for no change or a rewrite
  refutes        only positioned Lean diagnostics refute; never ok compiles ('not better'), lean exit / transport / usage-limit errors, timeouts
                 or heartbeat limits, statement / forbidden refusals, a check with no error
  registry       refuted at >= 2 real refutations with the same first error class; reopened when the best changes in the touched lines, kept
                 when it changes elsewhere; a signature that won (ledger) is never listed; text-less attempts group by error head after the
                 newest new best (a ledger dead name: always); a rewrite ({} move) is never grouped by its error alone
  attach_move    the check-path hook: the newest attempt only, and only when it is this text's failed check
  review fixes   (2026-10-13) text-less failures only as UNKNOWN NAMES (lemma-like names, under their own header), stale when the best was
                 adopted without an attempt or the session does not start from it; an insertion that won (anchor-free sig0) or is already in
                 the base is not listed; import / olean / header-line errors and errors above the declaration never refute, the `… in`
                 prefix is read through; touched lines keyed with neighbour and occurrence; a revert does not restore a voided count;
                 one tool call is one refutation; the rows-shown count; agent.py's two sites (source order)
  block          the REFUTED MOVES block: header, most refuted first, <= 1,200 chars with a 'more not shown' line, no Lean block over 2 lines
  prompts        build_prompt_v2(failed_moves=True) adds the block after the inline files (section 'failed_moves'); False and an empty
                 registry leave the prompt byte-identical; agent.py / agent_claude_code.py parse --failed-moves, default off
    python3 harness/test_failed_moves.py"""
from __future__ import annotations

import hashlib, pathlib, re, subprocess, sys, tempfile, traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import cc_levers as LV  # noqa: E402

STMT = "theorem foo (n : Nat) (h : 0 < n) : n ≠ 0 := by"
BEST = "\n".join([STMT, "  intro h0", "  subst h0", "  simp at h", "  exact absurd h (by decide)"])
REF = "\n".join([STMT, "  have h1 : n ≠ 0 := by", "    intro h0", "    subst h0", "    simp at h", "  exact h1"])


def sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()[:12]


def att(text: str | None, error: str | None, t: str, ok: bool = False, score=None, run="r1", parents=None, **kw) -> dict:
    a = {"sha": sha(text or t), "tokens": 10, "heartbeats": None if not ok else 100, "ok": ok, "error": error, "run_id": run, "t": t, **kw}
    if score is not None:
        a["score"] = score
    if text is not None and not ok:
        a["move"] = LV.move_of(parents or [("best", BEST), ("ref", REF)], text) or {}
    return a


def edit(base: str, old: str, new: str) -> str:
    assert old in base, old
    return base.replace(old, new, 1)


def ck(text: str, line: str, k: int = 0) -> str:
    """The touch key of the k-th line of `text` whose code is `line` (keys carry the previous line and the occurrence, review 2026-10-13)."""
    ls = LV._lines(text); keys = LV._ckeys(ls)
    return [keys[i] for i, l in enumerate(ls) if LV._code(l) == LV._code(line)][k]


E_UNK = "4:2: unknown identifier 'Nat.foo_bar'"
E_TM = "3:8: type mismatch h has type 0 < n but is expected to have type False"


# ---- abstract / move_of -----------------------------------------------------------------------------------------------------------------
def test_abstract():
    assert LV.abstract_code("  simp   [Nat.succ_le, h₁]  at h  -- note") == "simp [Nat.succ_le, h₁] at h"
    assert LV.abstract_code("exact h 0 (by norm_num : (2:ℝ) ≤ 3.5)") == "exact h # (by norm_num : (#:ℝ) ≤ #)"
    assert LV.abstract_code('simp [show "ab" = "cd" from rfl]') == 'simp [show "_" = "_" from rfl]'
    assert LV.abstract_code("exact ⟨x.1, h2, pow_two x, x₁⟩") == "exact ⟨x.1, h2, pow_two x, x₁⟩"   # projections / names with digits kept


def test_move_replace_signature():
    c1 = edit(BEST, "  simp at h", "  omega")
    m = LV.move_of([("best", BEST), ("ref", REF)], c1)
    assert m and m["par"] == "best" and m["show"] == "replace `simp at h` with `omega`", m
    assert m["touch"] == [ck(BEST, "simp at h")] and m["sig0"] == m["sig"] and "seq" not in m
    # same move with other whitespace / a comment: same signature; literals normalized
    assert LV.move_of([("best", BEST)], edit(BEST, "  simp at h", "    omega   -- try"))["sig"] == m["sig"]
    a = LV.move_of([("best", BEST)], edit(BEST, "  exact absurd h (by decide)", "  exact absurd h (Nat.lt_irrefl 0)"))
    b = LV.move_of([("best", BEST)], edit(BEST, "  exact absurd h (by decide)", "  exact absurd h (Nat.lt_irrefl 1)"))
    assert a["sig"] == b["sig"] and a["show"] != b["show"]
    # an identifier change is another move
    c = LV.move_of([("best", BEST)], edit(BEST, "  exact absurd h (by decide)", "  exact absurd h (Nat.lt_asymm 0)"))
    assert c["sig"] != a["sig"]
    # the same edit in another place is another move (the removed line differs)
    assert LV.move_of([("best", BEST)], edit(BEST, "  subst h0", "  omega"))["sig"] != m["sig"]


def test_move_parent_choice_insert_delete_rewrite():
    # an edit of the reference is measured against the reference, not the (distant) best
    r1 = edit(REF, "    simp at h", "    omega")
    m = LV.move_of([("best", BEST), ("ref", REF)], r1)
    assert m["par"] == "ref" and m["show"] == "replace `simp at h` with `omega`"
    # pure insertion: keyed by its neighbours, shown with the line before it
    ins = edit(BEST, "  subst h0\n", "  subst h0\n  norm_num\n")
    mi = LV.move_of([("best", BEST)], ins)
    assert mi["show"] == "insert `norm_num` after `subst h0`" and set(mi["touch"]) == {ck(BEST, "subst h0"), ck(BEST, "simp at h")}
    assert mi["sig0"] != mi["sig"] and mi["seq"] == [LV._lkey("subst h0"), LV._lkey("norm_num")]
    ins2 = edit(BEST, "  simp at h\n", "  simp at h\n  norm_num\n")
    assert LV.move_of([("best", BEST)], ins2)["sig"] != mi["sig"]
    assert LV.move_of([("best", BEST)], ins2)["sig0"] == mi["sig0"]   # the same insertion elsewhere: one anchor-free signature (ledger match)
    # deletion
    md = LV.move_of([("best", BEST)], edit(BEST, "  subst h0\n", ""))
    assert md["show"] == "delete `subst h0`" and md["touch"] == [ck(BEST, "subst h0")] and "seq" not in md
    # no change, no parent, a rewrite
    assert LV.move_of([("best", BEST)], BEST + "\n\n") is None
    assert LV.move_of([("best", None), ("ref", "")], BEST) is None
    rw = "\n".join([STMT, "  omega"])
    assert LV.move_of([("best", BEST), ("ref", REF)], rw) is None
    long_best = "\n".join([STMT] + [f"  have h{k} : n + {k} > 0 := by omega" for k in range(30)] + ["  omega"])
    big = long_best.replace(" := by omega", " := by positivity")   # 30 lines changed: over FM_MAX_LINES
    assert LV.move_of([("best", long_best)], big) is None
    # long lines are cut in the display, backticks never break the inline span
    lng = edit(BEST, "  simp at h", "  simp [" + ", ".join(f"Nat.lemma_{k}" for k in range(20)) + "] at `h")
    s = LV.move_of([("best", BEST)], lng)["show"]
    assert "…`" in s and s.count("`") == 4, s


# ---- refutes ----------------------------------------------------------------------------------------------------------------------------
def test_refutes():
    yes = [E_UNK, E_TM, "12:4: unsolved goals … [hypotheses omitted] ⊢ n ≠ 0", "line 3 `simp at h`, col 2: simp made no progress",
           "7:0: declaration uses 'sorry'"]
    no = [None, "", "lean exit 137: Killed", "lean exit 1: memgate: not enough memory",
          "5:2: (deterministic) timeout at `whnf`, maximum number of heartbeats (200000) has been reached",
          "error: timed out after 300s", "API error: rate limit (429)", "usage limit reached", "statement differs from the reference statement",
          "forbidden construct: native_decide"]
    for e in yes:
        assert LV.refutes({"ok": False, "error": e}), e
    for e in no:
        assert not LV.refutes({"ok": False, "error": e}), e
    assert not LV.refutes({"ok": True, "error": None, "score": None})            # a compile that was not better is no refutation
    assert not LV.refutes({"ok": True, "error": E_UNK})


# ---- registry ---------------------------------------------------------------------------------------------------------------------------
def _st(attempts, best=BEST, ledger=None) -> dict:
    return {"best": {"score": 70.0, "proof": best, "tokens": 20, "heartbeats": 500}, "attempts": attempts, "runs": [], **({"ledger": ledger} if ledger else {})}


def test_registry_threshold_and_classes():
    c1 = edit(BEST, "  exact absurd h (by decide)", "  exact absurd h (Nat.foo_bar 0)")
    c2 = edit(BEST, "  exact absurd h (by decide)", "  exact   absurd h (Nat.foo_bar 1)")   # same move: literal / whitespace differ
    c3 = edit(BEST, "  exact absurd h (by decide)", "  exact absurd h (Nat.foo_bar 2)")
    one = _st([att(c1, E_UNK, "2026-10-13T01:00:00Z")])
    assert LV.registry(one) == [] and LV.failed_moves_block(one) == ""
    two = _st([att(c1, E_UNK, "2026-10-13T01:00:00Z"), att(c2, E_UNK, "2026-10-13T01:05:00Z")])
    reg = LV.registry(two)
    assert len(reg) == 1 and reg[0]["n"] == 2 and reg[0]["cls"] == "unknown name" and reg[0]["kind"] == "move"
    assert reg[0]["show"] == "replace `exact absurd h (by decide)` with `exact absurd h (Nat.foo_bar 1)`"   # the newest example
    assert reg[0]["err"] == "unknown identifier 'Nat.foo_bar'"
    # the same move failing with another first error class is a separate group (1 + 1: not refuted)
    mixed = _st([att(c1, E_UNK, "2026-10-13T01:00:00Z"), att(c2, E_TM, "2026-10-13T01:05:00Z")])
    assert LV.registry(mixed) == []
    # not-better compiles, transport / process errors and timeouts never count
    noise = _st([att(c1, E_UNK, "2026-10-13T01:00:00Z"), att(c3, "lean exit 137: Killed", "2026-10-13T01:01:00Z"),
                 att(c3 + " ", "5:2: (deterministic) timeout at `whnf`, maximum number of heartbeats (200000) has been reached", "2026-10-13T01:02:00Z"),
                 {**att(c2, None, "2026-10-13T01:03:00Z", ok=True), "move": LV.move_of([("best", BEST)], c2)}])
    assert LV.registry(noise) == []
    assert len(LV.registry(two, min_refute=3)) == 0


def test_registry_reopen_on_best_change():
    c1 = edit(BEST, "  simp at h", "  omega"); c2 = edit(BEST, "  simp at h", "  omega  ")
    c2 = edit(c2, "  intro h0", "  intro h0 ")   # whitespace only elsewhere: still the same move
    a = [att(c1, "4:2: omega could not prove the goal", "2026-10-13T01:00:00Z"), att(c2, "4:2: omega could not prove the goal", "2026-10-13T01:05:00Z")]
    assert len(LV.registry(_st(a))) == 1 and LV.registry(_st(a))[0]["cls"] == "arith closer failed"
    # the best changed in the touched line: reopened (not listed)
    nb = edit(BEST, "  simp at h", "  simp only [Nat.lt_irrefl] at h")
    assert LV.registry(_st(a, best=nb)) == []
    # the best changed elsewhere: still refuted
    nb2 = edit(BEST, "  exact absurd h (by decide)", "  exact absurd h (by omega)")
    assert len(LV.registry(_st(a, best=nb2))) == 1
    # a literal change in the touched line also reopens (touch keys are the exact line)
    a3 = [att(edit(BEST, "  exact absurd h (by decide)", "  exact h.ne' (by rfl)"), E_TM, f"2026-10-13T01:0{k}:00Z") for k in range(2)]
    a3[1]["sha"] = "other"
    assert len(LV.registry(_st(a3))) == 1
    assert LV.registry(_st(a3, best=edit(BEST, "(by decide)", "(by decide : 0 < 1)"))) == []
    # the base is the session's candidate when given (a from-reference session: the reference's lines)
    r1 = edit(REF, "    simp at h", "    omega")
    ar = [att(r1, "5:4: omega could not prove the goal", f"2026-10-13T02:0{k}:00Z") for k in range(2)]
    ar[1]["sha"] = "x2"
    assert len(LV.registry(_st(ar), base=REF)) == 1 and len(LV.registry(_st(ar))) == 1   # `simp at h` is in both texts
    assert LV.registry(_st(ar), base="\n".join([STMT, "  omega"])) == []


def test_registry_ledger_wins_and_textless():
    c1 = edit(BEST, "  subst h0", "  cases h0"); c2 = edit(BEST, "  subst h0", "  cases  h0")
    a = [att(c1, E_TM, "2026-10-13T01:00:00Z"), att(c2, E_TM, "2026-10-13T01:05:00Z")]
    assert len(LV.registry(_st(a))) == 1
    won = {"wins": [{"run_id": "r0", "d_score": 1.2, "diff": "-  subst h0\n+  cases h0"}]}   # this very edit won somewhere: never refuted
    assert LV.registry(_st(a, ledger=won)) == []
    # a ledger win of an insertion matches without the insertion's neighbours (review 2026-10-13 finding 3; a win diff has no anchors)
    ins = [att(edit(BEST, "  subst h0\n", "  subst h0\n  norm_num at h\n"), E_TM, f"2026-10-13T01:1{k}:00Z") for k in range(2)]
    ins[1]["sha"] = "i2"
    assert len(LV.registry(_st(ins))) == 1
    assert LV.registry(_st(ins, ledger={"wins": [{"diff": "+  norm_num at h", "d_score": 0.4}]})) == []
    # text-less attempts (older records / a check path without the hook): grouped by error head, after the newest new best only
    tl = [BEST_AT, att(None, "4:2: unknown identifier 'Nat.foo'", "2026-10-13T01:00:00Z"), att(None, "9:6: unknown identifier 'Nat.foo'", "2026-10-13T01:01:00Z")]
    tl[2]["sha"] = "b"
    reg = LV.registry(_st(tl))
    assert len(reg) == 1 and reg[0]["kind"] == "error" and reg[0]["n"] == 2 and reg[0]["err"] == "unknown identifier 'Nat.foo'"
    newer_best = tl + [att(None, None, "2026-10-13T01:30:00Z", ok=True, score=72.0)]
    newer_best[-1]["sha"] = "c"
    assert LV.registry(_st(newer_best)) == []
    # ... unless the error names a ledger dead name (the environment does not change)
    assert len(LV.registry(_st(newer_best, ledger={"dead_names": ["Nat.foo"]}))) == 1
    assert LV.registry(_st(newer_best, ledger={"dead_names": ["Nat.fo"]})) == []
    # a rewrite (move {}) is never grouped by its error alone
    rw = [tl[0]] + [dict(x, move={}) for x in tl[1:]]
    assert LV.registry(_st(rw)) == []
    # moves rank before text-less errors; the most refuted first within each
    mix = a + tl + [att(edit(BEST, "  subst h0", "  cases   h0"), E_TM, "2026-10-13T01:06:00Z")]
    mix[-1]["sha"] = "d"
    r = LV.registry(_st(mix))
    assert [g["kind"] for g in r] == ["move", "error"] and r[0]["n"] == 3 and r[0]["calls"] == 3


BEST_AT = {"sha": sha(BEST), "tokens": 20, "heartbeats": 500, "ok": True, "error": None, "run_id": "r0", "t": "2026-10-13T00:30:00Z", "score": 70.0}


def test_textless_only_names():
    """Review 2026-10-13 finding 1: a generic error head (unsolved goals, linarith failed) merges unrelated edits: only names are listed, under
    their own header (no claim about edited lines)."""
    def two(e1, e2):
        x = [BEST_AT, att(None, e1, "2026-10-13T01:00:00Z"), att(None, e2, "2026-10-13T01:01:00Z"), att(None, e2, "2026-10-13T01:02:00Z")]
        x[2]["sha"], x[3]["sha"] = "b", "c"
        return _st(x)
    assert LV.registry(two("12:4: unsolved goals case succ … ⊢ False", "15:2: unsolved goals case succ … ⊢ False")) == []
    assert LV.registry(two("7:2: linarith failed to find a contradiction", "9:2: linarith failed to find a contradiction")) == []
    assert LV.registry(two("7:2: unknown identifier 'h₁'", "9:2: unknown identifier 'h₁'")) == []          # a local hypothesis: the candidate
    assert len(LV.registry(two("7:2: unknown identifier 'sq_nonneg''", "9:2: unknown identifier 'sq_nonneg''"))) == 1   # a lemma name
    assert len(LV.registry(two("7:2: unknown constant 'Foo'", "9:2: unknown constant 'Foo'"))) == 1
    st = two("7:2: unknown identifier 'Real.foo_le'", "9:2: unknown identifier 'Real.foo_le'")
    blk, n = LV.failed_moves_render(st)
    assert n == 1 and blk.startswith("UNKNOWN NAMES") and "REFUTED MOVES" not in blk and "candidate.lean" not in blk
    assert blk.split("\n")[1] == "- 3x unknown identifier 'Real.foo_le'", blk
    # with a refuted move too: the move under REFUTED MOVES first, then the names under their header
    st["attempts"] += [att(edit(BEST, "  subst h0", "  cases h0"), E_TM, f"2026-10-13T01:1{k}:00Z") for k in range(2)]
    st["attempts"][-1]["sha"] = "m2"
    blk, n = LV.failed_moves_render(st)
    ls = blk.split("\n")
    assert n == 2 and ls[0].startswith("REFUTED MOVES") and ls[1].startswith("- 2x [type mismatch] replace `subst h0`") and ls[2].startswith("UNKNOWN NAMES")


def test_textless_stale_best():
    """Review 2026-10-13 finding 2: a best adopted without an attempt here (hx merge_fresh_state, a relay) or a session that does not start from
    the stored best makes the error-only entries stale; a ledger dead name stays."""
    errs = [att(None, "4:2: unknown identifier 'Nat.foo'", "2026-10-13T01:00:00Z"), att(None, "9:6: unknown identifier 'Nat.foo'", "2026-10-13T01:01:00Z")]
    errs[1]["sha"] = "b"
    nb = edit(BEST, "  simp at h", "  simp only [Nat.pos_iff_ne_zero] at h")
    assert LV.registry(_st(errs, best=nb)) == []                                     # the stored best is not among the attempts: unknown epoch
    assert len(LV.registry(_st(errs, best=nb, ledger={"dead_names": ["Nat.foo"]}))) == 1
    late = {**_st(errs, best=nb), "fresh_lineages": [{"run_id": "f1", "adopted": True, "t": "2026-10-13T02:00:00Z"}]}
    assert LV.registry(late) == []                                                   # adopted after the errors
    early = {**_st(errs, best=nb), "fresh_lineages": [{"run_id": "f1", "adopted": True, "t": "2026-10-13T00:50:00Z"},
                                                      {"run_id": "f2", "adopted": False, "t": "2026-10-13T03:00:00Z"}]}
    assert len(LV.registry(early)) == 1                                              # adopted before them (a lineage not adopted: no epoch)
    st = _st([BEST_AT] + errs)
    assert len(LV.registry(st)) == 1 and len(LV.registry(st, base=BEST + "\n\n")) == 1
    assert LV.registry(st, base=REF) == []                                           # a from-reference session / a relay seed
    never = _st(errs, best=None); never["best"]["proof"] = None                     # never improved: the session starts from the reference
    assert len(LV.registry(never, base=REF)) == 1


def test_insertion_applied_and_env():
    """Review 2026-10-13 findings 3, 4, 7: an insertion the base already holds is not refuted (here at the end, where no neighbour after it
    changes); import / olean failures and errors above the declaration never refute; the `… in` modifier prefix is read through."""
    ins = edit(BEST, "  exact absurd h (by decide)", "  exact absurd h (by decide)\n  rfl")
    a = [att(ins, E_TM, f"2026-10-13T01:0{k}:00Z") for k in range(2)]
    a[1]["sha"] = "x"
    assert len(LV.registry(_st(a))) == 1 and LV.registry(_st(a, best=ins)) == []
    for e in ("1:0: object file /x/.lake/build/lib/Mathlib/Foo.olean of module Mathlib.Foo does not exist",
              "1:0: unknown module prefix 'Mathlib'", "3:0: unknown package 'Foo'", "1:7: unexpected token 'at'"):
        assert not LV.refutes({"ok": False, "error": e}), e
    mod = "(with the preceding `… in` modifier applied to the declaration, as in the file) 12:4: unknown identifier 'Nat.foo'"
    assert LV.refutes({"ok": False, "error": mod}) and LV._err_head(mod) == "unknown identifier 'Nat.foo'"
    assert not LV.refutes({"ok": False, "error": E_UNK, "move": {"sig": "s", "eline": 0}})
    assert LV.refutes({"ok": False, "error": E_UNK, "move": {"sig": "s", "eline": 3}})
    assert LV.error_line("23:4: unknown identifier 'x'", 20) == 3 and LV.error_line(mod, 20) is None and LV.error_line(None, 20) is None


def test_reopen_precise_and_revert():
    """Review 2026-10-13 finding 5: a change of the other copy of a repeated line keeps the move, a change of its own copy reopens it; a move
    reopened by a best change stays open when the best later reverts (void_stale on the check path); reference moves are never voided."""
    b2 = "\n".join([STMT, "  constructor", "  · simp", "    omega", "  · norm_num", "    omega"])
    mv = edit(b2, "  · norm_num\n    omega", "  · norm_num\n    linarith")
    a = [att(mv, "6:4: linarith failed", f"2026-10-13T01:0{k}:00Z", parents=[("best", b2)]) for k in range(2)]
    a[1]["sha"] = "y"
    assert len(LV.registry(_st(a, best=b2))) == 1
    other = edit(b2, "  · simp\n    omega", "  · simp\n    positivity")
    assert len(LV.registry(_st(a, best=other))) == 1                                # the other `omega` changed: still refuted
    own = edit(b2, "  · norm_num\n    omega", "  · norm_num\n    nlinarith [h]")
    assert LV.registry(_st(a, best=own)) == []                                      # its own copy changed: open (content keys missed this)
    # revert: a check against the changed best voids the move, a best restoring the line does not bring the count back
    st = _st(a, best=b2)
    ref_move = att(edit(REF, "    simp at h", "    omega"), "5:4: omega could not prove the goal", "2026-10-13T01:05:00Z")
    st["attempts"].append(ref_move)
    m = LV.record_move(st, [("best", own), ("ref", REF)], edit(own, "  · simp", "  · simp_all"), call="r2:7", eline=2)
    assert m["call"] == "r2:7" and m["eline"] == 2 and all(x["move"].get("void") for x in st["attempts"][:2])
    assert ref_move["move"]["par"] == "ref" and not ref_move["move"].get("void")
    assert LV.registry(st, base=b2) == []
    assert LV.void_stale(st, None) == 0 and LV.void_stale(st, b2) == 0


def test_one_call_one_refutation():
    """Review 2026-10-13 finding 8: literals are normalized, so two literal variants of one lean_check_variants batch are one refutation."""
    c1 = edit(BEST, "  exact absurd h (by decide)", "  exact absurd h (Nat.foo_bar 0)")
    c2 = edit(BEST, "  exact absurd h (by decide)", "  exact absurd h (Nat.foo_bar 1)")
    a = [att(c1, E_UNK, "2026-10-13T01:00:00Z"), att(c2, E_UNK, "2026-10-13T01:00:01Z")]
    for x in a:
        x["move"]["call"] = "r1:4"
    assert LV.registry(_st(a)) == []
    a.append(att(edit(BEST, "  exact absurd h (by decide)", "  exact absurd h (Nat.foo_bar 2)"), E_UNK, "2026-10-13T01:03:00Z"))
    a[-1]["move"]["call"] = "r1:6"
    reg = LV.registry(_st(a))
    assert len(reg) == 1 and reg[0]["n"] == 3 and reg[0]["calls"] == 2 and LV.failed_moves_render(_st(a))[0].count("\n- 3x [unknown name]") == 1


def test_attach_move():
    c1 = edit(BEST, "  simp at h", "  omega")
    st = _st([att(None, None, "2026-10-13T01:00:00Z", ok=True, score=70.0)])
    st["attempts"][0]["sha"] = "older"
    # a refusal before compiling records no attempt: the older attempt is left alone
    assert not LV.attach_move(st, [("best", BEST)], c1) and "move" not in st["attempts"][0]
    st["attempts"].append({"sha": sha(c1 + "\n"), "ok": False, "error": E_TM, "t": "2026-10-13T01:01:00Z"})   # leantools hashes the text as given
    assert LV.attach_move(st, [("best", BEST), ("ref", REF)], c1 + "\n") and st["attempts"][-1]["move"]["show"] == "replace `simp at h` with `omega`"
    assert not LV.attach_move(st, [("best", BEST)], c1 + "\n")   # already attached
    st["attempts"].append({"sha": sha(c1.rstrip()), "ok": False, "error": E_TM})   # agent.py hashes the stripped text
    assert LV.attach_move(st, [("best", BEST)], c1 + "\n\n")
    st["attempts"].append({"sha": sha("x"), "ok": True})
    assert not LV.attach_move(st, [("best", BEST)], "x")   # a compiling check gets no move
    st["attempts"].append({"sha": sha("\n".join([STMT, "  omega"])), "ok": False, "error": E_TM})
    assert not LV.attach_move(st, [("best", BEST)], "\n".join([STMT, "  omega"])) and st["attempts"][-1]["move"] == {}   # a rewrite


# ---- the block --------------------------------------------------------------------------------------------------------------------------
def test_block_cap_and_lint():
    long_best = "\n".join([STMT] + [f"  have h{k} : n + {k} > 0 := by simp [Nat.add_pos_left, Nat.succ_pos, Nat.lt_irrefl, h]" for k in range(40)] + ["  omega"])
    at = []
    for k in range(40):
        old = f"  have h{k} : n + {k} > 0 := by simp [Nat.add_pos_left, Nat.succ_pos, Nat.lt_irrefl, h]"
        for j in range(2 + (k % 3)):
            t = edit(long_best, old, old.replace("by simp", "by grind") + " " * j)
            a = att(t, f"{k + 2}:20: grind failed to prove the goal and here is a long tail " + "x" * 200, f"2026-10-13T{k % 24:02d}:{j:02d}:00Z",
                    parents=[("best", long_best)])
            a["sha"] = f"{k}-{j}"; at.append(a)
    st = _st(at, best=long_best)
    blk = LV.failed_moves_block(st)
    assert blk.startswith("REFUTED MOVES (do not retry without a new reason") and "at least 2 separate checks" in blk
    txt, n = LV.failed_moves_render(st)
    assert txt == blk and n == len(re.findall(r"(?m)^- \d+x ", blk)) and 0 < n < len(LV.registry(st))   # the count is the rows shown
    assert len(blk) <= LV.FM_CAP and re.search(r"^- \(\d+ more not shown\)$", blk, re.M), blk[-200:]
    assert LV.lean_block_lines(blk) <= 2 and LV.strip_lean_blocks(blk) == blk
    rows = [l for l in blk.split("\n")[1:] if l.startswith("- ") and "more not shown" not in l]
    assert rows and all(l.startswith("- 4x [") for l in rows[:3]), rows[:3]   # the most refuted first
    assert all(len(l) <= LV.FACTS_LINE + 60 for l in rows)
    assert LV.failed_moves_block(_st([])) == ""


# ---- prompts and flags ------------------------------------------------------------------------------------------------------------------
def test_prompt_v2_block_and_identity():
    from harness import prompt_v2 as pv
    from harness.agent import Workspace
    from harness.leantools import ROWS
    from probe.verify_candidates import newest_first
    name = "putnam_1964_b2"; row = ROWS[name]; primary = newest_first(row["version_info"])[0]
    with tempfile.TemporaryDirectory() as td:
        ws = Workspace(pathlib.Path(td) / name, row, primary, fresh=True)   # putnambench: no Lean environment is touched
        src = row["src"].rstrip()
        ws.state["best"] = {"score": 61.5, "proof": src, "tokens": 300, "heartbeats": 9000}
        kw = dict(leads=None, upstream=None, lever_review=True, current_run="r2")
        p0, s0 = pv.build_prompt_v2(name, row, primary, ws, **kw)
        p1, s1 = pv.build_prompt_v2(name, row, primary, ws, failed_moves=True, **kw)   # nothing refuted: byte-identical
        assert (p0, s0) == (p1, s1)
        c = edit(src, "    exact Set.nonempty_iff_ne_empty.mpr h₁", "    exact Set.nonempty_of_ne_empty h₁")
        for k in range(2):
            ws.state["attempts"].append({"sha": f"s{k}", "ok": False, "error": f"{12 + k}:10: unknown constant 'Set.nonempty_of_ne_empty'",
                                         "run_id": "r1", "t": f"2026-10-13T01:0{k}:00Z",
                                         "move": LV.move_of([("best", src), ("ref", row["src"])], c + " " * k)})
        p2, s2 = pv.build_prompt_v2(name, row, primary, ws, failed_moves=True, **kw)
        p3, s3 = pv.build_prompt_v2(name, row, primary, ws, **kw)
        assert "failed_moves" in s2 and "failed_moves" not in s3 and "REFUTED MOVES" not in p3
        assert s2.index("failed_moves") == s2.index("candidate.lean") + 1
        blk = LV.failed_moves_block(ws.state, base=(ws.root / "candidate.lean").read_text())
        assert blk and blk in p2 and p2.replace("\n\n" + blk, "", 1) == p3
        assert "2x [unknown name] replace `exact Set.nonempty_iff_ne_empty.mpr h₁` with `exact Set.nonempty_of_ne_empty h₁`" in blk
        assert p2.index("candidate.lean (your current best)") < p2.index("REFUTED MOVES") < p2.index("TECHNIQUE CARDS")


def test_flags_default_off():
    src = (ROOT / "harness/agent.py").read_text()
    assert re.search(r'add_argument\("--failed-moves", action="store_true"', src)
    assert 'getattr(args, "failed_moves", False)' in src
    cc = (ROOT / "harness/agent_claude_code.py").read_text()
    assert re.search(r'add_argument\("--failed-moves", action="store_true"', cc)
    # v1 / the reviewer refuse it (argparse error before anything runs: no claude, no Lean)
    for extra in (["--failed-moves"], ["--prompt", "v2", "--review", "--failed-moves"]):
        r = subprocess.run([sys.executable, str(ROOT / "harness/agent_claude_code.py"), "--problems", "x", *extra], capture_output=True, text=True,
                           timeout=120)
        assert r.returncode == 2 and "--failed-moves needs --prompt v2" in r.stderr, (extra, r.stderr[-300:])


def test_agent_wiring():
    """Review 2026-10-13 finding 9 (agent.py's run loop needs Lean and a model, so its two sites are checked in the source): the failed check's
    move goes into the attempt record before it is appended, only under the flag, with the tool call and the error line; the opening block is
    built after the from-reference / fresh-start resets of candidate.lean, from candidate.lean, and records the rows shown."""
    src = (ROOT / "harness/agent.py").read_text()
    i_rec = src.index('_rec = {"sha": sha, "tokens": toks')
    i_flag = src.index('if not r.ok and getattr(args, "failed_moves", False):', i_rec)
    i_move = src.index("_LVfm.record_move(ws.state, [(\"best\", best.get(\"proof\")), (\"ref\", row[\"src\"])], decl, call=f\"{args.run_id}:{tool_calls}\"", i_flag)
    i_app = src.index("ws.record_attempt(_rec)", i_rec)
    assert i_rec < i_flag < i_move < i_app and "eline=_LVfm.error_line(r.errors[0]" in src[i_move:i_app]
    resets = [m.start() for m in re.finditer(r'\(ws\.root / "candidate\.lean"\)\.write_text\(row\["src"\]\.rstrip\(\) \+ "\\n"\)', src)]
    i_open = src.index("_LVfm.failed_moves_render(ws.state, base=_fm_base)")
    i_free = src.index("# free deletions first")
    assert len(resets) >= 2 and max(resets) < i_open < i_free, (resets, i_open, i_free)
    assert max(resets) < src.index('_LVfm.void_stale(ws.state, ws.state["best"].get("proof"))') < i_open   # a best seen at the start voids too
    assert '_fm, ws.state["runs"][-1]["failed_moves"] = _LVfm.failed_moves_render' in src and 'msgs[0]["content"] += "\\n\\n" + _fm' in src[i_open:i_free]
    cc = (ROOT / "harness/agent_claude_code.py").read_text()
    assert "cc_levers.failed_moves_render(ws.state, base=_fmb)[1]" in cc and 'else (ws.state["best"].get("proof") or row["src"])' in cc
    assert cc.index('cc_levers.void_stale(ws.state, ws.state["best"].get("proof"))') < cc.index("prompt, sections = pv.build_prompt_v2(")


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
