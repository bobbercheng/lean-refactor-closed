#!/usr/bin/env python3
"""Bet D4 end_d4 (docs/closed_run2.md, "offline research wins as deterministic end-stage ops"; 2026-11-02: every research gain a
deterministic tool can reproduce is done by a tool, not a model): a $0, model-free, accept-gated pass at the END of every row (after the end
step, style_rw, end_dialect and end_ops; router --end-d4 on), built like bet D3's end_ops (harness/end_ops.py) and b102's end_dialect.

What it runs on the row's final (router.final_of), in this order:
  1. polish   harness/endstage.end_stage on that one proof with the D4 families only, each generic (it reads only the given proof's own
              text, the statement and the row's own environment):
                implied       (harness/tools/d4_implied.py, rule R1; env query with an axiom gate) a decide-family closer at the end
                              of the proof decides the hypothesis Q of a library theorem `Q -> P` (or `P ↔ Q`) instead of the goal P; the
                              point-free spellings (`L ∘'by C`, dependent composition) only under the sub-switch D4P (--end-d4-pointfree
                              on: a Nov 1 decision put them in future packages; the launcher decides shipping); the library-search bridge
                              (`apply forall_imp; exact?; C`: a search tactic written into the final) only under the sub-switch D4S
                              (--end-d4-search on: no ruling covers search tactics in finals; the launcher decides shipping)
                inlineeq      (harness/tools/d4_inlineeq.py, rule R2; env query) an equation proved inline in a simp-family lemma list
                              -> `← by simpa using h ARGS` from the item's own hint h or its environment siblings; plus pure trims of such
                              items (`(by t : T)` -> `show T by t`, ascription drop, `from by` -> `by`, a single-use `have` inlined)
                searchinline  (harness/tools/d4_search.py, rule R3; env query = one compile of the proof) a search tactic left in the
                              proof -> the "Try this" text Lean prints for it, and shorter spellings
                primeglue     (harness/tools/d4_lex.py) a prime-ended notation token joined to the next word (`'' s` -> `''s`): one
                              lexer token less, the same Lean tokens
                micro         (harness/tools/d4_micro.py) the research lanes' hand micro-rewrites no closed op covers: simp <-> norm_num
                              head swaps (alone and with one list item dropped), rw -> simp only, congr 1 <-> apply congrArg, a by-argument
                              unnested
              No sweep, no crossover, k 0 (the pick reads the row's seed and the final, keeps the better on the paired rule; the final is
              a floor), a tool phase of SECONDS wall and COMPILES compiles (each env query counts one), PASSES greedy passes while the
              incumbent changes, batch screening on (with the heartbeat bound: an expensive candidate is cut by maxHeartbeats) except for
              a candidate that runs a search tactic (`exact?`, `apply?`, ...; harness/tools/d4_search.SEARCH_RE) or any candidate while
              the incumbent runs one: a batch file holds the other candidates' renamed copies of the same theorem, which a library
              search can find and use (a fail there need not be a fail alone; seen on a real row, 2026-11-02), so those are measured
              unscreened (screener()). Every
              candidate is banked only through the end stage's own rule: paired scorer.accept.decide against the incumbent re-read right
              after it, then a confirmation on every pin.
  2. accept   the router's own check (router.end_d4_step = the end_dialect step's code with this module): the final and this pass's output
              back to back on the router's evaluator, every pin; adopted only when it reads strictly higher. Anything else, an exception
              included: the final stays byte-identical.
Every term-mode body a family writes stays on the `:=` line (the official worker counts `:=` + a line break as one more token). Off by
default: the router imports this module only with the flag, and config.json gets no "end_d4" key without it."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STEP = "end_d4"
FAMILIES = ("implied", "inlineeq", "searchinline", "primeglue", "micro")
MODULES = {"implied": "harness.tools.d4_implied", "inlineeq": "harness.tools.d4_inlineeq", "searchinline": "harness.tools.d4_search",
           "primeglue": "harness.tools.d4_lex", "micro": "harness.tools.d4_micro"}
TIERS = {"implied": 1, "inlineeq": 1, "searchinline": 1, "primeglue": 1, "micro": 1}   # one tier: registry order = FAMILIES order
QUERY = ("implied", "inlineeq", "searchinline")
POINTFREE_OPT_IN = "implied:pointfree"
SEARCH_OPT_IN = "implied:search"
SECONDS = 600.0        # the tool phase's wall per row (also the pick's phase wall)
COMPILES = 200         # the tool phase's compiles per row (a batch screen file counts one; each env query counts one)
PICK_COMPILES = 40     # the pick: the seed and the final on the primary pin, the better one's other pins
PASSES = 3             # greedy passes while the incumbent changes
CAPS = {"implied": 40, "inlineeq": 60, "searchinline": 20, "primeglue": 10, "micro": 60}
CODE = ("harness/end_d4.py", "harness/tools/d4_kit.py", "harness/tools/d4_implied.py", "harness/tools/d4_inlineeq.py",
        "harness/tools/d4_search.py", "harness/tools/d4_lex.py", "harness/tools/d4_micro.py", "harness/tools/d3_simpconst.py")


def register():
    """The pass's families in this process's harness.endstage (FAMILIES, QUERY_FAMILIES, CODE_FILES); idempotent; returns the module."""
    from harness import endstage as ES
    for f in FAMILIES:
        ES.FAMILIES.setdefault(f, {"module": MODULES[f], "tier": TIERS[f]})
    for f in QUERY:
        if f not in ES.QUERY_FAMILIES:
            ES.QUERY_FAMILIES = tuple(ES.QUERY_FAMILIES) + (f,)
    for f in CODE:
        if f not in ES.CODE_FILES:
            ES.CODE_FILES = tuple(ES.CODE_FILES) + (f,)
    return ES


def config(seconds: float = SECONDS, compiles: int = COMPILES, pointfree: bool = False, search: bool = False) -> dict:
    """The pass's frozen settings (router config.json "end_d4", written only when on)."""
    return {"families": list(FAMILIES), "seconds": float(seconds), "compiles": int(compiles), "pick_compiles": PICK_COMPILES,
            "passes": PASSES, "caps": dict(CAPS), "pointfree": bool(pointfree), "search": bool(search), "normalize": False}


def args_check(seconds, compiles) -> str | None:
    import math
    if not (isinstance(seconds, (int, float)) and math.isfinite(seconds) and seconds > 0):
        return f"--end-d4-seconds {seconds}: a finite number of seconds > 0"
    if not (isinstance(compiles, int) and compiles >= 1):
        return f"--end-d4-compiles {compiles}: an integer >= 1"
    try:
        ES = register()
        for f in FAMILIES:
            ES.families_for(False, (f,))
    except Exception as e:  # noqa: BLE001
        return f"--end-d4 on: the D4 families cannot be registered ({type(e).__name__}: {str(e)[:160]})"
    return None


def _floor(item: dict) -> dict:
    return {x: item[x] for x in ("proof", "score", "tokens", "heartbeats", "stage") if item.get(x) is not None}


def family_ctx(cfg: dict) -> dict | None:
    """The sub-switches as implied's opt-in ops (D4P: point-free; D4S: the search bridge); None without them (the default ops)."""
    opt = [o for o, on in ((SEARCH_OPT_IN, cfg.get("search")), (POINTFREE_OPT_IN, cfg.get("pointfree"))) if on]
    return {"implied": {"opt_in": opt}} if opt else None


SEARCH_UNSCREENED = "a search tactic in the candidate or the incumbent (the batch file's other copies are in its search space)"


def searches(text: str) -> bool:
    """True when `text` runs a search tactic outside comments and strings (harness/tools/d4_search.SEARCH_RE)."""
    from harness.normalize import _mask
    from harness.tools.d4_search import SEARCH_RE
    mask = _mask(text)
    return any(not mask[m.start()] for m in SEARCH_RE.finditer(text))


def screener(meter, log):
    """The tool phase's batch screen (the end stage's own: meter.screener with its defaults) with the D4 rule of the module docstring:
    a candidate that runs a search tactic, or every candidate while the incumbent (the control copy) runs one, is returned
    "unscreened" (it goes to the paired measurement, as a candidate the screen cannot judge does). None when the meter has no screener
    (the end stage then asks meter.screener itself, as it would)."""
    if not hasattr(meter, "screener"):
        return None
    from harness import endstage as ES
    scr = meter.screener(k=ES.SCREEN_K, max_depth=ES.SCREEN_DEPTH, cache=None, log=log)
    if scr is None:   # this meter does not screen
        return None
    inner = scr.screen

    def screen(items, **kw):
        ctl = kw.get("control")
        out, keep = {}, []
        for it in items:
            if (isinstance(ctl, str) and searches(ctl)) or searches(it["text"]):
                out[it["key"]] = {"verdict": "unscreened", "error": SEARCH_UNSCREENED}
            else:
                keep.append(it)
        if keep:
            out.update(inner(keep, **kw))
        return out
    scr.screen = screen
    return scr


def polish(row: dict, seed: str, cur: dict, meter, cfg: dict, log) -> dict:
    """Step 1: the end stage with the D4 families on the final (`cur`, the floor). Returns end_stage's result."""
    ES = register()
    return dict(ES.end_stage(row, seed, [], meter, k=0, sweep=False, crossover=False, max_compiles=int(cfg["pick_compiles"]),
                             checkpoint_bests={"final": _floor(cur)}, log=log, tools=tuple(cfg["families"]),
                             max_seconds=float(cfg["seconds"]), tools_max_compiles=int(cfg["compiles"]),
                             tools_max_seconds=float(cfg["seconds"]), passes=int(cfg["passes"]), family_caps=dict(cfg["caps"]),
                             family_ctx=family_ctx(cfg), screener=screener(meter, log)) or {})


def verified(res: dict) -> bool:
    ok = bool(res["verified"]) if "verified" in res else res.get("stage") not in (None, "unmeasured")
    return ok and isinstance(res.get("proof"), str) and bool(res["proof"].strip())


def normalize(name: str, decl: str, statement: str, log) -> tuple[str | None, dict]:
    """No normalizer in this pass (end_dialect runs it): (None, a short report)."""
    return None, {"status": "off"}
