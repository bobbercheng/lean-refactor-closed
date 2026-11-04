#!/usr/bin/env python3
"""Bet D4, rule R3 "searchinline" (docs/closed_run2.md; bet D4 2026-11-02): an end-stage family ("searchinline", registered only by
harness/end_d4.register(), never by default) with the harness/sweep.candidates contract and an ENV QUERY (harness/endstage.py
QUERY_FAMILIES): a search tactic left in a final proof (`exact?`, `simp?`, `aesop?`, ...) is re-run by Lean at every compile; its
"Try this" suggestion written in its place costs no search (tokens may rise: the paired measurement prices the trade).

  sites     a search tactic (SEARCH_RE: exact? apply? rw? simp? simp_all? simpa? dsimp? simp_arith? norm_num? field_simp? aesop? grind?
            hint try?) outside comments and strings; its span runs to the end of its line, a top-level `;` or `<;>`. At most MAX_SITES.
  query     one plain compile of the incumbent itself after the row's file prefix (Meter.command, as a validity compile places it; the
            primary pin): Lean's "Try this" information messages, in position order, paired with the sites in text order. The pairing
            holds only when there are as many messages as sites, every message sits at its site's column (Lean's: from the start of
            the file line, so a site on the `:=` line counts the declaration's text before the body) and every pair has the same line
            offset; otherwise nothing is proposed. Only the compile's own messages are read: nothing is guessed.
  generate  searchinline:inline  the site's span -> each suggestion of its message (whitespace collapsed; a multi-line suggestion that is
                                 not one tactic is skipped) and, for an `exact` / `refine` / `apply` of a `fun` term, shorter spellings:
                                 trailing binders eta-reduced (`fun a b => f b` -> `fun a => f`), unused binders `_`, the `λ` form, a
                                 term with no binder left written bare. At most MAX_PER_SITE per site, fewest tokens first.
            searchinline:tosearch  OPT-IN (the inverse, as closed run 1 found by itself): a one-line `exact T` whose term has at least
                                 MIN_TERM tokens and ends its line -> `exact?` (no query; the batch screen's heartbeat bound and timeout
                                 cut an expensive search).
The caller measures every candidate back to back with its incumbent (batch screen, paired decide, all-pin confirmation). No harm: no
site, no answer, a mismatch, a timeout or a budget stop proposes nothing and never changes the final. Generic by construction: the text
written comes from the proof itself and from Lean's own messages on it."""
from __future__ import annotations

import argparse, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.normalize import _mask, _pairs, OPEN, CLOSE  # noqa: E402
from harness.tools import d4_kit as K  # noqa: E402
from scorer.tokenize import split_declaration, count_tokens  # noqa: E402

FAMILY = "searchinline"
OPS = ("searchinline:inline", "searchinline:tosearch")
ALL_OPS = OPS
OPT_IN_OPS = ("searchinline:tosearch",)
DEFAULT_OPS = tuple(o for o in OPS if o not in OPT_IN_OPS)
TABLES: dict = {}
MAX_PER_OP = 16
MAX_SITES = 6
MAX_PER_SITE = 4
MIN_TERM = 4
QUERY_TIMEOUT = 300

SEARCH_RE = re.compile(r"(?<![\w.'?!])(exact\?|apply\?|rw\?|simp\?|simp_all\?|simpa\?|dsimp\?|simp_arith\?|norm_num\?|field_simp\?|aesop\?|"
                       r"grind\?|hint|try\?)(?![\w'?!])")
TRY_THIS = re.compile(r"^\s*Try (?:this|these):\s*", re.S)
ONE_TACTIC_RE = re.compile(r"^(exact|refine|apply|simp|simp_all|simpa|dsimp|simp_arith|norm_num|field_simp|rw|rewrite|grind|aesop|linarith|"
                           r"nlinarith|omega|decide|positivity|tauto|ring_nf|ring|use|exists|constructor|intro|rfl|trivial)(?![\w'])")
FUN_RE = re.compile(r"^(exact|refine|apply)\s+(?:fun|λ)\s*((?:[\w'₀-₉]+\s+)*[\w'₀-₉]+)\s*=>\s*(.+)$", re.S)
EXACT_RE = re.compile(r"(?<![\w.'?!])exact[ \t]+(?!\?)([^\n]+?)[ \t]*$", re.M)


def sites(body: str, col0: int = 0) -> list[dict]:
    """[{"lo", "hi": the tactic call's span, "tac", "line", "col"}] in text order (module docstring, "sites"). "col" is the column Lean
    reports: from the start of the file line, so a site on the body's first line (the `:=` line) adds col0, the length of the text before
    the body on that line."""
    mask = _mask(body)
    pairs = _pairs(body, mask)
    closers = {v: k for k, v in pairs.items()}
    out = []
    for m in SEARCH_RE.finditer(body):
        lo = m.start()
        if mask[lo]:
            continue
        hi, depth = m.end(), 0
        while hi < len(body) and body[hi] != "\n":
            ch = body[hi]
            if mask[hi]:
                break
            if ch in OPEN:
                depth += 1
            elif ch in CLOSE:
                if depth == 0 or hi in closers and closers[hi] < lo:
                    break
                depth -= 1
            elif depth == 0 and (ch == ";" or body.startswith("<;>", hi)):
                break
            hi += 1
        while hi > m.end() and body[hi - 1] in " \t":
            hi -= 1
        ls = body.rfind("\n", 0, lo) + 1
        out.append({"lo": lo, "hi": hi, "tac": body[lo:hi], "line": K.line_of(body, lo), "col": lo - ls + (col0 if ls == 0 else 0)})
        if len(out) >= MAX_SITES:
            break
    return out


def suggestions(text: str) -> list[str]:
    """The suggestions of one "Try this / Try these" message (fill_holes' rule: `[apply]` markers or bullets), whitespace kept."""
    m = TRY_THIS.match(text or "")
    if not m:
        return []
    body = text[m.end():].strip()
    if "[apply]" in body:
        items = [x.strip() for x in re.split(r"\[apply\]", body) if x.strip()]
    else:
        items = [re.sub(r"^[\s•\-\*]+", "", x).strip() for x in re.split(r"\n\s*[•\-\*]\s+", "\n" + body) if x.strip()]
    return [i for i in items if i and "sorry" not in i]


def pair(ss: list[dict], messages) -> dict | None:
    """{site index: [suggestions]} when the "Try this" messages pair with the sites (module docstring, "query"), else None."""
    msgs = []
    for m in messages or []:
        if not isinstance(m, dict) or m.get("severity") not in ("information", "info"):
            continue
        d = K.msg_text(m)
        if not TRY_THIS.match(d):
            continue
        pos = m.get("pos") or {}
        if not isinstance(pos.get("line"), int) or not isinstance(pos.get("column"), int):
            return None
        msgs.append((pos["line"], pos["column"], d))
    msgs.sort(key=lambda x: (x[0], x[1]))
    if not ss or len(msgs) != len(ss):
        return None
    offs = {ml - s["line"] for (ml, _, _), s in zip(msgs, ss)}
    if len(offs) != 1 or any(mc != s["col"] for (_, mc, _), s in zip(msgs, ss)):
        return None
    return {i: suggestions(d) for i, (_, _, d) in enumerate(msgs)}


def _word(s: str, w: str) -> bool:
    return re.search(r"(?<![\w.'])%s(?![\w'₀-₉])" % re.escape(w), s) is not None


def spellings(sug: str) -> list[str]:
    """The suggestion (one tactic, whitespace collapsed) and its shorter spellings (module docstring, "generate"); [] when it is not one
    tactic."""
    s = sug.strip()
    if "\n" in s:   # one tactic wrapped over lines only: its first line leaves a bracket open or ends in a term continuation
        first = s.split("\n", 1)[0]
        fm = _mask(first)
        depth = sum(1 for i, ch in enumerate(first) if ch in OPEN and not fm[i]) - sum(1 for i, ch in enumerate(first) if ch in CLOSE and not fm[i])
        if not ONE_TACTIC_RE.match(s) or not (depth > 0 or first.rstrip().endswith(("=>", "$", "<|", ","))):
            return []
        s = re.sub(r"\s*\n\s*", " ", s)
    if not ONE_TACTIC_RE.match(s):
        return []
    out = [s]
    m = FUN_RE.match(s)
    if m:
        kw, bs, F = m.group(1), m.group(2).split(), m.group(3).strip()
        while bs and F.endswith(" " + bs[-1]) and not _word(F[:-len(bs[-1]) - 1], bs[-1]) and not F.startswith("(") \
                and re.match(r"^[^\s()]+(?:\s|$)", F):
            F = F[:-len(bs[-1]) - 1].rstrip()
            bs.pop()
        bs = [b if _word(F, b) else "_" for b in bs]
        if not bs:
            out.append(f"{kw} {F}")
        else:
            out += [f"{kw} fun {' '.join(bs)} => {F}", f"{kw} λ{' '.join(bs)} => {F}"]
    return list(dict.fromkeys(out))


def query(proof: str, statement: str, run, *, versions=None, ctx: dict | None = None, stats: dict | None = None, log=None) -> dict | None:
    """The incumbent compiled once (module docstring, "query"). Returns {"searchinline_query": {...}, "searchinline_query_for": key};
    no site: an empty answer without a compile."""
    st = stats if stats is not None else {}
    log = log or (lambda *a: None)
    t0 = time.time()
    key = K.proof_key(proof)
    body = split_declaration(proof, statement)
    col0 = len(proof[:len(proof) - len(body)].rsplit("\n", 1)[-1]) if body is not None else 0   # the `:=` line's text before the body
    ss = sites(body, col0) if body is not None else []
    q = {"answered": False, "sites": [{k: s[k] for k in ("lo", "hi", "tac")} for s in ss], "suggestions": {}}
    if not ss:
        q["skip"] = "no search tactic in the proof"
        st["query"] = {"ids": 0, "used": 0, "vars": 0, "class_vars": 0, "skip": q["skip"]}
        return {"searchinline_query": q, "searchinline_query_for": key}
    vs = list(versions or [None])
    r = run(proof, vs[0])
    pr = pair(ss, getattr(r, "messages", None))
    if pr is None:
        q["skip"] = f"the Try-this messages do not pair with the {len(ss)} search site(s)"
    else:
        q["answered"] = True
        q["suggestions"] = {str(i): v for i, v in pr.items()}
    q["seconds"] = round(time.time() - t0, 2)
    st["query"] = {"ids": len(ss), "used": len(q["suggestions"]), "vars": sum(len(v) for v in q["suggestions"].values()), "class_vars": 0,
                   "seconds": q["seconds"], **({"skip": q["skip"]} if q.get("skip") else {})}
    log(f"searchinline: {len(ss)} search site(s), {len(q['suggestions'])} paired in {q['seconds']} s" + (f" ({q['skip']})" if q.get("skip") else ""))
    return {"searchinline_query": q, "searchinline_query_for": key}


def candidates(proof: str, statement: str, *, exchange: float | None = None, max_per_op: int | None = None,
               ctx: dict | None = None) -> list[dict]:
    ctx = ctx or {}
    ops = K.ops_for(FAMILY, OPS, DEFAULT_OPS, OPT_IN_OPS, ctx)
    hb = K.head_body(proof, statement)
    if hb is None or not ops:
        return []
    head, body = hb
    em = K.Emitter(proof, statement, head, body, int(max_per_op) if max_per_op else MAX_PER_OP)
    q = ctx.get("searchinline_query")
    if "searchinline:inline" in ops and q and ctx.get("searchinline_query_for") == K.proof_key(proof) and q.get("answered"):
        for i, s in enumerate(q.get("sites") or []):
            if body[s["lo"]:s["hi"]] != s["tac"]:
                continue
            outs = []
            for sug in (q.get("suggestions") or {}).get(str(i)) or []:
                outs += [x for x in spellings(sug) if x not in outs]
            outs.sort(key=lambda x: (count_tokens(x), len(x)))
            for x in outs[:MAX_PER_SITE]:
                em.add("searchinline:inline", body[:s["lo"]] + x + body[s["hi"]:], f"`{s['tac'][:30]}` -> `{x[:60]}`", save=False)
    if "searchinline:tosearch" in ops:
        mask = _mask(body)
        for m in EXACT_RE.finditer(body):
            t = m.group(1)
            if mask[m.start()] or count_tokens(t) < MIN_TERM or "?_" in t or ";" in t or "<;>" in t:
                continue
            em.add("searchinline:tosearch", body[:m.start()] + "exact?" + body[m.end():], f"`exact {t[:40]}` -> `exact?`")
    return em.out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="searchinline: the search sites of one declaration (no compile)")
    ap.add_argument("--file", required=True); ap.add_argument("--statement-file", required=True)
    a = ap.parse_args(argv)
    proof = Path(a.file).read_text(); stmt = Path(a.statement_file).read_text().rstrip("\n")
    for s in sites(split_declaration(proof, stmt) or ""):
        print(json.dumps(s, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
