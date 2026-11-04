#!/usr/bin/env python3
"""Snapshot of a clean-set ladder after the $0 cleanup (2026-10-14; docs/auto_brief_plan.md M3): per row, the best of the ladder's stored
best and the cleanup's candidates (autobrief S1, and S0 when free passes applied), each fully scored on every listed toolchain.
Writes <out>.jsonl ({"name", "proof"}, the submission format) and <out>.predictions.json (per-row scores and sources).
    python3 probe/autobrief/build_snapshot.py --work-root <ladder work root> --cleanup probe/autobrief/wu-best-ab1 --out <path stem>
    python3 probe/autobrief/build_snapshot.py --verify <path stem>.jsonl     (re-check every proof, full scoring; run in a capped unit)"""
import argparse, json, pathlib, statistics as st, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def build(work_root: str, cleanup: str, out: str) -> int:
    rows = [json.loads(l) for l in (ROOT / "data/benchmark_warmup.jsonl").open() if l.strip()]
    states = {json.loads(p.read_text())["problem"]: json.loads(p.read_text()) for p in pathlib.Path(work_root).glob("*/state.json")}
    clean = {json.loads(p.read_text())["problem"]: json.loads(p.read_text()) for p in pathlib.Path(cleanup).glob("*.json")}
    preds, lines = [], []
    for r in rows:
        n = r["name"]; b = states[n]["best"]
        pick = {"source": "ladder best", "proof": b["proof"], **{k: b.get(k) for k in ("score", "L", "H", "Z", "tokens", "heartbeats")}}
        c = clean.get(n) or {}
        cands = []
        if c.get("s1") and c["s1"]["full"].get("ok"):
            cands.append(("cleanup S1 (free passes + single-edit combination)", c["s1"]["proof"], c["s1"]["full"]))
        st0 = c.get("start") or {}
        if c.get("free_applied") and st0.get("ok") and float(st0.get("Z") or 0) >= 100 - 1e-9:
            cands.append((f"cleanup S0 (free passes: {', '.join(c['free_applied'])})", c["s0"], st0))
        for src, proof, ev in cands:
            if float(ev["score"]) > float(pick["score"] or 0) + 1e-9:
                pick = {"source": src, "proof": proof, **{k: ev.get(k) for k in ("score", "L", "H", "Z", "tokens", "heartbeats")}}
        lines.append(json.dumps({"name": n, "proof": pick["proof"].rstrip() + "\n"}, ensure_ascii=False))
        preds.append({"name": n, "ladder_best": b.get("score"), **{k: v for k, v in pick.items() if k != "proof"},
                      "api_spend_usd_list": round(float(states[n].get("api_spend") or 0), 4)})
    pathlib.Path(out + ".jsonl").write_text("\n".join(lines) + "\n")
    summary = {"rows": len(preds), "mean": round(st.mean(p["score"] for p in preds), 2), "L": round(st.mean(p["L"] for p in preds), 2),
               "H": round(st.mean(p["H"] for p in preds), 2), "ladder_mean": round(st.mean(p["ladder_best"] for p in preds), 2),
               "api_spend_usd_list_total": round(sum(p["api_spend_usd_list"] for p in preds), 2),
               "api_spend_usd_list_max": round(max(p["api_spend_usd_list"] for p in preds), 4)}
    pathlib.Path(out + ".predictions.json").write_text(json.dumps({"summary": summary, "rows": preds}, ensure_ascii=False, indent=1))
    print(json.dumps(summary))
    return 0


def verify(jsonl: str) -> int:
    from harness.normalize import evaluate
    from probe.verify_candidates import newest_first
    from harness.leantools import ROWS
    out, bad = [], 0
    for l in open(jsonl):
        if not l.strip():
            continue
        e = json.loads(l); row = ROWS[e["name"]]
        ev = evaluate(e["name"], e["proof"], newest_first(row["version_info"]), True)
        out.append({"name": e["name"], **{k: ev.get(k) for k in ("ok", "score", "L", "H", "Z", "tokens", "heartbeats", "compat", "error")}})
        bad += not ev.get("ok") or float(ev.get("Z") or 0) < 100 - 1e-9
        print(f"{e['name'][:50]:50s} ok={ev.get('ok')} score={ev.get('score')} Z={ev.get('Z')}", flush=True)
    p = pathlib.Path(jsonl).with_suffix(".verify.json")
    p.write_text(json.dumps({"rows": out, "mean": round(st.mean(r["score"] or 0 for r in out), 2), "failed": bad}, indent=1, ensure_ascii=False))
    print(f"mean {st.mean(r['score'] or 0 for r in out):.2f}; failed or Z<100: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--work-root"); ap.add_argument("--cleanup"); ap.add_argument("--out"); ap.add_argument("--verify")
    a = ap.parse_args()
    sys.exit(verify(a.verify) if a.verify else build(a.work_root, a.cleanup, a.out))
