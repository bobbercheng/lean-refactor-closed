"""Heartbeat profile of a tactic proof: where the heartbeats go, block by block, and the floor (Tier 1, panel proposal R1).

Four panel analysts built the same tool by hand (on four dev rows): cut the proof after each top-level step,
close the rest with `all_goals sorry`, measure the declaration's heartbeats, and take differences. The floor is the statement with a `sorry` body:
H can never pass (1 - floor / reference) on that problem, so it tells the agent how many heartbeat points are really left.

    python3 harness/profile.py <problem> <candidate.lean> [--max-cuts 10] [--remainder off|label|bisect]

bet-profiler (D1 of docs/closed_plus5_per_problem.md): a sequence with more steps than the cuts left ends its measured blocks with one whose
cost is the total minus the last cut, i.e. that step AND every later sibling, while 1350c858 labels it with that one step's lines and text.
The switch LRA_BET_PROFILE_REMAINDER (or --remainder / profile(remainder=...)) picks what happens there; OFF is the default:
  off     (unset, "", "0", "off", anything unknown) the 1350c858 output, byte for byte
  label   the same cuts; that block is labelled with the whole stretch it measured: lines to the sequence's end, "[n steps] " before its
          text and "steps": n
  bisect  (also "1", "on", "true", "yes") the same NUMBER of cuts, placed by bisection: the first step, then each cut halves the costliest
          stretch of >= 2 steps; every step is in exactly one block, a stretch left uncut is labelled as in `label`
A sequence the cuts cover is profiled exactly as before in every mode (same cuts, same blocks); only the note gains one sentence, and only
when a grouped block is in the output.
"""
from __future__ import annotations

import json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "harness")]

REMAINDER_ENV = "LRA_BET_PROFILE_REMAINDER"   # bet-profiler switch (module docstring); unset = off
GROUP_NOTE = (" A block whose text starts with [n steps] is n consecutive sibling steps measured together (the cuts ran out before they "
              "could be measured one by one); its lines span all n.")


def remainder_mode(value: str | None = None) -> str | None:
    """The bet-profiler mode: "label", "bisect" or None (off, the default) from `value`, else from $LRA_BET_PROFILE_REMAINDER."""
    v = (os.environ.get(REMAINDER_ENV, "") if value is None else str(value)).strip().lower()
    return "label" if v == "label" else "bisect" if v in ("bisect", "1", "on", "true", "yes") else None


def _block(lines: list[str], seq: dict, lo: int, hi: int, heartbeats) -> dict:
    """One profiled block: the steps lo..hi-1 of `seq` (hi = len(steps): through the sequence's end). One step = 1350c858's block dict
    exactly; n >= 2 steps: "[n steps] " before the text and "steps": n."""
    st = seq["steps"]; k = st[lo]; nxt = st[hi] if hi < len(st) else seq["end"]
    text = " ".join(l.strip() for l in lines[k:nxt] if l.strip())
    b = {"lines": f"{k + 1}-{nxt}", "depth_indent": seq["indent"], "text": (text if hi - lo == 1 else f"[{hi - lo} steps] {text}")[:100],
         "heartbeats": heartbeats}
    if hi - lo > 1:
        b["steps"] = hi - lo
    return b


def _bisect(lines: list[str], seq: dict, budget: int, cut, total) -> tuple[list[dict], int]:
    """bisect mode for a sequence with more steps than `budget` (>= 1) cuts: cut the first step, then repeatedly halve the costliest stretch of
    >= 2 steps (a measured cost before an unmeasured one, then the wider, then the earlier) until the cuts run out. (blocks in step order,
    cuts left)."""
    n = len(seq["steps"]); hb = {0: cut(seq, 0), n: total}; budget -= 1; spans = [(0, n)]
    def cost(sp):
        a, b = hb.get(sp[0]), hb.get(sp[1])
        return (b - a) if (a is not None and b is not None) else None
    while budget > 0:
        wide = [sp for sp in spans if sp[1] - sp[0] > 1]
        if not wide:
            break
        sp = max(wide, key=lambda sp: (cost(sp) is not None, cost(sp) or 0, sp[1] - sp[0], -sp[0]))
        mid = (sp[0] + sp[1]) // 2
        hb[mid] = cut(seq, mid); budget -= 1
        i = spans.index(sp); spans[i:i + 1] = [(sp[0], mid), (mid, sp[1])]
    return [_block(lines, seq, lo, hi, cost((lo, hi))) for lo, hi in spans], budget


def _measure(row: dict, decl: str, version: str) -> int | None:
    from scorer.compile import compile_putnam, compile_project
    r = (compile_putnam(row["header"], decl, version, count=True, timeout=600) if row["source"] == "putnambench"
         else compile_project(row, decl, version, count=True, timeout=600))
    # 2026-10-18: every floor / suffix-cut probe closes goals with `sorry` on purpose, and the scorer (correctly, for scoring)
    # reports any sorry as an error - so `r.ok` was False for all of them and the profile silently measured nothing on
    # ~80% of rows. A probe whose ONLY errors are the sorry is a valid heartbeat measurement.
    only_sorry = bool(r.errors) and all("sorry" in e for e in r.errors)
    return r.heartbeats if (r.ok or only_sorry) and r.heartbeats is not None else None


def _sequences(lines: list[str], first: int) -> list[dict]:
    """Tactic sequences: runs of step-start lines at one indentation inside the same parent block. A step owns the following lines that are
    indented deeper; `|` arm lines at the same indentation belong to the step that opened them (`induction … with`); bullets and `case` are
    sibling steps. A suffix cut closes everything that remains with `all_goals sorry`."""
    def ind(l): return len(l) - len(l.lstrip(" "))
    body = [k for k in range(first, len(lines)) if lines[k].strip() and not lines[k].strip().startswith("--")]
    seqs, used = [], set()
    for k in body:
        if k in used:
            continue
        s = lines[k].strip()
        if s.startswith(("|", "<;>", ")", "]", ",")):
            continue
        d = ind(lines[k]); steps = [k]; used.add(k); m = k + 1
        while m < len(lines):
            if not lines[m].strip() or lines[m].strip().startswith("--"):
                m += 1; continue
            dm = ind(lines[m])
            if dm < d:
                break
            if dm == d:
                if lines[m].strip().startswith(("|", "<;>")):   # arms of `induction/cases/match … with` belong to the step that opened them
                    used.add(m); m += 1; continue
                steps.append(m); used.add(m)                    # bullets / `case` / `next` are sibling steps
            m += 1
        seqs.append({"indent": d, "steps": steps, "end": m})
    return seqs


def profile(name: str, decl: str, max_cuts: int = 12, remainder: str | None = None) -> dict:
    from mine import ROWS
    from probe.verify_candidates import newest_first
    from goals import instrument
    from scorer.score import local_reference_heartbeats
    row = ROWS[name]; primary = newest_first(row["version_info"])[0]
    stmt = row["statement"]
    if instrument(decl, stmt, 1) is None:
        return {"ok": False, "note": "term-mode proof (no `:= by` block): only the total and the floor are measured.",
                "total": _measure(row, decl, primary), "floor": _measure(row, stmt.rstrip() + " := by\n  sorry", primary)}
    lines = decl.split("\n")
    head_end = next(k for k, l in enumerate(lines) if re.search(r":=\s*by\s*$", l) or re.search(r":=\s*by\b", l))
    first = head_end + 1
    seqs = _sequences(lines, first)
    total = _measure(row, decl, primary)
    floor = _measure(row, stmt.rstrip() + " := by\n  sorry", primary)
    budget = max_cuts; costs = []
    def suffix_cost(seq, k_idx):
        k = seq["steps"][k_idx]
        cut = lines[:k] + [" " * seq["indent"] + "all_goals sorry"] + lines[seq["end"]:]
        return _measure(row, "\n".join(cut), primary)
    mode = remainder_mode(remainder)   # bet-profiler; None (off) = 1350c858
    todo = [min(seqs, key=lambda s: (s["indent"], s["steps"][0]))] if seqs else []
    while todo and budget > 0:
        seq = todo.pop(0)
        if mode == "bisect" and len(seq["steps"]) > budget:
            new, budget = _bisect(lines, seq, budget, suffix_cost, total)
            costs += new
        else:
            hs = []
            for k_idx in range(len(seq["steps"])):
                if budget <= 0:
                    break
                hs.append(suffix_cost(seq, k_idx)); budget -= 1
            hs.append(total if seq is not None else None)
            for k_idx in range(len(hs) - 1):
                a, b = hs[k_idx], hs[k_idx + 1]
                k = seq["steps"][k_idx]; nxt = seq["steps"][k_idx + 1] if k_idx + 1 < len(seq["steps"]) else seq["end"]
                costs.append({"lines": f"{k + 1}-{nxt}", "depth_indent": seq["indent"],
                              "text": " ".join(l.strip() for l in lines[k:nxt] if l.strip())[:100],
                              "heartbeats": (b - a) if (a is not None and b is not None) else None})
            if mode == "label" and len(hs) - 1 < len(seq["steps"]):   # the last block measured every step the cuts did not reach
                costs[-1] = _block(lines, seq, len(hs) - 2, len(seq["steps"]), costs[-1]["heartbeats"])
        # descend into the costliest step of this sequence if it has nested sequences
        mine = [c for c in costs if c["depth_indent"] == seq["indent"] and c["heartbeats"] is not None]
        if mine:
            top = max(mine, key=lambda c: c["heartbeats"]); a, b = (int(x) for x in top["lines"].split("-"))
            inner = [s for s in seqs if s["indent"] > seq["indent"] and a <= s["steps"][0] < b and len(s["steps"]) >= 1]
            if inner:
                todo.append(max(inner, key=lambda s: len(s["steps"])))
    ref = local_reference_heartbeats(name)
    out = {"ok": total is not None, "total": total, "floor": floor, "reference": ref,
           "max_heartbeat_score": round((1 - floor / ref) * 100 / 3, 2) if (floor and ref) else None,
           "blocks": sorted(costs, key=lambda c: -(c["heartbeats"] or 0))[:15]}
    if total is not None and floor is not None and ref:
        out["points_left_heartbeats"] = round((total - floor) / ref * 100 / 3, 2)
    out["note"] = ("each block's cost = heartbeats saved if it and its later siblings were `sorry` minus the same for the next sibling; nested blocks "
                   "are profiled under the costliest step. Costs include elaborating terms (notation, instance search). Odd values mean a cut changed elaboration.")
    if mode and any(c.get("steps") for c in out["blocks"]):
        out["note"] += GROUP_NOTE
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("problem"); ap.add_argument("file"); ap.add_argument("--max-cuts", type=int, default=10)
    ap.add_argument("--remainder", choices=["off", "label", "bisect"], default=None, help=f"bet-profiler mode (default ${REMAINDER_ENV}, unset = off)")
    a = ap.parse_args()
    print(json.dumps(profile(a.problem, Path(a.file).read_text(), a.max_cuts, a.remainder), ensure_ascii=False, indent=1))
