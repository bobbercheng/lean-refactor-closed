#!/usr/bin/env python3
"""Bet D4, lexer rule "primeglue" (docs/closed_run2.md, the `∘'by` quirk of the research generalised; bet D4 2026-11-02): an end-stage
family ("primeglue", registered only by harness/end_d4.register(), never by default) with the harness/sweep.candidates contract. Pure: no
compile, no I/O, no table, no row knowledge.

The scorer's lexer (scorer/tokenize.py) joins `'` to the run of identifier characters that follows it, so a notation token that ENDS in
primes (`f '' s`, `g ⁻¹' s`, `f ∘' g`, `∑' i, ...`) followed by a blank and a word costs one token more than the same text without the
blank. Lean reads the notation token by its longest match and then the word (an identifier never starts with `'`), so the meaning is the
same; the compile decides.

  sites     a maximal run of `'` outside comments and strings, followed by blanks and a letter or `_`, and preceded either by a symbol
            character (not a letter, digit, `_`, `.` or blank; or the `¹` of `⁻¹`) or, for a run of two or more primes, by a blank.
  generate  primeglue:join   one candidate per site (the blanks deleted) and one with every site joined; each saves tokens.
The caller measures every candidate back to back with its incumbent (batch screen, paired decide, all-pin confirmation)."""
from __future__ import annotations

import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.normalize import _mask  # noqa: E402
from harness.tools import d4_kit as K  # noqa: E402
from scorer.tokenize import split_declaration  # noqa: E402

FAMILY = "primeglue"
OPS = ("primeglue:join",)
ALL_OPS = OPS
OPT_IN_OPS: tuple = ()
DEFAULT_OPS = OPS
TABLES: dict = {}
MAX_PER_OP = 12
SITE_RE = re.compile(r"('+)([ \t]+)(?=[^\W\d]|_)")


def sites(body: str) -> list[tuple[int, int]]:
    """[(start, end) of the blanks to delete] in text order (module docstring, "sites")."""
    mask = _mask(body)
    out = []
    for m in SITE_RE.finditer(body):
        a = m.start(1)
        if mask[a] or mask[m.end(2) - 1]:
            continue
        prev = body[a - 1] if a > 0 else "\n"
        if prev == "¹" and a > 1 and body[a - 2] == "⁻":
            ok = True
        elif prev in " \t":
            ok = len(m.group(1)) >= 2
        else:
            ok = not (prev.isalnum() or prev in "_.'\n")
        if ok:
            out.append((m.start(2), m.end(2)))
    return out


def candidates(proof: str, statement: str, *, exchange: float | None = None, max_per_op: int | None = None,
               ctx: dict | None = None) -> list[dict]:
    ops = K.ops_for(FAMILY, OPS, DEFAULT_OPS, OPT_IN_OPS, ctx)
    hb = K.head_body(proof, statement)
    if hb is None or not ops:
        return []
    head, body = hb
    em = K.Emitter(proof, statement, head, body, int(max_per_op) if max_per_op else MAX_PER_OP)
    ss = sites(body)
    if len(ss) > 1:
        nb = body
        for a, b in reversed(ss):
            nb = nb[:a] + nb[b:]
        em.add("primeglue:join", nb, f"{len(ss)} prime-ended tokens joined to the next word")
    for a, b in ss:
        em.add("primeglue:join", body[:a] + body[b:], f"`{body[max(0, a - 6):b + 6].strip()}` joined @L{K.line_of(body, a)}")
    return em.out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="primeglue candidates of one declaration (no compile)")
    ap.add_argument("--file", required=True); ap.add_argument("--statement-file", required=True)
    a = ap.parse_args(argv)
    proof = Path(a.file).read_text(); stmt = Path(a.statement_file).read_text().rstrip("\n")
    for c in candidates(proof, stmt):
        print(json.dumps({"op": c["op"], "note": c["note"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
