"""lean_skeleton junk salvage (b64 L1, 2026-10-26; docs/plateau_levers.md L1; agent.py --skeleton-salvage).

Sol degenerates inside a lean_skeleton call's arguments almost only on a session's FIRST skeleton call, and exactly where the next schema
property would follow the draft: in the 151 junk skeleton calls of four Sol runs (it1b, it2a, ck1a, ck1b; 0 junk in 11,227 calls to other
tools), 99 close the `content` string and then emit a whitespace run where `,"path": ""` would come; the other 52 end the draft and then
emit filler lines (a run of one repeated line, or lines at a smaller indentation than the proof, e.g. a column-0 marker word). The junk guard
drops the whole call, so the draft the model wrote is lost and the turn is wasted.

`salvage(args, statement)` recovers the draft when a usable Lean body is present and returns it as ordinary lean_skeleton input; nothing
else from the junk call is ever used (no `path`, no other tool call). Rules, all textual (no row knowledge):
  1. the `content` string: the parsed value when the arguments parsed, else the JSON string from `"content": "` up to its closing quote,
     or up to the end of the cut stream (then the last, partial line is dropped);
  2. the draft must start with the row's statement followed by `:=` (byte-identical, as lean_skeleton requires);
  3. the proof's base column is the indentation of the first non-blank line after the `:=` line; the draft is cut at the first later
     line indented less than that (it would end the declaration: the filler markers sit there), except a `termination_by` /
     `decreasing_by` clause, which belongs to the declaration at any column (review 2026-10-26: 1 of the 151 recorded calls);
  4. a final run of >= RUN_MIN identical lines collapses to one copy; blank lines and trailing spaces at the end are dropped;
  5. the result must contain 1..MAX_HOLES `sorry` holes and no junk (llm/junk.junk_reason) anywhere, else nothing is salvaged.
"""
from __future__ import annotations

import json
import re

RUN_MIN = 6        # a final run of this many identical lines is filler (legitimate drafts repeat a line at most a few times)
_DECL_TAIL = re.compile(r"(termination_by|decreasing_by)\b")   # clauses of the declaration itself, often written at column 0
MAX_HOLES = 40     # more holes than this after the cut: the filler was not removed; do not run it


def content_of(args) -> tuple[str | None, bool]:
    """The `content` argument of a junk lean_skeleton call and whether its string was closed. `args` is the parsed input (a dict, possibly
    with junk inside the string) or the raw argument text of a call cut mid-stream."""
    if isinstance(args, dict):
        if isinstance(args.get("content"), str):
            return args["content"], True
        args = args.get("_raw_arguments")
    if not isinstance(args, str):
        return None, False
    m = re.search(r'"content"\s*:\s*"', args)
    if not m:
        return None, False
    i, n = m.end(), len(args)
    while i < n:   # find the closing quote: skip escapes
        c = args[i]
        if c == "\\":
            i += 2; continue
        if c == '"':
            try:
                return json.loads(args[m.end() - 1:i + 1]), True
            except ValueError:
                return None, False
        i += 1
    body = args[m.end():]
    body = re.sub(r"\\(u[0-9a-fA-F]{0,3})?$", "", body)   # a cut escape at the very end (a lone backslash or a partial \uXXXX)
    try:
        return json.loads('"' + body + '"'), False
    except ValueError:
        return None, False


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def trim(draft: str, statement: str, closed: bool) -> tuple[str | None, str]:
    """Rules 2-4 on a decoded draft: (the trimmed draft, what was cut) or (None, why not usable)."""
    if not closed:
        draft = draft[:draft.rfind("\n")] if "\n" in draft else ""   # the last line was cut mid-stream
    if not draft.startswith(statement):
        return None, "the draft does not start with the reference statement"
    m = re.match(r"\s*:=", draft[len(statement):])
    if not m:
        return None, "no `:=` after the statement"
    head = draft[:len(statement) + m.end()]
    lines = draft[len(head):].split("\n")   # lines[0] is the rest of the `:=` line
    base = next((_indent(l) for l in lines[1:] if l.strip()), None)
    cut, why = len(lines), []
    if base:   # a body at column 0 has no smaller indentation to cut at
        for k in range(1, len(lines)):
            if lines[k].strip() and _indent(lines[k]) < base and not _DECL_TAIL.match(lines[k].lstrip()):
                cut = k; why.append(f"cut at body line {k} (indented {_indent(lines[k])} < {base})"); break
    lines = lines[:cut]
    while len(lines) > 1 and not lines[-1].strip():
        lines.pop()
    run = 1
    while run < len(lines) - 1 and lines[-1 - run].rstrip() == lines[-1].rstrip():
        run += 1
    if run >= RUN_MIN:
        lines = lines[:len(lines) - run + 1]; why.append(f"collapsed a final run of {run} identical lines")
    while len(lines) > 1 and not lines[-1].strip():
        lines.pop()
    out = (head + "\n".join(lines)).rstrip()
    if not out[len(head):].strip() or out[len(head):].strip() == "by":
        return None, "no proof body left after the cut"
    return out, "; ".join(why) or "draft complete before the junk"


def salvage(args, statement: str) -> dict:
    """{"draft": str | None, "why": str, "closed": bool, "dropped_chars": int}: the usable draft of a junk lean_skeleton call, or None."""
    from llm.junk import junk_reason
    text, closed = content_of(args)
    if text is None:
        return {"draft": None, "why": "no `content` string in the call", "closed": closed, "dropped_chars": 0}
    draft, why = trim(text, statement, closed)
    if draft is not None:
        holes = len(re.findall(r"\bsorry\b", draft))
        if not holes:
            draft, why = None, "no `sorry` hole in the salvaged draft"
        elif holes > MAX_HOLES:
            draft, why = None, f"{holes} `sorry` holes left after the cut (filler not removed)"
        elif junk_reason(draft):
            draft, why = None, "junk left inside the draft after the cut"
    return {"draft": draft, "why": why, "closed": closed, "dropped_chars": len(text) - len(draft) if draft is not None else len(text)}
