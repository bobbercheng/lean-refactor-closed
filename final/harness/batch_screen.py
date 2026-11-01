#!/usr/bin/env python3
"""Batch screening for the end stage's tool families (docs/tools_build_plan.md, round R2).

Why: every candidate the end stage reads is one Lean process, so the imports are loaded again for each; the R1 replay compiled 0.3% of t3's
and 4% of t1's candidates, and those failing compiles spent the row's wall budget. A screen compiles up to K candidates in ONE process and
lets only the copies that compile go on to the paired measurement (harness/endstage.attempt: paired decide, confirmation compile). The
screen never banks anything: a pass only means "measure it"; a fail is a compile error inside that candidate's own copy.

  file      the row's file on the primary pin, laid out as the meter's unmeasured compile lays it out (scorer/compile.py, hb_tool_eval
            Evaluator._compile): PutnamBench: header + blank line + copies; project rows: the file prefix before the declaration + blank
            line + copies, where the prefix's trailing `… in` combinator lines (`set_option … in`, `omit … in`, ...) are taken off the
            prefix and repeated before every copy when the meter's validity compile attaches them to the declaration (a core ending in a
            validity-relevant combinator, scorer.compile._ATTACHED_IN), otherwise dropped (the measured compile attaches them to its own
            command, not to the declaration); the declaration's own modifiers (docstring, visibility, `open … in`) are repeated before
            every copy, its attribute lists are not (below).
  copy k    [prefix `… in` lines] + `set_option maxHeartbeats N in` (when a bound is known, below) + `set_option Elab.async false in` (the
            measured compile's mode) + modifiers + the candidate with every name its statement declares renamed `<name>_lra_scr<k>`
            (every whole-identifier occurrence in the copy: the statement head, and self-references such as a recursive call or a
            PutnamBench `…_solution` used by the theorem; a dotted name's last component too), then `#print "LRA_SCREEN k"`.
  attrs     (R2 review 2026-10-22) copies share one environment, so a copy's attributes would act on the copies after it: `@[simp]` on
            copy 0 rewrote copy 1's goal away (`by simp; rfl` passed alone and failed in the batch), `@[to_additive n]` would declare n
            twice, a named `instance` would put K instances in scope. The attribute lists of the declaration the candidate proves (the
            modifiers' and the statement's, blanked: lines kept) are therefore dropped from every copy: Lean applies them after the body
            elaborates, so dropping them can turn a fail into a pass (one measurement more), never a pass into a fail. Not screenable
            (measured as before): a statement that declares a named instance, an attribute on an EARLIER declaration of the statement
            (dropping it could change the candidate's elaboration, keeping it leaks), an attribute list inside the proof.
  verdict   per copy, from Lean's JSON messages by line range: the copy starts clean when the previous marker printed (the parser was at a
            command boundary); an error (or a sorry warning) inside the copy's lines -> fail (a `maxHeartbeats` error -> fail "hb_bound");
            no error and its own marker printed -> pass; anything else -> unknown. An error in the shared prefix makes the whole batch
            inconclusive (environment), every copy unknown. Unknown copies go to the measurement as they did before screening.
  bound     N = 2 * h + 1000, where h is the heartbeat count above which a candidate cannot beat the incumbent even with zero tokens and
            every pin (score = mean(L, H, Z), each linear and unbounded below; h solves (L(0) + H(h) + 100) / 3 = the incumbent's score).
            Lean's maxHeartbeats and the meter's ARENA_HB are both in thousands of heartbeats; the factor 2 and the 1000 are margin. The
            bound only falls as the incumbent improves, so a cached "hb_bound" fail stays valid for the row.
  size      at most K copies, and at most TARGET_S / (the incumbent's primary-pin compile time) - 2 (the control's two copies; at least
            2): that time includes the imports, so it bounds one copy's elaboration from above and a batch of ordinary candidates fits
            in TARGET_S (600 s), under the meter's 900 s timeout, on slow rows too.
  timeouts  a batch's wall timeout is the incumbent's primary-pin compile time plus, per copy (the control's two included), that time (or the
            candidate's own timeout_s when smaller) plus 30 s, capped by the meter's timeout. A batch that times out, crashes (a non-zero exit without an
            error message) or leaves copies unknown is split in halves, at most `max_depth` times (default 2: 24 -> 12 -> 6); what is
            still unknown at the bottom is left to the measurement (a single candidate that timed out under at least its own timeout_s
            is a "timeout" fail, as its measurement would be).
  control   the incumbent (which compiles: it was measured) goes into every batch as copy 0; if its copy fails or its marker does not
            print in a file that finished, the layout does not hold on this row (an option, the marker or the prefix handling): the batch
            is inconclusive and the screener stops screening the row (every later candidate goes to the measurement unscreened), so a
            broken layout can never reject candidates. It also goes in as the LAST copy (R2 review): when copy 0 passed and the last
            copy fails, an earlier copy changed what later copies see (a leak the attrs rule does not know); the batch's fail verdicts
            become unknown (split, then measured), its passes stand (a pass is only "measure it"), stats["leaks"] counts it.
  cache     verdicts by candidate hash (endstage.sha) for the row; `cache` may be shared across calls.

Nothing here is mined from any proof: the marker, suffix and layout are fixed strings; the bound is computed from the row's own numbers.
The compile goes through the meter's own path (direct: hb_tool_eval.Evaluator._run with its slot gate, memory gate and timeout; lake:
scorer.compile) on the primary pin; one batch is one physical compile.
"""
from __future__ import annotations

import hashlib, math, re, time
from dataclasses import dataclass, field

SCREEN_K = 24          # candidates per batch
MAX_DEPTH = 2          # halvings of a batch that timed out / crashed / left copies unknown
TARGET_S = 600         # a batch's expected wall time at most (sizes the batch on slow rows)
SUFFIX = "_lra_scr"
MARK = "LRA_SCREEN"
_MARK_RE = re.compile(r"^" + MARK + r" (\d+)$")

_DECL_KW = re.compile(r"(?:^|(?<=[\s\]]))(theorem|lemma|def|abbrev|instance|example)\b")
_DECL_NAME = re.compile(r"\s+((?:«[^»]*»|[^\s(){}\[\]⦃:,«])+)")
_INST_PRIO = re.compile(r"\s*\(\s*priority\s*:=[^)]*\)")
_ID_BEFORE = r"(?<![\w'!?.])"      # not inside an identifier, not after a dot (a field or a qualified suffix)
_ID_AFTER = r"(?![\w'!?])"
_IN_LINE = re.compile(r"[ \t]*(?:omit|include|unseal|variable|set_option|open)\b[^\n]*\bin[ \t]*$")


def sha(text: str) -> str:
    """The end stage's candidate hash (harness/endstage.sha)."""
    return hashlib.sha256(text.strip().encode()).hexdigest()[:16]


# ------------------------------------------------------------------------------------------------------------------------------ text
def mask(text: str, attrs: list | None = None) -> str:
    """`text` with comments (`--` lines, nested `/- -/` blocks, docstrings), string literals and `@[...]` attribute lists replaced by
    spaces, newlines kept: every position still points at the same character of `text`. attrs: a list that gets each attribute list's
    (start, end)."""
    out, i, n = list(text), 0, len(text)

    def blank(a, b):
        for j in range(a, b):
            if out[j] != "\n":
                out[j] = " "
    while i < n:
        c = text[i]
        if text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            blank(i, j); i = j
        elif text.startswith("/-", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith("/-", j):
                    depth += 1; j += 2
                elif text.startswith("-/", j):
                    depth -= 1; j += 2
                else:
                    j += 1
            blank(i, j); i = j
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            j = min(n, j + 1)
            blank(i, j); i = j
        elif text.startswith("@[", i):
            depth, j = 0, i + 1
            while j < n:
                depth += {"[": 1, "]": -1}.get(text[j], 0)
                j += 1
                if depth == 0:
                    break
            blank(i, j)
            if attrs is not None:
                attrs.append((i, j))
            i = j
        else:
            i += 1
    return "".join(out)


def declared(statement: str) -> list[tuple[str, str | None, int]]:
    """(keyword, name as written or None, position of the name) for each declaration keyword of `statement` (comments, strings and
    attributes ignored; `foo.{u}` gives `foo`), in order; scorer.compile._declared with positions."""
    s, out = mask(statement), []
    for k in _DECL_KW.finditer(s):
        kw, pos = k.group(1), k.end()
        if kw == "example":
            out.append((kw, None, pos)); continue
        if kw == "instance":
            pm = _INST_PRIO.match(s, pos)
            pos = pm.end() if pm else pos
        m = _DECL_NAME.match(s, pos)
        name = (m.group(1).rstrip(".") or None) if m else None
        out.append((kw, name, m.start(1) if m else pos))
    return out


def attr_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of every `@[...]` attribute list of `text` outside comments and strings."""
    spans: list = []
    mask(text, spans)
    return spans


def drop_attrs(text: str, spans=None) -> str:
    """`text` with the given attribute lists (default: all of them) blanked to spaces, newlines kept; a line left blank is emptied."""
    spans = attr_spans(text) if spans is None else spans
    if not spans:
        return text
    out = list(text)
    for a, b in spans:
        for j in range(a, b):
            if out[j] != "\n":
                out[j] = " "
    lines = "".join(out).split("\n")
    touched = {k for a, b in spans for k in range(text.count("\n", 0, a), text.count("\n", 0, b) + 1)}
    return "\n".join("" if i in touched and not l.strip() else l for i, l in enumerate(lines))


def screen_statement(statement: str) -> tuple[str | None, str | None]:
    """(the statement as every copy writes it, why not screenable): the attribute lists of its LAST declaration (the one the
    candidate proves) blanked (module docstring, "attrs"); (None, why) when it declares a named instance or an attribute list attaches
    to an earlier declaration."""
    m = mask(statement)
    kws = [k.start(1) for k in _DECL_KW.finditer(m)]
    if any(kw == "instance" and n is not None for kw, n, _ in declared(statement)):
        return None, "the statement declares an instance (every copy's instance would be in scope for the copies after it)"
    spans = attr_spans(statement)
    if not spans:
        return statement, None
    last = kws[-1] if kws else len(statement)
    prev = kws[-2] if len(kws) > 1 else -1   # an attribute list attaches to the first declaration keyword after it
    if any(b <= prev for _, b in spans):
        return None, "an attribute on an earlier declaration of the statement (dropping it could change the candidate, keeping it leaks)"
    return drop_attrs(statement, [(a, b) for a, b in spans if b <= last]), None


def _suffixed(name: str, suffix: str) -> str:
    return name[:-1] + suffix + "»" if name.endswith("»") else name + suffix


def rename_copy(decl: str, statement: str, suffix: str) -> str | None:
    """`decl` (which starts with `statement`) with every name the statement declares renamed `<name><suffix>`: each whole-identifier
    occurrence of the name as written (and of a dotted name's last component, when it has 3 or more characters) outside comments and
    strings, so the head, a recursive call and a theorem's use of a declared `…_solution` stay consistent. `open … in` / `set_option … in`
    prefixes are untouched. None: the statement declares an anonymous instance (its generated name would clash between copies) or no
    declared name could be found at its head."""
    if not decl.startswith(statement):
        return None
    decls = declared(statement)
    if any(kw != "example" and n is None for kw, n, _ in decls):
        return None
    names = [n for kw, n, _ in decls if n]
    if not names:
        return decl                     # examples only: nothing to rename
    pats = []
    for n in dict.fromkeys(names):
        pats.append(n)
        last = n.rsplit(".", 1)[-1] if "." in n and not n.startswith("«") else None
        if last and len(last) >= 3 and last not in names:
            pats.append(last)
    m = mask(decl)
    hits = []
    for p in sorted(dict.fromkeys(pats), key=len, reverse=True):   # longest first: `A.b` before `b`
        for h in re.finditer(_ID_BEFORE + re.escape(p) + _ID_AFTER, m):
            if not any(a < h.end() and h.start() < b for a, b, _ in hits):
                hits.append((h.start(), h.end(), p))
    heads = {pos for kw, n, pos in decls if n}
    if not heads <= {a for a, _, _ in hits}:
        return None
    out = decl
    for a, b, p in sorted(hits, reverse=True):
        out = out[:a] + _suffixed(decl[a:b], suffix) + out[b:]
    return out


def strip_in_tail(core: str) -> tuple[str, list[str]]:
    """(core without its trailing `… in` combinator lines, those lines in order); comment-only and blank lines between them go too."""
    lines, tail = core.split("\n"), []
    ml = mask(core).split("\n")
    i = len(lines)
    while i > 0:
        t = ml[i - 1]
        if not t.strip():
            i -= 1
            continue
        if _IN_LINE.match(t):
            tail.insert(0, lines[i - 1].rstrip())
            i -= 1
            continue
        break
    if not tail:
        return core, []
    return "\n".join(lines[:i]) + "\n", tail


def hb_bound(metrics, reading: dict | None) -> int | None:
    """The `maxHeartbeats` value of the screen (module docstring, "bound"), from the meter's metrics(tokens, heartbeats, Z) -> {L, H,
    score_exact} and the incumbent's reading; None when the meter gives H no slope (no reference heartbeats) or the reading is missing."""
    try:
        target = 3.0 * float(reading["score_exact"])
        m0, m1 = metrics(0, 0, 100.0), metrics(0, 10 ** 6, 100.0)
        slope = (float(m0["H"]) - float(m1["H"])) / 10 ** 6       # points of H lost per heartbeat (thousands)
        if not slope > 0 or not math.isfinite(slope):
            return None
        L0 = float(m0["L"])
        h = (float(m0["H"]) - (target - L0 - 100.0)) / slope
        h = max(h, float(reading.get("heartbeats") or 0))
        return int(math.ceil(2 * h)) + 1000 if math.isfinite(h) else None
    except (TypeError, KeyError, ValueError, ZeroDivisionError):
        return None


# ---------------------------------------------------------------------------------------------------------------------------- layout
@dataclass
class Layout:
    """The shared part of a batch file on one pin: `head` (header or file prefix + blank line), the `… in` lines repeated before every copy,
    the declaration's modifiers, the lean arguments and the sorry-warning setting of the meter's unmeasured compile."""
    version: str
    head: str
    in_lines: list = field(default_factory=list)
    modifiers: str = ""
    lean_args: tuple = ()
    quiet: bool = False

    @property
    def first_line(self) -> int:
        return self.head.count("\n") + 1


def layout(row: dict, version: str) -> Layout:
    """The batch layout of `row` on `version` (raises when the project file or environment is missing)."""
    from scorer import compile as C
    if row["source"] == "putnambench":
        return Layout(version, row["header"].rstrip() + "\n\n")
    core, modifiers = C.split_modifiers(C.file_prefix(row, version))
    attach = bool(C._ATTACHED_IN.search(core))
    core2, tail = strip_in_tail(core)
    lean_args, quiet = C.lakefile_options(row["source"], version), False
    if C.force_warn_sorry() and C._warn_sorry_off(lean_args):
        lean_args, quiet = C._with_warn_sorry(lean_args), True
    return Layout(version, core2.rstrip("\n") + "\n\n", tail if attach else [], modifiers, tuple(lean_args), quiet)


def block(renamed: str, L: Layout, idx: int, hb_cap: int | None) -> tuple[str, int]:
    """(copy idx's text, the 0-based line of its marker within it); the modifiers' attribute lists are dropped (module docstring,
    "attrs")."""
    pre = "".join(l + "\n" for l in L.in_lines)
    if hb_cap:
        pre += f"set_option maxHeartbeats {int(hb_cap)} in\n"
    pre += "set_option Elab.async false in\n"
    text = pre + drop_attrs(L.modifiers) + renamed.rstrip() + "\n\n"
    return text + f'#print "{MARK} {idx}"\n\n', text.count("\n")


def build(texts: list[str], statement: str, L: Layout, hb_cap: int | None):
    """(body, copies, spans): the batch file, its copies part, and per text (first line, marker line), 1-based file lines; a text that
    cannot be renamed (or whose statement keeps an attribute that would leak, screen_statement) gets None (it is not in the file)."""
    blocks, spans = [], []
    line = L.first_line
    st2, _ = screen_statement(statement)
    for i, t in enumerate(texts):
        t = t.strip()
        r = None
        if st2 is not None and t.startswith(statement):
            r = rename_copy(st2 + t[len(statement):], st2, f"{SUFFIX}{i}")
        if r is None:
            spans.append(None)
            continue
        b, mk = block(r, L, i, hb_cap)
        spans.append((line, line + mk))
        line += b.count("\n")
        blocks.append(b)
    copies = "".join(blocks).rstrip() + "\n"
    return L.head + copies, copies, spans


def verdicts(res, spans: list, first_line: int) -> tuple[dict, str | None]:
    """({index: (verdict, error)}, inconclusive kind or None) from a finished batch compile (scorer.compile.CompileResult or alike:
    ok, messages, timed_out, errors). Inconclusive: "timeout", "crash" (failed without any error message), "env" (an error before the
    first copy: the shared prefix or the environment)."""
    from scorer.compile import _is_sorry_msg
    if getattr(res, "timed_out", False):
        return {}, "timeout"
    marks, bad = set(), []
    for m in getattr(res, "messages", None) or []:
        line = (m.get("pos") or {}).get("line") or 0
        data = str(m.get("data", ""))
        sev = m.get("severity")
        mm = _MARK_RE.match(data.strip())
        if sev == "information" and mm:
            marks.add(int(mm.group(1)))
            continue
        if sev == "error" or (_is_sorry_msg(m) and line >= first_line):
            bad.append((line, data, m.get("kind")))
    if any(l < first_line for l, _, _ in bad):
        e = next(d for l, d, _ in bad if l < first_line)
        return {}, "env: " + e[:200]
    if not bad and not getattr(res, "ok", False):   # failed without an error message: killed, out of memory, a crash
        return {}, "crash: " + str((getattr(res, "errors", None) or ["?"])[0])[:200]
    out, prev = {}, None
    for i, sp in enumerate(spans):
        if sp is None:
            continue
        s, mk = sp
        clean = prev is None or prev in marks
        errs = [(l, d, k) for l, d, k in bad if s <= l < mk]
        if not clean:
            out[i] = ("unknown", "the previous copy did not end at its marker")
        elif errs:
            l, d, k = errs[0]
            hb = k == "runtime.maxHeartbeats" or "maximum number of heartbeats" in d
            out[i] = ("hb_bound" if hb else "fail", f"{l - s + 1}: {d}"[:300])
        elif i in marks:
            out[i] = ("pass", None)
        else:
            out[i] = ("unknown", "its marker did not print")
        prev = i
    return out, None


# -------------------------------------------------------------------------------------------------------------------------- screener
class BatchScreener:
    """One row's screen on one pin. screen(items, need=, charge=, hb_cap=, compile_s=) -> {key: verdict dict}; verdict dict:
    {"verdict": pass | fail | hb_bound | timeout | unknown | unscreened, "error", "batch" (size), "depth", "cached"}.
    compile_fn(body, copies, layout, timeout) -> (CompileResult-like, physical compiles); `need(n)` is called before each compile (it may
    raise to stop: the end stage's budget), `charge(n)` after it."""

    def __init__(self, row: dict, compile_fn, *, version: str | None = None, timeout: int = 900, k: int = SCREEN_K,
                 max_depth: int = MAX_DEPTH, cache: dict | None = None, log=None, layout_fn=None):
        self.row, self.statement = row, row["statement"]
        self.version = version
        self.compile_fn, self.timeout = compile_fn, int(timeout)
        self.k, self.max_depth = max(1, int(k)), max(0, int(max_depth))
        self.cache = cache if cache is not None else {}
        self.log = log or (lambda m: None)
        self._layout_fn = layout_fn or layout
        self._layout = None
        self._layout_err = None
        self.stats = {"batches": 0, "compiles": 0, "seconds": 0.0, "splits": 0, "inconclusive": 0, "copies": 0, "leaks": 0}
        self.broken = None   # why screening stopped on this row (the control copy failed)
        self._stmt_why = screen_statement(self.statement)[1]   # the statement itself is not screenable (module docstring, "attrs")

    def _lay(self):
        if self._layout is None and self._layout_err is None:
            try:
                self._layout = self._layout_fn(self.row, self.version)
            except Exception as e:  # noqa: BLE001  (a missing project file: no screening on this row)
                self._layout_err = f"{type(e).__name__}: {e}"[:200]
        return self._layout

    def screenable(self, text: str) -> str | None:
        """None when `text` can go into a batch, else why not (it then goes to the measurement unscreened)."""
        from scorer.compile import SORRY_SWITCH_RE
        from scorer.forbidden import check_forbidden, strip_lean_comments
        from scorer.tokenize import split_declaration
        body = split_declaration(text, self.statement)
        if body is None:
            return "statement differs"
        if self._stmt_why:
            return self._stmt_why
        if check_forbidden(body):
            return "forbidden"
        if SORRY_SWITCH_RE.search(strip_lean_comments(body)):
            return "names a sorry-warning switch"
        if attr_spans(body):
            return "an attribute list inside the proof (it would act on the copies after it)"
        if rename_copy(text, self.statement, SUFFIX + "0") is None:
            return "the declared name cannot be renamed (anonymous instance)"
        return None

    def _modifiers_why(self, L: Layout) -> str | None:
        """The layout's modifiers attach to the statement's first declaration: their attribute lists can be dropped only when that is
        the declaration the candidate proves."""
        if attr_spans(L.modifiers) and len(declared(self.statement)) > 1:
            return "an attribute on an earlier declaration of the statement (the declaration's modifiers)"
        return None

    def batch_size(self, compile_s: float | None) -> int:
        """Candidates per batch: K, and TARGET_S / compile time less the two control copies (module docstring, "size")."""
        cs = float(compile_s) if isinstance(compile_s, (int, float)) and compile_s > 0 else 60.0
        return max(2, min(self.k, int(TARGET_S // cs) - 2))

    def batch_timeout(self, items: list[dict], compile_s: float | None, extra: int = 0) -> int:
        cs = float(compile_s) if isinstance(compile_s, (int, float)) and compile_s > 0 else 60.0
        allow = cs * extra
        for it in items:
            to = it.get("timeout_s")
            allow += min(float(to), cs) if isinstance(to, (int, float)) and to > 0 else cs
        return int(max(1, min(self.timeout, math.ceil(cs + allow) + 30)))

    def screen(self, items: list[dict], *, need=None, charge=None, hb_cap: int | None = None, compile_s: float | None = None,
               control: str | None = None) -> dict:
        """items: [{"key", "text", "timeout_s"?}] (key: the candidate hash). Verdicts are cached by key. control: a declaration that
        compiles (the incumbent), put first and last in every batch file (module docstring)."""
        out, todo = {}, []
        if control is not None and self.screenable(control) is not None:
            control = None
        for it in items:
            key = it["key"]
            if key in self.cache:
                out[key] = dict(self.cache[key], cached=True)
                continue
            why = self.screenable(it["text"]) if self.broken is None else f"screening stopped on this row: {self.broken}"
            if why is None and self._lay() is None:
                why = f"no layout: {self._layout_err}"
            if why is None:
                why = self._modifiers_why(self._layout)
            if why is not None:
                out[key] = {"verdict": "unscreened", "error": why}
                continue
            if any(t["key"] == key for t in todo):
                continue
            todo.append(it)
        kb = self.batch_size(compile_s)
        queue = [(todo[i:i + kb], 0) for i in range(0, len(todo), kb)]
        while queue:
            batch, depth = queue.pop(0)
            if self.broken is not None:
                for it in batch:
                    out[it["key"]] = {"verdict": "unscreened", "error": f"screening stopped on this row: {self.broken}"}
                continue
            if need:
                need(1)
            L = self._lay()
            off = 1 if control is not None else 0
            tail = len(batch) + 1 if off else None   # the control's trailing copy (the leak sentinel)
            texts = ([control] if off else []) + [it["text"] for it in batch] + ([control] if off else [])
            body, copies, spans = build(texts, self.statement, L, hb_cap)
            to = self.batch_timeout(batch, compile_s, extra=2 * off)
            t0 = time.time()
            res, n = self.compile_fn(body, copies, L, to)
            secs = time.time() - t0
            if charge:
                charge(int(n))
            self.stats["batches"] += 1
            self.stats["compiles"] += int(n)
            self.stats["seconds"] += secs
            self.stats["copies"] += len(batch)
            got, inc = verdicts(res, spans, L.first_line)
            if inc is None and off:
                cv, cerr = got.get(0, ("unknown", "not in the file"))
                if cv != "pass":   # the process finished, yet the incumbent's copy failed or its marker did not print: no layout here
                    self.broken = f"the incumbent's own copy is {cv} in the batch file ({str(cerr)[:160]})"
                    self.stats["broken"] = self.broken
                    inc = "env: " + self.broken
                else:
                    tv, terr = got.get(tail, ("unknown", "not in the file"))
                    if tv in ("fail", "hb_bound"):   # the incumbent passed first and failed last: an earlier copy changed later ones
                        self.stats["leaks"] += 1
                        self.log(f"screen: the incumbent's trailing copy failed ({str(terr)[:100]}); this batch's fails are unknown")
                        why = f"the incumbent's trailing copy failed in this batch ({str(terr)[:120]}): a copy may have changed later ones"
                        got = {i: (("unknown", why) if v[0] in ("fail", "hb_bound") else v) for i, v in got.items()}
                got = {i - off: v for i, v in got.items() if off <= i < tail}
            if inc is not None:
                self.stats["inconclusive"] += 1
                self.log(f"screen: batch of {len(batch)} inconclusive ({inc[:120]})")
            if inc is not None and inc.startswith("env"):
                for it in batch:
                    self._set(out, it, "unknown", inc, len(batch), depth)
                continue
            unknown = []
            for i, it in enumerate(batch):
                v, err = got.get(i, ("unknown", inc or "not in the file"))
                if v == "unknown":
                    unknown.append((it, err))
                else:
                    self._set(out, it, v, err, len(batch), depth)
            if not unknown:
                continue
            if depth < self.max_depth and (len(unknown) > 1 or len(batch) > 1):
                us = [it for it, _ in unknown]
                h = (len(us) + 1) // 2
                parts = [p for p in (us[:h], us[h:]) if p]
                self.stats["splits"] += 1
                for p in reversed(parts):
                    queue.insert(0, (p, depth + 1))
                continue
            for it, err in unknown:
                own = it.get("timeout_s")
                if inc == "timeout" and len(batch) == 1 and isinstance(own, (int, float)) and own > 0 and to >= own:
                    self._set(out, it, "timeout", f"timed out alone after {to} s (its own timeout {own:g} s)", 1, depth)
                else:
                    self._set(out, it, "unknown", err, len(batch), depth)
        return out

    def _set(self, out, it, verdict, err, size, depth):
        v = {"verdict": verdict, "error": err, "batch": size, "depth": depth}
        out[it["key"]] = v
        self.cache[it["key"]] = v


def meter_compile_fn(meter):
    """compile_fn for BatchScreener on harness/endstage.Meter's path: direct (its Evaluator: slot gate, memory gate, the given timeout) or
    lake (scorer.compile); the physical compiles are added to the meter's count."""
    def run(body: str, copies: str, L: Layout, timeout: int):
        from scorer import compile as C
        path = meter.freeze()
        row = meter.row
        ev, n0, n = None, 0, 0
        try:
            if path == "direct":
                ev = meter._evaluator(); n0 = ev.compiles
                t_ev, ev.timeout = ev.timeout, int(timeout)
                try:
                    r = ev._run(row, L.version, body, L.lean_args, L.first_line, L.quiet)
                finally:
                    ev.timeout = t_ev
                n = ev.compiles - n0
            elif row["source"] == "putnambench":
                r, n = C.compile_putnam(row["header"], copies, L.version, count=False, timeout=int(timeout)), 1
            else:
                r = C._lean_in_project(row["source"], L.version, body, L.lean_args, int(timeout), first_line=L.first_line,
                                       quiet_prefix_sorry=L.quiet)
                n = 1
        except Exception as e:  # noqa: BLE001  (fails closed: an inconclusive batch, its copies go to the measurement)
            r = C.CompileResult(False, None, 0.0, [f"environment: {type(e).__name__}: {e}"[:300]],
                                messages=[{"severity": "error", "pos": {"line": 0}, "data": f"environment: {type(e).__name__}"}])
            n = (ev.compiles - n0) if ev is not None else 0
        meter.compiles += n
        return r, n
    return run
