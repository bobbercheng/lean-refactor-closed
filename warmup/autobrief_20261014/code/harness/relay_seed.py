#!/usr/bin/env python3
"""Relay seeds for the closed lines (2026-10-10; docs/break_90_panel.md item 3).
The two closed lines golfed in isolation and never saw each other's tricks; after pass 3, 25 sessions that polished a lagging basin
gained 0 union points while 35 frontier sessions gained 27 times. A relay round seeds every session with the UNION BEST of its problem.
For each problem this writes, under OUT (default probe/relay/r1):
  <problem>.lean  the union best: the best compiling proof over the Opus 5.5 line, the GPT Astra line, the Flash bank, the normalizer's
                  union outputs (probe/normalize/union.jsonl) and the bounty compile (probe/bounty/results.jsonl);
  <problem>.md    a cross-line digest: provenance, each line's best, the exchange rate (points per token and per 100 heartbeats), the
                  tail of each line's notes (their tested and failed lists), the ceiling review's levers, and the lexer rules.
and prints the schedule (problems per line). Closed-model content stays in the closed lines; nothing enters the bank.
  python3 harness/relay_seed.py [--out probe/relay/r1] [--problems ...]       prints "opus: ..." and "astra: ..."
"""
from __future__ import annotations

import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.leantools import ROWS, HBS  # noqa: E402

SP = Path("/tmp/claude-scratch")   # a development scratch directory (not shipped)
REVIEW = SP / "tasks/ww79r5gs4.output"
SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def candidates(name: str) -> list[dict]:
    out = []
    for line, prefix in (("Opus 5.5 line", "ccline-opus55"), ("GPT Astra line", "cxline-astra")):
        for f in sorted((ROOT / "probe/runs").glob(f"{prefix}-*/verified.jsonl")):   # every run of the line: passes, relay, census, fresh, bounty, normalize
            for l in f.open():
                r = json.loads(l)
                if r["problem"] == name and r.get("primary_ok"):
                    out.append({"source": line, "run": f.parent.name, "score": r["score"], "tokens": r.get("tokens"), "heartbeats": r.get("heartbeats"), "proof": r["proof"]})
    from bank.store import load_all
    for r in load_all(name):
        p = r.get("provenance") or {}
        if p.get("model") == "glm-5.3-flash@z.ai" and p.get("mode") == "agent" and r.get("proof") and r.get("score"):
            out.append({"source": "Flash line", "run": p.get("run_id"), "score": r["score"], "tokens": r.get("tokens"), "heartbeats": r.get("heartbeats"), "proof": r["proof"]})
    nf = ROOT / "probe/normalize/union.jsonl"
    for l in (nf.open() if nf.exists() else []):
        r = json.loads(l)
        if r["problem"] == name and r.get("status") == "improved":
            a = r["after"]; out.append({"source": "normalizer on the union best", "run": "normalize", "score": a["score"], "tokens": a["tokens"], "heartbeats": a["heartbeats"], "proof": r["proof"]})
    bf = ROOT / "probe/bounty/results.jsonl"
    for l in (bf.open() if bf.exists() else []):
        r = json.loads(l)
        if r["problem"] == name and r.get("ok") and r.get("score") and r.get("by") != "test":
            out.append({"source": f"bounty compile ({r.get('lever', '')[:60]})", "run": "bounty", "score": r["score"], "tokens": r.get("tokens"), "heartbeats": r.get("heartbeats"), "proof": r["proof"]})
    return out


def review_levers(name: str) -> list[str]:
    if not REVIEW.exists():
        return []
    try:
        d = json.loads(REVIEW.read_text())
    except Exception:  # noqa: BLE001
        return []
    key = name.split(".")[-1][:30]
    for p in d.get("all", []):
        if key[:24] in p.get("file", ""):
            return [x[:400] for x in (p.get("inefficiencies") or [])[:3]]
    return []


def notes_tail(prefix: str, name: str, n: int = 1400) -> str:
    f = ROOT / f"harness/work_{prefix}" / SAFE.sub("_", name) / "notes.md"
    if not f.exists():
        return "(none)"
    t = f.read_text().strip()
    return ("..." + t[-n:]) if len(t) > n else t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="probe/relay/r1")
    ap.add_argument("--problems", nargs="*", default=None)
    a = ap.parse_args()
    out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
    sched = {"opus": [], "astra": []}
    for name in (a.problems or sorted(ROWS)):
        row = ROWS[name]; cs = candidates(name)
        if not cs:
            continue
        best = max(cs, key=lambda c: c["score"])
        lb = {s: max([c["score"] for c in cs if c["source"] == s] or [33.33]) for s in ("Opus 5.5 line", "GPT Astra line", "Flash line")}
        rt, rh = row["proof_length"], HBS.get(name) or 1
        (out / f"{SAFE.sub('_', name)}.lean").write_text(best["proof"].rstrip() + "\n")
        dg = [f"CROSS-LINE DIGEST for {name}",
              f"- Union best (now in candidate.lean): {best['score']} from the {best['source']} ({best['run']}), {best['tokens']} tokens, {best['heartbeats']} heartbeats.",
              f"- Each line's best: Opus 5.5 line {lb['Opus 5.5 line']}, GPT Astra line {lb['GPT Astra line']}, Flash line {lb['Flash line']}.",
              f"- Exchange rate on this problem: 1 token = {100 / (3 * rt):.3f} points, 100 heartbeats = {100 * 100 / (3 * rh):.3f} points.",
              "- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; "
              "a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.",
              "- Opus 5.5 line notes (tail):", notes_tail("ccline-opus55", name),
              "- GPT Astra line notes (tail):", notes_tail("cxline-astra", name)]
        lv = review_levers(name)
        if lv:
            dg += ["- Levers an independent review suggested (unverified unless marked):"] + [f"  * {x}" for x in lv]
        (out / f"{SAFE.sub('_', name)}.md").write_text("\n".join(dg) + "\n")
        holder = "opus" if best["source"].startswith("Opus") else ("astra" if best["source"].startswith("GPT") else "both")
        split = abs(lb["Opus 5.5 line"] - lb["GPT Astra line"]) <= 3.0
        if best["score"] >= 92:   # frozen by the old rule: only the frontier holder polishes it
            for h in (["opus", "astra"] if holder == "both" else [holder]):
                sched[h].append(name)
        elif split:               # both lines within 3 points: both polish the union best
            sched["opus"].append(name); sched["astra"].append(name)
    print("opus:", " ".join(sched["opus"])); print("astra:", " ".join(sched["astra"]))
    (out / "schedule.json").write_text(json.dumps(sched, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
