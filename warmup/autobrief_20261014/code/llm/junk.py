"""Junk detection for model output (2026-10-14; docs/warmup_clean_recheck.md).

Sol (GPT-6.1 via OpenRouter) sometimes degenerates inside a tool call's arguments: an endless whitespace run (`\\t\\t\\t \\n`), one short line
repeated hundreds of times, or `'''...' vs'''...` until the 12,000-token output cap (49 of 2,208 turns of the briefed warm-up run, $5.88 of
output = 18% of its spend; 19 turns in the first hour of the clean recheck). Measured on 2,084 trajectories (2026-10-14): every degenerate
junk call (113) is caught by `junk_reason`, at most 25% into the call (median 8%); 0 of 38,887 legitimate tool calls are flagged, and the
only legitimate-looking prefixes it flags (2 of 8,641 calls over 2,000 chars) were themselves junk content inside valid JSON.

Used by llm/openai_compat.py's stream guard (abort the generation as soon as junk appears: OpenRouter stops processing and billing on a
cancelled stream for OpenAI) and by harness/agent.py (never execute or re-send a junk call)."""
from __future__ import annotations

import re

MAX_ARG_CHARS = 60_000   # 2x the largest legitimate tool call measured (29,239 chars, lean_check_variants)
STEP = 1_000             # check points: every STEP chars of a growing text


def degenerate_tail(raw: str, window: int = 2000) -> bool:
    """True when `raw` ENDS in degenerate repetition (2026-10-11 warm-up Sol run: all 26 tool calls cut at the output cap were this:
    20 whitespace runs `\\t\\t\\t \\n` of varying length, 6 a short line like `\\n  all_goals sorry` repeated hundreds of times; no legitimate
    long write). Whitespace-only tail (escaped or not), or a unit of <= 40 chars repeated >= 20 times (<= 5% mismatches)."""
    tail = raw[-window:]
    if len(tail) < 200:
        return False
    if len(re.sub(r"(\\[tnr]|\s)+", "", tail)) < 0.1 * len(tail):
        return True
    return any(len(tail) >= 20 * k and sum(a != b for a, b in zip(tail, tail[k:])) <= 0.05 * (len(tail) - k) for k in range(1, 41))


def junk_reason(text: str, start: int = 0, max_chars: int = MAX_ARG_CHARS) -> str | None:
    """Why `text` (a tool call's raw arguments, or reply text) is junk, or None: over `max_chars`, or degenerate repetition at any check
    point (every STEP chars from `start`; a stream guard passes the last checked length so each check costs one window)."""
    if len(text) > max_chars:
        return f"{len(text)} chars of arguments (over {max_chars})"
    for i in range(max(STEP * (start // STEP + 1), 2 * STEP), len(text) + 1, STEP):
        if degenerate_tail(text[:i]):
            return f"degenerate repetition at char {i - 2 * STEP}-{i}: {text[max(0, i - 60):i]!r}"
    return None


class StreamGuard:
    """Incremental junk check over growing texts keyed by a slot (tool-call index, or 'content'): call `feed(slot, text)` with the full text
    so far after each chunk; returns the reason once the text is junk (then the caller aborts the stream), else None."""

    def __init__(self, max_chars: int = MAX_ARG_CHARS):
        self.max_chars, self.done = max_chars, {}

    def feed(self, slot, text: str) -> str | None:
        last = self.done.get(slot, 0)
        if len(text) - last < STEP and len(text) <= self.max_chars:
            return None
        self.done[slot] = len(text) - len(text) % STEP
        return junk_reason(text, start=last, max_chars=self.max_chars)
