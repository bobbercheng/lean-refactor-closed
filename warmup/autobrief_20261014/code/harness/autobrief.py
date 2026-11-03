#!/usr/bin/env python3
"""Auto-brief (docs/auto_brief_plan.md; 2026-10-14): a general, programmatic good start
computed IN THE RUN from the seed proof by CPU only, the same code for every row (nothing stored per problem: not a targeted optimization;
allowed in both tracks; the $3 cap counts only inference). Replaces what the theorem-keyed briefs gave (60% of their lines were tested
facts) with facts measured on this seed:
  1. free passes   normalize -> hb_rewrite -> hb_polish -> lint_delete on the seed: start candidate S0 (each kept only when it pays)
  2. hot spots     harness/profile.py: heartbeats per block of S0 (bounded cuts)
  3. sweep         single edits of S0, each compiled on the primary toolchain: delete one simp-list argument / one standalone tactic line
                   (lint_delete.search_dels), replace a block by a closer (whole proof, a bullet, a `have ... := by` block, a block's
                   last tactic) with grind / simp_all / aesop; outcome, Δtokens, Δheartbeats, Δscore recorded for every edit
  4. combine       the paying edits together (then greedily); the best compiling result, checked on every listed toolchain: S1
  5. brief         about 2.5k chars "measured on this seed": exchange rate, start numbers, hot spots, edits that pay, edits that fail
Output per row: <out-dir>/<ws>.json (everything, incl. S0/S1 proofs and every edit) and <ws>.md (the brief).
    python3 harness/autobrief.py --problems NAME ... --out-dir probe/autobrief/<tag> [--budget 80] [--workers 3] [--no-free] [--no-profile]
        [--rows data/abpool/abpool.jsonl --heartbeats data/abpool/heartbeats.jsonl]   (rows outside the warm-up file)
Compiles go through scorer.compile (memgate-admitted): run it in a memory-capped unit, never from an interactive shell."""
from __future__ import annotations

import argparse, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(1, str(ROOT / "harness"))
from harness.leantools import ROWS, HBS  # noqa: E402
from scorer.tokenize import split_declaration, count_tokens  # noqa: E402
from scorer.score import len_pct, hb_pct_local  # noqa: E402

CLOSERS = ("grind", "simp_all", "aesop")
MIN_GAIN = 0.05            # noise margin of a re-measured proof (lint_delete.MIN_GAIN)
BRIEF_CHARS = 2600         # the size of the theorem-keyed briefs it replaces (~3.6k with their headers)
OPENERS = ("by", "=>", "do", "then", "else", "with", "·", ":=", "<;>", "(", "[", "⟨", "{", ",", "←", "|")


@dataclass
class Edit:
    kind: str             # "del-arg" | "del-tac" | "closer"
    a: int                # span [a, b) of the body replaced by `repl`
    b: int
    repl: str
    line: int             # 1-based line of the span's start in the body
    label: str            # human text: what changes
    closer: str = ""
    res: dict = field(default_factory=dict)

    def apply(self, body: str) -> str:
        return body[: self.a] + self.repl + body[self.b:]


def _span_of(old: str, new: str) -> tuple[int, int, str]:
    """The single changed span turning `old` into `new`: (a, b, replacement)."""
    p = 0
    while p < min(len(old), len(new)) and old[p] == new[p]:
        p += 1
    s = 0
    while s < min(len(old), len(new)) - p and old[-1 - s] == new[-1 - s]:
        s += 1
    return p, len(old) - s, new[p: len(new) - s]


def _line_no(body: str, i: int) -> int:
    return body.count("\n", 0, i) + 1


def _short(s: str, n: int = 60) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def deletion_edits(body: str) -> list[Edit]:
    from harness import lint_delete as LD
    out = []
    for d in LD.search_dels(body):
        try:
            new = LD.render(body, [d])
        except Exception:  # noqa: BLE001
            continue
        if new == body:
            continue
        a, b, r = _span_of(body, new)
        what = _short(body[d.span[0]: d.span[1]] if d.span else body[a:b], 50)
        if d.kind == "arg":
            out.append(Edit("del-arg", a, b, r, _line_no(body, d.pos if d.pos >= 0 else a), f"delete `{what}` from the simp list"))
        else:
            out.append(Edit("del-tac", a, b, r, _line_no(body, d.pos if d.pos >= 0 else a), f"delete the tactic `{what}`"))
    return out


def _lines(body: str) -> list[tuple[int, int, int, str]]:
    """(start offset, end offset, indent, code) of every non-blank line, comments stripped (`--` outside strings)."""
    from harness.normalize import _mask
    mask = _mask(body); out = []; i = 0
    for raw in body.split("\n"):
        j = i + len(raw)
        code = "".join(ch if not mask[i + k] else " " for k, ch in enumerate(raw)) if i + len(raw) <= len(mask) else raw
        code = re.sub(r"--.*$", "", code).rstrip()
        if code.strip():
            out.append((i, j, len(code) - len(code.lstrip()), code.strip()))
        i = j + 1
    return out


def closer_sites(body: str) -> list[tuple[int, int, str, str]]:
    """(a, b, prefix, label) spans whose text a closer can replace: the whole proof after `by`; each bullet's block; each `have ... := by`
    block (inline or indented); the last tactic of a block when it is a single line. The closer is written as prefix + closer."""
    L = _lines(body)
    sites = []
    m = re.match(r"\s*by\b", body)
    if m and L:
        sites.append((m.end(), len(body.rstrip()), " ", "the whole proof"))

    def block_end(k: int) -> int:   # end offset of line k's block: the following lines indented deeper than line k
        ind = L[k][2]; e = L[k][1]
        for s, t, i2, _ in L[k + 1:]:
            if i2 <= ind:
                break
            e = t
        return e

    for k, (s, t, ind, code) in enumerate(L):
        if code.startswith(("· ", ". ")) or code in ("·", "."):   # Lean 4 accepts `.` as a bullet too
            a = s + ind + 1
            b = block_end(k)
            if b - a > 8:
                sites.append((a, b, " ", f"the bullet at line {_line_no(body, s)} (`{_short(code, 40)}`)"))
            continue
        hm = re.match(r"(?:have|haveI|show)\b.*?:=\s*by\b", code)
        if hm:
            a = s + ind + hm.end()
            b = block_end(k) if code.endswith("by") else t
            if b - a > 8:
                sites.append((a, b, " ", f"the proof of `{_short(code[:hm.end() - 2], 40)}` (line {_line_no(body, s)})"))
            continue
        nxt = L[k + 1][2] if k + 1 < len(L) else -1
        last_in_block = nxt < ind
        if last_in_block and not code.endswith(OPENERS) and not re.match(r"(case|next|\||calc|·)\b", code) and len(code) > 12:
            sites.append((s + ind, t, "", f"the closing tactic at line {_line_no(body, s)} (`{_short(code, 40)}`)"))
    seen, out = set(), []
    for a, b, p, lab in sites:
        if (a, b) not in seen:
            seen.add((a, b)); out.append((a, b, p, lab))
    return out


def closer_edits(body: str, closers=CLOSERS) -> list[Edit]:
    out = []
    for a, b, pre, lab in closer_sites(body):
        for c in closers:
            if body[a:b].strip() == c:   # already that closer: no edit
                continue
            out.append(Edit("closer", a, b, pre + c, _line_no(body, a), f"replace {lab} by `{c}`", closer=c))
    return out


def exchange_rate(name: str, row: dict, tokens: int, hb: int) -> tuple[float, float]:
    ref = row["proof_length"]; off = HBS.get(name)
    pt = (len_pct(ref, tokens - 1) - len_pct(ref, tokens)) / 3
    ph = (hb_pct_local(name, max(hb - 100, 0), off) - hb_pct_local(name, hb, off)) / 3
    return round(pt, 3), round(ph, 3)


def _ev_default(name: str):
    from harness.normalize import evaluate
    from probe.verify_candidates import newest_first
    versions = newest_first(ROWS[name]["version_info"])
    return lambda decl, full: evaluate(name, decl, versions, full)


def free_passes(name: str, decl: str, log) -> tuple[str, list[dict]]:
    """normalize -> hb_rewrite -> hb_polish -> lint_delete, each on the previous result, each kept only when it reports `improved`."""
    steps = []
    passes = [("normalize", lambda d: __import__("harness.normalize", fromlist=["normalize"]).normalize(name, d, log=lambda *a: None)),
              ("hb_rewrite", lambda d: __import__("harness.hb_rewrite", fromlist=["rewrite_proof"]).rewrite_proof(name, d)),
              ("hb_polish", lambda d: __import__("harness.hb_polish", fromlist=["polish"]).polish(name, d)),
              ("lint_delete", lambda d: __import__("harness.lint_delete", fromlist=["delete_proof"]).delete_proof(name, d))]
    for pname, fn in passes:
        t0 = time.time()
        try:
            r = fn(decl)
        except Exception as e:  # noqa: BLE001  (one pass failing never stops the brief)
            steps.append({"pass": pname, "status": f"error {type(e).__name__}: {str(e)[:120]}", "seconds": round(time.time() - t0, 1)}); continue
        st = r.get("status")
        steps.append({"pass": pname, "status": st, "before": r.get("before"), "after": r.get("after"), "gain": r.get("gain"),
                      "applied": r.get("applied"), "compiles": r.get("compiles"), "seconds": round(time.time() - t0, 1)})
        if st == "improved" and r.get("proof"):
            decl = r["proof"]
        log(f"  free pass {pname}: {st} ({steps[-1]['seconds']}s)")
    return decl, steps


def sweep(name: str, decl: str, *, budget: int, workers: int, ev, log) -> tuple[dict, list[Edit]]:
    """Every single edit (bounded by `budget` compiles), evaluated on the primary toolchain against the same decl's primary measurement."""
    row = ROWS[name]
    body = split_declaration(decl.rstrip(), row["statement"])
    head = decl.rstrip()[: len(decl.rstrip()) - len(body)]
    base = ev(decl, False)
    dels, clos = deletion_edits(body), closer_edits(body)
    # budget: closers on the largest spans first (the biggest possible token cut), then deletions; whole-proof closers always tried
    clos.sort(key=lambda e: (not e.label.startswith("replace the whole proof"), -(e.b - e.a)))
    n_clo = min(len(clos), max(budget // 2, budget - len(dels)))
    todo = clos[:n_clo] + dels[: max(0, budget - n_clo)]
    log(f"  sweep: {len(dels)} deletions, {len(clos)} closer edits; compiling {len(todo)} (budget {budget})")
    cache: dict[str, dict] = {}

    def run(e: Edit) -> Edit:
        cand = head + e.apply(body)
        if cand not in cache:
            try:
                cache[cand] = ev(cand, False)
            except Exception as ex:  # noqa: BLE001
                cache[cand] = {"ok": False, "error": f"{type(ex).__name__}: {str(ex)[:120]}"}
        r = cache[cand]
        e.res = {"ok": bool(r.get("ok")), "tokens": r.get("tokens"), "heartbeats": r.get("heartbeats"), "score": r.get("score"),
                 "error": (r.get("error") or "")[:160]}
        if r.get("ok") and base.get("ok"):
            e.res.update(d_tokens=r["tokens"] - base["tokens"], d_hb=(r["heartbeats"] or 0) - (base["heartbeats"] or 0),
                         d_score=round(float(r["score"]) - float(base["score"]), 2))
        return e
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        done = list(pool.map(run, todo))
    return base, done


def combine(name: str, decl: str, edits: list[Edit], base: dict, *, ev, budget: int, log) -> dict | None:
    """The paying edits together (non-overlapping, best first), else greedily one at a time; the best compiling result checked in full."""
    row = ROWS[name]
    body = split_declaration(decl.rstrip(), row["statement"]); head = decl.rstrip()[: len(decl.rstrip()) - len(body)]
    pay = sorted([e for e in edits if e.res.get("ok") and (e.res.get("d_score") or 0) > MIN_GAIN], key=lambda e: -e.res["d_score"])
    if not pay:
        return None

    def splice(es: list[Edit]) -> str:
        chosen, out = [], body
        for e in es:
            if all(e.b <= c.a or e.a >= c.b for c in chosen):
                chosen.append(e)
        for e in sorted(chosen, key=lambda e: -e.a):
            out = out[: e.a] + e.repl + out[e.b:]
        return head + out
    tries = []
    best = (pay[0].res["score"], head + pay[0].apply(body), [pay[0].label])
    if len(pay) > 1 and budget > 0:
        cand = splice(pay); r = ev(cand, False); budget -= 1; tries.append(r)
        if r.get("ok") and r["score"] > best[0]:
            best = (r["score"], cand, [e.label for e in pay])
        elif budget > 0:   # greedy: add each paying edit while the whole keeps compiling and gaining
            kept = [pay[0]]
            for e in pay[1:]:
                if budget <= 0:
                    break
                cand = splice(kept + [e]); r = ev(cand, False); budget -= 1
                if r.get("ok") and r["score"] > best[0] + MIN_GAIN:
                    kept.append(e); best = (r["score"], cand, [x.label for x in kept])
    full = ev(best[1], True)
    log(f"  combine: {len(best[2])} edit(s), primary {best[0]}, full {full.get('score')} (Z {full.get('Z')})")
    return {"proof": best[1], "labels": best[2], "primary_score": best[0], "full": {k: full.get(k) for k in ("ok", "tokens", "heartbeats", "L", "H", "Z", "score")}}


def render_brief(name: str, out: dict) -> str:
    """The auto-brief text (no problem name, no landmark of other runs: only what was measured on this seed in this run)."""
    s0, sd = out["start"], out["seed"]
    lines = ["AUTO-BRIEF (measured on THIS seed by the harness before your session: single edits compiled on the primary toolchain; "
             "facts about single edits, not limits: combinations and rewrites can do better)"]
    lines.append(f"- Seed: {sd.get('tokens')} tokens, {sd.get('heartbeats')} heartbeats, score {sd.get('score')}."
                 + (f" Free passes applied ({', '.join(out['free_applied'])}): start candidate {s0.get('tokens')} tokens, "
                    f"{s0.get('heartbeats')} heartbeats, score {s0.get('score')}." if out.get("free_applied") else ""))
    if out.get("s1"):
        f = out["s1"]["full"]
        lines.append(f"- Best combination of the paying single edits below: {f.get('tokens')} tokens, {f.get('heartbeats')} heartbeats, "
                     f"score {f.get('score')} (Z {f.get('Z')}); your workspace starts from it.")
    pt, ph = out["exchange"]
    lines.append(f"- Exchange rate here: 1 token = {pt} points, 100 heartbeats = {ph} points.")
    hs = [b for b in (out.get("profile") or {}).get("blocks", []) if b.get("heartbeats")]
    if hs:
        tot = sum(max(0, b["heartbeats"]) for b in hs) or 1
        lines.append("- Heartbeat hot spots: " + "; ".join(f"lines {b['lines']} ~{round(100 * max(0, b['heartbeats']) / tot)}% "
                                                           f"(`{_short(b['text'], 36)}`)" for b in hs[:3]) + ".")
    ed = out["edits"]
    pay, seen_site = [], set()
    for e in sorted([e for e in ed if e["ok"] and (e.get("d_score") or 0) > MIN_GAIN], key=lambda e: -e["d_score"]):
        site = (e["line"], e["label"].rsplit(" by `", 1)[0])   # one line per site: its best closer
        if site not in seen_site:
            seen_site.add(site); pay.append(e)
    if pay:
        lines.append("- Single edits that PAY:")
        for e in pay[:6]:
            lines.append(f"  - line {e['line']}: {e['label']}: {e['d_tokens']:+d} tokens, {e['d_hb']:+d} hb, score {e['d_score']:+.2f}")
    ok_np = [e for e in ed if e["ok"] and (e.get("d_score") or 0) <= MIN_GAIN and e["kind"] == "closer"]
    if ok_np:
        lines.append("- Compile but do not pay alone: " + "; ".join(f"line {e['line']} {e['label'][8:]} ({e['d_tokens']:+d} tok, {e['d_hb']:+d} hb)"
                                                                 for e in sorted(ok_np, key=lambda e: e['d_tokens'])[:3]) + ".")
    fails = [e for e in ed if not e["ok"]]
    if fails:
        fd = [e for e in fails if e["kind"].startswith("del")]
        fc = [e for e in fails if e["kind"] == "closer"]
        if fd:
            lines.append("- Deletions that FAIL (needed as they stand): " + "; ".join(f"line {e['line']} {e['label'][7:]}" for e in fd[:6]) + ".")
        if fc:
            by_site: dict = {}
            for e in fc:
                by_site.setdefault(e["label"].rsplit(" by `", 1)[0][8:], []).append(e["closer"])
            lines.append("- Closers that do NOT close: " + "; ".join(f"{site} ({'/'.join(cs)})" for site, cs in list(by_site.items())[:5]) + ".")
    txt = "\n".join(lines)
    return txt if len(txt) <= BRIEF_CHARS else txt[: BRIEF_CHARS - 1].rsplit("\n", 1)[0]


def autobrief(name: str, decl: str | None = None, *, budget: int = 80, workers: int = 3, free: bool = True, prof: bool = True,
              ev=None, log=print) -> dict:
    row = ROWS[name]; decl = decl or row["src"]; ev = ev or _ev_default(name); t0 = time.time()
    seed = ev(decl, True)
    out = {"problem": name, "seed": {k: seed.get(k) for k in ("ok", "tokens", "heartbeats", "L", "H", "Z", "score")}, "free": [], "free_applied": []}
    if not seed.get("ok"):
        out.update(status="seed does not compile", seconds=round(time.time() - t0, 1)); return out
    s0 = decl
    if free:
        s0, out["free"] = free_passes(name, decl, log)
        out["free_applied"] = [s["pass"] for s in out["free"] if s["status"] == "improved"]
    start = ev(s0, True) if s0 != decl else seed
    out["start"] = {k: start.get(k) for k in ("ok", "tokens", "heartbeats", "L", "H", "Z", "score")}; out["s0"] = s0
    out["exchange"] = exchange_rate(name, row, start["tokens"], start["heartbeats"] or 0)
    if prof:
        try:
            from harness.profile import profile
            out["profile"] = profile(name, s0, max_cuts=8)
        except Exception as e:  # noqa: BLE001
            out["profile"] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    base, edits = sweep(name, s0, budget=budget, workers=workers, ev=ev, log=log)
    out["sweep_base"] = {k: base.get(k) for k in ("ok", "tokens", "heartbeats", "score")}
    out["edits"] = [{"kind": e.kind, "line": e.line, "label": e.label, "closer": e.closer, **e.res} for e in edits]
    s1 = combine(name, s0, edits, base, ev=ev, budget=6, log=log)
    if s1 and s1["full"].get("ok") and float(s1["full"].get("Z") or 0) >= float(start.get("Z") or 0) - 1e-9 \
            and float(s1["full"]["score"]) > float(start["score"]) + MIN_GAIN:
        out["s1"] = s1
    out["brief"] = render_brief(name, out)
    best = out.get("s1", {}).get("full") or out["start"]
    out.update(status="ok", best_score=best.get("score"), gain=round(float(best["score"]) - float(seed["score"]), 2),
               compiles_sweep=len(edits), seconds=round(time.time() - t0, 1))
    return out


def safe(n: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", n)


def register_rows(rows_file: str, hb_file: str | None) -> list[str]:
    """Rows outside the warm-up file (e.g. the A/B pool) added to the shared ROWS / HBS dicts every module reads."""
    new = [json.loads(l) for l in (ROOT / rows_file).open() if l.strip()]
    for r in new:
        ROWS.setdefault(r["name"], r)
    if hb_file:
        for l in (ROOT / hb_file).open():
            if l.strip():
                h = json.loads(l); HBS.setdefault(h["name"], h["heartbeat"])
    try:
        import mine
        for r in new:
            mine.ROWS.setdefault(r["name"], r)
    except Exception:  # noqa: BLE001
        pass
    return [r["name"] for r in new]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--problems", nargs="*"); ap.add_argument("--out-dir", required=True)
    ap.add_argument("--budget", type=int, default=80); ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--row-workers", type=int, default=1, help="rows processed at once")
    ap.add_argument("--no-free", action="store_true"); ap.add_argument("--no-profile", action="store_true")
    ap.add_argument("--rows"); ap.add_argument("--heartbeats")
    ap.add_argument("--from-work-root", help="progressive auto-brief: measure each row's CURRENT BEST in this work root (state.json) "
                    "instead of the seed; the json records the best's sha")
    a = ap.parse_args(argv)
    names = register_rows(a.rows, a.heartbeats) if a.rows else []
    todo = a.problems or names or list(ROWS)
    od = Path(a.out_dir); od.mkdir(parents=True, exist_ok=True)

    def one(n: str):
        f = od / f"{safe(n)}.json"
        if f.exists():
            return
        log = lambda m: print(f"[{time.strftime('%H:%M:%S')}] {n[:24]}: {m}", flush=True)
        decl, src = None, "seed"
        if a.from_work_root:
            st = Path(a.from_work_root) / safe(n) / "state.json"
            best = (json.loads(st.read_text()).get("best") or {}) if st.exists() else {}
            if best.get("proof"):
                decl, src = best["proof"], "best:" + __import__("hashlib").sha256(best["proof"].encode()).hexdigest()[:12]
        try:
            r = autobrief(n, decl, budget=a.budget, workers=a.workers, free=not a.no_free, prof=not a.no_profile, log=log)
            r["source"] = src
        except Exception as e:  # noqa: BLE001
            r = {"problem": n, "status": f"error {type(e).__name__}: {str(e)[:200]}"}
        f.write_text(json.dumps(r, ensure_ascii=False, indent=1))
        if r.get("brief"):
            (od / f"{safe(n)}.md").write_text(r["brief"] + "\n")
        log(f"done: {r.get('status')} seed {r.get('seed', {}).get('score')} -> best {r.get('best_score')} ({r.get('seconds')}s)")
    with ThreadPoolExecutor(max_workers=max(1, a.row_workers)) as pool:
        list(pool.map(one, todo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
