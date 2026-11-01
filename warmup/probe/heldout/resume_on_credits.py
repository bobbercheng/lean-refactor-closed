#!/usr/bin/env python3
"""Resume the warm-up Sol run once the OpenRouter account has credits again (2026-10-12 01:34: every round-14 request got HTTP 402,
nothing billed; the runner stopped as designed). Polls the account balance (credits - usage) every
--interval seconds; when it reaches --min-balance, relaunches the runner unit with the same arguments (no early stop rule:
run until the cap) and exits. Bounded by --max-hours. The key is read from disk and never printed.
"""
from __future__ import annotations

import argparse, json, pathlib, subprocess, time, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--key-file", default="~/.config/vexorium/oline-keys/openrouter_openai_gpt-6.1-sol.key")
ap.add_argument("--min-balance", type=float, default=12.0, help="the run needs at most ~$10.91 more (15 x $2.85 cap - $31.84 spent)")
ap.add_argument("--interval", type=int, default=300); ap.add_argument("--max-hours", type=float, default=12.0)
ap.add_argument("--jobs", default="probe/heldout/wu-hx-sol/jobs.log"); ap.add_argument("--unit", default="lra-hx-warmup")
ap.add_argument("runner", nargs=argparse.REMAINDER)
a = ap.parse_args()
cmd = [c for c in a.runner if c != "--"]
assert cmd and "--stop-at" not in cmd
key = pathlib.Path(a.key_file).expanduser().read_text().strip()
jobs = pathlib.Path(a.jobs)


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime())}] {msg}"
    print(line, flush=True); jobs.open("a").write(line + "\n")


def balance() -> float | None:
    try:
        req = urllib.request.Request("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {key}"})
        d = json.load(urllib.request.urlopen(req, timeout=30))["data"]
        return float(d["total_credits"]) - float(d["total_usage"])
    except Exception:  # noqa: BLE001
        return None


log(f"resume-on-credits armed: relaunches {a.unit} when the OpenRouter balance reaches ${a.min_balance:g} (every {a.interval} s, up to {a.max_hours:g} h)")
deadline = time.time() + a.max_hours * 3600
while time.time() < deadline:
    b = balance()
    if b is not None and b >= a.min_balance:
        subprocess.run(["systemctl", "--user", "reset-failed", a.unit], capture_output=True)
        subprocess.run(["systemd-run", "--user", "--unit", a.unit, "-p", "MemoryMax=48G", "-p", "MemoryHigh=44G",
                        f"--working-directory={pathlib.Path.cwd()}", "-E", "PATH", "-E", "HOME", *cmd], check=True)
        log(f"RESUMED: OpenRouter balance ${b:.2f}; relaunched {a.unit} (continues the $2.85 rung)"); break
    time.sleep(a.interval)
else:
    log(f"resume-on-credits: {a.max_hours:g} h limit reached without credits; exiting (the run stays paused at its last snapshot)")
