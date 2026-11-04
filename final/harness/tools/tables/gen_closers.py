#!/usr/bin/env python3
"""Writes harness/tools/tables/closers.json, the closer table of T3 (harness/tools/t3_reclose.py). Nothing in the table is typed by hand.

Rule (also stored in the table):
  phase A  every leading token of the environment's `tactic` syntax category (closers_enum.lean: the category's first-token table, complete)
           that Lean's own category parser accepts ALONE, i.e. a tactic usable with no argument; then kept only when it is identifier-shaped
           ([A-Za-z_][A-Za-z0-9_'!]*), has no `?` (suggestion / library-search forms are out of scope in R1), passes the scorer's forbidden
           filter (scorer/forbidden.py) and its syntax kind is not under a `Test` namespace (Lean server test fixtures).
  phase B  each kept token is run as `example <template> := by (<token>)` on every goal of TEMPLATES below (synthetic goals written for this
           table: True, reflexivity, decidable arithmetic, a hypothesis in context, And/Or/Iff/Exists introduction from hypotheses, linear
           arithmetic, a rewrite by a hypothesis, two size-scaling pairs), one declaration per line, each under
           `set_option maxHeartbeats HB_LIMIT in`, `set_option linter.all false in` and the scorer's own heartbeat meter (scorer/compile.MEASURE_ELAB, `arena_measure`), with
           an empty PATH (a tactic that needs an external program fails) and -DmaxErrors=1000000 (Lean's default stops a file after 100
           errors), in chunks with a wall timeout (a chunk that times out is split
           until the culprit token is alone; it is recorded as a timeout).
  outcome  closed = no error, no warning, no message other than the meter's (a sorry warning is a warning, so closing through sorry is not
           closed); progress = the only message is Lean's `unsolved goals` error and its goal text differs from the no-op reference
           (`skip`) on the same template; runaway = an error naming the heartbeat limit or the recursion limit; unmeasured = the meter
           never reported for the line (Lean stopped before it; the chunk is split until the token that stops it is alone); fail =
           anything else.
  scope    core = `import Lean` on the oldest and the newest installed core toolchain; mathlib = `import Mathlib` on the oldest and the newest
           Mathlib build available here. A token's outcome in a scope is the INTERSECTION over that scope's pins (closed on every pin), so
           a closer that only works on a newer pin is not listed (it would cost Z on older pins).
  closers  tokens that close >= 1 template in the scope; progress makers: tokens that make progress on >= 1 template (the left side of
           `t1 <;> t2` in T3's depth-2 grammar).
  pairs    (phase C) for every progress maker t1 and every cheap closer t2 != t1 of a scope, `example <template> := by (t1 <;> t2)` on
           the templates where t1 made progress and neither part closes alone, on every pin of the scope; a pair is kept when it closes
           >= 1 such template on every pin ("adds"). T3's depth-2 `<;>` grammar uses only kept pairs.
  cost     per scope, from the measured heartbeats (the meter's unit, thousands of raw heartbeats): expensive when the median over the
           templates it closed exceeds COST_FACTOR x the median of all closers' medians, or the median over the templates it did NOT
           close exceeds COST_FACTOR x the closers' median of that (it searches long before giving up), or its max reaches half of
           HB_LIMIT, or it ran away / timed out / stopped Lean (memory) on any template, or it is size-sensitive (closes the small member of a scaling pair but not the large one, or
           uses more than SCALE_FACTOR x the heartbeats on the large one); cheap otherwise.

Run it inside a memory-capped unit (it compiles):
    export XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
    systemd-run --user --wait --pipe --unit lra-b62t-t3gen -p MemoryMax=16G -p OOMPolicy=continue -p RuntimeMaxSec=3600 \\
      --working-directory=<worktree> -E PATH -E HOME python3 harness/tools/tables/gen_closers.py
Options: --envs a,b (subset of ENV names), --jobs N (concurrent Lean processes in the unit, default 2), --work DIR (scratch, default a
temporary directory), --out PATH (default harness/tools/tables/closers.json), --raw PATH (also write every per-pin outcome), --from-raw a,b (aggregate
the --raw files of separate runs, e.g. one 16G unit per pin, and measure nothing)."""
from __future__ import annotations

import argparse, concurrent.futures as cf, datetime, json, os, re, statistics, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from scorer.compile import MEASURE_ELAB  # noqa: E402
from scorer.forbidden import check_forbidden  # noqa: E402

ENUM = HERE / "closers_enum.lean"
OUT = HERE / "closers.json"
TOOLCHAINS = Path.home() / ".elan" / "toolchains"
HB_LIMIT = 20000          # maxHeartbeats per template run (thousands of raw heartbeats, Lean's option unit)
COST_FACTOR = 4.0
SCALE_FACTOR = 10.0
CHUNK = 12                # tokens per Lean file in phase B
PAIR_LINES = 400          # template runs per Lean file in phase C
NOOP = "skip"             # the reference no-op for the progress test (core Lean's identity tactic)
# per template run: the heartbeat limit, linters off (their warnings are not the tactic's), the scorer's meter on the counting thread
PREFIX = f"set_option maxHeartbeats {HB_LIMIT} in set_option linter.all false in set_option Elab.async false in arena_measure"

# (id, binders and goal) - synthetic goals written for this table; generic facts over Prop / Nat / Int / Bool / List / Fin only.
TEMPLATES = [
    ("true", ": True"),
    ("refl", "(a : Nat) : a = a"),
    ("hyp", "(p : Prop) (hp : p) : p"),
    ("and_intro", "(p q : Prop) (hp : p) (hq : q) : p ∧ q"),
    ("or_left", "(p q : Prop) (hp : p) : p ∨ q"),
    ("or_right", "(p q : Prop) (hq : q) : p ∨ q"),
    ("iff_intro", "(p q : Prop) (h1 : p → q) (h2 : q → p) : p ↔ q"),
    ("exists_intro", "(P : Nat → Prop) (a : Nat) (h : P a) : ∃ x, P x"),
    ("nat_add", ": 2 + 2 = 4"),
    ("nat_lt", ": (3 : Nat) < 5"),
    ("nat_mod", ": (10 : Nat) % 3 = 1"),
    ("int_sub", ": (2 : Int) - 5 = -3"),
    ("lin_nat", "(a b : Nat) (h : a < b) : a + 1 ≤ b"),
    ("lin_int", "(a b : Int) (h : a ≤ b) : a - 1 < b"),
    ("add_comm", "(a b : Nat) : a + b = b + a"),
    ("append_nil", "(xs : List Nat) : xs ++ [] = xs"),
    ("false_elim", "(p : Prop) (h : False) : p"),
    ("contra", "(p : Prop) (h : p) (hn : ¬p) : (1 : Nat) = 2"),
    ("subst_val", "(a : Nat) (h : a = 3) : a + 1 = 4"),
    ("congr_arg", "(f : Nat → Nat) (a b : Nat) (h : a = b) : f a = f b"),
    ("modus_ponens", "(p q : Prop) (hpq : p → q) (hp : p) : q"),
    ("and_proj", "(p q r : Prop) (h : p ∧ q ∧ r) : r"),
    ("antisymm", "(a b : Nat) (h₁ : a ≤ b) (h₂ : b ≤ a) : a = b"),
    ("mul_zero", "(n : Nat) : n * 0 = 0"),
    ("and_swap", "(p q : Prop) (h : p ∧ q) : q ∧ p"),
    ("zero_lt_next", "(n : Nat) : 0 < n + 1"),
    ("bool_and", "(b : Bool) : (b && true) = b"),
    ("list_mem", "(x : Nat) (h : x ∈ [1, 2, 3]) : 1 ≤ x"),
    ("imp_intro", "(p q : Prop) (hq : q) : p → q"),
    ("rw_hyp", "(f : Nat → Nat) (h : ∀ x, f x = x) : f 2 = 2"),
    ("eq_trans", "(a b c : Nat) (h1 : a = b) (h2 : b = c) : a = c"),
    ("ne_self", "(s : Nat) (h : s ≠ s) : False"),
    ("fin_small", ": ∀ a b : Fin 3, a + b = b + a"),
    ("fin_large", ": ∀ a b : Fin 16, a + b = b + a"),
    ("bound_small", ": ∀ n, n < 8 → n * n ≠ 2"),
    ("bound_large", ": ∀ n, n < 200 → n * n ≠ 2"),
]
SCALING = [("fin_small", "fin_large"), ("bound_small", "bound_large")]

# name -> (imports line, how to find the environment): core pins use the toolchain alone, Mathlib pins a prepared environment directory
ENVS = {
    "core-oldest": {"scope": "core", "imports": "import Lean", "toolchain": "oldest"},
    "core-newest": {"scope": "core", "imports": "import Lean", "toolchain": "newest"},
    "mathlib-oldest": {"scope": "mathlib", "imports": "import Mathlib", "envdir": "envs/mathlib-v4.25.0"},
    "mathlib-newest": {"scope": "mathlib", "imports": "import Mathlib", "envdir": "envs/cslib-v4.33.0-rc2"},
}
TOKEN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_'!]*$")


def _ver_key(name: str):
    v = name.split("---", 1)[-1].lstrip("v")
    nums = [int(x) for x in re.findall(r"\d+", v.split("-")[0])]
    return (nums, 0 if "-rc" in v else 1, v)


def _core_toolchains() -> list[Path]:
    ts = [p for p in TOOLCHAINS.glob("leanprover--lean4---v*") if (p / "bin/lean").is_file()]
    return sorted(ts, key=lambda p: _ver_key(p.name))


def runtime(spec: dict) -> dict:
    """{"lean": binary, "env": process environment, "pin": toolchain string} for an ENVS entry."""
    if "toolchain" in spec:
        ts = _core_toolchains()
        if not ts:
            raise FileNotFoundError("no installed core toolchain under ~/.elan/toolchains")
        tc = ts[0] if spec["toolchain"] == "oldest" else ts[-1]
        return {"lean": tc / "bin/lean", "env": {"HOME": os.environ.get("HOME", ""), "PATH": ""},
                "pin": tc.name.replace("---", ":").replace("--", "/"), "where": "toolchain"}
    wd = (ROOT / spec["envdir"]).resolve()
    pin = (wd / "lean-toolchain").read_text().strip()
    lean = TOOLCHAINS / pin.replace("/", "--").replace(":", "---") / "bin/lean"
    if not lean.is_file():
        raise FileNotFoundError(f"toolchain {pin} is not installed")
    libs = [wd / ".lake/build/lib/lean"]
    man = json.loads((wd / "lake-manifest.json").read_text()) if (wd / "lake-manifest.json").exists() else {}
    pk = wd / man.get("packagesDir", ".lake/packages")
    if pk.is_dir():
        libs += [p / ".lake/build/lib/lean" for p in sorted(pk.iterdir())]
    libs = [str(p.resolve()) for p in libs if p.is_dir()]
    env = {"HOME": os.environ.get("HOME", ""), "PATH": "", "LEAN_PATH": os.pathsep.join(libs),
           "LEAN_SYSROOT": str(lean.parent.parent)}
    return {"lean": lean, "env": env, "pin": pin, "where": spec["envdir"]}


def _run(rt: dict, path: Path, timeout: int) -> tuple[list[dict], str, bool]:
    try:
        p = subprocess.run([str(rt["lean"]), "--json", "-M8000", "-DmaxErrors=1000000", path.name], cwd=str(path.parent), env=rt["env"],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return [], "", True
    msgs = []
    for line in p.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                msgs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return msgs, p.stdout + p.stderr, False


def phase_a(rt: dict, imports: str, work: Path) -> dict:
    f = work / f"enum_{abs(hash((str(rt['lean']), imports))) % 10**8}.lean"
    f.write_text(imports + "\n" + ENUM.read_text())
    msgs, raw, to = _run(rt, f, 900)
    if to:
        raise RuntimeError("phase A timed out")
    text = "\n".join(str(m.get("data", "")) for m in msgs) + "\n" + raw
    errs = [m for m in msgs if m.get("severity") == "error"]
    if errs:
        raise RuntimeError(f"phase A failed: {errs[0].get('data')}"[:500])
    toks = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0] == "T3TOK":
            toks[parts[1]] = parts[2]
    return toks


def keep_token(tok: str, kind: str) -> str | None:
    """None when the token is kept for phase B, else the exclusion reason."""
    if not TOKEN_RE.match(tok):
        return "not identifier-shaped" if "?" not in tok else "suggestion form (?)"
    if check_forbidden(tok):
        return "forbidden by the scorer"
    if ".Test." in kind or kind.startswith("Test."):
        return "Lean server test fixture"
    return None


def _file_text(imports: str, toks: list[str], tids: dict | None = None) -> tuple[str, dict]:
    """The phase-B/C file and {line number: (tactic text, template id)}; tids restricts a text to some templates."""
    head = imports + "\n\n" + MEASURE_ELAB
    lines, where = head.rstrip("\n").split("\n"), {}
    for tok in toks:
        for tid, goal in TEMPLATES:
            if tids is not None and tid not in tids.get(tok, ()):
                continue
            lines.append(f"{PREFIX} example {goal} := by ({tok})")   # parenthesised: an optional argument cannot run onto the next line
            where[len(lines)] = (tok, tid)
    return "\n".join(lines) + "\n", where


def _classify(msgs: list[dict]) -> dict:
    hb, errs, other = None, [], []
    for m in msgs:
        sev, data = m.get("severity"), str(m.get("data", ""))
        mm = re.search(r"ARENA_HB (\d+)", data) if sev == "information" else None
        if mm:
            hb = int(mm.group(1))
        elif sev == "error":
            errs.append(data)
        else:
            other.append(data)
    if hb is None and not errs and not other:
        return {"o": "unmeasured", "hb": None}   # the meter never reported: the file was cut short (see phase_b_chunk)
    if not errs and not other:
        return {"o": "closed", "hb": hb}
    if any(re.search(r"maxHeartbeats|heartbeats|maximum recursion depth|deterministic", e) for e in errs):
        return {"o": "runaway", "hb": hb}
    if len(errs) == 1 and not other and errs[0].startswith("unsolved goals"):
        return {"o": "open", "hb": hb, "goal": errs[0]}
    return {"o": "fail", "hb": hb}


def phase_b_chunk(rt: dict, imports: str, toks: list[str], work: Path, log, tids: dict | None = None) -> dict:
    """{tactic text: {template: outcome}}; a timed-out chunk is split until the culprit is alone."""
    text, where = _file_text(imports, toks, tids)
    f = work / f"meas_{abs(hash((str(rt['lean']), imports, tuple(toks)))) % 10**10}.lean"
    f.write_text(text)
    timeout = int(120 + 1.5 * len(where))
    t0 = time.time()
    msgs, raw, to = _run(rt, f, timeout)
    f.unlink(missing_ok=True)
    if to:
        if len(toks) == 1:
            log(f"  timeout: {toks[0]} ({timeout} s)")
            return {toks[0]: {tid: {"o": "timeout", "hb": None} for tid, _ in TEMPLATES if tids is None or tid in tids.get(toks[0], ())}}
        mid = len(toks) // 2
        log(f"  chunk of {len(toks)} timed out; splitting")
        out = phase_b_chunk(rt, imports, toks[:mid], work, log, tids)
        out.update(phase_b_chunk(rt, imports, toks[mid:], work, log, tids))
        return out
    by_line: dict = {}
    for m in msgs:
        ln = (m.get("pos") or {}).get("line")
        if ln in where:
            by_line.setdefault(ln, []).append(m)
    head_errs = [m for m in msgs if m.get("severity") == "error" and (m.get("pos") or {}).get("line") not in where]
    if head_errs:
        raise RuntimeError(f"phase B header failed: {head_errs[0].get('data')}"[:500])
    out: dict = {}
    for ln, (tok, tid) in where.items():
        out.setdefault(tok, {})[tid] = _classify(by_line.get(ln, []))
    cut = [t for t in toks if any(r["o"] == "unmeasured" for r in out[t].values())]
    if cut and len(toks) > 1:   # a line without the meter's message: Lean stopped early; isolate the token that stops it
        log(f"  chunk {toks[0]}..{toks[-1]}: {len(cut)} token(s) unmeasured (Lean stopped early: {raw[-200:]!r}); splitting")
        mid = len(toks) // 2
        out = phase_b_chunk(rt, imports, toks[:mid], work, log, tids)
        out.update(phase_b_chunk(rt, imports, toks[mid:], work, log, tids))
        return out
    log(f"  chunk {toks[0]}..{toks[-1]} ({len(toks)}) in {time.time() - t0:.0f} s" + (f"; {toks[0]} stops Lean early" if cut else ""))
    return out


def measure_env(name: str, jobs: int, work: Path, log) -> dict:
    spec = ENVS[name]
    rt = runtime(spec)
    log(f"{name}: {rt['pin']} ({rt['where']})")
    toks = phase_a(rt, spec["imports"], work)
    kept, excluded = [], {}
    for t, k in sorted(toks.items()):
        why = keep_token(t, k)
        if why:
            excluded[t] = why
        else:
            kept.append(t)
    log(f"  phase A: {len(toks)} tokens parse alone, {len(kept)} kept")
    ref = phase_b_chunk(rt, spec["imports"], [NOOP], work, log)[NOOP]
    chunks = [kept[i:i + CHUNK] for i in range(0, len(kept), CHUNK)]
    res: dict = {}
    with cf.ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        for part in ex.map(lambda c: phase_b_chunk(rt, spec["imports"], c, work, log), chunks):
            res.update(part)
    for tok, per in res.items():   # progress: unsolved goals that differ from the no-op reference
        for tid, r in per.items():
            if r["o"] == "open":
                r["o"] = "progress" if r.get("goal") != ref.get(tid, {}).get("goal") else "noop"
            r.pop("goal", None)
    return {"name": name, "scope": spec["scope"], "pin": rt["pin"], "where": rt["where"], "imports": spec["imports"],
            "parsed_alone": len(toks), "excluded": excluded, "outcomes": res}


def pair_plan(scope_tab: dict) -> tuple[list[str], dict]:
    """Phase C tests for one scope of an aggregated table: `t1 <;> t2` for every progress maker t1 (a tactic with a progress template)
    and every CHEAP closer t2 != t1, on the templates where t1 made progress and neither t1 nor t2 closes alone."""
    closers = {c["tactic"]: c for c in scope_tab.get("closers", [])}
    makers = [c for c in scope_tab.get("closers", []) + scope_tab.get("progress", []) if c.get("progress")]
    keys, tids = [], {}
    for m in sorted(makers, key=lambda c: c["tactic"]):
        for t2 in sorted(t for t, c in closers.items() if c["cost"] == "cheap"):
            if t2 == m["tactic"]:
                continue
            ts = [t for t in m["progress"] if t not in closers[t2]["closes"] and t not in m.get("closes", [])]
            if ts:
                k = f"{m['tactic']} <;> {t2}"
                keys.append(k)
                tids[k] = ts
    return keys, tids


def measure_pairs(name: str, table: dict, jobs: int, work: Path, log) -> dict:
    spec = ENVS[name]
    rt = runtime(spec)
    keys, tids = pair_plan(table["scopes"].get(spec["scope"], {}))
    log(f"{name}: phase C, {len(keys)} pairs, {sum(len(v) for v in tids.values())} runs on {rt['pin']}")
    chunks, cur, n = [], [], 0
    for k in keys:   # about PAIR_LINES template runs per Lean file
        cur.append(k)
        n += len(tids[k])
        if n >= PAIR_LINES:
            chunks.append(cur)
            cur, n = [], 0
    if cur:
        chunks.append(cur)
    res: dict = {}
    with cf.ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        for part in ex.map(lambda c: phase_b_chunk(rt, spec["imports"], c, work, log, tids), chunks):
            res.update(part)
    for per in res.values():
        for r in per.values():
            r.pop("goal", None)
    return {"name": name, "scope": spec["scope"], "pin": rt["pin"], "pairs": res}


def aggregate_pairs(scopes: dict, per_env_pairs: list[dict]) -> None:
    """Adds scopes[scope]["pairs"]: the measured pairs that close, on every pin of the scope, >= 1 template neither part closes alone."""
    for scope, tab in scopes.items():
        envs = [e for e in per_env_pairs if e["scope"] == scope]
        if not envs:
            continue
        keys = set.intersection(*(set(e["pairs"]) for e in envs))
        out = []
        for k in sorted(keys):
            adds = sorted({tid for tid in envs[0]["pairs"][k] if all(e["pairs"][k].get(tid, {}).get("o") == "closed" for e in envs)})
            if adds:
                hbs = [max(e["pairs"][k][tid]["hb"] or 0 for e in envs) for tid in adds]
                t1, t2 = k.split(" <;> ", 1)
                out.append({"t1": t1, "t2": t2, "adds": adds, "hb_median": statistics.median(hbs)})
        out.sort(key=lambda x: (-len(x["adds"]), x["t1"], x["t2"]))
        tab["pairs"] = out
        tab["pair_pins"] = [e["pin"] for e in envs]
        tab["pairs_tested"] = len(keys)


def aggregate(per_env: list[dict]) -> dict:
    scopes: dict = {}
    for scope in sorted({e["scope"] for e in per_env}):
        envs = [e for e in per_env if e["scope"] == scope]
        toks = set.intersection(*(set(e["outcomes"]) for e in envs)) if envs else set()
        closers, progress = [], []
        for tok in sorted(toks):
            closed = [tid for tid, _ in TEMPLATES if all(e["outcomes"][tok].get(tid, {}).get("o") == "closed" for e in envs)]
            prog = [tid for tid, _ in TEMPLATES if all(e["outcomes"][tok].get(tid, {}).get("o") in ("progress", "closed") for e in envs)
                    and any(e["outcomes"][tok].get(tid, {}).get("o") == "progress" for e in envs)]
            run_away = sorted({tid for e in envs for tid, r in e["outcomes"][tok].items() if r["o"] in ("runaway", "timeout", "unmeasured")})
            hbs = [max(e["outcomes"][tok][tid]["hb"] or 0 for e in envs) for tid in closed]
            fails = [max(e["outcomes"][tok][tid]["hb"] or 0 for e in envs) for tid, _ in TEMPLATES
                     if tid not in closed and all(e["outcomes"][tok].get(tid, {}).get("hb") is not None for e in envs)]
            size = []
            for small, large in SCALING:
                if small in closed:
                    if large not in closed:
                        size.append(small)
                    else:
                        hs = max(e["outcomes"][tok][small]["hb"] or 0 for e in envs)
                        hl = max(e["outcomes"][tok][large]["hb"] or 0 for e in envs)
                        if hl > SCALE_FACTOR * max(hs, 1):
                            size.append(small)
            entry = {"tactic": tok, "closes": closed, "progress": prog, "runaway_on": run_away, "size_sensitive": bool(size),
                     "hb_median": statistics.median(hbs) if hbs else None, "hb_max": max(hbs) if hbs else None,
                     "hb_fail_median": statistics.median(fails) if fails else None}
            if closed:
                closers.append(entry)
            elif prog:
                progress.append(entry)
        meds = [c["hb_median"] for c in closers if c["hb_median"] is not None]
        base = statistics.median(meds) if meds else 0
        fmeds = [c["hb_fail_median"] for c in closers if c["hb_fail_median"] is not None]
        fbase = statistics.median(fmeds) if fmeds else 0
        for c in closers + progress:
            why = []
            if c["hb_median"] is not None and c["hb_median"] > COST_FACTOR * max(base, 1):
                why.append(f"median {c['hb_median']} > {COST_FACTOR} x {base}")
            if c["hb_fail_median"] is not None and c["hb_fail_median"] > COST_FACTOR * max(fbase, 1):
                why.append(f"failing median {c['hb_fail_median']} > {COST_FACTOR} x {fbase} (searches before giving up)")
            if c["hb_max"] is not None and c["hb_max"] >= HB_LIMIT / 2:
                why.append(f"max {c['hb_max']} >= {HB_LIMIT // 2}")
            if c["runaway_on"]:
                why.append("ran away / timed out on " + ",".join(c["runaway_on"]))
            if c["size_sensitive"]:
                why.append("size-sensitive on a scaling pair")
            c["cost"] = "expensive" if why else "cheap"
            c["cost_why"] = "; ".join(why)
        closers.sort(key=lambda c: (-len(c["closes"]), c["cost"] != "cheap", c["tactic"]))
        progress.sort(key=lambda c: (-len(c["progress"]), c["cost"] != "cheap", c["tactic"]))
        scopes[scope] = {"pins": [e["pin"] for e in envs], "median_of_medians": base, "failing_median_of_medians": fbase,
                         "closers": closers, "progress": progress}
    return scopes


RULE = __doc__.split("Rule (also stored in the table):", 1)[1].split("Run it inside", 1)[0].strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--envs", default=",".join(ENVS))
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--work")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--raw")
    ap.add_argument("--from-raw", help="comma-separated --raw files of earlier runs: aggregate them, measure nothing")
    ap.add_argument("--pairs", action="store_true", help="phase C only: measure the pairs of --table on --envs, write --raw")
    ap.add_argument("--table", default=str(OUT), help="the aggregated table phase C reads")
    ap.add_argument("--from-raw-pairs", help="comma-separated phase-C --raw files to aggregate into the table's pairs")
    a = ap.parse_args(argv)
    log = lambda m: print(m, flush=True)  # noqa: E731
    tmp = None if (a.work or a.from_raw) else tempfile.TemporaryDirectory(prefix="t3gen_")
    if a.pairs:
        work = Path(a.work or tmp.name)
        work.mkdir(parents=True, exist_ok=True)
        tab = json.loads(Path(a.table).read_text())
        res = [measure_pairs(n, tab, a.jobs, work, log) for n in a.envs.split(",") if n]
        Path(a.raw or (work / "pairs.raw.json")).write_text(json.dumps(res, ensure_ascii=False))
        if tmp:
            tmp.cleanup()
        return 0
    if a.from_raw:
        per_env = [e for f in a.from_raw.split(",") if f for e in json.loads(Path(f).read_text())]
    else:
        work = Path(a.work or tmp.name)
        work.mkdir(parents=True, exist_ok=True)
        per_env = [measure_env(n, a.jobs, work, log) for n in [n for n in a.envs.split(",") if n]]
    names = [e["name"] for e in per_env]
    if a.raw:
        Path(a.raw).write_text(json.dumps(per_env, ensure_ascii=False))
    table = {
        "rule": RULE,
        "query": ("python3 harness/tools/tables/gen_closers.py --envs " + ",".join(names) + "   (phase A: harness/tools/tables/closers_enum.lean "
                  "with the scope's import line; phase B: one `" + PREFIX + " example <template> := by (<token>)` per line; run inside a "
                  "16G systemd unit)"),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "settings": {"hb_limit": HB_LIMIT, "cost_factor": COST_FACTOR, "scale_factor": SCALE_FACTOR, "noop_reference": NOOP},
        "templates": [{"id": t, "goal": g} for t, g in TEMPLATES],
        "envs": [{k: e[k] for k in ("name", "scope", "pin", "where", "imports", "parsed_alone")} | {"excluded": e["excluded"]}
                 for e in per_env],
        "scopes": aggregate(per_env),
    }
    if a.from_raw_pairs:
        aggregate_pairs(table["scopes"], [e for f in a.from_raw_pairs.split(",") if f for e in json.loads(Path(f).read_text())])
        table["query"] += ("; phase C: python3 harness/tools/tables/gen_closers.py --pairs --envs <pin> --raw <file> per pin, then "
                           "--from-raw <phase B raws> --from-raw-pairs <phase C raws>")
    Path(a.out).write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n")
    for s, v in table["scopes"].items():
        log(f"{s}: {len(v['closers'])} closers, {len(v['progress'])} progress makers on {v['pins']}"
            + (f"; {len(v['pairs'])} of {v['pairs_tested']} pairs add a template" if "pairs" in v else ""))
    if tmp:
        tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
