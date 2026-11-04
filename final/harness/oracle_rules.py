#!/usr/bin/env python3
"""Lean-oracle candidate family (2026-10-17): Lean's own
library search as a deterministic, $0 candidate generator. For every proof suffix (the last k top-level statements, k = 1..n) and every
nested `by` block, a probe replaces the span by `exact?`; when Lean answers "Try this: exact <term>", the span becomes `exact <term>`
and the candidate goes through the usual gate (primary compile, score margin, every toolchain with Z unchanged). This is where the
union's library wins live (one Mathlib characterization or one projection lemma per row):
a found lemma closes a goal in one term that a tactic suffix spent many tokens and heartbeats on.
Probes are ordinary compiles through the injected evaluator (`evaluate_fn(decl, False)` must return the compiler `messages`, as
harness/hb_tool_eval.Evaluator does); `oracle_candidates(evaluate_fn, max_probes)` returns a candidate function for
harness/postpass.rule_search, so gating, budgets and regeneration are shared. Knows no declarations, problems or lemma names.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.gap_rules import Body, Rule, _stmts  # noqa: E402
from scorer.tokenize import count_tokens  # noqa: E402

TRY_THIS = re.compile(r"^Try (?:this|these):\s*(?:\[apply\]\s*)?", re.S)
PROBE = "exact?"


def sites(body: str) -> list[dict]:
    """Spans to probe: {start, end, indent, label}; suffixes from the shortest (cheap, likely) to the whole proof, then nested `by`
    blocks largest first."""
    B = Body(body)
    if B.fb < 0 or B.first is None:
        return []
    out = []
    stmts = [s for s in B.top_stmts() if B.tactic(B.lines[s[0]])]
    n = len(stmts)
    for k in range(1, n + 1):
        h, l = stmts[n - k][0], stmts[-1][1]
        s, e = B.lines[h].start + B.lines[h].indent, B.lines[l].end
        out.append({"start": s, "end": e, "indent": B.top, "label": "whole proof" if k == n else f"last {k}"})
    nested = []
    for ln in B.lines:
        if not ln.code or not ln.code.endswith("by") or ln.idx + 1 >= len(B.lines) or B.mask[ln.end - 1] or ln.start < B.fb:
            continue
        nxt = next((x for x in B.lines[ln.idx + 1:] if x.code), None)
        if nxt is None or nxt.indent <= ln.indent or B.in_conv(nxt):
            continue
        blk = _stmts(B.lines, nxt.idx, len(B.lines), nxt.indent)
        if not blk:
            continue
        s, e = B.lines[blk[0][0]].start + nxt.indent, B.lines[blk[-1][1]].end
        if any(o["start"] == s and o["end"] == e for o in out):
            continue
        nested.append({"start": s, "end": e, "indent": nxt.indent, "label": f"by-block at line {ln.idx + 1}"})
    nested.sort(key=lambda o: -(o["end"] - o["start"]))
    return out + nested


def suggestion(messages) -> str | None:
    """The term of the first "Try this: exact <term>" message, else None."""
    for m in messages or []:
        d = str(m.get("data", ""))
        if not TRY_THIS.match(d):
            continue
        t = TRY_THIS.sub("", d, count=1).strip().split("\n\n")[0].strip()
        if t.startswith("exact "):
            return re.sub(r"\s*\n\s*", " ", t[len("exact "):]).strip()
    return None


def oracle_candidates(evaluate_fn, max_probes: int = 12, log=None, statement: str | None = None):
    """A candidate function for rule_search: probes each site once per body (memoised), spends at most `max_probes` probe compiles in
    total, and yields a Rule per suggestion whose text is not longer than the span it replaces."""
    state = {"probes": 0, "memo": {}}

    def candidates(body: str) -> list[Rule]:
        out = []
        for st in sites(body):
            if state["probes"] >= max_probes:
                break
            probe = body[:st["start"]] + PROBE + body[st["end"]:]
            key = probe   # the same probe text recurs across bodies (a suffix probe equals the whole-proof probe of the shortened body)
            if key in state["memo"]:
                term = state["memo"][key]
            else:
                state["probes"] += 1
                try:
                    r = evaluate_fn(statement + " :=" + probe if statement else probe, False)
                except Exception as e:  # noqa: BLE001
                    r = {"error": f"{type(e).__name__}: {e}"}
                term = suggestion(r.get("messages"))
                state["memo"][key] = term
                if log:
                    log(f"  oracle probe {st['label']}: " + (f"exact {term[:60]}" if term else (r.get("error") or "no suggestion")[:80]))
            if not term:
                continue
            rep = "exact " + term
            span = body[st["start"]:st["end"]]
            saved = count_tokens(span) - count_tokens(rep)
            if saved < 0:
                continue
            out.append(Rule("oracle-exact", ((st["start"], st["end"] - st["start"], rep),), f"{st['label']} -> exact {term[:50]}", saved))
        out.sort(key=lambda r: -r.priority)
        return out
    candidates.state = state
    return candidates
