#!/usr/bin/env python3
"""b66 closed package (retro A1, docs/retro_from_seed_gap.md section 4; 2026-10-27): ANY benchmark rows file -> the hx_heldout set
"final-clean". The organizers' final (Nov 1: 60 rows = warm-up 15 + new + LeanPool) comes as a JSONL in the warm-up file's schema; nothing
here knows a row by name: the same code stages the final, a dev pool or a rehearsal slice.

  check   validate the rows (schema, unique names, the seed starts with the statement, toolchain tags, a known source) and, with --envs,
          that every (source, toolchain) pin resolves to a built environment at the pinned commit (envs/<source>-<toolchain>, PutnamBench:
          envs/mathlib-<toolchain>)
  stage   copy the rows and their reference heartbeats to data/final/rows.jsonl + heartbeats.jsonl (+ STAGED.json: input sha256, counts,
          where the heartbeats came from). Heartbeats: --heartbeats FILE ({"name", "heartbeat"} lines, the warm-up release's format), else a
          row's own "heartbeat" field, else MEASURED here: the seed (`src`) compiled on the row's newest pin through the scorer (the same
          reading scorer/calibrate.py takes; our score's H is a ratio to it, so the counter's offset cancels). Re-staging identical input
          is a no-op; a different file over a staged one is refused unless --force (a run in progress reads data/final/ at every phase)
  split   the shard plan: k shards of ceil/floor(n/k) rows, balanced by seed length (longest first onto the lightest shard; seed tokens
          are the best cheap proxy of a row's session and compile time), each shard's names in the file's order; deterministic

    python3 harness/final_rows.py check --rows ROWS.jsonl [--envs]
    python3 harness/final_rows.py stage --rows ROWS.jsonl [--heartbeats HB.jsonl] [--jobs 3] [--force]
    python3 harness/final_rows.py split --rows ROWS.jsonl --shards 4
Measuring compiles: run it in a memory-capped unit (never from an interactive shell)."""
from __future__ import annotations

import argparse, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STAGE_DIR = ROOT / "data/final"       # hx_heldout SETS["final-clean"] reads data/final/rows.jsonl + heartbeats.jsonl
ROWS_FILE, HB_FILE, STAGED = "rows.jsonl", "heartbeats.jsonl", "STAGED.json"
# the six libraries of the closed track (organizer 2026-10-24: LeanPool is the sixth); scorer.compile resolves the env of each
SOURCES = ("putnambench", "strata", "cslib", "physlib", "arklib", "leanpool")
REQUIRED = ("name", "source", "statement", "src", "proof_length", "version_info")
TOOLCHAIN = re.compile(r"^v\d+\.\d+\.\d+(?:-rc\d+)?$")
COMMIT = re.compile(r"^[0-9a-f]{7,40}$")


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path) -> list[dict]:
    """The rows of a JSONL file (blank lines skipped); a line that is not a JSON object raises ValueError with its line number."""
    rows = []
    for i, l in enumerate(Path(path).read_text().splitlines(), 1):
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except ValueError as e:
            raise ValueError(f"{path}:{i}: not JSON ({e})") from None
        if not isinstance(r, dict):
            raise ValueError(f"{path}:{i}: not a JSON object")
        rows.append(r)
    return rows


def pins(row: dict) -> list[tuple[str, str]]:
    """[(toolchain, commit)] of a row, in the listed order."""
    out = []
    for vi in row.get("version_info") or []:
        if isinstance(vi, dict):
            out += [(str(v), str(c)) for v, c in vi.items()]
    return out


def env_key(source: str, toolchain: str) -> str:
    """The envs/ directory a pin compiles in (scorer.compile.env_dir / project_env_dir)."""
    return f"mathlib-{toolchain}" if source == "putnambench" else f"{source}-{toolchain}"


def validate(rows: list[dict]) -> tuple[list[str], list[str]]:
    """(errors, warnings). Errors refuse a run (a row the pipeline cannot read); warnings do not (the seed is still written for that row).
    Messages name a row by its position (row#NN), never by name: the same check runs on sealed slices."""
    errs, warns, seen = [], [], set()
    if not rows:
        errs.append("no rows")
    for k, r in enumerate(rows):
        tag = f"row#{k:02d}"
        miss = [f for f in REQUIRED if f not in r]
        if miss:
            errs.append(f"{tag}: missing {', '.join(miss)}"); continue
        if not isinstance(r["name"], str) or not r["name"].strip():
            errs.append(f"{tag}: empty name"); continue
        if r["name"] in seen:
            errs.append(f"{tag}: duplicate name (an earlier row has it)")
        seen.add(r["name"])
        if r["source"] not in SOURCES:
            errs.append(f"{tag}: unknown source {r['source']!r} (known: {', '.join(SOURCES)}; a new project needs its env and "
                        "scorer.compile.PROJECT_DIRS entry)")
        if r["source"] != "putnambench" and not r.get("file_path"):
            errs.append(f"{tag}: a {r['source']} row needs file_path (the module the declaration lives in)")
        if r["source"] == "putnambench" and not isinstance(r.get("header"), str):
            errs.append(f"{tag}: a putnambench row needs header (its imports)")
        p = pins(r)
        if not p:
            errs.append(f"{tag}: version_info lists no toolchain")
        for v, c in p:
            if not TOOLCHAIN.match(v):
                errs.append(f"{tag}: toolchain tag {v!r} is not vX.Y.Z[-rcN]")
            if not COMMIT.match(c):
                errs.append(f"{tag}: pin {c!r} of {v} is not a commit sha")
        if len({v for v, _ in p}) != len(p):
            errs.append(f"{tag}: a toolchain is listed twice")
        if not isinstance(r["proof_length"], int) or r["proof_length"] <= 0:
            errs.append(f"{tag}: proof_length must be a positive integer")
        if not isinstance(r["src"], str) or not r["src"].strip() or not isinstance(r["statement"], str) or not r["statement"].strip():
            errs.append(f"{tag}: empty src or statement"); continue
        from scorer.tokenize import split_declaration
        body = split_declaration(r["src"].rstrip(), r["statement"])
        if body is None:
            warns.append(f"{tag}: the seed does not start with the statement (its line is the seed anyway; every candidate must match)")
        else:
            from scorer.forbidden import check_forbidden
            bad = check_forbidden(body)
            if bad:
                warns.append(f"{tag}: the seed itself has a forbidden construct ({bad})")
    return errs, warns


def env_status(rows: list[dict], envs_dir: Path | None = None) -> list[dict]:
    """One record per (source, toolchain) pin the rows list: env dir, built (a lakefile, not a *.git-main clone), HEAD = pin (or the tracked
    files equal the pin: HEAD can move without the files, envs/manifest.py), and how many rows need it. Sorted by env key."""
    envs_dir = Path(envs_dir or ROOT / "envs")
    need: dict = {}
    for r in rows:
        for v, c in pins(r):
            e = need.setdefault(env_key(r["source"], v), {"env": env_key(r["source"], v), "source": r["source"], "toolchain": v, "pins": set(), "rows": 0})
            e["pins"].add(c); e["rows"] += 1
    out = []
    for k in sorted(need):
        e = need[k]; d = envs_dir / k; real = d.resolve()
        built = real.is_dir() and any((real / f).exists() for f in ("lakefile.lean", "lakefile.toml"))
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=real, capture_output=True, text=True).stdout.strip() if built else ""
        pin_ok = None
        if built and len(e["pins"]) == 1:
            want = next(iter(e["pins"]))
            pin_ok = head.startswith(want) or want.startswith(head) if head else False
            if not pin_ok:   # the tracked files may still equal the pin (what a compile reads)
                pin_ok = subprocess.run(["git", "diff", "--quiet", want, "--"], cwd=real, capture_output=True).returncode == 0
        elif built:
            pin_ok = False   # two rows pin one toolchain at two commits: one env cannot serve both
        out.append({"env": k, "source": e["source"], "toolchain": e["toolchain"], "pins": sorted(e["pins"]), "rows": e["rows"],
                    "exists": d.exists() or d.is_symlink(), "built": built, "head": head[:12], "pin_ok": pin_ok,
                    "ok": bool(built and pin_ok)})
    return out


# ---------------------------------------------------------------------------------------------------------------------------- heartbeats
def heartbeats_for(rows: list[dict], hb_path=None) -> tuple[dict, str]:
    """({name: reference heartbeats} for the rows that have one, where they came from): --heartbeats FILE first, else the rows' own
    "heartbeat" fields. Rows without one are measured by measure() (stage)."""
    names = {r["name"] for r in rows}
    if hb_path:
        d = {}
        for l in Path(hb_path).read_text().splitlines():
            if l.strip():
                h = json.loads(l)
                if h.get("name") in names and isinstance(h.get("heartbeat"), (int, float)) and h["heartbeat"] > 0:
                    d[h["name"]] = int(h["heartbeat"])
        return d, f"file {Path(hb_path).name}"
    d = {r["name"]: int(r["heartbeat"]) for r in rows if isinstance(r.get("heartbeat"), (int, float)) and r["heartbeat"] > 0}
    return d, "rows"


def measure(rows: list[dict], jobs: int = 3, log=print) -> dict:
    """{name: heartbeats} of each row's seed on its newest pin, measured through the scorer (memgate-admitted compiles, `jobs` at once).
    A row whose seed does not compile there is left out (the caller refuses: a row without a reference has no H)."""
    from concurrent.futures import ThreadPoolExecutor
    from scorer.compile import compile_putnam, compile_project
    from probe.verify_candidates import newest_first

    def one(k_r):
        k, r = k_r
        v = newest_first(r["version_info"])[0]
        t = time.time()
        res = compile_putnam(r["header"], r["src"], v, timeout=1800) if r["source"] == "putnambench" else compile_project(r, r["src"], v, timeout=1800)
        log(f"row#{k:02d}: reference on {v}: ok={res.ok} heartbeats={res.heartbeats} ({time.time() - t:.0f}s)")
        return r["name"], (res.heartbeats if res.ok and res.heartbeats else None)
    with ThreadPoolExecutor(max(1, int(jobs))) as ex:
        got = dict(ex.map(one, list(enumerate(rows))))
    return {n: int(h) for n, h in got.items() if h}


def stage(rows_path, hb_path=None, *, dest: Path | None = None, jobs: int = 3, force: bool = False, log=print) -> dict:
    """Validate and copy the rows (+ heartbeats) to dest (default data/final/). Returns the STAGED.json record. Raises SystemExit with the
    reason on a refusal (validation errors, a row without reference heartbeats, a different staged file without force)."""
    dest = Path(dest or STAGE_DIR)
    rows = load(rows_path)
    errs, warns = validate(rows)
    for w in warns:
        log(f"warning: {w}")
    if errs:
        raise SystemExit("rows refused:\n  " + "\n  ".join(errs))
    sha = sha256_file(rows_path)
    old = None
    try:
        old = json.loads((dest / STAGED).read_text())
    except (OSError, ValueError):
        pass
    if old and old.get("sha256") == sha and (dest / ROWS_FILE).exists() and (dest / HB_FILE).exists():
        log(f"rows already staged in {dest} ({old['rows']} row(s), sha256 {sha[:12]}): unchanged")
        return old
    if old and old.get("sha256") != sha and not force:
        raise SystemExit(f"{dest} holds another rows file (sha256 {str(old.get('sha256'))[:12]}, {old.get('rows')} rows); a run reading it would "
                         "change under its feet: use a new checkout, or --force once no run uses it")
    hbs, how = heartbeats_for(rows, hb_path)
    missing = [r for r in rows if r["name"] not in hbs]
    if missing:
        log(f"measuring the reference heartbeats of {len(missing)} row(s) (seed on its newest pin, {jobs} at once)")
        got = measure(missing, jobs=jobs, log=log)
        hbs.update(got)
        how = f"{how} + measured {len(got)}" if len(got) < len(rows) else "measured"
        still = [k for k, r in enumerate(rows) if r["name"] not in hbs]
        if still:
            raise SystemExit(f"no reference heartbeats for {len(still)} row(s) ({', '.join(f'row#{k:02d}' for k in still[:10])}): their seed "
                             "did not compile on its newest pin (check the envs: python3 harness/final_rows.py check --rows ... --envs)")
    dest.mkdir(parents=True, exist_ok=True)

    def atomic(name, text):
        tmp = dest / f".{name}.{os.getpid()}.tmp"; tmp.write_text(text); os.replace(tmp, dest / name)
    atomic(ROWS_FILE, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    atomic(HB_FILE, "".join(json.dumps({"name": r["name"], "heartbeat": hbs[r["name"]]}) + "\n" for r in rows))
    rec = {"source_file": str(Path(rows_path).resolve()), "sha256": sha, "rows": len(rows), "heartbeats": how,
           "sources": {s: sum(1 for r in rows if r["source"] == s) for s in sorted({r["source"] for r in rows})},
           "warnings": len(warns), "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    atomic(STAGED, json.dumps(rec, indent=1) + "\n")
    log(f"staged {len(rows)} row(s) into {dest} (heartbeats: {how}; sources {rec['sources']})")
    return rec


# ---------------------------------------------------------------------------------------------------------------------------- shards
def split(rows: list[dict], k: int) -> list[list[str]]:
    """k shards (at most one per row) of ceil/floor(n/k) rows each, balanced by seed tokens (proof_length): the rows longest first, each onto
    the lightest shard that still has room (ties: the lower index). Each shard lists its names in the rows file's order."""
    n = len(rows)
    k = max(1, min(int(k), n))
    cap = [n // k + (1 if i < n % k else 0) for i in range(k)]
    load_, members = [0] * k, [[] for _ in range(k)]
    order = sorted(range(n), key=lambda i: (-int(rows[i].get("proof_length") or 0), i))
    for i in order:
        j = min((s for s in range(k) if len(members[s]) < cap[s]), key=lambda s: (load_[s], s))
        members[j].append(i); load_[j] += int(rows[i].get("proof_length") or 0)
    return [[rows[i]["name"] for i in sorted(m)] for m in members]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "stage", "split"])
    ap.add_argument("--rows", required=True); ap.add_argument("--heartbeats")
    ap.add_argument("--envs", action="store_true", help="check: also every pin's environment")
    ap.add_argument("--jobs", type=int, default=3, help="stage: reference compiles at once (when heartbeats must be measured)")
    ap.add_argument("--force", action="store_true"); ap.add_argument("--shards", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "stage":
        stage(a.rows, a.heartbeats, jobs=a.jobs, force=a.force)
        return 0
    rows = load(a.rows)
    if a.cmd == "split":
        for i, s in enumerate(split(rows, a.shards)):
            print(f"shard {i + 1}: {len(s)} row(s), {sum(r['proof_length'] for r in rows if r['name'] in set(s))} seed tokens")
        return 0
    errs, warns = validate(rows)
    for w in warns:
        print("warning:", w)
    for e in errs:
        print("ERROR:", e)
    bad = 0
    if a.envs and not errs:
        for e in env_status(rows):
            print(f"{'ok ' if e['ok'] else 'BAD'} {e['env']:24s} rows {e['rows']:3d}  built {e['built']}  head {e['head'] or '-':12s} "
                  f"pin {','.join(p[:12] for p in e['pins'])}  pin_ok {e['pin_ok']}")
            bad += not e["ok"]
    print(f"{len(rows)} row(s): {len(errs)} error(s), {len(warns)} warning(s)" + (f", {bad} environment(s) missing or off-pin" if a.envs else ""))
    return 1 if errs or bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
