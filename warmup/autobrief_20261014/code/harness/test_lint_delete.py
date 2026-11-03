#!/usr/bin/env python3
"""Unit tests of harness/lint_delete.py (lint deletions + bounded deletion search), plain asserts, no Lean: the probe's warnings parsed into
located deletions (Lean core's "This simp argument is unused" in its v4.25 and v4.33 shapes, Mathlib's "'tac' tactic does nothing" and
"Unused tactic linter: `tac` does nothing", positions offset by the file header and the probe's set_option lines, multi-line lists,
repeated warnings under `<;>`, warnings in the statement / other linters / unmatched texts ignored), the probe ladder (unknown option ->
retried without it, other failures -> plain), deletion rendering (first / middle / last / every item, multi-line lists, `at h`, `using`,
`<;>`, `;`, bullets, nested lists), delsearch's candidates (simple arguments only; standalone single-line tactics only: no bullets, case
arms, calc steps, continuation lines, block openers, only-tactic blocks or closing tactics), the greedy logic with a stubbed evaluate (lint
all at once, then site by site; delsearch first improvement with restart, never retrying a rejected key, the noise margin, the stored-best
re-measure), the final all-pin check (Z drop / missing Z -> the longest passing prefix of the promoted steps, or no gain), max-compiles /
deadline stops, and the batch mode (banking through the injected check with kind and a bounded lock wait, run-id validation, row errors by
class only, no problem names on stdout or stderr). Every compile entry point is replaced by a guard that fails the run when called.
    python3 harness/test_lint_delete.py"""
from __future__ import annotations

import contextlib, io, json, pathlib, subprocess, sys, tempfile, traceback, types

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import lint_delete as LD  # noqa: E402
from harness.normalize import _mask  # noqa: E402
from harness import leantools as _LT, normalize as _NZ, inrun as _IR  # noqa: E402
from scorer import compile as _SC  # noqa: E402

# ---- compile guard: nothing in these tests may compile Lean or spawn a process -------------------------------------------------------------
GUARD_HITS: list = []


def _guard(label):
    def f(*a, **k):
        GUARD_HITS.append(label)
        raise AssertionError(f"{label} called in a unit test")
    return f


for _mod, _names in ((_LT, ("comp", "lean_check", "run_lean", "lean_run")), (_NZ, ("comp", "evaluate")), (_IR, ("locked_check",)),
                     (_SC, ("compile_putnam", "compile_project", "run_lean"))):
    for _n in _names:
        if hasattr(_mod, _n):
            setattr(_mod, _n, _guard(f"{_mod.__name__}.{_n}"))
subprocess.Popen = _guard("subprocess.Popen")

STMT = "theorem t (a b : Nat) (h : a = b) : b = a"
HL = 7   # file lines before the probe (header)
NOTE_ARGS = "\n\nNote: This linter can be disabled with `set_option linter.unusedSimpArgs false`"
NOTE_TAC = "\n\nNote: This linter can be disabled with `set_option linter.unusedTactic false`"


def _decl(body: str) -> str:
    return STMT + " := by\n" + body


def body_of(text: str) -> str:
    return " by\n" + text   # what split_declaration returns for _decl(text)


def _lc(text: str, off: int) -> dict:
    return {"line": text.count("\n", 0, off) + 1 + HL, "column": off - (text.rfind("\n", 0, off) + 1)}


def warn(probe: str, start: int, data: str, end: int | None = None, sev: str = "warning") -> dict:
    """A Lean --json message at probe offsets [start, end), as the compile parses it."""
    m = {"severity": sev, "data": data, "pos": _lc(probe, start), "fileName": "LRAScratch/c_0.lean"}
    m["endPos"] = _lc(probe, end) if end is not None else None
    return m


def unused_arg(arg: str, call: str, new: bool = True) -> str:
    """The core linter's text: v4.33 (new) and v4.25 (old: the hint's suggestion struck through character by character)."""
    struck = "".join(ch + "̵" for ch in arg)
    hint = (f"\n\nHint: Omit it from the simp argument list.\n  {call}" if new else
            f"\n\nHint: Omit it from the simp argument list.\n  {call.replace(arg, struck)}")
    return f"This simp argument is unused:\n  {arg}{hint}{NOTE_ARGS}"


def parse(text: str, msgs_of, opts=LD.LINT_OPTS):
    """(body, deletions, counts) for _decl(text), with msgs_of(probe) giving the messages."""
    d = _decl(text); pre = LD.probe_prefix(opts); probe = pre + d; b = body_of(text)
    dels, c = LD.lint_dels(b, len(d) - len(b), len(pre), probe, msgs_of(probe), HL)
    return b, dels, c


def cut(b, dels):
    return LD.render(b, dels)[len(" by\n"):]


# ---- lint: warning parsing ----------------------------------------------------------------------------------------------------------------
def test_parse_unused_simp_args():
    t = ("  simp only [foo, bar,\n    baz] at h\n  simp [Nat.add_comm a b, ← mul_assoc] <;> simp_all [qux]\n  exact h")

    def msgs(p):
        i = p.index("bar"); j = p.index("baz"); k = p.index("← mul_assoc"); q = p.index("qux")
        return [warn(p, i, unused_arg("bar", "simp only [foo, baz] at h"), i + 3),
                warn(p, j, unused_arg("baz", "simp only [foo, bar] at h", new=False), j + 3),
                warn(p, k, unused_arg("← mul_assoc", "simp [Nat.add_comm a b]") + "\n\nNote: Simp arguments with `←` have the additional effect of "
                     "removing the other direction from the simp set, even if the simp argument itself is unused.", k + 11),
                warn(p, q, unused_arg("qux", "simp_all"), q + 3), warn(p, q, unused_arg("qux", "simp_all"), q + 3),   # `<;>`: twice
                warn(p, p.index("theorem"), "unused variable `a`\n\nNote: This linter can be disabled with `set_option linter.unusedVariables false`"),
                warn(p, p.index("exact"), "declaration uses 'sorry'"),
                warn(p, 0, "ARENA_HB 1234", sev="information"),
                warn(p, p.index("foo"), unused_arg("fooo", "simp only [bar, baz] at h"), p.index("foo") + 3)]   # printed text differs
    b, dels, c = parse(t, msgs)
    assert [b[d.span[0]:d.span[1]] for d in dels] == ["bar", "baz", "← mul_assoc", "qux"], dels
    assert c == {"warnings": 6, "args": 4, "tactics": 0, "unmatched": 1}, c   # distinct deletions: the `<;>` copy counts once
    assert all(d.kind == "arg" and d.src == "lint" for d in dels)
    assert cut(b, dels) == "  simp only [foo] at h\n  simp [Nat.add_comm a b] <;> simp_all\n  exact h", cut(b, dels)
    # warnings in the statement (the probe's set_option lines, the theorem head) never become deletions
    _, dels2, c2 = parse("  simp [x]\n  exact h", lambda p: [warn(p, p.index("(h : a = b)") + 1, unused_arg("h", "simp"), None),
                                                            warn(p, 3, unused_arg("x", "simp"), None)])
    assert dels2 == [] and c2["warnings"] == 0, (dels2, c2)
    # a plain probe (no set_option lines): the same positions without the offset
    b, dels, c = parse("  simp [x, y]\n  exact h", lambda p: [warn(p, p.index("y]"), unused_arg("y", "simp [x]"), p.index("y]") + 1)], opts=())
    assert cut(b, dels) == "  simp [x]\n  exact h", cut(b, dels)


def test_parse_unused_tactics():
    t = "  skip\n  norm_num\n  simp <;> rfl\n  skip; simp\n  constructor\n  · skip\n  · exact h\n  exact h"

    def msgs(p):
        a = p.index("  skip\n") + 2; nn = p.index("norm_num"); rf = p.index("rfl"); s2 = p.index("skip; ")
        bs = p.index("· skip") + 2
        return [warn(p, a, "'skip' tactic does nothing" + NOTE_TAC, a + 4),                       # Mathlib v4.25 shape, with endPos
                warn(p, nn, "Unused tactic linter: `norm_num` does nothing" + NOTE_TAC, None),   # current shape, no endPos
                warn(p, rf, "Unused tactic linter: `rfl` does nothing" + NOTE_TAC, rf + 3),
                warn(p, s2, "'skip' tactic does nothing" + NOTE_TAC, s2 + 4),
                warn(p, bs, "'skip' tactic does nothing" + NOTE_TAC, bs + 4)]                    # a bullet's only tactic: left alone
    b, dels, c = parse(t, msgs)
    assert c == {"warnings": 5, "args": 0, "tactics": 4, "unmatched": 1}, c
    assert [d.whole for d in dels] == [True, True, False, False], dels
    assert cut(b, dels) == "  simp\n  simp\n  constructor\n  · skip\n  · exact h\n  exact h", cut(b, dels)
    # one at a time
    assert cut(b, [dels[2]]) == "  skip\n  norm_num\n  simp\n  skip; simp\n  constructor\n  · skip\n  · exact h\n  exact h"
    assert cut(b, [dels[3]]) == "  skip\n  norm_num\n  simp <;> rfl\n  simp\n  constructor\n  · skip\n  · exact h\n  exact h"
    # the last line of the body: its preceding newline goes with it
    b, dels, _ = parse("  exact h\n  skip", lambda p: [warn(p, p.rindex("skip"), "'skip' tactic does nothing" + NOTE_TAC, p.rindex("skip") + 4)])
    assert cut(b, dels) == "  exact h", cut(b, dels)


def test_probe_ladder():
    calls = []

    def cfn(text):
        calls.append(text.split("theorem")[0])
        if "linter.unusedTactic" in text:
            return types.SimpleNamespace(ok=False, messages=[{"severity": "error", "data": "Unknown option `linter.unusedTactic`"}], errors=[])
        return types.SimpleNamespace(ok=True, messages=[], errors=[])
    r, pre = LD.lint_probe(_decl("  simp"), cfn, LD.LINT_OPTS, lambda: True)
    assert r.ok and pre == "set_option linter.unusedSimpArgs true in\n" and len(calls) == 2, calls
    # the older wording in the compile's error strings
    calls.clear()
    cfn2 = lambda text: (calls.append(1), types.SimpleNamespace(ok="unusedTactic" not in text, messages=[],
                                                                  errors=["9:11: unknown option 'linter.unusedTactic'"]))[1]
    assert LD.lint_probe(_decl("  simp"), cfn2, LD.LINT_OPTS, lambda: True)[1] == "set_option linter.unusedSimpArgs true in\n"
    # any other failure (modifiers in front, a parse error): straight to the plain probe; a plain failure ends the ladder
    calls.clear()
    cfn3 = lambda text: (calls.append(text.startswith("set_option")), types.SimpleNamespace(ok=False, messages=[], errors=["1:0: unexpected token"]))[1]
    assert LD.lint_probe(_decl("  simp"), cfn3, LD.LINT_OPTS, lambda: True) == (None, "") and calls == [True, False], calls
    # the budget is asked before every compile
    calls.clear(); left = [1]

    def budget():
        left[0] -= 1
        return left[0] >= 0
    assert LD.lint_probe(_decl("  simp"), cfn3, LD.LINT_OPTS, budget) == (None, "") and calls == [True], calls


# ---- rendering ----------------------------------------------------------------------------------------------------------------------------
def arg(b, text, which=0):
    """The delsearch argument deletion of the which-th occurrence of item `text`."""
    return [d for d in LD.search_dels(b) if d.kind == "arg" and b[d.span[0]:d.span[1]] == text][which]


def test_render_lists():
    b = body_of("  simp only [a, b, c] at h\n  simpa [x,\n    y,\n    z] using h\n  simp [-foo, *]\n  simp [p] <;> simp [q, r]")
    assert cut(b, [arg(b, "a")]) .startswith("  simp only [b, c] at h\n")
    assert cut(b, [arg(b, "b")]).startswith("  simp only [a, c] at h\n")
    assert cut(b, [arg(b, "c")]).startswith("  simp only [a, b] at h\n")
    assert cut(b, [arg(b, "a"), arg(b, "c")]).startswith("  simp only [b] at h\n")
    assert cut(b, [arg(b, x) for x in "abc"]).startswith("  simp only at h\n")
    # multi-line lists keep the line break before each kept item
    assert "  simpa [y,\n    z] using h\n" in cut(b, [arg(b, "x")])
    assert "  simpa [x,\n    z] using h\n" in cut(b, [arg(b, "y")])
    assert "  simpa [x,\n    y] using h\n" in cut(b, [arg(b, "z")])
    assert "  simpa using h\n" in cut(b, [arg(b, x) for x in "xyz"])
    assert "  simp [*]\n" in cut(b, [arg(b, "-foo")]) and "  simp [-foo]\n" in cut(b, [arg(b, "*")])
    # `<;>`: each list on its own; an emptied list goes with its brackets
    assert cut(b, [arg(b, "p"), arg(b, "r")]).endswith("  simp <;> simp [q]")
    # an argument inside a deleted tactic is dropped with it
    line = next(d for d in LD.search_dels(b) if d.kind == "tac" and d.note.startswith("simp [-foo"))
    assert cut(b, [line, arg(b, "*")]) == cut(b, [line]) and "foo" not in cut(b, [line])
    # nested lists (an argument holding a simp call): the outer edit wins, the inner one is dropped
    b2 = body_of("  simp [a, show x = y by simp [q, w]]\n  exact h")
    dels = LD.search_dels(b2)
    assert [b2[d.span[0]:d.span[1]] for d in dels if d.kind == "arg"] == ["a", "q", "w"], dels
    assert cut(b2, [d for d in dels if d.kind == "arg" and b2[d.span[0]:d.span[1]] in ("a", "q")]) == "  simp [show x = y by simp [q, w]]\n  exact h"


def test_list_items():
    b = body_of('  simp [f x, (g, h), ⟨a, b⟩, "s,t", k] -- c, d\n  simp []\n  simp [a,]')
    mask = _mask(b); from harness.normalize import _pairs
    pairs = _pairs(b, mask)
    lb = b.index("["); items = LD._list_items(b, mask, pairs, lb)
    assert [b[x:y] for x, y in items] == ["f x", "(g, h)", "⟨a, b⟩", '"s,t"', "k"], items
    assert LD._list_items(b, mask, pairs, b.index("[]")) == [] and LD._list_items(b, mask, pairs, b.index("[a,]")) is None


# ---- delsearch candidates -----------------------------------------------------------------------------------------------------------------
def tacs(text):
    b = body_of(text)
    return [d.note for d in LD.search_dels(b) if d.kind == "tac"]


def test_search_args():
    b = body_of("  simp [f x, h, Nat.succ_le, ← two_mul, ↑cast_add, -bad, *, @foo, (h1), h₁] at h\n  -- simp [cmt]\n  have := \"simp [str]\"\n"
                "  simp? [no]\n  simp_all (config := {decide := true}) only [g1]\n  dsimp +zetaDelta only [g2]\n  exact (by simpa [g3] using h)\n"
                "  norm_num [nn]\n  aesop (add simp [aes])\n  exact h")
    got = [b[d.span[0]:d.span[1]] for d in LD.search_dels(b) if d.kind == "arg"]
    assert got == ["h", "Nat.succ_le", "← two_mul", "↑cast_add", "-bad", "*", "h₁", "g1", "g2", "g3"], got
    # term-mode bodies (no `by`) have no sites; a simp inside a term-mode `by` is one
    assert LD.search_dels(" fun x => foo [y]") == []
    assert [d.note for d in LD.search_dels(" foo (by simp [x, y])")] == ["x", "y"]


def test_search_lines():
    t = ("  intro x\n  norm_num\n  constructor\n  · simp\n    ring_nf\n    exact h\n  · exact h\n  cases n with\n  | zero => simp\n  | succ k => skip\n"
         "  calc a = b := by simp\n    _ = c := rfl\n  exact foo\n    bar\n  all_goals\n    simp\n  iterate 2\n    rfl\n  have h2 : a = a := by\n    rfl\n"
         "  simp at *\n  rw [h] <;>\n    simp\n  exact (f\n    x)\n  skip\n  exact h")
    got = tacs(t)
    # cleanup first (norm_num, ring_nf, simp at *, skip), then others, structural last; never: bullets, case arms, calc steps, continuation
    # lines, block openers, the only tactic of a block (all_goals / iterate / have bodies), the last tactic of a closing block
    assert got == ["norm_num", "ring_nf", "simp at *", "skip", "intro x", "constructor"], got
    # the first tactic of a nested block is a candidate when a sibling follows
    assert tacs("  have h2 : a = a := by\n    simp\n    rfl\n  exact h") == ["simp"]
    # a line after a `·` bullet line at the bullet's content column is a sibling (not the bullet's only tactic)
    assert tacs("  · simp\n    norm_num\n    rfl\n  exact h") == ["norm_num"]
    # comments: a comment line is no tactic; a `--` tail is deleted with its line
    b = body_of("  -- note\n  simp -- why\n  exact h")
    ds = [d for d in LD.search_dels(b) if d.kind == "tac"]
    assert [d.note for d in ds] == ["simp"] and cut(b, ds) == "  -- note\n  exact h", (ds, cut(b, ds))


def test_keys_survive_other_deletions():
    b = body_of("  simp [a, b]\n  norm_num\n  simp [a, b]\n  exact h")
    ds = LD.search_dels(b)
    keys = [d.key for d in ds]
    assert len(set(keys)) == len(keys), keys   # equal lines / items are told apart
    nn = next(d for d in ds if d.note == "norm_num")
    b2 = LD.render(b, [nn]); ds2 = LD.search_dels(b2)
    assert {d.key for d in ds2} == set(keys) - {nn.key}, ({d.key for d in ds2}, keys)


# ---- the greedy loop --------------------------------------------------------------------------------------------------------------------
class World:
    """Stub evaluate and probe compile. A candidate compiles iff every `need` substring is present; provisional score = base + the gains of
    the `gone` substrings that are absent; on the full check Z drops by 50 when a `z_need` substring is absent. The probe returns the
    messages built by `msgs(probe)`."""
    def __init__(self, gone=None, need=(), z_need=(), base=60.0, msgs=None, probe_ok=True):
        self.gone, self.need, self.z_need, self.base, self.calls, self.probes = gone or {}, need, z_need, base, [], []
        self.msgs, self.probe_ok = msgs or (lambda p: []), probe_ok

    def evaluate(self, d, full):
        self.calls.append((full, d))
        if not all(x in d for x in self.need):
            return {"ok": False}
        p = self.base + sum(v for k, v in self.gone.items() if k not in d)
        z = 100.0 - (50.0 if full and not all(k in d for k in self.z_need) else 0.0)
        return {"ok": True, "prov": round(p, 2), "Z": z, "score": round(p - (100 - z) / 3, 2), "tokens": 10, "heartbeats": 100}

    def compile(self, text):
        self.probes.append(text)
        return types.SimpleNamespace(ok=self.probe_ok, messages=self.msgs(text), errors=[])

    def run(self, d, **kw):
        kw.setdefault("head_lines", HL)
        return LD.delete_proof("t", d, evaluate_fn=self.evaluate, compile_fn=self.compile, statement=STMT, **kw)


def _arg_warns(*names):
    def msgs(p):
        out = []
        for nm in names:
            i = p.index(nm + ",") if nm + "," in p else p.index(nm + "]")
            out.append(warn(p, i, unused_arg(nm, "simp"), i + len(nm)))
        return out
    return msgs


def test_lint_all_at_once_then_site_by_site():
    d = _decl("  simp [a1, b1, c1]\n  exact h")
    w = World({"a1": 0.2, "c1": 0.2}, msgs=_arg_warns("a1", "c1"))
    r = w.run(d, ops=("lint",))
    assert r["status"] == "improved" and r["proof"] == _decl("  simp [b1]\n  exact h"), r
    assert r["applied"] == {"lint-arg": 2} and r["lint"]["probe"] == "ok" and r["lint"]["args"] == 2, r
    # base full + probe + all-at-once + final full = 4 compiles (the probe counts)
    assert r["compiles"] == 4 and len(w.calls) == 3 and len(w.probes) == 1 and w.probes[0].startswith(LD.probe_prefix(LD.LINT_OPTS)), r
    # all at once fails (a1 is needed despite the warning): site by site keeps only c1
    w = World({"a1": 0.2, "c1": 0.2}, need=("a1",), msgs=_arg_warns("a1", "c1"))
    r = w.run(d, ops=("lint",))
    assert r["status"] == "improved" and r["proof"] == _decl("  simp [a1, b1]\n  exact h") and r["applied"] == {"lint-arg": 1}, r
    assert [c[0] for c in w.calls] == [True, False, False, False, True], w.calls   # base, all, a1, c1, final
    # a deletion below the noise margin is not kept
    w = World({"a1": 0.04}, msgs=_arg_warns("a1"))
    r = w.run(_decl("  simp [a1, b1]\n  exact h"), ops=("lint",))
    assert r["status"] == "no gain" and r["proof"] == _decl("  simp [a1, b1]\n  exact h") and r["after"] == r["before"], r
    # the probe fails (also plain): lint reports it, delsearch still runs
    w = World({"b1": 0.3}, msgs=_arg_warns(), probe_ok=False)
    r = w.run(_decl("  simp [a1, b1]\n  exact h"))
    assert r["lint"]["probe"] == "failed" and len(w.probes) == 2 and r["status"] == "improved" and r["applied"] == {"delsearch-arg": 1}, r
    # opts=() (a project row with declaration modifiers): one plain probe
    w = World({"a1": 0.3}, msgs=_arg_warns("a1"))
    r = w.run(_decl("  simp [a1, b1]\n  exact h"), ops=("lint",), opts=())
    assert r["lint"]["probe"] == "plain" and w.probes == [_decl("  simp [a1, b1]\n  exact h")] and r["status"] == "improved", r


def test_delsearch_first_improvement_and_restart():
    d = _decl("  simp only [p, q, r] at h\n  norm_num\n  exact h")
    w = World({"q, ": 0.3, "norm_num": 0.3}, need=("p", "r]"))
    r = w.run(d, ops=("delsearch",))
    assert r["status"] == "improved" and r["proof"] == _decl("  simp only [p, r] at h\n  exact h"), r
    # p, q, r, then the cleanup lines `simp only ...` and `norm_num` (`exact h` closes the proof: never a candidate)
    assert r["applied"] == {"delsearch-arg": 1, "delsearch-tac": 1} and r["candidates"] == {"delsearch": 5}, r
    tried = [c[1][len(_decl("")):] for c in w.calls[1:-1]]
    # p fails; q promoted -> restart: p skipped (its key survives the sibling's deletion), r fails, the simp line (new code) fails,
    # norm_num promoted -> restart: every remaining key was rejected
    assert tried == ["  simp only [q, r] at h\n  norm_num\n  exact h", "  simp only [p, r] at h\n  norm_num\n  exact h",
                     "  simp only [p] at h\n  norm_num\n  exact h", "  norm_num\n  exact h", "  simp only [p, r] at h\n  exact h"], tried
    assert r["compiles"] == 7 and r["deleted"] == ["delsearch: q", "delsearch: norm_num"], r
    # lint's rejected deletions are never retried by delsearch
    w = World({"q, ": 0.3}, need=("p",), msgs=_arg_warns("p"))
    r = w.run(_decl("  simp only [p, q, r] at h\n  exact h"))
    texts = [c[1] for c in w.calls if not c[0]]
    assert sum("[q, r]" in t for t in texts) == 1, texts   # p tried once (by lint), never again
    assert r["status"] == "improved" and r["proof"] == _decl("  simp only [p, r] at h\n  exact h"), r
    # no candidates and no lint: nothing compiled
    w = World(); r = w.run(_decl("  exact h.symm"), ops=("delsearch",))
    assert r["status"] == "no sites" and r["compiles"] == 0 and w.calls == [], r


def test_noise_and_stored_base():
    stored = {"ok": True, "score": 60.0, "Z": 100.0, "L": 40.0, "H": 40.0}
    w = World({"b1": 0.3}); r = w.run(_decl("  simp [a1, b1]\n  exact h"), ops=("delsearch",), base=stored)
    assert r["status"] == "improved" and r["before"]["score"] == 60.0 and r["gain_vs_stored"] == 0.3, r
    assert [c[0] for c in w.calls] == [False, False, False, False, True], w.calls   # fresh primary, a1, b1, the simp line, final
    # the stored score was a lucky draw: a +0.12 deletion beats the fresh measurement but not the stored score by the margin
    w = World({"b1": 0.12}, base=59.9); r = w.run(_decl("  simp [a1, b1]\n  exact h"), ops=("delsearch",), base=stored)
    assert r["status"] == "no gain" and r["reason"] == "not strictly better on the full check", r
    # the input no longer compiles
    r = World(need=("zzz",)).run(_decl("  simp [a1, b1]\n  exact h"), base=stored)
    assert r["status"] == "input does not compile" and r["compiles"] == 1, r
    assert LD.delete_proof("t", "theorem other : True := by\n  simp", evaluate_fn=lambda d, f: {}, compile_fn=lambda t: None, statement=STMT,
                           head_lines=0)["status"] == "statement differs"


def test_final_all_pin_check():
    # three promoted steps; the third breaks an older pin: the longest passing prefix (two steps) is kept
    d = _decl("  simp [a1, b1, c1]\n  exact h")
    w = World({"a1": 0.3, "b1": 0.3, "c1": 0.3}, z_need=("c1",))
    r = w.run(d, ops=("delsearch",))
    assert r["status"] == "improved" and r["proof"] == _decl("  simp [c1]\n  exact h") and r["steps_dropped"] == 1, r
    assert r["applied"] == {"delsearch-arg": 2} and r["after"]["Z"] == 100.0, r
    # the only step breaks a pin: no gain, the input kept
    w = World({"a1": 0.3}, z_need=("a1",)); r = w.run(_decl("  simp [a1, b1]\n  exact h"), ops=("delsearch",))
    assert r["status"] == "no gain" and r["reason"] == "pins broke" and r["tried"]["Z"] == 50.0 and r["proof"] == _decl("  simp [a1, b1]\n  exact h"), r
    # a full check without Z is never taken as Z = 100
    class W3(World):
        def evaluate(self, d, full):
            e = super().evaluate(d, full)
            if full and "a1" not in d:
                e.pop("Z")
            return e
    r = W3({"a1": 0.3}).run(_decl("  simp [a1, b1]\n  exact h"), ops=("delsearch",))
    assert r["status"] == "no gain" and r["reason"] == "final check reported no Z", r
    # the prefix search respects the deadline
    class Late(World):
        def __init__(self, *a, **k):
            super().__init__(*a, **k); self.t = 0.0

        def evaluate(self, d, full):
            if full and "c1" not in d:
                self.t = 100.0
            return super().evaluate(d, full)
    w = Late({"a1": 0.3, "b1": 0.3, "c1": 0.3}, z_need=("c1",))
    r = w.run(d, ops=("delsearch",), deadline=50.0, clock=lambda: w.t)
    assert r["status"] == "no gain" and r["stopped"] == "deadline" and r["reason"] == "pins broke", r


def test_max_compiles_and_deadline():
    d = _decl("  simp [a1, b1, c1, d1]\n  exact h")
    w = World({"d1": 0.3}, need=("a1", "b1", "c1"))
    r = w.run(d, ops=("delsearch",), max_compiles=4)
    # base 1 + candidates until n = max - 1 (a1, b1) + nothing kept -> no final check
    assert r["stopped"] == "max-compiles" and r["status"] == "no gain" and len(w.calls) == 3 and r["compiles"] == 3, r
    w = World({"a1": 0.3}); r = w.run(d, ops=("delsearch",), max_compiles=3)
    assert r["stopped"] == "max-compiles" and r["status"] == "improved" and r["compiles"] == 3, r   # base, a1, final (reserved)
    # the probe counts against the budget: max 3 -> base, probe, then the reserved final only
    w = World({"a1": 0.3}, msgs=_arg_warns("a1")); r = w.run(d, max_compiles=3)
    assert r["stopped"] == "max-compiles" and r["status"] == "no gain" and len(w.probes) == 1, r
    t = iter(range(100))
    w = World({"c1": 0.3}); r = w.run(d, ops=("delsearch",), deadline=2, clock=lambda: next(t))
    assert r["stopped"] == "deadline" and r["status"] == "no gain" and len(w.calls) == 3, (r, w.calls)   # base, a1, b1; c1 never tried


# ---- review fixes (2026-10-13) ------------------------------------------------------------------------------------------------------------
def test_review_lint_pin_check_before_delsearch():
    # finding 1: the lint deletion (unused on the newest toolchain) breaks an older pin; norm_num alone would pay. The lint step is dropped
    # after one full check and delsearch starts from the input proof; the lint deletion is never retried.
    d = _decl("  simp [a1, b1]\n  norm_num\n  exact h")
    w = World({"a1": 0.3, "norm_num": 0.3}, need=("simp [",), z_need=("a1",), msgs=_arg_warns("a1"))
    r = w.run(d)
    assert r["status"] == "improved" and r["proof"] == _decl("  simp [a1, b1]\n  exact h") and r["applied"] == {"delsearch-tac": 1}, r
    assert r["lint"]["pins"] == "broke" and r["compiles"] == 8, r   # base, probe, a1, pin check, b1, simp line, norm_num, final
    assert sum(c[1].endswith("  simp [b1]\n  norm_num\n  exact h") for c in w.calls) == 2, w.calls   # the trial + its pin check only
    # the lint step holds on every pin and nothing else pays: the final check is the cached pin check (no extra compile)
    w = World({"a1": 0.3}, need=("simp [",), msgs=_arg_warns("a1"))
    r = w.run(d)
    assert r["status"] == "improved" and r["lint"]["pins"] == "ok" and r["applied"] == {"lint-arg": 1}, r
    assert r["compiles"] == 7 and [c[0] for c in w.calls] == [True, False, True, False, False, False], (r, w.calls)
    # lint only: no early pin check (the final check is the only full one)
    w = World({"a1": 0.3}, need=("simp [",), msgs=_arg_warns("a1"))
    r = w.run(d, ops=("lint",))
    assert "pins" not in r["lint"] and [c[0] for c in w.calls] == [True, False, True], w.calls
    # a lint-only run without warnings has no sites (it was 'no gain')
    w = World(msgs=lambda p: [])
    r = w.run(d, ops=("lint",))
    assert r["status"] == "no sites" and r["compiles"] == 2 and r["lint"]["warnings"] == 0, r


def test_review_tactic_deletion_shapes():
    # finding 2: a no-op tactic after a trailing `<;>` / `<|>` / `;` goes with that operator (the next tactic is not swallowed)
    for op in ("<;>", "<|>", ";"):
        b, dels, c = parse(f"  simp {op} -- c\n    rfl\n  exact h",
                           lambda p: [warn(p, p.index("rfl"), "'rfl' tactic does nothing" + NOTE_TAC, p.index("rfl") + 3)])
        assert c["tactics"] == 1 and not dels[0].whole and cut(b, dels) == "  simp\n  exact h", (op, cut(b, dels))
    # a line that is just `<;> tac` goes whole
    b, dels, _ = parse("  constructor\n  <;> rfl\n  exact h", lambda p: [warn(p, p.index("rfl"), "'rfl' tactic does nothing", p.index("rfl") + 3)])
    assert cut(b, dels) == "  constructor\n  exact h", cut(b, dels)
    # finding 5: the printed tactic must be the source text (up to blanks); a shifted position is unmatched
    t = "  simp only [a,\n    b]\n  norm_num\n  exact h"
    b, dels, c = parse(t, lambda p: [warn(p, p.index("simp"), "'simp only [a, b]' tactic does nothing", p.index("b]") + 2),
                                     warn(p, p.index("norm_num") + 2, "'norm_num' tactic does nothing", p.index("norm_num") + 10),
                                     warn(p, p.index("exact"), "'norm_num' tactic does nothing", p.index("exact") + 7)])
    assert c == {"warnings": 3, "args": 0, "tactics": 1, "unmatched": 2} and cut(b, dels) == "  norm_num\n  exact h", (c, cut(b, dels))


def test_review_line_candidates():
    # finding 3: a `first` opener followed by `| alt` lines, the left side of a leading `<;>` line, and `where` items are not candidates
    assert tacs("  intro x\n  first\n  | simp\n  | rfl\n  exact h") == ["intro x"]
    assert tacs("  constructor\n  <;> simp\n  norm_num\n  exact h") == ["norm_num"]
    assert tacs("  simp\n  exact h\nwhere\n  foo : Nat := 1\n  bar : Nat := 2") == ["simp"]
    assert tacs("  norm_num\n  exact h\ntermination_by n\ndecreasing_by\n  simp_wf\n  omega") == ["norm_num"]


def test_review_applied_counts_survive_rendering():
    # finding 4: an argument dropped by rendering (q1 inside the outer list's edited range) is neither compiled nor counted
    t = "  simp [a1, show x = y by simp [q1, w1]]\n  exact h"

    def msgs(p):
        i, q = p.index("a1"), p.index("q1")
        return [warn(p, i, unused_arg("a1", "simp"), i + 2), warn(p, q, unused_arg("q1", "simp"), q + 2)]
    b = body_of(t); d1 = LD.lint_dels(b, len(_decl(t)) - len(b), 0, _decl(t), msgs(_decl(t)), HL)[0]
    txt, kept = LD.render_kept(b, d1)
    assert [x.note for x in kept] == ["a1"] and txt == LD.render(b, d1), kept
    w = World({"a1": 0.3, "q1": 0.3}, msgs=msgs)
    r = w.run(_decl(t), ops=("lint",))
    assert r["status"] == "improved" and r["applied"] == {"lint-arg": 1} and r["deleted"] == ["lint: a1"], r
    assert r["compiles"] == 4, r   # base, probe, a1, final (the dropped q1 costs nothing)


def test_review_leave_one_out():
    # all at once pays (+0.1) but the `←` deletion costs 0.2: leave-one-out keeps it
    t = "  simp [← m1, b1, c1]\n  exact h"
    w = World({"← m1": -0.2, "b1": 0.3}, msgs=_arg_warns("← m1", "b1"))
    r = w.run(_decl(t), ops=("lint",))
    assert r["status"] == "improved" and r["proof"] == _decl("  simp [← m1, c1]\n  exact h") and r["applied"] == {"lint-arg": 1}, r
    assert len(w.calls) == 4, w.calls   # base, all at once, leave ← m1 out, final


def test_review_probe_layout_timeout_and_unknown_cache():
    # finding 5: modifiers ending mid-line shift the first line's columns
    real = _SC.file_prefix
    _SC.file_prefix = lambda row, version: "import X\n\n@[simp]\nprivate "
    try:
        assert LD._probe_layout({"source": "cslib"}, "v") == (3, (), 8)
        _SC.file_prefix = lambda row, version: "import X\n\n\n"
        assert LD._probe_layout({"source": "cslib"}, "v") == (2, LD.LINT_OPTS, 0)
    finally:
        _SC.file_prefix = real
    assert LD._probe_layout({"source": "putnambench", "header": "import Mathlib\nopen Real\n"}, "v") == (3, LD.LINT_OPTS, 0)
    d = STMT + " := by simp [x, y]"; b = " by simp [x, y]"; y = d.index("y]")
    m = [{"severity": "warning", "data": unused_arg("y", "simp [x]"), "pos": {"line": HL + 1, "column": y + 8}, "endPos": None}]
    dels, c = LD.lint_dels(b, len(d) - len(b), 0, d, m, HL, head_col=8)
    assert LD.render(b, dels) == " by simp [x]" and c["args"] == 1, (dels, c)
    assert LD.lint_dels(b, len(d) - len(b), 0, d, m, HL)[0] == []   # unshifted: off the line, ignored
    # finding 6: a timed-out probe is not retried plain
    calls = []
    cfn = lambda text: (calls.append(1), types.SimpleNamespace(ok=False, timed_out=True, messages=[], errors=["timeout"]))[1]
    assert LD.lint_probe(_decl("  simp"), cfn, LD.LINT_OPTS, lambda: True) == (None, "") and calls == [1], calls
    # finding 7: an option found unknown for a (source, toolchain) is not probed again in this process
    key = ("strata-test", "v0")
    LD._UNKNOWN_OPTS.pop(key, None)

    class NoTac(World):
        def compile(self, text):
            self.probes.append(text)
            bad = "linter.unusedTactic" in text
            return types.SimpleNamespace(ok=not bad, errors=[], messages=[{"severity": "error", "data": "Unknown option `linter.unusedTactic`"}]
                                         if bad else [])
    try:
        w = NoTac(); w.run(_decl("  simp [a1, b1]\n  exact h"), ops=("lint",), opt_key=key)
        assert len(w.probes) == 2 and LD._UNKNOWN_OPTS[key] == {"linter.unusedTactic"}, (w.probes, LD._UNKNOWN_OPTS)
        w = NoTac(); r = w.run(_decl("  simp [a1, b1]\n  exact h"), ops=("lint",), opt_key=key)
        assert len(w.probes) == 1 and w.probes[0].startswith("set_option linter.unusedSimpArgs true in\ntheorem") and r["lint"]["probe"] == "ok", w.probes
    finally:
        LD._UNKNOWN_OPTS.pop(key, None)


# ---- batch mode -------------------------------------------------------------------------------------------------------------------------
NAMES = ("putnam", "Core", "InitsUpdatesComm", "not_a_row", "P1", "P2", "1964")


def _work_root(td):
    wr = pathlib.Path(td)
    for name, best in (("putnam_1964_b2", {"score": 60.0, "proof": "P1", "Z": 100.0}), ("Core.InitsUpdatesComm", {"score": 50.0, "proof": "P2", "Z": 100.0}),
                       ("putnam_1964_a4", {"score": 33.33, "proof": None}), ("not_a_row", {"score": 70.0, "proof": "P3"})):
        (wr / name).mkdir(); (wr / name / "state.json").write_text(json.dumps({"problem": name, "best": best}))
    return wr


def test_work_root_post_pass():
    with tempfile.TemporaryDirectory() as td:
        wr = _work_root(td); seen, banked = [], []

        def dl(name, proof, base=None, max_compiles=24, ops=LD.OPS, deadline=None, **kw):
            seen.append((name, base["score"], ops, kw.get("min_gain")))
            return {"status": "improved" if proof == "P1" else "no gain", "proof": proof + "!", "compiles": 3, "applied": {"lint-arg": 1}}
        chk = lambda w, name, proof: (banked.append((w.name, proof)), {"new_best": True, "score": 61.25})[1]
        c = LD.delete_work_root(wr, "x-p1", delete_fn=dl, check_fn=chk, ops=("lint",))
        assert sorted(s[0] for s in seen) == ["Core.InitsUpdatesComm", "putnam_1964_b2"] and seen[0][2] == ("lint",) and seen[0][3] == LD.MIN_GAIN, seen
        assert banked == [("putnam_1964_b2", "P1!")] and c["problems"] == 2 and c["improved"] == 1 and c["banked"] == 1 and c["gain"] == 1.25, c
        assert [r["row"] for r in c["rows"]] == [1, 2] and not any("name" in r or "problem" in r for r in c["rows"])
        c = LD.delete_work_root(wr, "x", deadline_s=-1, delete_fn=dl, check_fn=chk)
        assert c["skipped_deadline"] == 2 and c["problems"] == 0
        c = LD.delete_work_root(wr, "x", delete_fn=lambda *a, **k: 1 / 0, check_fn=chk)
        assert c["errors"] == 2 and [r["status"] for r in c["rows"]] == ["error ZeroDivisionError"] * 2, c

        def chk_bad(w, name, proof):
            raise OSError(f"cannot open {w}/state.json")
        c = LD.delete_work_root(wr, "x", delete_fn=lambda name, proof, **kw: {"status": "improved", "proof": proof + "!", "compiles": 2},
                                check_fn=chk_bad)
        assert c["bank_errors"] == 2 and [r["status"] for r in c["rows"]] == ["bank error OSError"] * 2, c
        for bad in ("../x", "a/b", "..", "", ".hidden"):
            try:
                LD.delete_work_root(wr, bad, delete_fn=dl, check_fn=chk); raise AssertionError(bad)
            except ValueError:
                pass
        try:
            LD.delete_work_root(wr, "x", delete_fn=dl, check_fn=chk, kind="api"); raise AssertionError("kind")
        except ValueError:
            pass


def test_default_bank_kind_and_lock_wait():
    with tempfile.TemporaryDirectory() as td:
        wr = _work_root(td); got = []
        guard = _IR.locked_check
        _IR.locked_check = lambda w, name, text, prov, vpath, lock_wait=1700.0: (got.append((prov, vpath, lock_wait)), {"new_best": True, "score": 61.0})[1]
        try:
            c = LD.delete_work_root(wr, "x-p1", problems={"putnam_1964_b2"}, deadline_s=1000.0, clock=lambda: 5.0, kind="api-dev-only",
                                    delete_fn=lambda name, proof, **kw: {"status": "improved", "proof": proof + "!", "compiles": 2})
        finally:
            _IR.locked_check = guard
        assert c["banked"] == 1 and len(got) == 1, (c, got)
        prov, vpath, lw = got[0]
        assert prov == {"kind": "api-dev-only", "model": "lint-delete@cpu", "run_id": "x-p1", "mode": "lint-delete"}, prov
        assert vpath == ROOT / "probe/runs/x-p1/verified.jsonl" and lw == 1000.0, (vpath, lw)


def _run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            LD.main(argv)
        except SystemExit:
            pass
    return out.getvalue(), err.getvalue()


def test_batch_stdout_counts_only():
    with tempfile.TemporaryDirectory() as td:
        wr = _work_root(td)
        real, real_bank = LD.delete_proof, LD._bank
        seen = []
        LD.delete_proof = lambda name, proof, **kw: (seen.append(kw["ops"]), {"status": "improved", "proof": proof + "!", "compiles": 5,
                                                                             "applied": {"lint-arg": 2, "delsearch-tac": 1}})[1]
        LD._bank = lambda w, name, proof, run_id, **kw: (seen.append(kw), {"new_best": True, "score": 61.0})[1]
        try:
            s, e = _run_main(["--work-root", str(wr), "--run-id", "x-p1", "--max-compiles", "8", "--ops", "delsearch,lint"])
        finally:
            LD.delete_proof, LD._bank = real, real_bank
        assert "row#1 improved compiles 5 applied delsearch-tac:1,lint-arg:2 banked" in s and "2 banked" in s, s
        assert seen[0] == ("lint", "delsearch") and all(k["kind"] == "closed-dev-only" and k["lock_wait"] >= 60.0 for k in seen[1::2]), seen
        for name in NAMES:
            assert name not in s and name not in e, (name, s, e)
        # errors: by class only, no traceback, no names
        def boom(name, proof, **kw):
            raise ValueError(f"boom in {name} ({proof})")
        LD.delete_proof = boom
        try:
            s, e = _run_main(["--work-root", str(wr), "--run-id", "x-p1", "--kind", "api-dev-only"])
        finally:
            LD.delete_proof = real
        assert "error ValueError" in s and "2 errors" in s and "Traceback" not in e, (s, e)
        for name in NAMES:
            assert name not in s and name not in e, (name, s, e)
        s, e = _run_main(["--work-root", str(wr), "--run-id", "../../x"])
        assert s == "" and "--run-id" in e, (s, e)
        try:
            LD._ops_arg("lint,bogus"); raise AssertionError("bogus op")
        except SystemExit as ex:
            assert "unknown operator" in str(ex) and "bogus" in str(ex), ex
        assert LD._ops_arg("delsearch,lint") == ("lint", "delsearch") and LD._ops_arg(None) == LD.OPS


def main() -> int:
    tests = [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]
    bad = 0
    for k, fn in tests:
        try:
            fn(); print(f"PASS {k}")
        except Exception:  # noqa: BLE001
            bad += 1; print(f"FAIL {k}"); traceback.print_exc()
    if GUARD_HITS:
        bad += 1; print(f"FAIL compile guard: {GUARD_HITS}")
    print(f"{len(tests) - bad}/{len(tests)} passed" + ("" if not GUARD_HITS else " (compile guard hit)"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
