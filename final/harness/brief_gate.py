#!/usr/bin/env python3
"""Pipelined auto-brief gate (2026-10-22, docs/speed_review.md item 7; hx_heldout.py --auto-brief-pipeline, agent.py --auto-brief-wait).

Without the pipeline the ladder runs harness/autobrief.py over every row before any session, so every session waits for the slowest
row's brief. With it, the brief runs in the background and one agent.py batch starts at once; this gate decides when each row's
session may start inside that batch:
  - a row starts when its own brief JSON (<brief dir>/<ws>.json) exists; rows whose brief is ready go first, in the batch's row order;
  - when the brief process has ended (finished, timed out or stopped: the ladder then writes <brief dir>/ENDED), every remaining row may
    start, without a brief when it has none (agent.py then says "auto-brief: none for this row", as after today's timeout);
  - every wait is bounded: after `wait_s` seconds (the brief's own timeout plus a grace, passed by the ladder) the remaining rows start
    even if no marker came (a ladder that died never writes it);
  - at most `workers` sessions at once, and never two sessions of the same row at once.
harness/autobrief.py writes each row's JSON atomically (temp file + rename), so an existing JSON is a complete one."""
from __future__ import annotations

import re, time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

ENDED = ".brief_ended"   # written by the ladder (hx_heldout.AutoBrief) once the brief process has ended; existence is the signal
POLL_S = 5.0             # seconds between checks while no session can start (a few stat calls per check)


def safe(n: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", n)   # agent.py's / autobrief.py's work-dir and brief file name for row n


def brief_json(brief_dir, name: str) -> Path:
    return Path(brief_dir) / f"{safe(name)}.json"


def _print(msg: str) -> None:
    print(msg, flush=True)


def run_gated(names: list, workers: int, fn, brief_dir, wait_s: float, *, poll_s: float | None = None, log=_print,
              clock=time.monotonic, sleep=time.sleep) -> list:
    """fn(name) for every entry of `names` under the gate above; the results in `names` order (as ThreadPoolExecutor.map gives them).
    An exception in one row does not stop the others; the first one (in `names` order) is raised after every row has run."""
    d, workers = Path(brief_dir), max(1, int(workers))
    poll_s = POLL_S if poll_s is None else poll_s
    t0 = clock(); deadline = t0 + max(0.0, float(wait_s))
    pending = list(range(len(names)))
    running: dict = {}                   # future -> index into names
    results: list = [None] * len(names); errors: dict = {}
    ready0 = sum(brief_json(d, n).exists() for n in names)
    log(f"auto-brief gate: {ready0} of {len(names)} row(s) have their brief; the others start as theirs arrive or the brief process "
        f"ends (at most {float(wait_s):.0f}s), at most {workers} at once")
    with ThreadPoolExecutor(workers) as ex:
        while pending or running:
            while pending and len(running) < workers:
                busy = {names[i] for i in running.values()}
                free = [i for i in pending if names[i] not in busy]
                pick = next((i for i in free if brief_json(d, names[i]).exists()), None)
                why = "brief ready"
                if pick is None and free:
                    if (d / ENDED).exists():
                        pick, why = free[0], "the brief process ended without this row's brief"
                    elif clock() >= deadline:
                        pick, why = free[0], f"wait bound of {float(wait_s):.0f}s reached without this row's brief"
                if pick is None:
                    break
                pending.remove(pick)
                n = names[pick]
                log(f"{n[:18]:18s} auto-brief gate: session starts after {clock() - t0:.0f}s ({why})")
                running[ex.submit(fn, n)] = pick
            if running:
                done, _ = wait(list(running), timeout=poll_s, return_when=FIRST_COMPLETED)
                for f in done:
                    i = running.pop(f)
                    try:
                        results[i] = f.result()
                    except Exception as e:  # noqa: BLE001  (raised after every row ran, as ex.map would after its batch)
                        errors[i] = e
            elif pending:
                sleep(poll_s)
    if errors:
        raise errors[min(errors)]
    return results
