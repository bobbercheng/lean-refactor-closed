#!/usr/bin/env python3
"""Hourly status of the hosted-model line.
Prints: running units, per-arm best per problem (15 warm-up problems) next to the union, union and union+Sol means,
spend per arm, OpenRouter key usage, and the tail of the active run logs.   python3 harness/hx_status.py"""
from __future__ import annotations

import json, pathlib, subprocess, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARMS = ["haiku", "router", "sol", "solknow", "ds", "dsknow", "wu-sol", "wuclean1", "wuclean2", "argon1", "ab1"]
# 2026-10-13 review: the warm-up Sol ladder (held closed entry 90.47) lives in its own worktree
ARM_ROOTS = {"wu-sol": pathlib.Path.home() / "source/lra-ab/wu-hx/harness/hwork/wu-sol",
             # 2026-10-13 clean recheck (docs/warmup_clean_recheck.md): own whitelist worktree per arm; not part of union+Sol
             "wuclean1": pathlib.Path.home() / "source/lra-ab/wuclean-solclean1-hx/harness/hwork/wuclean-solclean1",
             "wuclean2": pathlib.Path.home() / "source/lra-ab/wuclean-solclean2-hx/harness/hwork/wuclean-solclean2",
             "argon1": pathlib.Path.home() / "source/lra-ab/wuclean-argon1-hx/harness/hwork/wuclean-argon1",   # Gemini 4 Argon, clean
             "ab1": pathlib.Path.home() / "source/lra-ab/wuclean-solab1-hx/harness/hwork/wuclean-solab1"}   # Sol + auto-brief A/B


def unit_states() -> list[str]:
    out = subprocess.run(["systemctl", "--user", "list-units", "lra-*", "--no-legend", "--state=running"], capture_output=True, text=True).stdout
    return [l.split()[0] for l in out.splitlines() if l.strip()]


def arm_bests(arm: str) -> dict:
    res = {}
    for st in ARM_ROOTS.get(arm, ROOT / "harness/hwork" / arm).glob("*/state.json"):
        d = json.loads(st.read_text())
        res[d["problem"]] = (d["best"].get("score") or 33.33, d.get("api_spend") or 0.0)
    return res


def key_usage() -> list[str]:
    rows = []
    for f in sorted((pathlib.Path.home() / ".config/vexorium/oline-keys").glob("*.key")):
        try:
            req = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {f.read_text().strip()}"})
            d = json.loads(urllib.request.urlopen(req, timeout=20).read())["data"]
            rows.append(f"{f.stem.replace('openrouter_', '')}: ${d.get('usage') or 0:.2f} / ${d.get('limit')}")
        except Exception as e:  # noqa: BLE001
            rows.append(f"{f.stem}: unavailable ({type(e).__name__})")
    return rows


def main() -> None:
    subprocess.run(["python3", "leaderboard/problem_scores.py"], cwd=ROOT, capture_output=True)
    ps = json.loads((ROOT / "leaderboard/problem_scores.json").read_text())
    U3 = ("flash-agent", "opus-5.5-line", "gpt-astra-line")
    B = {a: arm_bests(a) for a in ARMS}
    print(f"## Hosted-model status — {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}\n")
    print("Running units: " + (", ".join(unit_states()) or "none"))
    # system health (2026-10-11: OOM at 03:01 killed every unit; then a Codex app-server git-diff storm of ~24k processes)
    mem = subprocess.run(["free", "-g"], capture_output=True, text=True).stdout.splitlines()[1].split()
    git_n = subprocess.run(["pgrep", "-c", "git"], capture_output=True, text=True).stdout.strip() or "0"
    oom = subprocess.run("journalctl --user --since '-1h' --no-pager 2>/dev/null | grep -ci 'killed by the OOM killer'", shell=True,
                         capture_output=True, text=True).stdout.strip() or "0"
    flags = (["(git storm: left alone per operator unless memory is low)"] if int(git_n) > 200 else []) + (["⚠ OOM kills in the last hour"] if int(oom) > 0 else []) + \
            (["⚠ low memory (<15 GB available: git-storm rule applies)"] if int(mem[6]) < 15 else [])
    print(f"System: memory used {mem[2]} GB / {mem[1]} GB (available {mem[6]} GB) · git processes {git_n} · OOM kills last hour {oom}"
          + ("  " + " ".join(flags) if flags else "  ✓ healthy") + "\n")
    print("| problem | union | " + " | ".join(ARMS) + " |\n|---|---|" + "---|" * len(ARMS))
    u_sum = us_sum = 0.0
    for e in ps["problems"]:
        n = e["name"]; u = max((e["by_source"][s]["best"] or 33.33) for s in U3)
        sol_best = max([B[a][n][0] for a in ("sol", "solknow", "wu-sol") if n in B[a]] or [0])
        u_sum += u; us_sum += max(u, sol_best)
        cells = [(f"{B[a][n][0]:.2f}" + (" ★" if B[a][n][0] > u else "")) if n in B[a] else "—" for a in ARMS]
        print(f"| {n.split('.')[-1][:30]} | {u:.2f} | " + " | ".join(cells) + " |")
    k = len(ps["problems"])
    print(f"\n**Union {u_sum / k:.2f} · Union + Sol {us_sum / k:.2f}** (★ = beats the union on that problem)")
    # $2 milestone (2026-10-11): flag every problem whose spend in an arm has passed $2 (the hard cap is $2.85)
    print("Arm coverage and spend: " + "; ".join(f"{a} {len(B[a])}/15 ${sum(v[1] for v in B[a].values()):.2f}"
                                                  + (f" ⚠ {sum(v[1] >= 2.0 for v in B[a].values())} past $2" if any(v[1] >= 2.0 for v in B[a].values()) else "")
                                                  for a in ARMS))
    print("OpenRouter keys: " + "; ".join(key_usage()))
    # budget-ladder runs (hx_heldout.py: warm-up, sealed sets): the last milestone / round lines of any run active in the last 3 hours
    for jl in sorted(ROOT.glob("probe/heldout/*-hx-*/jobs.log")):
        if time.time() - jl.stat().st_mtime < 3 * 3600:
            tail = [l for l in jl.read_text().splitlines() if any(k in l for k in ("round", "MILESTONE", "STOP", "RESCUE", "fresh lineage", "DONE"))][-3:]
            print(f"{jl.parent.name}: " + " | ".join(t[27:140] for t in tail))
    for log in ("probe/hx-pilot.log", "probe/hx-sol15.log"):
        p = ROOT / log
        if p.exists():
            tail = [l for l in p.read_text().splitlines() if l.startswith("[")][-2:]
            print(f"{log}: " + " | ".join(t[:110] for t in tail))


if __name__ == "__main__":
    main()
