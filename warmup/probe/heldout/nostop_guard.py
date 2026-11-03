#!/usr/bin/env python3
"""Keep a budget-ladder run climbing to its cap (2026-10-11, warm-up Sol run: climb to the cap). The runner
was launched with an early stop rule (--stop-at/--stop-rung) that can only fire at that rung's milestone, between rounds, when no
session is in flight. If it fires, relaunch the runner with the same arguments minus the stop rule: it resumes from its logs and
lineage, re-prints the milestone, runs the rescue and climbs the next rungs. Exits once the stop rung's milestone has passed without
a stop, after a relaunch, at the end of the run, or after --max-hours.
"""
from __future__ import annotations

import argparse, pathlib, subprocess, time

ap = argparse.ArgumentParser()
ap.add_argument("--jobs", default="probe/heldout/wu-hx-sol/jobs.log")
ap.add_argument("--unit", default="lra-hx-warmup")
ap.add_argument("--stop-rung", default="2.00")
ap.add_argument("--max-hours", type=float, default=6.0)
ap.add_argument("--memory-max", default="48G"); ap.add_argument("--memory-high", default="44G")
ap.add_argument("runner", nargs=argparse.REMAINDER, help="-- python3 harness/hx_heldout.py <args without --stop-at/--stop-rung>")
a = ap.parse_args()
cmd = [c for c in a.runner if c != "--"]
assert cmd and "--stop-at" not in cmd and "--stop-rung" not in cmd, "pass the runner command WITHOUT the stop rule"
jobs = pathlib.Path(a.jobs)


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime())}] {msg}"
    print(line, flush=True); jobs.open("a").write(line + "\n")


start = jobs.read_text().count("STOP RULE")
log(f"no-stop guard armed: relaunches {a.unit} without the stop rule if it fires at the ${a.stop_rung} milestone (up to {a.max_hours:g} h)")
deadline = time.time() + a.max_hours * 3600
while time.time() < deadline:
    txt = jobs.read_text()
    tail = txt[txt.rfind(f"MILESTONE ${a.stop_rung}"):] if f"MILESTONE ${a.stop_rung}" in txt else ""
    if txt.count("STOP RULE") > start:
        active = subprocess.run(["systemctl", "--user", "is-active", a.unit], capture_output=True, text=True).stdout.strip()
        if active in ("active", "activating"):
            time.sleep(5); continue   # the runner is still printing its report and exiting
        subprocess.run(["systemctl", "--user", "reset-failed", a.unit], capture_output=True)
        subprocess.run(["systemd-run", "--user", "--unit", a.unit, "-p", f"MemoryMax={a.memory_max}", "-p", f"MemoryHigh={a.memory_high}",
                        f"--working-directory={pathlib.Path.cwd()}", "-E", "PATH", "-E", "HOME", *cmd], check=True)
        log("RELAUNCH: the early stop rule fired; relaunched without it (run to the cap)"); break
    if tail and any(k in tail for k in ("RESCUE", "(rung $", "HELDOUT DONE")) and "STOP RULE" not in tail:
        log(f"no-stop guard: the ${a.stop_rung} milestone passed without an early stop; exiting"); break
    time.sleep(10)
else:
    log(f"no-stop guard: {a.max_hours:g} h limit reached; exiting")
