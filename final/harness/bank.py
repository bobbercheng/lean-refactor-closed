#!/usr/bin/env python3
"""Per-row candidate bank (b63 launch set item 1; docs/adaptive_plan_93.md §4.1, logging contract docs/b63_logging_contract.md §2).

`<work root>/<row ws>/bank.jsonl`: one line per distinct compiling candidate of the row, from EVERY producer (ladder sessions through
agent.py --pool, the router's checkpoint cleanups and crossover, the end stage's families), so the end stage, the crossover and the
SHOWN block read one ledger instead of the per-run pool files. Fields (contract §2): sha (12 hex of the stripped text), source
(session:<run id> | clean@k | crossover | end:<stage> | family:<name> | seed), tokens, heartbeats, Z, compat (Z per pin, {pin: ok}; None
when the producer assumed Z), score (exact when the producer had one), klass (structural class tag, class_tag()), parent (sha of the
proof it was derived from, None for a seed or an unknown lineage), run_id, at. The text itself is in `proof`.

Pure functions over the entries: best(), pareto() (non-dominated on tokens x heartbeats at the top Z), class_spread() (how many
structural classes the bank holds: the SELECT rule keeps a runner-up only if it is of another class), pareto_delta() (what a new
entry adds over the bank's best score). Nothing here compiles or calls a model; the writers are agent._pool_add (sessions), router
(clean / crossover / end) and endstage (families, through the caller).

    python3 harness/bank.py <bank.jsonl|work root/ws dir> [--json]   # a readout: entries, classes, Pareto front, best
"""
from __future__ import annotations

import fcntl, hashlib, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FILE = "bank.jsonl"
FIELDS = ("sha", "source", "tokens", "heartbeats", "Z", "compat", "score", "klass", "parent", "run_id", "at", "proof")


def sha(text: str) -> str:
    return hashlib.sha256(text.rstrip().encode()).hexdigest()[:12]


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---- structural class tag -------------------------------------------------------------------------------------------------------------
_W = r"(?<![\w.'])"
_CASE = re.compile(_W + r"(?:case|case'|next|rcases|cases|induction|fun_induction|match)(?![\w'])")
_CALC = re.compile(_W + r"calc(?![\w'])")
_SIMP = re.compile(_W + r"(?:simp|simp_all|simpa|dsimp|simp_rw|norm_num|field_simp)(?![\w'?!])")
_EXT = re.compile(_W + r"(?:ext|funext|congr|gcongr|LinearMap\.ext|Basis\.ext)(?![\w'])")
_AUTO = re.compile(_W + r"(?:grind|aesop|omega|linarith|nlinarith|positivity|decide|tauto)(?![\w'?!])")
_HAVE = re.compile(_W + r"(?:have|let|obtain|suffices|show)(?![\w'])")


def class_tag(proof: str, statement: str | None = None) -> str:
    """A coarse structural class of a proof text, for the bank's class spread and the SELECT rule (plan §1.2): term | tactic + the dominant
    device among case-split / calc / ext / simp / auto / have-chain / plain, with a size bucket (the body's line count: s < 6, m < 20, l).
    Text only (no Lean); the same proof always gets the same tag; the tag never carries a name."""
    body = proof
    if statement and proof.startswith(statement):
        body = proof[len(statement):]
    elif not statement:   # no statement given: the body starts at `:= by` when there is one, else at the first `:=`
        m = re.search(r":=\s*by(?![\w'])", proof) or re.search(r":=", proof)
        body = proof[m.start():] if m else proof
    body = re.sub(r"--[^\n]*", "", body)
    lines = [l for l in body.splitlines() if l.strip()]
    size = "s" if len(lines) < 6 else "m" if len(lines) < 20 else "l"
    stripped = body.strip().lstrip(":=").strip()
    if not re.match(r"by(?![\w'])", stripped):
        return f"term/{size}"
    counts = {"case": len(_CASE.findall(body)), "calc": len(_CALC.findall(body)), "ext": len(_EXT.findall(body)),
              "simp": len(_SIMP.findall(body)), "auto": len(_AUTO.findall(body)), "have": len(_HAVE.findall(body))}
    arms = body.count("·") + body.count("| ")
    if counts["calc"]:
        dev = "calc"
    elif counts["case"] >= 1 and arms >= 2:
        dev = "cases"
    elif counts["ext"]:
        dev = "ext"
    elif counts["have"] >= 3:
        dev = "haves"
    elif counts["simp"] >= 2 and counts["simp"] >= counts["auto"]:
        dev = "simp"
    elif counts["auto"]:
        dev = "auto"
    else:
        dev = "plain"
    return f"tactic:{dev}/{size}"


# ---- entries -------------------------------------------------------------------------------------------------------------------------
def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def entry(proof: str, source: str, *, tokens=None, heartbeats=None, Z=None, compat=None, score=None, parent=None, run_id=None,
          statement: str | None = None, klass: str | None = None, at: str | None = None) -> dict:
    """One bank line. Z is taken from compat when given (the share of pins that compile); compat None = the producer assumed Z."""
    if compat and Z is None:
        oks = [bool(v) for v in compat.values()]
        Z = round(100.0 * sum(oks) / len(oks), 4) if oks else None
    return {"sha": sha(proof), "source": str(source), "tokens": None if tokens is None else int(tokens),
            "heartbeats": None if heartbeats is None else int(heartbeats), "Z": _num(Z), "compat": dict(compat) if compat else None,
            "score": _num(score), "klass": klass or class_tag(proof, statement), "parent": parent, "run_id": run_id, "at": at or now(),
            "proof": proof.rstrip()}


def file_of(root) -> Path:
    p = Path(root)
    return p if p.suffix == ".jsonl" else p / FILE


def read(root) -> list[dict]:
    """Every readable entry of a bank file (or of the bank in a row's directory); [] when absent. Duplicate shas keep the first line and
    merge the later lines' sources."""
    f = file_of(root)
    try:
        text = f.read_text()
    except OSError:
        return []
    out: dict[str, dict] = {}
    for l in text.splitlines():
        try:
            d = json.loads(l)
        except ValueError:
            continue
        if not isinstance(d, dict) or not isinstance(d.get("proof"), str) or not d.get("proof").strip():
            continue
        h = d.get("sha") or sha(d["proof"])
        d["sha"] = h
        cur = out.get(h)
        if cur is None:
            d.setdefault("sources", [d.get("source")])
            out[h] = d
        else:
            if d.get("source") and d["source"] not in cur.setdefault("sources", [cur.get("source")]):
                cur["sources"].append(d["source"])
            if d.get("compat") and not cur.get("compat"):   # a later line with the per-pin reading fills a provisional one
                cur.update({k: d[k] for k in ("score", "tokens", "heartbeats", "Z", "compat") if d.get(k) is not None})
            elif cur.get("score") is None and d.get("score") is not None:
                cur.update({k: d[k] for k in ("score", "tokens", "heartbeats", "Z") if d.get(k) is not None})
    return list(out.values())


def add(root, e: dict) -> bool:
    """Append one entry unless its sha is already in the file (locked append: several sessions of a row may write at once); a line that
    brings a per-pin compat for a sha whose lines have none is appended too (read() merges it into the first line). True when written."""
    f = file_of(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    e = {k: e.get(k) for k in FIELDS}
    if not e.get("proof"):
        return False
    e["sha"] = e.get("sha") or sha(e["proof"])
    e["at"] = e.get("at") or now()
    with f.open("a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.seek(0)
            for l in fh:
                try:
                    d = json.loads(l)
                except ValueError:
                    continue
                if d.get("sha") == e["sha"] and not (e.get("compat") and not d.get("compat")) and not (e.get("score") is not None and d.get("score") is None):
                    return False   # a later line that brings a compat or a score to a provisional / unscored line is appended (read() merges)
            fh.seek(0, 2)
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
            fh.flush()
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    return True


def add_many(root, entries) -> int:
    return sum(1 for e in entries if add(root, e))


# ---- views ---------------------------------------------------------------------------------------------------------------------------
def scored(entries) -> list[dict]:
    return [e for e in entries if _num(e.get("score")) is not None]


def best(entries) -> dict | None:
    s = scored(entries)
    return max(s, key=lambda e: (float(e["score"]), -(e.get("tokens") or 0))) if s else None


def top_z(entries) -> float | None:
    zs = [_num(e.get("Z")) for e in entries if _num(e.get("Z")) is not None]
    return max(zs) if zs else None


def pareto(entries) -> list[dict]:
    """The non-dominated entries on (tokens, heartbeats), fewer is better, among those at the bank's top Z (entries without a Z count as the
    top Z: a provisional reading is not a known regression); entries without both numbers are left out. Fewest tokens first."""
    z = top_z(entries)
    pool = [e for e in entries if e.get("tokens") is not None and e.get("heartbeats") is not None
            and (z is None or _num(e.get("Z")) is None or _num(e["Z"]) >= z - 1e-9)]
    out = []
    for e in pool:
        t, h = int(e["tokens"]), int(e["heartbeats"])
        dominated = any((int(o["tokens"]) <= t and int(o["heartbeats"]) <= h) and (int(o["tokens"]) < t or int(o["heartbeats"]) < h) for o in pool)
        if not dominated:
            out.append(e)
    return sorted(out, key=lambda e: (int(e["tokens"]), int(e["heartbeats"])))


def class_spread(entries) -> dict:
    out: dict = {}
    for e in entries:
        k = e.get("klass") or class_tag(e.get("proof") or "")
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def pareto_delta(entries, new: dict) -> float | None:
    """What `new` adds over the bank's best score (positive: a new top; None when either side has no score)."""
    b = best(entries)
    if b is None or _num(new.get("score")) is None:
        return None
    return round(float(new["score"]) - float(b["score"]), 4)


def runner_up(entries, within: float = 1.0) -> dict | None:
    """SELECT (plan §1.2): the best entry of ANOTHER structural class within `within` points of the best, else None."""
    b = best(entries)
    if b is None:
        return None
    others = [e for e in scored(entries) if e.get("klass") != b.get("klass") and float(b["score"]) - float(e["score"]) <= within]
    return max(others, key=lambda e: float(e["score"])) if others else None


def summary(entries) -> dict:
    b = best(entries)
    return {"entries": len(entries), "scored": len(scored(entries)), "classes": class_spread(entries), "pareto": len(pareto(entries)),
            "best": None if b is None else {k: b.get(k) for k in ("sha", "source", "score", "tokens", "heartbeats", "Z", "klass")},
            "sources": sorted({str(e.get("source")).split(":")[0] for e in entries}), "top_z": top_z(entries)}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    es = read(a.path)
    s = summary(es)
    if a.json:
        print(json.dumps(s, indent=1))
    else:
        print(f"{len(es)} entries, {s['scored']} scored, classes {s['classes']}, pareto {s['pareto']}, best {s['best']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
