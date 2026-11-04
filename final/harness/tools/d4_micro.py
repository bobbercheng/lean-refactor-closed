#!/usr/bin/env python3
"""Bet D4, micro-rewrites the research lanes found by hand and no closed-pipeline op covers (docs/closed_run2.md research lineages; bet D4
2026-11-02): an end-stage family ("micro", registered only by harness/end_d4.register(), never by default) with the harness/sweep.candidates
contract. Pure: no compile, no I/O, no table, no row knowledge; every token of a candidate comes from the proof being edited or is Lean /
Mathlib tactic syntax.

Ops (sites at tactic position: a line start (after `·`), or after `;`, `<;>`, `by`, `=>`; outside comments and strings):
  micro:normnum   simp-head swap `simp only [L]` -> `norm_num only [L]`, `simp [L]` -> `norm_num [L]` (token-neutral: norm_num's extensions
                  can replace lemmas of L and change the heartbeats either way)
  micro:simphead  the reverse swap `norm_num only [L]` -> `simp only [L]`, `norm_num [L]` -> `simp [L]`
  micro:joint     the swap plus the deletion of ONE item of L (lists of at most JOINT_MAX items): the single-edit passes cannot reach a
                  deletion that compiles only under the other head
  micro:rw2simp   `rw [rs]` / `rewrite [rs]` -> `simp only [rs]` (one token more; simp rewrites to a normal form, often far cheaper)
  micro:congr     `congr 1` <-> `apply congrArg`; `apply congrArg f` -> `apply congrArg` and `apply congrArg _`
  micro:byunnest  a one-line `exact F a (by T)` / `refine F a (by T)` whose last argument is a one-line by-block (no `?_` anywhere) ->
                  `apply F a` and `T` on the next line at the same indentation
The caller measures every candidate back to back with its incumbent (batch screen, paired decide, all-pin confirmation); the token-adding
and token-neutral ops are priced by that decision (a heartbeat gain must pay for them)."""
from __future__ import annotations

import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.normalize import _mask, _pairs  # noqa: E402
from harness.lint_delete import _list_items  # noqa: E402
from harness.tools import d4_kit as K  # noqa: E402
from scorer.tokenize import split_declaration  # noqa: E402

FAMILY = "micro"
OPS = ("micro:normnum", "micro:simphead", "micro:joint", "micro:rw2simp", "micro:congr", "micro:byunnest")
ALL_OPS = OPS
OPT_IN_OPS: tuple = ()
DEFAULT_OPS = OPS
TABLES: dict = {}
MAX_PER_OP = 24
JOINT_MAX = 24

TACPOS_RE = re.compile(r"(?:^[ \t]*(?:·[ \t]*)?|(?:;|<;>|(?<![\w.'])by|=>)[ \t]*)$")
SIMP_RE = re.compile(r"(?<![\w.'])simp(?![\w'?!])([ \t]+only)?[ \t]*(?=\[)")
NORMNUM_RE = re.compile(r"(?<![\w.'])norm_num(?![\w'?!])([ \t]+only)?[ \t]*(?=\[)")
RW_RE = re.compile(r"(?<![\w.'])(rw|rewrite)(?![\w'?!])[ \t]*(?=\[)")
CONGR1_RE = re.compile(r"(?<![\w.'])congr[ \t]+1(?![\w'])")
CONGRARG_RE = re.compile(r"(?<![\w.'])apply[ \t]+congrArg(?![\w'])((?:[ \t]+[^\s;]+)?)")
UNNEST_RE = re.compile(r"^([ \t]*)(exact|refine)[ \t]+(.+?)[ \t]*$")


def _tacpos(body: str, i: int) -> bool:
    ls = body.rfind("\n", 0, i) + 1
    return TACPOS_RE.search(body[ls:i]) is not None


def _end_ok(body: str, j: int) -> bool:
    """The tactic ends at j: end of line, `;`, `<;>`, a closing bracket or a comment."""
    rest = body[j:].lstrip(" \t")
    return rest == "" or rest[0] in "\n;)]}" or rest.startswith(("<;>", "--"))


def _swaps(body: str, mask, pairs, rx, new_head: str):
    """[(head span, list span, new head text)] for every `head [only] [` call at tactic position."""
    out = []
    for m in rx.finditer(body):
        if mask[m.start()] or not _tacpos(body, m.start()):
            continue
        lb = m.end()
        if lb not in pairs:
            continue
        out.append(((m.start(), m.end()), (lb, pairs[lb]), new_head + (" only" if m.group(1) else "") + " "))
    return out


def candidates(proof: str, statement: str, *, exchange: float | None = None, max_per_op: int | None = None,
               ctx: dict | None = None) -> list[dict]:
    ops = K.ops_for(FAMILY, OPS, DEFAULT_OPS, OPT_IN_OPS, ctx)
    hb = K.head_body(proof, statement)
    if hb is None or not ops:
        return []
    head, body = hb
    em = K.Emitter(proof, statement, head, body, int(max_per_op) if max_per_op else MAX_PER_OP)
    mask = _mask(body)
    pairs = _pairs(body, mask)
    swaps = [("micro:normnum", s) for s in _swaps(body, mask, pairs, SIMP_RE, "norm_num")]
    swaps += [("micro:simphead", s) for s in _swaps(body, mask, pairs, NORMNUM_RE, "simp")]
    for op, ((a, b), _, new) in swaps:
        if op in ops:
            em.add(op, body[:a] + new + body[b:], f"`{body[a:b].strip()}` -> `{new.strip()}` @L{K.line_of(body, a)}", save=False)
    if "micro:joint" in ops:
        for _, ((a, b), (lb, rb), new) in swaps:
            items = _list_items(body, mask, pairs, lb) or []
            if not 1 < len(items) <= JOINT_MAX:
                continue
            for k, (ia, ib) in enumerate(items):
                keep = [body[x:y] for j, (x, y) in enumerate(items) if j != k]
                nb = body[:a] + new + body[lb:lb + 1] + ", ".join(keep) + body[rb:]
                em.add("micro:joint", nb, f"`{new.strip()}` and `{body[ia:ib][:40]}` dropped @L{K.line_of(body, a)}")
    if "micro:rw2simp" in ops:
        for m in RW_RE.finditer(body):
            if mask[m.start()] or not _tacpos(body, m.start()) or m.end() not in pairs:
                continue
            em.add("micro:rw2simp", body[:m.start()] + "simp only " + body[m.end():], f"`{m.group(1)}` -> `simp only` @L{K.line_of(body, m.start())}",
                   save=False)
    if "micro:congr" in ops:
        for m in CONGR1_RE.finditer(body):
            if not mask[m.start()] and _tacpos(body, m.start()) and _end_ok(body, m.end()):
                em.add("micro:congr", body[:m.start()] + "apply congrArg" + body[m.end():], "`congr 1` -> `apply congrArg`", save=False)
        for m in CONGRARG_RE.finditer(body):
            if mask[m.start()] or not _tacpos(body, m.start()) or not _end_ok(body, m.end()):
                continue
            arg = m.group(1).strip()
            if arg:
                for rep in ("apply congrArg", "apply congrArg _"):
                    if arg != "_" or rep == "apply congrArg":
                        em.add("micro:congr", body[:m.start()] + rep + body[m.end():], f"`apply congrArg {arg[:30]}` -> `{rep}`", save=False)
            else:
                em.add("micro:congr", body[:m.start()] + "congr 1" + body[m.end():], "`apply congrArg` -> `congr 1`", save=False)
    if "micro:byunnest" in ops:
        pos = 0
        for ln in body.split("\n"):
            start = pos
            pos += len(ln) + 1
            m = UNNEST_RE.match(ln)
            if not m or mask[start + len(m.group(1))] or "?_" in ln or "--" in ln:
                continue
            ind, rest = m.group(1), m.group(3)
            if not rest.endswith(")"):
                continue
            lm = _mask(rest); lp = _pairs(rest, lm)
            op_ = [o for o, c in lp.items() if c == len(rest) - 1 and rest[o] == "("]
            if not op_:
                continue
            o = op_[0]
            inner = rest[o + 1:-1].strip()
            if not re.match(r"by(?![\w'])", inner) or o == 0:
                continue
            F, T = rest[:o].rstrip(), inner[2:].strip()
            if not F or not T or not ind:
                continue
            new_ln = f"{ind}apply {F}\n{ind}{T}"
            em.add("micro:byunnest", body[:start] + new_ln + body[start + len(ln):], f"`{m.group(2)} .. (by ..)` unnested @L{K.line_of(body, start)}")
    return em.out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="micro candidates of one declaration (no compile)")
    ap.add_argument("--file", required=True); ap.add_argument("--statement-file", required=True)
    a = ap.parse_args(argv)
    proof = Path(a.file).read_text(); stmt = Path(a.statement_file).read_text().rstrip("\n")
    for c in candidates(proof, stmt):
        print(json.dumps({"op": c["op"], "note": c["note"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
