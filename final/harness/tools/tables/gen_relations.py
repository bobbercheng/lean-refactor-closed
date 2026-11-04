#!/usr/bin/env python3
"""Writes harness/tools/tables/relations.json (the relation table: strengthenings R' ⇒ R, congruences of a relation over constructors,
one-sided rules, reflexivity, least/greatest elements, binder bridges) and instances.json (the instance index: named instances per class,
for the classes the library's own declarations take as instance-implicit binders) from relations_query.lean, run once per library
environment with that library's root module imported (Init, Std, Batteries, Mathlib and the library are in the environment; strata has no
Mathlib). Nothing in the tables is typed by hand: every line is the query's shape test on a theorem's TYPE (relations_query.lean, header).

relations.json
  pins            per environment: directory, toolchain, root module, theorems scanned, seconds
  strengthen      R (conclusion relation) -> [{"thm", "from": R', "dir": imp|flip|iff_mp|iff_mpr, "envs": [..], "root"}]
  congruence      R -> [{"thm", "ctor", "arity", "positions": [..], "same": bool, "envs", "root"}]
  one_sided       R -> [{"thm", "ctor", "hyps": 0|1, "side": L|R, "envs", "root"}]
  refl            R -> [{"thm", "envs", "root"}]
  least           R -> [{"thm", "ctor", "side", "envs", "root"}]
  binder_bridge   [{"thm", "kind": forall|exists, "lhs", "rhs", "envs", "root"}]
instances.json
  classes         class -> [{"name", "explicit", "inst", "implicit", "carrier", "needs" (classes of its instance binders), "envs", "root"}] (explicit = 0 entries are the ones a
                  `letI : C .. := name` can take without arguments; carrier "var" = an instance over any type, else the type former's head)
Excluded at generation time (plan §1.1 K0, r7 review 2026-10-25): every record whose `thm` / `name` is a declaration name listed in the
JSONL files of $LRA_TABLE_EXCLUDE (os.pathsep-separated, relative to the repository root; default data/benchmark_warmup.jsonl when present):
a benchmark row's own theorem never enters a table. The names are read at run time and written nowhere (the tables carry the count only).
    python3 harness/tools/tables/gen_relations.py --filter-only   # applies the exclusion to the stored tables (no Lean, no unit needed)
Run it inside a memory-capped unit (it runs Lean with the whole library imported, one environment at a time):
    systemd-run --user --wait --pipe -u lra-f-T10-tables-$RANDOM -p MemoryMax=48G -p OOMPolicy=continue -p RuntimeMaxSec=7200 \\
      -p WorkingDirectory=<worktree> -E PATH -E HOME python3 harness/tools/tables/gen_relations.py"""
from __future__ import annotations

import argparse, datetime, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
QUERY = HERE / "relations_query.lean"
OUT_REL = HERE / "relations.json"
OUT_INST = HERE / "instances.json"
TOOLCHAINS = Path.home() / ".elan" / "toolchains"
# one environment per library (the primary pin of most of its rows); the root module imported in each
ENVS = {"envs/strata-v4.26.0": "Strata", "envs/cslib-v4.32.0": "Cslib", "envs/arklib-v4.31.0": "ArkLib", "envs/physlib-v4.32.0": "Physlib"}
WALL_S = 3600
RULE = ("relations_query.lean (its header is the rule) run with the library's root module imported, one environment per library; a line "
        "is a shape test on a theorem's type after telescoping its binders (hyps = Prop-typed binders, rel e = (R, a, b) for e = R .. a b): "
        "S = concl R a b with exactly one hyp R' a b (or R' b a: flip), or R' a b ↔ R a b; C = concl R (c s..) (c t..) with every "
        "position shared or related by a hyp, all hyps used; O = one side a constructor application containing the other side or its hyp "
        "partner; F = R a a without hyps; L = R u b / R a u with u a data-free constant application; B = ∀/∃ ↔ ∀/∃; I = registered "
        "instances of the classes the library's own declarations take as instance-implicit binders. Deprecated and internal names skipped.")


EXCLUDE_ENV = "LRA_TABLE_EXCLUDE"
EXCLUDE_DEFAULT = ("data/benchmark_warmup.jsonl",)
EXCLUDE_RULE = ("records whose thm / name is a declaration name listed in $LRA_TABLE_EXCLUDE (default data/benchmark_warmup.jsonl) are "
                "dropped at generation time: a benchmark row's own theorem never enters a table (plan §1.1 K0)")


def excluded_names() -> set:
    """The declaration names no table may carry: the "name" field of every JSONL record in the files of $LRA_TABLE_EXCLUDE (default
    data/benchmark_warmup.jsonl; a missing file contributes nothing). Read at run time only; never written anywhere."""
    spec = os.environ.get(EXCLUDE_ENV)
    files = [f for f in spec.split(os.pathsep) if f] if spec else list(EXCLUDE_DEFAULT)
    out = set()
    for f in files:
        p = Path(f) if Path(f).is_absolute() else ROOT / f
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    n = json.loads(line).get("name")
                except (ValueError, AttributeError):
                    continue
                if isinstance(n, str) and n:
                    out.add(n)
    return out


def drop_excluded(rel: dict, inst: dict, names: set) -> int:
    """Removes, in place, every relation record whose "thm" and every instance record whose "name" is in `names` (a relation / class
    left without records is dropped); returns the number of records removed."""
    n = 0
    for sec, v in list(rel.items()):
        if isinstance(v, list):
            keep = [r for r in v if not (isinstance(r, dict) and r.get("thm") in names)]
            n += len(v) - len(keep); rel[sec] = keep
        elif isinstance(v, dict):
            for k, lst in list(v.items()):
                if isinstance(lst, list):
                    keep = [r for r in lst if not (isinstance(r, dict) and r.get("thm") in names)]
                    n += len(lst) - len(keep)
                    if keep:
                        v[k] = keep
                    else:
                        del v[k]
    cls = inst.get("classes") or {}
    for k, lst in list(cls.items()):
        keep = [r for r in lst if not (isinstance(r, dict) and r.get("name") in names)]
        n += len(lst) - len(keep)
        if keep:
            cls[k] = keep
        else:
            del cls[k]
    return n


def filter_stored(out_rel: Path, out_inst: Path, copy_to: str) -> int:
    """--filter-only: the exclusion applied to the stored tables (their generated_at / rule / query / pins kept; "exclude" added)."""
    meta = ("rule", "query", "generated_at", "generator", "pins", "exclude")
    R = json.loads(out_rel.read_text()); I = json.loads(out_inst.read_text())
    rel = {k: v for k, v in R.items() if k not in meta}; inst = {k: v for k, v in I.items() if k not in meta}
    n = drop_excluded(rel, inst, excluded_names())
    for path, T, body in ((out_rel, R, rel), (out_inst, I, inst)):
        head = {k: T[k] for k in meta if k in T}
        head["exclude"] = {"rule": EXCLUDE_RULE}
        path.write_text(json.dumps(dict(head, **body), ensure_ascii=False, indent=1) + "\n")
    if copy_to:
        Path(copy_to).mkdir(parents=True, exist_ok=True)
        shutil.copy(out_rel, Path(copy_to) / "relations.json")
        shutil.copy(out_inst, Path(copy_to) / "instances.json")
    print(f"filter-only: {n} record(s) removed from {out_rel.name} / {out_inst.name}", file=sys.stderr)
    return 0


def runtime(envdir: str) -> dict:
    wd = (ROOT / envdir).resolve()
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
    return {"lean": lean, "pin": pin, "env": {"HOME": os.environ.get("HOME", ""), "PATH": "", "LEAN_PATH": os.pathsep.join(libs),
                                              "LEAN_SYSROOT": str(lean.parent.parent)}}


def import_lines(envdir: str, root: str) -> str:
    """`import Root`, or, when the root module itself is not built (ArkLib: no ArkLib.olean), one import per built module under it."""
    lib = (ROOT / envdir / ".lake/build/lib/lean").resolve()
    if (lib / f"{root}.olean").is_file():
        return f"import {root}"
    mods = sorted(".".join(p.relative_to(lib).with_suffix("").parts) for p in (lib / root).rglob("*.olean"))
    if not mods:
        raise FileNotFoundError(f"no built modules under {lib / root}")
    return "\n".join(f"import {m}" for m in mods)


def parse(text: str) -> dict:
    out = {"S": [], "C": [], "O": [], "F": [], "L": [], "B": [], "I": [], "N": None, "K": None, "M": None}
    for line in text.splitlines():
        p = line.rstrip("\n").split("\t")
        k = p[0]
        if k in ("N", "K") and len(p) == 2:
            out[k] = int(p[1])
        elif k == "M" and len(p) == 2:
            out["M"] = p[1]
        elif k in out and k not in ("N", "K", "M"):
            out[k].append(p[1:])
    if out["N"] is None:
        raise ValueError("incomplete query output (no N line)")
    return out


def merge(per: dict) -> tuple[dict, dict]:
    def add(d: dict, key, rec: dict, env: str):
        slot = d.setdefault(key, {})
        k = json.dumps(rec, sort_keys=True)
        e = slot.setdefault(k, dict(rec, envs=[]))
        e["envs"].append(env)

    S: dict = {}; C: dict = {}; O: dict = {}; F: dict = {}; L: dict = {}; B: dict = {}; I: dict = {}
    for env, q in per.items():
        for thm, r1, r2, d, rt in q["S"]:
            add(S, r2, {"thm": thm, "from": r1, "dir": d, "root": rt}, env)
        for thm, R, c, ar, pos, same, rt in q["C"]:
            add(C, R, {"thm": thm, "ctor": c, "arity": int(ar), "positions": pos.split(","), "same": same == "true", "root": rt}, env)
        for thm, R, c, nh, side, rt in q["O"]:
            add(O, R, {"thm": thm, "ctor": c, "hyps": int(nh), "side": side, "root": rt}, env)
        for thm, R, rt in q["F"]:
            add(F, R, {"thm": thm, "root": rt}, env)
        for thm, R, c, side, rt in q["L"]:
            add(L, R, {"thm": thm, "ctor": c, "side": side, "root": rt}, env)
        for thm, kind, l, r, rt in q["B"]:
            add(B, "all", {"thm": thm, "kind": kind, "lhs": l, "rhs": r, "root": rt}, env)
        for name, cls, e, i, m, carrier, needs, rt in q["I"]:
            add(I, cls, {"name": name, "explicit": int(e), "inst": int(i), "implicit": int(m), "carrier": carrier,
                         "needs": [x for x in needs.split(",") if x], "root": rt}, env)

    def flat(d: dict) -> dict:
        return {k: sorted(v.values(), key=lambda r: (r.get("thm") or r.get("name"), r.get("dir", ""), r.get("ctor", "")))
                for k, v in sorted(d.items())}
    rel = {"strengthen": flat(S), "congruence": flat(C), "one_sided": flat(O), "refl": flat(F), "least": flat(L),
           "binder_bridge": flat(B).get("all", [])}
    return rel, {"classes": flat(I)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--envs", default=",".join(f"{k}={v}" for k, v in ENVS.items()), help="envdir=RootModule,...")
    ap.add_argument("--out-rel", default=str(OUT_REL))
    ap.add_argument("--out-inst", default=str(OUT_INST))
    ap.add_argument("--copy-to", default=str(ROOT / "probe/b63/dxr"), help="directory receiving copies of both tables ('' for none)")
    ap.add_argument("--raw-dir", default="", help="keep the raw query output per environment here")
    ap.add_argument("--filter-only", action="store_true", help="apply the generation-time exclusion to the stored tables (no Lean)")
    a = ap.parse_args(argv)
    if a.filter_only:
        return filter_stored(Path(a.out_rel), Path(a.out_inst), a.copy_to)
    if not os.environ.get("INVOCATION_ID"):
        sys.exit("gen_relations: run inside a memory-capped systemd unit (see the docstring)")
    per, meta = {}, []
    src = QUERY.read_text()
    for spec in a.envs.split(","):
        envdir, root = spec.split("=")
        rt = runtime(envdir); t0 = time.time()
        imports = import_lines(envdir, root)
        with tempfile.TemporaryDirectory(prefix="lra-relq-") as td:
            q = Path(td) / "relations_query.lean"
            q.write_text(src.replace("import LRA_IMPORT_ROOT", imports).replace("LRA_IMPORT_ROOT", root))
            p = subprocess.run([str(rt["lean"]), str(q)], cwd=td, env=rt["env"], capture_output=True, text=True, timeout=WALL_S)
        if a.raw_dir:
            Path(a.raw_dir).mkdir(parents=True, exist_ok=True)
            (Path(a.raw_dir) / (Path(envdir).name + ".tsv")).write_text(p.stdout)
            (Path(a.raw_dir) / (Path(envdir).name + ".err")).write_text(p.stderr)
        if p.returncode != 0:
            sys.stderr.write(f"{envdir}: query failed (rc {p.returncode})\n" + (p.stdout[-1500:] + p.stderr)[-3000:])
            return 1
        try:
            per[envdir] = parse(p.stdout)
        except ValueError as e:
            sys.stderr.write(f"{envdir}: {e}\n" + (p.stdout[-1500:] + p.stderr)[-3000:])
            return 1
        q = per[envdir]
        meta.append({"env": envdir, "pin": rt["pin"], "root": root, "theorems": q["N"], "lib_classes": q["K"],
                     "lines": {k: len(q[k]) for k in ("S", "C", "O", "F", "L", "B", "I")}, "seconds": round(time.time() - t0, 1)})
        print(f"{envdir} ({rt['pin']}): {meta[-1]}", file=sys.stderr)
    rel, inst = merge(per)
    dropped = drop_excluded(rel, inst, excluded_names())
    print(f"excluded {dropped} record(s) ({EXCLUDE_ENV})", file=sys.stderr)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    head = {"rule": RULE, "query": f"python3 harness/tools/tables/gen_relations.py --envs {a.envs}: lean relations_query.lean per environment",
            "generated_at": now, "generator": "harness/tools/tables/gen_relations.py", "pins": meta, "exclude": {"rule": EXCLUDE_RULE}}
    Path(a.out_rel).write_text(json.dumps(dict(head, **rel), ensure_ascii=False, indent=1) + "\n")
    Path(a.out_inst).write_text(json.dumps(dict(head, **inst), ensure_ascii=False, indent=1) + "\n")
    if a.copy_to:
        Path(a.copy_to).mkdir(parents=True, exist_ok=True)
        shutil.copy(a.out_rel, Path(a.copy_to) / "relations.json")
        shutil.copy(a.out_inst, Path(a.copy_to) / "instances.json")
    print(f"wrote {a.out_rel}: " + ", ".join(f"{k} {sum(len(v) for v in rel[k].values()) if isinstance(rel[k], dict) else len(rel[k])}"
                                            for k in rel), file=sys.stderr)
    print(f"wrote {a.out_inst}: {len(inst['classes'])} classes, {sum(len(v) for v in inst['classes'].values())} instances", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
