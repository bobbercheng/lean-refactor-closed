#!/usr/bin/env python3
"""Writes harness/tools/tables/bundled_homs.json (the structure-specific variants of the generic `map_*` lemmas that harness/hb_rewrite.py's
specialize operator proposes) from bundled_homs_query.lean, run with `import Mathlib` on the oldest and the newest Mathlib pin prepared
here (the mathlib scope of gen_closers.py). Nothing in the table is typed by hand: the structures, the generic lemmas and the pairs are the
query's output; the order of a lemma's variants is a count over the same environments.

Table fields:
  pins        the environments the query ran in (directory, toolchain) and per pin the counts of generics, structures and pairs
  specialize  generic lemma g -> the variants S.g that specialize g on EVERY pin (a variant only one pin has would fail to compile on the
              other), ordered by the size of S's namespace (declarations directly in it) summed over the pins, largest first, ties by
              name: the most used bundled homs first
  structures  S -> {"size": {pin: namespace size}} for every structure that appears in specialize
Run it inside a memory-capped unit (it runs Lean with all of Mathlib imported, one pin at a time):
    systemd-run --user --wait --pipe --unit lra-b62t-<id> -p MemoryMax=16G -p OOMPolicy=continue -p RuntimeMaxSec=1800 \\
      --working-directory=<worktree> -E PATH -E HOME python3 harness/tools/tables/gen_bundled_homs.py"""
from __future__ import annotations

import argparse, datetime, json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
QUERY = HERE / "bundled_homs_query.lean"
OUT = HERE / "bundled_homs.json"
TOOLCHAINS = Path.home() / ".elan" / "toolchains"
PINS = ("envs/mathlib-v4.25.0", "envs/cslib-v4.33.0-rc2")   # gen_closers.py ENVS mathlib-oldest / mathlib-newest
WALL_S = 1500
RULE = ("With `import Mathlib` on the oldest and the newest Mathlib pin (bundled_homs_query.lean), over declarations of modules under "
        "Init or Mathlib: a bundled hom is a structure (not a class) whose flattened fields include one named `map_<x>'`; a generic is a "
        "root-namespace theorem named `map_*`, not deprecated; S.g is a variant of g when the theorem S.g exists, is not deprecated, and "
        "Lean's `apply` of g closes S.g's conclusion with S.g's binders as hypotheses (g's conclusion unifies with it, instances "
        "synthesized). specialize keeps the variants that hold on every pin, ordered by S's namespace size (declarations directly in it) "
        "summed over the pins, largest first, ties by name. harness/hb_rewrite.py specialize replaces an occurrence of g by each of the "
        "first SPEC_CAP variants.")


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


def parse(text: str) -> dict:
    """The query's output -> {"generics": n, "sizes": {S: n}, "pairs": {(S, g): bool}}."""
    n = None; sizes: dict = {}; pairs: dict = {}
    for line in text.splitlines():
        p = line.split("\t")
        if p[0] == "R" and len(p) == 2:
            n = int(p[1])
        elif p[0] == "S" and len(p) == 3:
            sizes[p[1]] = int(p[2])
        elif p[0] == "P" and len(p) == 4:
            pairs[(p[1], p[2])] = p[3] == "true"
    if n is None or not sizes:
        raise ValueError("incomplete query output")
    return {"generics": n, "sizes": sizes, "pairs": pairs}


def build(per: dict) -> tuple[dict, dict]:
    """(specialize, structures) from the per-pin outputs: pairs true on every pin, ordered by summed namespace size."""
    pins = list(per)
    ok = set.intersection(*({k for k, v in per[p]["pairs"].items() if v} for p in pins))
    size = {s: sum(per[p]["sizes"].get(s, 0) for p in pins) for s, _ in ok}
    spec: dict = {}
    for s, g in sorted(ok, key=lambda sg: (sg[1], -size[sg[0]], sg[0])):
        spec.setdefault(g, []).append(f"{s}.{g}")
    structs = {s: {"size": {p: per[p]["sizes"].get(s, 0) for p in pins}} for s in sorted({s for s, _ in ok})}
    return dict(sorted(spec.items())), structs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pins", default=",".join(PINS), help="prepared environments with Mathlib built (relative to the worktree)")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    if not os.environ.get("INVOCATION_ID"):
        sys.exit("gen_bundled_homs: run inside a memory-capped systemd unit (see the docstring)")
    per, meta = {}, []
    for envdir in a.pins.split(","):
        rt = runtime(envdir); t0 = time.time()
        p = subprocess.run([str(rt["lean"]), str(QUERY)], cwd=str(HERE), env=rt["env"], capture_output=True, text=True, timeout=WALL_S)
        if p.returncode != 0:
            sys.stderr.write(f"{envdir}: query failed\n" + (p.stdout + p.stderr)[-3000:])
            return 1
        per[envdir] = parse(p.stdout)
        n_true = sum(per[envdir]["pairs"].values())
        meta.append({"env": envdir, "pin": rt["pin"], "generics": per[envdir]["generics"], "structures": len(per[envdir]["sizes"]),
                     "pairs": len(per[envdir]["pairs"]), "specializations": n_true, "seconds": round(time.time() - t0, 1)})
        print(f"{envdir} ({rt['pin']}): {meta[-1]}", file=sys.stderr)
    spec, structs = build(per)
    table = {
        "rule": RULE,
        "query": f"python3 harness/tools/tables/gen_bundled_homs.py --pins {a.pins}: lean harness/tools/tables/bundled_homs_query.lean "
                 "(import Mathlib) per pin",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "harness/tools/tables/gen_bundled_homs.py",
        "pins": meta,
        "specialize": spec,
        "structures": structs,
    }
    Path(a.out).write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {a.out}: {len(spec)} generics, {sum(len(v) for v in spec.values())} variants, {len(structs)} structures", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
