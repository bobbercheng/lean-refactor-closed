"""Paired, unrounded acceptance rule (B62b/B62c; docs/scaffold_panel.md "Agreed" and "Rulings").

Both sides are measured back to back on one meter in the same run, and compared unrounded, never against a stored or 2-decimal score
(score.problem_score rounds to 2 decimals, so a gain under 0.01 is invisible there). A candidate is banked when
  - it compiles on at least the incumbent's toolchains (Z not lower), and
  - it compiles on more toolchains (a Z gain) and scores higher, or
  - it saves at least 1 token or HB_EPS heartbeats (a smaller heartbeat-only change is within the meter's run-to-run spread, whatever it is
    worth in points: on a row with a small reference one heartbeat unit can be worth more than SMALL; review 2026-10-21) and either
    dominates (no more tokens, no more heartbeats, a higher exact score) or gains >= MIN_GAIN exact points.
Heartbeat-only gains need a fresh confirmation compile (the caller re-measures and passes the worse of the two readings).
Router checkpoints keep their own 0.05 signal bar (SIGNAL_GAIN); this rule is for golf sessions and the end stage only.
"""
from __future__ import annotations

MIN_GAIN = 0.005     # exact points
SMALL = 0.01         # (no longer a branch of decide: since the 2026-10-21 review every bank saves a token or HB_EPS heartbeats)
HB_EPS = 3           # heartbeats: the meter's repeat spread is <= 2 on >= 95% of rows (Rung 1 noise floor)
SIGNAL_GAIN = 0.05   # router checkpoint bar (unchanged)


def exact_score(L: float, H: float, Z: float) -> float:
    """The official per-problem score before rounding: mean of the length, heartbeat and compatibility percentages."""
    return (L + H + Z) / 3.0


def decide(inc: dict, cand: dict) -> tuple[bool, str]:
    """inc, cand: {"score": exact score, "tokens": int, "heartbeats": int, "Z": percent}. Returns (bank it, reason)."""
    if cand.get("score") is None or inc.get("score") is None:
        return False, "no score"
    if float(cand.get("Z", 100.0)) < float(inc.get("Z", 100.0)):
        return False, "compiles on fewer toolchains"
    d = float(cand["score"]) - float(inc["score"])
    dt = int(inc.get("tokens") or 0) - int(cand.get("tokens") or 0)
    dh = int(inc.get("heartbeats") or 0) - int(cand.get("heartbeats") or 0)
    if float(cand.get("Z", 100.0)) > float(inc.get("Z", 100.0)) and d > 0:
        return True, f"{d:+.4f} (compiles on more toolchains)"
    if not (dt >= 1 or dh >= HB_EPS):
        return False, f"{d:+.4f}: saves no token and fewer than {HB_EPS} heartbeats (within the meter's spread)"
    if d > 0 and dt >= 0 and dh >= 0:
        return True, f"dominates ({dt:+d} tokens, {dh:+d} heartbeats saved, {d:+.4f})"
    if d >= MIN_GAIN:
        return True, f"{d:+.4f} ({dt:+d} tokens, {dh:+d} heartbeats saved)"
    return False, f"{d:+.4f} is below the bar (+{MIN_GAIN})"
