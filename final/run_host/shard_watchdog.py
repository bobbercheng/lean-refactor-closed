#!/usr/bin/env python3
"""Shard watchdog for a live closed official run (operations tool on the run host; not package code; 2026-11-02).

`run_final.py run` restarts an unfinished shard at most --max-restarts times (default 1), counted inside the launcher process. Closed run
3's shards s1 and s2 used theirs at launch (a start-up race on the shared .git/config), so a second crash overnight would leave half the
rows stopped. This watchdog brings back a shard that is unfinished and has stayed down DEAD_S seconds (the launcher's own restart comes
after 300 s, so the watchdog never races it), with the package's own run_final.launch() (the same run.sh, unit, memory caps, CPU weight
and runaway guard; the run.sh on disk is re-run unchanged; a restart resumes the run dir: each row's spend so far is kept, so the $3.00 cap holds). At most --max per shard,
at least --gap seconds apart. When every shard is done and the launcher unit has exited, it runs the package's merge
(`run_final.py merge --out OUT`) if any shard's submission.jsonl is newer than the merged one, so the upload file holds every shard's final
lines. It never acts after `run_final.py stop` (STOP_REQUESTED), on a refusal (exit 2), or on a done shard. Each action and each give-up is
a line "WATCHDOG ..." in OUT/logs/watchdog.log and a push to the private ntfy topic in --ntfy-file (if given).

    python3 shard_watchdog.py --co CHECKOUT --out OUT --launcher-unit lra-final3-launch [--ntfy-file F] [--dry] [--once]
"""
from __future__ import annotations
import argparse, calendar, os, subprocess, sys, time, urllib.request
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--co", required=True); ap.add_argument("--out", required=True); ap.add_argument("--launcher-unit", required=True)
ap.add_argument("--ntfy-file"); ap.add_argument("--label", default="")
ap.add_argument("--dead-s", type=float, default=900.0); ap.add_argument("--max", type=int, default=4); ap.add_argument("--gap", type=float, default=1200.0)
ap.add_argument("--poll", type=float, default=60.0); ap.add_argument("--deadline", default=None)
ap.add_argument("--dry", action="store_true"); ap.add_argument("--once", action="store_true")
a = ap.parse_args()
CO, OUT = Path(a.co).resolve(), Path(a.out).resolve()
sys.path.insert(0, str(CO / "infra/closed_package"))
import run_final as R  # noqa: E402  (the package's own launch / state functions)
# A restart re-runs the run.sh the launcher wrote, byte for byte: launch() would regenerate it from THIS process's PATH and
# sys.executable, which differ from the launcher's (final<N>.sh exports elan + miniconda first).
R.run_sh = lambda sh, plan: (Path(sh["run_dir"]) / "run.sh").read_text()

LOGF = OUT / "logs" / "watchdog.log"
NAME = a.label or OUT.name
TOPIC = Path(a.ntfy_file).read_text().strip() if a.ntfy_file and Path(a.ntfy_file).exists() else ""
deadline = calendar.timegm(time.strptime(a.deadline[:19], "%Y-%m-%dT%H:%M:%S")) if a.deadline else None


def log(msg: str, push: bool = False) -> None:
    line = f"[watchdog {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}] {msg}"
    print(line, flush=True)
    if not a.dry:
        with LOGF.open("a") as f:
            f.write(line + "\n")
    if push and TOPIC and not a.dry:
        try:
            urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{TOPIC}", data=f"{NAME}: {msg}"[:300].encode(),
                                                          headers={"Priority": "high", "Title": f"closed {NAME} watchdog"}), timeout=20)
        except Exception as e:  # noqa: BLE001
            print(f"ntfy failed: {type(e).__name__}", flush=True)


def launcher_active() -> bool:
    return R.unit_state(a.launcher_unit)["active"] in ("active", "activating", "deactivating", "reloading")


def mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def merge_if_stale(plan: dict) -> None:
    newest = max(mtime(Path(sh["run_dir"]) / "submission.jsonl") for sh in plan["shards"])
    if mtime(OUT / "submission.jsonl") >= newest:
        log("every shard done, the launcher exited and the merged submission.jsonl is current: nothing to do; watchdog exits")
        return
    if a.dry:
        log("DRY: would run run_final.py merge (a shard's submission.jsonl is newer than the merged file)"); return
    r = subprocess.run([sys.executable, "infra/closed_package/run_final.py", "merge", "--out", str(OUT)], cwd=CO, capture_output=True,
                       text=True, timeout=3600)
    tail = " | ".join(((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-2:])[:240]
    log(f"WATCHDOG MERGE rc={r.returncode} (every shard done after a watchdog restart; the launcher had exited): {tail}", push=True)


dead_since: dict = {}; count: dict = {}; last_act: dict = {}; gave_up: set = set(); refused: set = set()


def main() -> int:
    log(f"start: co {CO}, out {OUT}, launcher {a.launcher_unit}, dead {a.dead_s:g} s, max {a.max}/shard, gap {a.gap:g} s"
        + (" (DRY: no action)" if a.dry else ""))
    while True:
        plan = R.load_plan(OUT)
        if plan is None:
            log(f"no plan.json in {OUT}: exits"); return 2
        if (OUT / R.STOP_FILE).exists():
            log("STOP_REQUESTED present (run_final.py stop): the watchdog restarts nothing and exits"); return 0
        now, done_all = time.time(), True
        for sh in plan["shards"]:
            lab = sh["label"]
            if R.running(sh, plan):
                dead_since.pop(lab, None); done_all = False; continue
            done, why = R.shard_done(sh)
            if done:
                dead_since.pop(lab, None); continue
            done_all = False
            rc = R.last_exit(sh)
            if rc in R.NO_RESTART_RC:
                if lab not in refused:
                    refused.add(lab); log(f"WATCHDOG shard {lab}: ended with a refusal ({why}); not restarted, needs a person", push=True)
                continue
            t0 = dead_since.setdefault(lab, now)
            down = now - t0
            if down < a.dead_s:
                continue
            if count.get(lab, 0) >= a.max:
                if lab not in gave_up:
                    gave_up.add(lab); log(f"WATCHDOG shard {lab}: still down ({why}) after {a.max} watchdog restarts: GIVING UP, needs a person", push=True)
                continue
            if now - last_act.get(lab, 0) < a.gap:
                continue
            n = count.get(lab, 0) + 1
            if a.dry:
                log(f"DRY: would restart shard {lab} ({why}; down {down / 60:.0f} min; launcher {'active' if launcher_active() else 'exited'})")
                continue
            ok = R.launch(sh, plan, lambda m: log("run_final: " + m))
            count[lab], last_act[lab] = n, now; dead_since.pop(lab, None)
            log(f"WATCHDOG RESTART shard {lab} {n}/{a.max}: it was down {down / 60:.0f} min ({why}); launcher "
                f"{'active' if launcher_active() else 'exited'}; launch {'ok' if ok else 'FAILED'}", push=True)
        if done_all and not launcher_active():
            merge_if_stale(plan); return 0
        if a.once:
            return 0
        if deadline and time.time() > deadline:
            log("deadline passed: watchdog exits"); return 0
        time.sleep(a.poll)


if __name__ == "__main__":
    while True:   # a cycle that raises (a file read mid-write, a systemctl hiccup) is logged and the watch goes on
        try:
            sys.exit(main())
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"cycle error {type(e).__name__}: {str(e)[:200]}; retrying in 120 s (restart counts kept)")
            time.sleep(120)
