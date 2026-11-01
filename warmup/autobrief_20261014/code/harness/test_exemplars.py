#!/usr/bin/env python3
"""Unit tests of harness/exemplars.py (exemplar transfer from the strongest rows, docs/cc_driver_v2.md §13), plain asserts, no Lean, no model, no
claude: fixture work roots and run dirs in temp directories (warm-up names for their statements only), and a read-only dry run on the warm-up
root (harness/work with probe/runs/agent-flash-*, the Opus line harness/work_ccline-opus55 with probe/runs/ccline-opus55-p*).
  features       tactic families with the scorer's lexer (simp only / grind only apart from simp / grind, exact?, the grouped families), rates
                 per 100 tokens, heartbeats per token, term mode; tactic lines without the `by` opener
  jumps          a line's chain from the reference: the first change (against the local reference heartbeats; an edit when its diff is small,
                 flagged first), a lower record skipped, a remeasured same body no jump, an edit, a later rewrite; lines kept apart; run dirs in
                 hx round order or natural glob order; records of problems without a workspace skipped
  contrast       within-problem effects (other problems' edits only; heartbeats, or tokens on the L axis); a family listed only when this row
                 uses more than the strong pool AND its removal beat adding it (or every edit); never a family it uses less; hot families
                 restrict the candidates; counts for a short best; same-source pool with >= MIN_SAME rows else every source, never the row's
                 own problem from any line
  hot            the stored best's own profile only, the families of the best's lines (not the excerpt), leaf blocks; HOT_CAP; no block text
  retrieval      same source first, entries with a pattern first, overlap with this best's (hot) families x relative saving (`by` no family),
                 never the row's own problem, only saving jumps, one per problem from any line, at most (top+1)//2 rewrites while an edit
                 qualifies, no rewrite of the reference for a best far from it, the L axis; a multi-place edit's mechanism only from the place
                 that removed its removed family
  leak lint      the written file: no Lean block > 2 lines, no identifier of only one other row, no problem name, no line of another row's proof
                 that carries such an identifier; a 2-tactic-line proof gives no pattern and at most one entry
  binding        the file in <work root>/_exemplars/ (outside the workspace); the header's sha and axis; exemplars_for() adds this best's hot
                 families, marks a file of an earlier best stale, nothing once the best reached the target; rows at or above the target get
                 nothing (a stale file and a first-version <ws>/exemplars.md removed); <= CAP chars; --dry-run writes nothing; another set's
                 root or run dir refused, a missing extra root counted
  prompt         prompt v2's WHAT WORKED ON THE STRONGEST ROWS block after the REVIEW block, stale marked, never from the reference
  hx             --claude-exemplars: the builder at ladder start (after the launch check of the extras) and after every batch, --exemplars on
                 every session, the option checks
  cli            counts-only stdout (row#k, never names)
    python3 harness/test_exemplars.py"""
from __future__ import annotations

import collections, contextlib, io, json, math, pathlib, re, subprocess, sys, tempfile, traceback, types

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import exemplars as EX, inrun, cc_levers as LV  # noqa: E402
from harness.leantools import ROWS, HBS  # noqa: E402
from scorer.tokenize import count_tokens  # noqa: E402

S1, S2, S3 = "CallElimCorrect.substOldPostSubset", "CallElimCorrect.extractedOldExprInVars", "Core.InitsUpdatesComm"   # strata
C1, C2 = "Cslib.SKI.parallelReduction_diamond", "Cslib.CCS.bisimilarity_congr_choice"                                 # cslib
P1 = "putnam_1964_b2"                                                                                                   # putnambench
T_BODY = "  induction t_var\n  · simp_all [s1_secret_def]\n  · simp_all\n    grind\n  all_goals simp_all"
S2_OLD = "  intro s2_x hs2\n  simp_all [s2_secret_lemma] at hs2\n  grind only [Shared.common_lemma]"
S2_BODY = "  intro s2_x hs2\n  simp only [s2_secret_lemma] at hs2\n  grind only [Shared.common_lemma]"
S3_BODY = "  cases s3_h\n  · simp only [s3_secret] at *\n  · grind only [Shared.common_lemma]"
C1_OLD = "  intro c1_a c1_b\n  aesop (add safe c1_secret)\n  exact c1_secret c1_a c1_b"
C1_BODY = "  intro c1_a c1_b\n  exact c1_secret c1_a c1_b"
C2_BODY = "  rcases c2_h with ⟨c2_u, c2_v⟩\n  exact c2_secret c2_u"
P1_BODY = "  simp_all [p1_secret]\n  norm_num\n  linarith"
X1_OLD = "  intro x1_a\n  simp_all [x1_secret] at x1_a\n  exact x1_done"     # the extra line's copy of the target's own problem
X1_BODY = "  intro x1_a\n  simp only [x1_secret] at x1_a\n  exact x1_done"
SECRET = ("s1_secret_def", "s1_block_secret", "t_var", "s2_secret_lemma", "s3_secret", "c1_secret", "c2_secret", "p1_secret", "x1_secret", "x1_done",
          "hs2", "s2_x", "c1_a", S1, S2, S3, C1, C2, P1, "substOldPostSubset", "extractedOldExprInVars", "InitsUpdatesComm",
          "parallelReduction_diamond", "bisimilarity_congr_choice")


def decl(name: str, body: str) -> str:
    return ROWS[name]["statement"] + " := by\n" + body


def hot_prof(proof: str) -> dict:
    """A heartbeat profile of T_BODY's proof (profile.py's shape): a parent block over the whole tactic sequence (left out: it contains the
    others) and two leaves; the 100-char excerpts name families the lines do not have (never lexed)."""
    L = proof.split("\n"); ln = lambda s: L.index(s) + 1
    a, b, top = ln("  all_goals simp_all"), ln("  · simp_all [s1_secret_def]"), ln("  induction t_var")
    return {"ok": True, "total": 3000, "floor": 200, "blocks": [{"lines": f"{top}-{a}", "heartbeats": 2700, "text": "induction t_var"},
                                                                 {"lines": f"{a}-{a}", "heartbeats": 1800, "text": "aesop s1_block_secret"},
                                                                 {"lines": f"{b}-{b}", "heartbeats": 600, "text": "decide"}]}


def rec(name: str, body: str, score: float, hb: int, run: str) -> dict:
    return {"problem": name, "proof": decl(name, body), "score": score, "tokens": count_tokens(" by\n" + body), "heartbeats": hb,
            "H": 50.0, "Z": 100.0, "provenance": {"run_id": run}}


def row(wr: pathlib.Path, name: str, body: str | None, score: float, hb: int, H: float, files: str = "", L: float = 80.0, **extra) -> pathlib.Path:
    d = wr / inrun.dirname(name); d.mkdir(parents=True)
    best = {"score": score, "proof": decl(name, body) if body else None, "tokens": count_tokens(" by\n" + (body or "")), "heartbeats": hb, "H": H,
            "L": L, "Z": 100.0}
    (d / "state.json").write_text(json.dumps(dict({"problem": name, "best": best, "attempts": [], "runs": []}, **extra)))
    (d / "original.lean").write_text(f"theorem {name.split('.')[-1]} : True := by\n  trivial\n{files}\n")
    (d / "context.lean").write_text("import Mathlib\n-- shared: Shared.common_lemma\n")
    return d


def world(td: pathlib.Path) -> dict:
    """Line 0 (the work root wr, runs fx-r1 / fx-r2) and line 1 (an extra root ex, run ex-r1). The target S1 (strata, 70, simp_all, a cached
    profile of its best); strong strata S2 (93, an edit simp_all -> simp only) and S3 (92); strong cslib C1 (95, an aesop line deleted); putnam
    P1 below (60); the extra line: C2 (91) and its own copy of S1 (96, a big simp_all edit that the target must never see)."""
    wr, ex, runs = td / "wr", td / "ex", td / "runs"
    for d in (wr, ex, runs):
        d.mkdir()
    sha = LV.proof_sha(decl(S1, T_BODY))
    row(wr, S1, T_BODY, 70.0, 3000, 60.0, "def s1_secret_def := 1\ndef t_var := 2\n", profile_cache={sha: hot_prof(decl(S1, T_BODY))}, hb_floor=200)
    row(wr, S2, S2_BODY, 93.0, 400, 90.0, "def s2_secret_lemma := 1\n")
    row(wr, S3, S3_BODY, 92.0, 500, 88.0, "def s3_secret := 1\n")
    row(wr, C1, C1_BODY, 95.0, 300, 95.0, "def c1_secret := 1\n")
    row(wr, P1, P1_BODY, 60.0, 2000, 50.0, "def p1_secret := 1\n")
    row(ex, S1, X1_BODY, 96.0, 800, 97.0, "def x1_secret := 1\ndef x1_done := 2\n")
    row(ex, C2, C2_BODY, 91.0, 600, 89.0, "def c2_secret := 1\n")
    w = lambda run, recs: ((runs / run).mkdir(), (runs / run / "verified.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs)))
    w("fx-r1", [rec(S1, T_BODY, 70.0, 3000, "fx-r1"), rec(S2, S2_OLD, 80.0, 1500, "fx-r1"), rec(C1, C1_OLD, 90.0, 1200, "fx-r1"),
                rec(P1, P1_BODY, 60.0, 2000, "fx-r1")])
    w("fx-r2", [rec(S2, S2_BODY, 93.0, 400, "fx-r2"), rec(C1, C1_BODY, 95.0, 300, "fx-r2")])
    w("ex-r1", [rec(S1, X1_OLD, 80.0, 3300, "ex-r1"), rec(S1, X1_BODY, 96.0, 800, "ex-r1"), rec(C2, C2_BODY, 91.0, 600, "ex-r1")])
    return {"wr": wr, "ex": ex, "runs": [runs / "fx-r1", runs / "fx-r2"], "extras": [(ex, [runs / "ex-r1"])], "td": td}


# ---- features and jumps -------------------------------------------------------------------------------------------------------------------
def test_features():
    body = (" by\n  simp only [a] at h\n  simp_all\n  grind only [x]\n  grind\n  exact?\n  rw [h] at k\n  rcases h with ⟨a, b⟩\n  obtain ⟨c⟩ := d\n"
            "  have e : 1 = 1 := by\n    first | rfl | omega\n  all_goals norm_num <;> nlinarith\n  exact ?_")
    c = EX.families(body)
    want = {"simp only": 1, "simp": 0, "simp_all": 1, "grind only": 1, "grind": 1, "exact?": 1, "rw": 1, "cases/induction": 2, "have/show/calc": 1,
            "first/try": 1, "omega": 1, "norm_num": 1, "linarith": 1, "all_goals/<;>": 2, "by": 2, "aesop": 0}
    assert {k: c[k] for k in want} == want, {k: c[k] for k in want}
    assert c["_tokens"] == count_tokens(body)
    f = EX.features(body, 120)
    assert f["tokens"] == c["_tokens"] and f["rates"]["simp_all"] == round(100.0 / c["_tokens"], 2) and abs(f["hb_tok"] - 120 / c["_tokens"]) < 1e-9
    assert not f["term"] and EX.features(" fun x => x.1", None)["term"] and EX.features("", 5) is None
    assert EX.nonblank("  a\n\n  -- note\n  b") == 2
    # review 2026-10-13: the ` by` opener is no tactic line (a 2-tactic proof counted 3 and passed the fragment floor)
    assert EX.nonblank(" by\n  norm_num at h\n  simp at h") == 3 and EX.tactic_lines(" by\n  norm_num at h\n  simp at h") == 2
    assert EX.tactic_lines(" by \n  a\n  b\n  c") == 3 and EX.tactic_lines(" by simp\n  exact h") == 2 and EX.tactic_lines(" fun x => x") == 1
    assert EX.axis_of(60.0, 80.0) == "H" and EX.axis_of(90.6, 70.0) == "L" and EX.axis_of(None, 70.0) == "H"
    assert EX.axis_of(83.12, 82.14) == "H" and EX.axis_of(85.0, 80.0) == "L"                       # near-ties stay on heartbeats


def test_jump_chain_and_lines():
    name = S2; ref = ROWS[name]; ref_hb = EX.ref_heartbeats(name)
    r1 = rec(name, S2_OLD, 80.0, 1500, "a"); r_low = rec(name, S2_BODY, 79.0, 100, "a"); r2 = rec(name, S2_BODY, 93.0, 400, "a")
    r2b = rec(name, S2_BODY, 94.0, 390, "a")                                                     # the same body remeasured higher: no jump
    r3 = rec(name, "  exact other_thing\n  omega", 95.0, 350, "a"); bad = dict(rec(name, S2_BODY, 99.0, 1, "a"), proof="theorem other : True := trivial")
    js = EX.chain(name, [r1, r_low, bad, r2, r2b, r3], 0, True)
    assert [(j["first"], j["kind"]) for j in js] == [(True, "rewrite"), (False, "edit"), (False, "rewrite")], [(j["first"], j["kind"]) for j in js]
    assert js[0]["d_tok"] == r1["tokens"] - ref["proof_length"] and js[0]["d_hb"] == 1500 - ref_hb and js[0]["hb_before"] == ref_hb
    assert ref_hb != HBS[name]                                                                   # the local reference measurement (H's scale)
    assert js[0]["tok_before"] == ref["proof_length"]
    assert (js[1]["d_score"], js[1]["d_hb"], js[1]["d_tok"], js[1]["hb_before"]) == (13.0, -1100, 1, 1500)
    assert (js[2]["d_score"], js[2]["hb_before"], js[2]["tok_before"]) == (1.0, 390, r2b["tokens"])   # against the remeasured record
    assert js[1]["diff"] == ["-  simp_all [s2_secret_lemma] at hs2", "+  simp only [s2_secret_lemma] at hs2"], js[1]["diff"]
    assert js[1]["before"]["simp_all"] == 1 and js[1]["after"]["simp only"] == 1 and js[1]["source"] == "strata" and all(j["strong"] for j in js)
    # review 2026-10-13: the first change of the reference is classified by the diff rule (a one-line change is an edit), the same body is none
    refb = EX.body_of(S1, ROWS[S1]["src"]); body = refb[refb.index("\n") + 1:]; L = body.split("\n"); L[-1] += "  -- tweak"
    js = EX.chain(S1, [rec(S1, body, 40.0, 5000, "a"), rec(S1, "\n".join(L), 41.0, 4000, "a")], 0, False)
    assert [(j["first"], j["kind"], j["d_hb"]) for j in js] == [(True, "edit", -1000)], [(j["first"], j["kind"], j["d_hb"]) for j in js]
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        for n in ("r10", "r2", "r1"):
            (td / f"x-r{n[1:]}").mkdir()
        for n in ("ab-hx-x-f2", "ab-hx-x-r1", "ab-hx-x-r2", "ab-hx-x-p1", "ab-hx-x-f12", "ab-hx-x-r12", "o-a2", "o-a10"):
            (td / n).mkdir()
        got, miss = EX.expand([str(td / "x-r*"), str(td / "nope")])
        assert [p.name for p in got] == ["x-r1", "x-r2", "x-r10"] and miss == 1                     # round order; a missing dir counted
        got, _ = EX.expand([str(td / "ab-hx-x-*")])                                                  # hx ids: round, then r / f / p (line_runs)
        assert [p.name for p in got] == ["ab-hx-x-r1", "ab-hx-x-p1", "ab-hx-x-r2", "ab-hx-x-f2", "ab-hx-x-r12", "ab-hx-x-f12"], [p.name for p in got]
        assert [p.name for p in EX.expand([str(td / "o-*")])[0]] == ["o-a2", "o-a10"]                # other names: natural order
        W = world(td); texts: dict = {}
        res = EX.build(W["wr"], W["runs"], W["extras"], write=False, texts=texts)
        c = res["c"]
        # line 0: S1, S2 (2), C1 (2), P1; line 1: S1 (2), C2: 9 jumps, the first of each (line, problem) flagged
        assert (c["records"], c["jumps"], c["first"], c["edits"], c["lines"], c["runs"]) == (9, 9, 6, 3, 2, 3), dict(c)
        assert (c["extra_rows"], c["extra_empty"], c["extra_missing"]) == (2, 0, 0), dict(c)
        (W["runs"][1] / "verified.jsonl").open("a").write(json.dumps(rec(S3, S3_BODY, 92.0, 500, "fx-r2")) + "\n")
        (W["runs"][1] / "verified.jsonl").open("a").write(json.dumps(rec(C2, C2_BODY, 91.0, 600, "fx-r2")) + "\n")   # no C2 workspace in line 0
        c = EX.build(W["wr"], W["runs"], W["extras"], write=False)["c"]
        assert c["jumps"] == 10 and c["records_skipped"] == 1, dict(c)


# ---- contrast, hot families, retrieval --------------------------------------------------------------------------------------------------
def _r(problem, source, H, score, rates, hb_tok=10.0, term=False, ref_hb=4000, line=0, tokens=200, L=80.0, ref_tok=None, axis="H"):
    cnt = collections.Counter({f: round(v * tokens / 100.0) for f, v in rates.items()})
    return {"problem": problem, "source": source, "H": H, "L": L, "axis": axis, "score": score, "ref_hb": ref_hb, "ref_tok": ref_tok, "line": line,
            "f": {"rates": dict({f: 0.0 for f in EX.FAMILIES}, **rates), "counts": cnt, "hb_tok": hb_tok, "term": term, "tokens": tokens}}


def _eff(d: dict, every: list) -> tuple:
    return {f: d.get(f, ([], [])) for f in EX.FAMILIES}, every


def _j(problem, source, d_hb, hb_before, before, after, kind="edit", first=False, strong=False, line=0, d_score=1.0, d_tok=-1, tok_before=100,
       old="  a\n  b\n  c", new="  a\n  b\n  c", diff=()):
    return {"line": line, "problem": problem, "source": source, "first": first, "kind": kind, "d_score": d_score, "d_tok": d_tok, "d_hb": d_hb,
            "hb_before": hb_before, "tok_before": tok_before, "before": collections.Counter(before), "after": collections.Counter(after), "old": old,
            "new": new, "diff": list(diff), "strong": strong}


def test_effects():
    lg = lambda a, b: math.log(b / a)
    J = [_j("A", "strata", -500, 1000, {"grind": 1}, {"omega": 1}), _j("B", "cslib", 100, 1000, {}, {"grind": 1}),
         _j("T", "strata", -900, 1000, {"grind": 1}, {}),                                          # the row's own problem: never
         _j("C", "strata", -800, 1000, {"grind": 1}, {}, kind="rewrite"),                          # a rewrite changes everything: no evidence
         _j("D", "strata", -10, 1000, {"by": 2}, {"by": 1}, d_tok=-50, tok_before=100), _j("E", "strata", None, None, {"grind": 1}, {})]
    per, every = EX.effects(J, "T", "H")
    assert per["grind"] == ([lg(1000, 500)], [lg(1000, 1100)]) and per["omega"] == ([], [lg(1000, 500)]) and per["by"] == ([], []), per["grind"]
    assert sorted(every) == sorted([lg(1000, 500), lg(1000, 1100), lg(1000, 990)])
    per, every = EX.effects(J, "T", "L")                                                            # the L axis: tokens (E has them)
    assert per["grind"][0] == [lg(100, 99)] * 2 and lg(100, 50) in every


def test_contrast_effects_and_pool():
    t = _r("T", "strata", 70.0, 70.0, {"simp_all": 4.2, "rw": 3.0, "grind": 2.0, "aesop": 1.0, "simp only": 0.0}, hb_tok=31.0)
    strong = [_r("A", "strata", 90.0, 93.0, {"simp only": 3.0}, 9.0), _r("B", "strata", 88.0, 92.0, {"simp only": 2.0}, 10.0),
              _r("C", "cslib", 95.0, 95.0, {"simp_all": 6.0}, 4.0), _r("T", "strata", 97.0, 96.0, {"simp_all": 9.0}, 2.0, line=1)]
    eff = _eff({"simp_all": ([-0.5] * 5, [0.1] * 4),          # removal beats adding: listed
                "rw": ([-0.02] * 6, [-0.06] * 5),             # adding saved more than removing (the warm-up's simp only): never listed
                "grind": ([-0.4] * 4, [0.2]),                 # < MIN_N added it: against every edit
                "aesop": ([-0.9] * 3, []),                    # < MIN_N removed it: no evidence
                "simp only": ([0.3] * 9, [-0.5] * 9)},        # this row uses less of it: never listed (no extra steps asked for)
               [-0.03] * 20)
    lines, scope, n = EX.contrast(t, strong, 90.0, eff, set())
    assert scope == "of this source" and n == 2, (scope, n)                                     # the same-source pool; never T from line 1
    txt = "\n".join(lines)
    assert "- H 88-90 there on references of 4.0k-4.0k hb; here H 70.0 on 4.0k hb" in txt and "median 9.5 there vs 31.0 here" in txt, txt
    assert ("- grind: 0.0 there vs 2.0 here per 100 tokens; other problems' edits that removed it: median -33% hb over 4 (every edit: -3% over 20)"
            in lines and "- simp_all: 0.0 there vs 4.2 here per 100 tokens; other problems' edits that removed it: median -39% hb over 5 (that added "
            "it: +11% over 4)" in lines), txt
    assert lines.index(next(l for l in lines if l.startswith("- simp_all"))) < lines.index(next(l for l in lines if l.startswith("- grind")))   # by effect
    assert not any(l.startswith(("- rw", "- aesop", "- simp only")) for l in lines), txt
    only = EX.contrast(t, strong, 90.0, eff, {"grind"})[0]                                         # hot families: the only candidates
    assert any(l.startswith("- grind") for l in only) and not any(l.startswith("- simp_all") for l in only), only
    short = _r("T", "strata", 70.0, 70.0, {"all_goals/<;>": 9.1}, tokens=22)                         # a 22-token best: counts, not rates
    lines = EX.contrast(short, strong, 90.0, _eff({"all_goals/<;>": ([-0.3] * 5, [0.05] * 6)}, []), set())[0]
    assert "- all_goals/<;>: 2 here in 22 tokens vs 0.0 per 100 tokens there; other problems' edits that removed it: median -26% hb over 5 (that " \
           "added it: +5% over 6)" in lines, lines
    lt = _r("T", "strata", 92.0, 80.0, {"simp_all": 4.2}, L=66.1, ref_tok=313, axis="L")            # the L axis: tokens, the L context line
    sl = [dict(r, ref_tok=200) for r in strong]
    lines = EX.contrast(lt, sl, 90.0, _eff({"simp_all": ([-0.5] * 5, [0.1] * 4)}, []), set())[0]
    assert lines[0] == "- L 80-80 there on references of 200-200 tokens; here L 66.1 on 313 tokens" and "median -39% tokens over 5" in lines[1], lines
    small = _eff({"simp_all": ([-0.03] * 5, [0.0] * 4)}, [])                                          # 3%: enough for tokens, not for heartbeats
    assert any(l.startswith("- simp_all") for l in EX.contrast(lt, sl, 90.0, small, set())[0])
    assert not any(l.startswith("- simp_all") for l in EX.contrast(t, strong, 90.0, small, set())[0])
    lines, scope, n = EX.contrast(t, strong[1:], 90.0, eff, set())                                   # one strata row left: every source
    assert scope == "of every source" and n == 2, (scope, n)
    assert EX.contrast(t, [strong[3]], 90.0, eff, set()) == ([], "of every source", 0)                # only its own problem is strong
    tm = _r("T", "strata", 70.0, 70.0, {}, term=False)
    st = [_r("A", "strata", 90.0, 93.0, {}, term=True), _r("B", "strata", 88.0, 92.0, {}, term=True)]
    assert "- term mode: 2 of 2 there vs a tactic proof here" in EX.contrast(tm, st, 90.0, _eff({}, []), set())[0]


def test_hot_families():
    proof = decl(S1, T_BODY); prof = hot_prof(proof); sha = LV.proof_sha(proof)
    lines, hot, head = EX.hot_families({"profile_cache": {sha: prof}}, proof)
    assert head.startswith("HEARTBEAT HOT FAMILIES (heartbeat_profile of the stored best, best.lean lines, leaf blocks: total 3000 hb")
    a, b = prof["blocks"][1]["lines"], prof["blocks"][2]["lines"]
    # the parent block (it contains both) is left out; families come from the best's own lines, not the excerpts (aesop, decide)
    assert lines == [f"- lines {a}: 1800 hb (64% above the floor): simp_all, all_goals/<;>", f"- lines {b}: 600 hb (21% above the floor): simp_all"], lines
    assert hot == {"simp_all", "all_goals/<;>"} and not any("secret" in l for l in lines)        # no block text leaves the function
    assert EX.hot_families({"profile_cache": {"b" * 12: prof}}, proof) == ([], set(), None)     # never another candidate's profile
    assert EX.hot_families({}, proof) == ([], set(), None) and EX.hot_families({"profile_cache": {sha: {"ok": False}}}, proof)[0] == []
    many = dict(prof, blocks=[{"lines": f"{k}-{k}", "heartbeats": 100 + k, "text": ""} for k in range(1, 9)])
    s = EX.hot_section({"profile_cache": {sha: many}}, proof)
    assert 0 < len(s) <= EX.HOT_CAP and s.count("\n- lines") <= EX.HOT_K and EX.hot_section({}, proof) == ""


def test_retrieval_ranking():
    t = _r("T", "strata", 70.0, 70.0, {"simp_all": 4.2, "rw": 3.0})
    idx = EX.Index({}, [])
    J = [_j("Q1", "cslib", -900, 1000, {"aesop": 1}, {}),                                    # other source, big saving, no overlap
         _j("Q2", "strata", -100, 1000, {"aesop": 1}, {}),                                    # same source, small, no overlap
         _j("Q3", "strata", -300, 1000, {"simp_all": 2}, {"simp only": 2}),                   # same source, overlap, hot
         _j("Q3", "strata", -650, 1000, {"simp_all": 1}, {"simp only": 1}, line=1),           # the same problem in another line: one of them only
         _j("T", "strata", -999, 1000, {"simp_all": 3}, {}),                                  # the target's own problem: never
         _j("Q4", "strata", 50, 1000, {"simp_all": 3}, {}),                                   # costs heartbeats: never
         _j("Q5", "strata", -700, 1000, {"rw": 4}, {"grind": 1}, kind="rewrite", first=True, strong=True),
         _j("Q6", "strata", -800, 1000, {"rw": 4}, {"grind": 1}, kind="rewrite", first=True),
         _j("Q7", "strata", -900, 1000, {"rw": 4}, {"grind": 1}, kind="rewrite", first=True)]
    # relevance (BASE + overlap + hot) x saving (x 1.25 strong): hot {simp_all}: Q3/1 1.14, Q7 1.13, Q5 1.09, Q6 1.0, Q3/0 0.53, Q2 0.03; Q1 last
    picks = EX.retrieve(t, J, {"simp_all"}, 3, 90.0, idx, {})
    got = [(p["j"]["problem"], p["j"]["line"]) for p in picks]
    assert got == [("Q3", 1), ("Q7", 0), ("Q5", 0)] and all(p["same"] for p in picks), got
    every = [p["j"]["problem"] for p in EX.retrieve(t, J, set(), 20, 90.0, idx, {})]
    assert every == ["Q7", "Q5", "Q6", "Q3", "Q2", "Q1"], every                                   # same source first; one per problem; only savings
    picks = EX.retrieve(t, J, set(), 3, 90.0, idx, {})                                           # no hot bonus: Q7, Q5, Q6 lead, at most 2 rewrites
    assert [p["j"]["problem"] for p in picks] == ["Q7", "Q5", "Q3"], [p["j"]["problem"] for p in picks]
    one = EX.retrieve(t, [J[2], dict(J[2], d_hb=-200)], set(), 2, 90.0, idx, {})                 # review 2026-10-13: one per problem in every pass
    assert len(one) == 1 and one[0]["j"]["d_hb"] == -300
    rw = EX.retrieve(t, [J[6], J[7], J[8], dict(J[2], problem="Q9", before=collections.Counter(), after=collections.Counter())], set(), 3, 90.0,
                     idx, {})
    assert [p["j"]["problem"] for p in rw] == ["Q7", "Q5", "Q6"], [p["j"]["problem"] for p in rw]   # the only edit says nothing: rewrites fill up
    txt = one[0]["texts"][0]
    assert txt == "[strata; edit] -300 hb (-30%), +1.00 score, -1 tok: simp_all 2->0, simp only 0->2", txt
    assert EX.retrieve(_r("T", "strata", 70.0, 70.0, {}), [J[4]], set(), 3, 90.0, idx, {}) == []
    # a rewrite of the reference only for a best near its reference (>= NEAR_REF of its tokens): 200 of 1000 is far
    far = [p["j"]["problem"] for p in EX.retrieve(dict(t, ref_tok=1000), J, set(), 20, 90.0, idx, {})]
    assert far == ["Q3", "Q2", "Q1"], far
    # an entry with a pattern before family changes alone (same source tier), whatever its relevance
    pat = _j("Q8", "strata", -20, 1000, {"simp_all": 1}, {"simp only": 1}, old="  intro a\n  simp_all [x] at h\n  exact h",
             new="  intro a\n  simp only [x] at h\n  exact h", diff=["-  simp_all [x] at h", "+  simp only [x] at h"])
    ps = EX.retrieve(t, J + [pat], set(), 3, 90.0, idx, {})
    assert ps[0]["j"]["problem"] == "Q8" and "`simp_all [$A] at $B` -> `simp only [$A] at $B`" in ps[0]["texts"][0], ps[0]["texts"]
    # `by` is no family: removing by-blocks gives no overlap with a best that has them
    tb = _r("T", "strata", 70.0, 70.0, {"by": 3.0})
    jb = [_j("QA", "strata", -500, 1000, {"by": 3, "aesop": 1}, {"by": 1}, d_score=1.0), _j("QB", "strata", -500, 1000, {"aesop": 1}, {}, d_score=2.0)]
    assert [p["j"]["problem"] for p in EX.retrieve(tb, jb, set(), 2, 90.0, idx, {})] == ["QB", "QA"]
    # the L axis: token-saving jumps that cost no heartbeats, numbers led by tokens
    tl = dict(t, axis="L")
    jl = [_j("QL", "strata", 0, 1000, {"simp_all": 1}, {}, d_tok=-40, tok_before=200), _j("QM", "strata", -500, 1000, {"simp_all": 1}, {}, d_tok=5),
          _j("QN", "strata", 30, 1000, {"simp_all": 1}, {}, d_tok=-90, tok_before=200)]
    pl = EX.retrieve(tl, jl, set(), 3, 90.0, idx, {})
    assert [p["j"]["problem"] for p in pl] == ["QL"] and pl[0]["texts"][0].startswith("[strata; edit] -40 tok (-20%), +1.00 score, +0 hb"), pl


def test_multi_place_mechanism():
    """Review 2026-10-13: an edit's mechanism comes from the changed place that removed its removed family, labelled as one of N; an edit
    whose places removed no family shows the family change alone."""
    idx = EX.Index({}, [])
    old = "  intro x\n  simp_all [foo, bar] at x\n  constructor\n  grind\n  exact x"
    new = "  intro x\n  simp_all [foo] at x\n  constructor\n  omega\n  exact x"
    from harness.discover import diff
    j = _j("Q", "strata", -600, 1000, EX.families(old), EX.families(new), old=old, new=new, diff=diff(old, new))
    texts = EX.describe(j, idx, 90.0)
    assert texts[0] == "[strata; edit] -600 hb (-60%), +1.00 score, -1 tok: at 1 of 2 changed places, `grind` -> `omega` (grind 1->0, omega 0->1)", texts
    one = dict(j, diff=diff(old, old.replace("grind", "omega")), after=EX.families(old.replace("grind", "omega")))
    assert EX.describe(one, idx, 90.0)[0].endswith(": `grind` -> `omega` (grind 1->0, omega 0->1)")   # one place: no label
    args = old.replace("[foo, bar]", "[foo]").replace("constructor", "constructor'")
    none = dict(j, diff=diff(old, args), after=EX.families(args), new=args)
    assert all("`" not in x or "e.g." in x for x in EX.describe(none, idx, 90.0))                    # no removed family: no mechanism


# ---- the written file: lint, sha, targets -----------------------------------------------------------------------------------------------
def test_build_leak_lint_and_retrieval():
    with tempfile.TemporaryDirectory() as td:
        W = world(pathlib.Path(td)); texts: dict = {}
        res = EX.build(W["wr"], W["runs"], W["extras"], texts=texts)
        ws = sorted(p.parent.name for p in W["wr"].glob("*/state.json")); k = ws.index(inrun.dirname(S1)); kp = ws.index(inrun.dirname(P1))
        fp = W["wr"] / EX.XDIR / f"{inrun.dirname(S1)}.md"
        assert EX.path_for(W["wr"] / inrun.dirname(S1)) == fp and not (W["wr"] / inrun.dirname(S1) / EX.FILE).exists()   # outside the workspace
        txt = fp.read_text()
        assert txt.rstrip("\n") == texts[k] and len(txt.rstrip("\n")) <= EX.CAP and set(texts) == {k, kp}, sorted(texts)
        body = EX.parse(txt)[1]
        assert body.startswith("STRONGEST ROWS STYLE (2 row(s) >= 90 of this source, other problems; the points left here are in heartbeats;"), body
        assert "- H 88-90 there on references of" in body and " here per 100 tokens;" not in body   # < MIN_N edits: no family line
        assert "HEARTBEAT HOT FAMILIES" not in body                                                 # added when the prompt is built
        tr = body[body.index("RETRIEVED TRANSFORMATIONS"):].split("\n")[1:]
        assert tr == ["1. [strata; edit; that row is now >= 90] -1100 hb (-73%), +13.00 score, +1 tok: `simp_all [$A] at $B` -> `simp only [$A] at "
                      "$B` (simp_all 1->0, simp only 0->1)",
                      f"2. [cslib; edit; that row is now >= 90] -900 hb (-75%), +5.00 score, "
                      f"{count_tokens(' by' + chr(10) + C1_BODY) - count_tokens(' by' + chr(10) + C1_OLD):+d} tok: aesop 1->0"], tr
        # no rewrite of the reference (this best keeps < half of its reference's tokens), one entry per problem, the extra line's S1: never
        assert "of the reference" not in body and "-2500 hb" not in body and "+16.00 score" not in body
        # the leak lint over every listed row: no Lean block, no problem name, no identifier of one row, no line of another row's proof
        idx = EX.Index({n: [d / inrun.dirname(n) / "original.lean", d / inrun.dirname(n) / "context.lean"]
                        for d in (W["wr"], W["ex"]) for n in (S1, S2, S3, C1, C2, P1) if (d / inrun.dirname(n)).exists()}, [S1, S2, S3, C1, C2, P1])
        assert inrun.leak_lint(txt, idx.terms, idx.owner, None, idx.declared) is None and LV.lean_block_lines(txt) <= 2
        for s in SECRET:
            assert s not in txt, s
        for b in (S2_BODY, S2_OLD, S3_BODY, C1_BODY, C1_OLD, C2_BODY, P1_BODY, X1_BODY, X1_OLD):
            for l in b.split("\n"):
                assert l.strip() not in txt, l
        assert res["c"]["lint_rejected"] == 0 and idx.ok("use `s2_secret_lemma` here") is False and idx.rejected == 1
        assert idx.ok("- simp_all: 0.0 there vs 4.2 here") and not idx.ok("1. pattern `exact " + S2 + "`")
        assert not idx.ok("- works:\n```lean\n  simp at h\n  exact h\n  omega\n```")


def test_two_line_proof_never_rebuilt():
    """Review 2026-10-13 (finding: a 2-tactic-line best came back whole from three entries): another row whose bests have 2 tactic lines, in
    two lines, gives at most one entry and no pattern or snippet."""
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td); wr, ex, runs = td / "wr", td / "ex", td / "runs"
        for d in (wr, ex, runs):
            d.mkdir()
        a, b, c = "  simp_all [s2_secret_lemma] at hs2\n  norm_num at hs2", "  norm_num at hs2\n  simp only [s2_secret_lemma] at hs2", "  norm_num at hs2"
        row(wr, S1, T_BODY, 70.0, 3000, 60.0, "def s1_secret_def := 1\n")
        row(wr, S2, b, 93.0, 400, 90.0, "def s2_secret_lemma := 1\n"); row(ex, S2, c, 95.0, 300, 95.0, "def s2_secret_lemma := 1\n")
        for run, recs in (("w-r1", [rec(S2, a, 80.0, 1500, "w"), rec(S2, b, 93.0, 400, "w")]), ("e-r1", [rec(S2, a, 80.0, 1500, "e"), rec(S2, c, 95.0, 300, "e")])):
            (runs / run).mkdir(); (runs / run / "verified.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        texts: dict = {}
        EX.build(wr, [runs / "w-r1"], [(ex, [runs / "e-r1"])], write=False, texts=texts)
        k = sorted(p.parent.name for p in wr.glob("*/state.json")).index(inrun.dirname(S1))
        txt = texts[k]; tr = txt[txt.index("RETRIEVED TRANSFORMATIONS"):].split("\n")[1:]
        assert len(tr) == 1 and "`" not in tr[0] and "norm_num at" not in txt and "simp only [" not in txt, txt


def test_sha_binding_targets_and_dry_run():
    with tempfile.TemporaryDirectory() as td:
        W = world(pathlib.Path(td)); w = W["wr"] / inrun.dirname(S1); fp = EX.path_for(w)
        stale = EX.path_for(W["wr"] / inrun.dirname(S2)); stale.parent.mkdir(); stale.write_text(EX.header("0" * 12, "t", 90, 1, 1) + "\nold\n")
        legacy = W["wr"] / inrun.dirname(S3) / EX.FILE; legacy.write_text(EX.header("0" * 12, "t", 90, 1, 1) + "\nold\n")   # the first version's place
        snap = {p: p.read_bytes() for p in W["wr"].rglob("*") if p.is_file()}
        c = EX.build(W["wr"], W["runs"], W["extras"], write=False)["c"]
        assert {p: p.read_bytes() for p in W["wr"].rglob("*") if p.is_file()} == snap               # a dry run writes and removes nothing
        assert (c["rows"], c["at_target"], c["below"], c["written"], c["removed"], c["legacy_removed"]) == (5, 3, 2, 2, 1, 1), dict(c)
        EX.build(W["wr"], W["runs"], W["extras"], t_iso="2026-10-13T02:00:00Z")
        st = json.loads((w / "state.json").read_text()); meta, body = EX.parse(fp.read_text())
        assert meta == {"best_sha": LV.proof_sha(st["best"]["proof"]), "t": "2026-10-13T02:00:00Z", "target": "90", "axis": "H", "strong": "2",
                        "transformations": "2"}, meta
        assert not stale.exists() and not legacy.exists()
        assert not any(EX.path_for(W["wr"] / inrun.dirname(n)).exists() for n in (S2, S3, C1))       # rows at or above the target: nothing
        text, sha, old = EX.exemplars_for(w, st)
        L = text.split("\n"); h = L.index(next(l for l in L if l.startswith("HEARTBEAT HOT FAMILIES")))
        assert sha == meta["best_sha"] and not old and L[0] == body.split("\n")[0] and L[h + 1].endswith("simp_all, all_goals/<;>"), text
        assert L[h + 3].startswith("RETRIEVED TRANSFORMATIONS") and len(text) <= EX.BLOCK_CAP        # the hot families before the retrieval
        moved = dict(st, best=dict(st["best"], proof=st["best"]["proof"] + "\n  -- a new best"))
        text, sha, old = EX.exemplars_for(w, moved)                                                  # review 2026-10-13: shown, marked stale
        assert old and sha == meta["best_sha"] and text.startswith(f"(built for an earlier best of this problem, sha {sha}:") and "HEARTBEAT HOT" not in text
        assert EX.exemplars_for(w, dict(st, best=dict(st["best"], score=90.0))) is None              # the best reached the target
        assert EX.exemplars_for(w, dict(st, best={"score": 33.33})) is None and EX.exemplars_for(W["wr"] / inrun.dirname(C1), st) is None
        assert EX.parse("no header\nx") is None
        hi = EX.build(W["wr"], W["runs"], W["extras"], target=65.0)["c"]                              # S1 (70) is now at the target: its file goes
        assert hi["at_target"] == 4 and hi["removed"] == 1 and not fp.exists() and EX.path_for(W["wr"] / inrun.dirname(P1)).exists(), dict(hi)
        tag = pathlib.Path(td) / "work_sealed3-x"; tag.mkdir()
        for bad in (dict(extras=[(tag, [])]), dict(runs=[pathlib.Path(td) / "abpool-hx-r1"]), dict(extras=[(pathlib.Path(td) / "abpool-gone", [])])):
            try:
                EX.build(W["wr"], **dict(dict(runs=[], extras=[]), **bad), write=False); raise AssertionError(bad)
            except ValueError as e:
                assert "refused" in str(e)
        assert EX.build(tag, [], [(pathlib.Path(td) / "sealed3-y", [])], write=False)["c"]["rows"] == 0   # the same set: allowed
        gone = EX.build(W["wr"], W["runs"], [(pathlib.Path(td) / "gone", [])], write=False)["c"]       # review 2026-10-13: counted, not fatal
        assert gone["extra_missing"] == 1 and gone["lines"] == 1 and gone["written"] == 2, dict(gone)
        assert "1 root(s) missing" in EX.summary(gone, 90.0, True)


def test_cap_fitting():
    proof = decl(S1, T_BODY)
    t = {"sha": "a" * 12, "state": {}, "proof": proof, "problem": "T", "source": "strata", "H": 60.0, "L": 80.0, "axis": "H", "ref_hb": 5000,
         "ref_tok": 100, "f": _r("T", "strata", 60.0, 60.0, {"simp_all": 5.0})["f"]}
    long = "x" * 600
    picks = [{"j": _j(f"Q{k}", "strata", -100, 1000, {}, {}), "same": True, "texts": [f"[strata; edit] {long} {k}", f"[strata; edit] short {k}"]}
             for k in range(3)]
    real = EX.retrieve
    EX.retrieve = lambda *a, **k: [dict(p) for p in picks]
    try:
        text, st = EX.compose(t, [_r("A", "strata", 90.0, 93.0, {})] * 2, [], EX.Index({}, []), 90.0, 3, {}, "now")
    finally:
        EX.retrieve = real
    assert len(text) <= EX.CAP and st["picks"] >= 2 and text.count("short") >= 1 and text.startswith(EX.TAG), (len(text), st)


# ---- prompt v2, hx, CLI -----------------------------------------------------------------------------------------------------------------
def test_prompt_block():
    from harness import prompt_v2 as pv
    from harness.agent import Workspace
    from probe.verify_candidates import newest_first
    row_ = ROWS[P1]; primary = newest_first(row_["version_info"])[0]
    with tempfile.TemporaryDirectory() as td:
        ws = Workspace(pathlib.Path(td) / P1, row_, primary, fresh=True)
        ws.state["best"] = {"score": 61.5, "proof": row_["src"], "tokens": 300, "heartbeats": 9000}; ws.state["attempts"] = [{"ok": True}]
        sha = LV.proof_sha(row_["src"])
        (ws.root / EX.FILE).write_text(EX.header(sha, "t", 90, 2, 1) + "\nLEGACYMARK\n")            # the first version's place: never read
        kw = dict(leads=None, upstream=None, lever_review=True, review="1. a lever", review_sha=sha, extras="\n\nEXTRAS")
        p, sec = pv.build_prompt_v2(P1, row_, primary, ws, exemplars="default", **kw)
        assert "exemplars" not in sec and "LEGACYMARK" not in p
        fp = EX.path_for(ws.root); fp.parent.mkdir(); fp.write_text(EX.header(sha, "t", 90, 2, 1) + "\nSTRONGEST ROWS STYLE (x):\n- simp_all: 0.0 there vs 4.2 here\n")
        p, sec = pv.build_prompt_v2(P1, row_, primary, ws, exemplars="default", **kw)
        assert sec[-3:] == ["review", "exemplars", "extras"], sec
        assert p.index("REVIEW (fresh eyes)") < p.index("WHAT WORKED ON THE STRONGEST ROWS") < p.index("- simp_all: 0.0 there vs 4.2 here") < p.index("EXTRAS")
        assert f"best sha {sha}" in p and "lra-exemplars" not in p and "OTHER problems, never this one" in p and "earlier best" not in p
        p0, sec0 = pv.build_prompt_v2(P1, row_, primary, ws, **kw)                                 # no flag: no block (and the rest unchanged)
        assert "exemplars" not in sec0 and "WHAT WORKED" not in p0 and p0 == p.replace(p[p.index("\n\nWHAT WORKED"):p.index("\n\nEXTRAS")], "")
        p, sec = pv.build_prompt_v2(P1, row_, primary, ws, exemplars="default", from_reference=True, leads=None, upstream=None)
        assert "exemplars" not in sec and "WHAT WORKED" not in p                                     # never in a from-reference session
        ws.state["best"]["proof"] = row_["src"] + "\n  -- another best"
        p, sec = pv.build_prompt_v2(P1, row_, primary, ws, exemplars="default", leads=None, upstream=None)
        assert "exemplars" in sec and f"(built for an earlier best of this problem, sha {sha}:" in p   # built for another best: marked stale
        ws.state["best"]["score"] = 90.0
        p, sec = pv.build_prompt_v2(P1, row_, primary, ws, exemplars="default", leads=None, upstream=None)
        assert "exemplars" not in sec                                                                # the best reached the file's target
        def boom(_ws):
            raise RuntimeError("no file system here")
        p, sec = pv.build_prompt_v2(P1, row_, primary, ws, exemplars=boom, leads=None, upstream=None)
        assert "exemplars" not in sec
        p, sec = pv.build_prompt_v2(P1, row_, primary, ws, exemplars=lambda _w: ("BODY " + "y" * 3000, "abc"), leads=None, upstream=None)
        assert "exemplars" in sec and len(p[p.index("BODY"):]) == EX.BLOCK_CAP


def test_hx_exemplars():
    from harness import hx_heldout as hx
    NS = types.SimpleNamespace
    a = NS(driver="claude", claude_model="claude-opus-5-5", claude_prompt="v2", claude_cache="5m", claude_sealed=False, claude_exemplars=True)
    c = hx.session_cmd(a, 2.85, "harness/hwork/x", "abpool-hx-t-r1", [P1], 2, "xhigh", False, [])
    assert "--exemplars" in c and c[-2:] == ["--problems", P1], c
    assert "--exemplars" not in hx.session_cmd(NS(**dict(vars(a), claude_exemplars=False)), 2.85, "r", "x-r1", [P1], 2, "xhigh", False, [])
    with tempfile.TemporaryDirectory() as td:
        cw = pathlib.Path(td)
        for rid, ver in (("ab-hx-x-r1", True), ("ab-hx-x-f1", False), ("ab-hx-x-p1", True), ("ab-hx-x-r2", True), ("ab-hx-x-rerun-r1", True)):
            (cw / "probe/runs" / rid).mkdir(parents=True)
            if ver:
                (cw / "probe/runs" / rid / "verified.jsonl").write_text("{}\n")
        S = NS(wt=cw, root="harness/hwork/ab-x", run_prefix="ab-hx-x-r"); got = []
        run = lambda cmd, cwd, timeout, say, tag: got.append((cmd, cwd, timeout, tag)) or 0
        ex = [["harness/hwork/ab-opus", "probe/runs/ab-hx-opus-r*"], ["/abs/other", "probe/runs/o-p1"], ["harness/hwork/ab-opus", "probe/runs/ab-hx-opus-p1"]]
        A = NS(claude_prompt="v2", claude_inrun=None, claude_polish=False, claude_exemplars=True, claude_exemplars_extra=ex, claude_exemplars_target=90.0)
        hx.cc_after_batch(S, A, 2, [P1], print, run=run)
        assert [g[3] for g in got] == ["discover --ledger-only", "run techniques", "exemplars"] and got[2][1:3] == (cw, 600), [g[3] for g in got]
        cmd = ["python3", "harness/exemplars.py", "--work-root", "harness/hwork/ab-x", "--target", "90", "--runs-dir", "probe/runs/ab-hx-x-r1",
               "probe/runs/ab-hx-x-p1", "probe/runs/ab-hx-x-r2", "--extra-root", "harness/hwork/ab-opus", "probe/runs/ab-hx-opus-r*",
               "probe/runs/ab-hx-opus-p1", "--extra-root", "/abs/other", "probe/runs/o-p1"]
        assert got[2][0] == cmd, got[2][0]
        got.clear(); hx.cc_after_batch(S, NS(claude_prompt="v2", claude_inrun=False, claude_polish=False), 2, [P1], print, run=run)
        assert got == []                                                                              # off by default
        # review 2026-10-13: the launch check (extras resolved against the worktree) and one build before the first round
        said = []; say = said.append
        assert hx.exemplars_start(S, A, say, run=run) == 2 and got == [] and "is not a directory" in said[-1]   # ab-opus / /abs/other missing
        (cw / "harness/hwork/ab-opus").mkdir(parents=True); other = cw / "other"; other.mkdir()
        A2 = NS(**dict(vars(A), claude_exemplars_extra=[["harness/hwork/ab-opus", "probe/runs/ab-hx-opus-r*"], [str(other), "probe/runs/o-p1"]]))
        assert hx.exemplars_check(S, A2) is None and hx.exemplars_start(S, A2, say, run=run) == 0
        assert [g[3] for g in got] == ["exemplars (ladder start)"] and got[0][0][:4] == cmd[:4] and got[0][1:3] == (cw, 600), got
        (cw / "harness/hwork/sealed3-cc").mkdir(parents=True)
        for bad in ([["harness/hwork/sealed3-cc", "probe/runs/x-r1"]], [["harness/hwork/ab-opus", "probe/runs/sealed3-cc-hx-r*"]]):
            assert "belongs to sealed3" in hx.exemplars_check(S, NS(**dict(vars(A), claude_exemplars_extra=bad)))
        assert hx.exemplars_check(S, NS(claude_exemplars_extra=None)) is None
    base = ["--set", "abpool", "--arm", "x", "--driver", "claude", "--claude-prompt", "v2"]
    ok = hx.build_parser().parse_args(base + ["--claude-exemplars", "--claude-exemplars-extra", "harness/hwork/ab-opus", "probe/runs/ab-*"])
    hx.check_args(hx.build_parser(), ok)
    assert ok.claude_exemplars_extra == [["harness/hwork/ab-opus", "probe/runs/ab-*"]] and ok.claude_exemplars_target == 90.0
    for bad in (["--set", "abpool", "--arm", "x", "--driver", "claude", "--claude-prompt", "v1", "--claude-exemplars"],
                base + ["--claude-exemplars-extra", "r", "d"], ["--set", "abpool", "--arm", "x", "--claude-exemplars"]):
        ap = hx.build_parser(); n = ap.parse_args(bad)
        with contextlib.redirect_stderr(io.StringIO()):
            try:
                hx.check_args(ap, n); raise AssertionError(bad)
            except SystemExit as e:
                assert e.code == 2, bad


def test_cli_counts_only():
    with tempfile.TemporaryDirectory() as td:
        W = world(pathlib.Path(td))
        cmd = [sys.executable, str(ROOT / "harness/exemplars.py"), "--work-root", str(W["wr"]), "--runs-dir", *map(str, W["runs"]),
               "--extra-root", str(W["ex"]), str(W["runs"][0].parent / "ex-*")]
        p = subprocess.run(cmd + ["--dry-run"], capture_output=True, text=True, timeout=300)
        assert p.returncode == 0, p.stderr[-800:]
        assert not (W["wr"] / EX.XDIR).exists()                                                    # dry run: nothing written
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        out = p.stdout.strip().split("\n")
        assert p.returncode == 0 and all(re.match(r"row#\d+: axis [HL], ", l) for l in out[:-1]) and len(out) == 3, p.stdout
        assert out[-1].startswith("exemplars: 5 row(s) in the work root (3 >= 90: nothing, 2 below (0 on the L axis), 0 without a best or row); 2 "
                                  "line(s), 3 run dir(s)"), out[-1]
        assert "2 exemplars file(s) written" in out[-1] and len(list((W["wr"] / EX.XDIR).glob("*.md"))) == 2, out[-1]
        for s in SECRET + ("$A", "simp_all ["):
            assert s not in p.stdout, s
        p = subprocess.run([sys.executable, str(ROOT / "harness/exemplars.py"), "--work-root", str(W["wr"]), "--extra-root",
                            str(pathlib.Path(td) / "work_abpool-z")], capture_output=True, text=True, timeout=300)
        assert p.returncode == 2 and "refused" in p.stderr                                           # another set: refused
        p = subprocess.run([sys.executable, str(ROOT / "harness/exemplars.py"), "--work-root", str(W["wr"]), "--dry-run", "--extra-root",
                            str(pathlib.Path(td) / "gone")], capture_output=True, text=True, timeout=300)
        assert p.returncode == 0 and p.stdout.strip().split("\n")[-1].startswith("exemplars WARNING: 1 extra root(s) missing"), p.stdout   # counted


def test_warmup_dry_run():
    """A read-only dry run on the warm-up root (Flash line, its agent-flash runs) with the Opus line as an extra root: counts printed; every text
    passes the leak lint over both lines' rows, carries no problem name and no line of another row's proof with an identifier of one row."""
    wr, opus = ROOT / "harness/work", ROOT / "harness/work_ccline-opus55"
    if not any(wr.glob("*/state.json")) or not any(opus.glob("*/state.json")):
        print("SKIP test_warmup_dry_run: no warm-up work roots"); return
    before = {d: sorted(p.name for p in d.rglob("*")) for d in (wr, opus)}
    runs, _ = EX.expand(["probe/runs/agent-flash-*"]); ext, _ = EX.expand(["probe/runs/ccline-opus55-p*"]); texts: dict = {}
    res = EX.build(wr, runs, [(opus, ext)], write=False, texts=texts)
    c = res["c"]
    print("  warm-up dry run: " + EX.summary(c, 90.0, True))
    assert {d: sorted(p.name for p in d.rglob("*")) for d in (wr, opus)} == before                  # read-only
    assert c["rows"] == 15 and c["written"] == len(texts) >= 1 and c["first"] >= 15 and c["edits"] >= 1 and c["strong"] >= 1, dict(c)
    files = {}
    for d in (wr, opus):
        for st in d.glob("*/state.json"):
            n = json.loads(st.read_text())["problem"]; files.setdefault(n, [st.parent / "original.lean", st.parent / "context.lean"])
    idx = EX.Index(files, list(files))
    one = {t for t, ps in idx.owner.items() if len(ps) == 1}
    leaky = set()
    for d in (wr, opus):
        for st in d.glob("*/state.json"):
            s = json.loads(st.read_text()); b = EX.body_of(s["problem"], (s.get("best") or {}).get("proof")) or ""
            leaky |= {l.strip() for l in b.split("\n") if set(re.findall(inrun.ID_RE, l)) & one and len(l.strip()) > 8}
    for k, txt in texts.items():
        assert len(txt) <= EX.CAP and idx.ok(txt.split("\n", 1)[1]) and LV.lean_block_lines(txt) <= 2, (k, len(txt))
        assert not any(n in txt for n in ROWS) and not any(l in txt for l in leaky), k
        assert "(H falls" not in txt and "(H rises" not in txt                                      # no cross-problem direction any more
    assert all(re.match(r"row#\d+: axis [HL], \d+ style line", l) for l in res["rows"])


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
