#!/usr/bin/env python3
"""The closed package's post-step (README.md section 10; v1 2026-11-03, v2 and v4su 2026-11-04): a $0, model-free, accept-gated pass
over a FINISHED run's merged upload file, or over an earlier pass's output. Our closed upload is closed official run 3's
`submission.jsonl` after chained passes of this step with the post-step v4su code (every op except the kernel-skip op kskip: 29 ops;
our decision of 2026-11-04, our upload carries no `set_option debug.*`; README.md section 10 lists the passes we ran).

    python3 infra/closed_package/post_step.py --out ~/lra-final      # pass 1: the run's --out, after `run_final.py run` has ended
    python3 infra/closed_package/post_step.py --out ~/lra-final --input ~/lra-final/post_step/proofs.post.jsonl --post-dir \
        ~/lra-final/post_step2                                        # pass 2: the same step on pass 1's output

Reads    <out>/submission.jsonl (the run's merged upload file: read, never written), <out>/plan.json (the shards, the rows file's sha256),
         each shard's finals.json (a row's stored score, tokens and heartbeats, taken only when that final's proof is the line's proof),
         and the rows with their reference heartbeats: by default the files the run staged in data/final/ (checked against plan.json),
         else --rows / --heartbeats. With --input FILE (a later pass): the step's input records are FILE's lines as they are (an
         earlier pass's <post-dir>/proofs.post.jsonl: name, proof, stored score, tokens, heartbeats of each row after that pass), one
         per line of submission.jsonl, same names, same order; submission.jsonl and the finals are then only checked against, not used.
Runs     harness/open_post.post_step (harness/open_post.py and harness/post/ byte-identical to our development commit 93959dcb,
         post-step v4su = post-step v4 715cd39d + the v5 op hb_smartunfold of 6b28b8e1) on that input, with the settings of our
         post-step v4 passes on closed run 3: every op except kskip (the default --ops DEFAULT_OPS: the nine v1 / v2 ops implied,
         closerprep, inlineeq, hintgrind, projpath, lexsurf, jointres, t4ind, ctorsearch, the fourteen v3 ops, the five v4 ops and the
         v5 op hb_smartunfold, in open_post's ORDER; kskip, which writes `set_option debug.skipKernelTC true in`, is off by our
         decision of 2026-11-04 and is not used in our upload; --ops all adds it back; --ops v4 / v3 / v2 / v1 and comma-separated subsets
         as open_post.py reads them; our passes are listed in README.md section 10), every row at once (--jobs = the number of rows),
         the step's wall 7200 s (no row starts after it), a row's wall 2700 s and 240 compiles (open_post's v4su defaults; v2's row
         wall was 3600 s), the sorry guard (LRA_FORCE_WARN_SORRY=1),
         git's safe.directory for this process tree, the `#print axioms` audit (harness/post_support.py), and the reference heartbeats
         file only: the warm-up table data/reference_heartbeats_local.json, which the run's own meter reads for the warm-up-named rows,
         is not read here (scorer.score's table is set empty in this process). Compile slots (LRA_HBTOOL_SLOTS): --compile-slots, default
         this host's (harness/host_knobs.py for one shard: min(32, physical cores)); our v4su passes used 56 on a 64-vCPU host.
         Open files: the ops keep many Lean processes and files open at once; this command raises its own soft limit (RLIMIT_NOFILE)
         to 65536 (our run's `ulimit -n 65536`), or to the hard limit when that is lower (then it warns: raise the hard limit, e.g.
         `ulimit -Hn 65536` as root or in limits.conf; a row that runs out of files stops and keeps its line).
         The step imports one module this package does not have, vendored byte for byte: harness/post/_v2deps/ (its docstring).
Writes   <out>/post_step/ (or --post-dir): the step's input proofs.jsonl, its outputs proofs.post.jsonl, submission.post.jsonl and
         post_report.json, its work files post/.
         <out>/submission.post.jsonl: THE UPLOAD FILE after the step, one {"name", "proof"} line per row in the rows' order. It is
         written only when it passes harness/final_merge.check against the rows and every line that differs from the step's input is a
         row the step adopted; otherwise nothing is written and the input stays the file to upload (submission.jsonl, or the earlier
         pass's <post-dir>/submission.post.jsonl). A later pass replaces it; each pass keeps its own copy in its --post-dir.
         <out>/post_report.json: the step's report plus this command's block "post_step" (also <post-dir>/post_report.json).
Exit     0 written and checked; 1 the step ran but its result failed a check (no submission.post.jsonl); 2 refused before the step.
Not running this command leaves the run's output exactly as it was (it is not part of `run_final.py`)."""
from __future__ import annotations

import argparse, hashlib, json, os, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from harness import final_rows as FR, final_merge as FM, host_knobs as HK  # noqa: E402

SOURCE = "closed-run3"          # the input records' "source" field (a label; the step copies it to "post_from" on an adopted row)
POST_DIR = "post_step"
OUT_FILE = "submission.post.jsonl"
REPORT_FILE = "post_report.json"
SECONDS, ROW_SECONDS, ROW_COMPILES = 7200.0, 2700.0, 240   # harness/open_post.py's (v4su) defaults, as in our passes
NOFILE = 65536          # our run's `ulimit -n`
DEFAULT_OPS = ("implied,closerprep,inlineeq,hintgrind,projpath,lexsurf,jointres,t4ind,ctorsearch,"   # v1 + v2 ops (no kskip)
               "argon_funind,argon_hbelab,argon_hpcert,sonnet_listdrop,sonnet_lintdrop,opus_hoist,opus_stepdrop,opus_rundrop,"
               "opus_scaffold,opus_armfold,opus_goalmerge,opus_patfuse,sonnet_surface,sol_harvest,"   # v3 ops
               "v4_unhyg,hb_hotctl,v4_patelide,v4_rescreen,hb_hotelab,"   # v4 ops
               "hb_smartunfold")   # the v5 op: every op of open_post's ORDER except kskip (2026-11-04)


def resource_inf():
    import resource
    return resource.RLIM_INFINITY


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


def raise_nofile(want: int = NOFILE) -> dict:
    """The process's soft RLIMIT_NOFILE raised to `want` (never lowered), capped by the hard limit: {"soft", "hard", "wanted"}."""
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = want if hard == resource.RLIM_INFINITY else min(want, hard)
    if soft != resource.RLIM_INFINITY and soft < target:
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
        soft = target
    return {"soft": soft, "hard": hard, "wanted": want}


def ops_order(spec: str, order: tuple, v1: tuple, aliases: dict | None = None) -> tuple:
    """--ops as harness/open_post.py main reads it: 'all', 'v1' (, 'v2', 'v3', 'v4': `aliases`) or a comma-separated subset of ORDER
    (in ORDER's order)."""
    if spec == "all":
        return tuple(order)
    if spec == "v1":
        return tuple(v1)
    if aliases and spec in aliases:
        return tuple(aliases[spec])
    want = [x.strip() for x in spec.split(",") if x.strip()]
    bad = [x for x in want if x not in order]
    if bad or not want:
        raise ValueError(f"unknown op(s) {bad}; the ops are {list(order)}")
    return tuple(x for x in order if x in want)


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
    ap.add_argument("--row-seconds", type=float, default=ROW_SECONDS, help="a row's wall (default 2700)")
    ap.add_argument("--row-compiles", type=int, default=ROW_COMPILES, help="a row's compiles (default 240)")
    ap.add_argument("--ops", default=DEFAULT_OPS, help="a comma-separated subset of the ops (default, our passes: every op except kskip, "
                                                       "i.e. no `set_option debug.skipKernelTC`; our last pass: hb_smartunfold), 'all' "
                                                       "(every op, kskip included; not used), 'v4' / 'v3' / 'v2' (open_post's aliases, "
                                                       "kskip included; not used) or 'v1' (kskip, implied, closerprep, inlineeq)")
    ap.add_argument("--input", default=None, help="a later pass: the step's input records, an earlier pass's <post-dir>/proofs.post.jsonl "
                                                  "(default: built from <out>/submission.jsonl and the shards' finals); needs a new "
                                                  "--post-dir")
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
    chain = None
    if a.input:
        chain = Path(a.input).expanduser().resolve()
        if not a.post_dir:
            return refuse("--input needs --post-dir NEW (the first pass's directory is <out>/post_step)")
        try:
            chain_lines = read_jsonl(chain)
        except (OSError, ValueError) as e:
            return refuse(f"--input {chain}: {e}")
        sub_names = [d["name"] for d in read_jsonl(sub)]
        if [d.get("name") for d in chain_lines] != sub_names or not all(isinstance(d.get("proof"), str) for d in chain_lines):
            return refuse(f"--input {chain}: not one record with a proof per line of {sub} (same names, same order)")
        tmpc = post_dir.parent / f".{post_dir.name}.input.{os.getpid()}.jsonl"
        tmpc.parent.mkdir(parents=True, exist_ok=True)
        FM.write([{"name": d["name"], "proof": d["proof"]} for d in chain_lines], tmpc)
        probs = FM.check(tmpc, rows)
        tmpc.unlink()
        if probs:
            return refuse(f"--input {chain} fails the package's upload-file check against {rows_path}: " + "; ".join(probs[:4]))
    if a.problems:
        unknown = sorted(set(a.problems) - {r["name"] for r in rows})
        if unknown:
            return refuse(f"--problems names {len(unknown)} row(s) not in the rows file: {unknown[:3]}")

    # the step's code: the one module this package lacks, registered under its own name first (harness/post/_v2deps), then the step
    # (its module level is constants only; the ops load when it runs) and the op list
    try:
        from harness.post import _v2deps
        vendored = _v2deps.install()
    except (OSError, RuntimeError) as e:
        return refuse(f"harness/post/_v2deps: {e}")
    from harness import open_post as P
    try:
        order = ops_order(a.ops, P.ORDER, P.V1_ORDER, {k: getattr(P, f"{k.upper()}_ORDER") for k in ("v2", "v3", "v4")})
    except ValueError as e:
        return refuse(f"--ops {a.ops}: {e}")

    sub_sha = sha256_file(sub)
    if chain is None:
        lines = read_jsonl(sub)
        finals, finals_read = shard_finals(out, plan)
        text, n_stored = build_input(lines, finals, SOURCE)
    else:   # a later pass: the earlier pass's records as they are (the step's input file gets their bytes)
        text = chain.read_text()
        lines = read_jsonl(chain)
        finals_read, n_stored = [], sum(1 for d in lines if isinstance(d.get("stored_score"), (int, float)))
    post_dir.mkdir(parents=True, exist_ok=True)
    inp = post_dir / "proofs.jsonl"
    inp.write_text(text)
    nofile = raise_nofile()
    if nofile["soft"] != resource_inf() and nofile["soft"] < NOFILE:
        log(f"WARNING: open files limited to {nofile['soft']} (hard limit {nofile['hard']}); our run had {NOFILE}: rows may stop with "
            f"'Too many open files' (they keep their line). Raise the hard limit (ulimit -Hn {NOFILE}) for our run's setting.")
    slots = int(a.compile_slots or HK.knobs(HK.host(), 1, len(rows))["compile_slots"])
    jobs = int(a.jobs or len(lines))
    if chain is None:
        log(f"input {inp}: {len(lines)} row(s) from {sub} (sha256 {sub_sha[:16]}), {n_stored} with the stored score of their final "
            f"({len(finals_read)} finals.json); rows {rows_path}, heartbeats {hbs_path}")
    else:
        log(f"input {inp}: {len(lines)} row(s) from --input {chain} (sha256 {sha256_file(chain)[:16]}), {n_stored} with a stored "
            f"score; rows {rows_path}, heartbeats {hbs_path}")
    log(f"settings: ops {a.ops}, jobs {jobs}, compile slots {slots}, step wall {a.seconds:g} s, row wall {a.row_seconds:g} s, row "
        f"compiles {a.row_compiles}, open files {nofile['soft']}" + (f", only {len(a.problems)} row(s)" if a.problems else ""))

    # the environment of our post-step run (harness/open_post.py main, which imports the open package's module: post_support here)
    from harness.post_support import SORRY_GUARD_ENV, git_trust, audit_proof
    from probe.verify_candidates import newest_first
    os.environ.update(SORRY_GUARD_ENV)
    git_trust(os.environ)
    os.environ["LRA_HBTOOL_SLOTS"] = str(slots)
    import scorer.score as score_mod
    score_mod._LOCAL_REF = {}   # the reference heartbeats file only (open_post's LRA_LOCAL_REF=none; this scorer reads that variable
    #                             as a file path only, so the table is emptied in this process, the step's only Python process)
    P.ORDER = order   # what open_post's own --ops sets (its main is not used here)
    log(f"ops: {', '.join(P.ORDER)}; vendored: {', '.join(vendored) or 'none'}")

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
             "input": {"path": str(chain), "sha256": sha256_file(chain)} if chain is not None else None, "post_dir": str(post_dir),
             "rows": {"path": str(rows_path), "sha256": FR.sha256_file(rows_path)},
             "heartbeats": {"path": str(hbs_path), "sha256": FR.sha256_file(hbs_path)},
             "finals_read": finals_read, "rows_with_stored_score": n_stored, "input_sha256": sha256_file(inp),
             "compile_slots": slots, "jobs": jobs, "ops": list(P.ORDER), "open_files": nofile, "vendored": vendored,
             "changed_rows": [f"row#{k:02d}" for k in changed], "problems": bad,
             "seconds": round(time.time() - t0, 1), "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if bad:
        block["output"] = None
        rep["post_step"] = block
        (out / REPORT_FILE).write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n")
        shutil.copyfile(out / REPORT_FILE, post_dir / REPORT_FILE)
        log("FAILED its checks (" + "; ".join(bad[:4]) + f"): no {OUT_FILE} written; upload {sub}")
        return 1
    tmp = out / f".{OUT_FILE}.{os.getpid()}.tmp"
    shutil.copyfile(cand, tmp)
    os.replace(tmp, out / OUT_FILE)
    block["output"] = {"path": str(out / OUT_FILE), "sha256": sha256_file(out / OUT_FILE)}
    rep["post_step"] = block
    (out / REPORT_FILE).write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n")
    shutil.copyfile(out / REPORT_FILE, post_dir / REPORT_FILE)
    log(f"done in {block['seconds']:.0f} s: {len(changed)} row(s) changed ({', '.join(block['changed_rows']) or 'none'}), stored mean "
        f"{rep.get('stored_mean_before')} -> {rep.get('stored_mean_after')}; upload {out / OUT_FILE} (sha256 "
        f"{block['output']['sha256'][:16]}; checked); report {out / REPORT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
