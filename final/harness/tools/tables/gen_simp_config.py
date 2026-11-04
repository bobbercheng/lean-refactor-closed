#!/usr/bin/env python3
"""Writes harness/tools/tables/simp_config_fields.json (the configuration settings harness/hb_tool_candidates.py's simp_config and
grind_config families may insert) from simp_config_query.lean, run on every installed core toolchain
(~/.elan/toolchains/leanprover--lean4---v*). Nothing in the table is typed by hand: the fields, their types, defaults and declaration
order are Lean's own (the configuration structure each tactic elaborates its options into), and a setting is kept only when every
toolchain accepts it on the goal True and none closes the goal False with it (the query's probes).

Table fields:
  per_toolchain  for each toolchain: every structure's fields in declaration order ([field, type, default]), the structure of each
                 tactic, the bare probe of each tactic ([accepted on True, closes False]) and, per tactic and field, each probed spelling
                 ({"opt" | "cfg": [accepted on True, closes False]})
  tactics        per tactic (simp, simpa, simp_all, grind): its structure; "toggles", the Bool fields present with the same default on
                 every toolchain, toggled away from that default, in declaration order (the relative order must agree on every
                 toolchain), each {"field", "default", "setting"} in the option form `+f` / `-f` when every toolchain accepts it, else
                 the config form `(config := { f := v })` when every toolchain accepts that, else dropped (listed in "dropped" with the
                 reason). No field is selected by name: the 2026-10-22 review removed the discharge-depth grid ("discharge"), which named
                 one Nat field by hand (a word of one union proof and of no seed), together with hb_tool_candidates' simp_discharge family
Run it inside a memory-capped unit (it runs Lean):
    systemd-run --user --wait --pipe --unit lra-merge-<id> -p MemoryMax=16G -p OOMPolicy=continue -p RuntimeMaxSec=1800 \\
      --working-directory=<worktree> -E PATH -E HOME python3 harness/tools/tables/gen_simp_config.py"""
from __future__ import annotations

import datetime, json, os, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
QUERY = HERE / "simp_config_query.lean"
OUT = HERE / "simp_config_fields.json"
TOOLCHAINS = Path.home() / ".elan" / "toolchains"
WALL_S = 600
RULE = ("The configuration structure each tactic elaborates its options into (Lean.Elab.Tactic.elabSimpConfig: simp and simpa -> "
        "Lean.Meta.Simp.Config, simp_all -> Lean.Meta.Simp.ConfigCtx; grind -> Lean.Grind.Config) is enumerated by "
        "simp_config_query.lean on every installed core toolchain: every field (flattened, Lean's declaration order, nothing filtered "
        "by name) with its type and default. toggles: every Bool field toggled away from its default, singly, in the option form +f "
        "(default false) / -f (default true) when every toolchain accepts it, else the config form (config := { f := v }) when every "
        "toolchain accepts that; kept only when the field has the same default on every toolchain and the setting is accepted on the "
        "goal True and does not close the goal False (a setting that closes False closes goals without a proof) on every toolchain; "
        "ordered by declaration order (the relative order agrees on every toolchain). No field is selected by name. "
        "harness/hb_tool_candidates.py offers a call each toggle of its tactic that the call does not already set, singly and in table "
        "order (simp_config, grind_config).")


def _ver_key(name: str):
    v = name.split("---", 1)[-1].lstrip("v")
    nums = [int(x) for x in re.findall(r"\d+", v.split("-")[0])]
    return (nums, 0 if "-rc" in v else 1, v)


def toolchains() -> list[Path]:
    ts = [p for p in TOOLCHAINS.glob("leanprover--lean4---v*") if (p / "bin/lean").is_file()]
    return sorted(ts, key=lambda p: _ver_key(p.name))


def _flag(s: str) -> bool:
    if s not in ("true", "false"):
        raise ValueError(f"not a Bool: {s!r}")
    return s == "true"


def parse(text: str) -> dict:
    """The query's output lines -> {"structures": {S: [[field, type, default]]}, "tactics": {tac: S}, "bare": {tac: [ok, closesFalse]},
    "probes": {tac: {field: {form: [ok, closesFalse]}}}, "settings": {tac: {field: {form: setting}}}} (form "opt" or "cfg")."""
    st: dict = {}; tac: dict = {}; bare: dict = {}; probes: dict = {}; settings: dict = {}
    for line in text.splitlines():
        p = line.split("\t")
        if p[0] == "F" and len(p) == 6:
            st.setdefault(p[1], []).append((int(p[2]), p[3], p[4], p[5]))
        elif p[0] == "T" and len(p) == 3:
            tac[p[1]] = p[2]
        elif p[0] == "B" and len(p) == 4:
            bare[p[1]] = [_flag(p[2]), _flag(p[3])]
        elif p[0] == "P" and len(p) == 7:
            t, form, field, setting = p[1], p[2], p[3], p[4]
            if form not in ("opt", "cfg"):
                raise ValueError(f"unknown probe form {form!r}")
            key = form
            probes.setdefault(t, {}).setdefault(field, {})[key] = [_flag(p[5]), _flag(p[6])]
            settings.setdefault(t, {}).setdefault(field, {})[key] = setting
    if not st or not tac or set(bare) != set(tac):
        raise ValueError("incomplete query output")
    for s, fs in st.items():
        if [i for i, *_ in fs] != list(range(len(fs))):
            raise ValueError(f"{s}: field indices are not 0 .. n-1")
    if not all(ok and not closes for ok, closes in bare.values()):
        raise ValueError(f"a bare probe failed on True or closed False: {bare}")
    return {"structures": {s: [[f, ty, d] for _, f, ty, d in fs] for s, fs in st.items()}, "tactics": tac, "bare": bare,
            "probes": probes, "settings": settings}


def _good(per: dict, tac: str, field: str, key: str) -> bool:
    """Accepted on True and not closing False on every toolchain."""
    return all((r["probes"].get(tac, {}).get(field, {}).get(key) or [False, True]) == [True, False] for r in per.values())


def common(per: dict) -> dict:
    """Per tactic: its toggles (module docstring), from every toolchain's parsed output."""
    tcs = list(per)
    tactics = per[tcs[0]]["tactics"]
    if any(per[t]["tactics"] != tactics for t in tcs):
        raise ValueError("the tactic -> structure map differs between toolchains")
    out = {}
    for tac, s in tactics.items():
        tables = [{f: (ty, d) for f, ty, d in per[t]["structures"][s]} for t in tcs]
        names = [f for f, _, _ in per[tcs[0]]["structures"][s]]
        shared = [f for f in names if all(f in tb and tb[f] == tables[0][f] for tb in tables)]
        for t in tcs:
            order = [f for f, _, _ in per[t]["structures"][s] if f in shared]
            if order != shared:
                raise ValueError(f"{s}: the declaration order of the shared fields differs on {t}")
        toggles, dropped = [], []
        for f in shared:
            ty, d = tables[0][f]
            if ty == "Bool" and d in ("true", "false"):
                key = "opt" if _good(per, tac, f, "opt") else ("cfg" if _good(per, tac, f, "cfg") else None)
                if key is None:
                    dropped.append({"field": f, "default": d == "true", "reason": "a toolchain rejects both spellings or one closes False"})
                    continue
                toggles.append({"field": f, "default": d == "true", "setting": per[tcs[0]]["settings"][tac][f][key]})
        absent = sorted({f for tb in tables for f in tb} - set(shared))
        out[tac] = {"structure": s, "toggles": toggles, "dropped": dropped, "not_on_every_toolchain": absent}
    return out


def main() -> int:
    if not os.environ.get("INVOCATION_ID"):
        sys.exit("gen_simp_config: run inside a memory-capped systemd unit (see the docstring)")
    per, failed = {}, {}
    for tc in toolchains():
        try:
            p = subprocess.run([str(tc / "bin/lean"), str(QUERY)], capture_output=True, text=True, timeout=WALL_S, cwd=str(HERE),
                               env={"HOME": os.environ.get("HOME", ""), "PATH": ""})
            if p.returncode != 0:
                raise RuntimeError((p.stdout + p.stderr)[-800:])
            per[tc.name] = parse(p.stdout)
            print(f"{tc.name}: {sum(len(v) for v in per[tc.name]['structures'].values())} fields", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            failed[tc.name] = f"{type(e).__name__}: {str(e)[:400]}"
            print(f"{tc.name}: query failed ({type(e).__name__})", file=sys.stderr)
    if not per:
        print("no toolchain ran the query", file=sys.stderr)
        return 1
    table = {
        "rule": RULE,
        "query": "python3 harness/tools/tables/gen_simp_config.py: lean harness/tools/tables/simp_config_query.lean (import Lean) on every "
                 "installed core toolchain",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "harness/tools/tables/gen_simp_config.py",
        "toolchains": list(per),
        "toolchains_failed": failed,
        "per_toolchain": {t: {k: r[k] for k in ("structures", "tactics", "bare", "probes")} for t, r in per.items()},
        "tactics": common(per),
    }
    OUT.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {OUT}: " + ", ".join(f"{t} {len(v['toggles'])} toggles"
                                       for t, v in table["tactics"].items())
          + f"; toolchains {len(per)} ok / {len(failed)} failed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
