#!/usr/bin/env python3
"""b66 closed package (retro A1; 2026-10-27): the shards' submission files -> ONE upload file with exactly one line per benchmark row.

Each shard is one router run on its slice of the rows (infra/closed_package/run_final.py); the router keeps its own <run dir>/submission.jsonl
complete on every exit path (harness/final_writer.py, b65-final). This merge never compiles (every shard line was verified by the stage that
produced it and compile-checked by its writer); it only decides, per row in the rows file's order:
  shard   the owning shard's line (plan.json's split; without a plan, the first shard file that has the row), when it passes the static
          checks: a non-empty proof that starts with the row's statement byte for byte (scorer.tokenize.split_declaration) and has no
          forbidden construct (scorer.forbidden)
  seed    else the benchmark's own proof (`src`): a missing shard file, a shard that never wrote the row, a line that fails a check
Lines for names the rows file does not have, and a row's lines in a shard that does not own it, are reported and dropped. Output: the
{"name", "proof"} lines (the Arena upload format) written atomically, and a report (per row: where the line came from, why, the shard
writer's own verdict from its submission_check.json; counts). check() re-reads any upload file against the rows (one line per row, in
order, nothing else; statement identity; forbidden constructs). Messages name rows by position (row#NN) only.

    python3 harness/final_merge.py --rows data/final/rows.jsonl --shard s1=OUT/shards/s1 --shard s2=... --out OUT/submission.jsonl [--plan OUT/plan.json]
    python3 harness/final_merge.py --rows data/final/rows.jsonl --check OUT/submission.jsonl"""
from __future__ import annotations

import argparse, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from harness.final_writer import SUBMISSION, CHECKS, static_check, sha12  # noqa: E402


def read_lines(path: Path) -> tuple[dict, list[str]]:
    """({name: proof} of the file's valid {"name", "proof"} lines (the first of a repeated name), problems). A missing file -> ({}, [why])."""
    out, probs = {}, []
    try:
        text = Path(path).read_text()
    except OSError as e:
        return {}, [f"not readable ({type(e).__name__})"]
    for i, l in enumerate(text.splitlines(), 1):
        if not l.strip():
            continue
        try:
            d = json.loads(l)
        except ValueError:
            probs.append(f"line {i}: not JSON"); continue
        if not (isinstance(d, dict) and isinstance(d.get("name"), str) and isinstance(d.get("proof"), str)):
            probs.append(f"line {i}: not a {{name, proof}} object"); continue
        if d["name"] in out:
            probs.append(f"line {i}: a repeated name"); continue
        out[d["name"]] = d["proof"]
    return out, probs


def merge(rows: list[dict], shards: dict, owners: dict | None = None) -> tuple[list[dict], dict]:
    """rows: the benchmark rows (order = upload order). shards: {label: run dir or submission file}. owners: {name: label} (plan.json), or
    None (the first shard, in label order, that has the row). Returns (the upload lines, the report)."""
    pos = {r["name"]: k for k, r in enumerate(rows)}
    files, verdicts, rep_sh = {}, {}, {}
    for lab in sorted(shards):
        p = Path(shards[lab])
        f = p / SUBMISSION if p.is_dir() or not p.suffix else p
        lines, probs = read_lines(f)
        files[lab] = lines
        try:
            verdicts[lab] = (json.loads((f.parent / CHECKS).read_text()).get("rows") or {})
        except (OSError, ValueError):
            verdicts[lab] = {}
        rep_sh[lab] = {"file": str(f), "lines": len(lines), "problems": probs[:20], "unknown_names": sum(1 for n in lines if n not in pos)}
    out, per_row, cnt = [], [], {"shard": 0, "seed": 0}
    for k, r in enumerate(rows):
        n, tag = r["name"], f"row#{k:02d}"
        own = (owners or {}).get(n)
        cands = [own] if own else [lab for lab in sorted(files) if n in files[lab]]
        rec = {"row": tag, "owner": own}
        if own and own not in files:
            rec["why"] = f"owner shard {own} has no submission file"
        for lab in cands:
            if lab not in files:
                continue
            p = files[lab].get(n)
            if p is None:
                unread = any(x.startswith("not readable") for x in rep_sh[lab]["problems"])
                rec["why"] = f"shard {lab}'s submission file is missing or unreadable" if unread else f"shard {lab} wrote no line for it"
                continue
            why = static_check(p, r.get("statement"))
            if why:
                rec["why"] = f"shard {lab} line refused: {why}"; continue
            rec.update(source=f"shard {lab}", sha=sha12(p), writer=(verdicts.get(lab, {}).get(n) or {}).get("verdict"),
                       pick=(verdicts.get(lab, {}).get(n) or {}).get("pick"))
            rec.pop("why", None)
            out.append({"name": n, "proof": p}); cnt["shard"] += 1
            break
        else:
            seed = r.get("src") or ""
            rec.update(source="seed", sha=sha12(seed))
            rec.setdefault("why", "no shard file has the row")
            sw = static_check(seed, r.get("statement"))
            if sw:
                rec["seed_check"] = sw   # the benchmark's own proof: written anyway (nothing better exists)
            out.append({"name": n, "proof": seed}); cnt["seed"] += 1
        per_row.append(rec)
    if owners:   # a row's line in a shard that does not own it (an older plan): dropped, counted
        for lab, lines in files.items():
            rep_sh[lab]["not_owned"] = sum(1 for n in lines if n in pos and owners.get(n) not in (None, lab))
    report = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rows": len(rows), "counts": cnt, "shards": rep_sh,
              "per_row": per_row}
    return out, report


def write(lines: list[dict], path: Path) -> None:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text("".join(json.dumps({"name": d["name"], "proof": d["proof"]}, ensure_ascii=False) + "\n" for d in lines))
    os.replace(tmp, path)


def check(path: Path, rows: list[dict]) -> list[str]:
    """Problems of an upload file against the rows: [] when it has exactly one {"name", "proof"} line per row, in the rows' order, no other
    line, every proof non-empty, starting with its statement and free of forbidden constructs."""
    probs = []
    try:
        text = Path(path).read_text()
    except OSError as e:
        return [f"not readable ({type(e).__name__})"]
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) != len(rows):
        probs.append(f"{len(lines)} line(s) for {len(rows)} row(s)")
    for k, l in enumerate(lines):
        try:
            d = json.loads(l)
        except ValueError:
            probs.append(f"line {k + 1}: not JSON"); continue
        if not isinstance(d, dict) or set(d) != {"name", "proof"}:
            probs.append(f"line {k + 1}: keys {sorted(d) if isinstance(d, dict) else type(d).__name__}, not exactly name and proof"); continue
        if k >= len(rows) or d["name"] != rows[k]["name"]:
            probs.append(f"line {k + 1}: not row#{k:02d} of the rows file (order or name)"); continue
        why = static_check(d["proof"], rows[k].get("statement"))
        if why and d["proof"].strip() != (rows[k].get("src") or "").strip():   # the seed itself is accepted as given
            probs.append(f"row#{k:02d}: {why}")
    return probs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", required=True)
    ap.add_argument("--shard", action="append", default=[], metavar="LABEL=PATH", help="a shard's run dir or submission file (repeat)")
    ap.add_argument("--plan", help="plan.json of infra/closed_package/run_final.py: the shard that owns each row")
    ap.add_argument("--out"); ap.add_argument("--report")
    ap.add_argument("--check", help="only check this upload file against --rows")
    a = ap.parse_args()
    from harness.final_rows import load
    rows = load(a.rows)
    if a.check:
        probs = check(Path(a.check), rows)
        for p in probs:
            print("PROBLEM:", p)
        print(f"{a.check}: {'OK' if not probs else 'FAILED'} ({len(rows)} row(s), {len(probs)} problem(s))")
        return 1 if probs else 0
    if not a.out or not a.shard:
        ap.error("--out and at least one --shard (or --check)")
    shards = dict(x.split("=", 1) for x in a.shard)
    owners = None
    if a.plan:
        owners = {n: s["label"] for s in json.loads(Path(a.plan).read_text())["shards"] for n in s["names"]}
    lines, rep = merge(rows, shards, owners)
    write(lines, Path(a.out))
    Path(a.report or Path(a.out).with_name("merge_report.json")).write_text(json.dumps(rep, indent=1) + "\n")
    probs = check(Path(a.out), rows)
    print(f"merged {len(lines)} line(s) into {a.out}: {rep['counts']['shard']} from shards, {rep['counts']['seed']} seed; check: "
          f"{'OK' if not probs else '; '.join(probs[:5])}")
    return 1 if probs else 0


if __name__ == "__main__":
    raise SystemExit(main())
