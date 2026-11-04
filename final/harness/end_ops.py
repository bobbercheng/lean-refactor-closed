#!/usr/bin/env python3
"""Bet D3 end_ops (docs/closed_plus5_per_problem.md, "End-stage ops"; bet-backend-replay 2026-11-02): a $0, model-free, accept-gated pass at
the END of every row (after the end step, style_rw and end_dialect; router --end-ops on), built like b102's end_dialect (harness/end_dialect.py).

What it runs on the row's final (router.final_of), in this order:
  1. polish   harness/endstage.end_stage on that one proof with the D3 families only: "grindmin" (harness/tools/d3_grind.py: a grind hint
              list's namespace form and ddmin's subsets / complements of the list) and "simpconst" (harness/tools/d3_simpconst.py: an
              anonymous-constructor literal in a simp-family lemma list replaced by a named constant that Lean, asked in the row's own
              environment, finds equal to it; an env query first, QUERY_FAMILIES). No sweep, no crossover, k 0 (the pick reads the row's seed
              and the final, keeps the better on the paired rule; the final is a floor), a tool phase of SECONDS wall and COMPILES compiles,
              PASSES greedy passes while the incumbent changes (ddmin's restart on the reduced list), batch screening on. Every candidate is
              banked only through the end stage's own rule: paired scorer.accept.decide against the incumbent re-read right after it, then
              a confirmation on every pin.
  2. accept   the router's own check (router.end_ops_step = the end_dialect step's code with this module): the final and this pass's output
              back to back on the router's evaluator, every pin; adopted only when it reads strictly higher. Anything else, an exception
              included: the final stays byte-identical.
Generic by construction: every rule reads only the given proof's own text and the row's own environment and writes Lean core syntax; no row
names, lemma names, proof fragments or tables. Off by default: the router imports this module only with the flag, and config.json gets no
"end_ops" key without it."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STEP = "end_ops"
FAMILIES = ("grindmin", "simpconst")
MODULES = {"grindmin": "harness.tools.d3_grind", "simpconst": "harness.tools.d3_simpconst"}
SECONDS = 600.0        # the tool phase's wall per row (also the pick's phase wall)
COMPILES = 300         # the tool phase's compiles per row (a batch screen file counts one; the env query counts one)
PICK_COMPILES = 40     # the pick: the seed and the final on the primary pin, the better one's other pins
PASSES = 6             # greedy passes while the incumbent changes (each re-runs ddmin's sequence on the reduced list)
CAPS = {"simpconst": 40}
CODE = ("harness/end_ops.py", "harness/tools/d3_grind.py", "harness/tools/d3_simpconst.py")


def register():
    """The pass's families in this process's harness.endstage (FAMILIES, QUERY_FAMILIES, CODE_FILES); idempotent; returns the module."""
    from harness import endstage as ES
    ES.FAMILIES.setdefault("grindmin", {"module": MODULES["grindmin"], "tier": 0})
    ES.FAMILIES.setdefault("simpconst", {"module": MODULES["simpconst"], "tier": 1})
    if "simpconst" not in ES.QUERY_FAMILIES:
        ES.QUERY_FAMILIES = tuple(ES.QUERY_FAMILIES) + ("simpconst",)
    for f in CODE:
        if f not in ES.CODE_FILES:
            ES.CODE_FILES = tuple(ES.CODE_FILES) + (f,)
    return ES


def config(seconds: float = SECONDS, compiles: int = COMPILES) -> dict:
    """The pass's frozen settings (router config.json "end_ops", written only when on)."""
    return {"families": list(FAMILIES), "seconds": float(seconds), "compiles": int(compiles), "pick_compiles": PICK_COMPILES,
            "passes": PASSES, "caps": dict(CAPS), "normalize": False}


def args_check(seconds, compiles) -> str | None:
    import math
    if not (isinstance(seconds, (int, float)) and math.isfinite(seconds) and seconds > 0):
        return f"--end-ops-seconds {seconds}: a finite number of seconds > 0"
    if not (isinstance(compiles, int) and compiles >= 1):
        return f"--end-ops-compiles {compiles}: an integer >= 1"
    try:
        register()
    except Exception as e:  # noqa: BLE001
        return f"--end-ops on: the D3 families cannot be registered ({type(e).__name__}: {str(e)[:160]})"
    return None


def _floor(item: dict) -> dict:
    return {x: item[x] for x in ("proof", "score", "tokens", "heartbeats", "stage") if item.get(x) is not None}


def polish(row: dict, seed: str, cur: dict, meter, cfg: dict, log) -> dict:
    """Step 1: the end stage with the D3 families on the final (`cur`, the floor). Returns end_stage's result."""
    ES = register()
    return dict(ES.end_stage(row, seed, [], meter, k=0, sweep=False, crossover=False, max_compiles=int(cfg["pick_compiles"]),
                             checkpoint_bests={"final": _floor(cur)}, log=log, tools=tuple(cfg["families"]),
                             max_seconds=float(cfg["seconds"]), tools_max_compiles=int(cfg["compiles"]),
                             tools_max_seconds=float(cfg["seconds"]), passes=int(cfg["passes"]), family_caps=dict(cfg["caps"])) or {})


def verified(res: dict) -> bool:
    ok = bool(res["verified"]) if "verified" in res else res.get("stage") not in (None, "unmeasured")
    return ok and isinstance(res.get("proof"), str) and bool(res["proof"].strip())


def normalize(name: str, decl: str, statement: str, log) -> tuple[str | None, dict]:
    """No normalizer in this pass (end_dialect runs it): (None, a short report)."""
    return None, {"status": "off"}
