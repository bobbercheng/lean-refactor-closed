#!/usr/bin/env python3
"""Unit tests of harness/transfer.py (the transfer lane, docs/cc_driver_v2.md §12), plain asserts, no Lean, no model: leantools.lean_check is
stubbed in-process (score = 100 - body tokens; a body with `PIN` fails one of five listed toolchains; `FAIL` does not compile), so the lane's
scratch pre-check and (for the canary's incumbent) inrun.locked_check run on the stub. Fixture rows use warm-up names for their statements only.
  abstract       identifier wildcards (consistent, tactic names / keywords / numerals kept), new-side names kept only when shared and lemma-style
                 (never a local projection), identity / unbound / unanchored / bracket-unbalanced rules and lemma substitutions dropped
  mine_win       diff groups, hunks glued by the hunk-free diff split again (a real merge kept), a truncated diff's last group dropped,
                 rewrites skipped, delete / pair / span mechanisms, dedupe across rows
  apply          binding to the target's own identifiers and indentation, all-sites (2-3 sites) then single sites, pair rule, in-line deletion
                 tidied, a binder name used elsewhere is no site
  closers        terminal closer lines harvested, abstracted, tried at the target's leaf sites (wildcards bound from that line); blocks and the
                 whole proof only for a closer without wildcards that lean_mine does not try
  lane           a sweep banks strictly better pre-checked results (ledger win, verified record, no second compile), records (mechanism, best
                 sha) dispositions and hits (counts only), and a later sweep compiles nothing already tried
  promotion      equal score not banked; a lost pin not banked even when the score is higher (pre-check and bank); a best that changed between
                 the pre-check and the bank is not overwritten; the bank compiles nothing
  offsets        a pair's candidates over several visits, max_cands per visit, a restarted lane going on from the recorded offset
  live rows      an open runs[] entry (a session or a reviewer in progress) or an unused review leaves the row alone, at the scan and at the bank
  infra          a timeout / killed compile records nothing (until the second strike); kill_until_quiet
  fairness       least-scanned rows first, ties by index; the per-row time slice; a stop leaves no disposition
  feedback       mechanisms.json, the TRANSFER HITS section of the techniques file (each entry passes the leak lint), inrun.build keeps it
  mine roots     a mine root's copy of the line's own problem is skipped, the feedback lint uses the line's rows, a sealed / A/B-pool root is
                 refused across sets, run ids keep the set prefix
  operators      hb_polish / normalize as mechanisms (stubbed functions), pre-checked and banked through the same path
  cli / canary   counts-only output (row#k, never names), a dry run writes nothing; the canary finds and banks a known transfer
    python3 harness/test_transfer.py"""
from __future__ import annotations

import collections, contextlib, json, pathlib, re, subprocess, sys, tempfile, threading, time, traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import transfer as T, inrun  # noqa: E402
from harness.leantools import ROWS  # noqa: E402
from harness.cc_levers import proof_sha  # noqa: E402

A, B, C, D = "putnam_1964_b2", "putnam_1995_a3", "putnam_1964_a4", "Core.InitsUpdatesComm"
SECRET = ("foo_lemma", "bar_lemma", "baz_lemma", "qux_lemma", "foo_done", "done_b", "step_b", "PIN_c", "d_done", "alpha_one", A, B, C, D)
CALLS: list = []


def stub_check(name, decl, state, prov, vpath):
    """leantools.lean_check's contract: an attempt appended; compat and score only when the provisional beats the best; best replaced, `score` on
    the attempt and a verified record on a new best."""
    from scorer.tokenize import split_declaration, count_tokens
    from scorer.score import compat_pct
    CALLS.append(name)
    body = split_declaration(decl.rstrip(), ROWS[name]["statement"])
    if body is None:
        return {"ok": False, "errors": ["statement differs"]}
    ok = "FAIL" not in body; toks = count_tokens(body)
    att = {"ok": ok, "run_id": prov.get("run_id"), "tokens": toks, "heartbeats": 1000}
    state.setdefault("attempts", []).append(att)
    res = {"ok": ok, "tokens": toks, "heartbeats": 1000}
    if not ok:
        return res
    pv = round(100.0 - toks, 2); res["predicted_score_if_compatible"] = pv
    best = state.setdefault("best", {"score": 33.33, "proof": None})
    if pv > best.get("score", 33.33):
        compat = {f"v{k}": k < 4 or "PIN" not in body for k in range(5)}
        Z = compat_pct(compat); sc = round(pv - (100.0 - Z) / 3, 2); res.update(compat=compat, score=sc)
        if sc > best.get("score", 33.33):
            state["best"] = {"score": sc, "proof": decl, "tokens": toks, "heartbeats": 1000, "Z": Z, "compat": compat}
            att["score"] = sc; res["new_best"] = True
            if vpath:
                vpath.parent.mkdir(parents=True, exist_ok=True)
                with vpath.open("a") as f:
                    f.write(json.dumps({"problem": name, "score": sc, "provenance": prov}) + "\n")
    return res


@contextlib.contextmanager
def stubbed():
    from harness import leantools as LT
    real = LT.lean_check; LT.lean_check = stub_check; CALLS.clear()
    try:
        yield
    finally:
        LT.lean_check = real


def decl_of(name: str, body: str) -> str:
    return ROWS[name]["statement"] + " := by\n" + body


def score_of(name: str, body: str) -> float:
    from scorer.tokenize import split_declaration, count_tokens
    return round(100.0 - count_tokens(split_declaration(decl_of(name, body).rstrip(), ROWS[name]["statement"])), 2)


def win(diff: str, kind: str = "edit", ds: float = 0.5) -> dict:
    return {"diff": diff, "kind": kind, "d_score": ds, "d_tokens": -1, "d_heartbeats": 0, "sha": str(abs(hash(diff)))[:12]}


def row(wr: pathlib.Path, name: str, body: str, wins=(), files: str = "", z: float = 100.0) -> pathlib.Path:
    d = wr / inrun.dirname(name); d.mkdir(parents=True)
    st = {"problem": name, "best": {"score": score_of(name, body), "proof": decl_of(name, body), "tokens": 1, "heartbeats": 1000, "Z": z},
          "attempts": [], "runs": [], "ledger": {"wins": list(wins)}}
    (d / "state.json").write_text(json.dumps(st))
    (d / "original.lean").write_text(f"theorem {name.split('.')[-1]} : True := by\n  trivial\n{files}\n")
    (d / "context.lean").write_text("import Mathlib\n-- shared: Nat.zero_add PIN_shared_lemma\n")
    return d


A_BODY = "  rw [← foo_lemma]\n  exact foo_done"
A_WINS = [win("-  rw [← foo_lemma (F := F)]\n+  rw [← foo_lemma]"),
          win("-  classical"),
          win("-  case succ =>\n-    rename_i n ih\n+  case succ n ih =>"),
          win("-  norm_num at h\n+  simp at h"),
          win("-  " + "x\n-  ".join(["omega"] * 3) + "x\n+  grind", kind="rewrite"),
          win("-  exact alpha_one\n+  exact alpha_two")]
B_BODY = "  classical\n  rw [← bar_lemma (G := G)]\n  case succ =>\n    rename_i m ihm\n    exact step_b m ihm\n  exact done_b"
C_BODY = "  simp only [baz_lemma (H := H), qux_lemma (K := K), quux_lemma (L := L)] at h\n  exact PIN_c"   # all sites: +15 L, -6.67 Z: higher, still refused
D_BODY = "  norm_num at hx\n  exact d_done"


def world(td: pathlib.Path) -> pathlib.Path:
    wr = td / "wr"; wr.mkdir()
    row(wr, A, A_BODY, A_WINS, "def foo_lemma := 1\ndef foo_done := 2\n")
    row(wr, B, B_BODY, (), "def bar_lemma := 1\ndef step_b := 2\ndef done_b := 3\n")
    row(wr, C, C_BODY, (), "def baz_lemma := 1\ndef qux_lemma := 1\ndef PIN_c := 2\n")
    row(wr, D, D_BODY, (), "def d_done := 1\n")
    return wr


def lane(wr, **kw) -> T.Lane:
    kw.setdefault("ops", ()); kw.setdefault("jobs", 1); kw.setdefault("vpath", wr.parent / "verified.jsonl"); kw.setdefault("log", lambda *a, **k: None)
    return T.Lane(wr, **kw)


# ---- abstraction and mining ---------------------------------------------------------------------------------------------------------------
def test_lex_and_abstract():
    assert [t[1] for t in T.lex("  rw [← foo_bar (F := F)] -- note")] == ["rw", "[", "←", "foo_bar", "(", "F", ":=", "F", ")", "]"]
    assert [t[1] for t in T.lex("exact λx => h.1.2 x <;> simp?")] == ["exact", "λ", "x", "=>", "h.1.2", "x", "<;>", "simp?"]
    m = T.abstract("rule", ["  rw [← foo_bar (F := F)]"], ["  rw [← foo_bar]"], {})
    assert [T._sig(p) for p in m["pat"]] == ["rw [ ← $0 ( $1 := $1 ) ]"] and T.show(m["new"][0]) == "rw [← $A]", m
    assert T.describe(m) == "`rw [← $A ($B := $B)]` -> `rw [← $A]`"
    m = T.abstract("rule", ["  simp only [foo, bar] at h"], ["  simp only [bar] at h"], {})          # tactic names kept, consistent wildcards
    assert T._sig(m["pat"][0]) == "simp only [ $0 , $1 ] at $2" and T.show(m["new"][0]) == "simp only [$B] at $C"
    m = T.abstract("rule", ["  refine Nat.le_induction (m := 1) ?base h"], ["  refine Nat.le_induction ?base h"], {})
    assert "1" in T._sig(m["pat"][0]).split() and m["nw"] == 4                                        # numerals literal
    assert T.abstract("rule", ["  exact alpha_one"], ["  exact alpha_two"], {}) is None              # alpha_two cannot be bound
    assert T.abstract("rule", ["  exact foo"], ["  exact foo"], {}) is None                          # identity
    assert T.abstract("rule", ["  foo bar"], ["  bar foo"], {}) is None                              # no literal anchor
    assert T.abstract("rule", ["  exact (foo"], ["  exact foo"], {}) is None                         # unbalanced: its `)` sat elsewhere
    owner = {"Nat.zero_add": {"P", "Q"}, "alpha_aux": {"P"}, "s'": {"P", "Q"}, "Mine.lemma_x": set(), "Mine": {"P"}}
    m = T.abstract("rule", ["  simp at h"], ["  simp [Nat.zero_add] at h"], owner)
    assert m and "Nat.zero_add" in T.show(m["new"][0])                                              # shared: literal
    assert T.abstract("rule", ["  simp at h"], ["  simp [Nat.succ_le_of_lt] at h"], owner)          # library-style, no single owner
    assert T.abstract("rule", ["  simp at h"], ["  simp [alpha_aux] at h"], owner) is None          # one row's name
    assert T.abstract("rule", ["  exact h"], ["  use s', h"], owner) is None                        # a short local, even in 2 rows' files
    assert T.abstract("rule", ["  simp at h"], ["  simp [Mine.lemma_x] at h"], owner) is None       # its namespace is one row's
    assert T.abstract("rule", ["  exact foo_x"], ["  apply Nat.zero_add"], owner) is None           # one row's term replaced by a lemma
    assert T.abstract("rule", ["  omega"], ["  exact i.isLt"], {"i.isLt": {"P", "Q"}}) is None        # a local's projection, even in 2 rows
    s = T.span_of("  rw [← foo_bar (F := F)]", "  rw [← foo_bar]", {})
    assert s["kind"] == "span" and T.describe(s) == "inside a line `($A := $A)` -> (nothing)", T.describe(s)
    assert T.span_of("  simp", "  grind", {}) is None                                                # the whole line: the rule covers it


def test_mine_win_groups_and_dedupe():
    assert T.groups("-a\n+b\n-c\n-d\n+e\n+f\n+g\n-h") == [(["a"], ["b"]), (["c", "d"], ["e", "f", "g"]), (["h"], [])]
    kinds = lambda w: sorted(m["kind"] for m in T.mine_win(w, {}))
    assert kinds(A_WINS[0]) == ["rule", "span"] and kinds(A_WINS[1]) == ["delete"] and kinds(A_WINS[2]) == ["rule"]
    assert kinds(A_WINS[4]) == [] and kinds(A_WINS[5]) == [] and kinds(win("-  · simp")) == []        # rewrite; unbound; a bullet line
    assert kinds(win("-  simp at h\n+  grind\n-  classical")) == ["delete", "rule"]
    long = win("-  simp at h\n+  grind\n-  classical" + " " * T.DIFF_CAP)                             # diff[:700] may have cut its last line
    assert kinds(long) == ["rule"], kinds(long)
    pair = next(m for m in T.mine_win(A_WINS[2], {}) if m["kind"] == "rule")
    assert pair["rel"] == [0, 2] and pair["nrel"] == [0] and T.describe(pair) == "`case $A => ⏎ rename_i $B $C` -> `case $A $B $C =>`"
    glued = T.mine_win(win("-  classical\n-  · norm_num at h\n+  · simp at h"), {})   # two hunks: a deletion, then a one-line change
    assert sorted(m["kind"] for m in glued) == ["delete", "rule", "span"], [T.describe(m) for m in glued]
    assert {T.describe(m) for m in glued if m["kind"] != "span"} == {"delete the line `classical`", "`· norm_num at $A` -> `· simp at $A`"}
    assert [T.describe(m) for m in T.mine_win(win("-  norm_num at h\n+  simp at h\n+  classical"), {}) if m["kind"] == "rule"] == [
        "`norm_num at $A` -> `simp at $A`"]                                                         # a lone insertion after it: no mechanism
    assert [T.describe(m) for m in T.mine_win(win("-  rw [foo_a]\n-  rw [foo_b]\n+  rw [foo_a, foo_b]"), {})] == [
        "`rw [$A] ⏎ rw [$B]` -> `rw [$A, $B]`"]                                                     # a real merge stays one rule
    with tempfile.TemporaryDirectory() as td:
        wr = world(pathlib.Path(td))
        row(wr, "Cslib.SKI.parallelReduction_diamond", A_BODY, A_WINS[:1])   # the same rule won on a second row
        L = lane(wr); L.mine()
        rw = [m for m in L.mechs.values() if m["kind"] == "rule" and T.describe(m).startswith("`rw")]
        assert len(rw) == 1 and len(rw[0]["src"]) == 2 and rw[0]["wins"] == 2, [(T.describe(m), m["src"]) for m in rw]


# ---- application --------------------------------------------------------------------------------------------------------------------------
def test_apply_binding_sites_and_spans():
    stmt = ROWS[B]["statement"]
    rule = T.abstract("rule", ["  rw [← foo_lemma (F := F)]"], ["  rw [← foo_lemma]"], {})
    c = T.rule_cands(rule, decl_of(B, B_BODY), stmt)
    assert c == [decl_of(B, B_BODY.replace("rw [← bar_lemma (G := G)]", "rw [← bar_lemma]"))], c
    two = "  rw [← p_one (G := G)]\n  · rw [← p_two (K := K)]\n    rw [← p_three (K := K)]"
    c = T.rule_cands(rule, decl_of(B, two), stmt)
    assert len(c) == 3 and c[0] == decl_of(B, "  rw [← p_one]\n  · rw [← p_two (K := K)]\n    rw [← p_three]"), c   # all sites, then singles
    assert T.rule_cands(rule, decl_of(B, two), stmt, cap=2) == c[:2]
    pair = next(m for m in T.mine_win(A_WINS[2], {}) if m["kind"] == "rule")
    c = T.rule_cands(pair, decl_of(B, B_BODY), stmt)
    assert c == [decl_of(B, B_BODY.replace("  case succ =>\n    rename_i m ihm\n", "  case succ m ihm =>\n"))], c
    assert T.rule_cands(pair, decl_of(B, "  case succ =>\n      rename_i m ihm"), stmt) == []        # relative indentation differs
    span = T.span_of("  rw [← foo_lemma (F := F)]", "  rw [← foo_lemma]", {})
    c = T.rule_cands(span, decl_of(B, "  simp only [q_lemma (G := G), r_lemma (K := K)] at h"), stmt)
    assert c[0] == decl_of(B, "  simp only [q_lemma, r_lemma] at h") and len(c) == 3, c
    dl = T.mine_win(A_WINS[1], {})[0]
    assert T.rule_cands(dl, decl_of(B, "  classical\n  exact h"), stmt) == [decl_of(B, "  exact h")]
    assert T.rule_cands(dl, decl_of(B, "  classical\n    exact h"), stmt) == []                     # never orphan continuation lines
    assert T.rule_cands(rule, "theorem other : True := by\n  rw [← a (F := F)]", stmt) == []         # statement differs
    many = "\n".join(f"  rw [← p_{k} (G := G)]" for k in range(5))
    c = T.rule_cands(rule, decl_of(B, many), stmt)                                                  # > 3 sites: single sites only, in order
    assert len(c) == 5 and c[0] == decl_of(B, many.replace("p_0 (G := G)", "p_0")) and c[4] == decl_of(B, many.replace("p_4 (G := G)", "p_4"))
    hv = T.span_of("  have h_one (k : Nat) : k = k := by", "  haveI (k : Nat) : k = k := by", {})
    assert T.describe(hv) == "inside a line `have $A` -> `haveI`" and hv["bind"] == [0], (T.describe(hv), hv["bind"])
    assert T.rule_cands(hv, decl_of(B, "  have t_h : True := by\n    trivial\n  exact t_h"), stmt) == []   # its name is used later
    assert T.rule_cands(hv, decl_of(B, "  have t_h : True := by\n    trivial\n  exact done_b"), stmt) == [
        decl_of(B, "  haveI : True := by\n    trivial\n  exact done_b")]


def test_closer_harvest_and_application():
    body = (" by\n  constructor\n  · simp_all\n  · exact s_two\n  have k : a = b := by simp\n  all_goals first | rfl | omega\n"
            "  case inr h => simpa using hx_s\n  rw [x]\n  omega")
    assert T.closer_lines(body) == ["simp_all", "all_goals first | rfl | omega", "simpa using hx_s", "omega"], T.closer_lines(body)
    assert T.closer_lines(" by grind") == ["grind"]
    assert T.closer_lines("  exact ⟨t_a,\n    t_b⟩") == [] and T.closer_lines("  simp [t_a,\n    t_b]") == []   # inside a term: no tactic
    m = T.closer_mech("simpa using hx_s", {})
    assert m["nw"] == 1 and T.describe(m) == "closer `simpa using $A` in place of a goal's last tactic"
    assert T.closer_mech("grind [p_a, p_b, p_c]", {}) is None                                         # > MAX_CLOSER_WILD wildcards
    assert T.show(T.closer_mech("grind [Nat.zero_add]", {"Nat.zero_add": {"P", "Q"}})["new"][0]) == "grind [Nat.zero_add]"
    stmt = ROWS[B]["statement"]
    tgt = decl_of(B, "  have key : t_alpha = t_beta := by\n    rw [t_def]\n    exact t_trans (t_aux t_alpha)\n  exact key")
    c = T.closer_cands(T.closer_mech("simp_all", {}), tgt, stmt)   # leaf sites only, largest saving first: lean_mine tries simp_all on blocks
    assert c == [tgt.replace("exact t_trans (t_aux t_alpha)", "simp_all"), tgt.replace("  exact key", "  simp_all")], c
    c = T.closer_cands(T.closer_mech("rfl", {}), tgt, stmt)        # not one of lean_mine's closers: then also blocks and the whole proof
    assert c[:2] == [tgt.replace("exact t_trans (t_aux t_alpha)", "rfl"), tgt.replace("  exact key", "  rfl")], c[:2]
    assert c[2] == stmt + " := by rfl" and decl_of(B, "  have key : t_alpha = t_beta := by rfl\n  exact key") in c[3:], c[2:]
    c = T.closer_cands(m, tgt, stmt)                               # wildcards bound from the replaced line's own names
    assert tgt.replace("exact t_trans (t_aux t_alpha)", "simpa using t_aux") in c and all("hx_s" not in x and "using key" not in x for x in c)
    assert T.closer_cands(T.closer_mech("simp_all", {}), decl_of(B, "  simp"), stmt) == []           # no saving: no candidate


# ---- the lane -----------------------------------------------------------------------------------------------------------------------------
def test_sweep_banks_records_and_dedupes():
    with tempfile.TemporaryDirectory() as td, stubbed():
        wr = world(pathlib.Path(td)); logs = []
        L = lane(wr, log=logs.append)
        c = L.sweep()
        stB = json.loads((wr / B / "state.json").read_text())
        assert stB["best"]["proof"] == decl_of(B, "  rw [← bar_lemma]\n  case succ m ihm =>\n    exact step_b m ihm\n  exact done_b"), stB["best"]["proof"]
        assert c["hits"] == 3 and {k for k in c if k.startswith("hit:")} == {"hit:rule", "hit:delete"}, c
        assert len(stB["ledger"]["wins"]) == 3 and all(w["source"] == "v2-check" and w["run_id"] == L.run_id for w in stB["ledger"]["wins"])
        assert (wr / B / "best.lean").exists() and len((wr.parent / "verified.jsonl").read_text().splitlines()) == 3
        assert stB["best"]["Z"] == 100.0 and not any(a.get("run_id") is None for a in stB["attempts"])
        for n in (C, D):   # PIN loses a pin (Z guard), D's rule only ties
            st = json.loads((wr / inrun.dirname(n) / "state.json").read_text())
            assert st["best"]["score"] == score_of(n, {C: C_BODY, D: D_BODY}[n]) and st["attempts"] == [], n
        xd = wr / T.XDIR; disp = [json.loads(l) for l in (xd / "dispositions.jsonl").read_text().splitlines()]
        assert {d["row"] for d in disp} == {inrun.src_key(inrun.dirname(n)) for n in (B, C, D)} and sum(d["hit"] for d in disp) == 3
        hits = [json.loads(l) for l in (xd / "hits.jsonl").read_text().splitlines()]
        assert [h["i"] for h in hits] == [3, 3, 3] and all(set(h) == {"m", "k", "row", "i", "d", "t"} for h in hits)
        blob = "".join(p.read_text() for p in xd.iterdir() if p.is_file()) + "\n".join(logs)
        for s in SECRET:
            assert s not in blob, s
        assert logs and all(re.fullmatch(r"transfer hit: row#\d+ \w+ [+-]\d+\.\d\d", x) for x in logs), logs
        n0 = len(CALLS); c2 = lane(wr).sweep()                    # a fresh lane on the same root: everything was tried on these bests
        assert len(CALLS) == n0 and c2["pairs"] == 0 and c2["compiled"] == 0, (len(CALLS) - n0, c2)
        st = json.loads((wr / inrun.dirname(D) / "state.json").read_text()); st["best"]["proof"] = decl_of(D, "  norm_num at hy\n  exact d_done")
        (wr / inrun.dirname(D) / "state.json").write_text(json.dumps(st))
        c3 = lane(wr).sweep()                                     # a new best (sha) on one row: only its pairs run again
        assert c3["pairs"] >= 1 and len({x for x in CALLS[n0:]}) == 1 and CALLS[n0] == D, (c3, CALLS[n0:])


def test_parallel_rows_and_follow_loop():
    finals = []
    for jobs in (1, 4):   # rows in parallel (one compile each, per-row state locks): the same bests as one at a time
        with tempfile.TemporaryDirectory() as td, stubbed():
            wr = world(pathlib.Path(td)); c = lane(wr, jobs=jobs).sweep()
            finals.append((c["hits"], [json.loads((wr / inrun.dirname(n) / "state.json").read_text())["best"]["proof"] for n in (A, B, C, D)]))
    assert finals[0] == finals[1] and finals[0][0] == 3, finals
    with tempfile.TemporaryDirectory() as td, stubbed():   # --follow: a sweep per poll until the deadline; a new best between polls is picked up
        wr = world(pathlib.Path(td)); now = [0.0]; said = []; w = wr / inrun.dirname(D)

        def sleep(s):
            now[0] += s
            if now[0] == 300.0:   # a session's new best on D, between the first and the second sweep
                st = json.loads((w / "state.json").read_text()); st["best"]["proof"] = decl_of(D, "  norm_num at hz\n  exact d_done")
                (w / "state.json").write_text(json.dumps(st))
        L = lane(wr, clock=lambda: now[0], deadline=1500.0)
        k = T.run_loop(L, 1, True, 600.0, said.append, sleep=sleep)
        assert k == 3 and len(said) == 3 and all(s.startswith(f"transfer sweep {i + 1}:") for i, s in enumerate(said)), said
        assert " 3 hit(s) banked" in said[0] and " 0 (mechanism, best) pair(s)" in said[2], said
        assert " 2 (mechanism, best) pair(s) tried, 2 candidate(s), 1 compiled;" in said[1], said[1]   # rule and span: the same text, one compile
        assert T.run_loop(lane(wr), 2, False, 600.0, said.append, sleep=sleep) == 2 and now[0] == 1500.0   # --sweeps: no waiting
        for s in said:
            assert not any(x in s for x in SECRET), s


def test_strict_promotion_and_changed_best():
    best = {"score": 70.0, "Z": 100.0}
    ok5 = {f"v{k}": True for k in range(5)}; pin = dict(ok5, v4=False)
    assert T.verdict({"ok": True, "score": 71.0, "compat": ok5}, best) == 71.0
    assert T.verdict({"ok": True, "score": 70.0, "compat": ok5}, best) is None                       # equal: not strictly better
    assert T.verdict({"ok": True, "score": 75.0, "compat": pin}, best) is None                       # higher, but a pin lost
    assert T.verdict({"ok": True, "score": 75.0, "compat": pin}, {"score": 70.0, "Z": 80.0}) == 75.0  # the best had lost it already
    assert T.verdict({"ok": True, "score": 75.0}, best) is None and T.verdict({"ok": False, "score": 99.0, "compat": ok5}, best) is None
    assert T.verdict({"ok": True, "predicted_score_if_compatible": 99.0}, best) is None                # no full score: did not beat the best
    with tempfile.TemporaryDirectory() as td, stubbed():   # the bank commits the pre-checked result: no compile under the lock
        wr = world(pathlib.Path(td)); w = wr / B; before = (w / "state.json").read_text(); sha0 = proof_sha(decl_of(B, B_BODY))
        res = T.default_precheck(B, decl_of(B, "  exact done_b"), score_of(B, B_BODY), {"run_id": "x"})
        assert res["_bank"]["best"]["proof"] == decl_of(B, "  exact done_b") and res["_bank"]["record"] and CALLS == [B]
        assert (w / "state.json").read_text() == before                                             # the pre-check recorded nothing
        assert T.default_bank(w, B, res, {"run_id": "x"}, None, "0" * 12) == {"skipped": "changed"}
        lost = dict(res, compat=dict(res["compat"], v4=False))                                      # a pin lost since: never banked
        assert T.default_bank(w, B, lost, {"run_id": "x"}, None, sha0) == {"skipped": "not better"}
        assert T.default_bank(w, B, {"ok": True}, {"run_id": "x"}, None, sha0) == {"skipped": "no checked result"}
        assert (w / "state.json").read_text() == before and not (w / "best.lean").exists()
        vp = pathlib.Path(td) / "v.jsonl"; r = T.default_bank(w, B, res, {"run_id": "x"}, vp, sha0)
        st = json.loads((w / "state.json").read_text())
        assert r["new_best"] and r["score"] == res["score"] and CALLS == [B]                         # banked without a second compile
        assert st["best"]["proof"] == decl_of(B, "  exact done_b") and [a["run_id"] for a in st["attempts"]] == ["x"]
        assert len(st["ledger"]["wins"]) == 1 and st["ledger"]["wins"][0]["run_id"] == "x" and (w / "best.lean").exists()
        assert len(vp.read_text().splitlines()) == 1 and json.loads(vp.read_text())["provenance"]["run_id"] == "x"
    with tempfile.TemporaryDirectory() as td, stubbed():   # a bank refusal other than a moved best is a miss: recorded, never retried in a loop
        wr = world(pathlib.Path(td))
        c = lane(wr, rows_filter={B}, bank=lambda *a: {"skipped": "not better"}, deadline=time.time() + 60).sweep()
        assert c["hits"] == 0 and c["pairs"] >= 3 and c["cut"] == 0, c
        assert json.loads((wr / B / "state.json").read_text())["best"]["proof"] == decl_of(B, B_BODY)
    with tempfile.TemporaryDirectory() as td, stubbed():   # a session banks a new best between the lane's pre-check and its bank
        wr = world(pathlib.Path(td)); w = wr / B; sess = decl_of(B, "  exact done_b")
        def pre(name, decl, score, prov):
            if name == B and json.loads((w / "state.json").read_text())["best"]["proof"] != sess:
                inrun.locked_check(w, B, sess, {"run_id": "session"}, None)
            return T.default_precheck(name, decl, score, prov)
        c = lane(wr, rows_filter={B}, precheck=pre).sweep()
        st = json.loads((w / "state.json").read_text())
        assert st["best"]["proof"] == sess and c["hits"] == 0, (c, st["best"]["proof"][-60:])
        assert [a["run_id"] for a in st["attempts"]] == ["session"]                                  # the lane's bank compiled nothing
        disp = (wr / T.XDIR / "dispositions.jsonl").read_text().splitlines() if (wr / T.XDIR / "dispositions.jsonl").exists() else []
        assert all(json.loads(l)["b"] != proof_sha(decl_of(B, B_BODY)) for l in disp)             # nothing recorded against the old best


def test_pair_offsets():
    many = "\n".join(f"  rw [← p_{k} (G := G)]" for k in range(5)) + "\n  exact done_b"
    with tempfile.TemporaryDirectory() as td, stubbed():
        wr = pathlib.Path(td) / "wr"; wr.mkdir(); stmt = ROWS[B]["statement"]
        row(wr, A, A_BODY, A_WINS[:1], "def foo_lemma := 1\n"); row(wr, B, many)
        good = decl_of(B, many.replace("p_4 (G := G)", "p_4")); tried = []

        def pre(name, decl, score, prov):   # only the last site's candidate checks
            tried.append(decl)
            return T.default_precheck(name, decl, score, prov) if decl == good else {"ok": False, "errors": ["1:1: no"]}
        L = lane(wr, rows_filter={B}, mine_rows={A}, precheck=pre, max_cands=2); L.mine()
        m = next(x for x in L.mechs.values() if x["kind"] == "rule"); rb = next(r for r in L.rows if r["problem"] == B)
        best = json.loads((wr / B / "state.json").read_text())["best"]; sha = proof_sha(best["proof"]); c = collections.Counter()
        cands = L.candidates(m, best["proof"], stmt)
        assert len(cands) == 5 and cands[4] == good
        assert L.try_pair(rb, m, best, sha, stmt, {}, c) == "more" and L.offset[(m["id"], sha)] == 2
        L2 = lane(wr, rows_filter={B}, mine_rows={A}, precheck=pre, max_cands=2)   # a restarted lane goes on from the recorded offset
        assert L2.offset[(m["id"], sha)] == 2 and (m["id"], sha) not in L2.done
        L2.mine(); m2 = L2.mechs[m["id"]]
        assert L2.try_pair(rb, m2, best, sha, stmt, {}, c) == "more" and L2.try_pair(rb, m2, best, sha, stmt, {}, c) == "banked"
        assert tried == cands and (m["id"], sha) in L2.done and c["hits"] == 1                    # each candidate compiled once, over 3 visits
        disp = [json.loads(l) for l in (wr / T.XDIR / "dispositions.jsonl").read_text().splitlines()]
        assert [(d["next"], d["all"], d["cand"]) for d in disp] == [(2, 0, 2), (4, 0, 2), (5, 1, 1)], disp
        assert json.loads((wr / B / "state.json").read_text())["best"]["proof"] == good


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def test_live_rows_left_alone():
    from harness import cc_levers as LV
    now = time.time()
    with tempfile.TemporaryDirectory() as td:
        w = pathlib.Path(td)
        assert T.live({"runs": []}, w) is None and T.live({}, w) is None
        assert T.live({"runs": [{"run_id": "s", "started": _iso(now - 60)}]}, w) == "session"
        for end in ({"ended": _iso(now)}, {"best_after": 50.0}, {"skipped": "budget"}):
            assert T.live({"runs": [dict({"run_id": "s", "started": _iso(now - 60)}, **end)]}, w) is None, end
        assert T.live({"runs": [{"run_id": "s", "started": _iso(now - T.LIVE_H * 3600 - 60)}]}, w) is None   # a driver that died
        best = {"proof": decl_of(B, B_BODY)}
        (w / "review.md").write_text(LV.review_header(proof_sha(best["proof"]), "rv", _iso(now), {"levers": 1}) + "\n1. a lever\n")
        st = {"best": best, "runs": [{"run_id": "rv", "kind": "review", "started": _iso(now - 60), "ended": _iso(now)}]}
        assert T.live(st, w) == "review"                                                          # a paid review not used yet
        st["runs"].append({"run_id": "ex", "started": _iso(now), "ended": _iso(now)})
        assert T.live(st, w) is None                                                              # an executor session used it
    with tempfile.TemporaryDirectory() as td, stubbed():
        wr = world(pathlib.Path(td)); sp = wr / B / "state.json"; s = json.loads(sp.read_text())
        s["runs"] = [{"run_id": "s1", "started": _iso(now)}]; sp.write_text(json.dumps(s))
        c = lane(wr, rows_filter={B}).sweep()
        assert c["live"] == 1 and c["pairs"] == 0 and CALLS == [] and json.loads(sp.read_text())["best"]["proof"] == decl_of(B, B_BODY), c
        s["runs"][0]["ended"] = _iso(now); sp.write_text(json.dumps(s))

        def pre(name, decl, score, prov):   # a session starts while the lane pre-checks: the bank leaves the row alone
            st = json.loads(sp.read_text()); st["runs"].append({"run_id": "s2", "started": _iso(time.time())}); sp.write_text(json.dumps(st))
            return T.default_precheck(name, decl, score, prov)
        c = lane(wr, rows_filter={B}, precheck=pre).sweep()
        assert c["live"] == 1 and c["hits"] == 0 and c["pairs"] <= 1 and CALLS, c                   # at most the pair already under way
        assert json.loads(sp.read_text())["best"]["proof"] == decl_of(B, B_BODY)


def test_infra_failures_record_nothing():
    assert T._infra({"errors": ["timeout"]}) and T._infra({"errors": ["lean exit -9: killed"]})
    assert T._infra({"ok": True, "compat_failures": {"v4": {"errors": ["timeout"]}}})
    assert not T._infra({"errors": ["3:4: unknown identifier"]}) and not T._infra({"errors": ["lean exit 1: x"]}) and not T._infra({})
    with tempfile.TemporaryDirectory() as td, stubbed():
        wr = world(pathlib.Path(td)); n = [0]

        def pre(name, decl, score, prov):
            n[0] += 1; return {"ok": False, "errors": ["timeout"]}
        L = lane(wr, rows_filter={B}, precheck=pre); c = L.sweep()
        assert c["infra"] == 1 and c["pairs"] == 0 and n[0] == 1 and not (wr / T.XDIR / "dispositions.jsonl").exists(), c
        c = L.sweep()                                                                              # the second strike: a real timeout, recorded
        assert c["pairs"] == 1 and c["infra"] == 1, c
    seq = [2, 1, 0, 0, 5]; real = T.kill_own
    T.kill_own = lambda: seq.pop(0)
    try:
        assert T.kill_until_quiet(sleep=lambda s: None) == 3 and seq == [5]                         # until two quiet rounds in a row
    finally:
        T.kill_own = real


def test_mine_roots_and_sets():
    E = "Cslib.SKI.parallelReduction_diamond"
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td); wr = world(td); mr = td / "other"; mr.mkdir()
        row(mr, E, "  simp at h_e\n  exact e_done", [win("-  simp at h_e\n+  simp [special_lemma] at h_e")], "def special_lemma := 1\n")
        row(mr, A, A_BODY, [win("-  norm_num")])                                                    # another line's copy of the line's own A
        p = wr / inrun.dirname(B) / "original.lean"; p.write_text(p.read_text() + "def special_lemma := 2\n")
        L = lane(wr, mine_roots=[mr]); L.mine()
        ds = [T.describe(m) for m in L.mechs.values()]
        assert "`simp at $A` -> `simp [special_lemma] at $A`" in ds and "delete the line `norm_num`" not in ds, ds
        m = next(m for m in L.mechs.values() if "special_lemma" in T.describe(m)); L.hits[m["id"]] = [("k", 1.0)]
        fb, rej = L.feedback()
        assert fb == [] and rej["single-problem-identifier"] == 1, (fb, rej)                       # only B among the line's rows has it
        assert inrun.leak_lint(T.describe(m), L.line_index[2], L.owner, None, None) is None         # (the union index would let it through)
        sealed = td / "work_sealed3-x"; sealed.mkdir()
        for bad in (dict(root=wr, mine_roots=[sealed]), dict(root=sealed, mine_roots=[td / "abpool-y"]), dict(root=sealed, run_id="x-xfer")):
            try:
                T.Lane(bad.pop("root"), **bad); raise AssertionError(bad)
            except ValueError:
                pass
        assert T.Lane(sealed).run_id == "sealed3-x-xfer" and T.Lane(sealed, mine_roots=[td / "sealed3-y", wr]).run_id == "sealed3-x-xfer"
        assert T.Lane(wr).run_id == "wr-xfer" and T.set_tag(wr) is None and T.set_tag(sealed / "sub") == "sealed3"
        assert not T.canary(sealed, {"source": A, "target": B})["pass"]


def test_fairness_slice_and_stop():
    with tempfile.TemporaryDirectory() as td:
        wr = world(pathlib.Path(td)); L = lane(wr); L.mine()
        L.rowstat = {inrun.src_key(inrun.dirname(B)): {"slices": 2}, inrun.src_key(inrun.dirname(D)): {"slices": 1}}
        assert [r["problem"] for r in L.scan_rows()] == [C, A, D, B]                                  # fewest slices first, then row index
        F = lane(wr, rows_filter={B, D}); F.mine()
        assert [r["problem"] for r in F.scan_rows()] == [D, B] and [r["i"] for r in F.scan_rows()] == [0, 3]
    with tempfile.TemporaryDirectory() as td, stubbed():
        wr = world(pathlib.Path(td)); now = [0.0]
        def pre(*a):
            now[0] += 1000.0; return T.default_precheck(*a)
        L = lane(wr, rows_filter={B}, clock=lambda: now[0], slice_s=900.0, deadline=1e12, precheck=pre)
        c = L.sweep()
        assert c["pairs"] == 1 and c["hits"] == 1 and c["cut"] == 1, c                              # the first pair finishes, then the slice ends
        assert L.rowstat[inrun.src_key(inrun.dirname(B))]["slices"] == 1
        c = L.sweep(); assert c["pairs"] == 1, c                                                     # the next sweep goes on where it stopped
    with tempfile.TemporaryDirectory() as td, stubbed():
        wr = world(pathlib.Path(td)); stop = threading.Event()
        def pre(*a):
            stop.set(); return T.default_precheck(*a)
        c = lane(wr, rows_filter={B}, precheck=pre, stop=stop).sweep()
        assert c["pairs"] == 0 and c["hits"] == 0 and not (wr / T.XDIR / "dispositions.jsonl").exists(), c   # stopped: nothing recorded
        assert json.loads((wr / B / "state.json").read_text())["best"]["proof"] == decl_of(B, B_BODY)


def test_feedback_section_and_leak_lint():
    with tempfile.TemporaryDirectory() as td, stubbed():
        wr = world(pathlib.Path(td)); L = lane(wr); L.sweep()
        mj = json.loads((wr / T.XDIR / "mechanisms.json").read_text())
        fb = list(mj["feedback"])
        assert fb and {f["kind"] for f in fb} == {"rule", "delete"} and all(f["hits"] == 1 and f["rows"] == 1 for f in fb), fb
        for f in fb:
            assert inrun.leak_lint(f["pattern"], L.line_index[2], L.line_index[0], None, L.line_index[1]) is None, f
        assert any(m["hits"] == 0 and m["applications"] >= 1 for m in mj["mechanisms"]) and all("src" not in m for m in mj["mechanisms"])
        tech = inrun.load(wr); assert tech["transfer"] == fb
        txt = inrun.render(tech)
        assert "TRANSFER HITS" in txt and "`rw [← $A ($B := $B)]` -> `rw [← $A]`: 1 hit(s) on 1 row(s), +" in txt and len(txt) <= inrun.TECH_CAP
        blob = json.dumps(mj) + txt
        for s in SECRET:
            assert s not in blob, s
        t = inrun.build(wr, [], runs_dir=pathlib.Path(td) / "runs", toolchain_of=lambda n: "v", rows={})
        assert t["transfer"] == fb                                                                   # a rebuilt techniques file keeps them
        mj["feedback"].append({"pattern": "use `foo_lemma` here", "hits": 1, "rows": 1, "d_score": 1.0})   # one row's identifier
        (wr / T.XDIR / "mechanisms.json").write_text(json.dumps(mj))
        assert inrun.build(wr, [], runs_dir=pathlib.Path(td) / "runs", toolchain_of=lambda n: "v", rows={})["transfer"] == fb
        inrun.write(wr, dict(t, transfer=[])); T.write_techniques(wr, fb)                           # the lane rewrites only its key
        assert inrun.load(wr)["transfer"] == fb and inrun.load(wr)["problems"] == t["problems"]
        assert sorted(p.name for p in wr.iterdir() if p.is_file()) == ["_run_techniques.json"]   # atomic writes leave no temp file


def test_operators():
    calls = []
    def polish(name, decl, best):
        calls.append(name)
        return decl.replace("\n  exact d_done", "") if name == D and "exact d_done" in decl else None
    with tempfile.TemporaryDirectory() as td, stubbed():
        wr = world(pathlib.Path(td))
        L = lane(wr, rows_filter={D}, ops=("hb_polish", "normalize"), op_fns={"hb_polish": polish, "normalize": lambda n, d, b: None})
        c = L.sweep()
        assert c["hit:operator"] == 1 and json.loads((wr / inrun.dirname(D) / "state.json").read_text())["best"]["proof"] == decl_of(D, "  norm_num at hx")
        assert calls == [D, D], calls                                                               # once on the old best, once on the new
        L.sweep(); assert calls == [D, D], calls                                                    # (operator, best sha) tried once
        assert any(m["kind"] == "operator" and m["hits"] == 1 for m in json.loads((wr / T.XDIR / "mechanisms.json").read_text())["mechanisms"])


def test_cli_dry_run_counts_only():
    with tempfile.TemporaryDirectory() as td:
        wr = world(pathlib.Path(td))
        p = subprocess.run([sys.executable, str(ROOT / "harness/transfer.py"), "--work-root", str(wr), "--dry-run"], capture_output=True, text=True,
                           timeout=300)
        assert p.returncode == 0, p.stderr[-800:]
        assert p.stdout.startswith("transfer dry run: 4 row(s)") and "pair(s) pending on 4 row(s)" in p.stdout, p.stdout   # operators on every row
        for s in SECRET + ("$A", "rw ["):
            assert s not in p.stdout, s
        assert not (wr / T.XDIR).exists() and sorted(x.name for x in wr.iterdir()) == sorted(inrun.dirname(n) for n in (A, B, C, D))
        c = collections.Counter(hits=2, rows=3, pairs=5, candidates=6, compiled=5, gain=1.5)
        line = T.summary(1, c, lane(wr))
        assert line.startswith("transfer sweep 1: 3 row(s) scanned") and "2 hit(s) banked (summed gain +1.50)" in line


def test_canary():
    with tempfile.TemporaryDirectory() as td, stubbed():
        wr = world(pathlib.Path(td)); snap = {p: p.read_bytes() for p in wr.rglob("*") if p.is_file()}
        r = T.canary(wr, {"source": A, "target": B})
        assert r["pass"] and r["hits"] == 3 and r["mechanisms"] >= 4 and r["gain"] > 0, r
        assert {p: p.read_bytes() for p in wr.rglob("*") if p.is_file()} == snap and not (ROOT / "probe/runs/transfer-canary").exists()
        assert not T.canary(wr, {"source": D, "target": B})["pass"]                                  # nothing to transfer from D
        assert not T.canary(wr, {"source": A, "target": "no.such.row"})["pass"]
        (pathlib.Path(td) / "inc.lean").write_text(decl_of(C, "  rw [← baz_lemma (H := H)]\n  exact c_done"))
        r = T.canary(wr, {"source": A, "target": C, "target_best": "inc.lean"}, pathlib.Path(td))   # an incumbent installed by one check
        assert r["pass"] and r["hits"] == 1, r


def test_warmup_root_read_only():
    wr = ROOT / "harness/work"
    if not any(wr.glob("*/state.json")):
        print("SKIP test_warmup_root_read_only: no warm-up work root"); return
    before = sorted(p.name for p in wr.iterdir())
    L = T.Lane(wr, write=False, log=lambda *a, **k: None); c = L.dry_run()
    kinds = {m["kind"] for m in L.mechs.values()}
    assert {"rule", "operator", "closer"} <= kinds and c["rows"] >= 1 and c["pairs_pending"] >= 1, (kinds, c)
    assert all(len(m["pat"]) <= 2 for m in L.mechs.values() if m.get("pat")) and sorted(p.name for p in wr.iterdir()) == before


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
