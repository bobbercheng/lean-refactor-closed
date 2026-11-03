#!/usr/bin/env python3
"""Unit tests of harness/hb_polish.py (R8 heartbeat polish, driver v2 round 2), plain asserts, no Lean: string-level rewrite rules and the
strictly-better selection with stubbed compile / evaluate functions.
  sites          bare simp / simp_all / simpa / dsimp / grind found; `only`, `?`, config/options, comments, strings and the statement skipped
  probe          `?` after every head; positions in the probe map to Lean's (line, column) with the header offset
  suggestions    "Try this" lists read at each site, unioned over repeated invocations (`<;>`), other messages ignored
  rewrite        `<head> only [list]` with the rest of the call kept (` at h`, ` using e`); an empty list gives `<head> only`
  polish         all sites at once when that pays; otherwise site by site (simp_all only only where strictly better); a Z drop on the full
                 check rejects ("pins broke"); no sites / input not compiling / no gain; the grind-free retry probe; prune via simp_prune
  work_root      the ladder's post-pass: only stored bests, strictly-better results banked through the injected check, counts only
    python3 harness/test_hb_polish.py"""
from __future__ import annotations

import json, pathlib, sys, tempfile, traceback, types

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import hb_polish as HP  # noqa: E402

STMT = "theorem t (a b : Nat) (h : a = b) : b = a"


def _decl(body: str) -> str:
    return STMT + " := by\n" + body


def msg(probe: str, head_pos: int, text: str, head_lines: int = 0) -> dict:
    line = probe.count("\n", 0, head_pos) + 1 + head_lines
    return {"severity": "information", "data": text, "pos": {"line": line, "column": head_pos - (probe.rfind("\n", 0, head_pos) + 1)}}


def test_sites():
    d = _decl("  simp [foo] at h\n  simp only [bar]\n  simp? at h\n  -- simp_all here\n  simp_all\n  exact (by simpa using h)\n"
              "  dsimp (config := {}) \n  simp +arith\n  grind [→ baz]\n  have := \"simp\"\n  simp_arith\n  norm_num [simp_lemma]")
    s = HP.cert_sites(d, d.index(":= by"))
    assert [x["head"] for x in s] == ["simp", "simp_all", "simpa", "grind"], s
    first = s[0]
    assert d[first["start"]:first["args_end"]] == "simp [foo]" and d[first["head_end"]:first["head_end"] + 6] == " [foo]"
    assert d[s[3]["start"]:s[3]["args_end"]] == "grind [→ baz]"
    assert HP.cert_sites(_decl("  simp"), len(_decl("  simp")))  == []   # nothing before `start` (the statement) is a site
    # round-2 review (2026-10-12): rule builders inside aesop clauses are not tactics (their `?` form broke the whole probe)
    d = _decl("  aesop (add simp foo)\n  aesop (add norm simp [a, b]) (erase grind)\n  simp_all\n  exact (by simp)\n  simp (disch := simp) [bar] at h")
    s = HP.cert_sites(d, d.index(":= by"))
    assert [d[x["start"]:x["args_end"]] for x in s] == ["simp_all", "simp", "simp"], s   # the `(by simp)` term and the discharger stay sites
    assert "simp?" not in HP.probe_of(d, s)[0].split("simp_all?")[0]


def test_probe_and_suggestions():
    d = _decl("  simp [foo] at h\n  all_goals simp_all\n  grind")
    s = HP.cert_sites(d)
    probe, pos = HP.probe_of(d, s)
    assert probe == _decl("  simp? [foo] at h\n  all_goals simp_all?\n  grind?") and [probe[p:p + 4] for p in pos] == ["simp", "simp", "grin"]
    msgs = [msg(probe, pos[0], "Try this: simp only [foo, Nat.add_comm] at h", 5),
            msg(probe, pos[1], "Try this: simp_all only [h]", 5), msg(probe, pos[1], "Try this: simp_all only [Nat.succ_le,\n    h]", 5),
            msg(probe, pos[2], "Try this: grind only [= foo]", 5), msg(probe, pos[2], "unused variable `x`", 5),
            msg(probe, pos[0] + 1, "Try this: simp only [WRONG]", 5)]
    sg = HP.suggestions(probe, pos, msgs, 5)
    assert sg == {0: ["foo", "Nat.add_comm"], 1: ["h", "Nat.succ_le"], 2: ["= foo"]}, sg
    assert HP.suggestions(probe, pos, msgs, 0) == {}   # the header offset matters


def test_rewrite():
    d = _decl("  simp [foo] at h\n  simpa [x] using h\n  simp_all\n  dsimp\n  grind")
    s = HP.cert_sites(d)
    sg = {0: ["foo", "bar"], 1: ["y"], 2: ["h"], 3: [], 4: ["= foo"]}
    assert HP.rewrite(d, s, sg, range(5)) == _decl("  simp only [foo, bar] at h\n  simpa only [y] using h\n  simp_all only [h]\n  dsimp only\n  grind only [= foo]")
    assert HP.rewrite(d, s, sg, [2]) == _decl("  simp [foo] at h\n  simpa [x] using h\n  simp_all only [h]\n  dsimp\n  grind")


class World:
    """Stub compile / evaluate: the probe compile answers "Try this" at each site; evaluate scores by a table of substrings."""
    def __init__(self, suggest: dict, scores: dict, base=60.0, z=100.0, z_fail=(), probe_ok=lambda p: True):
        self.suggest, self.scores, self.base, self.z, self.z_fail, self.probe_ok, self.calls = suggest, scores, base, z, z_fail, probe_ok, []

    def compile(self, probe):
        self.calls.append(("compile", probe))
        if not self.probe_ok(probe):
            return types.SimpleNamespace(ok=False, messages=[])
        s = HP.cert_sites(probe.replace("?", ""))   # the sites of the decl this probe came from
        sub = [x for x in s if probe.count(x["head"] + "?")]
        _p, pos = HP.probe_of(probe.replace("?", ""), sub)
        return types.SimpleNamespace(ok=True, messages=[msg(probe, pos[k], f"Try this: {x['head']} only [{self.suggest[x['head']]}]")
                                                        for k, x in enumerate(sub) if x["head"] in self.suggest])

    def evaluate(self, d, full):
        self.calls.append(("eval", full, d))
        sc = self.base + sum(v for k, v in self.scores.items() if k in d)
        z = self.z - (50.0 if full and any(k in d for k in self.z_fail) else 0.0)
        return {"ok": True, "score": round(sc - (100 - z) / 3, 2), "Z": z, "prov": round(sc, 2)}

    def run(self, d, **kw):
        return HP.polish("t", d, compile_fn=self.compile, evaluate_fn=self.evaluate, head_lines=0, statement=STMT, **kw)


def test_polish_all_at_once():
    w = World({"simp": "foo", "simp_all": "h"}, {"simp only [foo]": 0.5, "simp_all only [h]": 0.4})
    r = w.run(_decl("  simp at h\n  simp_all"))
    assert r["status"] == "improved" and r["proof"] == _decl("  simp only [foo] at h\n  simp_all only [h]") and r["gain"] == 0.9, r
    assert r["applied"] == {"simp only": 1, "simp_all only": 1} and sum(1 for c in w.calls if c[0] == "compile") == 1


def test_polish_greedy_simp_all_only_where_better():
    # simp_all only costs more than it saves here: all-at-once loses, site by site keeps the simp one only
    w = World({"simp": "foo", "simp_all": "h, a, b, c"}, {"simp only [foo]": 0.5, "simp_all only [h, a, b, c]": -0.9})
    r = w.run(_decl("  simp at h\n  simp_all"))
    assert r["status"] == "improved" and r["proof"] == _decl("  simp only [foo] at h\n  simp_all") and r["applied"] == {"simp only": 1}, r


def test_polish_rejects_z_drop_and_reports():
    w = World({"grind": "= foo"}, {"grind only": 1.0}, z_fail=("grind only",))   # `grind only` missing on an older pin: Z drops on the full check
    r = w.run(_decl("  grind"))
    assert r["status"] == "pins broke" and r["proof"] == _decl("  grind") and r["after"] == r["before"], r
    assert w.run(_decl("  exact h.symm"))["status"] == "no sites"
    assert World({}, {}).run(_decl("  simp"))["status"] == "no gain"   # no suggestion came back
    bad = HP.polish("t", _decl("  simp"), compile_fn=lambda p: None, evaluate_fn=lambda d, f: {"ok": False}, head_lines=0, statement=STMT)
    assert bad["status"] == "input does not compile"
    assert HP.polish("t", "theorem other : True := by\n  simp", compile_fn=lambda p: None, evaluate_fn=lambda d, f: {}, head_lines=0,
                     statement=STMT)["status"] == "statement differs"


def test_polish_grind_free_retry_and_base():
    # the first probe (with grind?) fails, as on a toolchain without `grind?`: the second leaves grind out
    w = World({"simp": "foo"}, {"simp only [foo]": 0.7}, probe_ok=lambda p: "grind?" not in p)
    base = {"ok": True, "score": 60.0, "Z": 100.0, "L": 40.0, "H": 40.0}
    r = w.run(_decl("  simp at h\n  grind"), base=base)
    assert r["status"] == "improved" and r["proof"] == _decl("  simp only [foo] at h\n  grind") and r["before"]["score"] == 60.0, r
    assert sum(1 for c in w.calls if c[0] == "compile") == 2 and not any(c[0] == "eval" and c[2] == _decl("  simp at h\n  grind") for c in w.calls)
    assert HP.prov(base) == 60.0 and HP.prov({"score": 50.0, "Z": 50.0}) == 66.67 and HP.prov({"prov": 61.0}) == 61.0


def test_polish_prune():
    import harness.leantools as LT
    d = _decl("  simp only [a, b, c] at h")
    real = LT.simp_prune
    LT.simp_prune = lambda decl, fn, hl: (decl.replace("[a, b, c]", "[a]"), 2)
    try:
        w = World({}, {"[a]": 0.3})
        r = w.run(d)
        assert r["status"] == "improved" and r["proof"] == _decl("  simp only [a] at h") and r["applied"] == {"pruned lemmas": 2}, r
        assert World({}, {"[a]": -0.3}).run(d)["status"] == "no gain"
    finally:
        LT.simp_prune = real


def test_work_root_post_pass():
    with tempfile.TemporaryDirectory() as td:
        wr = pathlib.Path(td)
        for name, best in (("putnam_1964_b2", {"score": 60.0, "proof": "P1", "Z": 100.0}), ("putnam_1964_a4", {"score": 33.33, "proof": None}),
                           ("not_a_row", {"score": 70.0, "proof": "P3"})):
            (wr / name).mkdir(); (wr / name / "state.json").write_text(json.dumps({"problem": name, "best": best}))
        seen, banked = [], []
        pol = lambda name, proof, base=None, max_compiles=12: (seen.append((name, base)), {"status": "improved", "proof": proof + "!", "compiles": 3})[1]
        chk = lambda w, name, proof: (banked.append((w.name, proof)), {"new_best": True, "score": 61.25})[1]
        c = HP.polish_work_root(wr, "x-p1", polish_fn=pol, check_fn=chk)
        assert seen == [("putnam_1964_b2", {"ok": True, "score": 60.0, "Z": 100.0, "L": None, "H": None, "tokens": None, "heartbeats": None})], seen
        assert banked == [("putnam_1964_b2", "P1!")] and c == {"problems": 1, "improved": 1, "banked": 1, "gain": 1.25, "compiles": 3, "skipped_deadline": 0}, c
        c = HP.polish_work_root(wr, "x-p1", problems={"putnam_1964_a4"}, polish_fn=pol, check_fn=chk)
        assert c["problems"] == 0
        c = HP.polish_work_root(wr, "x-p1", deadline_s=-1, polish_fn=pol, check_fn=chk)
        assert c["skipped_deadline"] == 1 and c["problems"] == 0


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
