"""b65-final (audit C3, decided 2026-10-27 under the no-harm rule: a stopped, failed or over-cap LLM request must not harm the run
or its results): when an OpenRouter max_price pin error is CONFIRMED.

A pinned preset's 404 "No endpoints found that satisfy the max price" or 503 "No allowed providers", answered before any data, is $0
(agent.maybe_billed False) and NOT fatal on first sight: a short outage of the in-pin providers reads the same (b65-cap made it fatal at once;
the adversarial pass, docs/b65_failure_audit.md C3, showed one transient error then stopped the whole run with no output). It is CONFIRMED
only when the same pin error (one preset) is seen
  - on >= PIN_ROWS (2) different rows within PIN_WINDOW_S (the 404 only: ROWS_RULE_SKIP), or
  - >= PIN_TRIES (3) times on one row with no answer in between, spread over >= PIN_WINDOW_S (10 min), PIN_BACKOFF_S apart ($0 each).
Review 2026-10-27 (builder's open issue 1; audit T1 "503 for 10 minutes, then 200" must not stop the run): with 15 sessions in flight one
short "No allowed providers" blip reaches 2 rows within seconds, and the 2-row rule then ended every paid step of the run for good. The
404 "No endpoints found that satisfy the max price" is OpenRouter's endpoint catalog (the live check's answer to a pin below the price), so
2 rows confirm it; a 503 (an outage of the in-pin providers reads the same) confirms only by one row's streak (>= 10 min of errors).
A confirmation (and a PIN_MARKER file) expires after PIN_WINDOW_S: the next call is sent again (a re-probe); a re-probe that fails again
re-confirms at once, one that is answered clears it. An ANSWER of the preset (any row) lifts the pin errors seen before it: a flapping pin
(some endpoints in the pin answer) is never confirmed, each error is $0 and retried (in-process: PinWatch.clear; across the async
ladder's processes: an "answered" line in pin_events.jsonl, which rows_rule reads).
Used by agent.py (one process: its sessions' threads; pin_events.jsonl in its run dir), hx_heldout.py (across the async ladder's processes,
from those files; it writes PIN_MARKER into the in-flight sessions' run dirs) and review.py (the router's review calls). No heavy imports:
hx_heldout's scheduler imports it. LRA_PIN_WINDOW_S / LRA_PIN_BACKOFF_S exist for the tests (selftest, fake servers) only.
b66 (retro A3, preset fallback; docs/b66_robust.md): a confirmation is per PRESET. A marker names its preset and ends only that preset's
sessions (marker_fresh(preset=)): after the router moved a pinned preset's rungs to another preset of the run, a fresh marker of the pinned
one in a reused async run dir must not end the other preset's sessions. hx_heldout hands the preset on with the message (PinMsg); the router
asks confirmed() whether a candidate preset's own errors already confirm it before it falls back to it.
"""
from __future__ import annotations

import json, os, threading, time
from pathlib import Path

PIN_WINDOW_S = float(os.environ.get("LRA_PIN_WINDOW_S") or 600)    # confirmation spread on one row, the 2-row window, and the expiry
PIN_BACKOFF_S = float(os.environ.get("LRA_PIN_BACKOFF_S") or 300)  # between two tries of one call after a pin error ($0 each)
PIN_ROWS, PIN_TRIES = 2, 3
PIN_FATAL_RC = 78                    # sysexits EX_CONFIG: agent.py / hx_heldout / the router after a CONFIRMED pin (outputs complete)
PIN_MARKER = "pin_unservable.json"   # a confirmation, in a run dir (probe/runs/<run id>/, writable from the ladder's containers)
PIN_EVENTS = "pin_events.jsonl"      # every pin error a session saw (one line each: preset, row, t, status, message)
ROWS_RULE_SKIP = (503,)              # review 2026-10-27: statuses the 2-row rule does not count (a 503 may be a short outage: streak only)


def _now(now):
    return time.time() if now is None else float(now)


def _on_rows(e) -> bool:
    """An error the 2-row rule counts: not a ROWS_RULE_SKIP status (review 2026-10-27; an unknown status counts)."""
    try:
        return int(e.get("status")) not in ROWS_RULE_SKIP
    except (TypeError, ValueError):
        return True


def rows_rule(events, now=None) -> dict | None:
    """Rule 1: {"preset", "rows", "message", "why"} when one preset's pin error was seen on >= PIN_ROWS rows within PIN_WINDOW_S of `now`
    and after the preset's last answer (an "answered" event). Review 2026-10-27: a 503 (ROWS_RULE_SKIP) is not counted here."""
    now = _now(now)
    ans: dict = {}
    for e in events:
        try:
            if e.get("kind") == "answered":
                ans[e["preset"]] = max(ans.get(e["preset"], 0.0), float(e["t"]))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    by: dict = {}
    for e in events:
        try:
            if e.get("kind", "error") == "error" and _on_rows(e) and now - float(e["t"]) <= PIN_WINDOW_S and float(e["t"]) > ans.get(e["preset"], -1.0):
                by.setdefault(e["preset"], {})[e["row"]] = e
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    for preset, rows in sorted(by.items()):
        if len(rows) >= PIN_ROWS:
            last = max(rows.values(), key=lambda e: float(e["t"]))
            return {"preset": preset, "rows": sorted(rows), "message": last.get("message") or "",
                    "why": f"seen on {len(rows)} rows within {PIN_WINDOW_S / 60:g} min"}
    return None


def streak_rule(times) -> str | None:
    """Rule 2: the why when one row's pin-error times (no answer in between) are >= PIN_TRIES spread over >= PIN_WINDOW_S."""
    if len(times) >= PIN_TRIES and times[-1] - times[0] >= PIN_WINDOW_S:
        return f"{len(times)} tries on one row over {(times[-1] - times[0]) / 60:.1f} min"
    return None


class PinWatch:
    """One process's pin errors (thread-safe): observe() each one, clear() on an answer, dead() while a confirmation is fresh."""

    def __init__(self):
        self.lock = threading.Lock()
        self.events: list = []      # {"preset", "row", "t", "message", "status"}
        self.streak: dict = {}      # (preset, row) -> times of its pin errors since its last answer
        self.confirmed: dict = {}   # preset -> {"message", "t", "why", "rows"} (the latest confirmation; fresh for PIN_WINDOW_S)
        self.history: list = []     # every confirmation of this process (the router's summary.json)
        self.skipped: dict = {}     # preset -> rows whose call was not sent or failed for good on a confirmed pin
        self.ans_written: dict = {}  # (run dir, preset) -> pin_events.jsonl mtime after this process's last "answered" line there

    def observe(self, preset: str, row: str, message: str, now=None, status=None) -> str | None:
        """One pin error ($0; `status` its HTTP status: a 503 counts for the streak only). Returns the CONFIRMED message (and records it)
        when this error confirms the pin, else None."""
        now = _now(now)
        with self.lock:
            self.events = [e for e in self.events if now - e["t"] <= PIN_WINDOW_S] + [{"preset": preset, "row": row, "t": now, "message": message,
                                                                                        "status": status}]
            st = self.streak.setdefault((preset, row), [])
            st.append(now)
            why = None
            if preset in self.confirmed:   # confirmed before and expired since (a fresh one is never sent): the re-probe failed again
                why = "the re-probe after an expired confirmation failed again"
            else:
                r1 = rows_rule([e for e in self.events if e["preset"] == preset], now)
                why = r1["why"] if r1 else streak_rule(st)
            if not why:
                return None
            rows = sorted({e["row"] for e in self.events if e["preset"] == preset} | {row})
            full = f"CONFIRMED ({why}): {message}"
            self.confirmed[preset] = {"message": full, "t": now, "why": why, "rows": rows}
            self.history.append({"preset": preset, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "why": why, "rows": len(rows),
                                 "message": full[:300]})
            return full

    def clear(self, preset: str, row: str) -> bool:
        """An answer after this row's pin errors: the row's streak ends, the preset's earlier errors (every row) no longer count and a
        confirmation of the preset (an expired one being re-probed) is lifted. True if one was."""
        with self.lock:
            self.streak.pop((preset, row), None)
            self.events = [e for e in self.events if e["preset"] != preset]
            return self.confirmed.pop(preset, None) is not None

    def pending(self, preset: str, row: str | None = None) -> bool:
        """True while this process holds pin errors of the preset (of this row, when given) that an answer would lift (cheap: no lock)."""
        if row is not None and (preset, row) in self.streak:
            return True
        return any(e["preset"] == preset for e in self.events) or preset in self.confirmed

    def answered(self, preset: str, row: str, run_dir=None) -> bool:
        """One answered call of the preset: lifts this process's pin errors of it (clear) and, when the run dir's pin_events.jsonl changed
        since this process last wrote an answer there, appends an "answered" line (other processes' errors before it stop counting: one stat
        per turn, one line per burst of errors). True when this row had pin errors (the caller logs it)."""
        had = (preset, row) in self.streak
        if self.pending(preset, row):
            self.clear(preset, row)
        if run_dir is None:
            return had
        p = Path(run_dir) / PIN_EVENTS
        try:
            mt = p.stat().st_mtime
        except OSError:
            return had
        key = (str(run_dir), preset)
        if mt > self.ans_written.get(key, 0.0):
            append_event(run_dir, preset, row, None, "answered", kind="answered")
            try:
                self.ans_written[key] = p.stat().st_mtime
            except OSError:
                pass
        return had

    def dead(self, preset: str, now=None) -> str | None:
        """The confirmation message while it is fresh (no request is sent), None once it expired (the next call re-probes)."""
        now = _now(now)
        with self.lock:
            c = self.confirmed.get(preset)
            return c["message"] if c and now - c["t"] < PIN_WINDOW_S else None

    def skip(self, preset: str, row: str) -> None:
        with self.lock:
            self.skipped.setdefault(preset, set()).add(row)

    def reset(self) -> None:   # tests
        with self.lock:
            self.events, self.streak, self.confirmed, self.history, self.skipped, self.ans_written = [], {}, {}, [], {}, {}


def wait_backoff(seconds: float, stop=None, poll: float = 5.0) -> bool:
    """Sleep `seconds` (bounded), polling stop() every `poll` s; True as soon as stop() is true (a confirmation from elsewhere)."""
    end = time.time() + max(0.0, seconds)
    while True:
        if stop is not None and stop():
            return True
        left = end - time.time()
        if left <= 0:
            return False
        time.sleep(min(poll, left))


def marker_fresh(run_dir: Path, now=None, preset: str | None = None) -> str | None:
    """The message of a PIN_MARKER in `run_dir` younger than PIN_WINDOW_S, else None (an expired marker is a re-probe, not a stop). b66
    (A3): with `preset`, a marker that names ANOTHER preset is not this preset's stop (None); a marker without a preset (written before
    b66, or by a writer that did not know it) still stops every session, as before."""
    p = Path(run_dir) / PIN_MARKER
    try:
        if _now(now) - p.stat().st_mtime < PIN_WINDOW_S:
            j = json.loads(p.read_text())
            if preset and j.get("preset") and j.get("preset") != preset:
                return None
            return j.get("message") or str(p)
    except (OSError, ValueError, AttributeError):
        pass
    return None


class PinMsg(str):
    """b66 (A3): a confirmation message that carries its preset (hx_heldout.pin_stop -> pin_out -> the ladder's out-dir marker, where the
    router reads which preset to fall back from). A str everywhere else, as before."""
    preset = ""


def pin_msg(msg: str, preset: str | None) -> PinMsg:
    m = PinMsg(msg)
    m.preset = preset or getattr(msg, "preset", "") or ""
    return m


def confirmed(events, preset: str, now=None) -> str | None:
    """b66 (A3): the why when these pin_events.jsonl lines alone already confirm `preset` (rows_rule, or one row's streak with no answer
    after it, each within PIN_WINDOW_S of `now`), else None: what the router asks before it moves a pinned preset's rungs to this one."""
    now = _now(now)
    ev = [e for e in events if isinstance(e, dict) and e.get("preset") == preset]
    hit = rows_rule(ev, now)
    if hit:
        return hit["why"]
    last_ans = max([float(e.get("t") or 0) for e in ev if e.get("kind") == "answered"] or [-1.0])
    by: dict = {}
    for e in ev:
        try:
            t = float(e["t"])
            if e.get("kind", "error") == "error" and t > last_ans and now - t <= 2 * PIN_WINDOW_S:
                by.setdefault(e.get("row"), []).append(t)
        except (KeyError, TypeError, ValueError):
            continue
    for ts in by.values():
        why = streak_rule(sorted(ts))
        if why:
            return why
    return None


def write_marker(run_dir: Path, preset: str, message: str, pin=None, why: str | None = None, rows=None) -> None:
    """A confirmation into a run dir (atomic): agent.py after its own, hx_heldout into every in-flight session's dir after a cross-row one."""
    try:
        p = Path(run_dir); p.mkdir(parents=True, exist_ok=True)
        tmp = p / f".{PIN_MARKER}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps({"preset": preset, "pin": pin, "message": message, "why": why, "rows": rows,
                                   "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=1) + "\n")
        os.replace(tmp, p / PIN_MARKER)
    except OSError:
        pass


def append_event(run_dir: Path, preset: str, row: str, status, message: str, now=None, kind: str = "error") -> None:
    """One pin error (kind "error") or an answer after pin errors (kind "answered": rows_rule drops the preset's earlier errors) into
    <run dir>/pin_events.jsonl (one short line, O_APPEND: whole lines across the async ladder's processes)."""
    try:
        line = json.dumps({"preset": preset, "row": row, "t": _now(now), "status": status, "message": message[:300], "kind": kind}) + "\n"
        fd = os.open(Path(run_dir) / PIN_EVENTS, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line.encode())
        finally:
            os.close(fd)
    except OSError:
        pass


def read_events(run_dirs, since: float = 0.0) -> list:
    """Every readable pin_events.jsonl line at or after `since` in these run dirs (a torn line is skipped)."""
    out = []
    for d in run_dirs:
        try:
            lines = (Path(d) / PIN_EVENTS).read_text(errors="replace").splitlines()
        except OSError:
            continue
        for l in lines:
            try:
                e = json.loads(l)
                if float(e.get("t") or 0) >= since:
                    out.append(e)
            except (ValueError, TypeError, AttributeError):
                continue
    return out
