#!/usr/bin/env python3
"""T2, goal-order and loop-schedule restructurer, R2 (docs/tools_build_plan.md; spec item a2). Pure: no compile, no I/O beyond
reading its own generated table, no row knowledge. It re-arranges the proof's own tactics; the only tokens it adds are the goal-list
combinators `rotate_left`, `any_goals`, `all_goals`, `repeat`, `repeat'` (TABLES["t2_combinators"]) and, at an intro-family line, the
intro-family heads `intro`, `intros`, `rintro` (TABLES["t2_intro_forms"]). The caller measures every candidate back to back with its
incumbent and banks it only through scorer/accept.decide.

    candidates(proof, statement, *, exchange=None, max_per_op=40, ctx=None) -> [{"op", "decl", "note"}]
      the harness/sweep.candidates contract: full declarations with the statement byte-identical, unique, deterministic, OPS order and
      cheapest (fewest tokens) first inside each op, at most max_per_op per op. `exchange` is accepted and not used. ctx is optional:
      ctx["goals"] = [{"line": declaration line (1-based), "n_goals": goals before that line}] (harness/goals.py) bounds the rotations.

Operators (R1, unchanged unless marked R2)
  t2:intros     a named intro / intros / rintro line (simple names or `_`) whose names are not used later in its block -> `intros`,
                `intro` (one name), `intro` + `intros`, `repeat intro`; names used only as a prefix -> `intro <prefix>` + `intros`.
                R2: the same forms for an `intro` / `rintro` line with anonymous-constructor patterns (`⟨a, b⟩`, no `rfl`, `-`, `|`, `@`
                or `:`) none of whose names is used later in its block
  t2:intromerge adjacent intro-family lines -> one line: named pairs with an `intros` or `rintro` side (`intro`/`intro` pairs are
                hb_rewrite's intromerge), `intro` + `intros` / `intros` + `intros` -> `intros`, unused-name `intro x` + `intros` -> `intros`.
                R2: NON-ADJACENT named lines of one block whose lines in between only bind or rewrite hypotheses (a `have` / `haveI` /
                `letI` / `replace` / `obtain` line with a depth-0 `:=`, `rcases e with p`, `specialize`, `clear`, or any line whose `at`
                location names hypotheses only, no `⊢` / `*`; no depth-0 `|` alternation) and never mention the later line's names: the
                later names join the earlier line (`rintro` when either side is one, else `intro`)
  t2:introdestr R2: an intro-family binder `h` destructured by the next tactic line of its block (`obtain p := h` / `rcases h with p`,
                one line, no type ascription) and used nowhere else in the block -> `rintro` with `p` in place of `h` (`(p)` when `p` is a
                depth-0 alternation)
  t2:funintro   R2: a whole tactic line `refine fun B => ?_` -> `intro B`; `exact fun B => e` / `refine fun B => e` -> `intro B` + `exact e`
                / `refine e`; `exact fun B => by t` -> `intro B` + `t` (a `by` block on the following lines: its lines, dedented). B: simple
                names, `_` or anonymous-constructor patterns (then `rintro`), no type ascription
  t2:altdrop    one alternative of a `first | a | b ...` dropped (a lone survivor loses its `first |`): a tactic line led by wrappers, and
                (R2) the `first` arm of a `<;>` chain
  t2:chain      R2: an arm of a `T <;> ... <;> A` chain (one tactic: its line, deeper continuation lines and following lines that start
                with `<;>`; T led by no wrapper but any_goals / all_goals, no depth-0 `;`, `=>`, `by`, `fun`, `first`, `try`, `calc` or
                `from` before the arm), scheduled on the loop op's placement grid with the line up to the arm as the body. The arm is an
                unwrapped `try S` (it takes the rest of the line), else a parenthesized `(try S)` with later arms U, else the last arm A:
                `try S` -> `any_goals S` after the chain (or after the enclosing all_goals / any_goals block), with U as `all_goals U`
                after it; A = `first | a1 ...` -> the closers (TABLES["t2_closers"]; mixed or unlisted both ways) leave the arm, each
                (or as one `first` group) after the chain or after the enclosing block, under any_goals or all_goals, the rest stay on
                the arm; A any other tactic whose head is not a decomposer -> A on its own line after the chain (the positional k = 0
                form; it compiles only where the head leaves one goal). At most SITE_CAP per site
  t2:loop       `[·] [W] repeat[']? first | a1 | ... | ak` (one line, `(first | ...)` or `|` lines under `first`; W any wrappers): alternatives
                classified from TABLES["t2_closers"] (closer: moves out of the loop; mixed or not in the table: tried in both roles; the
                rest stay in the body). The body is the non-closers (one line each, or kept as one `first`); each closer, one by one or as
                one `first` group, goes before the loop, inside the body after the decomposers, after the loop, or after the enclosing
                all_goals / any_goals block, under any_goals or all_goals, with repeat or repeat'. At most SITE_CAP per site, fewest tokens
                first, ties in the fixed grid order (placement, combinator, loop as listed here).
  t2:try2pos    a `try T`, `all_goals try T`, `all_goals (try T)` or `any_goals T` line (T on that line) deleted and `rotate_left k` + `T`
                (no rotate for k = 0, bare `rotate_left` for k = 1) inserted after one of the earlier tactics of its block (or in place),
                k = 0..min(n - 1, 12) with n from ctx["goals"], 0..12 without it; fewest tokens first, then nearest (distance + k).
                R2: T may continue on deeper lines; the multi-line blocks `try` / `any_goals` / `all_goals try` + an indented block and
                `all_goals` + a block whose only tactic is a `try` (T = the block, dedented) are sites too; `all_goals` + any other block
                is hoisted in place only (k = 0: the block dedented); the `try S` arm of a `<;>` chain (as t2:chain finds it) is
                hoisted out of the chain: `rotate_left k` + `S` (+ `all_goals U` for later arms U) right after the chain, k = 0..12.
                A site continued by a following `<;>` line is only the chain's.
  t2:altorder   R2: one alternative of a one-line `first | ...` (the altdrop sites) moved to the front (token-neutral; alternatives run in
                order, so this only changes which ones fail before the one that succeeds)
Sites: tactic lines only; never a line holding a comment or a string, inside brackets (a `by` in a term), inside a conv block, or in an
attribute. The match conditions above (wrapper words, hypothesis-binding heads, `at` locations) only select sites; no token is emitted
from them. Not here (R3): the probe-based nameless pass under unhygienic with renaming, the per-goal closer probe and never-firing
alternatives, a `try` after `;`, a `first` or plain arm in the middle of a chain, bar-line (`| alt` lines) `first` for altdrop /
altorder, non-adjacent destructuring (`obtain p := h` later in the block) and binders inside patterns for t2:introdestr, the
transparency wrapper grid.
Cost: finders return keys and a builder; a full body is joined only for a candidate being emitted. try2pos keeps per site the
2 * max_per_op + 2 smallest keys (the farther points cannot be emitted), loop and chain keep SITE_CAP schedules per site deduplicated on
the site's own lines, so generation is linear in the sites (a 900-line proof with 150 try lines: well under a second and 20 MB).
Evidence scope (review 2026-10-22): in the $0 reconstruction audit R1's t2:try2pos and t2:loop fired on warm-up-derived proofs only and on
no non-warm-up proof, so in the readouts a T2 bank on a warm-up row is a same-row rebuild (never tuning or adoption evidence) and "fires
somewhere" is judged on non-warm-up rows. T2 stays opt-in (harness/endstage.DEFAULT_FAMILIES is the sweep alone) until the
pre-registered held-out check shows it firing on at least 10% of rows. R2 widened it by the stated syntactic rules above, not by new
templates; the $0 firing count on the 42 tuning-set finals is in the R2 round's readout (counts only).
    python3 harness/tools/t2_schedule.py --file proof.lean --statement-file stmt.txt     candidates as JSON lines (op, note, dtok)"""
from __future__ import annotations

import argparse, itertools, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.normalize import _mask, _pairs  # noqa: E402
import harness.hb_rewrite as HR  # noqa: E402
from scorer.tokenize import split_declaration, count_tokens  # noqa: E402

TABLE_DIR = Path(__file__).resolve().parent / "tables"
CLOSERS_PATH = TABLE_DIR / "t2_closers.json"
TABLES: dict = {
    "t2_closers": {
        "rule": "class of every leading token of Lean core's tactic category, bare and with one term argument, measured on a fixed "
                "synthetic goal battery on every installed core toolchain: closer = closed some goal and never succeeded leaving a goal "
                "open or unchanged; mixed = both; decomposer = never closed, left some open; inert = otherwise (the rule text and the "
                "counts are in the file)",
        "query": "harness/tools/tables/t2_closers_query.lean, run by harness/tools/tables/gen_t2_closers.py",
        "path": "harness/tools/tables/t2_closers.json",
    },
    "t2_combinators": {
        "rule": "the goal-list combinators the T2 spec lets the scheduler add (rotate_left, any_goals, all_goals, repeat, repeat'): core "
                "tactics that only reorder or iterate goals; each checked present in Lean core's tactic token table on every toolchain "
                "(the `combinators` field of t2_closers.json); every other token of a candidate comes from the proof being edited",
        "query": "harness/tools/tables/t2_closers_query.lean (C lines), run by harness/tools/tables/gen_t2_closers.py",
        "path": "harness/tools/tables/t2_closers.json",
    },
    "t2_intro_forms": {
        "rule": "the intro-family heads T2 spec item (i) works with: the nameless forms `intros`, `intro`, `intro` + `intros`, `repeat "
                "intro` (built only from the tokens intro / intros and the combinator repeat), and (R2) `intro` / `rintro` as the head of a "
                "line that takes over binders or patterns already written in the proof (a later intro line's names, the pattern of the "
                "obtain / rcases line that destructures a binder, the binders of a `fun` the line replaces); each head checked present in "
                "Lean core's tactic token table on every toolchain (the `present` field of t2_closers.json); nameless forms only where the "
                "line's names are not used later in its block (no renaming)",
        "query": "harness/tools/tables/t2_closers_query.lean (K lines), run by harness/tools/tables/gen_t2_closers.py",
        "path": "harness/tools/tables/t2_closers.json",
    },
}
OPS = ("t2:intros", "t2:intromerge", "t2:introdestr", "t2:funintro", "t2:altdrop", "t2:chain", "t2:loop", "t2:try2pos",
       "t2:altorder")
MAX_PER_OP = 40
SITE_CAP = 150      # loop / chain schedules kept per site (fewest tokens first)
MAX_ROT = 12        # rotations tried when the goal count is unknown
MAX_EITHER = 4      # mixed / unlisted alternatives tried in both roles one by one; more than this: all body or all closer
IND = "  "

NAME = r"[^\W\d][\w'!?₀-₉]*"
INTRO_RE = re.compile(r"^(?P<ind>[ \t]*)(?P<bul>·[ \t]+)?(?P<head>intro|intros|rintro)(?P<names>(?:[ \t]+(?:" + NAME + r"|_))+)[ \t]*$")
BARE_INTRO_RE = re.compile(r"^(?P<ind>[ \t]*)(?P<head>intro|intros)[ \t]*$")
WRAP = r"(?:any_goals|all_goals|with_[A-Za-z_]+)"
LOOP_RE = re.compile(r"^(?P<ind>[ \t]*)(?P<bul>·[ \t]+)?(?P<wr>(?:" + WRAP + r"[ \t]+)*)(?P<loop>repeat'?)[ \t]+(?P<paren>\([ \t]*)?first(?![\w'!?])[ \t]*")
FIRST_LINE_RE = re.compile(r"^(?P<lead>[ \t]*(?:(?:" + WRAP + r"|repeat'?|try)[ \t]+)*)(?P<paren>\([ \t]*)?first(?![\w'!?])[ \t]*(?P<bars>\|.*)$")
TRY_RE = re.compile(r"^(?P<ind>[ \t]*)(?:(?P<all>all_goals)[ \t]+(?P<p>\([ \t]*)?try|try|(?P<any>any_goals))[ \t]+(?P<t>\S.*?)[ \t]*$")
SKIP_LINE = re.compile(r"^(\||<;>|\)|\]|\}|⟩|,|_\s*[=<≤>≥]|\.\.|calc\b|=>|:=|fun\b|with\b|then\b|else\b)")
CONT_END = (",", "(", "[", "⟨", "{", "<;>", "|", ":=", "←", "$", "<|", "▸", "∘", "→", "↔", "∧", "∨", "=", "≤", "<", "+", "*")
# R2 syntax (site selection only; nothing below is emitted)
INTRO_ANY_RE = re.compile(r"^(?P<ind>[ \t]*)(?P<bul>·[ \t]+)?(?P<head>intro|intros|rintro)[ \t]+(?P<rest>\S.*?)[ \t]*$")
PAT_RE = re.compile(r"⟨[⟨⟩,\s\w'!?₀-₉]*⟩")                 # an anonymous-constructor pattern of names, `_` and nested patterns
LEAD_RE = re.compile(r"[ \t]*(?:·[ \t]+)?")
LEADWRAP_RE = re.compile(r"(?:try|repeat'?|first|focus|iterate|any_goals|all_goals|with_[A-Za-z_]+|·)(?![\w'!?])")
TRYARM_RE = re.compile(r"try(?![\w'!?])[ \t]+(?P<s>\S.*)$")
FIRSTARM_RE = re.compile(r"first(?![\w'!?])[ \t]*(?P<bars>\|.*)$")
BLOCK_HEAD_RE = re.compile(r"(?P<w>try|any_goals|all_goals[ \t]+try|all_goals)")
HYP_HEAD_RE = re.compile(r"(?P<h>have|haveI|letI|replace|obtain|rcases|specialize|clear)(?![\w'!?])")
FUNLINE_RE = re.compile(r"^(?P<ind>[ \t]*)(?P<bul>·[ \t]+)?(?P<head>exact|refine)[ \t]+fun[ \t]+(?P<rest>\S.*?)[ \t]*$")
OBTAIN_RE = re.compile(r"obtain[ \t]+(?P<rest>\S.*)$")
RCASES_RE = re.compile(r"rcases[ \t]+(?P<h>" + NAME + r")[ \t]+with[ \t]+(?P<pat>\S.*)$")
_IDC = re.compile(r"[\w.'!?₀-₉]")
_WORDS0 = ("by", "fun", "first", "from", "at", "with", "calc", "try", "λ")
CHAIN_BAD = {";", "=>", "by", "fun", "first", "try", "calc", "from", "λ"}   # markers that may not precede a chain's last `<;>`


def _scan0(text: str) -> list[tuple[int, str]] | None:
    """Depth-0 markers of one line of code (it holds no comment or string): (index, marker) for `<;>`, `;`, `|`, `:=`, `=>`, `:` and
    the words of _WORDS0; None when its brackets do not balance."""
    out, d, i, n = [], 0, 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "([{⟨":
            d += 1; i += 1; continue
        if ch in ")]}⟩":
            d -= 1
            if d < 0:
                return None
            i += 1; continue
        if d == 0:
            if text.startswith("<;>", i):
                out.append((i, "<;>")); i += 3; continue
            if text.startswith(":=", i) or text.startswith("=>", i):
                out.append((i, text[i:i + 2])); i += 2; continue
            if text.startswith("::", i):
                i += 2; continue
            if ch == ";" or ch == ":":
                out.append((i, ch))
            elif ch == "|" and text[i + 1:i + 2] not in ("|", ">") and text[i - 1:i] not in ("|", "<"):
                out.append((i, "|"))
            elif (i == 0 or not _IDC.match(text[i - 1])):
                for w in _WORDS0:
                    if text.startswith(w, i) and not _IDC.match(text[i + len(w):i + len(w) + 1] or " "):
                        out.append((i, w)); i += len(w) - 1
                        break
        i += 1
    return out if d == 0 else None


def _binders(text: str) -> list[str] | None:
    """Depth-0 whitespace-separated binders of an intro-family line or a `fun`; None when the brackets do not balance."""
    out, d, cur = [], 0, ""
    for ch in text:
        if ch in "([{⟨":
            d += 1
        elif ch in ")]}⟩":
            d -= 1
            if d < 0:
                return None
        if ch in " \t" and d == 0:
            if cur:
                out.append(cur); cur = ""
        else:
            cur += ch
    if d:
        return None
    if cur:
        out.append(cur)
    return out


def _simple(b: str) -> bool:
    return b == "_" or re.fullmatch(NAME, b) is not None


def _pattern(b: str) -> bool:
    """An anonymous-constructor pattern of plain names (no rfl, `-`, `|`, `@`, `:`; nothing that splits goals or substitutes)."""
    return PAT_RE.fullmatch(b) is not None and not re.search(r"(?<![\w'])rfl(?![\w'])", b)


def _pat_names(b: str) -> list[str]:
    return [x for x in re.findall(NAME, b) if x != "_"]


def _wrapped(text: str) -> bool:
    """Is the whole of text one parenthesized group `( ... )`?"""
    if not (text.startswith("(") and text.endswith(")")):
        return False
    d = 0
    for i, ch in enumerate(text):
        d += ch in "([{⟨"
        d -= ch in ")]}⟩"
        if d == 0 and i < len(text) - 1:
            return False
    return d == 0


def _dedent(lines: list[str]) -> list[str]:
    ind = min((len(x) - len(x.lstrip(" \t")) for x in lines if x.strip()), default=0)
    return [x[ind:] if x.strip() else "" for x in lines]


def _ext(B, li: int) -> int:
    """B.extent of line li; for a bullet line, of the bullet's tactic (lines deeper than its content column)."""
    m = LEAD_RE.match(B.lines[li])
    return B.extent(li, len(m.group(0))) if "·" in m.group(0) else B.extent(li)


# ---- the generated closer table -----------------------------------------------------------------------------------------------------
_CLS: dict | None = None


def _classes() -> dict:
    """{token: {"bare": class, "arg": class}} from t2_closers.json; {} when the table is missing (every alternative then goes both ways)."""
    global _CLS
    if _CLS is None:
        try:
            forms = json.loads(CLOSERS_PATH.read_text()).get("forms") or {}
            _CLS = {t: {f: v.get("class") for f, v in fs.items()} for t, fs in forms.items()}
        except (OSError, ValueError):
            _CLS = {}
    return _CLS


def role(alt: str) -> str:
    """closer | either | body for one `first` alternative, from its head token's measured class."""
    m = re.match(r"[^\W\d][\w'!?]*", alt.strip())
    if not m:
        return "either"
    head = m.group(0); forms = _classes().get(head)
    if not forms:
        return "either"
    bare = alt.strip() == head
    cls = forms.get("bare") if bare else (forms.get("arg") or forms.get("bare"))
    if cls == "closer":
        return "closer"
    if cls in ("decomposer", "inert"):
        return "body"
    return "either"


# ---- the line model -----------------------------------------------------------------------------------------------------------------
class _Body:
    def __init__(self, body: str):
        self.body = body
        self.mask = _mask(body)
        self.pairs = _pairs(body, self.mask)
        self.fb = HR._first_by(body, self.mask)
        self.lines = body.split("\n")
        self.starts, p = [], 0
        for ln in self.lines:
            self.starts.append(p); p += len(ln) + 1
        self.spans = [(i, j) for i, j in self.pairs.items() if j > i]
        self._tl: dict = {}
        self._chain: dict = {}
        self.tokens = count_tokens(body)

    def ind(self, li: int) -> int:
        ln = self.lines[li]
        return len(ln) - len(ln.lstrip(" \t"))

    def blank(self, li: int) -> bool:
        """No code on the line (empty, or only a comment)."""
        s = self.starts[li]
        return not any(not self.body[p].isspace() and not self.mask[p] for p in range(s, s + len(self.lines[li])))

    def clean(self, li: int) -> bool:
        """The line holds no comment or string character."""
        s = self.starts[li]
        return not any(self.mask[p] for p in range(s, s + len(self.lines[li])))

    def code(self, li: int) -> str:
        s = self.starts[li]
        return "".join(ch for p, ch in enumerate(self.lines[li], s) if not self.mask[p])

    def in_brackets(self, li: int) -> bool:
        s = self.starts[li] + self.ind(li)
        return any(i < s < j for i, j in self.spans)

    def tactic_line(self, li: int) -> bool:
        """A line that starts a tactic of a tactic block (after the proof's first `by`, not inside brackets or conv, not an alternative
        arm or a continuation of the previous line)."""
        if li in self._tl:
            return self._tl[li]
        self._tl[li] = ok = self._tactic_line(li)
        return ok

    def _tactic_line(self, li: int) -> bool:
        if self.blank(li):
            return False
        s = self.starts[li] + self.ind(li)
        if self.fb < 0 or s <= self.fb or self.mask[s]:
            return False
        if SKIP_LINE.match(self.lines[li].lstrip()) or self.in_brackets(li) or HR._in_conv(self.body, self.mask, s):
            return False
        p = self.prev_code(li)
        if p is None:
            return True
        pc = self.code(p).rstrip()
        if re.search(r"(?<![\w.'!?])by$", pc):          # a `by` block starts here (it must be indented under its line)
            return self.ind(li) > self.ind(p) or p == 0
        if pc.endswith("=>"):                            # `case t =>` / `next =>` / `| pat =>` arms hold tactics; `fun x =>` a term
            pend = self.starts[p] + len(self.lines[p].rstrip())
            return HR._tactic_arrow(self.body, self.mask, pend)
        if pc.endswith(CONT_END) or re.search(r"(?<![\w.'!?])(with|then|else|from|fun|at)$", pc):
            return False
        return True

    def prev_code(self, li: int):
        j = li - 1
        while j >= 0 and self.blank(j):
            j -= 1
        return j if j >= 0 else None

    def extent(self, li: int, col: int | None = None) -> int:
        """Index after line li and its continuation lines, those indented deeper than col (default: li's indent; a bullet's content
        column for the tactic after the bullet); trailing blank lines excluded."""
        c, j, last = (self.ind(li) if col is None else col), li + 1, li
        while j < len(self.lines):
            if not self.blank(j):
                if self.ind(j) <= c:
                    break
                last = j
            j += 1
        return last + 1

    def block_end(self, li: int, strict: bool = False) -> int:
        """Index after the last line of the block holding li: following lines indented >= its indent (> with strict)."""
        c, j, last = self.ind(li), li + 1, li
        while j < len(self.lines):
            if not self.blank(j):
                if self.ind(j) < c or (strict and self.ind(j) == c):
                    break
                last = j
            j += 1
        return last + 1

    def parent(self, li: int):
        c, j = self.ind(li), li - 1
        while j >= 0:
            if not self.blank(j) and self.ind(j) < c:
                return j
            j -= 1
        return None

    def siblings_before(self, li: int) -> list[int]:
        """Earlier tactic lines of li's block at its indent, nearest first; stops at the block opener or at a non-tactic line."""
        c, j, out = self.ind(li), li - 1, []
        while j >= 0:
            if not self.blank(j):
                if self.ind(j) < c:
                    break
                if self.ind(j) == c:
                    if not self.tactic_line(j):
                        break
                    out.append(j)
            j -= 1
        return out

    def uses(self, a: int, b: int, name: str) -> bool:
        """Is `name` used as a word in the code of lines [a, b)?"""
        rx = re.compile(r"(?<![\w.'!?])" + re.escape(name) + r"(?![\w'!?₀-₉])")
        return any(rx.search(self.code(j)) for j in range(a, min(b, len(self.lines))))


def _join(lines: list[str]) -> str:
    return "\n".join(lines)


def _replace(lines: list[str], a: int, b: int, new: list[str]) -> list[str]:
    return lines[:a] + new + lines[b:]


# ---- t2:intros, t2:intromerge ---------------------------------------------------------------------------------------------------------
def _intro_scope(B: _Body, li: int, bullet: bool) -> tuple[int, int]:
    return li + 1, B.block_end(li, strict=bullet)


def _intro_pat_line(B: _Body, li: int):
    """(match, binders) of an `intro` / `rintro` line with at least one anonymous-constructor pattern (R2), else None."""
    m = INTRO_ANY_RE.match(B.lines[li])
    if not m or m.group("head") == "intros" or INTRO_RE.match(B.lines[li]) or not B.clean(li) or not B.tactic_line(li) \
            or _ext(B, li) != li + 1:
        return None
    marks = _scan0(m.group("rest"))
    bs = _binders(m.group("rest"))
    if marks or not bs or not all(_simple(b) or _pattern(b) for b in bs):
        return None
    return m, bs


def _intros(B: _Body) -> list[tuple]:
    out = []
    for li in range(len(B.lines)):
        m = INTRO_RE.match(B.lines[li])
        if not m or not B.clean(li) or not B.tactic_line(li):
            pm = _intro_pat_line(B, li)
            if pm is None:
                continue
            m, bs = pm   # R2: patterns, nameless only when none of their names is used later in the block
            a, b = _intro_scope(B, li, bool(m.group("bul")))
            if any(B.uses(a, b, n) for x in bs for n in _pat_names(x)):
                continue
            lead = m.group("ind") + (m.group("bul") or ""); cont = " " * len(lead); k = len(bs)
            forms = [[lead + "intros"]] + ([[lead + "intro"]] if k == 1 else [[lead + "intro", cont + "intros"], [lead + "repeat intro"]])
            for f in forms:
                out.append(("t2:intros", f"{m.group('head')} {' '.join(bs)} -> {' / '.join(x.strip() for x in f)}"[:60],
                            _replace(B.lines, li, li + 1, f), li))
            continue
        names = m.group("names").split(); k = len(names)
        a, b = _intro_scope(B, li, bool(m.group("bul")))
        used = [n != "_" and B.uses(a, b, n) for n in names]
        lead = m.group("ind") + (m.group("bul") or "")
        cont = " " * (len(lead))   # the indent of a second line in the same block
        forms: list[list[str]] = []
        if not any(used):
            forms.append([lead + "intros"])
            if k == 1:
                forms.append([lead + "intro"])
            if k >= 2:
                forms.append([lead + "intro", cont + "intros"])
                forms.append([lead + "repeat intro"])
        else:
            p = max(i for i, u in enumerate(used) if u) + 1   # names after the last used one are unused
            if k - p >= 2:
                forms.append([lead + "intro " + " ".join(names[:p]), cont + "intros"])
        for f in forms:
            out.append(("t2:intros", f"{m.group('head')} {' '.join(names)} -> {' / '.join(x.strip() for x in f)}"[:60],
                        _replace(B.lines, li, li + 1, f), li))
    return out


def _intromerge(B: _Body) -> list[tuple]:
    out = []
    for li in range(len(B.lines) - 1):
        lj = li + 1
        if not (B.clean(li) and B.clean(lj) and B.tactic_line(li) and B.tactic_line(lj)) or B.ind(li) != B.ind(lj):
            continue
        a, b = B.lines[li], B.lines[lj]
        ma, mb = INTRO_RE.match(a), INTRO_RE.match(b)
        na, nb = BARE_INTRO_RE.match(a), BARE_INTRO_RE.match(b)
        ind = " " * B.ind(li)
        if ma and mb and not ma.group("bul") and not mb.group("bul") and (ma.group("head"), mb.group("head")) != ("intro", "intro"):
            new = ind + "intro " + " ".join(ma.group("names").split() + mb.group("names").split())
            out.append(("t2:intromerge", f"{a.strip()} + {b.strip()}"[:60], _replace(B.lines, li, lj + 1, [new]), li))
        if na and nb and nb.group("head") == "intros":   # intro + intros, intros + intros -> intros
            out.append(("t2:intromerge", f"{a.strip()} + intros", _replace(B.lines, li, lj + 1, [ind + "intros"]), li))
        if ma and nb and not ma.group("bul") and nb.group("head") == "intros":
            names = ma.group("names").split()
            s0, s1 = _intro_scope(B, lj, False)
            if not any(n != "_" and B.uses(s0, s1, n) for n in names):
                out.append(("t2:intromerge", f"{a.strip()} + intros"[:60], _replace(B.lines, li, lj + 1, [ind + "intros"]), li))
    return out + _intromerge_far(B)


def _hyp_only(B: _Body, j: int) -> bool:
    """Does tactic line j (with its continuation lines) only bind or rewrite hypotheses, leaving the goal list as it is?"""
    code = B.code(j).strip()
    marks = _scan0(code)
    if marks is None or any(k in ("|", ";", "<;>") for _, k in marks):
        return False
    m = HYP_HEAD_RE.match(code)
    if m:
        if m.group("h") in ("have", "haveI", "letI", "replace", "obtain"):
            return any(k == ":=" for _, k in marks)          # without `:=` the new fact is a new goal first
        if m.group("h") == "rcases":
            return any(k == "with" for _, k in marks)
        return True
    ats = [p for p, k in marks if k == "at"]
    if not ats or B.extent(j) != j + 1:
        return False
    locs = code[ats[-1] + 2:].split()
    return bool(locs) and all(re.fullmatch(NAME, x) for x in locs)


def _intromerge_far(B: _Body) -> list[tuple]:
    """R2: a named intro-family line merged into an earlier one of its block across hypothesis-only lines."""
    out = []
    for li in range(len(B.lines)):
        ma = INTRO_RE.match(B.lines[li])
        if not ma or ma.group("bul") or not B.clean(li) or not B.tactic_line(li):
            continue
        c, j, between = B.ind(li), li + 1, []
        while j < len(B.lines):
            if B.blank(j):
                j += 1; continue
            if B.ind(j) != c or not B.tactic_line(j) or not B.clean(j) or B.lines[j].lstrip().startswith("·"):
                break
            mb = INTRO_RE.match(B.lines[j])
            if mb:
                if between and not mb.group("bul"):
                    names_b = mb.group("names").split()
                    if not any(n != "_" and B.uses(between[0], j, n) for n in names_b):
                        head = "rintro" if "rintro" in (ma.group("head"), mb.group("head")) else "intro"
                        new = " " * c + head + " " + " ".join(ma.group("names").split() + names_b)
                        lines = _replace(B.lines, j, j + 1, [])
                        out.append(("t2:intromerge", f"{B.lines[li].strip()} + {B.lines[j].strip()} (L+{j - li})"[:60],
                                    _replace(lines, li, li + 1, [new]), li))
                break
            if not _hyp_only(B, j):
                break
            between.append(j)
            j = B.extent(j)
    return out


def _introdestr(B: _Body) -> list[tuple]:
    """R2: an intro-family binder destructured by the next line (`obtain p := h` / `rcases h with p`) -> `rintro ... p ...`."""
    out = []
    for li in range(len(B.lines)):
        m = INTRO_ANY_RE.match(B.lines[li])
        if not m or not B.clean(li) or not B.tactic_line(li) or _ext(B, li) != li + 1:
            continue
        rest = m.group("rest")
        mk = _scan0(rest)
        if mk is None or mk:
            continue
        bs = _binders(rest)
        if not bs or not all(_simple(b) or (m.group("head") != "intros" and _pattern(b)) for b in bs):
            continue
        lead = m.group("ind") + (m.group("bul") or ""); col = len(lead)
        j = li + 1
        while j < len(B.lines) and B.blank(j):
            j += 1
        if j >= len(B.lines) or B.ind(j) != col or not B.clean(j) or not B.tactic_line(j) or _ext(B, j) != j + 1:
            continue
        code = B.lines[j].strip()
        h = pat = None
        mo, mr = OBTAIN_RE.match(code), RCASES_RE.match(code)
        if mo:
            marks = _scan0(mo.group("rest"))
            if not marks:
                continue
            eqs = [q for q, k in marks if k == ":="]
            if len(eqs) != 1 or any(k in (":", ";", "<;>") for _, k in marks):
                continue
            pat, h = mo.group("rest")[:eqs[0]].strip(), mo.group("rest")[eqs[0] + 2:].strip()
        elif mr:
            marks = _scan0(mr.group("pat"))
            if marks is None or any(k in (":", ";", "<;>", ":=") for _, k in marks):
                continue
            h, pat = mr.group("h"), mr.group("pat").strip()
        if not h or not pat or not re.fullmatch(NAME, h) or bs.count(h) != 1:
            continue
        a, b = _intro_scope(B, li, bool(m.group("bul")))
        if B.uses(j + 1, b, h):
            continue
        if any(k == "|" for _, k in (_scan0(pat) or [])) and not _wrapped(pat):
            pat = "(" + pat + ")"
        new = lead + "rintro " + " ".join(pat if x == h else x for x in bs)
        lines = _replace(B.lines, li, j + 1, [new])
        out.append(("t2:introdestr", f"{B.lines[li].strip()} + {code}"[:60], lines, li))
    return out


def _funintro(B: _Body) -> list[tuple]:
    """R2: `refine fun B => ?_` -> `intro B`; `exact|refine fun B => e` -> `intro B` + `exact|refine e`; `exact fun B => by t` -> `intro B`
    + `t` (a `by` block on the next lines: its lines dedented)."""
    out = []
    for li in range(len(B.lines)):
        m = FUNLINE_RE.match(B.lines[li])
        if not m or not B.clean(li) or not B.tactic_line(li):
            continue
        rest = m.group("rest")
        marks = _scan0(rest)
        arrows = [q for q, k in (marks or []) if k == "=>"]
        if not arrows:
            continue
        bt, e = rest[:arrows[0]].strip(), rest[arrows[0] + 2:].strip()
        if any(q < arrows[0] for q, k in marks if k != "=>"):
            continue
        bs = _binders(bt)
        if not bs or not all(_simple(x) or _pattern(x) for x in bs):
            continue
        lead = m.group("ind") + (m.group("bul") or ""); cont = " " * len(lead)
        head = "intro " if all(_simple(x) for x in bs) else "rintro "
        b = _ext(B, li)
        if not all(B.clean(j) for j in range(li, b)):
            continue
        tail = B.lines[li + 1:b]
        first = [lead + head + " ".join(bs)]
        if e == "?_" and m.group("head") == "refine" and not tail:
            new = first
        elif e == "by":
            if not tail:
                continue
            new = first + [cont + x if x.strip() else x for x in _dedent(tail)]
        elif re.match(r"by(?![\w'!?])", e):
            if tail or not e[2:].strip():
                continue
            new = first + [cont + e[2:].strip()]
        elif e:
            if m.group("bul") and tail:
                continue
            new = first + [cont + m.group("head") + " " + e] + tail
        else:
            continue
        out.append(("t2:funintro", f"{m.group('head')} fun {bt} => ... -> {head.strip()}"[:60], _replace(B.lines, li, b, new), li))
    return out


# ---- first alternatives ---------------------------------------------------------------------------------------------------------------
def _split_alts(text: str) -> list[str] | None:
    """Depth-0 `|` alternatives of `| a | b ...` (text starts at the first bar); None when a depth-0 `<;>` makes the grouping ambiguous or
    the brackets do not balance."""
    d, cur, out = 0, "", []
    i = 0
    if not text.lstrip().startswith("|"):
        return None
    text = text.lstrip()[1:]
    while i < len(text):
        ch = text[i]
        if text.startswith("<;>", i) and d == 0:
            return None
        if ch in "([{⟨":
            d += 1
        elif ch in ")]}⟩":
            d -= 1
            if d < 0:
                return None
        if ch == "|" and d == 0 and text[i - 1:i] != "<" and text[i + 1:i + 2] not in ("|", ">") and text[i - 1:i] != "|":
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
        i += 1
    if d != 0:
        return None
    out.append(cur.strip())
    return out if all(out) and len(out) >= 2 else None


def _loop_site(B: _Body, li: int) -> dict | None:
    """A `[W] repeat[']? first | ...` site at line li: {a, b (line range), ind, wr (wrapper words), loop, alts}."""
    ln = B.lines[li]
    m = LOOP_RE.match(ln)
    if not m or not B.tactic_line(li):
        return None
    rest = ln[m.end():]
    b = B.extent(li, len(m.group("ind")) + len(m.group("bul") or "") if m.group("bul") else None)
    if not all(B.clean(j) for j in range(li, b)):
        return None
    if m.group("paren"):
        if b != li + 1 or not rest.rstrip().endswith(")"):
            return None
        alts = _split_alts(rest.rstrip()[:-1])
    elif rest.strip():
        if b != li + 1:
            return None
        alts = _split_alts(rest)
    else:   # `repeat first` with one `| alt` line each below it
        sub = [B.lines[j] for j in range(li + 1, b) if not B.blank(j)]
        if not sub or any(not s.lstrip().startswith("|") for s in sub) or len({len(s) - len(s.lstrip()) for s in sub}) != 1:
            return None
        alts = []
        for s in sub:
            one = _split_alts(s.lstrip())
            if one is not None:
                return None   # two alternatives on one bar line: leave it
            t = s.lstrip()[1:].strip()
            if not t or "<;>" in t:
                return None
            alts.append(t)
        if len(alts) < 2:
            return None
    if not alts:
        return None
    return {"a": li, "b": b, "ind": m.group("ind"), "bul": m.group("bul") or "", "wr": m.group("wr").split(), "loop": m.group("loop"),
            "alts": alts}


def _wrap(ind: str, wr: list[str], seq: list[tuple]) -> list[str]:
    """Lines for the wrapper chain `wr` applied to the tactic sequence `seq` ([(text, [child lines])]) at indent ind."""
    def render(i: str, s: list[tuple]) -> list[str]:
        out = []
        for text, kids in s:
            out.append(i + text)
            out += [i + IND + k for k in kids]
        return out
    if not wr:
        return render(ind, seq)
    if len(seq) == 1 and not seq[0][1]:
        return [ind + " ".join(wr) + " " + seq[0][0]]
    return [ind + " ".join(wr)] + render(ind + IND, seq)


def _schedules(site: dict) -> list[tuple]:
    """(new site lines, lines to insert after the enclosing block, label) for every schedule of the site, in the fixed grid order."""
    alts = site["alts"]; roles = [role(a) for a in alts]
    either = [i for i, r in enumerate(roles) if r == "either"]
    if len(either) <= MAX_EITHER:
        assigns = [dict(zip(either, bits)) for bits in itertools.product((False, True), repeat=len(either))]
    else:
        assigns = [{i: False for i in either}, {i: True for i in either}]
    has_block = any(w in ("any_goals", "all_goals") for w in site["wr"]) or site.get("outer") is not None
    places = ("before", "inbody", "after") + (("block",) if has_block else ())
    combs = ("any_goals", "all_goals")
    out = []
    for asg in assigns:
        closers = [a for i, a in enumerate(alts) if roles[i] == "closer" or (roles[i] == "either" and asg[i])]
        body = [a for i, a in enumerate(alts) if roles[i] == "body" or (roles[i] == "either" and not asg[i])]
        if not closers or not body:
            continue
        shapes = [body] if len(body) == 1 else [["first | " + " | ".join(body)], body]
        units = [[c] for c in closers]
        unit_sets = [("each", units)] if len(closers) <= 3 else [("uniform", units)]
        if len(closers) >= 2:
            unit_sets.append(("group", [["first | " + " | ".join(closers)]]))
        for loop in ("repeat", "repeat'"):
            for shape in shapes:
                for kind, us in unit_sets:
                    if kind == "uniform":   # more than 3 closers: every closer at one shared placement and combinator
                        grids = [tuple([pc] * len(us)) for pc in itertools.product(places, combs)]
                    else:
                        grids = list(itertools.product(itertools.product(places, combs), repeat=len(us)))
                    for grid in grids:
                        before, inbody, after, block = [], [], [], []
                        for u, (pl, cb) in zip(us, grid):
                            line = f"{cb} {u[0]}"
                            {"before": before, "inbody": inbody, "after": after, "block": block}[pl].append(line)
                        if len(shape) == 1 and not inbody:
                            loop_item = (f"{loop} {shape[0]}", [])
                        else:
                            loop_item = (loop, list(shape) + inbody)
                        seq = [(x, []) for x in before] + [loop_item] + [(x, []) for x in after]
                        lab = f"{loop}; " + ", ".join(f"{u[0][:14]}:{pl}/{cb[:3]}" for u, (pl, cb) in zip(us, grid))
                        out.append((seq, block, lab))
    return out


def _loops(B: _Body) -> list[tuple]:
    """(op, note, build, li, key) per kept schedule; build() gives the body lines. Only the site's own new lines (and the lines added after
    the enclosing block) are made per schedule; a full body is built only for the SITE_CAP kept per site, and only when emitted."""
    out = []
    ntok: dict = {}

    def tk(lines: list[str]) -> int:   # the site's lines hold no comment or string, so the count adds up line by line
        n = 0
        for x in lines:
            if x not in ntok:
                ntok[x] = count_tokens(x)
            n += ntok[x]
        return n
    for li in range(len(B.lines)):
        site = _loop_site(B, li)
        if not site:
            continue
        # the enclosing block: the site's own any_goals / all_goals wrapper, else a parent line that is only wrappers with one of them
        site["outer"] = None
        if not site["bul"] and not any(w in ("any_goals", "all_goals") for w in site["wr"]):
            p = B.parent(li)
            if p is not None and B.clean(p) and B.tactic_line(p) and re.fullmatch(
                    r"(?:" + WRAP + r"[ \t]+)*" + WRAP, B.lines[p].strip()) and re.search(r"any_goals|all_goals", B.lines[p]):
                site["outer"] = p
        bul = site["bul"]; ind = site["ind"] + " " * len(bul); cands = []   # a bullet's tactic: its content column
        own = any(w in ("any_goals", "all_goals") for w in site["wr"])
        old_tok = count_tokens(_join(B.lines[site["a"]:site["b"]]))
        pind = " " * B.ind(site["outer"]) if site["outer"] is not None else ""
        for n, (seq, block, lab) in enumerate(_schedules(site)):
            new = _wrap(ind, site["wr"], seq)
            if bul:
                new[0] = site["ind"] + bul + new[0][len(ind):]
            if block and own:   # after the site's own all_goals / any_goals: the closers follow at the site's indent
                new, extra = new + [ind + x for x in block], []
            else:               # after the enclosing wrapper-only block line's whole block, at that line's indent (or nothing)
                extra = [pind + x for x in block] if block else []
            tok = B.tokens - old_tok + tk(new) + (tk(block) if block and not own else 0)
            cands.append((tok, n, lab, new, extra))
        cands.sort(key=lambda x: (x[0], x[1]))
        uniq, texts = [], set()
        for c in cands:   # two grid points can give one text (the cap counts distinct schedules); the rest of the body is fixed per site
            t = (_join(c[3]), _join(c[4]))
            if t not in texts:
                texts.add(t); uniq.append(c)
            if len(uniq) >= SITE_CAP:
                break
        for rank, (tok, n, lab, new, extra) in enumerate(uniq):
            out.append(("t2:loop", lab[:60], _loop_builder(B, site, new, extra), li, (tok, rank)))
    return out


def _loop_builder(B: _Body, site: dict, new: list[str], extra: list[str]):
    def build() -> list[str]:
        if extra:
            pe = B.extent(site["outer"])
            lines = _replace(B.lines, pe, pe, extra)
            return _replace(lines, site["a"], site["b"], new)
        return _replace(B.lines, site["a"], site["b"], new)
    return build


# ---- t2:chain (R2) -------------------------------------------------------------------------------------------------------------------
def _outer(B: _Body, li: int):
    """A parent line of li that is only wrappers with an any_goals / all_goals among them (the enclosing block), else None."""
    p = B.parent(li)
    if p is not None and B.clean(p) and B.tactic_line(p) and re.fullmatch(
            r"(?:" + WRAP + r"[ \t]+)*" + WRAP, B.lines[p].strip()) and re.search(r"any_goals|all_goals", B.lines[p]):
        return p
    return None


def _chain_site(B: _Body, li: int) -> dict | None:
    """The last depth-0 arm of a one-line `T <;> ... <;> A` tactic line: {a, b, lead, cont, head (the line without the arm), kind
    (try | first | plain), s (try / plain), alts (first)}; None when the line is no such chain."""
    if li in B._chain:
        return B._chain[li]
    B._chain[li] = site = _chain_site0(B, li)
    return site


def _logical_end(B: _Body, li: int) -> int:
    """Index after the tactic that starts at line li: its continuation lines (deeper) and the lines that continue it with a leading
    `<;>` at its own indent or deeper (each with their continuation lines)."""
    b = _ext(B, li)
    while True:
        j = b
        while j < len(B.lines) and B.blank(j):
            j += 1
        if j >= len(B.lines) or B.ind(j) < B.ind(li) or not B.code(j).lstrip().startswith("<;>"):
            return b
        b = B.extent(j)


def _chain_site0(B: _Body, li: int) -> dict | None:
    if not B.tactic_line(li):
        return None
    b = _logical_end(B, li)
    if not any("<;>" in B.lines[j] for j in range(li, b)) or not all(B.clean(j) for j in range(li, b)):
        return None
    ln = _join([x.rstrip() for x in B.lines[li:b]])
    lead = LEAD_RE.match(ln).group(0); text = ln[len(lead):]
    marks = _scan0(text)
    seps = [q for q, k in (marks or []) if k == "<;>"]
    if not seps:
        return None
    # the arm: an unwrapped `try` after a depth-0 `<;>` takes the rest of the line (its tactic sequence); else a parenthesized `(try S)`
    # arm with arms after it (hoisted with them: the later arms go under all_goals); else the last arm
    cut, rest = seps[-1], None
    tfirst = [q for q in seps if TRYARM_RE.match(text[q + 3:].lstrip())]
    if tfirst:
        cut = tfirst[0]
    else:
        for i in range(len(seps) - 2, -1, -1):
            mid = text[seps[i] + 3:seps[i + 1]].strip()
            if _wrapped(mid) and TRYARM_RE.match(mid[1:-1].strip()):
                cut, rest = seps[i], text[seps[i + 1] + 3:].strip()
                break
    if any(q < cut and k in CHAIN_BAD for q, k in marks):
        return None
    head = text[:cut].rstrip()
    arm = (text[cut + 3:seps[seps.index(cut) + 1]] if rest is not None else text[cut + 3:]).strip()
    lw = LEADWRAP_RE.match(head)
    if not head or not arm or (lw and lw.group(0) not in ("any_goals", "all_goals")) or rest == "":
        return None
    inner = arm[1:-1].strip() if _wrapped(arm) else arm
    site = {"a": li, "b": b, "lead": lead, "cont": " " * len(lead), "head": lead + head, "s": None, "alts": None, "rest": rest}
    mt, mf = TRYARM_RE.match(inner), FIRSTARM_RE.match(inner)
    if mt:
        site.update(kind="try", s=mt.group("s").strip())
    elif mf:
        alts = _split_alts(mf.group("bars"))
        if not alts:
            return None
        site.update(kind="first", alts=alts)
    else:
        if role(arm) == "body":
            return None
        site.update(kind="plain", s=arm)
    return site


def _chain_schedules(site: dict, outer: bool) -> list[tuple]:
    """(lines after the site's line, lines after the enclosing block, label) per schedule, in the fixed grid order."""
    places = ("after",) + (("block",) if outer else ())
    out = []
    if site["kind"] == "plain":
        return [([site["s"]], [], f"arm {site['s'][:20]}: next line")]
    if site["kind"] == "try":
        if site.get("rest") is not None:   # a middle `(try S)` arm: S, then the later arms on every goal
            return [(["any_goals " + site["s"], "all_goals " + site["rest"]], [], f"try {site['s'][:20]}:after/any + rest/all")]
        for pl in places:
            line = "any_goals " + site["s"]
            out.append(([line], [], f"try {site['s'][:20]}:{pl}/any") if pl == "after" else ([], [line], f"try {site['s'][:20]}:{pl}/any"))
        return out
    alts = site["alts"]; roles = [role(x) for x in alts]
    either = [i for i, r in enumerate(roles) if r == "either"]
    if len(either) <= MAX_EITHER:
        assigns = [dict(zip(either, bits)) for bits in itertools.product((False, True), repeat=len(either))]
    else:
        assigns = [{i: False for i in either}, {i: True for i in either}]
    for asg in assigns:
        closers = [x for i, x in enumerate(alts) if roles[i] == "closer" or (roles[i] == "either" and asg[i])]
        body = [x for i, x in enumerate(alts) if roles[i] == "body" or (roles[i] == "either" and not asg[i])]
        if not closers:
            continue
        arm = "" if not body else (body[0] if len(body) == 1 else "first | " + " | ".join(body))
        units = [c for c in closers]
        unit_sets = [("each", units)] if len(closers) <= 3 else [("uniform", units)]
        if len(closers) >= 2:
            unit_sets.append(("group", ["first | " + " | ".join(closers)]))
        for kind, us in unit_sets:
            if kind == "uniform":
                grids = [tuple([pc] * len(us)) for pc in itertools.product(places, ("any_goals", "all_goals"))]
            else:
                grids = list(itertools.product(itertools.product(places, ("any_goals", "all_goals")), repeat=len(us)))
            for grid in grids:
                after = [f"{cb} {u}" for u, (pl, cb) in zip(us, grid) if pl == "after"]
                block = [f"{cb} {u}" for u, (pl, cb) in zip(us, grid) if pl == "block"]
                lab = (f"<;> {arm[:12]}; " if arm else "") + ", ".join(f"{u[:12]}:{pl}/{cb[:3]}" for u, (pl, cb) in zip(us, grid))
                out.append((after, block, lab, arm))
    return out


def _chains(B: _Body) -> list[tuple]:
    """(op, note, build, li, key) per kept chain schedule (at most SITE_CAP per site, fewest tokens first)."""
    out = []
    for li in range(len(B.lines)):
        site = _chain_site(B, li)
        if not site:
            continue
        op_ = _outer(B, li) if not site["lead"].strip() else None
        pind = " " * B.ind(op_) if op_ is not None else ""
        old_tok = count_tokens(_join(B.lines[site["a"]:site["b"]]))
        cands = []
        for n, sch in enumerate(_chain_schedules(site, op_ is not None)):
            after, block, lab = sch[:3]
            line = site["head"] + (" <;> " + sch[3] if len(sch) > 3 and sch[3] else "")
            new = [line] + [site["cont"] + x for x in after]
            extra = [pind + x for x in block]
            tok = B.tokens - old_tok + count_tokens(_join(new)) + (count_tokens(_join(extra)) if extra else 0)
            cands.append((tok, n, lab, new, extra))
        cands.sort(key=lambda x: (x[0], x[1]))
        uniq, texts = [], set()
        for c in cands:
            t = (_join(c[3]), _join(c[4]))
            if t not in texts:
                texts.add(t); uniq.append(c)
            if len(uniq) >= SITE_CAP:
                break
        for rank, (tok, n, lab, new, extra) in enumerate(uniq):
            out.append(("t2:chain", lab[:60], _loop_builder(B, {"a": site["a"], "b": site["b"], "outer": op_}, new, extra), li, (tok, rank)))
    return out


# ---- t2:altdrop, t2:altorder ----------------------------------------------------------------------------------------------------------
def _first_sites(B: _Body) -> list[tuple]:
    """(line, render(alts) -> new line, alts) for every one-line `first | ...`: led by wrappers (R1) or the arm of a `<;>` chain (R2)."""
    out = []
    for li in range(len(B.lines)):
        m = FIRST_LINE_RE.match(B.lines[li].rstrip())
        if m and B.clean(li) and B.tactic_line(li) and B.extent(li) == li + 1 and _logical_end(B, li) == li + 1:
            bars, close = m.group("bars"), ""
            if m.group("paren"):
                if not bars.endswith(")"):
                    continue
                bars, close = bars[:-1], ")"
            alts = _split_alts(bars)
            if not alts:
                continue
            lead = m.group("lead")

            def render(keep, lead=lead, close=close):
                if len(keep) == 1:
                    return lead + ("(" + keep[0] + ")" if close else keep[0])
                return lead + ("(" if close else "") + "first | " + " | ".join(keep) + close
            out.append((li, li + 1, render, alts))
            continue
        site = _chain_site(B, li)
        if site and site["kind"] == "first":
            def render(keep, head=site["head"]):
                return head + " <;> " + (keep[0] if len(keep) == 1 else "first | " + " | ".join(keep))
            out.append((li, site["b"], render, site["alts"]))
    return out


def _altdrop(B: _Body, sites: list) -> list[tuple]:
    """One alternative of a one-line `first | ...` dropped (a lone survivor replaces the `first`)."""
    out = []
    for li, b, render, alts in sites:
        for i in range(len(alts)):
            out.append(("t2:altdrop", f"drop {alts[i][:40]}", _replace(B.lines, li, b, [render(alts[:i] + alts[i + 1:])]), li))
    return out


def _altorder(B: _Body, sites: list) -> list[tuple]:
    """R2: one alternative of a one-line `first | ...` moved to the front (token-neutral)."""
    out = []
    for li, b, render, alts in sites:
        for i in range(1, len(alts)):
            if alts[i] == alts[0]:
                continue
            out.append(("t2:altorder", f"front {alts[i][:40]}", _replace(B.lines, li, b, [render([alts[i]] + alts[:i] + alts[i + 1:])]),
                        li))
    return out


# ---- t2:try2pos ---------------------------------------------------------------------------------------------------------------------
def _goal_counts(ctx: dict | None, head_lines: int) -> dict:
    """{body line index: goals before it} from ctx["goals"] (declaration lines, 1-based)."""
    out = {}
    for g in (ctx or {}).get("goals") or []:
        try:
            out[int(g["line"]) - 1 - head_lines] = int(g["n_goals"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _try_site(B: _Body, li: int) -> dict | None:
    """A positional site at line li: {a, b (lines replaced), keep (their replacement), tl (the tactic lines to insert, indented), ind,
    label, mode (pos: in place or after an earlier sibling, rotations; inplace: k = 0 in place only; after: right after the line)}."""
    ln = B.lines[li]
    if not B.clean(li) or not B.tactic_line(li):
        return None
    ind = ln[:B.ind(li)]
    if _logical_end(B, li) != B.extent(li):   # a `<;>` line continues it: the chain's own site (below) or none
        site = _chain_site(B, li)
        if not (site and site["kind"] == "try"):
            return None
    m = TRY_RE.match(ln)
    if m:
        b = B.extent(li)
        if not all(B.clean(j) for j in range(li, b)):
            return None
        t = m.group("t")
        if m.group("p"):   # `all_goals (try T)`
            if not t.endswith(")") or b != li + 1:
                return None
            t = t[:-1].rstrip()
        if not t:
            return None
        return {"a": li, "b": b, "keep": [], "tl": [ind + t] + B.lines[li + 1:b], "ind": ind, "label": t, "mode": "pos"}
    mb = BLOCK_HEAD_RE.fullmatch(ln.strip())
    if mb:   # R2: a multi-line block
        b = B.extent(li)
        if b == li + 1 or not all(B.clean(j) for j in range(li, b)):
            return None
        blk, mode = B.lines[li + 1:b], "pos"
        if mb.group("w") == "all_goals":
            col = min(B.ind(x) for x in range(li + 1, b) if not B.blank(x))
            tops = [j for j in range(li + 1, b) if not B.blank(j) and B.ind(j) == col]
            tm = TRY_RE.match(B.lines[tops[0]]) if len(tops) == 1 else None
            if len(tops) == 1 and tm and not tm.group("all") and not tm.group("any") and B.extent(tops[0]) == b:
                blk = [B.lines[tops[0]].strip()[3:].strip()] + B.lines[tops[0] + 1:b]          # `all_goals` + `try T`
                tl = [ind + blk[0]] + blk[1:]
                return {"a": li, "b": b, "keep": [], "tl": tl, "ind": ind, "label": blk[0], "mode": "pos"}
            if len(tops) == 1 and B.lines[tops[0]].strip() == "try" and B.extent(tops[0]) == b and b > tops[0] + 1:
                blk = B.lines[tops[0] + 1:b]                                                 # `all_goals` + `try` + a block
            else:
                mode = "inplace"
        tl = [ind + x if x.strip() else x for x in _dedent(blk)]
        return {"a": li, "b": b, "keep": [], "tl": tl, "ind": ind, "label": tl[0].strip() + (" ..." if len(tl) > 1 else ""), "mode": mode}
    site = _chain_site(B, li)
    if site and site["kind"] == "try":   # R2: hoisted out of the chain, right after its line
        tl = [site["cont"] + site["s"]] + ([site["cont"] + "all_goals " + site["rest"]] if site.get("rest") is not None else [])
        return {"a": li, "b": site["b"], "keep": [site["head"]], "tl": tl, "ind": site["cont"], "label": site["s"], "mode": "after"}
    return None


def _try2pos(B: _Body, counts: dict, max_per_op: int = MAX_PER_OP) -> list[tuple]:
    """(op, note, build, li, key) per kept (insertion point, rotation) of each try site. Inside one site the key (tokens, dist + k, dist, k)
    orders a fixed rotation k by distance and the token count depends on k alone, so only the first `cap` points that admit k can be
    emitted; per site the `cap` smallest keys are kept (cap = 2 * max_per_op + 2: room for duplicates and the in-place original).
    Generation is linear in the number of try sites times cap, whatever the block length."""
    out = []
    cap = 2 * max(1, max_per_op) + 2
    for li in range(len(B.lines)):
        site = _try_site(B, li)
        if not site:
            continue
        a, b, ind = site["a"], site["b"], site["ind"]
        old_tok = count_tokens(_join(B.lines[a:b])) - (count_tokens(_join(site["keep"])) if site["keep"] else 0)
        ins_tok = [count_tokens(_join(_ins(ind, site["tl"], k))) for k in range(MAX_ROT + 1)]
        if site["mode"] == "after":
            points = [b]
            kmax_of = lambda pos: MAX_ROT  # noqa: E731   (the goals the chain's head leaves are not in ctx)
        else:
            kmax_of = lambda pos: MAX_ROT if counts.get(pos) is None else max(0, min(counts[pos] - 1, MAX_ROT))  # noqa: E731
            if site["mode"] == "inplace":
                kmax_of = lambda pos: 0  # noqa: E731
            # insertion points: in place, then after each earlier sibling (its whole extent), nearest first; dist = rank of the point.
            # Scanning stops once `cap` points admit every rotation (the farther ones cannot be emitted).
            points, pset = [a], {a}
            full = kmax_of(a) == MAX_ROT
            for sib in (B.siblings_before(li) if site["mode"] == "pos" else ()):
                if full >= cap:
                    break
                pe = B.extent(sib)
                last = pe - 1
                while last > sib and B.blank(last):
                    last -= 1
                if B.code(last).rstrip().endswith(CONT_END):
                    break
                if pe not in pset:
                    points.append(pe); pset.add(pe); full += kmax_of(pe) == MAX_ROT
        keys = []
        for k in range(MAX_ROT + 1):
            got = 0
            for dist, pos in enumerate(points):
                if got >= cap:
                    break
                if k <= kmax_of(pos):
                    keys.append((B.tokens - old_tok + ins_tok[k], dist + k, dist, k, pos)); got += 1
        keys.sort()
        for tok, dk, dist, k, pos in keys[:cap]:
            out.append(("t2:try2pos", f"{site['label'][:30]} -> L{pos - li:+d} rot {k}", _try_builder(B, site, pos, _ins(ind, site["tl"], k)),
                        li, (tok, dk, dist, k)))
    return out


def _ins(ind: str, tl: list[str], k: int) -> list[str]:
    return ([ind + ("rotate_left" if k == 1 else f"rotate_left {k}")] if k else []) + list(tl)


def _try_builder(B: _Body, site: dict, pos: int, ins: list[str]):
    a, b, keep = site["a"], site["b"], site["keep"]
    if pos >= b:   # right after the site's own (kept) line
        return lambda: B.lines[:a] + keep + ins + B.lines[b:]
    return lambda: B.lines[:pos] + ins + B.lines[pos:a] + keep + B.lines[b:]


# ---- the public entry -----------------------------------------------------------------------------------------------------------------
def _normalize(body: str) -> str:
    """A one-line `by tac` proof as `by` + an indented line (same tokens), so the line-based sites see its tactic."""
    if "\n" in body.strip():
        return body
    m = re.match(r"([ \t]*)by[ \t]+(\S.*)$", body)
    if not m:
        return body
    return m.group(1) + "by\n" + IND + m.group(2).rstrip()


def candidates(proof: str, statement: str, *, exchange: float | None = None, max_per_op: int = MAX_PER_OP,
               ctx: dict | None = None) -> list[dict]:
    """[{"op", "decl", "note"}]: every T2 candidate of the declaration, OPS order, fewest tokens first inside each op."""
    body = split_declaration(proof, statement)
    if body is None:
        return []
    head = proof[:len(proof) - len(body)]
    nbody = _normalize(body)
    B = _Body(nbody)
    if B.fb < 0:
        return []
    counts = _goal_counts(ctx, head.count("\n")) if nbody == body else {}
    # every finder gives (op, note, lines or build(), line, [key]); a full body is joined only while emitting (at most max_per_op kept per op)
    fsites = _first_sites(B)
    raw = (_intros(B) + _intromerge(B) + _introdestr(B) + _funintro(B) + _altdrop(B, fsites) + _chains(B) + _loops(B)
           + _try2pos(B, counts, max_per_op) + _altorder(B, fsites))
    newline0 = bool(re.match(r"[ \t]*\n", body))
    by_op: dict = {}
    for item in raw:
        op, note, lines, li = item[:4]
        key = item[4] if len(item) > 4 else None
        if key is None:
            key = (count_tokens(_join(lines)), 0)
        by_op.setdefault(op, []).append((key, li, note, lines))
    out, seen = [], {proof, proof.rstrip(), head + nbody, (head + nbody).rstrip()}
    for op in OPS:
        n = 0
        for key, li, note, lines in sorted(by_op.get(op, ()), key=lambda x: (x[0][0],) + tuple(x[0][1:]) + (x[1],)):
            if n >= max_per_op:
                break
            nb = _join(lines() if callable(lines) else lines)
            decl = head + nb
            if decl in seen or decl.rstrip() in seen:
                continue
            if not newline0 and re.match(r"[ \t]*\n", nb):
                continue
            if split_declaration(decl, statement) != nb:
                continue
            seen.add(decl); seen.add(decl.rstrip()); n += 1
            out.append({"op": op, "decl": decl, "note": f"{note} @L{head.count(chr(10)) + li + 1}"})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="T2 schedule candidates of one declaration (no compile)")
    ap.add_argument("--file", required=True, help="the declaration (statement := body)")
    ap.add_argument("--statement-file", required=True, help="the exact statement text")
    ap.add_argument("--max-per-op", type=int, default=MAX_PER_OP)
    a = ap.parse_args(argv)
    proof = Path(a.file).read_text(); stmt = Path(a.statement_file).read_text().rstrip("\n")
    t0 = count_tokens(split_declaration(proof, stmt) or "")
    for d in candidates(proof, stmt, max_per_op=a.max_per_op):
        print(json.dumps({"op": d["op"], "note": d["note"], "dtok": count_tokens(split_declaration(d["decl"], stmt)) - t0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
