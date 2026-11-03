#!/usr/bin/env python3
"""Unit tests of harness/inrun.py (in-run learning, driver v2 round 2, docs/cc_driver_v2.md §9), plain asserts, no Lean, no git, no model
(leantools.lean_check is stubbed in-process for the locked check).
  ledger_win     agent.py's winning-edit record with discover's body diff: sha identical to discover's, edit vs rewrite, dedupe, newest 30
  locked_check   a stubbed check under the state lock: ledger win on a new best, `axis` and `progress` in the result
  leak_lint      lean-block / problem-name / single-problem-identifier, shared identifiers and tactic words pass
  build          patterns only when confirmed on >= 2 problems (identifiers stripped, shared library names kept), GENERAL notes through the
                 lint (dedupe, counts of rejections), closer prices per toolchain (n >= 2 one-line blocks), operational fixes from trajectories
                 (resolved only, class + canned fix: no command or error text), nothing problem-specific in the file, written inside the work
                 root only; render() capped; the CLI prints counts only
    python3 harness/test_inrun.py"""
from __future__ import annotations

import gzip, hashlib, json, pathlib, subprocess, sys, tempfile, traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import inrun  # noqa: E402

P = "putnam_1964_b2"


def test_ledger_win_matches_discover():
    from harness.discover import diff, body
    from harness.leantools import ROWS
    row = ROWS[P]; stmt = row["statement"]
    prev = {"score": 50.0, "proof": stmt + " := by\n  simp\n  have h := 1\n  omega", "tokens": 10, "heartbeats": 500}
    new = {"score": 52.5, "proof": stmt + " := by\n  simp\n  have h := 1\n  grind", "tokens": 9, "heartbeats": 400}
    w = inrun.ledger_win(P, prev, new, "run-a", 7)
    want = "\n".join(diff(body(prev["proof"], row), body(new["proof"], row)))[:700]
    assert w["diff"] == want == "-  omega\n+  grind" and w["sha"] == hashlib.sha256(want.encode()).hexdigest()[:12], w
    assert (w["kind"], w["d_score"], w["d_tokens"], w["d_heartbeats"], w["check"], w["source"]) == ("edit", 2.5, -1, -100, 7, "v2-check")
    r = inrun.ledger_win(P, {"score": 33.33, "proof": None}, new, "run-a", 1)
    assert r["kind"] == "rewrite" and r["d_tokens"] == 9 - row["proof_length"]
    st = {}
    assert inrun.append_win(st, w) and not inrun.append_win(st, dict(w)) and not inrun.append_win(st, r)
    assert len(st["ledger"]["wins"]) == 1
    for k in range(40):
        inrun.append_win(st, dict(w, sha=f"s{k}"))
    assert len(st["ledger"]["wins"]) == 30 and st["ledger"]["wins"][-1]["sha"] == "s39"


def test_locked_check_ledger_axis_progress():
    from harness import leantools as LT
    from harness.leantools import ROWS
    stmt = ROWS[P]["statement"]; real = LT.lean_check

    def stub(name, decl, state, prov, vpath):   # leantools' contract: attempts appended, best replaced and score set on a new best
        ok = "FAIL" not in decl; sc = float(decl.rsplit("SCORE ", 1)[1]) if ok else None
        att = {"ok": ok, "run_id": prov["run_id"], "tokens": 9, "heartbeats": 3000}
        state["attempts"].append(att); res = {"ok": ok, "tokens": 9, "heartbeats": 3000}
        if ok and sc > state["best"]["score"]:
            state["best"] = {"score": sc, "proof": decl, "tokens": 9, "heartbeats": 3000}; att["score"] = sc; res["new_best"] = True
        return res
    LT.lean_check = stub
    try:
        with tempfile.TemporaryDirectory() as td:
            w = pathlib.Path(td)
            (w / "state.json").write_text(json.dumps({"problem": P, "best": {"score": 50.0, "proof": stmt + " := by\n  simp\n  omega -- SCORE 50",
                                                                             "tokens": 10, "heartbeats": 4000}, "attempts": [], "runs": [], "hb_floor": 1000}))
            prov = {"run_id": "r1"}
            res = inrun.locked_check(w, P, stmt + " := by\n  simp\n  grind -- SCORE 55", prov, None)
            st = json.loads((w / "state.json").read_text())
            assert res["new_best"] and len(st["ledger"]["wins"]) == 1 and st["ledger"]["wins"][0]["kind"] == "edit", st.get("ledger")
            assert (w / "best.lean").read_text().endswith("SCORE 55\n")
            ax = res["axis"]
            assert ax["heartbeat_floor"] == 1000 and ax["points_left_heartbeats"] > 0 and ax["one_token_equals_heartbeats"] > 0
            assert res["progress"]["checks_since_new_best"] == 0 and res["progress"]["checks_this_session"] == 1
            res = inrun.locked_check(w, P, stmt + " := by\n  FAIL", prov, None)
            assert "axis" not in res and res["progress"]["checks_since_new_best"] == 1 and not res["progress"]["may_finish"]
    finally:
        LT.lean_check = real


def test_leak_lint():
    owner = {"alpha_helper": {"A"}, "shared_helper": {"A", "B"}, "Foo.alpha_helper": {"A"}}
    terms = inrun.name_terms(["Foo.alpha_lemma", "Cslib.Typing.progress"], {"Foo.alpha_lemma": {"file_path": "Foo/AlphaFile.lean"}})
    assert {"Foo.alpha_lemma", "alpha_lemma", "AlphaFile"} <= terms and "progress" not in terms   # a plain-word short name is not a term
    L = lambda t: inrun.leak_lint(t, terms, owner)
    assert L("prefer `simp only` lists over bare `simp_all` on small references") is None
    assert L("`shared_helper` is a simp lemma in this project") is None                      # in two problems' files
    assert L("alpha_helper closes the base case") == "single-problem-identifier"
    assert L("use `Foo.alpha_helper` here") == "single-problem-identifier"
    assert L("the alpha_lemma trick: induct twice") == "problem-name"
    assert L("see AlphaFile for the idiom") == "problem-name"
    assert L("works:\n```lean\n  simp at h\n  exact h\n  omega\n```") == "lean-block"
    assert L("works: `simp at h; exact h`") is None                                           # one line of code is fine
    assert L("make progress with omega first") is None
    # round-2 review (2026-10-12): flush-left code, tactics the first list missed, and non-consecutive code lines all count
    assert L("- GENERAL: this closes it:\nrcases h with ⟨x, hx⟩\nrefine ⟨x, ?_⟩\nsimp at hx\nexact hx.symm") == "lean-block"
    assert L("- GENERAL: membership without grind:\nsimp only [List.mem_append, List.mem_cons] at h\nrcases h with h | h | h\nexact Or.inl h\nomega") == "lean-block"
    assert L("- GENERAL: casts:\n  intros x y\n  push_cast\n  simp_rw [two_mul]\n  exact_mod_cast hxy\n  norm_cast") == "lean-block"
    assert L("- GENERAL: first\n  simp at h\n  then\n  omega\n  and\n  exact h") == "lean-block"
    assert L("- GENERAL: when simp_all is slow on a small reference,\n  try the `simp?` certificate list first;\n  it usually pays.") is None
    # plain-word names declared in one problem's files (`Admissible`, `frob`) are identifiers too, with or without backticks
    D = lambda t: inrun.leak_lint(t, set(), {"Admissible": {"A"}, "frob": {"A"}, "Shared": {"A", "B"}}, None, {"Admissible", "frob", "Shared"})
    assert D("GENERAL: unfold Admissible first, then frob reduces by simp") == "single-problem-identifier"
    assert D("GENERAL: unfold Shared first") is None and D("GENERAL: unfold the definition first") is None


def test_declared_names_and_own_notes():
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td) / "a.lean"
        f.write_text("@[simp] def Admissible (n : Nat) : Prop := n > 0\nprivate noncomputable def Foo.frob : Nat := 0\ntheorem t : True := trivial\n"
                     "-- def notAdecl in a comment\n")
        got = inrun.declared_names({"A": [f]})
        assert {"Admissible", "Foo.frob", "frob", "t"} <= got and "notAdecl" not in got, got
    tech = {"notes": ["mine only", "shared", "theirs"], "note_src": [[inrun.src_key("P_dir")], [inrun.src_key("P_dir"), inrun.src_key("Q")],
                                                                     [inrun.src_key("Q")]], "patterns": [], "ops": [], "closer_prices": {}}
    mine = inrun.render(tech, exclude="P_dir")
    assert "mine only" not in mine and "shared" in mine and "theirs" in mine
    assert "mine only" in inrun.render(tech) and "mine only" in inrun.render(tech, exclude="Q") and "theirs" not in inrun.render(tech, exclude="Q")
    assert "mine only" in inrun.render({"notes": ["mine only"]}, exclude="P_dir")   # an older file without sources: shown as before


def _prob(wr: pathlib.Path, name: str, wins: list, notes: str, original: str, cache=None) -> None:
    d = wr / inrun.dirname(name); d.mkdir(parents=True)
    st = {"problem": name, "best": {"score": 60.0, "proof": "p"}, "attempts": [], "runs": [], "ledger": {"wins": wins}}
    if cache:
        st["profile_cache"] = cache
    (d / "state.json").write_text(json.dumps(st)); (d / "notes.md").write_text(notes)
    (d / "original.lean").write_text(original); (d / "context.lean").write_text("import Mathlib\n")


def _traj(runs_dir: pathlib.Path, run: str, name: str, sessions: list) -> None:
    d = runs_dir / run / "trajectories"; d.mkdir(parents=True, exist_ok=True)
    with gzip.open(d / f"{inrun.dirname(name)}.jsonl.gz", "wt") as f:
        for sess in sessions:
            f.write(json.dumps({"type": "header", "problem": name}) + "\n")
            for k, (err, text) in enumerate(sess):
                f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{k}", "name": "Bash",
                                                                                   "input": {"command": f"cd /x/{name} && ls"}}]}}) + "\n")
                f.write(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{k}", "is_error": err,
                                                                             "content": text}]}}) + "\n")


A, B, C = "Foo.alpha_lemma", "Bar.beta_theorem", "Baz.gammaCase"


def _world(td: pathlib.Path):
    wr = td / "wr"; runs = td / "runs"; wr.mkdir()
    e = lambda diff, ds=1.0, dt=2, dh=-200, kind="edit": {"diff": diff, "d_score": ds, "d_tokens": dt, "d_heartbeats": dh, "kind": kind, "sha": diff[:12]}
    _prob(wr, A, [e("-  grind [alpha_helper]\n+  simp only [alpha_helper, Nat.add_comm]", 1.0, 3, -300),
                  e("-  exact alpha_one\n+  exact alpha_two"),                                   # only the problem's identifiers changed
                  e("-  " + "x\n-  ".join(["omega"] * 3) + "x\n+  grind", 5.0, kind="rewrite")],    # a rewrite: not a pattern
          "# Notes\n- GENERAL: `simp only` with the `?` certificate list beats bare `simp_all` on heartbeats\n"
          "- GENERAL: alpha_helper closes the base case\n- GENERAL: `shared_helper` is a simp lemma\n- local: alpha only\n",
          "theorem alpha_lemma : True := by\n  exact alpha_helper shared_helper\n",
          cache={"s1": {"blocks": [{"lines": "3-3", "heartbeats": 230, "text": "grind"}, {"lines": "4-6", "heartbeats": 900, "text": "simp_all"}]}})
    _prob(wr, B, [e("-  grind\n+  simp only [beta_aux, Nat.add_comm]", 0.6, 7, -100)],
          "## Notes\n* GENERAL: the beta_theorem trick works everywhere\n- GENERAL: this works:\n  ```lean\n  simp at h\n  exact h\n  omega\n  ```\n",
          "theorem beta_theorem : True := by\n  simp [beta_aux, shared_helper]\n",
          cache={"s2": {"blocks": [{"lines": "2-2", "heartbeats": 240, "text": "· grind [x]"}, {"lines": "5-5", "heartbeats": 1400, "text": "simp_all"}]}})
    _prob(wr, C, [e("-  have h := gamma_x\n+  exact gamma_x", 0.4)],
          "GENERAL: prefer omega over linarith on Nat goals\n\n- GENERAL: `Simp only` with the `?` certificate list beats bare `simp_all` on heartbeats\n",
          "theorem gammaCase : True := by\n  exact gamma_x\n",
          cache={"s3": {"blocks": [{"lines": "2-2", "heartbeats": 100, "text": "grind"}]}})
    _traj(runs, "rr1", A, [[(True, f"This Bash command contains multiple operations. The following part requires approval: grep {A}"), (False, "ok")],
                           [(True, f"Output redirection to '/tmp/{A}.lean' needs approval.")]])
    _traj(runs, "rr1", B, [[(True, "This Bash command contains multiple operations."), (False, "fine")]])
    return wr, runs


def test_build_techniques():
    with tempfile.TemporaryDirectory() as td:
        wr, runs = _world(pathlib.Path(td))
        tc = {A: "v4.26.0", B: "v4.26.0", C: "v4.20.0"}
        rows = {A: {"file_path": "Foo/AlphaFile.lean"}}
        t = inrun.build(wr, ["rr1"], runs_dir=runs, toolchain_of=tc.get, rows=rows)
        assert t["problems"] == 3 and t["runs"] == 1
        assert [p["pattern"] for p in t["patterns"]] == ["grind -> simp only + Nat.add_comm"], t["patterns"]
        p = t["patterns"][0]
        assert (p["problems"], p["wins"], p["d_score"], p["d_tokens"], p["d_heartbeats"]) == (2, 2, 0.8, 5.0, -200)
        assert p["example"] == "- grind / + simp only [ _ , Nat.add_comm ]", p["example"]   # the first problem in dir order (Bar.*)
        assert t["notes"] == ["prefer omega over linarith on Nat goals", "`Simp only` with the `?` certificate list beats bare `simp_all` on heartbeats",
                              "`shared_helper` is a simp lemma"], t["notes"]   # dir order; the second copy of a note is dropped
        assert t["rejected_notes"] == {"single-problem-identifier": 1, "problem-name": 1, "lean-block": 1}, t["rejected_notes"]
        assert t["closer_prices"] == {"v4.26.0": {"grind": {"median_hb": 235, "n": 2}}}, t["closer_prices"]
        assert [(o["class"], o["sessions"], o["resolved"]) for o in t["ops"]] == [("compound", 2, 2)], t["ops"]
        # round-2 review: each note keeps its (hashed) source workspaces; the duplicated note has two; no problem name in the file
        ka, kc = inrun.src_key(inrun.dirname(A)), inrun.src_key(inrun.dirname(C))
        assert t["note_src"] == [[kc], [kc, ka], [ka]] and t["unreadable_trajectories"] == 0, t["note_src"]
        assert "prefer omega over linarith" not in inrun.render(t, exclude=inrun.dirname(C)) and "prefer omega" in inrun.render(t, exclude=inrun.dirname(A))
        blob = json.dumps(t)
        for leak in (A, B, C, "alpha_helper", "beta_aux", "gamma_x", "alpha_lemma", "/tmp/", "cd /x"):
            assert leak not in blob, leak
        f = inrun.write(wr, t)
        assert f == (wr / "_run_techniques.json").resolve() and inrun.load(wr) == t
        try:
            inrun.write(wr / "missing", t); raise AssertionError("write outside an existing work root must be refused")
        except ValueError:
            pass
        txt = inrun.render(t)
        assert txt.startswith("RUN TECHNIQUES") and "grind -> simp only + Nat.add_comm: 2 problems" in txt and "`grind` 235 (n=2)" in txt
        assert "one command per Bash call" in txt and "prefer omega over linarith" in txt and len(txt) <= inrun.TECH_CAP
        big = dict(t, notes=["n" * 290] * 12)
        assert len(inrun.render(big)) <= inrun.TECH_CAP and inrun.render(big).endswith("(truncated)")
        assert inrun.render({}) == "" and inrun.render(None) == "" and inrun.render({"patterns": [], "ops": [], "notes": [], "closer_prices": {}}) == ""


def test_damaged_trajectory_and_not_read_class():
    """Round-2 review: a truncated gzip trajectory (a driver killed mid-append) raises EOFError, not OSError: it is skipped and counted, the
    build goes on; Claude Code's "File has not been read yet" denial is its own class with a canned fix."""
    with tempfile.TemporaryDirectory() as td:
        wr, runs = _world(pathlib.Path(td))
        _traj(runs, "rr2", A, [[(True, "<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>"),
                                (False, "The file candidate.lean has been updated.")]])
        big = runs / "rr2" / "trajectories" / "zz_damaged.jsonl.gz"
        with gzip.open(big, "wt") as h:
            for k in range(3000):
                h.write(json.dumps({"type": "header" if k == 0 else "user", "k": k, "pad": "x" * 60}) + "\n")
        b = big.read_bytes(); big.write_bytes(b[: len(b) // 2])
        t = inrun.build(wr, ["rr1", "rr2"], runs_dir=runs, toolchain_of=lambda n: "v4.26.0", rows={})
        assert t["unreadable_trajectories"] == 1, t.get("unreadable_trajectories")
        assert ("not-read", 1, 1) in [(o["class"], o["sessions"], o["resolved"]) for o in t["ops"]], t["ops"]
        assert "Read a file once before you Edit it" in inrun.render(t)


def test_locked_check_atomic_write():
    from harness import leantools as LT
    real = LT.lean_check
    LT.lean_check = lambda name, decl, state, prov, vpath: (state["attempts"].append({"ok": False, "run_id": "r"}), {"ok": False})[1]
    try:
        with tempfile.TemporaryDirectory() as td:
            w = pathlib.Path(td)
            (w / "state.json").write_text(json.dumps({"problem": P, "best": {"score": 33.33, "proof": None}, "attempts": [], "runs": []}))
            inrun.locked_check(w, P, "x", {"run_id": "r"}, None)
            assert len(json.loads((w / "state.json").read_text())["attempts"]) == 1
            assert sorted(x.name for x in w.iterdir()) == [".state.lock", "state.json"], list(w.iterdir())   # no temp file left behind
    finally:
        LT.lean_check = real


def test_cli_counts_only():
    with tempfile.TemporaryDirectory() as td:
        wr, runs = _world(pathlib.Path(td))
        p = subprocess.run([sys.executable, str(ROOT / "harness/inrun.py"), "--work-root", str(wr), "--runs", "rr1", "--runs-dir", str(runs)],
                           capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, p.stderr[-800:]
        assert "1 edit pattern(s)" in p.stdout and "1 operational fix(es)" in p.stdout and "3 GENERAL note(s) kept, 3 rejected" in p.stdout, p.stdout
        assert not any(x in p.stdout for x in (A, B, C, "alpha", "beta", "gamma")), p.stdout
        assert (wr / "_run_techniques.json").exists() and sorted(x.name for x in wr.iterdir() if x.is_file()) == ["_run_techniques.json"]


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
