#!/usr/bin/env python3
"""Generate harness/tools/tables/projections.json (T1 projection spelling table) from the Lean environment.

Rule: run projections_query.lean (next to this script) with `lake env lean` in one prepared Mathlib environment; it prints every structure
declared under Init or Mathlib in the import closure of its four imports (basic bundled structures: logic/equiv, order homs, group homs,
finset defs), with its direct fields in declaration order (`x.i` is the i-th of them, 1-based), the parent structure of each subobject
field, the class and Prop flags, and for every field name the number of projection functions and of other declarations in that slice whose
name ends with it. Nothing is typed by hand: the table is exactly that output. Run it only inside a memory-capped unit:
    systemd-run --user --wait --pipe --unit lra-b62t-<id> -p MemoryMax=16G -p OOMPolicy=continue -p RuntimeMaxSec=1800 \
        --working-directory=<worktree> -E PATH -E HOME python3 harness/tools/tables/gen_projections.py [--env envs/mathlib-v4.27.0]"""
from __future__ import annotations

import argparse, json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
QUERY = HERE / "projections_query.lean"
OUT = HERE / "projections.json"
RULE = ("every structure declared in a module under Init or Mathlib in the import closure of the query's imports, its direct fields in "
        "declaration order (Lean.getStructureFields; `x.i` = field i, 1-based), the parent of each subobject field, class/Prop flags; per "
        "field name the count of projection functions and of other declarations in that slice whose last name component it is")


def parse(text: str) -> tuple[dict, dict]:
    structs, names = {}, {}
    for line in text.splitlines():
        parts = line.split("\t")
        if parts[0] == "S" and len(parts) == 5:
            _, name, cls, prop, fields = parts
            fl, parents = [], {}
            for f in (fields.split(",") if fields else []):
                fname, _, parent = f.partition(":")
                fl.append(fname)
                if parent:
                    parents[fname] = parent
            structs[name] = {"fields": fl, "parents": parents, "class": cls == "true", "prop": prop == "true"}
        elif parts[0] == "N" and len(parts) == 4:
            names[parts[1]] = {"proj": int(parts[2]), "other": int(parts[3])}
    return structs, names


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="envs/mathlib-v4.27.0", help="prepared Mathlib environment (relative to the worktree)")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    if not os.environ.get("INVOCATION_ID"):
        sys.exit("gen_projections: run inside a memory-capped systemd unit (see the docstring)")
    wd = (ROOT / a.env).resolve()
    pin = (wd / "lean-toolchain").read_text().strip()
    env = dict(os.environ, PATH=f"{Path.home() / '.elan/bin'}:{os.environ.get('PATH', '')}")
    t0 = time.time()
    p = subprocess.run(["lake", "env", "lean", "-M16000", str(QUERY)], cwd=wd, env=env, capture_output=True, text=True, timeout=1500)
    if p.returncode != 0:
        sys.stderr.write(p.stdout[-4000:] + p.stderr[-4000:])
        return 1
    structs, names = parse(p.stdout)
    if not structs or not names:
        sys.stderr.write("gen_projections: empty query output\n")
        return 1
    imports = [l.split()[1] for l in QUERY.read_text().splitlines() if l.startswith("import ")]
    table = {"rule": RULE, "query": (f"python3 {Path(__file__).resolve().relative_to(ROOT)} --env {a.env}: lake env lean "
                                     f"{QUERY.relative_to(ROOT)} ({pin}); imports {', '.join(imports)}"),
             "generator": str(Path(__file__).resolve().relative_to(ROOT)), "pin": pin,
             "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seconds": round(time.time() - t0, 1),
             "structures": structs, "names": names}
    Path(a.out).write_text(json.dumps(table, ensure_ascii=False, indent=0, sort_keys=True) + "\n")
    print(f"{len(structs)} structures, {len(names)} field names -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
