#!/usr/bin/env python3
"""Unit tests of the sorry / axiom audit (scorer/compile.py, probe/audit_held.py; 2026-10-13), plain asserts, no Lean: scorer.compile.run_lean
is replaced by a stub that reads the scratch file it was given and answers with a synthetic `lean --json` message stream (one JSON object per
line, the fields Lean serialises: fileName, pos, endPos, severity, caption, data, kind), and the env dirs point at a temporary directory.
  sorry          the warning in both text forms ('sorry' up to v4.27, `sorry` from v4.28) and by `kind` alone fails the compile with a clear
                 error, putnam and project paths, measured and unmeasured; at error severity it is one error, not two; a project prefix's
                 own sorried declaration (before the candidate's first line) does not count
  normal         an ordinary warning (unused variable) still compiles ok, heartbeats still parsed
  sorry_blind    a pin whose lakefile sets -Dwarn.sorry=false is marked; audit_axioms forces warn.sorry=true last
  axioms         `#print axioms` parsing: sorted list, wrapped list, none, sorryAx, a message before the first line ignored; decl_name on
                 synthetic and on every warm-up / held-out set #1 statement; audit_axioms appends `#print axioms <name>` and reports extras
  module         a `module` file prefix: no `#print axioms`, the declaration alone (sorry check only), skipped='module'
  cli            probe/audit_held.py: stored bests of a work root / best record of a verified.jsonl, flags as row#k, counts only
    python3 scorer/test_compile_audit.py"""
from __future__ import annotations

import collections, contextlib, io, json, os, sys, tempfile, traceback, types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scorer.compile as C  # noqa: E402

DECL = "theorem foo (n : Nat) : n + 0 = n := by\n  stop\n  simp"


def msg(line, data, severity="warning", kind=None, col=8):
    m = {"fileName": "LRAScratch/c_x.lean", "pos": {"line": line, "column": col}, "endPos": {"line": line, "column": col + 3},
         "keepFullRange": False, "severity": severity, "caption": "", "data": data}
    if kind is not None:
        m["kind"] = kind
    return m


@contextlib.contextmanager
def stub(answer, prefix="namespace X\n\ntheorem pre : True := by\n  sorry\n", lakefile=None):
    """Replace run_lean with `answer(body_text, argv) -> list of messages` (exit 0) and point every env dir at a temporary directory; the
    project file prefix is `prefix`. Yields the list of (argv, body) calls."""
    calls = []

    def fake_run_lean(argv, cwd=None, **kw):
        body = (Path(cwd) / argv[-1]).read_text()
        calls.append((argv, body))
        out = answer(body, argv)
        return types.SimpleNamespace(stdout="\n".join(json.dumps(m) for m in out) + "\n", stderr="", returncode=0)

    saved = {k: getattr(C, k) for k in ("run_lean", "env_dir", "project_env_dir", "file_prefix")}
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        if lakefile:
            (wd / "lakefile.toml").write_text(lakefile)
        C.run_lean = fake_run_lean
        C.env_dir = lambda version, source="putnambench": wd
        C.project_env_dir = lambda source, version: wd
        C.file_prefix = lambda row, version: prefix
        try:
            yield calls
        finally:
            for k, v in saved.items():
                setattr(C, k, v)


def line_of(body: str, needle: str) -> int:
    return body[: body.index(needle)].count("\n") + 1


def hb_answer(extra):
    """ARENA_HB info at the declaration plus `extra(body)` messages."""
    def ans(body, argv):
        out = list(extra(body))
        if "arena_measure\n" in body:
            out.append(msg(line_of(body, "theorem foo"), "ARENA_HB 1234", "information"))
        return out
    return ans


PUTNAM = {"name": "putnam_x", "source": "putnambench", "header": "import Mathlib\nopen Real\n", "statement": "theorem foo (n : Nat) : n + 0 = n",
          "version_info": [["v4.32.0"]]}
PROJ = {"name": "X.foo", "source": "strata", "file_path": "X.lean", "statement": "theorem foo (n : Nat) : n + 0 = n", "version_info": [["v4.32.0"]]}


# ---- sorry ---------------------------------------------------------------------------------------------------------------------------------
def test_putnam_sorry_old_form():
    with stub(hb_answer(lambda b: [msg(line_of(b, "theorem foo"), "declaration uses 'sorry'")])):
        r = C.compile_putnam(PUTNAM["header"], DECL, "v4.25.0")
    assert not r.ok and r.heartbeats == 1234 and r.warnings == 1, r
    assert len(r.errors) == 1 and C.SORRY_ERR in r.errors[0] and "stop" in r.errors[0], r.errors


def test_putnam_sorry_new_form_and_kind():
    for data, kind in (("declaration uses `sorry`", "hasSorry"), ("declaration uses `sorry`", None), ("something else", "hasSorry")):
        with stub(hb_answer(lambda b: [msg(line_of(b, "theorem foo"), data, kind=kind)])):
            for count in (True, False):
                r = C.compile_putnam(PUTNAM["header"], DECL, "v4.32.0", count=count)
                assert not r.ok and any(C.SORRY_ERR in e for e in r.errors), (data, kind, count, r.errors)


def test_sorry_at_error_severity_is_one_error():
    with stub(hb_answer(lambda b: [msg(line_of(b, "theorem foo"), "declaration uses `sorry`", "error", "hasSorry")])):
        r = C.compile_putnam(PUTNAM["header"], DECL, "v4.32.0")
    assert not r.ok and len(r.errors) == 1 and C.SORRY_ERR not in r.errors[0], r.errors


def test_normal_warning_ok():
    unused = "unused variable `h`\n\nNote: This linter can be disabled with `set_option linter.unusedVariables false`"
    with stub(hb_answer(lambda b: [msg(line_of(b, "theorem foo"), unused)])):
        r = C.compile_putnam(PUTNAM["header"], DECL, "v4.32.0")
        assert r.ok and r.heartbeats == 1234 and r.warnings == 1 and r.errors == [], r
        p = C.compile_project(PROJ, DECL, "v4.32.0", lean_args=())
        assert p.ok and p.heartbeats == 1234 and p.errors == [] and not p.sorry_blind, p


def test_project_prefix_sorry_ignored_candidate_sorry_counted():
    prefix_warn = lambda b: [msg(line_of(b, "theorem pre"), "declaration uses `sorry`", kind="hasSorry")]
    with stub(hb_answer(prefix_warn)) as calls:
        for count in (True, False):
            r = C.compile_project(PROJ, DECL, "v4.32.0", count=count, lean_args=())
            assert r.ok and r.errors == [] and r.warnings == 1, (count, r)
        assert calls and all("theorem pre" in b for _, b in calls)
    both = lambda b: prefix_warn(b) + [msg(line_of(b, "theorem foo"), "declaration uses `sorry`", kind="hasSorry")]
    with stub(hb_answer(both)):
        for count in (True, False):
            r = C.compile_project(PROJ, DECL, "v4.32.0", count=count, lean_args=())
            assert not r.ok and len(r.errors) == 1 and C.SORRY_ERR in r.errors[0], (count, r.errors)
            assert r.errors[0].split(":")[0] != "4", r.errors   # the candidate's line, not the prefix's


def test_putnam_sorry_before_first_line_ignored():
    # nothing in a putnam header can carry a sorry, but the rule is the same: only the candidate's lines count
    with stub(hb_answer(lambda b: [msg(1, "declaration uses `sorry`", kind="hasSorry")])):
        r = C.compile_putnam(PUTNAM["header"], DECL, "v4.32.0")
    assert r.ok, r.errors


def test_sorry_blind_and_forced_on():
    lake = '[[lean_lib]]\nname = "P"\nmoreLeanArgs = ["-Dwarn.sorry=false", "-Dweak.says.verify=true"]\n'
    with stub(hb_answer(lambda b: []), lakefile=lake) as calls:
        r = C.compile_project(PROJ, DECL, "v4.32.0")
        assert r.ok and r.sorry_blind and "-Dwarn.sorry=false" in calls[-1][0], (r, calls[-1][0])
        a = C.audit_axioms(PROJ, DECL, "v4.32.0")
        argv = calls[-1][0]
        flags = [x for x in argv if x.startswith("-Dwarn.sorry=")]
        assert flags == ["-Dwarn.sorry=true"] and "-Dweak.says.verify=true" in argv and not a.compile.sorry_blind, argv
    assert not C._warn_sorry_off(("-Dwarn.sorry=false", "-Dwarn.sorry=true")) and C._warn_sorry_off(("-Dweak.warn.sorry=false",))


@contextlib.contextmanager
def env_var(k, v):
    old = os.environ.get(k)
    os.environ[k] = v
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = old


def test_force_warn_sorry_opt_in():
    """Review finding 1: LRA_FORCE_WARN_SORRY=1 replaces a lakefile warn.sorry=false by true in the hot path and keeps the prefix's own sorry
    warnings out of `warnings`; unset, the arguments are exactly lakefile_options (heartbeat calibration untouched); other pins unchanged."""
    lake = '[[lean_lib]]\nname = "P"\nmoreLeanArgs = ["-Dwarn.sorry=false", "-Dweak.says.verify=true"]\n'
    prefix_warn = lambda b: [msg(line_of(b, "theorem pre"), "declaration uses `sorry`", kind="hasSorry")]
    cand_warn = lambda b: [msg(line_of(b, "theorem foo"), "declaration uses `sorry`", kind="hasSorry")]
    with stub(hb_answer(prefix_warn), lakefile=lake) as calls:
        with env_var("LRA_FORCE_WARN_SORRY", ""):
            r = C.compile_project(PROJ, DECL, "v4.32.0")
        assert calls[-1][0][5:-1] == list(C.lakefile_options("physlib", "v4.32.0")) and r.sorry_blind and r.warnings == 1, (calls[-1][0], r)
        with env_var("LRA_FORCE_WARN_SORRY", "1"):
            for count in (True, False):
                r = C.compile_project(PROJ, DECL, "v4.32.0", count=count)
                argv = calls[-1][0]
                assert [x for x in argv if "warn.sorry" in x] == ["-Dwarn.sorry=true"] and "-Dweak.says.verify=true" in argv, argv
                assert r.ok and not r.sorry_blind and r.warnings == 0, (count, r)   # the prefix's sorry warning is not counted
    with stub(hb_answer(lambda b: prefix_warn(b) + cand_warn(b)), lakefile=lake):
        with env_var("LRA_FORCE_WARN_SORRY", "1"):
            r = C.compile_project(PROJ, DECL, "v4.32.0")
    assert not r.ok and r.warnings == 1 and any(C.SORRY_ERR in e for e in r.errors), r
    plain = '[leanOptions]\nautoImplicit = false\n'
    with stub(hb_answer(lambda b: []), lakefile=plain) as calls:
        with env_var("LRA_FORCE_WARN_SORRY", "1"):
            C.compile_project(PROJ, DECL, "v4.32.0")
        assert calls[-1][0][5:-1] == ["-DautoImplicit=false"], calls[-1][0]


def test_sorry_switch():
    """Review finding 2: a candidate naming warn.sorry or #guard_msgs fails, in both paths; a comment mentioning them, or a project prefix
    using them, does not."""
    bad = ["set_option warn.sorry false in\ntheorem foo (n : Nat) : n + 0 = n := by\n  stop\n  simp",
           "set_option weak.warn.sorry false in\ntheorem foo (n : Nat) : n + 0 = n := by simp",
           "#guard_msgs (drop warning) in\ntheorem foo (n : Nat) : n + 0 = n := by\n  stop\n  simp"]
    with stub(hb_answer(lambda b: [])):
        for d in bad:
            for count in (True, False):
                for r in (C.compile_putnam(PUTNAM["header"], d, "v4.32.0", count=count),
                          C.compile_project(PROJ, d, "v4.32.0", count=count, lean_args=())):
                    assert not r.ok and sum(C.SORRY_SWITCH_ERR in e for e in r.errors) == 1, (d, count, r.errors)
        ok = "theorem foo (n : Nat) : n + 0 = n := by\n  -- no set_option warn.sorry false, no #guard_msgs\n  simp"
        assert C.compile_putnam(PUTNAM["header"], ok, "v4.32.0").ok
    with stub(hb_answer(lambda b: []), prefix="namespace X\n\nset_option warn.sorry false\n#guard_msgs in\n#check 1\n"):
        assert C.compile_project(PROJ, DECL.replace("stop\n  ", ""), "v4.32.0", lean_args=()).ok


def test_putnam_header_trailing_whitespace_lines():
    """Review finding 6: a header ending in whitespace-only lines with spaces must not push first_line past the theorem."""
    header = "import Mathlib\nopen Real\n  \n \t\n"
    with stub(hb_answer(lambda b: [msg(line_of(b, "theorem foo"), "declaration uses `sorry`", kind="hasSorry")])):
        for count in (True, False):
            r = C.compile_putnam(header, DECL, "v4.32.0", count=count)
            assert not r.ok and any(C.SORRY_ERR in e for e in r.errors), (count, r.errors)
        a = C.audit_axioms(dict(PUTNAM, header=header), DECL, "v4.32.0")
    assert a.sorry_warning and a.first_line == 3, a


# ---- axioms --------------------------------------------------------------------------------------------------------------------------------
def test_parse_axioms():
    m = lambda line, d: msg(line, d, "information", col=0)
    assert C.parse_axioms([m(9, "'foo' depends on axioms: [propext, Classical.choice, Quot.sound]")]) == ["propext", "Classical.choice", "Quot.sound"]
    assert C.parse_axioms([m(9, "'X.foo' depends on axioms: [propext,\n Classical.choice,\n Quot.sound,\n sorryAx]")])[-1] == "sorryAx"
    assert C.parse_axioms([m(9, "'foo' does not depend on any axioms")]) == []
    assert C.parse_axioms([m(9, "ARENA_HB 12")]) is None and C.parse_axioms([]) is None
    early = [m(2, "'pre' depends on axioms: [sorryAx]"), m(9, "'foo' depends on axioms: [propext]")]
    assert C.parse_axioms(early, first_line=5) == ["propext"] and C.parse_axioms(early[:1], first_line=5) is None
    a = C.AxiomAudit("foo", ["propext", "Classical.choice", "Quot.sound", "Lean.ofReduceBool", "sorryAx"])
    assert a.extra == ["Lean.ofReduceBool", "sorryAx"] and a.sorry
    assert C.AxiomAudit("foo", ["propext"]).extra == [] and not C.AxiomAudit("foo", ["propext"]).sorry


def test_decl_name():
    cases = {
        "theorem foo (n : Nat) : n = n": "foo",
        "open OldExpressions in\ntheorem substOldPostSubset:\n  True": "substOldPostSubset",
        "/-- This theorem bar is about lemma baz. -/\n@[simp] lemma Foo.bar_baz {α : Type} : True": "Foo.bar_baz",
        "-- theorem commented\nprivate theorem p_1 : True": "p_1",
        "theorem «weird name» : True": "«weird name»",
        "theorem foo.{u} (α : Sort u) : True": "foo",
        "protected theorem Nat.foo' [Inhabited α] : True": "Nat.foo'",
        "example : True": None,
        "instance : Inhabited Nat": None,
        "instance instFoo : Inhabited Nat": "instFoo",
        "set_option maxHeartbeats 400000 in\ntheorem putnam_1964_b2 (S : Type*) : True": "putnam_1964_b2",
    }
    for s, want in cases.items():
        assert C.decl_name(s) == want, (s, C.decl_name(s), want)
    # review finding 7: a solution abbrev before the theorem, instance priority, a keyword inside an attribute string
    sol = "noncomputable abbrev putnam_x_solution : ℕ := 5\ntheorem putnam_x (n : ℕ) : n = putnam_x_solution"
    assert C.decl_name(sol, "putnam_x") == "putnam_x" and C.decl_name(sol) == "putnam_x", C.decl_name(sol)
    assert C.decl_name(sol, "putnam_x_solution") == "putnam_x_solution"
    assert C.decl_name("instance (priority := 100) instFoo : Inhabited Nat") == "instFoo"
    assert C.decl_name('@[deprecated "lemma about theorem x" (since := "2025")] theorem real_one : True') == "real_one"
    assert C.decl_name("@[simp, to_additive (attr := simp) \"doc\"]\nlemma mul_foo : True", "X.mul_foo") == "mul_foo"
    assert C.decl_name("theorem _root_.Nat.foo : True", "Nat.foo") == "_root_.Nat.foo"
    n = 0
    for f in ("data/benchmark_warmup.jsonl", "data/heldout/heldout.jsonl"):
        for l in (ROOT / f).open():
            if l.strip():
                r = json.loads(l); n += 1
                for got in (C.decl_name(r["statement"]), C.decl_name(r["statement"], r["name"])):
                    assert got and (r["name"] == got or r["name"].endswith("." + got)), (r["name"], got)
    assert n >= 15, n


def test_namespace_and_qualified_name():
    pre = ("/- namespace Fake -/\nimport A\n\nnamespace Core.Sem\n\nsection Helpers\nvariable (x : Nat)\nend Helpers\n\nnoncomputable section\n"
           "namespace Inner\ntheorem t : True := trivial\nend Inner\n\nnamespace Deep.Er\n")
    assert C.current_namespace(pre) == "Core.Sem.Deep.Er", C.current_namespace(pre)
    assert C.current_namespace(pre + "end Deep.Er\nend\n") == "Core.Sem"
    assert C.current_namespace("import Mathlib\nopen Real\n") == "" and C.current_namespace("end\nend\n") == ""
    assert C.qualified_name("foo", "X.Y") == "X.Y.foo" and C.qualified_name("foo", "") == "foo"
    assert C.qualified_name("_root_.Nat.foo", "X") == "Nat.foo"


def test_audit_print_block():
    """Review findings 5 and 8: both name forms under pp.fullNames; parse from the #print block only; errors there are print_errors."""
    pre = "namespace X\n\ntheorem pre : True := by\n  sorry\n\n/-- doc -/\n@[simp]\n"
    def ans(body, argv):
        out = [msg(line_of(body, "theorem pre"), "'pre' depends on axioms: [sorryAx]", "information")]   # a decoy before the candidate
        short = line_of(body, "#print axioms foo")
        out.append(msg(short + 0, "unknown constant 'foo'", "error", col=15))
        out.append(msg(line_of(body, "#print axioms X.foo"), "'X.foo' depends on axioms: [propext,\n Classical.choice]", "information"))
        return out
    with stub(ans, prefix=pre) as calls:
        a = C.audit_axioms(dict(PROJ, name="X.foo"), DECL.replace("stop\n  ", ""), "v4.32.0")
    body = calls[-1][1]
    assert body.count("set_option pp.fullNames true in\n#print axioms ") == 2 and "#print axioms X.foo\n" in body, body
    assert a.print_line == line_of(body, "set_option pp.fullNames true in\n#print axioms foo"), (a.print_line, body)
    assert a.axioms == ["propext", "Classical.choice"] and a.extra == [] and not a.sorry, a
    assert len(a.print_errors) == 1 and a.decl_errors == [] and not a.compile.ok, (a.print_errors, a.decl_errors)
    with stub(lambda b, v: [msg(line_of(b, "#print axioms foo"), "'foo' depends on axioms: [propext]", "information")]) as calls:
        p = C.audit_axioms(PUTNAM, DECL, "v4.32.0")   # no namespace: one form
    assert calls[-1][1].count("#print axioms") == 1 and p.axioms == ["propext"] and p.print_line == line_of(calls[-1][1], "set_option pp.fullNames")


def test_parse_axioms_null_line():
    m = {"pos": {"line": None}, "severity": "information", "data": "'foo' depends on axioms: [propext]"}
    assert C.parse_axioms([m], first_line=5) == ["propext"] and C.parse_axioms([dict(m, pos=None)], first_line=5) == ["propext"]


def test_module_sorry_at_error_severity():
    """Review finding 3: Strata's warningAsError reports the sorry as an error; the audit still calls it sorry (module rows too)."""
    mod_prefix = "module\n\npublic import Strata.Foo\n\nnamespace X\n"
    with stub(lambda b, a: [msg(line_of(b, "theorem foo"), "declaration uses `sorry`", "error", "hasSorry")], prefix=mod_prefix):
        a = C.audit_axioms(PROJ, DECL, "v4.29.1")
    assert a.skipped == "module" and a.sorry_warning and a.sorry and a.decl_errors == [] and not a.compile.ok, a
    assert _audit_module().classify(a) == ["sorry"]


def test_audit_axioms_putnam_and_project():
    def ans(body, argv):
        if "#print axioms foo" not in body:
            return []
        return [msg(line_of(body, "#print axioms foo"), "'foo' depends on axioms: [propext, Lean.ofReduceBool, Quot.sound]", "information", col=0)]
    with stub(ans) as calls:
        a = C.audit_axioms(PUTNAM, DECL, "v4.32.0")
        assert a.name == "foo" and a.axioms == ["propext", "Lean.ofReduceBool", "Quot.sound"] and a.extra == ["Lean.ofReduceBool"], a
        assert not a.sorry and a.compile.ok and "arena_measure" not in calls[-1][1] and calls[-1][1].rstrip().endswith("#print axioms foo")
        p = C.audit_axioms(PROJ, DECL, "v4.32.0")
        assert p.axioms == ["propext", "Lean.ofReduceBool", "Quot.sound"] and p.skipped is None and "theorem pre" in calls[-1][1], p
        off = C.audit_axioms(PROJ, DECL, "v4.32.0", axioms=False)
        assert off.skipped == "off" and off.axioms is None and "#print axioms" not in calls[-1][1]
        nn = C.audit_axioms(dict(PUTNAM, statement="example : True"), "example : True := trivial", "v4.32.0")
        assert nn.skipped == "no-name" and nn.compile is not None and "#print axioms" not in calls[-1][1]
    def sorry_ans(body, argv):
        return [msg(line_of(body, "theorem foo"), "declaration uses `sorry`", kind="hasSorry"),
                msg(line_of(body, "#print axioms foo"), "'foo' depends on axioms: [sorryAx]", "information", col=0)]
    with stub(sorry_ans):
        s = C.audit_axioms(PUTNAM, DECL, "v4.32.0")
    assert s.sorry and s.axioms == ["sorryAx"] and not s.compile.ok, s


# ---- module --------------------------------------------------------------------------------------------------------------------------------
def test_module_skip():
    mod_prefix = "/- Copyright -/\nmodule\n\npublic import Strata.Foo\n\nnamespace X\n"
    with stub(lambda b, a: [msg(line_of(b, "theorem foo"), "declaration uses `sorry`", kind="hasSorry")], prefix=mod_prefix) as calls:
        a = C.audit_axioms(PROJ, DECL, "v4.32.0")
    assert a.skipped == "module" and a.axioms is None and a.sorry and len(calls) == 1 and "#print axioms" not in calls[0][1], a


# ---- cli -----------------------------------------------------------------------------------------------------------------------------------
def _audit_module():
    sys.path.insert(0, str(ROOT / "probe"))
    import audit_held as AH
    return AH


def CR(ok, errs=(), to=False, msgs=()):
    return C.CompileResult(ok, None, 1.0, list(errs), timed_out=to, messages=list(msgs))


SORRY_MSGS = [msg(5, "declaration uses `sorry`", kind="hasSorry")]


def test_cli_counts_only():
    AH = _audit_module()
    verdicts = {   # proof -> AxiomAudit the stub returns (first_line 3, #print axioms block from line 20)
        "P_CLEAN": C.AxiomAudit("a", ["propext"], None, CR(True), 3, 20),
        "P_SORRY": C.AxiomAudit("b", ["sorryAx"], None, CR(False, ["5:8: " + C.SORRY_ERR + " (…)"], msgs=SORRY_MSGS), 3, 20),
        "P_AX": C.AxiomAudit("c", ["propext", "Lean.ofReduceBool"], None, CR(True), 3, 20),
        "P_MOD": C.AxiomAudit("d", None, "module", CR(True), 3),
        "P_BROKEN": C.AxiomAudit("e", None, None, CR(False, ["3:1: unknown identifier"]), 3, 20),
        "P_TO": C.AxiomAudit("f", None, None, CR(False, ["timeout"], True), 3, 20),
    }
    seen = []
    def audit(row, proof, version, axioms=True):
        seen.append((row["name"], version, axioms))
        if proof == "P_RAISE":
            raise ValueError("statement found 0 times")
        return verdicts[proof]
    names = ["SECRET_" + k for k in ["a", "b", "c", "d", "e", "f", "g"]]
    proofs = ["P_CLEAN", "P_SORRY", "P_AX", "P_MOD", "P_BROKEN", "P_TO", "P_RAISE"]
    rows = {n: {"name": n, "version_info": [["v4.30.0", "v4.32.0"]]} for n in names}
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "work"
        for n, p in zip(names, proofs):
            (root / n).mkdir(parents=True); (root / n / "state.json").write_text(json.dumps({"problem": n, "best": {"proof": p, "score": 50}}))
        (root / "SECRET_h").mkdir(); (root / "SECRET_h" / "state.json").write_text(json.dumps({"problem": "SECRET_h", "best": {"score": 33.33, "proof": None}}))
        (root / "SECRET_i").mkdir(); (root / "SECRET_i" / "state.json").write_text(json.dumps({"problem": "SECRET_i", "best": {"proof": "P_CLEAN"}}))
        lines = []
        n = AH.run(AH.bests_of_root(root), rows, audit=audit, out=lines.append, jobs=2)
        text = "\n".join(lines)
        assert "SECRET" not in text and "sorryAx" not in text and "ofReduceBool" not in text, text
        flagged = {l.split(":")[0]: l.split(": ", 1)[1] for l in lines[:-1]}
        assert flagged == {"row#1": "sorry", "row#2": "axioms", "row#4": "compile", "row#5": "timeout", "row#6": "error (ValueError)",
                           "row#8": "no row (pass its set with --rows)"}, flagged
        assert n["audited"] == 7 and n["sorry"] == 1 and n["axioms"] == 1 and n["skipped (module)"] == 1 and n["no best"] == 1 and n["no row"] == 1, n
        assert lines[-1].startswith("summary: audited 7, sorry 1, axioms 1"), lines[-1]
        assert {v for _, v, _ in seen} == {"v4.32.0"} and all(ax for _, _, ax in seen)
        vf = Path(td) / "verified.jsonl"
        vf.write_text("".join(json.dumps(r) + "\n" for r in [
            {"problem": "SECRET_b", "proof": "P_CLEAN", "score": 60}, {"problem": "SECRET_b", "proof": "P_SORRY", "score": 70},
            {"problem": "SECRET_a", "proof": "P_AX", "score": 40}, {"problem": "SECRET_a", "proof": "P_CLEAN", "score": 40},
            {"problem": "SECRET_c", "proof": "P_SORRY", "score": 99, "primary_ok": False}]))
        assert AH.bests_of_verified(vf) == [("SECRET_a", "P_AX"), ("SECRET_b", "P_SORRY")]
        lines = []
        n = AH.run(AH.bests_of_verified(vf), rows, version="v4.30.0", axioms=False, audit=audit, out=lines.append)
        assert lines == ["row#0: axioms", "row#1: sorry", "summary: audited 2, sorry 1, axioms 1"], lines
        assert seen[-1][1:] == ("v4.30.0", False)
        assert AH.exit_code(n) == 1 and AH.exit_code(collections.Counter(compile=1)) == 2 and AH.exit_code(collections.Counter(audited=3)) == 0


def test_cli_flags_and_reference_baseline():
    """Review findings 3, 4, 8: transitive sorryAx / native axioms explained by the reference are not flagged; a Strata-style sorry at
    error severity is 'sorry', not 'compile'; an error on the #print axioms lines is 'undetermined', not 'compile'; the switch flag."""
    AH = _audit_module()
    err_sorry = [msg(5, "declaration uses `sorry`", "error", "hasSorry")]
    V = {
        "P_TRANS": C.AxiomAudit("a", ["propext", "sorryAx"], None, CR(True), 3, 20),                     # transitive, reference has it too
        "P_TRANS_NEW": C.AxiomAudit("b", ["propext", "sorryAx"], None, CR(True), 3, 20),                 # transitive, reference lacks it
        "P_NATIVE_REF": C.AxiomAudit("c", ["propext", "Lean.ofReduceBool"], None, CR(True), 3, 20),     # pseudo decl, in the reference
        "P_MODSORRY": C.AxiomAudit("d", None, "module", CR(False, ["5:8: declaration uses `sorry`"], msgs=err_sorry), 3),
        "P_UNRES": C.AxiomAudit("e", None, None, CR(False, ["21:15: unknown constant 'X.e'", "23:15: unknown constant 'e'"]), 3, 20),
        "P_HALF": C.AxiomAudit("f", ["propext"], None, CR(False, ["21:15: unknown constant 'f'"]), 3, 20),
        "P_SWITCH": C.AxiomAudit("g", ["propext"], None, CR(False, ["the declaration uses `#guard_msgs`, which " + C.SORRY_SWITCH_ERR]), 3, 20),
        "REF_SORRY": C.AxiomAudit("r", ["propext", "sorryAx", "Lean.ofReduceBool"], None, CR(True), 3, 20),
        "REF_CLEAN": C.AxiomAudit("r", ["propext"], None, CR(True), 3, 20),
    }
    refs = {"SECRET_a": "REF_SORRY", "SECRET_b": "REF_CLEAN", "SECRET_c": "REF_SORRY", "SECRET_d": "REF_CLEAN", "SECRET_e": "REF_CLEAN",
            "SECRET_f": "REF_CLEAN", "SECRET_g": "REF_CLEAN"}
    calls = []
    def audit(row, proof, version, axioms=True):
        calls.append(proof)
        return V[proof]
    rows = {n: {"name": n, "src": r, "version_info": [["v4.32.0"]]} for n, r in refs.items()}
    items = list(zip(sorted(refs), ["P_TRANS", "P_TRANS_NEW", "P_NATIVE_REF", "P_MODSORRY", "P_UNRES", "P_HALF", "P_SWITCH"]))
    lines = []
    n = AH.run(items, rows, audit=audit, out=lines.append)
    flagged = {l.split(":")[0]: l.split(": ", 1)[1] for l in lines[:-1]}
    assert flagged == {"row#1": "sorryAx", "row#3": "sorry", "row#4": "undetermined", "row#6": "switch"}, flagged
    assert n["as reference"] == 2 and n["undetermined"] == 1 and not n["compile"], n
    assert calls.count("REF_SORRY") == 2 and calls.count("REF_CLEAN") == 1, calls   # the reference only when the candidate has extras
    assert "SECRET" not in "\n".join(lines) and AH.exit_code(n) == 1
    lines = []
    n = AH.run(items[:1], rows, audit=audit, out=lines.append, ref=False)
    assert lines[0] == "row#0: sorryAx", lines   # no baseline: the transitive sorryAx is flagged


def test_cli_rows_are_added():
    """Review finding 10: --rows adds to the default row files instead of replacing them."""
    AH = _audit_module()
    got = {}

    def fake_run(items, rows, **kw):
        got["rows"] = rows
        return collections.Counter()
    saved, AH.run = AH.run, fake_run
    try:
        with tempfile.TemporaryDirectory() as td:
            extra = Path(td) / "extra.jsonl"
            extra.write_text(json.dumps({"name": "SECRET_extra", "version_info": [["v4.32.0"]]}) + "\n")
            (Path(td) / "w").mkdir()
            AH.main(["--work-root", str(Path(td) / "w"), "--rows", str(extra)])
    finally:
        AH.run = saved
    assert "SECRET_extra" in got["rows"] and "putnam_1964_b2" in got["rows"], len(got["rows"])


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
