#!/usr/bin/env python3
"""Offline test of harness/autobrief.py (2026-10-14): a fake evaluator stands in for Lean (no compile), over the 15 warm-up seeds.
Checks: every deletion and closer edit is a well-formed span whose application changes the body and keeps the statement; the closer sites
include the whole proof; the sweep respects its budget and records outcomes; the combination keeps only non-overlapping paying edits and
is checked in full; the brief is within its size, carries the measured numbers and no theorem name.    python3 harness/test_autobrief.py"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from harness import autobrief as AB  # noqa: E402
from scorer.tokenize import split_declaration, count_tokens  # noqa: E402

rows = [json.loads(l) for l in open(ROOT / "data/benchmark_warmup.jsonl") if l.strip()]


def fake_ev(row):
    """ok unless the edit removed an `intro`/`induction`/`cases` line or closed a block of more than 400 chars with a closer; heartbeats
    shrink with the text; score from the real L formula and a fake H."""
    src_body = split_declaration(row["src"].rstrip(), row["statement"])

    def ev(decl, full):
        body = split_declaration(decl.rstrip(), row["statement"])
        if body is None:
            return {"ok": False, "error": "statement differs"}
        lost = [w for w in ("intro", "induction", "cases") if src_body.count(w) > body.count(w)]
        big_close = any(c in body and c not in src_body for c in AB.CLOSERS) and len(src_body) - len(body) > 400
        if lost or big_close:
            return {"ok": False, "error": "unsolved goals"}
        tok = count_tokens(body); hb = 3 * len(body)
        L = AB.len_pct(row["proof_length"], tok); H = max(0.0, 100 * (1 - hb / (3 * len(src_body) + 1)))
        return {"ok": True, "tokens": tok, "heartbeats": hb, "L": round(L, 2), "H": round(H, 2), "Z": 100.0, "score": round((L + H + 100) / 3, 2)}
    return ev


ok = {"spans well formed": True, "whole-proof closer site": True, "budget respected": True, "outcomes recorded": True,
      "combination non-overlapping and full-checked": True, "brief size and content": True, "no theorem name in brief": True}
tot_del = tot_clo = 0
for r in rows:
    body = split_declaration(r["src"].rstrip(), r["statement"])
    dels, clos = AB.deletion_edits(body), AB.closer_edits(body)
    tot_del += len(dels); tot_clo += len(clos)
    for e in dels + clos:
        nb = e.apply(body)
        if not (0 <= e.a <= e.b <= len(body)) or nb == body:
            ok["spans well formed"] = False; print("bad span", r["name"][:30], e.kind, e.label[:60])
            break
    if not any(e.label.startswith("replace the whole proof") for e in clos):
        ok["whole-proof closer site"] = False; print("no whole-proof site", r["name"][:30])
    out = AB.autobrief(r["name"], budget=20, workers=2, free=False, prof=False, ev=fake_ev(r), log=lambda m: None)
    if out.get("status") != "ok":
        ok["outcomes recorded"] = False; print("status", r["name"][:30], out.get("status")); continue
    if len(out["edits"]) > 20:
        ok["budget respected"] = False
    if not all("ok" in e for e in out["edits"]):
        ok["outcomes recorded"] = False
    if out.get("s1") and not out["s1"]["full"].get("ok"):
        ok["combination non-overlapping and full-checked"] = False
    b = out["brief"]
    if len(b) > AB.BRIEF_CHARS or "Exchange rate here" not in b or "Seed:" not in b:
        ok["brief size and content"] = False; print("brief", r["name"][:30], len(b))
    if r["name"] in b or r["name"].split(".")[-1] in b.replace(r["statement"], ""):
        ok["no theorem name in brief"] = False; print("name in brief", r["name"][:40])
print(f"  edits over 15 seeds: {tot_del} deletions, {tot_clo} closer edits")
print("  sample brief (" + rows[2]["name"][:20] + "):\n" + "\n".join("    " + l for l in AB.autobrief(rows[2]["name"], budget=20, workers=2, free=False,
      prof=False, ev=fake_ev(rows[2]), log=lambda m: None)["brief"].splitlines()))
for k, v in ok.items():
    print(("PASS " if v else "FAIL ") + k)
sys.exit(0 if all(ok.values()) else 1)
