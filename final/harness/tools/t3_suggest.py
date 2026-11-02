#!/usr/bin/env python3
"""T3 goal-aware closers (round R3, opt-in): ask Lean which tactic closes the goal left at each of T3's top spans, then let T3 propose the
span replaced by each answer (op "t3:hint" in harness/tools/t3_reclose.py; end stage: --t3-suggest). The probes are the only compiles;
the candidates they lead to go through the end stage's batch screen, paired decide and confirmation compile like every other candidate.

  probe     for a span of the incumbent (t3_reclose.ranked_spans: T3's ranking, top TOP_SPANS), the incumbent with the span replaced by
            one suggestion tactic, chosen by the rule PROBE_RULE: Mathlib's `hint` when the row imports Mathlib (T3's scope rule,
            t3_reclose._scope: ctx "scope", else "source" (strata is core-only, every other source imports Mathlib), else "imports"),
            otherwise Lean core's `try?`. Checked 2026-10-22 on the installed pins: `try?` answers on every core toolchain v4.25.0 ...
            v4.33.0-rc2; Mathlib.Tactic.Hint is built in every Mathlib-based env (mathlib-v4.25.0 ... v4.27.0, arklib, cslib, physlib)
            and imported by Mathlib.Tactic.Common; `hint` answered on mathlib-v4.25.0 and cslib-v4.33.0-rc2. A row whose import closure
            has no `hint` (every judged probe copy has the error "unknown tactic" at the probe's line) is probed once more with `try?`
            (stats "fallback"). Modes (probe_tactics): "rule" (the default, above), "try?" or "hint" (that tactic on every row; `hint`
            falls back as above), "both" (`hint` and `try?` on a Mathlib row: `hint` reports only its first closer, `try?` every closer
            it found; `try?` alone on a core row). Several tactics are probed one after the other, each in files of its own with its own
            file allowance (review R3, 2026-10-22: in shared files the second tactic's copies were the ones PROBE_MAX_FILES cut on a slow
            row, so "both" was `hint` alone there), so mode "both" probes the same spans as "hint" and "try?" alone and its result is the
            union of theirs; stats "by_tactic" counts each tactic's probes.
  batch     compile_batch(texts) -> [None | that copy's messages, each with "decl_line" (its line within the text, 1-based)]: None when
            the copy was not in a file that finished (not renameable, timed out, crashed). batch_compiler() builds it on
            harness/batch_screen.py's file layout (renamed copies, `#print` markers, per-copy line ranges, the declaration's attribute
            lists dropped; the probed declaration as an `example`, "anonymous" below) with `set_option maxHeartbeats P in` per copy,
            P = probe_hb_cap(the incumbent's heartbeats) = the incumbent's heartbeats + PROBE_HB_SEARCH (thousands, as Lean's option and
            the meter count them; the copy elaborates the proof without the span, plus the search). Measured 2026-10-22 on a dev row
            (physlib, incumbent 2039, `try?` on 4 spans, one copy per file): cap 10000 -> 31 s for the 4, every copy finished;
            cap 50000 and Lean's default 200000 -> 2 of 4 copies past their wall timeout (about 50 s each); at the default, a file of
            8 copies (`hint` and `try?`) timed out after 200 s and its results were lost.
            What the cap bounds (review R3, 2026-10-22). `hint` (Mathlib) searches under the declaration's own count: a slow search ends
            in a heartbeat error inside its copy (seen on mathlib-v4.25.0: stopped at the cap after 3 s). `try?` does too on v4.25.0. From
            v4.26.0 (checked up to v4.33.0-rc2, Lean/Elab/Tactic/Try.lean) `try?` runs its search with unlimited heartbeats and gives
            each tactic it tries a fresh budget equal to the declaration's maxHeartbeats, a heartbeat stop being an ordinary failure:
            the cap then bounds each tried tactic, not their sum, and no option inside the file bounds the sum. A tactic-level
            `set_option maxHeartbeats S in try?` does not either: Lean's tactic `set_option` changes the options but not the
            elaborator's heartbeat limit (checked 2026-10-22 on v4.25.0, v4.27.0 and v4.33.0-rc2: `set_option maxHeartbeats 1 in try?`
            printed the same suggestions as an uncapped `try?`, and `set_option maxHeartbeats 1 in omega` elaborated, while the kernel
            check of the auxiliary proof does read the option: it would only add kernel timeouts). A `try?` copy is bounded by its
            file's wall timeout alone; hence files per tactic (above: a slow `try?` copy cannot cost the `hint` copies), one halving,
            and per-tactic counters of the copies lost to a timeout or a crash ("timeout" / "crash") and of judged copies stopped by
            heartbeats ("hb_out"). The probe's wall time per pin is to be measured
            before a config with `try?` is frozen. At most PROBE_K copies and TARGET_S / (compile time + PROBE_EXTRA_S) per file,
            a wall timeout of compile time + copies x (compile time + PROBE_EXTRA_S) + 30 s (capped by the meter's), one halving of a
            file that timed out or crashed (PROBE_DEPTH), at most PROBE_MAX_FILES files per call (halvings included; spans in T3's rank
            order, so a slow row probes its top spans only: 20 spans in one file at a 10 s compile, 7 per file at 60 s, 1 at 300 s).
            need(1) before each file (the caller's budget may raise), charge(n) after it. A copy that comes back None carries its reason
            in the result's "why" ({index: "timeout" | "crash" | "skipped" | "unbuildable"}).
  parse     Lean's suggestion messages (severity information) at the probe's line of its copy. Formats seen on the installed toolchains
            (core v4.25.0 ... v4.33.0-rc2, Mathlib v4.25.0 and v4.33.0-rc2): "Try this:\\n  [apply] t", "Try these:\\n  [apply] t1\\n
            [apply] t2 ..."; a long suggestion wraps onto deeper-indented lines; Mathlib's `hint` marks a closing tactic with "🎉"
            ("🎉️", with U+FE0F, on v4.33) and a progress-only one with a following "Remaining subgoals:" block. Also accepted: the one-line
            "Try this: t" and "• t" bullets of older toolchains. Kept: closing suggestions that are one logical line (a newline only
            inside brackets; whitespace collapsed). Dropped and counted: progress-only ("progress"), a newline at bracket depth 0 such as
            a `grind =>` script ("structured"), `#` anchors such as `grind only [#8121]` ("pin_local": the hash differs between
            toolchains), inaccessible names `✝` ("inaccessible"), `sorry` / `admit` ("sorry"), a `?` tactic ("search"), comments
            ("comment"), the probe tactic itself ("probe"), a name of a batch copy (`_lra_scr<k>`, "batch_copy"), an internal name (a
            component starting with `_`, such as the auxiliary `simp` lemmas of the probe's own `example`, `_example._simp_3`, seen
            2026-10-22 on a physlib dev row: the name does not exist in the real file, "internal").
  anonymous copies all share one environment, and library search (`exact?` inside `hint`) finds an earlier copy that proves the same
            goal (seen 2026-10-22 on mathlib-v4.25.0: `exact <name>_lra_scr0 a b h`), which does not exist in the real file. The probe
            file therefore writes the statement's last declaration (theorem / lemma / def / abbrev) as an `example`: no name, nothing
            added to the environment (`private` / `noncomputable` / `nonrec` stay, `protected` goes: it needs a namespace). Not done
            (the copies keep their renamed names, the "batch_copy" drop still applies) when the keyword and the name are on different
            lines, the name has explicit universes (`.{u}`) or a namespace prefix (`theorem Foo.bar` resolves names inside Foo), or
            the proof names the declaration (a recursive call).
  clean     `try?` and `hint` close the goal they report on with their first closer (checked on v4.25.0 / v4.33.0-rc2: the steps
            after the probe ran on the remaining goals), but only the MAIN goal: where the span closed more (the last steps of a block
            with several goals open, measured 2026-10-22 on a core dev row: 2 of 2 suggestions left "unsolved goals"), the probe copy
            ends in an error. A span's suggestions are kept only when its probe copy has no error message at all ("copy_error"
            otherwise, counted per suggestion), so the probe also screens its own first suggestion.
  result    suggest() -> {(start, end): [tactic, ...]}: per span with at least one kept suggestion, deduplicated, fewest tokens first
            (Lean's order on ties, then the tactics' order). The keys are the span's character offsets in the probed proof; T3 uses them
            only on that same proof (ctx "suggestions_for" = proof_key(proof), required).
Provenance (docs/tools_build_plan.md): every token of a kept suggestion is printed by Lean at run time for the row's own goal. This module
types no Lean token besides the two probe tactics of PROBE_RULE, the option names of the batch layout, and the message markers above; none
is taken from a proof.
    python3 harness/tools/t3_suggest.py --messages lean.jsonl --line N    parse the suggestions at line N of a `lean --json` output"""
from __future__ import annotations

import argparse, hashlib, json, math, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.batch_screen import SUFFIX as BATCH_SUFFIX  # noqa: E402  (the screen's copy suffix, `_lra_scr<k>`)
from scorer.tokenize import count_tokens  # noqa: E402

PROBE_MATHLIB = "hint"     # Mathlib.Tactic.Hint
PROBE_CORE = "try?"        # Lean core (Init.Try)
PROBE_RULE = ("probe tactic: Mathlib's `hint` when the row imports Mathlib (t3_reclose._scope == 'mathlib'), else Lean core's `try?`; "
              "a probe whose copies all fail with 'unknown tactic' at the probe is redone with `try?`; opt-in modes: try?, hint, both")
PROBE_K = 20               # probe copies per Lean file at most (T3 ranks TOP_SPANS = 20 spans)
PROBE_EXTRA_S = 20         # seconds allowed per probe copy on top of the incumbent's compile time (the search itself)
PROBE_HB_SEARCH = 20000    # heartbeats (thousands) a probe copy may spend beyond the incumbent's own (the search; module docstring)
PROBE_DEPTH = 1            # halvings of a probe file that timed out or crashed
PROBE_MAX_FILES = 2        # probe files (compiles) per suggest() call: the top-ranked spans that fit are probed, the rest are not
TARGET_S = 600             # a probe file's expected wall time at most (harness/batch_screen.TARGET_S)
UNKNOWN_TACTIC = "unknown tactic"
REMAINING = "Remaining subgoals:"

_HEAD = re.compile(r"^\s*Try (?:this|these):[ \t]*(.*)$")
_ITEM = re.compile(r"^(\s*)(?:\[apply\]|•)[ \t]?(.*)$")
_APPLY = re.compile(r"^\[apply\][ \t]?")
_PARTY = re.compile("^\U0001F389️?[ \t]*")
_SORRY = re.compile(r"(?<![\w.'])(?:sorry|admit)(?![\w'])")
_SEARCH = re.compile(r"[\w']\?(?![\w'])")
_HB_OUT = re.compile(r"maximum number of heartbeats|deterministic\) timeout|\(kernel\) deterministic timeout")   # a heartbeat stop
_INTERNAL = re.compile(r"(?:^|(?<=[^\w'.])|(?<=\.))_[A-Za-z0-9]")   # a name component starting with `_` (`_example._simp_3`); `_` holes pass   # `exact?`, `simp?`, `simp_all?` (a `?_` / `?x` hole has no identifier character before it)


def proof_key(proof: str) -> str:
    """The key T3 checks ctx["suggestions_for"] against (sha256 of the stripped proof, 16 hex digits; harness/endstage.sha)."""
    return hashlib.sha256(proof.strip().encode()).hexdigest()[:16]


def probe_tactic(scope: str) -> str:
    """PROBE_RULE: `hint` for a Mathlib scope, `try?` otherwise."""
    return PROBE_MATHLIB if scope == "mathlib" else PROBE_CORE


MODES = ("rule", "try?", "hint", "both")


def probe_tactics(scope: str, mode: str | None = "rule") -> tuple[str, ...]:
    """The probe tactics of a row of T3 scope `scope` under `mode` (module docstring, "probe")."""
    if mode in (None, "rule", True):
        return (probe_tactic(scope),)
    if mode == "both":
        return (PROBE_MATHLIB, PROBE_CORE) if scope == "mathlib" else (PROBE_CORE,)
    if mode in (PROBE_CORE, PROBE_MATHLIB):
        return (mode,)
    raise ValueError(f"unknown probe mode {mode!r} (known: {', '.join(MODES)})")


def probe_hb_cap(heartbeats) -> int:
    """`maxHeartbeats` of a probe copy (thousands): the incumbent's heartbeats + PROBE_HB_SEARCH."""
    try:
        h = int(heartbeats or 0)
    except (TypeError, ValueError):
        h = 0
    return max(0, h) + PROBE_HB_SEARCH


# ----------------------------------------------------------------------------------------------------------------------------- parse
def _depth0_newline(text: str) -> bool:
    depth = 0
    for ch in text:
        if ch in "([{⟨":
            depth += 1
        elif ch in ")]}⟩":
            depth -= 1
        elif ch == "\n" and depth <= 0:
            return True
    return False


def _why_dropped(text: str, probe: str | None) -> str | None:
    if not text:
        return "empty"
    if "--" in text or "/-" in text:
        return "comment"
    if "#" in text:
        return "pin_local"
    if BATCH_SUFFIX in text:
        return "batch_copy"
    if _INTERNAL.search(text):
        return "internal"
    if "✝" in text:
        return "inaccessible"
    if _SORRY.search(text):
        return "sorry"
    if _SEARCH.search(text):
        return "search"
    if probe is not None and text == probe:
        return "probe"
    return None


def parse_message(data, probe: str | None = None) -> list[dict]:
    """The suggestions of one Lean message: [{"text", "kept", "why"}] in Lean's order ("text": whitespace-collapsed for a one-line
    suggestion, as printed otherwise; "why": None when kept, else the drop reason of the module docstring). [] for a message that is not
    a suggestion."""
    lines = str(data or "").split("\n")
    m = _HEAD.match(lines[0]) if lines else None
    if not m:
        return []
    items: list[dict] = []
    cur = None
    if m.group(1).strip():   # "Try this: t" on one line (older toolchains)
        cur = {"lines": [_APPLY.sub("", m.group(1).strip())], "closes": True, "done": False}
        items.append(cur)
    for ln in lines[1:]:
        im = _ITEM.match(ln)
        if im:
            cur = {"lines": [im.group(2)], "closes": True, "done": False}
            items.append(cur)
            continue
        if cur is None:
            continue
        if ln.strip() == REMAINING:
            cur["closes"], cur["done"] = False, True
            continue
        if not cur["done"] and ln.strip():
            cur["lines"].append(ln)
    out = []
    for it in items:
        first = _PARTY.sub("", it["lines"][0].strip())
        raw = "\n".join([first] + it["lines"][1:]).strip()
        if not it["closes"]:
            out.append({"text": " ".join(raw.split()), "kept": False, "why": "progress"})
            continue
        if _depth0_newline(raw):
            out.append({"text": raw, "kept": False, "why": "structured"})
            continue
        text = " ".join(raw.split())
        why = _why_dropped(text, probe)
        out.append({"text": text, "kept": why is None, "why": why})
    return out


def _line_of(m: dict) -> int | None:
    return m.get("decl_line") if m.get("decl_line") is not None else (m.get("pos") or {}).get("line")


def suggestions_at(messages, line: int, probe: str | None = None) -> tuple[list[str], dict]:
    """(kept suggestions, info) from the messages of one copy at `line` (each message's "decl_line", else its "pos" line): the
    suggestion messages there, in order, deduplicated; info: {"dropped": {why: n}, "unknown_tactic": bool, "messages": n}."""
    kept, seen, info = [], set(), {"dropped": {}, "unknown_tactic": False, "messages": 0}
    for m in messages or []:
        if _line_of(m) != line:
            continue
        data = str(m.get("data", ""))
        if m.get("severity") == "error" and data.strip().startswith(UNKNOWN_TACTIC):
            info["unknown_tactic"] = True
        if m.get("severity") != "information":
            continue
        got = parse_message(data, probe)
        if got:
            info["messages"] += 1
        for s in got:
            if not s["kept"]:
                info["dropped"][s["why"]] = info["dropped"].get(s["why"], 0) + 1
            elif s["text"] not in seen:
                seen.add(s["text"])
                kept.append(s["text"])
    return kept, info


# ----------------------------------------------------------------------------------------------------------------------------- probe
def as_example(statement: str, proof: str | None = None) -> str | None:
    """`statement` with its last declaration written as an `example` (module docstring, "anonymous"), or None when that is not done.
    Lines are kept (the change stays on the keyword's line)."""
    from harness.batch_screen import _DECL_KW, _ID_AFTER, _ID_BEFORE, declared, mask
    m = mask(statement)
    kws = list(_DECL_KW.finditer(m))
    decls = declared(statement)
    if not kws or not decls or len(kws) != len(decls):
        return None
    k, (kw, name, pos) = kws[-1], decls[-1]
    if kw not in ("theorem", "lemma", "def", "abbrev") or not name:
        return None
    gap = statement[k.end(1):pos]
    end = pos + len(name)
    if gap.strip(" \t") or statement[end:end + 2] == ".{" or statement[pos:end] != name:
        return None
    if "." in name and not name.startswith("«"):   # `theorem Foo.bar` resolves names in namespace Foo; an `example` would not
        return None
    if proof is not None and proof.startswith(statement):
        body = mask(proof)[len(statement):]
        if re.search(_ID_BEFORE + re.escape(name) + _ID_AFTER, body):
            return None
    head = statement[:k.start(1)]
    pm = re.search(r"(?<![\w.'])protected[ \t]+$", head)
    if pm:
        head = head[:pm.start()]
    return head + "example" + statement[end:]


def _span_key(sp) -> tuple[int, int] | None:
    try:
        if isinstance(sp, dict):
            return int(sp["start"]), int(sp["end"])
        a, b = sp
        return int(a), int(b)
    except (KeyError, TypeError, ValueError):
        return None


def probe_text(proof: str, key: tuple[int, int], tactic: str) -> str:
    return proof[:key[0]] + tactic + proof[key[1]:]


def suggest(proof: str, statement: str, spans, compile_batch, *, tactic=PROBE_CORE, fallback: str | None = PROBE_CORE,
            max_spans: int | None = None, stats: dict | None = None, log=None, require_clean: bool = True) -> dict:
    """{(start, end): [tactic, ...]} (module docstring, "result") for `spans` (T3 span dicts with "start" / "end", or (start, end) pairs)
    of `proof`, probed with `tactic` (one tactic, or several: every span with each, in the same compile_batch call, the suggestions
    merged) through compile_batch(texts) (module docstring, "batch"); `fallback`: the tactic of a second probe when every copy of the
    first (single) tactic is unknown on this row (None: no second probe); require_clean: keep a span's suggestions only when its probe copy has
    no error (module docstring, "clean"). Several tactics: one compile_batch call per tactic, in the given order, each over every span
    (module docstring, "probe"). stats (updated, counters summed over calls): tactic, probes, judged, spans_with, suggestions, dropped
    {why: n}, fallback, seconds, by_tactic {tactic: {probes, judged, unknown, hb_out, timeout, crash, skipped, unbuildable, spans_with,
    suggestions, seconds}}."""
    st = stats if stats is not None else {}
    log = log or (lambda m: None)
    keys = []
    for sp in (spans or []) if proof.startswith(statement) else []:
        k = _span_key(sp)
        if k and len(statement) <= k[0] < k[1] <= len(proof) and k not in keys:
            keys.append(k)
    if max_spans is not None:
        keys = keys[:max(0, int(max_spans))]
    st.setdefault("probes", 0)
    st.setdefault("judged", 0)
    st.setdefault("dropped", {})
    for c in ("spans_with", "suggestions"):
        st.setdefault(c, 0)
    if not keys:
        st.setdefault("tactic", tactic)
        return {}
    t0 = time.time()

    tacs = (tactic,) if isinstance(tactic, str) else tuple(dict.fromkeys(tactic))
    by = st.setdefault("by_tactic", {})

    def run(tac):
        """One tactic over every span, in one compile_batch call (its own files): ({span: [kept]}, judged, unknown)."""
        B = by.setdefault(tac, {})
        for c in ("probes", "judged", "unknown", "hb_out", "timeout", "crash", "skipped", "unbuildable", "spans_with", "suggestions"):
            B.setdefault(c, 0)
        texts = [probe_text(proof, k, tac) for k in keys]
        t1 = time.time()
        got = compile_batch(texts)
        B["seconds"] = round(B.get("seconds", 0.0) + time.time() - t1, 1)
        why = dict(getattr(got, "why", None) or {})
        got = list(got or []) + [None] * (len(texts) - len(got or []))
        st["probes"] += len(texts)
        B["probes"] += len(texts)
        merged, judged, unknown = {}, 0, 0
        for i, (k, text, msgs) in enumerate(zip(keys, texts, got)):
            if msgs is None:
                w = why.get(i, "timeout")
                B[w] = B.get(w, 0) + 1
                continue
            judged += 1
            B["hb_out"] += any(m.get("severity") == "error" and _HB_OUT.search(str(m.get("data", ""))) for m in msgs)
            kept, info = suggestions_at(msgs, text[:k[0]].count("\n") + 1, tac)
            unknown += bool(info["unknown_tactic"])
            for w, n in info["dropped"].items():
                st["dropped"][w] = st["dropped"].get(w, 0) + n
            if kept and require_clean and any(m.get("severity") == "error" for m in msgs):
                st["dropped"]["copy_error"] = st["dropped"].get("copy_error", 0) + len(kept)
                kept = []
            if kept:
                merged.setdefault(k, []).extend(t for t in kept if t not in merged.get(k, []))
        st["judged"] += judged
        B["judged"] += judged
        B["unknown"] += unknown
        B["spans_with"] += len(merged)
        B["suggestions"] += sum(len(v) for v in merged.values())
        return merged, judged, unknown

    merged: dict = {}
    for tac in tacs:
        got, judged, unknown = run(tac)
        if fallback and len(tacs) == 1 and fallback != tac and judged and unknown == judged:
            log(f"t3 suggest: `{tac}` is unknown on this row; probing again with `{fallback}`")
            st["fallback"] = fallback
            got, judged, unknown = run(fallback)
        for k in keys:   # span order; per span the tactics' order, then Lean's
            for t in got.get(k, []):
                if t not in merged.setdefault(k, []):
                    merged[k].append(t)
    res = {k: sorted(v, key=lambda s: (count_tokens(s), v.index(s))) for k, v in merged.items() if v}
    st["tactic"] = "+".join(tacs)
    st["spans_with"] += len(res)
    st["suggestions"] += sum(len(v) for v in res.values())
    st["seconds"] = round(st.get("seconds", 0.0) + time.time() - t0, 1)
    return res


class _Judged(list):
    """compile_batch's result: a list (None for a copy that was not judged) with "why" {index: reason} for those copies."""

    def __init__(self, items=()):
        super().__init__(items)
        self.why: dict = {}


def batch_compiler(statement: str, compile_fn, layout, *, hb_cap: int | None = None, compile_s: float | None = None, timeout: int = 900,
                   k: int = PROBE_K, depth: int = PROBE_DEPTH, need=None, charge=None, stats: dict | None = None, log=None,
                   anonymous: bool = True, max_files: int | None = PROBE_MAX_FILES):
    """compile_batch for suggest() on harness/batch_screen.py's file layout (module docstring, "batch"). compile_fn(body, copies, layout,
    timeout) -> (CompileResult-like: ok, messages, timed_out, errors; physical compiles), as BatchScreener's. anonymous: the probed
    declaration as an `example` where as_example() allows it (module docstring, "anonymous"); a file holds copies of one statement form
    (texts that cannot be written as an example go into files of their own). max_files: compiles per call at most (None: no bound); the
    texts left over come back None (stats "copies_skipped"). The returned list carries "why" {index: "timeout" | "crash" | "skipped" |
    "unbuildable"} for the copies that come back None."""
    from harness.batch_screen import build
    st = stats if stats is not None else {}
    log = log or (lambda m: None)
    cs = float(compile_s) if isinstance(compile_s, (int, float)) and compile_s > 0 else 60.0
    kb = max(1, min(int(k), int(TARGET_S // (cs + PROBE_EXTRA_S))))

    def _anon(t: str) -> tuple[str, str]:   # (the text as the file writes it, the statement it starts with)
        if anonymous and t.startswith(statement):
            ex = as_example(statement, t)
            if ex is not None:
                return ex + t[len(statement):], ex
        return t, statement

    def compile_batch(texts: list[str]) -> list:
        out = _Judged([None] * len(texts))
        files = [0]
        forms = [_anon(t) for t in texts]
        st["anonymous"] = st.get("anonymous", 0) + sum(1 for _, s_ in forms if s_ != statement)
        groups: dict = {}
        for i, (_, s_) in enumerate(forms):
            groups.setdefault(s_, []).append(i)
        queue = [(g[i:i + kb], 0) for g in groups.values() for i in range(0, len(g), kb)]
        while queue:
            idx, d = queue.pop(0)
            body, copies, spans = build([forms[i][0] for i in idx], forms[idx[0]][1], layout, hb_cap)
            if d == 0 and any(sp is None for sp in spans):   # not renameable (or not this statement): never in a file
                st["unbuildable"] = st.get("unbuildable", 0) + sum(sp is None for sp in spans)
            for i, sp in zip(idx, spans):
                if sp is None:
                    out.why[i] = "unbuildable"
            if all(sp is None for sp in spans):
                continue
            if max_files is not None and files[0] >= int(max_files):
                st["copies_skipped"] = st.get("copies_skipped", 0) + sum(sp is not None for sp in spans)
                out.why.update({i: "skipped" for i, sp in zip(idx, spans) if sp is not None})
                continue
            if need:
                need(1)
            files[0] += 1
            to = int(max(1, min(int(timeout), math.ceil(cs + len(idx) * (cs + PROBE_EXTRA_S)) + 30)))
            t0 = time.time()
            res, n = compile_fn(body, copies, layout, to)
            if charge:
                charge(int(n))
            st["batches"] = st.get("batches", 0) + 1
            st["compiles"] = st.get("compiles", 0) + int(n)
            st["batch_seconds"] = round(st.get("batch_seconds", 0.0) + time.time() - t0, 1)
            msgs = list(getattr(res, "messages", None) or [])
            if getattr(res, "timed_out", False) or (not msgs and not getattr(res, "ok", False)):
                kind = "timeout" if getattr(res, "timed_out", False) else "crash"
                st[kind + "s"] = st.get(kind + "s", 0) + 1
                if d < depth and len(idx) > 1:
                    h = (len(idx) + 1) // 2
                    queue[:0] = [(idx[:h], d + 1), (idx[h:], d + 1)]
                    log(f"t3 suggest: a probe file of {len(idx)} {kind}; halved")
                else:
                    out.why.update({i: kind for i, sp in zip(idx, spans) if sp is not None})
                continue
            for j, sp in enumerate(spans):
                if sp is None:
                    continue
                s, mk = sp
                text = forms[idx[j]][0].strip()
                first = (mk - 2) - text.count("\n")   # batch_screen.block: the declaration, a blank line, then the marker
                out[idx[j]] = [dict(m, decl_line=((m.get("pos") or {}).get("line") or 0) - first + 1) for m in msgs
                               if s <= ((m.get("pos") or {}).get("line") or 0) < mk]
        return out
    return compile_batch


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--messages", required=True, help="a `lean --json` output (one JSON message per line)")
    ap.add_argument("--line", type=int, required=True)
    ap.add_argument("--probe", default=None)
    a = ap.parse_args(argv)
    msgs = [json.loads(l) for l in Path(a.messages).read_text().splitlines() if l.startswith("{")]
    kept, info = suggestions_at(msgs, a.line, a.probe)
    print(json.dumps({"kept": kept, **info}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
