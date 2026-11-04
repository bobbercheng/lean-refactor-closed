#!/usr/bin/env python3
"""Bets test helper and readout (bet-backend-replay, 2026-11-02; driven by infra/closed_package/bets_test.sh). No model call, no compile.

    python3 infra/closed_package/bets_readout.py subset --rows ROWS.jsonl --heartbeats HB.jsonl --test-rows TEST_ROWS.json --out DIR
        DIR/rows.jsonl + DIR/heartbeats.jsonl: the test rows (TEST_ROWS.json: {"rows": [{"name", "why"}, ...]} or a list of names) in
        the rows file's order, with their reference heartbeats (both arms read the same two files)
    python3 infra/closed_package/bets_readout.py state --out ARM_OUT
        one JSON line: {"shards": {label: running|done|<why not>}, "all_done", "any_running"} (run_final.py's own tests)
    python3 infra/closed_package/bets_readout.py readout --ctl CTL_OUT --bet BET_OUT [--run1 RUN1] [--run1-hb HB.jsonl] [--json OUT.json]
        [--test-rows TEST_ROWS.json]
        the paired readout: per row the control's and the bets arm's final score (the shards' finals.json, the router's stored scale) and
        spend, d = bets - control; mean, median, wins / losses / ties (|d| < TIE), a 95 % bootstrap CI of the mean d (10,000 resamples,
        seeded) and a t interval, the sign test's two-sided p; the same of each arm against closed run 1's finals (RUN1 = its
        finals_all.json, or its run_final --out dir: shards/*/finals.json), with the rows whose reference heartbeats differ from run 1's
        (--run1-hb, run 1's heartbeats file) flagged (their run-1 delta mixes references). Rows missing from an arm are listed, never
        counted as 0. --test-rows: the paired d also per selection criterion (the rows' "criteria" flags, e.g. d1_long / sol_stall / gap3),
        so a bet aimed at one kind of row is read on those rows."""
from __future__ import annotations

import argparse, json, math, random, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TIE = 0.005
BOOT, SEED = 10000, 20261102


def _jsonl(path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def test_names(path) -> list[str]:
    d = json.loads(Path(path).read_text())
    rows = d.get("rows") if isinstance(d, dict) else d
    return [r["name"] if isinstance(r, dict) else str(r) for r in rows]


def cmd_subset(a) -> int:
    want = test_names(a.test_rows)
    rows = _jsonl(a.rows)
    have = {r["name"] for r in rows}
    miss = [n for n in want if n not in have]
    if miss:
        print(f"subset: {len(miss)} test row(s) not in {a.rows}: {miss[:5]}", file=sys.stderr); return 2
    hb = {h["name"]: h["heartbeat"] for h in _jsonl(a.heartbeats)}
    nohb = [n for n in want if n not in hb]
    if nohb:
        print(f"subset: {len(nohb)} test row(s) without reference heartbeats in {a.heartbeats}: {nohb[:5]}", file=sys.stderr); return 2
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    keep = [r for r in rows if r["name"] in set(want)]
    (out / "rows.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep))
    (out / "heartbeats.jsonl").write_text("".join(json.dumps({"name": r["name"], "heartbeat": hb[r["name"]]}) + "\n" for r in keep))
    print(f"subset: {len(keep)} row(s) -> {out / 'rows.jsonl'}, {out / 'heartbeats.jsonl'}")
    return 0


def cmd_state(a) -> int:
    sys.path.insert(0, str(ROOT / "infra/closed_package"))
    import run_final as RF   # noqa: E402
    out = Path(a.out).expanduser().resolve()
    plan = RF.load_plan(out)
    if not plan:
        print(json.dumps({"shards": {}, "all_done": False, "any_running": False, "note": f"no plan in {out}"})); return 0
    st = {}
    for sh in plan["shards"]:
        if RF.running(sh, plan):
            st[sh["label"]] = "running"
        else:
            done, why = RF.shard_done(sh)
            st[sh["label"]] = "done" if done else why
    print(json.dumps({"shards": st, "all_done": all(v == "done" for v in st.values()), "any_running": any(v == "running" for v in st.values())}))
    return 0


def arm_finals(out) -> dict:
    """{name: {"score", "spend", "stage"}} of a run_final --out dir (every shard's finals.json) or of a finals_all.json file."""
    p = Path(out)
    files = [p] if p.is_file() else sorted(p.glob("shards/*/finals.json"))
    res = {}
    for f in files:
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        for n, v in (d or {}).items():
            if isinstance(v, dict) and v.get("score") is not None:
                res[n] = {"score": float(v["score"]), "spend": v.get("spend"), "stage": v.get("stage")}
    return res


def staged_hb(out) -> dict:
    """The reference heartbeats an arm ran with (its heartbeats file copy, written by bets_test.sh), else {}."""
    for f in (Path(out) / "heartbeats.jsonl", Path(out).parent / "heartbeats.jsonl"):
        if f.is_file():
            return {h["name"]: h["heartbeat"] for h in _jsonl(f)}
    return {}


def stats(ds: list[float]) -> dict:
    n = len(ds)
    if not n:
        return {"n": 0}
    mean = sum(ds) / n
    out = {"n": n, "mean": round(mean, 4), "median": round(statistics.median(ds), 4), "wins": sum(1 for d in ds if d >= TIE),
           "losses": sum(1 for d in ds if d <= -TIE), "ties": sum(1 for d in ds if abs(d) < TIE), "sum": round(sum(ds), 3)}
    rng = random.Random(SEED)
    bm = sorted(sum(rng.choice(ds) for _ in range(n)) / n for _ in range(BOOT))
    out["ci95_boot"] = [round(bm[int(0.025 * BOOT)], 4), round(bm[int(0.975 * BOOT) - 1], 4)]
    if n > 1:
        sd = statistics.stdev(ds)
        tq = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
              13: 2.160, 14: 2.145, 15: 2.131, 20: 2.086, 30: 2.042}
        t = tq.get(n - 1) or (tq[max(k for k in tq if k <= n - 1)] if n - 1 < 30 else 1.96)
        out["sd"] = round(sd, 4)
        out["ci95_t"] = [round(mean - t * sd / math.sqrt(n), 4), round(mean + t * sd / math.sqrt(n), 4)]
    k, m = out["wins"], out["wins"] + out["losses"]   # sign test, ties dropped
    if m:
        p = sum(math.comb(m, i) for i in range(0, min(k, m - k) + 1)) / 2 ** m * 2
        out["sign_p"] = round(min(1.0, p), 4)
    return out


def cmd_readout(a) -> int:
    ctl, bet = arm_finals(a.ctl), arm_finals(a.bet)
    run1 = arm_finals(a.run1) if a.run1 else {}
    hb_c, hb_b = staged_hb(a.ctl), staged_hb(a.bet)
    hb1 = {h["name"]: h["heartbeat"] for h in _jsonl(a.run1_hb)} if a.run1_hb else {}
    names = [n for n in (list(hb_c) or sorted(set(ctl) | set(bet))) if n in set(ctl) | set(bet) | set(hb_c)]
    rows, paired, vs1c, vs1b, missing, refdiff = [], [], [], [], [], []
    for n in names:
        c, b, r = ctl.get(n), bet.get(n), run1.get(n)
        rec = {"name": n, "ctl": c and c["score"], "bet": b and b["score"], "run1": r and r["score"],
               "ctl_spend": c and c.get("spend"), "bet_spend": b and b.get("spend"), "bet_stage": b and b.get("stage")}
        if c is None or b is None:
            missing.append(n)
        else:
            rec["d"] = round(b["score"] - c["score"], 4); paired.append(rec["d"])
        diff = bool(hb1) and n in hb1 and (hb_c.get(n) not in (None, hb1[n]) or hb_b.get(n) not in (None, hb1[n]))
        rec["ref_differs_from_run1"] = diff
        if diff:
            refdiff.append(n)
        if r is not None and not diff:
            if c is not None:
                rec["ctl_vs_run1"] = round(c["score"] - r["score"], 4); vs1c.append(rec["ctl_vs_run1"])
            if b is not None:
                rec["bet_vs_run1"] = round(b["score"] - r["score"], 4); vs1b.append(rec["bet_vs_run1"])
        rows.append(rec)
    sp = lambda arm: [float(x[f"{arm}_spend"]) for x in rows if x.get(f"{arm}_spend") is not None]   # noqa: E731
    rep = {"ctl": str(a.ctl), "bet": str(a.bet), "run1": str(a.run1) if a.run1 else None, "rows": rows, "missing": missing,
           "ref_differs_from_run1": refdiff, "paired_bet_minus_ctl": stats(paired), "ctl_minus_run1": stats(vs1c), "bet_minus_run1": stats(vs1b),
           "means": {k: round(sum(v) / len(v), 4) if v else None for k, v in
                     (("ctl", [x["ctl"] for x in rows if x["ctl"] is not None]), ("bet", [x["bet"] for x in rows if x["bet"] is not None]),
                      ("run1", [x["run1"] for x in rows if x["run1"] is not None]))},
           "spend": {arm: {"mean": round(sum(sp(arm)) / len(sp(arm)), 4) if sp(arm) else None, "max": max(sp(arm)) if sp(arm) else None,
                           "over_cap": sum(1 for v in sp(arm) if v > 3.0)} for arm in ("ctl", "bet")}}
    if a.test_rows:   # the paired d per selection criterion
        try:
            tr = json.loads(Path(a.test_rows).read_text())
            crit = {r["name"]: r.get("criteria") or {} for r in (tr.get("rows") if isinstance(tr, dict) else tr) if isinstance(r, dict)}
        except (OSError, ValueError):
            crit = {}
        keys = sorted({k for c in crit.values() for k, v in c.items() if v})
        rep["by_criterion"] = {k: stats([x["d"] for x in rows if "d" in x and (crit.get(x["name"]) or {}).get(k)]) for k in keys}
    lines = [f"bets readout: control {a.ctl} vs bets {a.bet}" + (f"; run 1 {a.run1}" if a.run1 else ""),
             f"{'row':44s} {'ctl':>7s} {'bet':>7s} {'d':>7s} {'run1':>7s} {'ctl$':>6s} {'bet$':>6s}"]
    for x in rows:
        f = lambda v, w=7, p=2: (f"{v:{w}.{p}f}" if isinstance(v, (int, float)) else f"{'-':>{w}s}")   # noqa: E731
        lines.append(f"{x['name'][-44:]:44s} {f(x['ctl'])} {f(x['bet'])} {f(x.get('d'))} {f(x['run1'])}{'*' if x['ref_differs_from_run1'] else ' '}"
                     f"{f(x['ctl_spend'], 6)} {f(x['bet_spend'], 6)}")
    for k, lab in (("paired_bet_minus_ctl", "bets - control"), ("ctl_minus_run1", "control - run 1"), ("bet_minus_run1", "bets - run 1")):
        s = rep[k]
        if s.get("n"):
            lines.append(f"{lab:16s} n {s['n']}: mean {s['mean']:+.3f}, median {s['median']:+.3f}, wins {s['wins']} / losses {s['losses']} / "
                         f"ties {s['ties']}, 95% CI boot [{s['ci95_boot'][0]:+.3f}, {s['ci95_boot'][1]:+.3f}]"
                         + (f", t [{s['ci95_t'][0]:+.3f}, {s['ci95_t'][1]:+.3f}]" if "ci95_t" in s else "")
                         + (f", sign p {s['sign_p']}" if "sign_p" in s else ""))
    for k, s in (rep.get("by_criterion") or {}).items():
        if s.get("n"):
            lines.append(f"  rows with {k:12s} n {s['n']}: mean d {s['mean']:+.3f}, median {s['median']:+.3f}, wins {s['wins']} / losses {s['losses']}")
    if missing:
        lines.append(f"missing in an arm (not counted): {', '.join(missing)}")
    if refdiff:
        lines.append(f"* reference heartbeats differ from run 1's (left out of the run-1 comparison): {', '.join(refdiff)}")
    lines.append("spend: " + "; ".join(f"{k} mean ${v['mean']} max ${v['max']} over cap {v['over_cap']}" for k, v in rep["spend"].items()))
    rep["text"] = "\n".join(lines)
    print(rep["text"])
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("subset"); s.add_argument("--rows", required=True); s.add_argument("--heartbeats", required=True)
    s.add_argument("--test-rows", required=True); s.add_argument("--out", required=True)
    s = sp.add_parser("state"); s.add_argument("--out", required=True)
    s = sp.add_parser("readout"); s.add_argument("--ctl", required=True); s.add_argument("--bet", required=True)
    s.add_argument("--run1"); s.add_argument("--run1-hb"); s.add_argument("--json"); s.add_argument("--test-rows")
    a = ap.parse_args(argv)
    return {"subset": cmd_subset, "state": cmd_state, "readout": cmd_readout}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
