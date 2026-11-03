#!/usr/bin/env python3
"""Closed-track budget-ladder runner (2026-10-11: per-problem cap, a $2 warning milestone per problem). One hosted model, the current harness, every
problem in its own work root (so state.json api_spend is that problem's whole spend).

BUDGET LADDER (default rungs $2.00, $2.85): rounds of 40-turn sessions fill EVERY problem up to a rung before any problem may pass it
(breadth-first). Each finished rung writes a MILESTONE report (mean score, spend, per-repo means, score at budget) over all problems,
so the $2 snapshot is complete and uncensored before any money goes past $2. The agent's gate is a hard bound (it reserves each
turn's worst case), so no problem's spend ever crosses the current rung; agent.py also records the moment a problem's spend crosses
$2 (state.json budget_milestones). Resumable: rerunning continues at the next round and rung.

Sets: warmup (the 15 official warm-up rows). Only scores, spend
and the per-turn cost/best numbers are read, never proof, trajectory text or errors.
    python3 harness/hx_heldout.py --set warmup --arm sol [--rungs 1.0,2.0,2.85] [--report]
"""
from __future__ import annotations

import argparse, gzip, json, pathlib, re, statistics, subprocess, time
from concurrent.futures import ThreadPoolExecutor

MAIN = pathlib.Path(__file__).resolve().parents[1]
SETS = {   # the 15 official warm-up rows (2026-10-11: warm-up run, knowledge and tools reused, proofs not; target >= 89.5)
        "warmup": ("data/benchmark_warmup.jsonl", "data/benchmark_heartbeats.jsonl", "wu", None)}
SESSION_FLOOR = 0.30   # no session starts with less left: the first turn's worst case (opening context uncached + 12k output) is ~$0.15-0.27


class Set:
    def __init__(self, key: str, arm: str):
        path, hb, self.prefix, self.ref_log = SETS[key]
        self.rows = [json.loads(l) for l in (MAIN / path).open() if l.strip()]
        self.names = [r["name"] for r in self.rows]
        self.hb_path = MAIN / hb
        self.wt = pathlib.Path.home() / f"source/lra-ab/{self.prefix}-hx"
        self.root = f"harness/hwork/{self.prefix}-{arm}"
        self.run_prefix = f"{self.prefix}-hx-{arm}-r"
        self.out = MAIN / f"probe/heldout/{self.prefix}-hx-{arm}"


def setup_worktree(S: Set, ref: str, log) -> None:
    """Worktree at `ref` whose data files carry the set's rows ; envs symlinked from main."""
    if not S.wt.exists():
        subprocess.run(["git", "worktree", "add", "--detach", str(S.wt), ref], cwd=MAIN, check=True, capture_output=True)
    subprocess.run(["git", "-C", str(S.wt), "checkout", "-q", "--detach", ref], check=True)
    ign = subprocess.run(["git", "status", "--ignored", "--porcelain", "envs"], cwd=MAIN, capture_output=True, text=True).stdout
    for d in [l[3:].rstrip("/") for l in ign.splitlines() if l.startswith("!!")]:
        if not (S.wt / d).exists():
            (S.wt / d).symlink_to(MAIN / d)
    if S.prefix == "wu":   # official rows already live in data/; their local reference heartbeats are calibrated, never overwrite them
        log(f"worktree {S.wt} at {ref}: warm-up rows used as committed"); return
    hbs = [json.loads(l) for l in S.hb_path.open() if l.strip()]
    names = set(S.names)
    for f, new in (("data/benchmark_warmup.jsonl", S.rows), ("data/benchmark_heartbeats.jsonl", hbs)):
        p = S.wt / f
        keep = [l for l in p.read_text().splitlines() if l.strip() and json.loads(l)["name"] not in names]
        p.write_text("\n".join(keep + [json.dumps(r, ensure_ascii=False) for r in new]) + "\n")
    p = S.wt / "data/reference_heartbeats_local.json"; d = json.loads(p.read_text())
    for h in hbs:
        r = next(x for x in S.rows if x["name"] == h["name"])
        d[h["name"]] = {"toolchain": list(r["version_info"][0])[0], "heartbeats_local": h["heartbeat"], "heartbeats_official": h["heartbeat"], "ok": True}
    p.write_text(json.dumps(d, indent=1))
    log(f"worktree {S.wt} at {ref} ({subprocess.run(['git', '-C', str(S.wt), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()}), {len(S.rows)} rows")


def states(S: Set) -> dict:
    """Keyed by the problem name stored IN each state.json: work-dir names are sanitized and differ for some problems (the first
    version counted two such problems as unstarted: 33.33 and $0)."""
    res = {}
    for st in (S.wt / S.root).glob("*/state.json"):
        d = json.loads(st.read_text())
        if d.get("problem") in S.names:
            res[d["problem"]] = {"score": d["best"].get("score") or 33.33, "spend": float(d.get("api_spend") or 0)}
    return res


def targets(S: Set) -> dict:
    """Per-problem target score for choosing rescue problems: the union best on the warm-up (a score, not a proof); 100 elsewhere."""
    try:
        u = {e["name"]: e.get("union") for e in json.loads((MAIN / "leaderboard/problem_scores.json").read_text())["problems"]}
    except (OSError, ValueError, KeyError):
        u = {}
    return {n: (u.get(n) or 100.0) for n in S.names}


def safe(n: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", n)   # agent.py's work-dir / trajectory name for problem n


def typical_first(S: Set) -> dict:
    """Warm-up only: the score Sol + briefs typically reaches in its FIRST session on each problem (scores from the earlier solknow arm;
    knowledge, never proofs). Used to spot a bad first draw."""
    if S.prefix != "wu":
        return {}
    out = {}
    for st in (MAIN / "harness/hwork/solknow").glob("*/state.json"):
        d = json.loads(st.read_text())
        runs = [r.get("run_id") for r in d.get("runs", []) if r.get("run_id")]
        if runs:
            sc = [a.get("score") or 0 for a in d.get("attempts", []) if a.get("run_id") == runs[0] and a.get("ok")]
            if sc:
                out[d["problem"]] = max(sc)
    return out


def fresh_round(S: Set, names: list[str], rung: float, run_id: str, effort: str, restructure: bool, extra: list, preset: str,
                workers: int, say) -> None:
    """One session per problem in an EMPTY workspace (2026-10-11: a rescue does not resume from the current checkpoint): its
    state.json holds no proof, notes or variants, only the problem's spend so far, so the agent's hard cap at `rung` covers the main and
    the fresh lineage together. Afterwards the spend carries back, the fresh best replaces the main best only if higher, and the fresh
    workspace is archived (never resumed)."""
    froot = S.wt / f"{S.root}-fresh"
    main = {json.loads(p.read_text()).get("problem"): p for p in (S.wt / S.root).glob("*/state.json")}
    rows = {r["name"]: r for r in S.rows}
    for n in names:
        d = froot / safe(n); d.mkdir(parents=True, exist_ok=True)
        spend = float(json.loads(main[n].read_text()).get("api_spend") or 0) if n in main else 0.0
        (d / "state.json").write_text(json.dumps({"problem": n, "best": {"score": 33.33, "proof": None, "tokens": rows[n]["proof_length"], "heartbeats": None},
                                                  "attempts": [], "runs": [], "api_spend": spend, "lineage": "fresh"}, ensure_ascii=False, indent=1))
        (d / "notes.md").write_text("# Notes (yours to keep; persisted across runs)\n")
    cmd = ["python3", "harness/agent.py", "--model-preset", preset, "--reasoning-effort", effort, "--turns", "40", "--no-adaptive-turns",
           "--max-tokens", "4000", "--budget-usd", str(rung), "--budget-milestones", "2.0", "--workers", str(workers),
           "--work-root", f"{S.root}-fresh", "--run-id", run_id, *(["--from-reference", "--brief", "restructure"] if restructure else []),
           *extra, "--problems", *names]
    with (S.out / f"{run_id}.log").open("a") as f:
        subprocess.run(cmd, cwd=S.wt, stdout=f, stderr=subprocess.STDOUT)
    for n in names:
        fs = froot / safe(n) / "state.json"
        if not fs.exists() or n not in main:
            continue
        r = json.loads(fs.read_text()); m = json.loads(main[n].read_text())
        added = float(r.get("api_spend") or 0) - float(m.get("api_spend") or 0)
        gain = (r["best"].get("score") or 0) > (m["best"].get("score") or 0)
        m["api_spend"] = max(float(m.get("api_spend") or 0), float(r.get("api_spend") or 0))   # seeded with main's spend: fresh = main + new
        if gain:
            m["best"] = r["best"]
        if r.get("budget_milestones"):
            m.setdefault("budget_milestones", {}).update({k: v for k, v in r["budget_milestones"].items() if k not in m.get("budget_milestones", {})})
        m.setdefault("fresh_lineages", []).append({"run_id": run_id, "spend": round(added, 6), "score": r["best"].get("score"), "adopted": gain,
                                                   "restructure": restructure, "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        main[n].write_text(json.dumps(m, ensure_ascii=False, indent=1))
        say(f"  fresh lineage ({'restructure' if restructure else 'restart'}): +${added:.3f}, {r['best'].get('score')} -> "
            f"{'ADOPTED' if gain else 'main best kept'}")
    froot.rename(S.wt / f"{S.root}-fresh.done-{run_id}")


def rounds(S: Set) -> list[pathlib.Path]:
    return sorted(S.wt.glob(f"probe/runs/{S.run_prefix}*"), key=lambda p: int(re.search(r"-r(\d+)$", p.name).group(1)))


def fresh_rounds(S: Set) -> list[pathlib.Path]:
    return sorted(S.wt.glob(f"probe/runs/{S.run_prefix[:-1]}f*"))


def _events(f: pathlib.Path):
    op = gzip.open if f.suffix == ".gz" else open
    with op(f, "rt") as h:
        for line in h:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "turn":
                yield e


def curve(S: Set, marks: list[float]) -> dict:
    """Best score reached by cumulative spend <= mark, per problem (numbers from turn events only)."""
    out = {}
    for n in S.names:
        spent, best, pts = 0.0, 33.33, []
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", n)   # agent.py's trajectory file name for problem n
        for rd in sorted(rounds(S) + fresh_rounds(S), key=lambda p: p.stat().st_mtime):
            for f in (rd / "trajectories" / f"{safe}.jsonl.gz", rd / "trajectories" / f"{safe}.jsonl"):
                if f.exists():
                    for e in _events(f):
                        spent += e.get("cost") or 0.0
                        best = max(best, e.get("best_so_far") or 33.33)
                        pts.append((spent, best))
        out[n] = {m: max([b for s, b in pts if s <= m] or [33.33]) for m in marks}
    return out


def ref_scores(S: Set) -> dict | None:
    if not S.ref_log:
        return None
    ref = {}
    for line in (MAIN / S.ref_log).read_text().splitlines():
        m = re.search(r"done  (\S+) rc=\d+ best=([0-9.]+)", line)
        if m:
            ref[m.group(1)] = float(m.group(2))
    return {n: ref.get(n, 33.33) for n in S.names}


def report(S: Set, arm: str, rung: float, say, title: str = "REPORT") -> None:
    st, F = states(S), ref_scores(S)
    marks = sorted({0.5, 1.0, 1.5, 2.0, 2.5, rung} | {m for m in (2.85,) if m <= rung})
    C = curve(S, [m for m in marks if m <= rung + 1e-9])
    sc = {n: st.get(n, {"score": 33.33})["score"] for n in S.names}
    sp = [st[n]["spend"] for n in S.names if n in st]
    ref = (f" (Flash cold 1-pass ref {statistics.mean(F.values()):.2f}; wins {sum(sc[n] > F[n] for n in S.names)}/{len(S.names)})" if F else "")
    say(f"{title} {S.prefix} arm {arm}, rung ${rung:.2f}: mean {statistics.mean(sc.values()):.2f} over {len(S.names)}{ref}")
    by = lambda key: {k: [sc[r['name']] for r in S.rows if str(key(r)) == k] for k in sorted({str(key(r)) for r in S.rows})}
    say("  " + "; ".join(f"{k} n={len(v)} {statistics.mean(v):.2f}" for k, v in {**by(lambda r: r.get('stratum')), **by(lambda r: r['source'])}.items() if v))
    if sp:
        say(f"  spend: total ${sum(sp):.2f}, mean ${statistics.mean(sp):.3f}, MAX ${max(sp):.3f} per problem (rung ${rung:.2f}; past $2: {sum(x >= 2.0 for x in sp)})")
    say("  score at budget: " + " · ".join(f"${m:.2f} {statistics.mean(C[n][m] for n in S.names):.2f}" for m in sorted(next(iter(C.values())))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="warmup", choices=sorted(SETS)); ap.add_argument("--arm", required=True)
    ap.add_argument("--preset", default="gpt-6.1-sol"); ap.add_argument("--effort", default="medium")
    ap.add_argument("--rungs", default="2.0,2.85", help="budget ladder: every problem is filled to a rung before any goes past it")
    ap.add_argument("--max-rounds", type=int, default=14); ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--ref", default="HEAD"); ap.add_argument("--report", action="store_true")
    ap.add_argument("--brief-dir", default=None, help="facts-only knowledge briefs (knowledge, never proofs), passed to every session")
    ap.add_argument("--stop-at", type=float, default=None, help="stop after the --stop-rung milestone if its mean is >= this")
    ap.add_argument("--stop-rung", type=float, default=2.0)
    ap.add_argument("--rescue", type=int, default=0, help="after the --rescue-rung milestone, one FRESH restructure session (empty work root: "
                    "no stored best, notes or variants; knowledge and tools only) for the K problems furthest below their target")
    ap.add_argument("--rescue-rung", type=float, default=2.0); ap.add_argument("--rescue-effort", default="high")
    ap.add_argument("--lineage-rule", action=argparse.BooleanOptionalAction, default=True, help="restart stuck or badly-drawn problems fresh")
    ap.add_argument("--max-fresh", type=int, default=2)
    a = ap.parse_args()
    S = Set(a.set, a.arm); S.out.mkdir(parents=True, exist_ok=True)
    rungs = [float(x) for x in a.rungs.split(",") if x.strip()]
    extra = ["--brief-dir", a.brief_dir] if a.brief_dir else []
    def say(msg: str) -> None:
        line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime())}] {msg}"
        print(line, flush=True); (S.out / "jobs.log").open("a").write(line + "\n")
    if a.report:
        report(S, a.arm, rungs[-1], say); return 0
    setup_worktree(S, subprocess.run(["git", "rev-parse", a.ref], cwd=MAIN, capture_output=True, text=True).stdout.strip(), say)
    # Lineage rule (2026-10-11: after a very poor start point, another fresh start may beat a resume;
    # data: a resumed 2nd session gains +0.89 on average and ~0.1-0.6 on stuck problems, while two independent first sessions
    # differ by ~2-4 points, so a second draw beats another resume on a stuck problem): after every round, a problem below its target by
    # >= 3 points restarts FRESH (empty workspace, max of the lineages kept) when its last session gained < 0.5 (stuck) or its first
    # session landed >= 4 below its typical first session (bad draw); at most 2 fresh restarts per problem, otherwise it resumes.
    T, T1 = targets(S), typical_first(S)
    lin_path = S.out / "lineage.json"
    lin = json.loads(lin_path.read_text()) if lin_path.exists() else {}
    def wants_fresh(n: str, best: float) -> bool:
        L = lin.get(n) or {}
        if not L.get("sessions") or L.get("fresh", 0) >= a.max_fresh or T[n] - best < 3.0:
            return False
        if L["sessions"] == 1 and n in T1 and best < T1[n] - 4.0:
            return True
        return L.get("last_gain") is not None and L["last_gain"] < 0.5
    r = len(rounds(S)) + len(fresh_rounds(S))
    for rung in rungs:
        while True:
            st = states(S)
            todo = [n for n in S.names if st.get(n, {"spend": 0.0})["spend"] + SESSION_FLOOR < rung]
            if not todo:
                break
            if r >= a.max_rounds:
                say(f"max rounds ({a.max_rounds}) reached on rung ${rung:.2f}; stopping"); report(S, a.arm, rung, say); return 1
            r += 1
            score = lambda n: st.get(n, {"score": 33.33})["score"]
            fresh = [n for n in todo if wants_fresh(n, score(n))] if a.lineage_rule else []
            resume = [n for n in todo if n not in fresh]
            say(f"round {r} (rung ${rung:.2f}): {len(resume)} resume, {len(fresh)} fresh restart (spent so far ${sum(v['spend'] for v in st.values()):.2f})")
            jobs = []
            if resume:
                run_id = f"{S.run_prefix}{r}"
                cmd = ["python3", "harness/agent.py", "--model-preset", a.preset, "--reasoning-effort", a.effort, "--turns", "40", "--no-adaptive-turns",
                       "--max-tokens", "4000", "--budget-usd", str(rung), "--budget-milestones", "2.0", "--workers", str(a.workers),
                       "--work-root", S.root, "--run-id", run_id, *extra, "--problems", *resume]
                def run_resume(cmd=cmd, run_id=run_id):
                    with (S.out / f"{run_id}.log").open("a") as f:
                        subprocess.run(cmd, cwd=S.wt, stdout=f, stderr=subprocess.STDOUT)
                jobs.append(run_resume)
            if fresh:
                fid = f"{S.run_prefix[:-1]}f{r}"
                jobs.append(lambda fid=fid: fresh_round(S, fresh, rung, fid, a.effort, False, extra, a.preset, max(1, min(a.workers, len(fresh))), say))
            with ThreadPoolExecutor(len(jobs)) as ex:
                list(ex.map(lambda j: j(), jobs))
            st2 = states(S)
            for n in todo:
                L = lin.setdefault(n, {"sessions": 0, "fresh": 0, "last_gain": None})
                L["sessions"] += 1; L["last_gain"] = round(st2.get(n, {"score": 33.33})["score"] - score(n), 3)
                L["fresh"] += n in fresh
                L.setdefault("gains", []).append([rung, L["last_gain"]])   # per-rung gain history for the rescue's stuck test
            lin_path.write_text(json.dumps(lin, indent=1))
            if sum(v["spend"] for v in st2.values()) <= sum(v["spend"] for v in st.values()) + 1e-6:
                logs = "".join((S.out / f).read_text() for f in [f"{S.run_prefix}{r}.log", f"{S.run_prefix[:-1]}f{r}.log"] if (S.out / f).exists())
                if logs.count("budget reached") >= len(todo):   # every session stopped before its first turn: the rung is full
                    say(f"round {r}: rung ${rung:.2f} full (every remaining session's first-turn worst case exceeds what is left)"); break
                say(f"round {r}: no spend recorded (API or key problem?); stopping"); return 1
            say(f"round {r} done: mean so far {statistics.mean(st2.get(n, {'score': 33.33})['score'] for n in S.names):.2f}")
        report(S, a.arm, rung, say, title=f"MILESTONE ${rung:.2f}")
        st = states(S)
        mean = statistics.mean(st.get(n, {"score": 33.33})["score"] for n in S.names)
        if a.stop_at is not None and abs(rung - a.stop_rung) < 1e-9 and mean >= a.stop_at:
            say(f"STOP RULE: mean {mean:.2f} >= {a.stop_at} at the ${rung:.2f} milestone; not climbing further"); break
        nxt = next((x for x in rungs if x > rung + 1e-9), None)
        if a.rescue and abs(rung - a.rescue_rung) < 1e-9 and nxt and not (S.out / "rescue.done").exists():
            cands = [n for n in S.names if nxt - st.get(n, {"spend": 0.0})["spend"] >= SESSION_FLOOR]
            # 2026-10-11 (warm-up: Electromagnetism climbed 33.33 -> 73.89 on this rung, yet was still furthest below target): a rescue is a
            # fresh draw for STUCK problems; one still climbing keeps resuming. Stuck = gained < 0.5 over the whole rung, not the last session:
            # a rung's trailing session is often a few turns long (the turn reserve fills what is left) and gains ~0 even on a climbing problem.
            rung_gain = lambda n: sum(g for rg, g in (lin.get(n) or {}).get("gains", []) if abs(rg - rung) < 1e-9 and g is not None)
            climbing = [n for n in cands if not (lin.get(n) or {}).get("gains") or rung_gain(n) >= 0.5]
            cands = [n for n in cands if n not in climbing]
            if climbing:
                say(f"RESCUE: {len(climbing)} candidate(s) skipped as not stuck (gained >= 0.5 on this rung, or no session yet)"
                    + (f": {', '.join(climbing)}" if S.prefix == "wu" else ""))
            pick = sorted(cands, key=lambda n: st.get(n, {"score": 33.33})["score"] - T[n])[: a.rescue]
            if pick:
                r += 1
                say(f"RESCUE: one fresh RESTRUCTURE session (empty workspace, effort {a.rescue_effort}) for {len(pick)} problems furthest below target")
                fresh_round(S, pick, nxt, f"{S.run_prefix[:-1]}f{r}", a.rescue_effort, True, extra, a.preset, len(pick), say)
                report(S, a.arm, rung, say, title="AFTER RESCUE")
            (S.out / "rescue.done").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    say("HELDOUT DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
