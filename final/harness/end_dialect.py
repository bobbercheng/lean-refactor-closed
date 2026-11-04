#!/usr/bin/env python3
"""b102 end_dialect: a $0, model-free, accept-gated pass at the END of every row (after the end step and style_rw; router --end-dialect on).

What it runs on the row's final (router.final_of), in this order:
  1. dialect   harness/endstage.end_stage on that one proof with the deterministic dialect families only: "dialect" (harness/dialect.py,
               b98: compact-dialect rewrites of the proof's own text), "udialect" (harness/dialect_union.py, b102b: projtail, a flat
               destructuring pattern keeps its first names and the rest becomes one name used through numeric projections) and "unhyg"
               (harness/dialect_unhyg.py, b98: names Lean gives under `unhygienic`, a probe family: Lean is asked, nothing is guessed).
               No sweep, no crossover, k 0 (the pick reads the row's seed and the final, keeps the better on the paired rule; the final is
               a floor), a tool phase of SECONDS wall and COMPILES compiles, PASSES greedy passes while the incumbent changes, batch
               screening on. Every candidate is banked only through the end stage's own rule: paired scorer.accept.decide against the
               incumbent re-read right after it, then a confirmation on every pin. T4 is NOT run here (r10 already runs it; registering
               it would widen its probe for the run's other end stages in this process).
  2. normalize harness/normalize.normalize (the lexer normalizer: `fun`/`λ`, `$`, bare lambdas, `<|`, `;`; compile-verified with
               bisection, all pins, kept only when its score is higher) on step 1's output; skipped without a site (no compile).
  3. accept    the router's own check (router.end_dialect_step): the final and this pass's output back to back on the router's evaluator,
               every pin; adopted only when it reads strictly higher (end_guard ok and a positive same-meter delta; on the lake fallback
               meter: scorer.accept.decide on the end-stage meter's paired reading). The final then leaves on its stored scale plus that
               delta (as the end step and style_rw). Anything else, an exception included: the final stays byte-identical.
Generic by construction: every rule reads only the given proof's own text and the statement's own names and writes Lean core syntax; no
row names, lemma names, proof fragments or tables (leak scan: 0 hits). Off by default: the router imports this module only with the flag,
and config.json gets no "end_dialect" key without it."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STEP = "end_dialect"
FAMILIES = ("dialect", "udialect", "unhyg")
SECONDS = 600.0        # the tool phase's wall per row (also the pick's phase wall)
COMPILES = 400         # the tool phase's compiles per row (a batch screen file counts one)
PICK_COMPILES = 40     # the pick: the seed and the final on the primary pin, the better one's other pins
PASSES = 4             # greedy passes while the incumbent changes
CAPS = {"unhyg": 60}   # the probe family's compiles (its probe included)
CODE = ("harness/end_dialect.py", "harness/dialect.py", "harness/dialect_unhyg.py", "harness/dialect_union.py")


def register():
    """The pass's families in this process's harness.endstage (FAMILIES, PROBE_FAMILIES, CODE_FILES); idempotent; returns the module.
    T4's probe constants are left as they are (dialect.register(t4=False))."""
    from harness import dialect as D
    ES = D.register(t4=False)
    ES.FAMILIES.setdefault("udialect", {"module": "harness.dialect_union", "tier": 0})
    for f in CODE:
        if f not in ES.CODE_FILES:
            ES.CODE_FILES = tuple(ES.CODE_FILES) + (f,)
    return ES


def config(seconds: float = SECONDS, compiles: int = COMPILES) -> dict:
    """The pass's frozen settings (router config.json "end_dialect", written only when on)."""
    return {"families": list(FAMILIES), "seconds": float(seconds), "compiles": int(compiles), "pick_compiles": PICK_COMPILES,
            "passes": PASSES, "caps": dict(CAPS), "normalize": True}


def args_check(seconds, compiles) -> str | None:
    import math
    if not (isinstance(seconds, (int, float)) and math.isfinite(seconds) and seconds > 0):
        return f"--end-dialect-seconds {seconds}: a finite number of seconds > 0"
    if not (isinstance(compiles, int) and compiles >= 1):
        return f"--end-dialect-compiles {compiles}: an integer >= 1"
    try:
        register()
    except Exception as e:  # noqa: BLE001
        return f"--end-dialect on: the dialect families cannot be registered ({type(e).__name__}: {str(e)[:160]})"
    return None


def _floor(item: dict) -> dict:
    return {x: item[x] for x in ("proof", "score", "tokens", "heartbeats", "stage") if item.get(x) is not None}


def polish(row: dict, seed: str, cur: dict, meter, cfg: dict, log) -> dict:
    """Step 1: the end stage with the dialect families on the final (`cur`, the floor). Returns end_stage's result."""
    ES = register()
    return dict(ES.end_stage(row, seed, [], meter, k=0, sweep=False, crossover=False, max_compiles=int(cfg["pick_compiles"]),
                             checkpoint_bests={"final": _floor(cur)}, log=log, tools=tuple(cfg["families"]),
                             max_seconds=float(cfg["seconds"]), tools_max_compiles=int(cfg["compiles"]),
                             tools_max_seconds=float(cfg["seconds"]), passes=int(cfg["passes"]), family_caps=dict(cfg["caps"])) or {})


def verified(res: dict) -> bool:
    ok = bool(res["verified"]) if "verified" in res else res.get("stage") not in (None, "unmeasured")
    return ok and isinstance(res.get("proof"), str) and bool(res["proof"].strip())


def normalize(name: str, decl: str, statement: str, log) -> tuple[str | None, dict]:
    """Step 2: harness/normalize.normalize on `decl` -> (the improved proof or None, a short report). No site: no compile."""
    from harness import normalize as N
    from scorer.tokenize import split_declaration
    body = split_declaration(decl.rstrip(), statement)
    if body is None:
        return None, {"status": "statement differs"}
    if not N.sites(body):
        return None, {"status": "no sites", "compiles": 0}
    r = N.normalize(name, decl, log=lambda *a, **k: None)
    rep = {k: r.get(k) for k in ("status", "sites", "compiles", "applied", "gain", "before", "after") if r.get(k) is not None}
    out = r.get("proof") if r.get("status") == "improved" and isinstance(r.get("proof"), str) else None
    if out is not None and out.strip() == decl.strip():
        out = None
    log(f"end_dialect normalize: {rep.get('status')} ({rep.get('compiles', 0)} compiles)")
    return out, rep
