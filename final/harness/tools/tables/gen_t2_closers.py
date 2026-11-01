#!/usr/bin/env python3
"""Writes harness/tools/tables/t2_closers.json from t2_closers_query.lean, run on every installed core toolchain (~/.elan/toolchains,
leanprover--lean4---v*), and merges the outcomes. Nothing in the table is typed by hand: the token list is Lean's tactic leading-token
table, the classes come from the measured outcomes on the query's synthetic battery.

Class of a token form (bare `tok`, or `tok x` with one term argument), from the outcome counts summed over the toolchains:
  closer      closed some battery goal, and never succeeded while leaving a goal open or unchanged (and never closed through sorry)
  mixed       closed some goal and also left one open or unchanged (it can act as a closer or as a decomposer)
  decomposer  never closed a goal, left one open
  inert       neither (it only failed, left the goal unchanged or used sorry)
The T2 scheduler moves closers out of a `first` loop, tries mixed and unlisted forms in both roles, keeps the others in the loop body.

Run it inside a memory-capped unit (it compiles):
    systemd-run --user --wait --pipe --unit lra-b62t-t2gen -p MemoryMax=16G -p OOMPolicy=continue -p RuntimeMaxSec=1800 \\
      --working-directory=<worktree> -E PATH -E HOME python3 harness/tools/tables/gen_t2_closers.py"""
from __future__ import annotations

import collections, datetime, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUERY = HERE / "t2_closers_query.lean"
OUT = HERE / "t2_closers.json"
TOOLCHAINS = Path.home() / ".elan" / "toolchains"
RULE = ("Every leading token of Lean core's `tactic` syntax category (Init + Lean; complete, nothing filtered by name), bare and with one "
        "term argument, run on a fixed battery of synthetic Prop/Nat goals (t2_closers_query.lean) on every installed core toolchain; "
        "class per form from the summed outcomes (a token whose runs did not finish within the wall-clock limit on a toolchain is skipped there and on every later toolchain, listed in skipped_hung): closer = closed some goal and never left one open or unchanged or closed through "
        "sorry; mixed = closed some and left some open/unchanged; decomposer = never closed, left some open; inert = otherwise. "
        "combinators: the five goal-list combinators the T2 spec allows the scheduler to add (rotate_left, any_goals, all_goals, "
        "repeat, repeat'), each checked present in the same token table on every toolchain.")


def classify(cnt: dict) -> str:
    if cnt.get("closed") and not (cnt.get("open") or cnt.get("unchanged") or cnt.get("sorry")):
        return "closer"
    if cnt.get("closed"):
        return "mixed"
    if cnt.get("open"):
        return "decomposer"
    return "inert"


WALL_S = 90       # one toolchain's whole query; core toolchains finish it in about 10 s
MAX_SKIPS = 12


def run_one(lean: Path, carried: list[str]) -> tuple[list[str], str, list[str]]:
    """The query's output lines on one toolchain, an error text ("" when it ran), and the tokens skipped because the query did not finish
    within WALL_S with them (the last token the query announced before the limit is skipped and the query rerun; tokens that hung on an
    earlier toolchain are skipped from the start)."""
    import os
    skip: list[str] = list(carried)
    for _ in range(MAX_SKIPS + 1):
        env = dict(os.environ, T2_SKIP=",".join(skip))
        try:
            p = subprocess.run([str(lean), str(QUERY)], capture_output=True, text=True, timeout=WALL_S, cwd=str(HERE), env=env)
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            ks = [l.split("\t")[1] for l in out.splitlines() if l.startswith("K\t")]
            if not ks or ks[-1] in skip:
                return [], f"timeout after {WALL_S} s with no new token to skip", skip
            skip.append(ks[-1])
            print(f"{lean.parent.parent.name}: {ks[-1]} did not finish in {WALL_S} s, skipped", file=sys.stderr, flush=True)
            continue
        err = "" if p.returncode == 0 else (p.stdout + p.stderr)[-2000:]
        return p.stdout.splitlines(), err, skip
    return [], f"more than {MAX_SKIPS} tokens hung", skip


def main() -> int:
    tcs = sorted(d for d in TOOLCHAINS.iterdir() if d.name.startswith("leanprover--lean4---v") and (d / "bin" / "lean").exists())
    counts: dict = collections.defaultdict(collections.Counter)
    present: dict = collections.defaultdict(list)
    comb: dict = collections.defaultdict(list)
    used, failed, hung = [], {}, collections.defaultdict(list)
    for tc in tcs:
        lines, err, skipped = run_one(tc / "bin" / "lean", sorted(hung))
        for t in skipped:
            hung[t].append(tc.name)
        if err:
            failed[tc.name] = err
            print(f"{tc.name}: query failed", file=sys.stderr)
            continue
        used.append(tc.name)
        for line in lines:
            p = line.split("\t")
            if p[0] == "R" and len(p) == 5:
                counts[(p[1], p[2])][p[4]] += 1
            elif p[0] == "K" and len(p) == 4:
                present[p[1]].append(tc.name)
            elif p[0] == "C" and len(p) == 3 and p[2] == "true":
                comb[p[1]].append(tc.name)
        print(f"{tc.name}: {sum(1 for l in lines if l.startswith('R'))} runs", file=sys.stderr)
    if not used:
        print("no toolchain ran the query", file=sys.stderr)
        return 1
    forms: dict = {}
    for (tok, form), cnt in sorted(counts.items()):
        forms.setdefault(tok, {})[form] = {"class": classify(cnt), "counts": dict(sorted(cnt.items()))}
    table = {
        "rule": RULE,
        "query": "harness/tools/tables/t2_closers_query.lean via harness/tools/tables/gen_t2_closers.py (lean <query> per toolchain)",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "toolchains": used,
        "toolchains_failed": sorted(failed),
        "forms": forms,
        "present": {t: v for t, v in sorted(present.items())},
        "skipped_hung": {t: v for t, v in sorted(hung.items())},
        "combinators": {c: sorted(comb.get(c, [])) for c in ("rotate_left", "any_goals", "all_goals", "repeat", "repeat'")},
    }
    OUT.write_text(json.dumps(table, ensure_ascii=False, indent=1, sort_keys=False) + "\n")
    by = collections.Counter(f["class"] for t in forms.values() for f in t.values())
    print(f"wrote {OUT}: {len(forms)} tokens, classes {dict(by)}, toolchains {len(used)} ok / {len(failed)} failed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
