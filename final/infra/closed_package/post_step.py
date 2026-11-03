#!/usr/bin/env python3
"""The closed package's post-step (added 2026-11-03; README.md section 10): one $0, model-free, deterministic, accept-gated pass over a
FINISHED run's merged upload file. Our formal closed upload is closed official run 1's `submission.jsonl` after this step.

    python3 infra/closed_package/post_step.py --out ~/lra-final      # the run's --out, after `run_final.py run` has ended

Reads    <out>/submission.jsonl (the run's merged upload file: read, never written), <out>/plan.json (the shards, the rows file's sha256),
         each shard's finals.json (a row's stored score, tokens and heartbeats, taken only when that final's proof is the line's proof),
         and the rows with their reference heartbeats: by default the files the run staged in data/final/ (checked against plan.json),
         else --rows / --heartbeats.
Runs     harness/open_post.post_step (its files byte-identical to our development commit 5cb18d3b) on that input, with the settings of our
         post-step run on closed run 1: every row at once (--jobs = the number of rows), this host's compile slots (harness/host_knobs.py
         for one shard: min(32, physical cores); LRA_HBTOOL_SLOTS), the step's wall 7200 s (no row starts after it), a row's wall 2400 s
         and 120 compiles, the sorry guard (LRA_FORCE_WARN_SORRY=1), git's safe.directory for this process tree, the `#print axioms`
         audit (harness/post_support.py), and the reference heartbeats file only: the warm-up table data/reference_heartbeats_local.json,
         which the run's own meter reads for the warm-up-named rows, is not read here (scorer.score's table is set empty in this process).
Writes   <out>/post_step/: the step's input proofs.jsonl, its outputs proofs.post.jsonl and post_report.json, its work files post/.
         <out>/submission.post.jsonl: THE UPLOAD FILE after the step, one {"name", "proof"} line per row in the rows' order. It is
         written only when it passes harness/final_merge.check against the rows and every line that differs from submission.jsonl is a
         row the step adopted; otherwise nothing is written and submission.jsonl stays the file to upload.
         <out>/post_report.json: the step's report plus this command's block "post_step".
Exit     0 written and checked; 1 the step ran but its result failed a check (no submission.post.jsonl); 2 refused before the step.
Not running this command leaves the run's output exactly as it was (it is not part of `run_final.py`)."""
from __future__ import annotations

import argparse, hashlib, json, os, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from harness import final_rows as FR, final_merge as FM, host_knobs as HK  # noqa: E402

SOURCE = "closed-run1"          # the input records' "source" field (a label; the step copies it to "post_from" on an adopted row)
POST_DIR = "post_step"
OUT_FILE = "submission.post.jsonl"
REPORT_FILE = "post_report.json"
SECONDS, ROW_SECONDS, ROW_COMPILES = 7200.0, 2400.0, 120   # harness/open_post.py's defaults, as in our run


def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] [post_step] {msg}", flush=True)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def shard_finals(out: Path, plan: dict | None) -> tuple[dict, list[str]]:
    """({name: final record} of the run's shards' finals.json, the files read): each shard's run directory from plan.json, or
    <out>/shards/<label>/ when that directory is not on this host (an out directory copied elsewhere); without a plan,
    <out>/shards/*/finals.json."""
    if plan and plan.get("shards"):
        dirs = []
        for sh in plan["shards"]:
            d = Path(str(sh.get("run_dir") or ""))
            dirs.append(d if (d / "finals.json").is_file() else out / "shards" / str(sh.get("label")))
    else:
        dirs = sorted(p.parent for p in (out / "shards").glob("*/finals.json"))
    finals, read = {}, []
    for d in dirs:
        try:
            f = json.loads((d / "finals.json").read_text())
        except (OSError, ValueError):
            continue
        if isinstance(f, dict):
            read.append(str(d / "finals.json"))
            for n, r in f.items():
                if isinstance(r, dict):
                    finals.setdefault(n, r)
    return finals, read


def build_input(lines: list[dict], finals: dict, source: str) -> tuple[str, int]:
    """The step's input: per line of the merged file {"name", "proof", "source"} plus "stored_score", "tokens", "heartbeats" of the
    row's final when that final's proof is this line's proof (the step uses the stored score as a floor: an adopted proof must round
    above it). Returns (text, rows with a stored score)."""
    out, n = [], 0
    for d in lines:
        rec = {"name": d["name"], "proof": d["proof"], "source": source}
        f = finals.get(d["name"])
        if (isinstance(f, dict) and isinstance(f.get("proof"), str) and f["proof"].rstrip() == str(d["proof"]).rstrip()
                and isinstance(f.get("score"), (int, float))):
            rec.update(stored_score=f["score"], tokens=f.get("tokens"), heartbeats=f.get("heartbeats"))
            n += 1
        out.append(json.dumps(rec, ensure_ascii=False))
    return "".join(l + "\n" for l in out), n


def refuse(msg: str) -> int:
    log(f"REFUSED: {msg}")
    return 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(Path.home() / "lra-final"), help="the run's --out (default ~/lra-final)")
    ap.add_argument("--rows", help="the rows file (default: the run's staged data/final/rows.jsonl)")
    ap.add_argument("--heartbeats", help="the reference heartbeats file (default: the run's staged data/final/heartbeats.jsonl)")
    ap.add_argument("--jobs", type=int, default=None, help="rows at once (default: every row)")
    ap.add_argument("--compile-slots", type=int, default=None, help="Lean compiles at once (default: harness/host_knobs.py, one shard)")
    ap.add_argument("--seconds", type=float, default=SECONDS, help="the step's wall: no row starts after it (default 7200)")
    ap.add_argument("--row-seconds", type=float, default=ROW_SECONDS, help="a row's wall (default 2400)")
    ap.add_argument("--row-compiles", type=int, default=ROW_COMPILES, help="a row's compiles (default 120)")
    ap.add_argument("--problems", nargs="*", default=None, help="only these rows (names); every other row keeps its line (a smoke test)")
    ap.add_argument("--post-dir", default=None, help=f"the step's directory (default <out>/{POST_DIR}; must not exist yet)")
    a = ap.parse_args(argv)
    t0 = time.time()

    out = Path(a.out).expanduser().resolve()
    sub = out / "submission.jsonl"
    if not sub.is_file():
        return refuse(f"no {sub}: run the post-step on a finished run's --out (run_final.py run ... --out DIR)")
    post_dir = Path(a.post_dir).expanduser().resolve() if a.post_dir else out / POST_DIR
    if post_dir.exists() and any(post_dir.iterdir()):
        return refuse(f"{post_dir} exists: the step writes a fresh directory; move it (and {out / OUT_FILE}) aside, or pass --post-dir NEW")
    try:
        plan = json.loads((out / "plan.json").read_text())
    except (OSError, ValueError):
        plan = None
        log(f"no readable {out / 'plan.json'}: the shards' finals are looked up under {out / 'shards'}")

    if a.rows:
        if not a.heartbeats:
            return refuse("--rows needs --heartbeats (the reference heartbeats the run used)")
        rows_path, hbs_path = Path(a.rows).expanduser().resolve(), Path(a.heartbeats).expanduser().resolve()
        if plan and FR.sha256_file(rows_path) != plan.get("rows_sha256"):
            log(f"warning: {rows_path} is not the rows file of plan.json (sha256 differs); the merged file is checked against it below")
    else:
        rows_path, hbs_path = FR.STAGE_DIR / FR.ROWS_FILE, FR.STAGE_DIR / FR.HB_FILE
        if a.heartbeats:
            hbs_path = Path(a.heartbeats).expanduser().resolve()
        try:
            staged = json.loads((FR.STAGE_DIR / FR.STAGED).read_text())
        except (OSError, ValueError):
            staged = {}
        if not rows_path.is_file() or not hbs_path.is_file():
            return refuse(f"no staged rows in {FR.STAGE_DIR} (or no heartbeats file): pass --rows ROWS.jsonl --heartbeats HEARTBEATS.jsonl")
        if plan and staged.get("sha256") != plan.get("rows_sha256"):
            return refuse(f"{FR.STAGE_DIR} holds another rows file than this run's plan.json: pass --rows / --heartbeats")
    for p in (rows_path, hbs_path):
        if not p.is_file():
            return refuse(f"not a file: {p}")
    rows = FR.load(rows_path)
    probs = FM.check(sub, rows)
    if probs:
        return refuse(f"{sub} fails the package's upload-file check against {rows_path}: " + "; ".join(probs[:4]))
    if a.problems:
        unknown = sorted(set(a.problems) - {r["name"] for r in rows})
        if unknown:
            return refuse(f"--problems names {len(unknown)} row(s) not in the rows file: {unknown[:3]}")

    sub_sha = sha256_file(sub)
    lines = read_jsonl(sub)
    finals, finals_read = shard_finals(out, plan)
    text, n_stored = build_input(lines, finals, SOURCE)
    post_dir.mkdir(parents=True, exist_ok=True)
    inp = post_dir / "proofs.jsonl"
    inp.write_text(text)
    slots = int(a.compile_slots or HK.knobs(HK.host(), 1, len(rows))["compile_slots"])
    jobs = int(a.jobs or len(lines))
    log(f"input {inp}: {len(lines)} row(s) from {sub} (sha256 {sub_sha[:16]}), {n_stored} with the stored score of their final "
        f"({len(finals_read)} finals.json); rows {rows_path}, heartbeats {hbs_path}")
    log(f"settings: jobs {jobs}, compile slots {slots}, step wall {a.seconds:g} s, row wall {a.row_seconds:g} s, row compiles "
        f"{a.row_compiles}" + (f", only {len(a.problems)} row(s)" if a.problems else ""))

    # the environment of our post-step run (harness/open_post.py main, which imports the open package's module: post_support here)
    from harness.post_support import SORRY_GUARD_ENV, git_trust, audit_proof
    from probe.verify_candidates import newest_first
    os.environ.update(SORRY_GUARD_ENV)
    git_trust(os.environ)
    os.environ["LRA_HBTOOL_SLOTS"] = str(slots)
    import scorer.score as score_mod
    score_mod._LOCAL_REF = {}   # the reference heartbeats file only (open_post's LRA_LOCAL_REF=none; this scorer has no such switch)
    from harness import open_post as P

    def audit(row, decl):
        return audit_proof(row, decl, newest_first(row["version_info"]), {})

    rep = P.post_step(str(rows_path), str(hbs_path), post_dir, jobs=jobs, seconds=a.seconds, row_seconds=a.row_seconds,
                      row_compiles=a.row_compiles, problems=a.problems, input_path=inp, audit=audit)

    # the upload file: checked before it gets its name; the run's own file must be untouched
    res = post_dir / P.POST_FILE
    post = read_jsonl(res)
    status = {k: (r or {}).get("status") for k, r in enumerate(rep.get("rows") or [])}
    bad = []
    if len(post) != len(lines):
        bad.append(f"{len(post)} line(s) for {len(lines)} input line(s)")
    changed = []
    for k, (d, e) in enumerate(zip(lines, post)):
        if d["name"] != e.get("name"):
            bad.append(f"line {k + 1}: name differs from the input's"); continue
        if e.get("proof") != d["proof"]:
            changed.append(k)
            if status.get(k) != "adopted":
                bad.append(f"row#{k:02d}: changed without an adoption (status {status.get(k)})")
    cand = post_dir / OUT_FILE
    FM.write([{"name": e["name"], "proof": e["proof"]} for e in post], cand)
    bad += FM.check(cand, rows)
    if sha256_file(sub) != sub_sha:
        bad.append(f"{sub} changed during the step")
    block = {"command": "infra/closed_package/post_step.py", "out": str(out), "submission": {"path": str(sub), "sha256": sub_sha},
             "rows": {"path": str(rows_path), "sha256": FR.sha256_file(rows_path)},
             "heartbeats": {"path": str(hbs_path), "sha256": FR.sha256_file(hbs_path)},
             "finals_read": finals_read, "rows_with_stored_score": n_stored, "input_sha256": sha256_file(inp),
             "compile_slots": slots, "jobs": jobs, "changed_rows": [f"row#{k:02d}" for k in changed], "problems": bad,
             "seconds": round(time.time() - t0, 1), "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if bad:
        block["output"] = None
        rep["post_step"] = block
        (out / REPORT_FILE).write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n")
        log("FAILED its checks (" + "; ".join(bad[:4]) + f"): no {OUT_FILE} written; upload {sub}")
        return 1
    tmp = out / f".{OUT_FILE}.{os.getpid()}.tmp"
    shutil.copyfile(cand, tmp)
    os.replace(tmp, out / OUT_FILE)
    block["output"] = {"path": str(out / OUT_FILE), "sha256": sha256_file(out / OUT_FILE)}
    rep["post_step"] = block
    (out / REPORT_FILE).write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n")
    log(f"done in {block['seconds']:.0f} s: {len(changed)} row(s) changed ({', '.join(block['changed_rows']) or 'none'}), stored mean "
        f"{rep.get('stored_mean_before')} -> {rep.get('stored_mean_after')}; upload {out / OUT_FILE} (sha256 "
        f"{block['output']['sha256'][:16]}; checked); report {out / REPORT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
