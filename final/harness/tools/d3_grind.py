#!/usr/bin/env python3
"""Bet D3, grind-hint compaction (docs/closed_plus5_per_problem.md, "End-stage ops"; bet-backend-replay 2026-11-02): an end-stage family
("grindmin", registered only by harness/end_ops.register(), never by default) with the harness/sweep.candidates contract. Pure: no compile,
no I/O, no table, no row knowledge; every token of a candidate comes from the proof being edited (a hint list's own items and the namespaces
of its own identifiers) or is Lean syntax. The caller measures every candidate back to back with its incumbent (batch screen, paired
scorer.accept.decide, all-pin confirmation); nothing here is trusted.

    candidates(proof, statement, *, exchange=None, max_per_op=None, ctx=None) -> [{"op", "decl", "note"}]

A grind hint list is the `[...]` of a `grind` tactic (also `grind only`, after its configuration groups `(gen := 2)` and `+flag` / `-flag`
options; never `grind?`). Ops, every one generated per list:
  grindmin:set    the namespace form: two or more items of the list that are a bare identifier `N.c` (an optional modifier such as `→`, `←`,
                  `=` before it) with the same namespace N are replaced by ONE item, `N` and `intro N` (two candidates), at the first one's
                  place (Lean's grind takes an inductive type's name as a hint for its constructors / its cases; whether this proof
                  compiles with it, and reads higher, is the end stage's question)
  grindmin:ddmin  ddmin over the list (Zeller's delta debugging): its test sequence at granularity g = 2, 4, 8, ... up to the list's
                  length n, each of the g chunks kept alone (a subset) and each left out (a complement), and the empty list (`[...]` and
                  `only` kept as written are dropped together with the brackets); ordered by items removed (most first), then position.
                  The test is the end stage's own acceptance; its greedy passes (harness/end_ops.PASSES) re-run the sequence on the reduced
                  list, which is ddmin's restart after a successful reduction.
ctx: {"ops": [...]} an allow-list (the end stage's), op names with or without the "grindmin:" prefix.
    python3 harness/tools/d3_grind.py --file proof.lean --statement-file stmt.txt     candidates as JSON lines"""
from __future__ import annotations

import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.normalize import _mask, _pairs  # noqa: E402
from harness.lint_delete import _list_items  # noqa: E402
from scorer.tokenize import split_declaration, count_tokens  # noqa: E402

FAMILY = "grindmin"
OPS = (f"{FAMILY}:set", f"{FAMILY}:ddmin")
ALL_OPS = OPS
OPT_IN_OPS: tuple = ()
DEFAULT_OPS = OPS
TABLES: dict = {}
MAX_PER_OP = 64        # ddmin's sequence on a 15-item list is ~60 lists; the batch screen reads 24 per compile
MAX_LISTS = 8          # grind lists per proof (the first ones in text order)

IDENT = r"[^\W\d][\w'!?₀-₉]*(?:\.(?:\d+|[^\W\d][\w'!?₀-₉]*))*"
GRIND_RE = re.compile(r"(?<![\w.'?!₀-₉])grind(?![\w'?!₀-₉])")
FLAG_RE = re.compile(r"[+-][^\W\d][\w'.]*")
MOD_RE = re.compile(r"^(?:→|←|=|_=_|⇒|←=|\.|!|usr|ext|inj|intro|cases(?:\s+eager)?)\s*")
BARE_RE = re.compile(r"^(%s)$" % IDENT)


def _op_names(ops) -> list[str]:
    out = []
    for o in (ops.split(",") if isinstance(ops, str) else list(ops or [])):
        o = str(o).strip()
        if o:
            out.append(o if o.startswith(FAMILY + ":") else f"{FAMILY}:{o}")
    return out


def ops_for(ctx: dict | None) -> tuple[str, ...]:
    ctx = ctx or {}
    if ctx.get("ops") is not None:
        want = set(_op_names(ctx["ops"]))
        return tuple(o for o in OPS if o in want)
    return DEFAULT_OPS


def grind_lists(body: str) -> list[dict]:
    """The grind hint lists of a proof body: [{"g": index of `grind`, "lb", "rb": the brackets, "items": [(a, b)], "only": span or None}]."""
    mask = _mask(body)
    pairs = _pairs(body, mask)
    out = []
    for m in GRIND_RE.finditer(body):
        g = m.start()
        if mask[g] or (g > 0 and body[g - 1] == "."):
            continue
        p = m.end()
        only = None
        while True:   # options before the list: whitespace (one line break allowed), `only`, `(...)` groups, `+flag` / `-flag`
            q = p
            while q < len(body) and body[q] in " \t":
                q += 1
            if q < len(body) and body[q] == "\n":
                q2 = q + 1
                while q2 < len(body) and body[q2] in " \t":
                    q2 += 1
                if q2 < len(body) and body[q2] in "[(+-" and not body.startswith("--", q2):
                    q = q2
            if q >= len(body) or mask[q]:
                break
            if body.startswith("only", q) and not re.match(r"[\w'.]", body[q + 4:q + 5] or " "):
                only = (q, q + 4); p = q + 4; continue
            if body[q] == "(" and q in pairs:
                p = pairs[q] + 1; continue
            fm = FLAG_RE.match(body, q)
            if fm and not body.startswith("--", q):
                p = fm.end(); continue
            p = q
            break
        if p < len(body) and body[p] == "[" and not mask[p] and p in pairs:
            items = _list_items(body, mask, pairs, p)
            if items:
                out.append({"g": g, "lb": p, "rb": pairs[p], "items": items, "only": only})
        if len(out) >= MAX_LISTS:
            break
    return out


def _with_items(body: str, L: dict, keep: list[str]) -> str:
    """The body with list L's items replaced by `keep` (", "-joined); an empty `keep` drops the brackets and the blanks before them."""
    lb, rb = L["lb"], L["rb"]
    if keep:
        return body[:lb + 1] + ", ".join(keep) + body[rb:]
    a = lb
    while a > 0 and body[a - 1] in " \t":
        a -= 1
    return body[:a] + body[rb + 1:]


def _namespace(item: str) -> str | None:
    """N of a bare (optionally modified) identifier item `[mod] N.c`, else None."""
    t = MOD_RE.sub("", item.strip(), count=1).strip()
    m = BARE_RE.match(t)
    if not m or "." not in t:
        return None
    ns = t.rsplit(".", 1)[0]
    return ns if ns and not ns[-1].isdigit() else None


def set_lists(items: list[str]) -> list[tuple[list[str], str]]:
    """grindmin:set on one list's item texts: [(new items, note)]."""
    groups: dict = {}
    for i, it in enumerate(items):
        ns = _namespace(it)
        if ns:
            groups.setdefault(ns, []).append(i)
    out = []
    for ns, idx in groups.items():
        if len(idx) < 2:
            continue
        for rep in (ns, f"intro {ns}"):
            new = []
            for i, it in enumerate(items):
                if i == idx[0]:
                    new.append(rep)
                elif i not in idx:
                    new.append(it)
            out.append((new, f"{len(idx)} `{ns}.*` hints -> `{rep}`"))
    return out


def ddmin_lists(items: list[str]) -> list[tuple[list[str], str]]:
    """grindmin:ddmin on one list's item texts: [(kept items, note)], most items removed first, then by position; distinct, never the list."""
    n = len(items)
    seq, seen = [], {tuple(items)}

    def add(keep_idx, note):
        kept = [items[i] for i in keep_idx]
        k = tuple(kept)
        if k not in seen:
            seen.add(k); seq.append((n - len(kept), min(set(range(n)) - set(keep_idx)) if len(kept) < n else 0, kept, note))
    add([], "all hints dropped")
    g = 2
    while True:
        g = min(g, n)
        size = n / g
        chunks = [list(range(int(round(j * size)), int(round((j + 1) * size)))) for j in range(g)]
        for j, ch in enumerate(chunks):
            if not ch:
                continue
            add(ch, f"ddmin g={g}: chunk {j + 1}/{g} kept alone ({len(ch)} of {n})")
            add([i for i in range(n) if i not in ch], f"ddmin g={g}: chunk {j + 1}/{g} left out ({len(ch)} of {n})")
        if g >= n:
            break
        g *= 2
    seq.sort(key=lambda x: (-x[0], x[1]))
    return [(kept, note) for _r, _p, kept, note in seq]


def candidates(proof: str, statement: str, *, exchange: float | None = None, max_per_op: int | None = None,
               ctx: dict | None = None) -> list[dict]:
    """[{"op", "decl", "note"}] for the ops of ops_for(ctx), OPS order, then the lists in text order; distinct texts, each saving tokens."""
    ops = ops_for(ctx)
    body = split_declaration(proof, statement)
    if body is None or not ops:
        return []
    head = proof[:len(proof) - len(body)]
    t0 = count_tokens(body)
    cap = int(max_per_op) if max_per_op else MAX_PER_OP
    out, seen = [], {proof.rstrip()}
    lists = grind_lists(body)
    for op in ops:
        n = 0
        for L in lists:
            items = [body[a:b] for a, b in L["items"]]
            try:
                gen = set_lists(items) if op.endswith(":set") else ddmin_lists(items)
            except Exception:  # noqa: BLE001  (a generator fault never stops the others)
                continue
            for keep, note in gen:
                if n >= cap:
                    break
                nb = _with_items(body, L, keep)
                decl = head + nb
                if decl.rstrip() in seen or split_declaration(decl, statement) != nb or count_tokens(nb) >= t0:
                    continue
                seen.add(decl.rstrip()); n += 1
                line = decl.count("\n", 0, len(head) + L["g"]) + 1
                out.append({"op": op, "decl": decl, "note": f"{note} @L{line}"})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="grind-hint compaction candidates of one declaration (no compile)")
    ap.add_argument("--file", required=True); ap.add_argument("--statement-file", required=True)
    ap.add_argument("--ops", default=",".join(OPS))
    a = ap.parse_args(argv)
    proof = Path(a.file).read_text(); stmt = Path(a.statement_file).read_text().rstrip("\n")
    t0 = count_tokens(split_declaration(proof, stmt) or "")
    for d in candidates(proof, stmt, ctx={"ops": _op_names(a.ops)}):
        print(json.dumps({"op": d["op"], "note": d["note"], "dtok": count_tokens(split_declaration(d["decl"], stmt)) - t0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
