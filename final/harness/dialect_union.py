#!/usr/bin/env python3
"""Union-derived dialect rules (b102b, 2026-11-01): more deterministic, model-free source-to-source rewrites, same contract as harness/dialect.py.

    candidates(proof, statement, *, exchange=None, max_per_op=MAX_PER_OP, ctx=None) -> [{"op": "udialect:<rule>", "decl", "note", "tokens"}]

Where they come from. A $0 comparison of the closed pipeline's finals with the best union proofs on the warm-up (docs/b102b_union_mining.md)
split the gap into style (same lemmas and induction scheme, written in fewer tokens) and structure (another decomposition). The style
part that the existing families do not already reach (harness/dialect.py rules, harness/dialect_unhyg.py, T4, the sweep) gave the rules
below. They are GENERIC: no row names, no lemma names, no proof fragments, no tables; every rule reads only the given proof's own text (its
binder names, its indentation and bracket structure) and the statement's own hypothesis names, and writes Lean core syntax (`.1` / `.2`
projections, `subst_vars`, `simp only`, `with_reducible`). The statement is never edited. Candidates are UNVERIFIED: the caller compiles
each one on every pin and banks only a strictly better official score.

Rules (each as single sites and as one all-sites edit):
  projtail    a flat anonymous-constructor pattern (`obtain` / `have` / `let ⟨..⟩ := e`, `rcases e with ⟨..⟩`, an `intro` / `rintro`
              argument, `fun ⟨..⟩ =>` / `λ⟨..⟩ =>`) keeps its first k names and binds the rest as ONE name; every later use of a
              collapsed name becomes that name's numeric projection path (`h.1`, `h.2.1`, ..., `h.2.2`). A projection path is one lexer
              token, so each collapsed name saves its own token and its comma (k = 0: the whole pattern, brackets too). Skipped when a
              collapsed name is bound again in its scope, used in a hypothesis position (`at`, `clear`, `revert`, `subst`, `specialize`,
              `generalizing`, `induction`, `rename_i`), as a named argument `(x := ..)` or after `@`. Existential witnesses cannot be
              projected: those candidates simply do not compile (k >= 1 keeps them).
  convdrop    (OPT-IN) a `conv_lhs` / `conv_rhs` / `conv` block (no `at` / `in`) whose body rewrites: (i) the header dropped when the body has no
              navigation; (ii) the header and the navigation lines (`enter`, `congr`, `ext`, `arg`, `lhs`, `rhs`, `skip`) dropped;
              (iii) as (ii) with `rw` / `rewrite` / `erw` written `simp only` (rewrites under binders the navigation reached).
  substvars   (OPT-IN) the statement has hypotheses `(h : x = e)` defining a local `x`: `subst_vars` first, the items naming those hypotheses
              dropped from rewrite / simp lists (an emptied `rw` line dropped); proposed only when neither the hypothesis nor `x` is
              named anywhere else in the proof.
  wreducible  (OPT-IN, op not in DEFAULT_OPS: one MORE token, a heartbeat lever) a closing `assumption` / `exact e` / `apply e` / `rfl`
              line (alone or under `all_goals` / `any_goals`) run under `with_reducible`; only proposed when ctx["opt_in"] lists it.
Every rule except wreducible proposes only candidates with fewer tokens than the proof (scorer/tokenize.py). Default ops: projtail; an
opt-in op runs when ctx["opt_in"] or the ctx["ops"] allow-list names it."""
from __future__ import annotations

import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from harness.dialect import blank, dedent, extent, ident_char, indent, scope_end, _ident_positions  # noqa: E402
from scorer.tokenize import count_tokens, split_declaration  # noqa: E402

FAMILY = "udialect"
MAX_CANDS = 300
MAX_PER_OP = 80
MAX_K_PER_SITE = 6         # projtail: split points tried per site (k = 0 .. n-2, fewest kept names first)

NAME_RE = r"[^\s,⟨⟩()\[\]{}|:=@$]+"
FLAT_RE = re.compile(r"⟨([^⟨⟩()\[\]|]*)⟩")
HYP_POS_RE = re.compile(r"\b(at|clear|revert|subst|specialize|generalizing|induction|rename_i)\b[^\n;]*$")
BIND_HEADS = r"(?:intro|intros|rintro|obtain|have|let|set|generalize|by_cases|choose|funext|ext|introv)"


# ---------------------------------------------------------------- projtail
def _elements(inner: str) -> list[str] | None:
    parts = [p.strip() for p in inner.split(",")]
    if len(parts) < 2 or any(not p for p in parts):
        return None
    return parts


def _plain(p: str) -> bool:
    return p == "_" or (bool(re.fullmatch(NAME_RE, p)) and p not in ("rfl", "-") and not p[0].isdigit() and ident_char(p[0]))


def _rebound(name: str, text: str) -> bool:
    """`name` is bound again somewhere in text (a binder head's argument list, a pattern, a case / match arm, a lambda)."""
    n = re.escape(name)
    w = rf"(?<![\w.'!?]){n}(?![\w'!?])"
    pats = [rf"(?<![\w.']){BIND_HEADS}\b[^\n:=]*{w}",                 # intro x / have x / obtain x ... (before any `:` / `:=`)
            rf"⟨[^⟨⟩\n]*{w}[^⟨⟩\n]*⟩\s*(?::[^=\n]*)?:=",     # ⟨.. x ..⟩ :=
            rf"(?<![\w.'])(?:case'?|next)\b[^\n=]*{w}[^\n]*=>",
            rf"^\s*\|[^\n=]*{w}[^\n]*=>",
            rf"(?:(?<![\w.'])fun\b|λ)[^=\n]*{w}[^\n]*=>",
            rf"(?<![\w.'])with\b[^\n]*{w}"]
    return any(re.search(p, text, re.M) for p in pats)


def _bad_use(name: str, text: str, positions: list[int]) -> bool:
    for p in positions:
        line_start = text.rfind("\n", 0, p) + 1
        before = text[line_start:p]
        if HYP_POS_RE.search(before):
            return True
        if before.rstrip().endswith("@"):
            return True
        if re.match(r"\s*:=", text[p + len(name):]) and before.rstrip().endswith("("):
            return True
    return False


def _rename_uses(text: str, mapping: dict) -> str | None:
    """Every identifier use of a mapped name replaced (all names at once); None when one is rebound or used in a bad position."""
    edits = []
    for name, new in mapping.items():
        pos = _ident_positions(name, text)
        if not pos:
            continue
        if _rebound(name, text) or _bad_use(name, text, pos):
            return None
        edits += [(p, p + len(name), new) for p in pos]
    edits.sort()
    for (a, b, _), (c, d, _) in zip(edits, edits[1:]):
        if c < b:
            return None
    for a, b, r in reversed(edits):
        text = text[:a] + r + text[b:]
    return text


def _paths(m: int) -> list[str]:
    return [".2" * j + ".1" for j in range(m - 1)] + [".2" * (m - 1)]


def _collapse(parts: list[str], k: int):
    """(new pattern text, {old name: new use text}) keeping parts[:k] and binding the rest as one name; None if not collapsible."""
    suf = parts[k:]
    if len(suf) < 2 or not all(_plain(p) for p in suf):
        return None
    named = [p for p in suf if p != "_"]
    if not named:
        return None
    B = named[0]
    mapping = {p: B + path for p, path in zip(suf, _paths(len(suf))) if p != "_"}
    pat = B if k == 0 else "⟨" + ", ".join(parts[:k] + [B]) + "⟩"
    return pat, mapping


def _projtail_sites(lines):
    """(line index, span start, span end, inner text, scope kind) of each flat pattern at a binding site."""
    sites = []
    for i, l in enumerate(lines):
        if "<;>" in l:
            continue
        m = re.match(r"^(\s*)(?:·\s*)?(obtain|have|let)\s+(⟨[^⟨⟩()\[\]|]*⟩)\s*(?::[^=]*)?:=", l)
        if m:
            sites.append((i, m.start(3), m.end(3), m.group(3)[1:-1], "block_after_extent"))
        m = re.match(r"^(\s*)(?:·\s*)?rcases\s+.+?\s+with\s+(⟨[^⟨⟩()\[\]|]*⟩)\s*$", l)
        if m:
            sites.append((i, m.start(2), m.end(2), m.group(2)[1:-1], "block_after_line"))
        m = re.match(r"^(\s*)(?:·\s*)?(intro|rintro)\s+(.*)$", l)
        if m:
            for fm in FLAT_RE.finditer(l, m.start(3)):
                sites.append((i, fm.start(), fm.end(), fm.group(1), "block_after_line"))
        for fm in re.finditer(r"(?:\bfun\s*|λ\s*)(⟨[^⟨⟩()\[\]|]*⟩)\s*=>", l):
            sites.append((i, fm.start(1), fm.end(1), fm.group(1)[1:-1], "lambda"))
    return sites


def _lambda_scope_end(text: str, start: int) -> int:
    """End of a lambda body starting at text[start]: the first unmatched closer or depth-0 comma (the end of text otherwise)."""
    d = 0
    for k in range(start, len(text)):
        ch = text[k]
        if ch in "([{⟨":
            d += 1
        elif ch in ")]}⟩":
            if d == 0:
                return k
            d -= 1
        elif ch == "," and d == 0:
            return k
    return len(text)


def _projtail_edit(lines, site, k):
    i, a, b, inner, kind = site
    parts = _elements(inner)
    if parts is None:
        return None
    got = _collapse(parts, k)
    if got is None:
        return None
    pat, mapping = got
    new_line = lines[i][:a] + pat + lines[i][b:]
    if k == 0:   # a single-name rcases / obtain pattern on a local does not bind that name (it keeps the local): write `have`
        m = re.match(r"^(\s*(?:·\s*)?)obtain\b", new_line)
        if m:
            new_line = m.group(1) + "have" + new_line[m.end():]
        m = re.match(r"^(\s*(?:·\s*)?)rcases\s+(.+?)\s+with\s+" + re.escape(pat) + r"\s*$", new_line)
        if m:
            new_line = f"{m.group(1)}have {pat} := {m.group(2)}"
    if kind == "lambda":
        # scope: from after the `=>` to the lambda body's end, inside the line's own extent
        e = extent(lines, i)
        seg = "\n".join([new_line] + lines[i + 1:e])
        arrow = seg.find("=>", a + len(pat))
        if arrow < 0:
            return None
        s0 = arrow + 2
        s1 = _lambda_scope_end(seg, s0)
        body = _rename_uses(seg[s0:s1], mapping)
        if body is None or body == seg[s0:s1]:
            return None
        seg = seg[:s0] + body + seg[s1:]
        return lines[:i] + seg.split("\n") + lines[e:]
    s0 = extent(lines, i) if kind == "block_after_extent" else i + 1
    s1 = scope_end(lines, i)
    if s0 >= s1:
        return None
    scope = "\n".join(lines[s0:s1])
    new_scope = _rename_uses(scope, mapping)
    if new_scope is None or new_scope == scope:
        return None
    return lines[:i] + [new_line] + lines[i + 1:s0] + new_scope.split("\n") + lines[s1:]


def r_projtail(lines, statement=None):
    out = []
    sites = _projtail_sites(lines)
    best_per_site = []
    for si, st in enumerate(sites):
        parts = _elements(st[3])
        if parts is None:
            continue
        got_any = None
        for k in range(0, min(len(parts) - 1, MAX_K_PER_SITE)):
            nl = _projtail_edit(lines, st, k)
            if nl is not None:
                out.append((f"L{st[0]}:k{k}", nl))
                if got_any is None:
                    got_any = k
        if got_any is not None:
            best_per_site.append((si, got_any))
    # all sites at once: each site at its smallest working k, and each site at k = 1 (keeps an existential witness), bottom-up so the
    # line indices of earlier sites stay valid
    for label, pick in (("all", lambda k0, n: k0), ("all_k1", lambda k0, n: max(k0, 1) if n > 2 else k0)):
        if len(best_per_site) < 2:
            break
        cur = list(lines)
        ok = 0
        for si, k0 in sorted(best_per_site, key=lambda t: -sites[t[0]][0]):
            st = _projtail_sites(cur)
            # re-find the same site on the current text (same line, same start)
            match = [s for s in st if s[0] == sites[si][0] and s[1] == sites[si][1]]
            if not match:
                continue
            n = len(_elements(match[0][3]) or [])
            nl = _projtail_edit(cur, match[0], pick(k0, n))
            if nl is not None:
                cur = nl; ok += 1
        if ok >= 2 and cur != lines:
            out.append((label, cur))
    return out


# ---------------------------------------------------------------- convdrop
CONV_RE = re.compile(r"^(\s*)(?:·\s*)?(conv_lhs|conv_rhs|conv)\s*=>\s*(.*)$")
NAV_RE = re.compile(r"^\s*(enter\b|congr\b|ext\b|arg\b|lhs\b|rhs\b|skip\b|intro\b|pattern\b)")
RW_HEAD_RE = re.compile(r"^(\s*)(rw|rewrite|erw)(\s*\[)")


def _conv_variants(lines, i):
    m = CONV_RE.match(lines[i])
    if not m:
        return []
    d = indent(lines[i])
    e = extent(lines, i)
    body = ([" " * (d + 2) + m.group(3)] if m.group(3).strip() else []) + lines[i + 1:e]
    body = [x for x in body if not blank(x)]
    if not body:
        return []
    base = min(indent(x) for x in body)
    if any(re.match(r"^\s*(conv|conv_lhs|conv_rhs)\b", x) for x in body):
        return []
    # only flat bodies (the navigation lines and the rewrites at one indentation, continuation lines deeper)
    nav = [x for x in body if indent(x) == base and NAV_RE.match(x)]
    keep = [x for x in body if not (indent(x) == base and NAV_RE.match(x))]
    if not keep:
        return []
    out = []
    ded = dedent(keep, base - d, d)
    if not nav:
        out.append(("plain", lines[:i] + ded + lines[e:]))
    else:
        out.append(("nav", lines[:i] + ded + lines[e:]))
    simp = [RW_HEAD_RE.sub(lambda mm: f"{mm.group(1)}simp only{mm.group(3)}", x) for x in ded]
    if simp != ded:
        out.append(("simp", lines[:i] + simp + lines[e:]))
    return out


def r_convdrop(lines, statement=None):
    out = []
    sites = [i for i, l in enumerate(lines) if CONV_RE.match(l)]
    for i in sites:
        for kind, nl in _conv_variants(lines, i):
            out.append((f"L{i}:{kind}", nl))
    if len(sites) >= 2:
        for want in ("nav", "simp"):
            cur = list(lines)
            for i in sorted(sites, reverse=True):
                vs = dict(_conv_variants(cur, i))
                nl = vs.get(want) or vs.get("plain") or vs.get("nav")
                if nl is not None:
                    cur = nl
            if cur != lines:
                out.append((f"all_{want}", cur))
    return out


# ---------------------------------------------------------------- substvars
def _def_hyps(statement: str) -> list[tuple[str, str]]:
    """(hypothesis, variable) for statement binders `(h : x = e)` where x is a plain name bound earlier in the statement."""
    out = []
    for m in re.finditer(r"\(\s*([^\s:()]+)\s*:\s*([^\s:()=]+)\s*=\s", statement):
        h, x = m.group(1), m.group(2)
        if not re.fullmatch(NAME_RE, x) or "." in x:
            continue
        pre = statement[:m.start()]
        if re.search(rf"[({{]\s*(?:[^\s:(){{}}]+\s+)*{re.escape(x)}(?:\s+[^\s:(){{}}]+)*\s*:", pre):
            out.append((h, x))
    return out


def _drop_items(text: str, name: str) -> str:
    """Remove `name` / `← name` / `↓name` items from bracket lists; an emptied rw / rewrite / erw tactic line is removed."""
    item = rf"\s*(?:←\s*|↓\s*|<-\s*)?{re.escape(name)}(?![\w'.!?])\s*"
    text = re.sub(rf"\[{item},", "[", text)
    text = re.sub(rf",{item}(?=[,\]])", "", text)
    text = re.sub(rf"\[{item}\]", "[]", text)
    lines = [l for l in text.split("\n") if not re.match(r"^\s*(?:·\s*)?(?:rw|rewrite|erw|nth_rewrite\s+\d+)\s*\[\]\s*$", l)]
    lines = [re.sub(r"\s*\[\](?=\s|$)", "", l) if re.match(r"^\s*(?:·\s*)?(?:simp|simp_all|dsimp|simp_rw|field_simp|norm_num)\b", l) else l
             for l in lines]
    return "\n".join(lines)


def r_substvars(lines, statement=None):
    if not statement:
        return []
    hyps = _def_hyps(statement)
    if not hyps:
        return []
    body = "\n".join(lines)
    new = body
    for h, _ in hyps:
        new = _drop_items(new, h)
    if any(_ident_positions(h, new) or _ident_positions(x, new) for h, x in hyps):
        return []
    nl = new.split("\n")
    # insert `subst_vars` as the first tactic of the top block
    m = re.match(r"^(\s*by)(\s*)(.*)$", nl[0])
    if not m:
        return []
    rest = m.group(3).strip()
    if rest in ("", "unhygienic"):
        j = next((t for t in range(1, len(nl)) if not blank(nl[t])), None)
        if j is None:
            return []
        out = nl[:j] + [" " * indent(nl[j]) + "subst_vars"] + nl[j:]
    else:                     # a tactic on the `by` line itself: not handled (no layout guess)
        return []
    return [("top", out)]


# ---------------------------------------------------------------- wreducible (opt-in: one more token)
WR_RE = re.compile(r"^(\s*)((?:·\s*)?)((?:all_goals|any_goals)\s+)?(assumption|exact\s.+|apply\s.+|rfl)\s*$")


def r_wreducible(lines, statement=None):
    out = []
    sites = [i for i, l in enumerate(lines) if WR_RE.match(l) and "with_reducible" not in l]
    for i in sites:
        m = WR_RE.match(lines[i])
        nl = list(lines)
        nl[i] = f"{m.group(1)}{m.group(2)}{m.group(3) or ''}with_reducible {m.group(4)}"
        out.append((f"L{i}", nl))
    return out


RULES = [("projtail", r_projtail), ("convdrop", r_convdrop), ("substvars", r_substvars), ("wreducible", r_wreducible)]
# Measured 2026-11-01 (docs/b102b_union_mining.md section 4): projtail banked on finb 1/15 and on a dev pool 4/9 (12 of 12 compiling
# candidates strictly better); convdrop 0 banks (14 candidates, 1 compiled, more heartbeats), substvars no site in 615 stored finals,
# wreducible 0 of 84 (and it duplicates the sweep's addwr). So only projtail is a default op; the others run when listed.
OPT_IN = {"convdrop", "substvars", "wreducible"}
OPS = tuple(f"{FAMILY}:{n}" for n, _ in RULES)
DEFAULT_OPS = tuple(f"{FAMILY}:{n}" for n, _ in RULES if n not in OPT_IN)


def rule_candidates(proof: str, statement: str, max_cands: int = MAX_CANDS, rules=None, opt_in=()) -> list[dict]:
    body = split_declaration(proof.rstrip(), statement)
    if body is None:
        return []
    head = proof.rstrip()[:len(proof.rstrip()) - len(body)]
    lines = body.split("\n")
    base_tok = count_tokens(body)
    seen = {body.rstrip()}
    out = []
    for name, fn in RULES:
        if (rules is not None and name not in rules) or (name in OPT_IN and name not in opt_in and (rules is None or name not in rules)):
            continue
        try:
            res = fn(lines, statement)
        except Exception:  # noqa: BLE001  (a rule that cannot parse this proof proposes nothing)
            res = []
        for note, nl in res:
            nb = "\n".join(nl).rstrip()
            if nb in seen or re.match(r"[ \t]*\n", nb):
                continue
            seen.add(nb)
            t = count_tokens(nb)
            if t >= base_tok and name != "wreducible":
                continue
            if name == "wreducible" and t > base_tok + 1:
                continue
            out.append({"op": f"{FAMILY}:{name}", "decl": head + nb + "\n", "note": note, "tokens": t})
    out.sort(key=lambda c: c["tokens"])
    return out[:max_cands]


def candidates(proof: str, statement: str, *, exchange: float | None = None, max_per_op: int = MAX_PER_OP, ctx: dict | None = None,
               max_cands: int = MAX_CANDS) -> list[dict]:
    """The family's candidates (pure: no compile, no I/O): ctx["ops"] an allow-list (with or without the prefix), ctx["opt_in"] adds an
    opt-in op; at most max_per_op per op, fewest tokens first."""
    ctx = ctx or {}
    want = ctx.get("ops")
    rules = None if not want else {str(o).split(":", 1)[-1] for o in want}
    opt_in = {str(o).split(":", 1)[-1] for o in (ctx.get("opt_in") or ())}
    out, per = [], {}
    for c in rule_candidates(proof, statement, max_cands=max_cands, rules=rules, opt_in=opt_in):
        if per.get(c["op"], 0) >= int(max_per_op):
            continue
        per[c["op"]] = per.get(c["op"], 0) + 1
        out.append(c)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", required=True); ap.add_argument("--statement-file", required=True)
    ap.add_argument("--opt-in", nargs="*", default=[])
    a = ap.parse_args()
    for c in candidates(Path(a.file).read_text(), Path(a.statement_file).read_text(), ctx={"opt_in": a.opt_in}):
        print(json.dumps(c, ensure_ascii=False))
