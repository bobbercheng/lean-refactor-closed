#!/usr/bin/env python3
"""b66 closed package (retro A1 item 3; 2026-10-27): the Lean environments a benchmark rows file needs, one entry per (project, pinned
toolchain), in the format of infra/vast/harness_envs.json (the open track's infra/open_package/envs_from_rows.py, plus LeanPool and the
clone mode): repository key and URL, the pinned commit, the rows' modules (to `lake build`), whether the project fetches Mathlib's prebuilt
cache, whether the upstream clone is blobless. PutnamBench rows compile in a plain Mathlib checkout at the pinned commit (envs/mathlib-<v>,
no modules). A source this file does not know needs --url SOURCE=URL [--no-cache SOURCE] [--blobless SOURCE] (and a scorer.compile
PROJECT_DIRS entry: harness/final_rows.py check refuses an unknown source first).

    python3 infra/closed_package/envs_from_rows.py --rows ROWS.jsonl --out envs/final_envs.json [--url NAME=URL ...]
    infra/closed_package/install_envs.sh reads that file (default envs/final_envs.json) and builds what is missing."""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.final_rows import load, pins, env_key  # noqa: E402

URLS = {"strata": "https://github.com/strata-org/Strata", "physlib": "https://github.com/leanprover-community/physlib",
        "cslib": "https://github.com/leanprover/cslib", "arklib": "https://github.com/Verified-zkEVM/ArkLib",
        "putnambench": "https://github.com/leanprover-community/mathlib4",
        "leanpool": "https://github.com/LeanPool/lean-pool"}     # the sixth library (organizer 2026-10-24; docs/leanpool_env.md)
NO_CACHE = {"strata"}                 # projects without a Mathlib dependency
REPO = {"putnambench": "mathlib4"}    # the upstream clone's key (envs/mathlib4; the others envs/<repo>.git-main)
BLOBLESS = {"putnambench", "leanpool"}   # big histories: blobless clones (mathlib4 as setup_mathlib.sh, LeanPool as leanpool_vm.sh)


def envs(rows: list[dict], urls: dict, no_cache: set, blobless: set) -> dict:
    out: dict = {}
    for r in rows:
        src = r["source"]
        if src not in urls:
            raise SystemExit(f"source {src!r}: no repository URL; pass --url {src}=<git url>")
        mod = None if src == "putnambench" else r["file_path"].removesuffix(".lean").replace("/", ".")
        for ver, commit in pins(r):
            key = env_key(src, ver)
            e = out.setdefault(key, {"repo": REPO.get(src, src), "url": urls[src], "commit": commit, "modules": [],
                                     "cache": src not in no_cache, "blobless": src in blobless})
            if e["commit"] != commit:
                raise SystemExit(f"{key}: two commits ({e['commit'][:12]} and {commit[:12]}) for one toolchain")
            if mod and mod not in e["modules"]:
                e["modules"].append(mod)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", required=True); ap.add_argument("--out", default=str(ROOT / "envs/final_envs.json"))
    ap.add_argument("--url", action="append", default=[], metavar="SOURCE=URL")
    ap.add_argument("--no-cache", action="append", default=[]); ap.add_argument("--blobless", action="append", default=[])
    a = ap.parse_args()
    urls = dict(URLS, **dict(x.split("=", 1) for x in a.url))
    d = envs(load(a.rows), urls, NO_CACHE | set(a.no_cache), BLOBLESS | set(a.blobless))
    Path(a.out).write_text(json.dumps(d, indent=1) + "\n")
    print(f"{len(d)} environment(s), {len({v['repo'] for v in d.values()})} repositories -> {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
