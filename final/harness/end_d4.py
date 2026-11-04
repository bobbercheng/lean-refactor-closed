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
              and, each only under its own sub-switch (OPT_FAMILIES; registered, run and frozen into the config only when on), in a
              SECOND end stage after this one (opt_stage: its own tool-phase wall and compiles, the sum of OPT_EXTRA over the families
              on; it starts from this stage's output, whose reading, with its compile seconds, it takes over without a compile, so the
              first stage is exactly D4's and the families' budget is not shared away):
                closerprep    (harness/tools/d4_closerprep.py, env query; sub-switch D4C, --end-d4-closerprep on) `conv_rhs => reduce`
                              / `conv_lhs => reduce` / `conv => reduce` on the line before a decide-family closer, alone and JOINTLY with
                              a ddmin drop (the complement half of D3's sequence) of a simp-family lemma list before it; on a prepared
                              closer (the insertion banked by an earlier pass) the ddmin drops alone
                simpnorm      (harness/tools/d4_simpnorm.py, env query; sub-switch D4N, --end-d4-simpnorm on) a few generic core
                              algebraic normalisation lemmas (GENERIC: zero_mul, ite_mul, zsmul_eq_mul both ways, ...) appended to a
                              simp-family list before a decide-family closer: those the row's environment holds (axiom gate) and its simp
                              set used (Lean's own `simp?` suggestion on the call); singles and pairs
              Both spaces are too large to screen and measure one by one on a row whose compile takes tens of seconds: each family's
              query reads its space in one-file batches (harness/tools/d4_measure.py: heartbeats per variant around elabCommand, the
              incumbent as the control) and proposes only the few variants predicted to read higher (heartbeats saved minus tokens added
              at the row's exchange rate); the proposals are measured and banked by the end stage's own rule like every candidate.
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
default: the router imports this module only with the flag, and config.json gets no "end_d4" key without it; with D4 on and D4C / D4N
off, the config, the registry and the end stage call are exactly D4's (no key, family, budget or code file of theirs)."""
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
# the sub-switch families (D4C: closerprep, D4N: simpnorm; each needs D4): run in a second end stage after the D4 one (opt_stage), each
# with its own config key, family cap and tool-phase budget (OPT_EXTRA: seconds, compiles; the stage's budget is their sum)
OPT_FAMILIES = ("closerprep", "simpnorm")
OPT_MODULES = {"closerprep": "harness.tools.d4_closerprep", "simpnorm": "harness.tools.d4_simpnorm"}
OPT_QUERY = ("closerprep", "simpnorm")   # both have an env query (the measured space)
OPT_CAPS = {"closerprep": 80, "simpnorm": 60}
OPT_EXTRA = {"closerprep": (600.0, 80), "simpnorm": (450.0, 60)}
OPT_CODE = {"closerprep": ("harness/tools/d4_closerprep.py", "harness/tools/d4_measure.py"),
            "simpnorm": ("harness/tools/d4_closerprep.py", "harness/tools/d4_measure.py", "harness/tools/d4_simpnorm.py")}


def register(opt=()):
    """The pass's families in this process's harness.endstage (FAMILIES, QUERY_FAMILIES, CODE_FILES), plus the sub-switch families named in
    `opt` (OPT_FAMILIES); idempotent; returns the module."""
    from harness import endstage as ES
    opt = [f for f in OPT_FAMILIES if f in set(opt or ())]
    mods = dict(MODULES, **{f: OPT_MODULES[f] for f in opt})
    for f in list(FAMILIES) + opt:
        ES.FAMILIES.setdefault(f, {"module": mods[f], "tier": TIERS.get(f, 1)})
    for f in tuple(QUERY) + tuple(f for f in OPT_QUERY if f in opt):
        if f not in ES.QUERY_FAMILIES:
            ES.QUERY_FAMILIES = tuple(ES.QUERY_FAMILIES) + (f,)
    for f in tuple(CODE) + tuple(c for o in opt for c in OPT_CODE[o]):
        if f not in ES.CODE_FILES:
            ES.CODE_FILES = tuple(ES.CODE_FILES) + (f,)
    return ES


def config(seconds: float = SECONDS, compiles: int = COMPILES, pointfree: bool = False, search: bool = False, closerprep: bool = False,
           simpnorm: bool = False) -> dict:
    """The pass's frozen settings (router config.json "end_d4", written only when on). D4C / D4N add their family, cap, a key of their
    own ("closerprep" / "simpnorm": true) and "extra" (the tool-phase seconds and compiles they add) only when on: without them the dict
    is D4's exactly."""
    cfg = {"families": list(FAMILIES), "seconds": float(seconds), "compiles": int(compiles), "pick_compiles": PICK_COMPILES,
           "passes": PASSES, "caps": dict(CAPS), "pointfree": bool(pointfree), "search": bool(search), "normalize": False}
    opt = [f for f, on in (("closerprep", closerprep), ("simpnorm", simpnorm)) if on]
    if opt:
        cfg["families"] += opt
        cfg["caps"].update({f: OPT_CAPS[f] for f in opt})
        cfg.update({f: True for f in opt})
        cfg["extra"] = {"seconds": float(sum(OPT_EXTRA[f][0] for f in opt)), "compiles": int(sum(OPT_EXTRA[f][1] for f in opt))}
    return cfg


def opt_families(cfg: dict) -> list[str]:
    """The sub-switch families a config turns on (OPT_FAMILIES order)."""
    return [f for f in OPT_FAMILIES if cfg.get(f) and f in (cfg.get("families") or [])]


def args_check(seconds, compiles, opt=()) -> str | None:
    import math
    if not (isinstance(seconds, (int, float)) and math.isfinite(seconds) and seconds > 0):
        return f"--end-d4-seconds {seconds}: a finite number of seconds > 0"
    if not (isinstance(compiles, int) and compiles >= 1):
        return f"--end-d4-compiles {compiles}: an integer >= 1"
    try:
        ES = register(opt)
        for f in list(FAMILIES) + [f for f in OPT_FAMILIES if f in set(opt or ())]:
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
    """Step 1: the end stage with the D4 families on the final (`cur`, the floor); then, only when a sub-switch family is on (D4C / D4N),
    a second end stage with those families alone on the first one's output (opt_stage). Returns end_stage's result (the two merged)."""
    opt = opt_families(cfg)
    ES = register(opt)
    secs: dict = {}
    undo = _record_seconds(ES, meter, secs) if opt else None   # D4C / D4N only: the first stage's compile seconds per text
    try:
        res = dict(ES.end_stage(row, seed, [], meter, k=0, sweep=False, crossover=False, max_compiles=int(cfg["pick_compiles"]),
                                checkpoint_bests={"final": _floor(cur)}, log=log, tools=tuple(f for f in cfg["families"] if f in FAMILIES),
                                max_seconds=float(cfg["seconds"]), tools_max_compiles=int(cfg["compiles"]),
                                tools_max_seconds=float(cfg["seconds"]), passes=int(cfg["passes"]), family_caps=dict(cfg["caps"]),
                                family_ctx=family_ctx(cfg), screener=screener(meter, log)) or {})
    finally:
        if undo is not None:
            undo()
    return opt_stage(ES, row, seed, cur, meter, cfg, log, res, opt, seconds=secs) if opt else res


def _record_seconds(ES, meter, out: dict):
    """D4C / D4N (review 2026-11-02): record, by text sha, the primary pin's wall seconds of every reading meter.measure returns during
    the D4 stage (the reading the second stage takes over as known has no "seconds": without them its families' ctx has no compile_s,
    d4_measure.budget falls back to its default and a slow row's measuring file outruns the query timeout). The meter's own measure is
    wrapped on the instance; the returned undo() restores it. None when the meter has no measure to wrap."""
    inner = getattr(meter, "measure", None)
    if not callable(inner):
        return None
    had = "measure" in getattr(meter, "__dict__", {})

    def measure(decl, *a, **kw):
        r = inner(decl, *a, **kw)
        if isinstance(r, dict) and r.get("ok") and isinstance(r.get("seconds"), (int, float)) and r["seconds"] > 0:
            out[ES.sha(str(decl))] = float(r["seconds"])
        return r
    try:
        meter.measure = measure
    except Exception:  # noqa: BLE001  (a meter that refuses the attribute: no record, the default budget stays)
        return None

    def undo():
        try:
            if had:
                meter.measure = inner
            else:
                del meter.measure
        except Exception:  # noqa: BLE001
            pass
    return undo


def opt_ctx(row: dict, meter, opt) -> dict:
    """The sub-switch families' ctx: the row's exchange rate (reference heartbeats / reference tokens, the end stage's own), which their
    queries use to choose what to measure next (the generators get it as `exchange` too)."""
    ref_hb, n = getattr(meter, "ref_hb", None), row.get("proof_length")
    ex = (float(ref_hb) / float(n)) if isinstance(ref_hb, (int, float)) and ref_hb and isinstance(n, (int, float)) and n else None
    return {f: {"exchange": ex} for f in opt}


def opt_stage(ES, row: dict, seed: str, cur: dict, meter, cfg: dict, log, res: dict, opt, seconds: dict | None = None) -> dict:
    """The sub-switch families' own end stage (module docstring): their own tool-phase wall and compiles (cfg "extra"), started from the
    D4 stage's output. When that output was read and confirmed on this meter, its reading is handed over as known (the pick then reads
    nothing and skips the seed: its floor is carried); otherwise the pick reads the seed and the final as the first stage did. Every bank
    goes through the end stage's own rule. `seconds` {sha: wall seconds} (polish's record of the D4 stage's readings): the handed-over
    reading gets its text's seconds, as a reading the pick took would have them (the families' ctx compile_s). Returns the D4 stage's
    result with this stage's decisions, compiles, seconds and family summary added; the proof and metrics are this stage's when it banked
    something, else the D4 stage's."""
    extra = cfg.get("extra") or {}
    sec, nc = float(extra.get("seconds") or 0.0), int(extra.get("compiles") or 0)
    if sec <= 0 or nc <= 0:
        return res
    known, floor_sha, start = None, None, cur
    m = res.get("metrics") or {}
    if verified(res):
        start = {"proof": res["proof"], "score": m.get("score"), "tokens": m.get("tokens"), "heartbeats": m.get("heartbeats"),
                 "stage": res.get("stage")}
        if m.get("compat") and m.get("meter") and m.get("score_exact") is not None and m.get("tokens") is not None \
                and m.get("heartbeats") is not None:
            floor_sha = ES.sha(res["proof"])
            known = {floor_sha: dict(m, ok=True)}
            if isinstance((seconds or {}).get(floor_sha), (int, float)):
                known[floor_sha]["seconds"] = round(float(seconds[floor_sha]), 2)
    try:
        r2 = dict(ES.end_stage(row, seed, [], meter, k=0, sweep=False, crossover=False, max_compiles=int(cfg["pick_compiles"]),
                               checkpoint_bests={"final": _floor(start)}, log=log, tools=tuple(opt), max_seconds=sec,
                               tools_max_compiles=nc, tools_max_seconds=sec, passes=int(cfg["passes"]),
                               family_caps={f: cfg["caps"][f] for f in opt if f in cfg["caps"]}, family_ctx=opt_ctx(row, meter, opt),
                               screener=screener(meter, log), known_readings=known, floor_sha=floor_sha) or {})
    except Exception as e:  # noqa: BLE001  (the second stage never costs the first one's result)
        out = dict(res)
        out["opt_stage"] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
        log(f"end_d4: the {'+'.join(opt)} stage failed ({out['opt_stage']['error']}); the D4 stage's output stands")
        return out
    base = (res.get("proof") or "").strip() if verified(res) else (cur.get("proof") or "").strip()
    banked = verified(r2) and (r2.get("proof") or "").strip() not in ("", base)
    out = dict(r2 if banked else res)
    for d in r2.get("decisions") or []:
        d.setdefault("stage", "+".join(opt))
    out["decisions"] = list(res.get("decisions") or []) + list(r2.get("decisions") or [])
    out["compiles"] = int(res.get("compiles") or 0) + int(r2.get("compiles") or 0)
    out["seconds"] = round(float(res.get("seconds") or 0.0) + float(r2.get("seconds") or 0.0), 1)
    out["families"] = dict(res.get("families") or {}, **(r2.get("families") or {}))
    out["tools"] = list(res.get("tools") or []) + [f for f in r2.get("tools") or [] if f not in (res.get("tools") or [])]
    out["phases"] = res.get("phases")
    out["opt_stage"] = {"families": list(opt), "banked": banked, "stage": r2.get("stage"), "compiles": r2.get("compiles"),
                        "seconds": r2.get("seconds"), "phases": r2.get("phases"), "known_floor": bool(known),
                        "known_seconds": (known or {}).get(floor_sha, {}).get("seconds") if known else None}
    return out


def verified(res: dict) -> bool:
    ok = bool(res["verified"]) if "verified" in res else res.get("stage") not in (None, "unmeasured")
    return ok and isinstance(res.get("proof"), str) and bool(res["proof"].strip())


def normalize(name: str, decl: str, statement: str, log) -> tuple[str | None, dict]:
    """No normalizer in this pass (end_dialect runs it): (None, a short report)."""
    return None, {"status": "off"}
