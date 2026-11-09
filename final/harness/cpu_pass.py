#!/usr/bin/env python3
"""C0 pre-session CPU pass (b63 launch set item 6; docs/adaptive_plan_93.md §1.1 C0, logging contract §2 cpu_pass.json / shown.json).

$0, CPU only, before session 1 of a row: the frozen end stage (harness/endstage.py --config, default probe/b63/c0_config.json = the r5
families on a C0 budget) runs on the SEED (or on the work root's current best with --from-work-root), its verified output B0 is
  - banked: <work root>/<ws>/bank.jsonl (harness/bank.py; source c0:<stage>, parent = the seed) with the seed itself (source seed),
  - logged: <work root>/<ws>/cpu_pass.json {families run, order, wall per family, banked deltas, B0 score vs seed, compiles, seconds},
  - handed to the session: the row's auto-brief json (<auto-brief dir>/<ws>.json, harness/autobrief.py) gets `c0` {proof, full numbers,
    families, delta} and `shown` (the SHOWN block: the unified diff of B0 against the seed with tokens / heartbeats / score and the family
    labels that produced it, never a lemma hint), and its brief text (`brief` and the .md) gets the SHOWN block appended. agent.py
    --auto-brief starts the workspace from `c0` when it beats `s1` / the start, and records shown.json per session (contract §2).
The seed is always among the candidates, so a C0 that finds nothing leaves the row as it was (B0 = seed, delta 0). Rows the end stage
cannot read are logged and skipped. Compiles go through scorer.compile (memgate-admitted): run it in a memory-capped unit or the line's
container (hx_heldout --agent-c0), never from an interactive shell.
    python3 harness/cpu_pass.py --work-root harness/hwork/<line> --auto-brief-dir harness/hwork/<line>/_autobrief --problems NAME ...
        [--config probe/b63/c0_config.json] [--rows R.jsonl --heartbeats H.jsonl] [--jobs 2] [--out DIR] [--from-work-root]"""
from __future__ import annotations

import argparse, difflib, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(1, str(ROOT / "harness"))

DEFAULT_CONFIG = "probe/b63/c0_config.json"
SHOWN_MAX_CHARS = 9000      # ~3k tokens (plan §1.1 L: the SHOWN block renderer caps at 3k tokens)
SHOWN_MAX_ITEMS = 3


def safe(n: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", n)


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def unified(seed: str, cand: str) -> str:
    d = difflib.unified_diff(seed.rstrip().splitlines(), cand.rstrip().splitlines(), "seed", "compiled", lineterm="", n=1)
    return "\n".join(l for l in d if not l.startswith(("---", "+++")))


def render_shown(items: list[dict]) -> str:
    """The SHOWN block (plan: 'the model is never told; it is shown compiled code of its own proof'): per item the family labels, the
    numbers against the seed and the unified diff. Text only; capped."""
    if not items:
        return ""
    lines = ["SHOWN (compiled by the harness from THIS seed before your session, $0, verified on every listed toolchain; each is a "
             "real alternative text of the same proof with its measured numbers, not a hint):"]
    for k, it in enumerate(items[:SHOWN_MAX_ITEMS], 1):
        lines.append(f"({k}) {it['tokens']} tokens, {it['heartbeats']} heartbeats, score {it['score']:.2f} (seed {it['seed_score']:.2f}, "
                     f"{it['delta']:+.2f}); produced by: {', '.join(it['families']) or 'pick'}; sha {it['sha']}")
        lines.append(it["diff"])
    txt = "\n".join(lines)
    return txt if len(txt) <= SHOWN_MAX_CHARS else txt[:SHOWN_MAX_CHARS - 1].rsplit("\n", 1)[0] + "\n(cut)"


def render_artifact_shown(art: dict, best: dict, turns: int | None = None) -> str:
    """The SHOWN block of an ARTIFACT-SESSION (b63 item 16; agent.py --artifact): the same renderer as render_shown (a unified diff of the
    compiled artifact against the row's best, the numbers), plus the holes with their goals and what the session is for. Text only; capped."""
    from scorer.tokenize import count_tokens
    bp = (best.get("proof") or "").rstrip()
    holes = art.get("holes") or []
    try:
        te = art.get("tokens_est")
        if te is None:   # the body after the first `:=` (the statement is byte-identical to the row's, so this is the proof body)
            m = re.search(r":=", art["text"])
            te = count_tokens(art["text"][m.end():]) if m else None
    except Exception:  # noqa: BLE001
        te = art.get("tokens_est")
    head = [f"SHOWN ARTIFACT (compiled by the harness from THIS row's proofs, $0; kind {art.get('kind')}, produced by {art.get('source')}; a real "
            f"alternative text of the same proof, not a hint). It is candidate.lean now; best.lean holds your current best "
            f"({best.get('tokens')} tokens, {best.get('heartbeats')} heartbeats, score {best.get('score')})."]
    if holes:
        head.append(f"The artifact elaborates with {len(holes)} `sorry` hole(s) (each `sorry` counts as a token here: ~{te} tokens with the holes; "
                    "heartbeats are measured once every hole is filled). The holes and their goals:")
        for h in holes:
            head.append(f"  hole {h.get('hole_id')} (line {h.get('line')}): ⊢ {h.get('goal') or '(run lean_skeleton on candidate.lean for the goal)'}")
    else:
        head.append(f"The artifact compiles ({te} tokens" + (f", {art.get('heartbeats')} heartbeats, score {art.get('score')}" if art.get("heartbeats") else "") + ").")
    diff = unified(bp, art["text"]) if bp else art["text"].rstrip()
    head.append("Its diff against your best (- best, + artifact):\n" + diff)
    head.append("YOUR JOB IN THIS SESSION" + (f" ({turns} turns)" if turns else "") + ": " + ("fill the holes so the whole text compiles (lean_skeleton returns every hole's goal; lean_run "
                "tests a closer on one goal), then lean_check the full candidate and polish it. finish is refused while the artifact has open holes and a third "
                "of the budget remains." if holes else "polish the artifact (it is a different architecture from your best): lean_check it, then cut tokens / "
                "heartbeats where its profile says.") + " Do not start over from original.lean and do not rewrite best.lean's architecture back in.")
    txt = "\n".join(head)
    return txt if len(txt) <= SHOWN_MAX_CHARS else txt[:SHOWN_MAX_CHARS - 1].rsplit("\n", 1)[0] + "\n(cut)"


def families_of(rec: dict) -> list[str]:
    fams = []
    for d in rec.get("decisions") or []:
        if d.get("banked") and d.get("fop") and d["fop"] not in fams:
            fams.append(d["fop"])
    return fams


def wall_by_family(rec: dict) -> dict:
    out = {}
    for fam, st in (rec.get("families") or {}).items():
        if isinstance(st, dict) and st.get("seconds") is not None:
            out[fam] = round(float(st["seconds"]), 1)
    for ph, st in (rec.get("phases") or {}).items():
        if isinstance(st, dict) and st.get("seconds") is not None:
            out[f"phase:{ph}"] = round(float(st["seconds"]), 1)
    return out


def run_endstage(run: Path, out: Path, rows: str | None, hbs: str | None, cfg: str, jobs: int, log) -> dict:
    cmd = [sys.executable, "-u", str(ROOT / "harness/endstage.py"), "--run-dir", str(run), "--out", str(out), "--config", cfg, "--jobs", str(jobs)]
    if rows:
        cmd += ["--rows", rows]
    if hbs:
        cmd += ["--heartbeats", hbs]
    env = dict(os.environ)
    if out.resolve().is_relative_to(ROOT):   # the end stage's compile slots next to its output (a line's container can write there)
        env.setdefault("LRA_HBTOOL_SCRATCH", str(out / ".scratch"))
    with (out / "endstage.log").open("a") as f:
        rc = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, env=env).returncode
    log(f"end stage exit {rc}")
    recs = {}
    p = out / "report.jsonl"
    if p.exists():
        for l in p.read_text().splitlines():
            try:
                r = json.loads(l) if l.strip() else None
            except ValueError:
                continue
            if r and r.get("out"):
                recs[r["problem"]] = r
    return recs


def apply_row(name: str, rec: dict | None, seed: str, work_root: Path, ab_dir: Path | None, log, cfg: str, from_work_root: bool) -> dict:
    from harness import bank as BK
    ws = work_root / safe(name); ws.mkdir(parents=True, exist_ok=True)
    im = (rec or {}).get("input_measured") or {}
    end = (rec or {}).get("end") or {}
    out_proof = ((rec or {}).get("out") or {}).get("proof") or ""
    seed_score = im.get("score_exact")
    rec_out = {"problem": name, "at": now(), "config": cfg, "source": "work-root best" if from_work_root else "seed",
               "families": sorted((rec or {}).get("families") or {}), "order": families_of(rec or {}), "wall": wall_by_family(rec or {}),
               "banked": [{"fop": d.get("fop"), "d_score": d.get("d_score"), "d_tokens": d.get("d_tokens"), "d_heartbeats": d.get("d_heartbeats")}
                          for d in (rec or {}).get("decisions") or [] if d.get("banked") and d.get("fop")],
               "seed": {k: im.get(k) for k in ("ok", "score_exact", "tokens", "heartbeats", "Z")},
               "B0": {k: end.get(k) for k in ("score_exact", "tokens", "heartbeats", "Z", "stage")},
               "delta": (rec or {}).get("delta"), "compiles": (rec or {}).get("compiles"), "seconds": (rec or {}).get("seconds"),
               "meter": (rec or {}).get("meter"), "status": "ok" if rec else "no end-stage record"}
    BK.add(ws, BK.entry(seed, "seed", tokens=im.get("tokens"), heartbeats=im.get("heartbeats"), Z=im.get("Z"), compat=im.get("compat"), score=seed_score))
    changed = bool(rec) and out_proof.strip() and out_proof.strip() != seed.strip() and end.get("score_exact") is not None and seed_score is not None \
        and float(end["score_exact"]) > float(seed_score)
    shown = []
    if changed:
        stage = f"c0:{end.get('stage') or 'end'}"
        BK.add(ws, BK.entry(out_proof, stage, tokens=end.get("tokens"), heartbeats=end.get("heartbeats"), Z=end.get("Z"), score=end.get("score_exact"),
                            compat=((rec or {}).get("out") or {}).get("compat"), parent=BK.sha(seed)))   # compat = the end stage's all-pin confirmation
        shown.append({"sha": BK.sha(out_proof), "tokens": end.get("tokens"), "heartbeats": end.get("heartbeats"), "score": float(end["score_exact"]),
                      "seed_score": float(seed_score), "delta": float(end["score_exact"]) - float(seed_score), "families": rec_out["order"],
                      "diff": unified(seed, out_proof)})
    rec_out["shown"] = [{k: v for k, v in s.items() if k != "diff"} for s in shown]
    (ws / "cpu_pass.json").write_text(json.dumps(rec_out, ensure_ascii=False, indent=1))
    if ab_dir is not None:
        f = ab_dir / f"{safe(name)}.json"
        try:
            ab = json.loads(f.read_text()) if f.exists() else {"problem": name, "status": "c0 only", "brief": ""}
        except ValueError:
            ab = {"problem": name, "status": "c0 only", "brief": ""}
        ab["c0"] = {"proof": out_proof if changed else seed, "full": {"ok": True, "score": end.get("score_exact") if changed else seed_score,
                                                                       "tokens": (end if changed else im).get("tokens"), "heartbeats": (end if changed else im).get("heartbeats"),
                                                                       "Z": (end if changed else im).get("Z")},
                    "families": rec_out["order"], "delta": rec_out["delta"], "changed": changed, "at": now()}
        ab["shown"] = shown
        txt = render_shown(shown)
        if txt and "SHOWN (" not in (ab.get("brief") or ""):
            ab["brief"] = ((ab.get("brief") or "").rstrip() + "\n\n" + txt).strip()
            md = ab_dir / f"{safe(name)}.md"
            md.write_text(ab["brief"] + "\n")
        tmp = f.with_suffix(".tmp"); tmp.write_text(json.dumps(ab, ensure_ascii=False, indent=1)); tmp.replace(f)
    log(f"{'B0 ' + str(round(float(end['score_exact']), 2)) + ' vs seed ' + str(round(float(seed_score), 2)) if changed else 'B0 = seed'}"
        f" ({rec_out['compiles']} compiles, {rec_out['seconds']} s)" if rec else "no end-stage record")
    return rec_out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work-root", required=True, help="the line's work root (bank.jsonl / cpu_pass.json go to <work root>/<ws>/)")
    ap.add_argument("--auto-brief-dir", default=None, help="the auto-brief dir: c0 + shown go into <dir>/<ws>.json and the SHOWN block into the brief")
    ap.add_argument("--problems", nargs="*"); ap.add_argument("--rows"); ap.add_argument("--heartbeats")
    ap.add_argument("--config", default=DEFAULT_CONFIG); ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--out", default=None, help="the end stage's run/out dirs (default <work root>/_c0)")
    ap.add_argument("--from-work-root", action="store_true", help="start from each row's current best in the work root instead of the seed")
    a = ap.parse_args(argv)
    from harness.leantools import ROWS
    if a.rows:
        from harness.autobrief import register_rows
        register_rows(a.rows, a.heartbeats)
    names = a.problems or list(ROWS)
    work_root = Path(a.work_root); work_root = work_root if work_root.is_absolute() else ROOT / work_root
    out = Path(a.out) if a.out else work_root / "_c0"
    out = out if out.is_absolute() else ROOT / out
    run = out / "run"; (run / "rows").mkdir(parents=True, exist_ok=True); (out / "end").mkdir(parents=True, exist_ok=True)
    log = lambda m: print(f"[{time.strftime('%H:%M:%S')}] c0: {m}", flush=True)   # noqa: E731
    seeds, finals = {}, {}
    for n in names:
        if n not in ROWS:
            log(f"unknown row skipped"); continue
        try:   # done earlier (a resumed ladder); a record without an end-stage result is retried
            if json.loads((work_root / safe(n) / "cpu_pass.json").read_text()).get("status") == "ok":
                continue
        except (OSError, ValueError):
            pass
        seed = ROWS[n]["src"]
        if a.from_work_root:
            st = work_root / safe(n) / "state.json"
            try:
                b = json.loads(st.read_text()).get("best") or {}
                seed = b.get("proof") or seed
            except (OSError, ValueError):
                pass
        seeds[n] = seed
        finals[n] = {"proof": seed, "score": None, "spend": 0.0}
        (run / "rows" / f"{safe(n)}.json").write_text(json.dumps({"problem": n}))
    if not seeds:
        log("nothing to do"); return 0
    (run / "finals.json").write_text(json.dumps(finals, ensure_ascii=False, indent=1))
    t0 = time.time()
    log(f"{len(seeds)} row(s), config {a.config}, jobs {a.jobs}")
    recs = run_endstage(run, out / "end", a.rows, a.heartbeats, a.config, a.jobs, log)
    ab_dir = Path(a.auto_brief_dir) if a.auto_brief_dir else None
    if ab_dir is not None and not ab_dir.is_absolute():
        ab_dir = ROOT / ab_dir
    done = 0
    for n, seed in seeds.items():
        try:
            r = apply_row(n, recs.get(n), seed, work_root, ab_dir, lambda m, n=n: log(f"row {safe(n)[:40]}: {m}"), a.config, a.from_work_root)
            done += r["status"] == "ok"
        except Exception as e:  # noqa: BLE001
            log(f"row failed: {type(e).__name__}: {str(e)[:120]}")
    log(f"done: {done}/{len(seeds)} rows with a C0 record in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
