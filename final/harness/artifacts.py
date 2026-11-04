#!/usr/bin/env python3
"""Compiled artifacts and near-misses: the only inputs of a paid route (b63 item 16; docs/adaptive_plan_93.md §1.1 C1, §1.4; logging
contract §2 cpu_pass.json).

Governing rule (plan §0): paid work after the common ladder starts only from a COMPILED artifact; no artifact -> no paid route. This module
defines the record shape the C1 pass / sessions write and the router reads, nothing here compiles or calls a model.

Record shape (one JSON object; stored under `artifacts` of rows/<ws>.cpu_pass.json (router) or <ws>/cpu_pass.json (C0), as
{"skeletons": [...], "near_misses": [...]}; dedup by sha):
  skeleton   {"type": "skeleton", "sha", "kind": template | transpiled | fold-skeleton | rebuild | flattened | draft | skeleton,
              "text": the declaration with `sorry` holes (statement byte-identical to the row's), "holes": [{"hole_id": k (1-based, in
              text order), "line": 1-based line in the text, "goal": the hole's goal digest}], "errors": [] (a skeleton with a real error
              is not compiled), "tokens_est": tokens of the body with the holes counted, "source": "<family | session:<run id> | step>",
              "parent": sha of the proof it was derived from or None, "structural": bool (a different structural class than the row's
              best: bank.class_tag differs), "at"}
  near_miss  {"type": "near_miss", "sha", "text": the full candidate (no sorry), "first_error": the first compile error (digest), "open_goals":
              [goal digests parsed from the error messages, <= 3 kept; [] when the error is not an unsolved-goals error],
              "open_goals_source": "error-digest" | "goal-map", "technique": a free label (the family / op that made it, or None),
              "source", "parent", "at"}

Routes (plan §1.4; route_for()):
  REPAIR            a skeleton with 1..REPAIR_MAX_HOLES holes, or >= REPAIR_MIN_NEAR_MISSES near-misses each with <= REPAIR_MAX_OPEN_GOALS
                    open goals (classes c3/c5 when a diagnosis exists; without one the artifact shape alone decides)
  ARTIFACT-SESSION  a skeleton with REPAIR_MAX_HOLES+1..SESSION_MAX_HOLES holes, or a structurally different skeleton (any hole count up
                    to SESSION_MAX_HOLES) of kind template / transpiled / rebuild / fold-skeleton / flattened (classes c2/c4)
  none              no artifact, no near-miss (polish-only; the flex rule and the review)
Every decision carries the artifact's sha and a reason string, for route.json / decisions.jsonl (contract §2).
"""
from __future__ import annotations

import hashlib, json, re, time
from pathlib import Path

REPAIR_MAX_HOLES = 3
SESSION_MAX_HOLES = 6
REPAIR_MIN_NEAR_MISSES = 2
REPAIR_MAX_OPEN_GOALS = 3
MAX_KEEP = 12            # records of each type kept per row (newest first)
STRUCTURAL_KINDS = ("template", "transpiled", "rebuild", "fold-skeleton", "flattened")
_SORRY = re.compile(r"(?<![\w'])sorry(?![\w'])")
_GOAL_LINE = re.compile(r"(?m)^\s*⊢\s*(.+)$")


def sha(text: str) -> str:
    return hashlib.sha256(text.rstrip().encode()).hexdigest()[:12]


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def holes_of(text: str) -> list[dict]:
    """The `sorry` holes of a text in order: hole_id (1-based) and line (1-based). Goals are filled by the caller (goals.skeleton_check)."""
    out = []
    for li, line in enumerate(text.split("\n"), 1):
        for _ in _SORRY.finditer(line):
            out.append({"hole_id": len(out) + 1, "line": li, "goal": None})
    return out


def fill_hole(text: str, hole_id: int, fill: str) -> str | None:
    """The text with its hole_id-th `sorry` (text order) replaced by `fill`; None when there is no such hole. A multi-line fill in a tactic
    hole is indented to the hole's column."""
    n = 0
    for m in _SORRY.finditer(text):
        n += 1
        if n == int(hole_id):
            col = m.start() - (text.rfind("\n", 0, m.start()) + 1)
            fl = fill.strip("\n")
            if "\n" in fl:
                # the fill's own relative indentation is kept (a nested block under its first line must stay deeper): the continuation
                # lines are dedented by their common margin and re-indented to the hole's column (review 2026-10-25: lstrip flattened them)
                lines = fl.split("\n")
                rest = [l for l in lines[1:] if l.strip()]
                margin = min((len(l) - len(l.lstrip()) for l in rest), default=0)
                fl = lines[0] + "\n" + "\n".join(" " * col + l[margin:] if l.strip() else l for l in lines[1:])
            return text[:m.start()] + fl + text[m.end():]
    return None


_DIGEST_GOAL = re.compile(r"⊢ (.*?)(?= ‖ | case \S+ |$)")


def open_goals_from_error(err: str, limit: int = REPAIR_MAX_OPEN_GOALS + 1) -> list[str]:
    """Goal digests (the `⊢ ...` goals) in an `unsolved goals` style error text; [] for any other error. Both forms: Lean's multi-line message
    (one `⊢` line per goal) and the one-line digest every stored error is (harness/leantools.digest_error: whitespace collapsed, goals as
    `⊢ goal` joined by ` ‖ ` or ` case <tag> `). Review 2026-10-25: only the multi-line form was parsed, so no stored near-miss ever carried
    an open goal (G8 census: 0 of 214, while 77 of their first errors hold a `⊢`) and the <= 3 open-goals condition was never applied."""
    if not err or "⊢" not in err:
        return []
    gs = _GOAL_LINE.findall(err) if "\n" in err.strip() else []
    if not gs:
        gs = _DIGEST_GOAL.findall(re.sub(r"\s+", " ", err).strip())
    return [g for g in (re.sub(r"\s+", " ", x).strip()[:200] for x in gs) if g][:limit]


def skeleton(text: str, holes: list[dict] | None, source: str, kind: str = "skeleton", *, errors=None, parent: str | None = None,
             tokens_est: int | None = None, structural: bool | None = None, best_text: str | None = None, at: str | None = None) -> dict:
    text = text.rstrip()
    hs = holes if holes is not None else holes_of(text)
    hs = [{"hole_id": int(h.get("hole_id") or i + 1), "line": h.get("line"), "goal": (h.get("goal") or None)} for i, h in enumerate(hs)]
    if structural is None and best_text is not None:
        from harness.bank import class_tag
        structural = class_tag(text) != class_tag(best_text)
    return {"type": "skeleton", "sha": sha(text), "kind": kind, "text": text, "holes": hs, "errors": list(errors or []), "tokens_est": tokens_est,
            "source": str(source), "parent": parent, "structural": bool(structural) if structural is not None else None, "at": at or now()}


def near_miss(text: str, first_error: str | None, source: str, *, open_goals=None, technique: str | None = None, parent: str | None = None,
              at: str | None = None) -> dict:
    text = text.rstrip()
    og = list(open_goals) if open_goals is not None else open_goals_from_error(first_error or "")
    return {"type": "near_miss", "sha": sha(text), "text": text, "first_error": (first_error or "")[:400], "open_goals": og[:REPAIR_MAX_OPEN_GOALS + 1],
            "open_goals_source": "goal-map" if open_goals is not None else "error-digest", "technique": technique, "source": str(source),
            "parent": parent, "at": at or now()}


# ---- storage (the `artifacts` key of a cpu_pass.json) --------------------------------------------------------------------------------
def read(path) -> dict:
    """{"skeletons": [...], "near_misses": [...]} from a cpu_pass.json (or a directory holding one); empty lists when absent."""
    p = Path(path)
    if p.is_dir():
        p = p / "cpu_pass.json"
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        return {"skeletons": [], "near_misses": []}
    a = d.get("artifacts") or {}
    return {"skeletons": [x for x in a.get("skeletons") or [] if isinstance(x, dict) and x.get("text")],
            "near_misses": [x for x in a.get("near_misses") or [] if isinstance(x, dict) and x.get("text")]}


def write(path, records: list[dict], keep: int = MAX_KEEP) -> dict:
    """Merge records into the `artifacts` of a cpu_pass.json (created as a stub when absent): dedup by sha (the first record of a sha is kept
    and its holes/goals filled from a later one), newest `keep` of each type. Returns the stored artifacts. Atomic write."""
    p = Path(path)
    if p.is_dir():
        p = p / "cpu_pass.json"
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        d = {"problem": None, "passes": {}, "stub": True, "note": "artifacts only (no CPU pass record yet)"}
    a = d.setdefault("artifacts", {"skeletons": [], "near_misses": []})
    a.setdefault("skeletons", []); a.setdefault("near_misses", [])
    for r in records:
        if not isinstance(r, dict) or not r.get("text"):
            continue
        key = "skeletons" if r.get("type") == "skeleton" else "near_misses"
        r = dict(r); r["sha"] = r.get("sha") or sha(r["text"])
        cur = next((x for x in a[key] if x.get("sha") == r["sha"]), None)
        if cur is None:
            a[key].append(r)
        else:
            if key == "skeletons" and any(h.get("goal") for h in r.get("holes") or []) and not any(h.get("goal") for h in cur.get("holes") or []):
                cur["holes"] = r["holes"]
            if r.get("source") and r["source"] not in str(cur.get("source")):
                cur["source"] = f"{cur.get('source')}+{r['source']}"
    for key in ("skeletons", "near_misses"):
        a[key] = sorted(a[key], key=lambda x: str(x.get("at") or ""), reverse=True)[:keep]
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1)); tmp.replace(p)
    return a


def collect_from_session(ws_dir, statement: str | None = None, best_text: str | None = None) -> list[dict]:
    """Records from a session work dir (agent.py --pool writes <ws>/skeletons.jsonl for every lean_skeleton draft that elaborated without a
    real error, and <ws>/near_misses.jsonl for every full candidate that failed to compile)."""
    d = Path(ws_dir); out = []
    for fn, mk in (("skeletons.jsonl", "skeleton"), ("near_misses.jsonl", "near_miss")):
        f = d / fn
        try:
            lines = f.read_text().splitlines()
        except OSError:
            continue
        for l in lines[-MAX_KEEP * 3:]:
            try:
                r = json.loads(l)
            except ValueError:
                continue
            if not isinstance(r, dict) or not r.get("text"):
                continue
            if statement is not None and not r["text"].lstrip().startswith(statement):
                continue   # the statement must be byte-identical (the scorer's rule); anything else is not an artifact of this row
            src = f"session:{r.get('run_id') or '?'}"
            if mk == "skeleton":
                out.append(skeleton(r["text"], r.get("holes"), src, kind=r.get("kind") or "draft", errors=r.get("errors"), parent=r.get("parent"),
                                    tokens_est=r.get("tokens_est"), best_text=best_text, at=r.get("at")))
            else:
                out.append(near_miss(r["text"], r.get("first_error"), src, open_goals=r.get("open_goals"), technique=r.get("technique"),
                                     parent=r.get("parent"), at=r.get("at")))
    return out


# ---- the route -------------------------------------------------------------------------------------------------------------------------
def _n_holes(s: dict) -> int:
    return len(s.get("holes") or holes_of(s.get("text") or ""))


def route_for(arts: dict, classes: dict | None = None, best_sha: str | None = None) -> dict:
    """The paid route an artifact set supports (plan §1.4): {"kind": "repair" | "artifact-session" | None, "artifact": record or None,
    "near_misses": [records] (repair over near-misses), "reason": str, "candidates": counts}. Pure. A skeleton whose sha is the row's best
    (holes 0) is not an artifact. Classes (c1..c6 scores, harness/diagnose.py when it exists) only ORDER the two routes when both are
    possible: c2/c4 >= 0.5 prefers the session, else repair first."""
    sk = [s for s in arts.get("skeletons") or [] if s.get("text") and not s.get("errors") and s.get("sha") != best_sha and _n_holes(s) >= 1]
    nm = [n for n in arts.get("near_misses") or [] if n.get("text") and n.get("sha") != best_sha and len(n.get("open_goals") or []) <= REPAIR_MAX_OPEN_GOALS]
    counts = {"skeletons": len(arts.get("skeletons") or []), "near_misses": len(arts.get("near_misses") or []), "repair_skeletons": 0, "session_skeletons": 0,
              "repair_near_misses": len(nm)}
    rep_sk = sorted([s for s in sk if _n_holes(s) <= REPAIR_MAX_HOLES], key=lambda s: (_n_holes(s), s.get("tokens_est") or 1 << 30))
    ses_sk = sorted([s for s in sk if _n_holes(s) <= SESSION_MAX_HOLES and (_n_holes(s) > REPAIR_MAX_HOLES or (s.get("structural") and s.get("kind") in STRUCTURAL_KINDS))],
                    key=lambda s: (0 if s.get("structural") else 1, _n_holes(s)))
    counts["repair_skeletons"], counts["session_skeletons"] = len(rep_sk), len(ses_sk)
    c = classes or {}
    plan_first = any(float(c.get(k) or 0) >= 0.5 for k in ("c2", "c4")) and not any(float(c.get(k) or 0) >= 0.5 for k in ("c3", "c5"))
    repair = None
    if rep_sk:
        s = rep_sk[0]
        repair = {"kind": "repair", "artifact": s, "near_misses": [], "reason": f"skeleton {s['sha']} ({s.get('kind')}, {s.get('source')}) with {_n_holes(s)} hole(s) <= {REPAIR_MAX_HOLES}"}
    elif len(nm) >= REPAIR_MIN_NEAR_MISSES:
        nms = sorted(nm, key=lambda n: (len(n.get("open_goals") or []), str(n.get("at") or "")))[:4]
        repair = {"kind": "repair", "artifact": None, "near_misses": nms,
                  "reason": f"{len(nm)} near-miss(es) with <= {REPAIR_MAX_OPEN_GOALS} open goals (shas {', '.join(n['sha'] for n in nms)})"}
    session = None
    if ses_sk:
        s = ses_sk[0]
        session = {"kind": "artifact-session", "artifact": s, "near_misses": [],
                   "reason": f"skeleton {s['sha']} ({s.get('kind')}, {s.get('source')}) with {_n_holes(s)} hole(s)" + (", structurally different" if s.get("structural") else "")}
    pick = (session or repair) if plan_first else (repair or session)
    if pick is None:
        return {"kind": None, "artifact": None, "near_misses": [], "reason": "no compiled artifact with holes and fewer than "
                f"{REPAIR_MIN_NEAR_MISSES} near-misses with <= {REPAIR_MAX_OPEN_GOALS} open goals", "candidates": counts}
    pick = dict(pick); pick["candidates"] = counts
    if plan_first and session and repair:
        pick["reason"] += "; session first (c2/c4 class)"
    return pick


def summary(arts: dict) -> dict:
    """Numbers only (sealed sets: no text, no names)."""
    return {"skeletons": [{"sha": s.get("sha"), "kind": s.get("kind"), "holes": _n_holes(s), "structural": s.get("structural"), "source": str(s.get("source"))[:40]}
                          for s in arts.get("skeletons") or []],
            "near_misses": [{"sha": n.get("sha"), "open_goals": len(n.get("open_goals") or []), "source": str(n.get("source"))[:40]} for n in arts.get("near_misses") or []]}


# ---- agent.py --artifact -----------------------------------------------------------------------------------------------------------
def safe(n: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", n)


def load_record(path, name: str, statement: str | None = None) -> dict | None:
    """The artifact record for `name` from PATH: a directory (<dir>/<ws>.artifact.json), a JSON record ({"text": ...}, any problem), or a JSON
    map {problem: record}. None when there is none for this row, or when its statement is not the row's (byte-identical prefix)."""
    p = Path(path)
    if p.is_dir():
        p = p / f"{safe(name)}.artifact.json"
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    rec = None
    if isinstance(d, dict) and isinstance(d.get("text"), str):
        rec = d if d.get("problem") in (None, name) else None
    elif isinstance(d, dict):
        rec = d.get(name) if isinstance(d.get(name), dict) else None
    if not rec or not isinstance(rec.get("text"), str) or not rec["text"].strip():
        return None
    if statement is not None and not rec["text"].lstrip().startswith(statement):
        return None
    rec = dict(rec); rec["text"] = rec["text"].rstrip(); rec["sha"] = rec.get("sha") or sha(rec["text"])
    rec.setdefault("kind", "skeleton"); rec.setdefault("source", "?")
    if rec.get("holes") is None:
        rec["holes"] = holes_of(rec["text"])
    return rec


def write_record(path, name: str, rec: dict) -> Path:
    """<dir>/<ws>.artifact.json (what agent.py --artifact DIR reads, one file per row)."""
    d = Path(path); d.mkdir(parents=True, exist_ok=True)
    f = d / f"{safe(name)}.artifact.json"
    tmp = f.with_suffix(".tmp"); tmp.write_text(json.dumps(dict(rec, problem=name), ensure_ascii=False, indent=1)); tmp.replace(f)
    return f
