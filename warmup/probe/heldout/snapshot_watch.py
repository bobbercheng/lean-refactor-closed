#!/usr/bin/env python3
"""Snapshot a budget-ladder run the first time its mean reaches a threshold, without stopping it (2026-10-11, warm-up
Sol run: log and snapshot at >= 89.5, but keep climbing to the cap). Also snapshots the final state
when the runner logs HELDOUT DONE. Bounded: exits at the end of the run or after --max-hours.

  python3 probe/heldout/snapshot_watch.py --root ~/source/lra-ab/wu-hx/harness/hwork/wu-sol --out probe/heldout/wu-hx-sol

A snapshot directory holds submission.jsonl ({name, proof} for every benchmark row, in the Arena upload format; a row without
an improvement carries its reference proof, since a missing row scores 0) and scores.json (per-problem local score, tokens,
heartbeats, spend; total / mean / max spend). Scores are the calibrated local scorer's, not the worker's.
"""
from __future__ import annotations

import argparse, json, pathlib, statistics, time

ap = argparse.ArgumentParser()
ap.add_argument("--root", required=True, help="work root holding <problem>/state.json")
ap.add_argument("--rows", default="data/benchmark_warmup.jsonl")
ap.add_argument("--out", required=True, help="run output dir (jobs.log lives here; snapshots/ is created)")
ap.add_argument("--threshold", type=float, default=89.5)
ap.add_argument("--interval", type=int, default=120)
ap.add_argument("--max-hours", type=float, default=10.0)
a = ap.parse_args()

root, out = pathlib.Path(a.root).expanduser(), pathlib.Path(a.out)
rows = [json.loads(l) for l in open(a.rows) if l.strip()]
jobs = out / "jobs.log"
snaps = out / "snapshots"; snaps.mkdir(exist_ok=True)


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime())}] {msg}"
    print(line, flush=True); jobs.open("a").write(line + "\n")


def read_states() -> dict | None:
    st = {}
    for p in root.glob("*/state.json"):
        try:
            d = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return None   # caught mid-write: try again next tick
        st[d.get("problem")] = d
    return st


def snapshot(st: dict, tag: str) -> float:
    now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    d = snaps / f"{tag}-{now}"; d.mkdir()
    sub, per = [], {}
    for r in rows:
        s = st.get(r["name"]) or {}
        b = s.get("best") or {}
        sub.append({"name": r["name"], "proof": b.get("proof") or r["src"]})
        per[r["name"]] = {"score": b.get("score") or 33.33, "tokens": b.get("tokens"), "heartbeats": b.get("heartbeats"),
                          "improved": bool(b.get("proof")), "spend": round(float(s.get("api_spend") or 0), 6),
                          "budget_milestones": s.get("budget_milestones") or {}}
    (d / "submission.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in sub))
    sp = [v["spend"] for v in per.values()]
    mean = statistics.mean(v["score"] for v in per.values())
    (d / "scores.json").write_text(json.dumps({"taken": now, "tag": tag, "mean_local": round(mean, 2), "spend_total": round(sum(sp), 4),
                                               "spend_mean": round(statistics.mean(sp), 4), "spend_max": round(max(sp), 4),
                                               "problems": per}, ensure_ascii=False, indent=1))
    log(f"SNAPSHOT {tag}: local mean {mean:.2f} over {len(rows)}; spend total ${sum(sp):.2f}, mean ${statistics.mean(sp):.3f}, "
        f"MAX ${max(sp):.3f} per problem; saved {d} (run continues)")
    return mean


deadline = time.time() + a.max_hours * 3600
taken = any(p.name.startswith("reached") for p in snaps.iterdir())
log(f"snapshot watcher armed: threshold {a.threshold}, every {a.interval} s, up to {a.max_hours:g} h"
    + (" (threshold snapshot already taken)" if taken else ""))
while time.time() < deadline:
    txt = jobs.read_text() if jobs.exists() else ""
    done = txt.count("HELDOUT DONE") > txt.count("STOP RULE")   # an early stop is relaunched (nostop_guard.py), so it is not the end
    st = read_states()
    if st is not None:
        mean = statistics.mean(((st.get(r["name"]) or {}).get("best") or {}).get("score") or 33.33 for r in rows)
        if not taken and mean >= a.threshold:
            snapshot(st, f"reached{a.threshold:g}"); taken = True
        if done:
            snapshot(st, "final"); log("snapshot watcher: run finished, exiting"); break
    time.sleep(a.interval)
else:
    log(f"snapshot watcher: {a.max_hours:g} h limit reached without HELDOUT DONE; exiting (threshold snapshot taken: {taken})")
