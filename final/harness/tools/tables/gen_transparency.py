#!/usr/bin/env python3
"""Writes harness/tools/tables/transparency_wrappers.json (the transparency wrappers the sweep's addwr operator may insert) from
transparency_query.lean, run on every installed core toolchain (~/.elan/toolchains/leanprover--lean4---v*). Nothing in the table is typed
by hand: the wrapper tokens are the leading tokens of Lean's `tactic` syntax category whose run changes the transparency setting a wrapped
tactic sees, measured by the query's probe; the order of the settings is Lean's own TransparencyMode.lt.

Table fields:
  per_toolchain  for each toolchain: the number of tactic tokens enumerated, the default setting (the bare probe's), the constructors of
                 Lean.Meta.TransparencyMode in declaration order, and every wrapper with the setting it runs its tactics under
  wrappers       every wrapper seen on any toolchain: its setting and the toolchains that have it
  common         the wrappers present, with the same setting, on every toolchain the query ran on (a wrapper only some pins have would
                 fail to compile on the others), sorted from the least to the greatest setting by TransparencyMode.lt (the order must
                 agree on every toolchain); harness/sweep.py's addwr inserts common[0], the least setting every toolchain has
Run it inside a memory-capped unit (it runs Lean):
    systemd-run --user --wait --pipe --unit lra-b62t-<id> -p MemoryMax=16G -p OOMPolicy=continue -p RuntimeMaxSec=1800 \\
      --working-directory=<worktree> -E PATH -E HOME python3 harness/tools/tables/gen_transparency.py"""
from __future__ import annotations

import datetime, json, os, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
QUERY = HERE / "transparency_query.lean"
OUT = HERE / "transparency_wrappers.json"
TOOLCHAINS = Path.home() / ".elan" / "toolchains"
WALL_S = 300
RULE = ("Every leading token of Lean core's `tactic` syntax category (Init + Lean; complete, nothing filtered by name) is run as "
        "`<token> <probe>` on the goal True, where the probe (transparency_query.lean) fails with the transparency setting it runs under "
        "(Lean.Meta.getTransparency); a token whose run reports a setting other than the bare probe's (the default) is a transparency "
        "wrapper, recorded with that setting, on every installed core toolchain. common = the wrappers present with the same setting on "
        "every toolchain, sorted from the least to the greatest setting by Lean's own TransparencyMode.lt (consistent on every "
        "toolchain). harness/sweep.py addwr inserts common[0]: the least transparency setting that every toolchain's tactic framework "
        "offers as a wrapper.")


def _ver_key(name: str):
    v = name.split("---", 1)[-1].lstrip("v")
    nums = [int(x) for x in re.findall(r"\d+", v.split("-")[0])]
    return (nums, 0 if "-rc" in v else 1, v)


def toolchains() -> list[Path]:
    ts = [p for p in TOOLCHAINS.glob("leanprover--lean4---v*") if (p / "bin/lean").is_file()]
    return sorted(ts, key=lambda p: _ver_key(p.name))


def parse(text: str) -> dict:
    """The query's output lines -> {"tokens", "default", "modes", "lt", "wrappers"} (settings by constructor short name)."""
    modes: dict = {}; lt: dict = {}; wr: dict = {}; n = None; b = None
    for line in text.splitlines():
        p = line.split("\t")
        if p[0] == "N" and len(p) == 2:
            n = int(p[1])
        elif p[0] == "M" and len(p) == 3:
            modes[int(p[1])] = p[2].rsplit(".", 1)[-1]
        elif p[0] == "L" and len(p) == 4:
            lt[(int(p[1]), int(p[2]))] = p[3] == "true"
        elif p[0] == "B" and len(p) == 2:
            b = int(p[1])
        elif p[0] == "W" and len(p) == 3:
            wr[p[1]] = int(p[2])
    if n is None or b is None or not modes or len(lt) != len(modes) ** 2:
        raise ValueError("incomplete query output")
    name = lambda i: modes[i]  # noqa: E731
    return {"tokens": n, "default": name(b), "modes": [modes[i] for i in sorted(modes)],
            "lt": sorted([name(a), name(c)] for (a, c), v in lt.items() if v), "wrappers": {t: name(i) for t, i in sorted(wr.items())}}


def common(per: dict) -> list[dict]:
    """Wrappers with the same setting on every toolchain, least setting first (Lean's lt; it must agree on every toolchain)."""
    tcs = list(per)
    toks = set.intersection(*(set(per[t]["wrappers"]) for t in tcs)) if tcs else set()
    same = sorted(t for t in toks if len({per[tc]["wrappers"][t] for tc in tcs}) == 1)
    mode = {t: per[tcs[0]]["wrappers"][t] for t in same}
    below = {}
    for t in same:
        counts = {sum(1 for u in same if [mode[u], mode[t]] in per[tc]["lt"]) for tc in tcs}
        if len(counts) != 1:
            raise ValueError(f"the order of {mode[t]} differs between toolchains")
        below[t] = counts.pop()
    if len(set(below.values())) != len(below):
        raise ValueError("two common wrappers share a setting rank")
    return [{"token": t, "mode": mode[t], "rank": below[t]} for t in sorted(same, key=lambda t: below[t])]


def main() -> int:
    if not os.environ.get("INVOCATION_ID"):
        sys.exit("gen_transparency: run inside a memory-capped systemd unit (see the docstring)")
    per, failed = {}, {}
    for tc in toolchains():
        try:
            p = subprocess.run([str(tc / "bin/lean"), str(QUERY)], capture_output=True, text=True, timeout=WALL_S, cwd=str(HERE),
                               env={"HOME": os.environ.get("HOME", ""), "PATH": ""})
            if p.returncode != 0:
                raise RuntimeError((p.stdout + p.stderr)[-800:])
            per[tc.name] = parse(p.stdout)
            print(f"{tc.name}: {per[tc.name]['tokens']} tokens, wrappers {per[tc.name]['wrappers']}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            failed[tc.name] = f"{type(e).__name__}: {str(e)[:400]}"
            print(f"{tc.name}: query failed ({type(e).__name__})", file=sys.stderr)
    if not per:
        print("no toolchain ran the query", file=sys.stderr)
        return 1
    seen: dict = {}
    for tc, r in per.items():
        for t, m in r["wrappers"].items():
            seen.setdefault(t, {"modes": set(), "toolchains": []})
            seen[t]["modes"].add(m); seen[t]["toolchains"].append(tc)
    table = {
        "rule": RULE,
        "query": "python3 harness/tools/tables/gen_transparency.py: lean harness/tools/tables/transparency_query.lean (import Lean) on every "
                 "installed core toolchain",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "harness/tools/tables/gen_transparency.py",
        "toolchains": list(per),
        "toolchains_failed": failed,
        "per_toolchain": per,
        "wrappers": {t: {"modes": sorted(v["modes"]), "toolchains": v["toolchains"]} for t, v in sorted(seen.items())},
        "common": common(per),
    }
    OUT.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {OUT}: {len(seen)} wrappers, common {[c['token'] for c in table['common']]}, toolchains {len(per)} ok / "
          f"{len(failed)} failed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
