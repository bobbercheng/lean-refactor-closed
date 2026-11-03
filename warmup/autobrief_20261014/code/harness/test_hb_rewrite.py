#!/usr/bin/env python3
"""Unit tests of harness/hb_rewrite.py (heartbeat micro-normalizer), plain asserts, no Lean: site detection and rewriting per operator on
realistic snippets (negative cases: comments, strings, mid-term words, term notation `exists x, p`, `<|`, rwa / erw / nth_rw / rw_mod_cast /
simp_rw, conv blocks, the last `rw` of a closing block, `<;>`, multi-line lists and arguments, `at h`), the greedy loop with a stubbed
evaluate (keeps exactly the sites that pay, leave-one-out after an all-at-once group, the noise margin, the stored-best re-measure), the
final all-pin check (Z drop / missing Z -> no gain, the one-operator fallback and its deadline), max-compiles / deadline stops, and the batch
mode (banking through the injected check with kind and a bounded lock wait, run-id validation, row errors by class only, no problem names
on stdout or stderr). Every compile entry point is replaced by a guard that fails the run when called.
    python3 harness/test_hb_rewrite.py"""
from __future__ import annotations

import contextlib, io, json, pathlib, random, subprocess, sys, tempfile, traceback, zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import hb_rewrite as HR  # noqa: E402
from harness.normalize import apply, _mask  # noqa: E402
from harness import leantools as _LT, normalize as _NZ, inrun as _IR  # noqa: E402

# ---- compile guard: nothing in these tests may compile Lean or spawn a process -------------------------------------------------------------
GUARD_HITS: list = []


def _guard(label):
    def f(*a, **k):
        GUARD_HITS.append(label)
        raise AssertionError(f"{label} called in a unit test")
    return f


for _mod, _names in ((_LT, ("comp", "lean_check", "run_lean", "lean_run")), (_NZ, ("comp", "evaluate")), (_IR, ("locked_check",))):
    for _n in _names:
        if hasattr(_mod, _n):
            setattr(_mod, _n, _guard(f"{_mod.__name__}.{_n}"))
subprocess.Popen = _guard("subprocess.Popen")

STMT = "theorem t (a b : Nat) (h : a = b) : b = a"


def _decl(body: str) -> str:
    return STMT + " := by\n" + body


def body_of(text: str) -> str:
    return " by\n" + text   # what split_declaration returns for _decl(text)


def sites_of(text: str, op: str):
    b = body_of(text)
    return b, [s for s in HR.sites(b, (op,))]


def calls(b, ss):
    return [b[s.span[0]:s.span[1]] for s in ss]


def one(b, s):
    return apply(b, [s])[len(" by\n"):]


def rep_of(b, s):
    """The text that replaces the site's call (the line from the call on)."""
    return one(b, s)[s.span[0] - 4:].split("\n")[0]


# ---- operators --------------------------------------------------------------------------------------------------------------------------
def test_rw2rewrite():
    t = ("  intro x\n  rw [foo, ← bar] at h\n  -- rw [in_comment]\n  rwa [baz] at h\n  erw [q]\n  nth_rw 2 [q]\n  rw_mod_cast [q]\n"
         "  simp_rw [q]\n  exact (by rw [h])\n  have := \"rw [s]\"\n  simp <;> rw [h1,\n    h2]\n  exact h.rw\n  exact foo rw_lemma\n"
         "  · rw [Nat.add_comm] at h ⊢ <;> simp\n  all_goals rw (config := {}) [x]\n  rw? \n  /- rw [blk] -/ rw [after_block]\n  iterate 2 rw [it]")
    b, ss = sites_of(t, "rw2rewrite")
    # `exact (by rw [h])`: the last tactic of a `by` block, its rfl closed the goal -> not a site
    assert calls(b, ss) == ["rw [foo, ← bar] at h", "rw [h1,\n    h2]", "rw [Nat.add_comm] at h ⊢", "rw (config := {}) [x]",
                            "rw [after_block]", "rw [it]"], calls(b, ss)
    # the last tactic of a combinator block (<;>, all_goals, iterate) is a late site; a leading comment does not make a tactic final
    assert [s.late for s in ss] == [False, True, False, True, False, True], [s.late for s in ss]
    assert one(b, ss[0]).splitlines()[1] == "  rewrite [foo, ← bar] at h"
    assert one(b, ss[1]).endswith("simp <;> rewrite [h1,\n    h2]\n  exact h.rw\n  exact foo rw_lemma\n  · rw [Nat.add_comm] at h ⊢ <;> simp\n"
                                  "  all_goals rw (config := {}) [x]\n  rw? \n  /- rw [blk] -/ rw [after_block]\n  iterate 2 rw [it]")
    assert all(s.dtok == 0 for s in ss)   # rw and rewrite are one arena token each
    # no `by` before the site: a term-mode body has no tactic sites
    assert HR.sites(" fun x => foo\n  rw [h]", ("rw2rewrite",)) == []
    # closing blocks (bullet inline / bullet block / by / end of proof) and conv blocks are not sites; a combinator block's last rw is late;
    # the `at` clause stops at a comment
    t2 = ("  constructor\n  · rw [a]\n  · simp\n    rw [b] at g\n  have : x := by rw [c]\n  conv_lhs => rw [Nat.add_comm]\n  conv =>\n"
          "    lhs\n    rw [d]\n  all_goals\n    rw [e]\n  rw [f] at g -- note, x\n  case h => rw [k]\n  rw [z]")
    b, ss = sites_of(t2, "rw2rewrite")
    assert calls(b, ss) == ["rw [e]", "rw [f] at g"] and [s.late for s in ss] == [True, False], (calls(b, ss), [s.late for s in ss])
    # conv: simp only is still a site there (conv has dsimp)
    assert calls(*sites_of("  conv_lhs => simp only [f]\n  exact h", "simponly2dsimp")) == ["simp only [f]"]


def test_simponly2dsimp():
    t = ("  simp only [f, g] at h ⊢\n  simp only\n  simp_all only [x]\n  simpa only [x] using h\n  simp (config := {}) only [y]\n"
         "  simp only [a] at h <;> simp only [b]\n  exact ⟨by simp only [c], h⟩\n  -- simp only [d]\n  exact h simp only")
    b, ss = sites_of(t, "simponly2dsimp")
    assert calls(b, ss) == ["simp only [f, g] at h ⊢", "simp only", "simp only [a] at h", "simp only [b]", "simp only [c]"], calls(b, ss)
    assert one(b, ss[0]).startswith("  dsimp only [f, g] at h ⊢\n  simp only\n") and all(s.dtok == 0 for s in ss)
    assert "<;> dsimp only [b]" in one(b, ss[3]) and "⟨by dsimp only [c], h⟩" in one(b, ss[4])


def test_simprw2only():
    t = "  simp_rw [mul_comm a, ← add_assoc] at h ⊢\n  simp_rw (config := {}) [x]\n  -- simp_rw [y]\n  simp_rw [h1,\n    h2] <;> rfl"
    b, ss = sites_of(t, "simprw2only")
    assert calls(b, ss) == ["simp_rw [mul_comm a, ← add_assoc] at h ⊢", "simp_rw (config := {}) [x]", "simp_rw [h1,\n    h2]"]
    assert one(b, ss[0]).splitlines()[0] == "  simp only [mul_comm a, ← add_assoc] at h ⊢" and ss[0].dtok == 1
    assert one(b, ss[1]).splitlines()[1] == "  simp (config := {}) only [x]"
    assert "simp only [h1,\n    h2] <;> rfl" in one(b, ss[2])


def test_repeatrw():
    t = ("  repeat rw [h]\n  repeat (rw [Nat.mul_comm] at g)\n  repeat\n    rw [mul_comm]\n  exact h\n  repeat rw [k] <;> simp\n"
         "  repeat\n    rw [a]\n    simp\n  repeat' rw [r]\n  repeat rw (config := {}) [c]\n  · repeat\n      rw [p, q]\n    simp")
    b, ss = sites_of(t, "repeatrw")
    assert calls(b, ss) == ["repeat rw [h]", "repeat (rw [Nat.mul_comm] at g)", "repeat\n    rw [mul_comm]", "repeat\n      rw [p, q]"], calls(b, ss)
    out = apply(b, ss)[len(" by\n"):]
    assert out.startswith("  simp only [h]\n  simp only [Nat.mul_comm] at g\n  simp only [mul_comm]\n  exact h\n  repeat rw [k] <;> simp\n"), out
    assert out.endswith("  · simp only [p, q]\n    simp"), out
    assert [s.dtok for s in ss] == [0, -2, 0, 0]
    # a repeat site and the rw inside it conflict: they are never both kept
    allb = HR.sites(b)
    rep, inner = next(s for s in allb if s.op == "repeatrw"), next(s for s in allb if s.op == "rw2rewrite")
    assert HR.conflicts(inner, [rep])
    # a further line aligned with the rw belongs to the repeat body: moving it out of the loop would break the proof
    assert sites_of("  repeat rw [h]\n         rw [g]\n  exact x", "repeatrw")[1] == []


def test_use_exists():
    t = ("  constructor\n  · use 1, 2\n    simp\n  · use x\n  exists 3\n  exact foo\n  have : ∃ n, n = 0 := by exists 0\n  use! 5\n"
         "  use (discharger := skip) 6\n  use f <;> simp\n  use a,\n    b\n  -- use z\n  exact List.exists_of_mem h\n  rcases h with ⟨y, hy⟩\n  exists y")
    b, ss = sites_of(t, "use2refine")
    got = [(b[s.span[0]:s.span[1]], rep_of(b, s)) for s in ss]
    assert [g[0] for g in got] == ["use 1, 2"] * 4 + ["use x"] * 4 + ["use f"] * 4 + ["use a,\n    b"] * 4, got
    # every call gets all four variants; the layout (last tactic of its block or not) only orders them
    assert [g[1] for g in got] == ["refine ⟨1, 2, ?_⟩", "exists 1, 2", "exact ⟨1, 2⟩", "exact ⟨1, 2, rfl⟩",
                                   "exact ⟨x⟩", "exact ⟨x, rfl⟩", "exists x", "refine ⟨x, ?_⟩",
                                   "refine ⟨f, ?_⟩ <;> simp", "exists f <;> simp", "exact ⟨f⟩ <;> simp", "exact ⟨f, rfl⟩ <;> simp",
                                   "refine ⟨a, b, ?_⟩", "exists a, b", "exact ⟨a, b⟩", "exact ⟨a, b, rfl⟩"], got
    assert [s.dtok for s in ss][:2] == [4, 0] and len({s.span for s in ss[:4]}) == 1   # variants of one call share its span
    b, ss = sites_of(t, "exists2refine")
    reps = [rep_of(b, s) for s in ss]
    assert reps == ["refine ⟨3, ?_⟩", "exact ⟨3, rfl⟩", "exact ⟨0, rfl⟩", "refine ⟨0, ?_⟩", "exact ⟨y, rfl⟩", "refine ⟨y, ?_⟩"], reps
    # term operators inside the arguments (`<|`, `|>.`) do not end them; the call is final under a `·` (next line less indented)
    b, ss = sites_of("  cases h\n  · use s', htr.choiceR, .bisim <| .refl _\n  · exact hb |>.imp id", "use2refine")
    assert [one(b, s).splitlines()[1] for s in ss] == ["  · exact ⟨s', htr.choiceR, .bisim <| .refl _⟩",
                                                       "  · exact ⟨s', htr.choiceR, .bisim <| .refl _, rfl⟩",
                                                       "  · exists s', htr.choiceR, .bisim <| .refl _",
                                                       "  · refine ⟨s', htr.choiceR, .bisim <| .refl _, ?_⟩"], [one(b, s) for s in ss]
    # a complete argument list on sibling goals (no bullets, same indent): `exact ⟨args⟩` is offered although the layout says not final
    b, ss = sites_of("  induction h\n  use p, h, .red_K ..\n  use e, .red_K .., h", "use2refine")
    assert "exact ⟨p, h, .red_K ..⟩" in [rep_of(b, s) for s in ss], [rep_of(b, s) for s in ss]
    b, ss = sites_of("  induction h with\n  | a => use a₂, h₂, .refl a₂\n  | b => exact x", "use2refine")
    assert rep_of(b, ss[0]) == "exact ⟨a₂, h₂, .refl a₂⟩", [rep_of(b, s) for s in ss]


def test_use_exists_negative():
    # term notation `exists x, p`: in a type, after `<|`, in a fun body, in a set-builder; `|` alternatives only inside `first`
    t = ("  have h1 : (exists x, x = 1) := ⟨1, rfl⟩\n  exact foo <| exists x, P x\n  have h2 := fun z => exists x, x = z\n"
         "  have h3 : {n | exists m, m = n} = s := rfl\n  first | exists 1 | exact h\n  cases n with\n  | zero => exists 0\n  | succ k => exact h")
    b, ss = sites_of(t, "exists2refine")
    assert sorted({b[s.span[0]:s.span[1]] for s in ss}) == ["exists 0", "exists 1"], calls(b, ss)
    mask = _mask(b); i = b.index("exists x, P x")
    assert HR._prev_token(b, mask, i) == "<|" and not HR._tac_pos(b, mask, i, b.index("by"))
    # bar lines under `first`
    b, ss = sites_of("  first\n  | exists 1\n  | exact h", "exists2refine")
    assert calls(b, ss)[:1] == ["exists 1"], calls(b, ss)
    # arguments continued below (`by` at the line end, an application on the next line) are not sites; commas in strings do not split
    t = '  use 1, by\n    simp\n  use foo\n    bar\n  use "a,b", 2'
    b, ss = sites_of(t, "use2refine")
    assert {b[s.span[0]:s.span[1]] for s in ss} == {'use "a,b", 2'}, calls(b, ss)
    assert rep_of(b, ss[0]) == 'exact ⟨"a,b", 2⟩' and 'refine ⟨"a,b", 2, ?_⟩' in [rep_of(b, s) for s in ss]


def test_withreducible():
    t = ("  first | apply foo | exact bar | simp\n  first\n    | apply A\n    | (apply B)\n    | with_reducible apply C\n    | exact D\n"
         "  exact h\n  -- first | apply E\n  exact h (first)\n  all_goals first | apply F <;> simp | exact G x\n  first | apply H; simp | exact I")
    b, ss = sites_of(t, "withreducible")
    marks = [b[s.span[0]:s.span[0] + 9] for s in ss]
    # `apply F <;> simp` and `apply H; simp`: with_reducible takes a sequence, it would also cover simp -> not sites
    assert marks == ["apply foo", "exact bar", "apply A\n ", "exact D\n ", "exact G x", "exact I"], marks
    out = apply(b, ss)[len(" by\n"):]
    assert out.splitlines()[0] == "  first | with_reducible apply foo | with_reducible exact bar | simp"
    assert "    | with_reducible exact D\n  exact h\n" in out and "(apply B)" in out and "exact h (first)" in out
    assert "| apply F <;> simp | with_reducible exact G x" in out and "| apply H; simp | with_reducible exact I" in out
    assert all(s.dtok == 1 for s in ss)
    # bars aligned with `first` (Mathlib style); a later bar left of the first bar's column is not first's (colGe); a continuation line
    b, ss = sites_of("  first\n  | apply A\n  | exact B\n  exact h", "withreducible")
    assert [b[s.span[0]:s.span[1]] for s in ss] == ["apply", "exact"], calls(b, ss)
    b, ss = sites_of("  first | apply A\n    | exact B\n  exact h", "withreducible")
    assert [b[s.span[0]:s.span[0] + 7] for s in ss] == ["apply A"], calls(b, ss)
    b, ss = sites_of("  first | apply A\n          <;> simp\n  exact h", "withreducible")
    assert ss == [], calls(b, ss)


def test_masked_and_sorted():
    t = '  have s := "use 1, rw [x], first | apply y"\n  /- simp only [z]\n  rw [w] -/\n  exact h'
    assert HR.sites(body_of(t)) == []
    b = body_of("  use 1\n  simp only [x]\n  rw [h]\n  simp_rw [g]\n  repeat rw [k]")
    assert [s.op for s in HR.sites(b)] == ["repeatrw", "rw2rewrite", "rw2rewrite", "simponly2dsimp", "simprw2only"] + ["use2refine"] * 4


# ---- the greedy loop --------------------------------------------------------------------------------------------------------------------
class World:
    """Stub evaluate: fails when a `bad` substring is present; provisional score = base + the gains of the substrings present; on the full
    check Z drops by 50 when a `z_fail` substring is present."""
    def __init__(self, gains=None, bad=(), z_fail=(), base=60.0):
        self.gains, self.bad, self.z_fail, self.base, self.calls = gains or {}, bad, z_fail, base, []

    def evaluate(self, d, full):
        self.calls.append((full, d))
        if any(x in d for x in self.bad):
            return {"ok": False}
        p = self.base + sum(v for k, v in self.gains.items() if k in d)
        z = 100.0 - (50.0 if full and any(k in d for k in self.z_fail) else 0.0)
        return {"ok": True, "prov": round(p, 2), "Z": z, "score": round(p - (100 - z) / 3, 2), "tokens": 10, "heartbeats": 100}

    def run(self, d, **kw):
        return HR.rewrite_proof("t", d, evaluate_fn=self.evaluate, statement=STMT, **kw)


class Noisy(World):
    """World plus a deterministic heartbeat jitter of up to +-0.02 per compile (an unchanged proof re-measures up to +-0.03)."""
    def __init__(self, seed, **kw):
        super().__init__(**kw); self.seed = seed

    def evaluate(self, d, full):
        e = super().evaluate(d, full)
        if e.get("ok"):
            j = random.Random(zlib.crc32(d.encode()) * 1000 + self.seed * 7 + len(self.calls)).uniform(-0.02, 0.02)
            e["prov"] += j; e["score"] += j
        return e


def test_greedy_keeps_exactly_improving_sites():
    d = _decl("  rw [a]\n  rw [b]\n  rw [c]\n  exact h")
    w = World({"rewrite [a]": 0.3, "rewrite [c]": -0.1}, bad=("rewrite [b]",))
    r = w.run(d)
    assert r["status"] == "improved" and r["proof"] == _decl("  rewrite [a]\n  rw [b]\n  rw [c]\n  exact h"), r
    assert r["applied"] == {"rw2rewrite": 1} and r["gain"] == 0.3 and r["sites"] == {"rw2rewrite": 3}, r
    # base full + all-at-once (fails) + 3 per-site + final full = 6
    assert r["compiles"] == 6 == len(w.calls) and [c[0] for c in w.calls] == [True, False, False, False, False, True]
    # a neutral site (prov equal) is never kept, nor one below the noise margin
    for g in (0.0, 0.04):
        w = World({"rewrite [a]": g}); r = w.run(_decl("  rw [a]\n  exact h"))
        assert r["status"] == "no gain" and r["proof"] == _decl("  rw [a]\n  exact h") and r["after"] == r["before"], r


def test_noise_margin_and_stale_base():
    # 8 sites with no real effect under +-0.02 noise: never 'improved' (seeds 0..39)
    d = _decl("".join(f"  rw [h{k}]\n" for k in range(8)) + "  exact h")
    got = [Noisy(seed).run(d)["status"] for seed in range(40)]
    assert got.count("improved") == 0, got
    stored = {"ok": True, "score": 60.0, "Z": 100.0, "L": 40.0, "H": 40.0}
    # a stored best re-measured: one fresh primary compile, the gain judged against max(stored, fresh)
    w = World({"rewrite [a]": 0.3}); r = w.run(_decl("  rw [a]\n  exact h"), base=stored)
    assert r["status"] == "improved" and r["compiles"] == 3 and [c[0] for c in w.calls] == [False, False, True], r
    assert r["before"]["score"] == 60.0 and r["stored"]["score"] == 60.0 and r["gain"] == 0.3 and r["gain_vs_stored"] == 0.3, r
    # the stored score was a lucky draw (fresh 59.9): a +0.12 site beats the fresh baseline but not the stored score by the margin
    w = World({"rewrite [a]": 0.12}, base=59.9); r = w.run(_decl("  rw [a]\n  exact h"), base=stored)
    assert r["status"] == "no gain" and r["reason"] == "not strictly better on the full check", r
    # the stored best no longer compiles on the primary toolchain
    r = World(bad=("rw [a]",)).run(_decl("  rw [a]\n  exact h"), base=stored)
    assert r["status"] == "input does not compile" and r["compiles"] == 1, r


def test_all_at_once_and_variants():
    w = World({"dsimp only [x]": 0.2, "dsimp only [y]": 0.2})
    r = w.run(_decl("  simp only [x]\n  simp only [y] at h\n  exact h"))
    assert r["status"] == "improved" and r["applied"] == {"simponly2dsimp": 2}, r
    assert r["compiles"] == 5, r   # base, all-at-once, leave-one-out x 2, final
    # mixed signs: the all-at-once group pays (+0.3) but y alone costs -0.2 -> leave-one-out drops y
    w = World({"dsimp only [x]": 0.5, "dsimp only [y]": -0.2})
    r = w.run(_decl("  simp only [x]\n  simp only [y] at h\n  exact h"))
    assert r["status"] == "improved" and r["proof"] == _decl("  dsimp only [x]\n  simp only [y] at h\n  exact h") and r["gain"] == 0.5, r
    # rw2rewrite is monotone: no leave-one-out after its all-at-once group (base, all-at-once, final)
    w = World({"rewrite [a]": 0.1, "rewrite [b]": 0.1}); r = w.run(_decl("  rw [a]\n  rw [b]\n  exact h"))
    assert r["status"] == "improved" and r["applied"] == {"rw2rewrite": 2} and r["compiles"] == 3, r
    # use: the refine variant fails (the discharger closed the goal); the exists variant pays and is kept; nothing else on that span
    w = World({"exists 1": 0.4, "refine ⟨1, ?_⟩": 1.0}, bad=("refine ⟨1, ?_⟩",))
    r = w.run(_decl("  use 1\n  simp"))
    assert r["status"] == "improved" and r["proof"] == _decl("  exists 1\n  simp") and r["applied"] == {"use2refine": 1}, r
    assert r["sites"] == {"use2refine": 1} and r["candidates"] == 4, r
    # a complete argument list: refine / exists add a component and fail; exact ⟨args⟩ pays
    w = World({"exact ⟨1, 2⟩": 0.3}, bad=("refine", "exists", "rfl⟩"))
    r = w.run(_decl("  use 1, 2\n  simp"))
    assert r["status"] == "improved" and r["proof"] == _decl("  exact ⟨1, 2⟩\n  simp"), r
    # a token-costing site still has to raise the whole score (the stub's gain is the net of L and H)
    w = World({"with_reducible apply": -0.05}); assert w.run(_decl("  first | apply foo | exact h"))["status"] == "no gain"
    # --ops restricts the operators
    w = World({"rewrite [a]": 0.3, "dsimp only": 0.3})
    r = w.run(_decl("  rw [a]\n  simp only [b]"), ops=("simponly2dsimp",))
    assert r["applied"] == {"simponly2dsimp": 1} and r["sites"] == {"simponly2dsimp": 1}, r
    # late sites (the last rw of a combinator block) are tried after every other site
    w = World({"rewrite": 0.3, "dsimp only": 0.3})
    w.run(_decl("  all_goals\n    rw [e]\n  simp only [x]\n  exact h"))
    assert "dsimp only [x]" in w.calls[1][1] and "rewrite [e]" not in w.calls[1][1] and "rewrite [e]" in w.calls[2][1], w.calls


def test_final_all_pin_check():
    # the only kept operator breaks an older pin: Z drops on the full check -> no gain, input kept
    w = World({"dsimp only [x]": 0.5}, z_fail=("dsimp only",))
    r = w.run(_decl("  simp only [x]\n  exact h"))
    assert r["status"] == "no gain" and r["reason"] == "pins broke" and r["proof"] == _decl("  simp only [x]\n  exact h"), r
    assert r["after"] == r["before"] and r["tried"]["Z"] == 50.0
    # two operators kept, one breaks a pin: the fallback drops that operator's sites and keeps the other
    w = World({"dsimp only [x]": 0.5, "rewrite [a]": 0.3}, z_fail=("dsimp only",))
    r = w.run(_decl("  rw [a]\n  simp only [x]"))
    assert r["status"] == "improved" and r["proof"] == _decl("  rewrite [a]\n  simp only [x]") and r["applied"] == {"rw2rewrite": 1}, r
    # the fallback respects the deadline
    class Late(World):
        def __init__(self, *a, **k):
            super().__init__(*a, **k); self.t = 0.0

        def evaluate(self, d, full):
            if full and "dsimp" in d:
                self.t = 100.0
            return super().evaluate(d, full)
    w = Late({"dsimp only [x]": 0.5, "rewrite [a]": 0.3}, z_fail=("dsimp only",))
    r = w.run(_decl("  rw [a]\n  simp only [x]\n  exact h"), deadline=50.0, clock=lambda: w.t)
    assert r["status"] == "no gain" and r["reason"] == "pins broke" and r["stopped"] == "deadline" and len(w.calls) == 4, (r, len(w.calls))
    # the full check scores lower than the input (the provisional gain does not hold): no gain
    class W2(World):
        def evaluate(self, d, full):
            e = super().evaluate(d, full)
            if full and "rewrite" in d:
                e["score"] = 59.0
            return e
    r = W2({"rewrite [a]": 0.3}).run(_decl("  rw [a]\n  exact h"))
    assert r["status"] == "no gain" and r["reason"] == "not strictly better on the full check", r
    # a full check without Z is never taken as Z = 100
    class W3(World):
        def evaluate(self, d, full):
            e = super().evaluate(d, full)
            if full and "rewrite" in d:
                e.pop("Z")
            return e
    r = W3({"rewrite [a]": 0.3}).run(_decl("  rw [a]\n  exact h"))
    assert r["status"] == "no gain" and r["reason"] == "final check reported no Z", r
    assert World().run(_decl("  exact h.symm"))["status"] == "no sites"
    assert World().run(_decl("  exact h.symm"))["compiles"] == 0   # no sites: nothing compiled
    bad = HR.rewrite_proof("t", _decl("  rw [a]\n  exact h"), evaluate_fn=lambda d, f: {"ok": False}, statement=STMT)
    assert bad["status"] == "input does not compile"
    assert HR.rewrite_proof("t", "theorem other : True := by\n  rw [a]", evaluate_fn=lambda d, f: {}, statement=STMT)["status"] == "statement differs"


def test_max_compiles_and_deadline():
    d = _decl("  rw [a]\n  rw [b]\n  rw [c]\n  rw [d]\n  rw [e]\n  exact h")
    w = World({"rewrite [a]": 0.3, "rewrite [e]": 0.3}, bad=("rewrite [b]",))
    r = w.run(d, max_compiles=4, all_at_once=False)
    # base 1 + per-site until n = max - 1 (2 sites) + final 1 = 4; e is never tried
    assert r["stopped"] == "max-compiles" and r["compiles"] == 4 == len(w.calls) and r["applied"] == {"rw2rewrite": 1}, r
    assert "rw [e]" in r["proof"] and r["proof"].count("rewrite") == 1
    t = iter(range(100))
    w = World({"rewrite [a]": 0.3, "rewrite [e]": 0.3})
    r = w.run(d, deadline=2, clock=lambda: next(t), all_at_once=False)
    assert r["stopped"] == "deadline" and r["applied"] == {"rw2rewrite": 1} and len(w.calls) == 4, r   # base, a, b, final
    # the all-at-once compile is skipped when the budget cannot also cover the per-site pass
    w = World({"rewrite": 0.3}); r = w.run(d, max_compiles=6)
    assert [c[0] for c in w.calls][:2] == [True, False] and w.calls[1][1].count("rewrite") == 1, w.calls[1]


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

        def rw(name, proof, base=None, max_compiles=24, ops=HR.OPS, deadline=None, **kw):
            seen.append((name, base["score"], ops, kw.get("min_gain")))
            return {"status": "improved" if proof == "P1" else "no gain", "proof": proof + "!", "compiles": 3, "applied": {"rw2rewrite": 1}}
        chk = lambda w, name, proof: (banked.append((w.name, proof)), {"new_best": True, "score": 61.25})[1]
        c = HR.rewrite_work_root(wr, "x-p1", rewrite_fn=rw, check_fn=chk, ops=("rw2rewrite",))
        assert sorted(s[0] for s in seen) == ["Core.InitsUpdatesComm", "putnam_1964_b2"] and seen[0][2] == ("rw2rewrite",), seen
        assert seen[0][3] == HR.MIN_GAIN, seen
        assert banked == [("putnam_1964_b2", "P1!")] and c["problems"] == 2 and c["improved"] == 1 and c["banked"] == 1 and c["gain"] == 1.25, c
        assert [r["row"] for r in c["rows"]] == [1, 2] and not any("name" in r or "problem" in r for r in c["rows"])
        assert HR.rewrite_work_root(wr, "x", problems={"putnam_1964_a4"}, rewrite_fn=rw, check_fn=chk)["problems"] == 0
        c = HR.rewrite_work_root(wr, "x", deadline_s=-1, rewrite_fn=rw, check_fn=chk)
        assert c["skipped_deadline"] == 2 and c["problems"] == 0
        boom = lambda *a, **k: 1 / 0
        c = HR.rewrite_work_root(wr, "x", rewrite_fn=boom, check_fn=chk)
        assert c["errors"] == 2 and [r["status"] for r in c["rows"]] == ["error ZeroDivisionError"] * 2, c
        # the reported gain is against the best as stored when banking (a live line moved it during the pass), not the pre-pass snapshot
        def rw_live(name, proof, **kw):
            sp = wr / name / "state.json"; s = json.loads(sp.read_text()); s["best"]["score"] = 60.5; sp.write_text(json.dumps(s))
            return {"status": "improved" if proof == "P1" else "no gain", "proof": proof + "!", "compiles": 3, "applied": {}}
        c = HR.rewrite_work_root(wr, "x", problems={"putnam_1964_b2"}, rewrite_fn=rw_live, check_fn=chk)
        assert c["gain"] == 0.75, c
        # a banking failure is recorded by class, the pass goes on
        def chk_bad(w, name, proof):
            raise OSError(f"cannot open {w}/state.json")
        c = HR.rewrite_work_root(wr, "x", rewrite_fn=lambda name, proof, **kw: {"status": "improved", "proof": proof + "!", "compiles": 2},
                                 check_fn=chk_bad)
        assert c["bank_errors"] == 2 and c["problems"] == 2 and [r["status"] for r in c["rows"]] == ["bank error OSError"] * 2, c
        # run ids are validated; kinds are restricted
        for bad in ("../x", "a/b", "..", "", ".hidden"):
            try:
                HR.rewrite_work_root(wr, bad, rewrite_fn=rw, check_fn=chk); raise AssertionError(bad)
            except ValueError:
                pass
        try:
            HR.rewrite_work_root(wr, "x", rewrite_fn=rw, check_fn=chk, kind="api"); raise AssertionError("kind")
        except ValueError:
            pass


def test_default_bank_kind_and_lock_wait():
    with tempfile.TemporaryDirectory() as td:
        wr = _work_root(td); got = []
        guard = _IR.locked_check
        _IR.locked_check = lambda w, name, text, prov, vpath, lock_wait=1700.0: (got.append((prov, vpath, lock_wait)), {"new_best": True, "score": 61.0})[1]
        try:
            c = HR.rewrite_work_root(wr, "x-p1", problems={"putnam_1964_b2"}, deadline_s=1000.0, clock=lambda: 5.0, kind="api-dev-only",
                                     rewrite_fn=lambda name, proof, **kw: {"status": "improved", "proof": proof + "!", "compiles": 2})
        finally:
            _IR.locked_check = guard
        assert c["banked"] == 1 and len(got) == 1, (c, got)
        prov, vpath, lw = got[0]
        assert prov == {"kind": "api-dev-only", "model": "hb-rewrite@cpu", "run_id": "x-p1", "mode": "hb-rewrite"}, prov
        assert vpath == ROOT / "probe/runs/x-p1/verified.jsonl" and lw == 1000.0, (vpath, lw)


def _run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            HR.main(argv)
        except SystemExit:
            pass
    return out.getvalue(), err.getvalue()


def test_batch_stdout_has_no_problem_names():
    with tempfile.TemporaryDirectory() as td:
        wr = _work_root(td)
        real_rw, real_bank = HR.rewrite_proof, HR._bank
        seen = []
        HR.rewrite_proof = lambda name, proof, **kw: {"status": "improved", "proof": proof + "!", "compiles": 5, "applied": {"rw2rewrite": 2}}
        HR._bank = lambda w, name, proof, run_id, **kw: (seen.append(kw), {"new_best": True, "score": 61.0})[1]
        try:
            s, e = _run_main(["--work-root", str(wr), "--run-id", "x-p1", "--max-compiles", "8", "--ops", "rw2rewrite,use2refine"])
        finally:
            HR.rewrite_proof, HR._bank = real_rw, real_bank
        assert "row#1 improved" in s and "row#2 improved" in s and "2 banked" in s, s
        assert seen and all(k["kind"] == "closed-dev-only" and k["lock_wait"] >= 60.0 for k in seen), seen
        for name in NAMES:
            assert name not in s and name not in e, (name, s, e)


def test_batch_errors_have_no_problem_names():
    with tempfile.TemporaryDirectory() as td:
        wr = _work_root(td)
        real_rw, real_bank = HR.rewrite_proof, HR._bank

        def rw(name, proof, **kw):
            if proof == "P2":
                raise ValueError(f"boom in {name} ({proof})")
            return {"status": "improved", "proof": proof + "!", "compiles": 5, "applied": {"rw2rewrite": 1}}

        def bank(w, name, proof, run_id, **kw):
            raise OSError(f"cannot open {w}/state.json for {name}")
        HR.rewrite_proof, HR._bank = rw, bank
        try:
            s, e = _run_main(["--work-root", str(wr), "--run-id", "x-p1", "--kind", "api-dev-only"])
        finally:
            HR.rewrite_proof, HR._bank = real_rw, real_bank
        assert "bank error OSError" in s and "error ValueError" in s and "1 errors, 1 bank errors" in s, s
        assert "Traceback" not in e, e
        for name in NAMES:
            assert name not in s and name not in e, (name, s, e)
        # an invalid run id is refused before anything runs
        s, e = _run_main(["--work-root", str(wr), "--run-id", "../../x"])
        assert s == "" and "--run-id" in e, (s, e)


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
