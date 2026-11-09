"""Submission ledger: every Arena submission (prepared, sent, scored) with
enough detail to trace it back — benchmark version, file checksum, per-problem
provenance and local predictions, the worker's per-problem results, and the
prediction error. Machine record: submit/ledger.jsonl (one JSON per line, the
latest line for a given `id` wins). Human view: submit/SUBMISSIONS.md.

Usage:
  python3 submit/ledger.py register <id> <jsonl> --note "..." [--predictions <json>]
  python3 submit/ledger.py sent <id> --when 2026-10-06T04:38Z --track open --user Vexorium
  python3 submit/ledger.py scored <id> --results <worker_table.json> [--combined 33.33 --rank 8]
  python3 submit/ledger.py render
"""
from __future__ import annotations

import argparse, hashlib, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LEDGER = ROOT / "submit/ledger.jsonl"
VIEW = ROOT / "submit/SUBMISSIONS.md"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load() -> dict:
    out: dict = {}
    if LEDGER.exists():
        for l in LEDGER.open():
            if l.strip():
                d = json.loads(l); out[d["id"]] = {**out.get(d["id"], {}), **d}
    return out


def save(rec: dict) -> None:
    rec["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with LEDGER.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def benchmark_info() -> dict:
    b = ROOT / "data/benchmark_warmup.jsonl"; h = ROOT / "data/benchmark_heartbeats.jsonl"
    rows = [json.loads(l) for l in b.open() if l.strip()]
    return {"set": "warmup-15", "benchmark_sha256": sha(b)[:16], "heartbeats_sha256": sha(h)[:16], "n_problems": len(rows)}


def register(args) -> None:
    from scorer.tokenize import split_declaration, count_tokens
    from bank.store import sha as proof_sha, load_all
    rows = {json.loads(l)["name"]: json.loads(l) for l in (ROOT / "data/benchmark_warmup.jsonl").open() if l.strip()}
    bank = {r["sha256"]: r for r in load_all()}
    f = Path(args.jsonl).resolve()
    preds = json.loads(Path(args.predictions).read_text()) if args.predictions else {}
    problems = {}
    for l in f.open():
        if not l.strip():
            continue
        d = json.loads(l); name = d["name"]; row = rows[name]
        body = split_declaration(d["proof"], row["statement"])
        s = proof_sha(d["proof"])
        is_ref = d["proof"].rstrip() == row["src"].rstrip()
        b = bank.get(s)
        entry = {"proof_sha256": s[:16], "change": "reference (unchanged)" if is_ref else "modified",
                 "tokens": count_tokens(body) if body else None, "ref_tokens": row["proof_length"]}
        if b:
            entry["provenance"] = b.get("provenance"); entry["bank_record"] = f"bank/{name}/{s}.json"
        if name in preds and not preds[name].get("reference"):
            p = preds[name]; entry["local_prediction"] = {k: p[k] for k in ("L", "H_pred", "H_if_official_ref", "Z", "score", "hb_local") if k in p}
        elif is_ref:
            entry["local_prediction"] = {"L": 0.0, "H_pred": 0.0, "Z": 100.0, "score": 33.33}
        problems[name] = entry
    rec = {"id": args.id, "status": "prepared", "file": str(f.relative_to(ROOT)), "file_sha256": sha(f)[:16],
           "benchmark": benchmark_info(), "note": args.note, "n_rows": len(problems),
           "predicted_combined": preds.get("_predicted_combined", round(sum(p["local_prediction"]["score"] for p in problems.values()) / 15, 2)),
           "problems": problems, "prepared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    save(rec); print(f"registered {args.id}: {len(problems)} rows, predicted combined {rec['predicted_combined']}")


def sent(args) -> None:
    rec = load()[args.id]
    rec.update({"status": "sent", "sent_at": args.when, "track": args.track, "username": args.user}); save(rec); print("marked sent")


def scored(args) -> None:
    rec = load()[args.id]
    table = json.loads(Path(args.results).read_text())  # list of rows: [problem, result, score, length, L%, heartbeats, H%, zeroshot, notes]
    num = lambda s: float(re.sub(r"[^0-9.\-]", "", s.split(" of ")[0])) if re.search(r"\d", s) else None
    for r in table:
        if not r or r[0] == "PROBLEM" or r[0] not in rec["problems"]:
            continue
        name, result, score, length, Lp, hb, Hp, zs, notes = (r + [""] * 9)[:9]
        w = {"result": result, "score": num(score), "tokens": num(length), "L": num(Lp), "heartbeats": num(hb), "H": num(Hp),
             "zero_shot": zs, "notes": notes}
        rec["problems"][name]["worker"] = w
        lp = rec["problems"][name].get("local_prediction") or {}
        if lp and w["score"] is not None:
            rec["problems"][name]["delta"] = {"score": round(w["score"] - lp.get("score", 0), 2),
                                              "L": round((w["L"] or 0) - lp.get("L", 0), 2),
                                              "H_vs_pred": round((w["H"] or 0) - lp.get("H_pred", 0), 2),
                                              "H_vs_official_ref_formula": round((w["H"] or 0) - lp.get("H_if_official_ref", lp.get("H_pred", 0)), 2)}
    rec.update({"status": "scored", "scored_at": args.when or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "worker_combined": args.combined, "leaderboard_rank": args.rank})
    save(rec); print("recorded worker results")


def render(_args=None) -> None:
    recs = sorted(load().values(), key=lambda r: r.get("prepared_at", ""))
    out = ["# Submissions ledger — Vexorium (Track 2)\n",
           "Source of truth: `submit/ledger.jsonl` (append-only; latest line per id wins). Regenerate this file with `python3 submit/ledger.py render`.\n"]
    for r in recs:
        out.append(f"\n## {r['id']} — {r['status']}\n")
        out.append(f"- File: `{r['file']}` (sha256 {r['file_sha256']}), {r['n_rows']} rows · benchmark {r['benchmark']['set']} (sha {r['benchmark']['benchmark_sha256']}, heartbeats sha {r['benchmark']['heartbeats_sha256']})")
        out.append(f"- Note: {r.get('note','')}")
        out.append(f"- Prepared {r.get('prepared_at','')} · sent {r.get('sent_at','—')} ({r.get('track','—')} track, user {r.get('username','—')}) · scored {r.get('scored_at','—')}")
        out.append(f"- **Predicted combined {r.get('predicted_combined')}** · **worker combined {r.get('worker_combined','—')}** · rank {r.get('leaderboard_rank','—')}")
        out.append("\n| problem | change / provenance | tokens | pred L | pred H | pred score | worker L | worker H | worker Z | worker score | Δscore |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for name, p in r["problems"].items():
            lp = p.get("local_prediction") or {}; w = p.get("worker") or {}; d = p.get("delta") or {}
            prov = p.get("provenance") or {}
            change = p["change"] if p["change"].startswith("reference") else f"{p['change']} · {prov.get('model','?')} {prov.get('mode','')} r{prov.get('round','')} (dev-only)" if prov.get("kind")=="api-dev-only" else p["change"]
            fmt = lambda v: "—" if v is None or v == "" else (f"{v:+.2f}" if isinstance(v, float) else str(v))
            out.append(f"| {name[:38]} | {change} | {p.get('tokens')}/{p.get('ref_tokens')} | {fmt(lp.get('L'))} | {fmt(lp.get('H_pred'))} | {lp.get('score','—')} | {fmt(w.get('L'))} | {fmt(w.get('H'))} | {w.get('zero_shot','—')} | {w.get('score','—')} | {fmt(d.get('score'))} |")
    VIEW.write_text("\n".join(out) + "\n"); print(f"rendered {VIEW.relative_to(ROOT)} ({len(recs)} submissions)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("register"); a.add_argument("id"); a.add_argument("jsonl"); a.add_argument("--note", default=""); a.add_argument("--predictions"); a.set_defaults(fn=register)
    b = sub.add_parser("sent"); b.add_argument("id"); b.add_argument("--when", required=True); b.add_argument("--track", default="open"); b.add_argument("--user", default="Vexorium"); b.set_defaults(fn=sent)
    c = sub.add_parser("scored"); c.add_argument("id"); c.add_argument("--results", required=True); c.add_argument("--combined", type=float); c.add_argument("--rank", type=int); c.add_argument("--when"); c.set_defaults(fn=scored)
    d = sub.add_parser("render"); d.set_defaults(fn=render)
    args = ap.parse_args(); args.fn(args)
    if args.cmd != "render":
        render()
