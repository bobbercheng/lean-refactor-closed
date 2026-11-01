#!/usr/bin/env python3
"""Router v2.2 (docs/router_v2.md; 2026-10-18): a per-row policy over the existing stages, inside the hard per-row cap.

  per checkpoint k (--checkpoints, default $1.25, $1.90):
  Lk      the Sol budget ladder (harness/hx_heldout.py, the arm's own flags via --ladder-args) fills the active rows to checkpoint k
  CLEAN   $0: postpass free, rules, oracle on the active rows; a gain is written back to the ladder's work root (adopt guard: > best +
          min gain), so the next ladder session resumes the cleaned proof
  GATE    one decision per row and checkpoint, measured numbers only (score, spend, the ladder's last session gain), persisted once in
          decisions.jsonl (a resume never re-decides):
            room = target x cap - review reserve - spend   (b65 defaults: 1.0 x $3.00 - $0.25)
            room < session floor                                  -> none    (review only)
            G >= gate (85), or L-bound (H >= 90 and L <= 75),
              or still climbing (last session gain >= 1.0),
              or room < the re-plan minimum                       -> ladder  (stays active: the next checkpoint, then the top)
            otherwise (low and flat)                              -> replan  (one Sol re-plan session from the current best: restructure
                                                                              brief, high effort, budget = room; --twins: two half-budget
                                                                              sessions from the same start, the better one kept)
          2026-10-18 replay of the deployable run (wuclean-hx-solab1): at $1 the ladder still gained 1.4-4.5 per session on 4 of the 5
          rows below 85 (up to +8.6 to the end); a score-only gate would have re-planned them. Only one was flat.
  TOP     rows still on the ladder after the last checkpoint: hx_heldout continues them to target x cap - reserve (--target-frac:
          default 1.0 since b65 (2026-10-26: the whole cap, made safe by mechanisms, not margins; 1.0 approved 2026-10-22): the
          default --cap $3.00 x 1.0 = $3.00 - review reserve $0.25 = ladder top $2.75; the review's room = $3.00 - the row's spend - $0.001
          (>= $0.2490 for a row at the top); was 0.90 (top $2.45))
  REPLAN  replan rows: the postpass replan stage (a seeded work root inside the arm's worktree; in the arm's container when it has one)
  CLEAN2  $0 again on every row a paid tier changed
  REVIEW  Argon medium multi-round review (3 rounds x 5 edits) on every row, budget cap - spend - SPEND_MARGIN rounded down (b64 L0,
          --review-budget room: the row's whole room under the cap, at least the reserve the ladder top leaves; `reserve` = the pre-L0
          min(reserve, ...)); never routed away. Every review call is priced at its worst case (input uncached + its output cap) at the CAP
          price (b64 L0, --cap-price announced: Argon at its announced $4 / $20, agent.cap_prices; `list` = the metered table) before it is
          sent and shrunk or skipped when it would not fit (harness/review.py), so spend <= cap holds with no headroom (target 1.0) at the
          list price and at the announced one. Spend is REPORTED at the list table (finals, summary); the row ledger, which every gate reads
          (decide(), the routed slices, the review budget), holds the Argon calls at the cap price
  TAIL    --tail-preset P (b68, docs/b68_tail.md; off by default, frozen): after every row's review, rows whose room under the cap (cap -
          metered spend at the cap price - $0.001) is at least --tail-min-room and P's session floor run agent.py sessions of P in their own
          work root from their current best (hx_heldout --tail; each session's --budget-usd = the row's state spend + that room, so the
          existing worst-case pre-call gate keeps the row under the cap); the work root's new best enters the row only when it is better back
          to back on every pin (step `tail`); then the end stage. A pin of P: b66's fallback, else the tail stops at $0
  END     --end-stage (B62b, docs/scaffold_panel.md "Rulings"; off by default, frozen; runs started before the option keep it off): $0 on
          every row after the review. harness/endstage.py (imported only with the flag) collects the row's distinct proofs (seed, every
          step's output, the run's pool.jsonl: the arm's work root and every re-plan root), re-measures the top --end-k and the floors
          (the best after each checkpoint cleanup and the review output) back to back on one meter (the direct path; a self-test per
          (source, pin) and a whole-run fallback to the lake path inside endstage.Meter), sweeps and crosses them over, banks with
          scorer/accept.decide. Its verified output is the row's final when the router's evaluator, reading it and the review output back
          to back on every pin, does not find it lower by more than the meter's spread (HB_EPS heartbeats); else the review output stays.
          The fold's 0.05 comparison is not used here: it would compare readings from different meters. A finished end step never re-runs.
  OUT     <run>/finals.json (best verified proof per row + spend), summary.json, rows/<ws>.json (every step), decisions.jsonl, router.log,
          submission.jsonl ({"name", "proof"} per row, the upload format) + submission_check.json (harness/final_writer.py)
  ALWAYS  (b65-final, audit C1 + C2; 2026-10-27 no-harm rule) submission.jsonl exists from the start (every row's seed proof), is
          updated per row (checkpoint cleanups, each finished row), and main's finally writes finals.json (when the run did not get to OUT)
          and submission.jsonl again on EVERY exit path: normal end, a short stop (exit 3), a confirmed pin, an exception, SIGTERM (exit 143).
          Per row: the best candidate that passes the static checks and compiles on every pin, else the seed (a timed-out compile is retried
          once, never a demotion). A short stop still keeps its resume contract (no recorded step runs: a restart re-runs that ladder phase).
  PIN     (b65-final, audit C3) a ladder phase that exits agent.PIN_FATAL_RC (a CONFIRMED max_price pin of the line's Sol preset; one pin
          error is retried at $0 by the session, harness/pinwatch.py) starts no further paid session: no later ladder phase, re-plan, twin or
          review; the run finishes on its $0 path (cleanups, crossover, end stage on every row's best), writes every output and exits
          PIN_STOP_RC (79; summary.json "exit" and "pin_unservable" explain it). Persisted in <run>/pin_stop.json: a restart stays on the $0
          path. A confirmed pin of the REVIEW preset (Argon, in this process) skips that row's review at $0 (review spend 0, not the budget),
          the run goes on and exits as usual; summary.json flags it (pin_unservable, pin_review_skipped).
          b66 (retro A3, docs/b66_robust.md): the $0 path only when NO ladder preset is left: a confirmed pin of one ladder preset while
          another OpenRouter session preset of the run still answers (--preset-by-rung's Sol-main <-> Terra-main, or --pin-fallback-preset)
          re-runs that phase with every session of the pinned preset on the other one (hx_heldout --preset-fallback; gated at its own cap
          price); recorded in pin_fallback.json, decisions.jsonl (kind pin-fallback) and summary.json. The review likewise continues on
          --review-fallback-model (when set) after a confirmed pin of the review preset, else skips at $0 as above.

GUARD   (lever 2, 2026-10-22) a "-clean" set's --ladder-args must carry the final pipeline's measured ladder flags, --no-lineage-rule
          and --rescue 0 (as hx_heldout parses them); otherwise the router refuses before any spend, unless --allow-lineage-rule.
REAP    (b67, docs/b67_final.md section 4) nothing the router started outlives it. scorer.memgate starts every Lean compile in its own
          session, so no process-group signal reaches one, and a compile whose holder died ran on with no timeout and outside the memory
          gate. Every process of this invocation carries REAP_ENV=<tag> (inherited through fork and exec: the ladder, its sessions' docker
          clients, every compile, the end stage's workbench); on every exit path, after the outputs, compile admission is closed for this
          process (memgate CLOSED_ENV), steps finished from then on are not recorded (a restart re-runs them), every tagged process gets
          SIGTERM and, after REAP_GRACE_S, SIGKILL, and (SIGTERM, an exception, or something was still running) this arm's session
          containers still running are stopped. A ladder phase that hits
          --ladder-timeout is stopped the same way (its own LADDER_REAP_ENV tag: SIGTERM, LADDER_STOP_GRACE_S, SIGKILL) instead of a
          SIGKILL of hx_heldout alone, which left its sessions running in their containers; so is what a phase whose hx_heldout ended on
          its own (a crash, an OOM kill) left running (b67 review). After an exception the command line ends at once, as on SIGTERM
          (_entry), and a workbench restart starts no Lean once admission is closed (harness/workbench.py).

Modes: --set/--arm (an hx_heldout arm: the work root holds best + api_spend per row; all tiers) or --input finals.json (rows carrying
proof/score/spend; no ladder tiers: ladder decisions become none). --dry-run: no model call anywhere (ladder phases skipped, replan and
review stubbed): the $0 path end to end. Resumable at step granularity. Compiles go through scorer.compile (memgate-admitted): run it in a
memory-capped unit, never from an interactive shell.
    python3 harness/router.py --set warmup-clean --arm rtr1 --run-dir probe/router/<tag> --ladder-args "<the arm's hx_heldout flags>"
    python3 harness/router.py --input finals.json --run-dir probe/router/<tag> [--dry-run] [--end-stage [--end-k 6 --end-max-compiles 60]]
"""
from __future__ import annotations

import argparse, importlib, inspect, json, math, os, re, shlex, signal, subprocess, sys, threading, time, traceback, types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(1, str(ROOT / "harness"))
from harness import postpass as P  # noqa: E402
from harness import leantools as LT  # noqa: E402
from scorer.accept import HB_EPS, exact_score  # noqa: E402
from scorer.score import hb_pct_local, len_pct, local_reference_heartbeats  # noqa: E402

POLICY = "router-v2.2"       # the policy string of the v2.2 gate (decide(policy=POLICY_V22)); v3 runs write POLICY_V3
POLICY_V22, POLICY_V3 = "router-v2.2", "router-v3"
# b63 launch set item 2 (docs/adaptive_plan_93.md §1.4-1.5, G1 replay probe/b63/dxr/G1.json): plateau = spend >= 0.75 and gain[-1] < 0.30 and
# gain[-2] < 1.0 and cpu_gain < 0.05. It decides ORDER (an artifact route first when one exists), never forbids later ladder spend: after the
# fire the v2 ladder still gained 0.36/cell (10.9 points over 30 cells), so a "stop" rule would forfeit that.
PLATEAU_SPEND, PLATEAU_G1, PLATEAU_G2, PLATEAU_CPU = 0.75, 0.30, 1.0, 0.05
NO_CANDIDATE = 60.0          # a measured score below this means no compiling candidate of the model's own yet (seed-level, plan §1.4)
FLEX_SCORE = 90.0            # flex (plan §1.1 F): a plateaued row at or above this leaves the rest unspent; below it the ladder continues
V3_CHECKPOINTS = (0.75, 1.00, 1.25, 1.60, 1.90)   # the finer gate schedule of the v3 policy (plan §1.5)
KINDS = ("ladder-continue", "bank", "repair", "artifact-session", "polish-only", "unspent", "replan", "twin", "select", "none")   # decision kinds (contract §2)
# b63 item 17 (plan §1.1 F, §1.2, §4.1 item 17; PB3-G3): twins. At the flex point (last checkpoint, plateau, G < FLEX_SCORE) a c6 row
# (reference proof < C6_REF_TOKENS tokens and the row's ladder sessions cost <= C6_SESSION each) or a row whose bank already holds a compiling
# candidate of ANOTHER structural class within TWIN_WITHIN of the best (diverse_of: the runner-up SELECT would keep) splits the remaining room
# between two lineages from the same checkpoint best B0: the ladder lineage (its work root, with its history) up to a lower top, and a twin
# (postpass.seed_workspace: a fresh work root whose stored best is B0, no history) with the other half. One shared ledger per row (RowLedger);
# SELECT after both: the best lineage goes on, the runner-up is kept (as a row step, so the crossover and the end stage see it as a parent)
# only if within TWIN_WITHIN points and of a different class.
# Off by default (--twins; the PB3-G3 pilot, probe/b63/g3_twins.md, decides whether it becomes default).
C6_REF_TOKENS, C6_SESSION = 80, 0.20
TWIN_WITHIN = 1.0
TWIN_ARGS = "--reasoning-effort medium --max-tokens 4000 --pattern-cards --budget-reclaim --name-neighbors --pool"   # the v3 ladder session's agent.py flags
TWIN_TURNS = 40          # as the ladder's sessions (hx_heldout.session_cmd --turns 40)
GATE = 85.0            # tier-0/1 measured score below which a row is in the structural regime (docs/router_v2.md §3; refit on sealed sets)
TARGET_FRAC = 1.0      # 2026-10-18: spend up to ~90% of the cap (score over cost); the cap stays hard. 2026-10-22: 1.0 approved
                       # (the ladder top lifted to cap - reserve; the review no longer needs the headroom: each call is priced before it is sent).
                       # b65 (2026-10-26, use the whole cap): 1.0 is the default (was 0.90)
REVIEW_RESERVE = 0.25  # Argon review, reserved on every row (each call's worst case, input included, fits what is left of it: harness/review.py)
SPEND_MARGIN = 0.001   # 2026-10-22: kept off the review budget against the 4-decimal rounding of recorded spends along a row's steps (<= $0.00005 each)
REVIEW_MAX_TOKENS = 16000   # 2026-10-19: one review call's worst case (cap x output price, $0.16 for Argon) must fit the reserve; at the
                            # 32k default it was $0.32 > $0.25 and every review was skipped (measured calls cost ~$0.04)
# b64 L0 (cap safety; docs/plateau_levers.md section 2): the review's budget is the row's room under the cap ("room"), not min(reserve, room)
# ("reserve", the pre-L0 rule), and every paid Argon call (review, REPAIR) is gated at the announced price ("announced"; "list" = pre-L0).
REVIEW_BUDGET_MODES = ("room", "reserve")
CAP_PRICE_MODES = ("announced", "list")


def review_budget_usd(cap: float, spend: float, reserve: float, mode: str = "room") -> float:
    """The review's dollar budget (cap-price dollars) for a row whose ledger holds `spend`: rounded DOWN to 1e-4 with SPEND_MARGIN under the
    cap, so spend + budget <= cap - SPEND_MARGIN. mode room (b64 L0): all of the room; reserve: at most `reserve` (the pre-L0 rule)."""
    if mode not in REVIEW_BUDGET_MODES:
        raise ValueError(f"review budget mode {mode!r}: one of {REVIEW_BUDGET_MODES}")
    left = cap - float(spend or 0) - SPEND_MARGIN
    return math.floor((left if mode == "room" else min(reserve, left)) * 1e4) / 1e4


def cap_arithmetic(cap: float, frac: float, reserve: float, top: float, budget_mode: str = "room") -> str:
    """b65 (4): the router's start line deriving the ladder top and the review's budget from --cap (the arithmetic the gates use)."""
    at_top = review_budget_usd(cap, top, reserve, budget_mode)
    return (f"cap ${cap:.2f} x target {frac:g} = ${cap * frac:.2f}; - review reserve ${reserve:.2f} = ladder top ${top:.2f}; review budget "
            + (f"= cap - row spend - ${SPEND_MARGIN:g} margin, rounded down to 1e-4 (a row at the top: ${cap:.2f} - ${top:.2f} - ${SPEND_MARGIN:g} = "
               f"${at_top:.4f})" if budget_mode == "room" else f"= min(reserve, cap - row spend - ${SPEND_MARGIN:g}) (a row at the top: ${at_top:.4f})"))


MIN_REPLAN = 0.50      # a re-plan session below this is not worth starting (Sol, 40 turns: ~$0.5-1.2 measured)
SESSION_FLOOR = 0.30   # hx_heldout.SESSION_FLOOR: no session starts with less left
# b65-final (audit C3): the router's exit after a CONFIRMED max_price pin of the ladder's preset stopped every paid step and the run finished on
# its $0 path (outputs complete; the ladder's own code is agent.PIN_FATAL_RC = 78); SIGTERM (systemd stop, a kill): outputs written, then 143
PIN_STOP_RC, TERM_RC = 79, 143
PIN_STOP_FILE = "pin_stop.json"
CLIMB = 1.0            # a ladder whose last session gained this much is still climbing: keep it (the re-plan must beat the ladder)
CHECKPOINTS = (1.25, 1.90)
ROUTE_BUDGET = 0.50       # b63 item 16 (plan §1.1 P): one routed step (REPAIR or ARTIFACT-SESSION) <= $0.50
ROUTE_SECOND_GAIN = 0.30  # a second routed step only if the first banked >= this ...
ROUTE_SECOND_ROOM = 0.55  # ... and this much room is left (plan §1.2)
REPAIR_STEPS = 10         # REPAIR: <= 10 steps, stop after 2 dry (harness/repair.py)
ARTIFACT_TURNS = 14       # ARTIFACT-SESSION: <= 12-16 turns (agent.py --artifact caps at 16)
# review 2026-10-25: the ARTIFACT-SESSION's agent.py flags = the v3 ladder's per-session flags (hx_heldout.session_cmd effort/max-tokens +
# probe/b63/v3_config.md --agent-*), NOT the open-ended re-plan's REPLAN_ARGS: its `--brief restructure` (SCOUT C: change the architecture)
# contradicts a session that must fill the shown artifact's holes; the G8 pilot (probe/b63/g8_pilot.py) runs both of its Sol arms with these
ARTIFACT_ARGS = "--reasoning-effort medium --max-tokens 4000 --pattern-cards --name-neighbors --pool --budget-reclaim"
REPAIR_RUNNER = None      # tests inject a fake REPAIR (name, best, route, budget, log) -> harness.repair.run_repair's dict; None = the real loop
LBOUND_H, LBOUND_L = 90.0, 75.0   # L-bound rows: the heavy tier bought exactly 0.0; micro-levers won
CLEAN_STAGES = ["free", "rules", "oracle"]
# 2026-10-19 (speed): checkpoint cleanups run only the high-yield free passes (Stage 2 logs: hb_rewrite improved 46% of runs,
# normalize 38%, hb_tool 18%; lint_delete 9%, hb_preorder 7%, hb_polish 4% for 12.6 h of 19); the full chain runs once per row, at the end
CHECKPOINT_FREE_PASSES = ("normalize", "hb_rewrite", "hb_tool")
CLEAN_DEADLINE_S = P.build_parser().get_default("deadline_s")   # L5: the cleanups' rules-stage wall limit (postpass's default, 1800 s)
LEGACY = {"fast_checkpoint_cleanup": False, "rules_exclude": [], "end_stage": False, "routes": False,   # run dirs whose frozen config predates an option
          "gate_policy": "v2.2", "cross": False, "flex": False, "twin_args": TWIN_ARGS, "twin_turns": TWIN_TURNS,
          "review_budget": "reserve", "cap_price": "list", "clean_deadline_s": CLEAN_DEADLINE_S,
          "end_dual_start": False, "sweep_before_review": False, "stop_at": None,   # b65
          "review_fallback_model": None, "pin_fallback_preset": None}   # b66 (A3)
                                                                                           # keep the old behaviour on resume
CLEAN2_STAGES = ["free", "rules"]
REPLAN_ARGS = "--brief restructure --reasoning-effort high --max-tokens 8000 --pattern-cards"
ITEM_KEYS = ("proof", "score", "tokens", "heartbeats", "L", "H", "Z", "compat", "verified", "stage")
END_K = 6               # B62b end stage: candidates re-measured besides the seed and the floors (endstage.K)
END_MAX_COMPILES = 60   # B62b end stage: compiles per row, the run-start self-test excluded (endstage.MAX_COMPILES)
CHECKPOINT_STEP = re.compile(r"clean@\d+$")   # the row's best after each checkpoint cleanup is a floor of the end stage
POOL_FILES = ("pool.jsonl", "bank.jsonl")   # per row: the run pool (agent.py --pool) and the bank (harness/bank.py, b63 item 1)


def safe(n: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", n)


def masker(names, tags):
    """2026-10-19 (exposure: a review line carried a sealed name truncated differently from the 40-char prefix the old anonymizer
    replaced): every token that starts with a name's first 16 characters, or equals a distinctive last component, becomes its tag."""
    pats = []
    for n in sorted(names, key=len, reverse=True):
        t = tags[n]
        pats.append((re.compile(re.escape(n[:16]) + r"[^\s:,()\[\]]*"), t))
        last = n.split(".")[-1]
        if len(last) >= 10:
            pats.append((re.compile(r"(?<![\w.])" + re.escape(last[:10]) + r"[^\s:,()\[\]]*"), t))

    def mask(m: str) -> str:
        for p, t in pats:
            m = p.sub(t, m)
        return m
    return mask


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ladder_flag_problems(A) -> list[str]:
    """Lever 2 guard (2026-10-22; docs/distill_to_tools.md): the final pipeline's measured ladder runs with --no-lineage-rule and --rescue 0
    (no fresh lineages, no rescue; no twins and no re-plan are router flags). The arm's --ladder-args are read by hx_heldout's own parser,
    after the --set/--arm the router passes first, exactly as ladder() hands them over (abbreviations, repeats and the last value win as
    there). Returns what is off the measured pipeline; [] when it matches."""
    import hx_heldout as H
    hp = H.build_parser()

    def _refuse(msg):
        raise ValueError(msg)
    hp.error = _refuse
    try:
        ns, _ = hp.parse_known_args(["--set", A.set, "--arm", A.arm or "-", *shlex.split(A.ladder_args or "")])
    except (ValueError, argparse.ArgumentError) as e:
        return [f"--ladder-args cannot be read by hx_heldout ({e})"]
    out = []
    if ns.lineage_rule:
        out.append("the lineage rule is on (hx_heldout's default; pass --no-lineage-rule)")
    if ns.rescue > 0:
        out.append(f"--rescue {ns.rescue} > 0")
    return out


def ladder_rungs_override(A) -> str | None:
    """2026-10-23 (b62-v2 review): ladder() passes the router's --rungs (checkpoints + top) BEFORE --ladder-args, so a --rungs (or an
    abbreviation of it) inside --ladder-args would win in hx_heldout's parser and fill rows past the top (cap - review reserve), the review
    then landing on top of that. Returns the overriding value, or None."""
    import hx_heldout as H
    hp = H.build_parser()
    hp.set_defaults(rungs=None)

    def _refuse(msg):
        raise ValueError(msg)
    hp.error = _refuse
    try:
        ns, _ = hp.parse_known_args(["--set", A.set, "--arm", A.arm or "-", *shlex.split(A.ladder_args or "")])
    except (ValueError, argparse.ArgumentError):
        return None   # unreadable --ladder-args: the ladder's own parser refuses them before any session
    return ns.rungs


def ladder_first_session(A) -> dict | None:
    """b64 planner (T2, docs/first_half_gap.md section 6.2): the first-session flags inside --ladder-args (hx_heldout --first-preset /
    --first-effort / --first-budget), read by hx_heldout's own parser as ladder_flag_problems reads them: {"preset", "effort" (the first
    session's effective effort), "budget"}, or None. Frozen in config.json as `first_session` (written only when set; absent = None): a
    resume whose --ladder-args change them is refused."""
    if not A.set:
        return None
    import hx_heldout as H
    hp = H.build_parser()

    def _refuse(msg):
        raise ValueError(msg)
    hp.error = _refuse
    try:
        ns, _ = hp.parse_known_args(["--set", A.set, "--arm", A.arm or "-", *shlex.split(A.ladder_args or "")])
    except (ValueError, argparse.ArgumentError):
        return None   # unreadable --ladder-args: the ladder's own parser refuses them before any session
    if not getattr(ns, "first_preset", None):
        return None
    return {"preset": ns.first_preset, "effort": ns.first_effort or ns.effort, "budget": ns.first_budget}


def ladder_preset_by_rung(A) -> dict | None:
    """b65 steps (T3-T5, probe/b65/steps_tests.md): hx_heldout --preset-by-rung inside --ladder-args, read by hx_heldout's own parser as
    ladder_first_session reads the first-session flags: {"R.RR": {"preset", "effort" (effective)}}, or None. Frozen in config.json as
    `preset_by_rung` (written only when set; absent = None): a resume whose --ladder-args change it is refused."""
    if not A.set:
        return None
    import hx_heldout as H
    hp = H.build_parser()

    def _refuse(msg):
        raise ValueError(msg)
    hp.error = _refuse
    try:
        ns, _ = hp.parse_known_args(["--set", A.set, "--arm", A.arm or "-", *shlex.split(A.ladder_args or "")])
        m = H.rung_presets(ns.preset_by_rung)
    except (ValueError, argparse.ArgumentError):
        return None   # unreadable --ladder-args: the ladder's own parser refuses them before any session
    return {f"{R:.2f}": {"preset": P, "effort": E or ns.effort} for R, (P, E) in sorted(m.items())} or None


def stop_out(A, S, names: list, at: float, say) -> int:
    """b65 steps (--stop-at): the run ends where its ladder reached `at` (a checkpoint: before that checkpoint's $0 step and gate; the top:
    before the re-plan, clean2, cross, review and end stage). finals.json = each row's work-root best and spend there (the ladder's own
    item); summary.json carries `stopped_at` and the spend at the cap price (state.json cap_extra). Exit 1 when a row passed `at` there."""
    items = work_root_items(S, names)
    out = {n: {k: v for k, v in items[n].items() if k not in ("state_path", "seed")} for n in names}
    (A.run_dir / "finals.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    capx = {n: round(float(out[n].get("spend") or 0) + state_cap_extra(items[n].get("state_path")), 6) for n in names}
    sc = {n: float(out[n].get("score") or 33.33) for n in names}
    over = [n for n in names if capx[n] > at + 1e-9]
    summ = {"stopped_at": at, "rows": len(names), "at": now(), "mean_final": round(sum(sc.values()) / max(1, len(names)), 3),
            "spend_max": max([float(out[n].get("spend") or 0) for n in names] or [0]), "cap_spend_max": max(capx.values() or [0]),
            "over_at_cap_price": over, "per_row": {n: {"final": out[n].get("score"), "spend": out[n].get("spend"), "cap_spend": capx[n],
                                                       "inherited": (RowStore(A.run_dir, n).d.get("start_from") or {}).get("inherited")}
                                                   for n in names},
            "start": {"source": A.start_from, "start_at": A.start_at, "item": A.start_item, "history": A.start_history,
                      "start_sha": A.start_sha} if A.start_from else None}
    (A.run_dir / "summary.json").write_text(json.dumps(summ, indent=1))
    say(f"stopped at ${at:.2f} (--stop-at): mean {summ['mean_final']} over {len(names)} row(s); spend max ${summ['spend_max']:.2f}, at the cap "
        f"price ${summ['cap_spend_max']:.2f}" + (f"; PAST ${at:.2f} AT THE CAP PRICE {over}" if over else ""))
    return 1 if over else 0


def state_cap_extra(state_path) -> float:
    """b64 planner: the arm's state.json cap_extra (an hx_heldout --first-preset first session's cap-price difference, agent.py b64 L0); 0
    without a state or the key."""
    try:
        return float(json.loads(Path(state_path).read_text()).get("cap_extra") or 0) if state_path else 0.0
    except (OSError, ValueError, AttributeError):
        return 0.0


def ladder_cap_extra(led: "RowLedger", state_path) -> None:
    """b64 planner: the ladder's cap-price difference into the row ledger (label cap_extra:ladder) next to its `sessions` spend, so decide(),
    the routed slices, the review budget and the summary's cap_spend see the row at the cap price; no label (the ledger as before) without."""
    cx = state_cap_extra(state_path)
    if cx > 0:
        led.set("cap_extra:ladder", cx)


# ------------------------------------------------------------------------------------------------------------------------- the gate
def plateau_of(spend, gains, cpu_gain) -> dict:
    """The plateau flag and its inputs (plan §1.5; G1 replay): gains = the ladder's per-session gains on this row (hx_heldout lineage.json,
    sessions under $0.05 already left out), cpu_gain = what the checkpoint's CPU pass banked. A row without a session gain is never on a
    plateau (no evidence); a single gain leaves gain[-2] open (counted as satisfied)."""
    g = [float(x) for x in (gains or []) if x is not None]
    g1 = g[-1] if g else None
    g2 = g[-2] if len(g) >= 2 else None
    cg = float(cpu_gain or 0.0)
    fired = (float(spend or 0) >= PLATEAU_SPEND - 1e-9 and g1 is not None and g1 < PLATEAU_G1 and (g2 is None or g2 < PLATEAU_G2)
             and cg < PLATEAU_CPU)
    return {"plateau": bool(fired), "gain1": g1, "gain2": g2, "cpu_gain": round(cg, 4)}


def decide(G, L, H, spend, *, cap, frac=TARGET_FRAC, reserve=REVIEW_RESERVE, gate=GATE, min_replan=MIN_REPLAN, floor=SESSION_FLOOR,
           twins=False, ladder=True, last_gain=None, climb=CLIMB, dead=None, replan=True, policy=POLICY_V22, gains=None, cpu_gain=None,
           artifact=None, final=False, flex=True, c6=None, diverse=False) -> dict:
    """Pure: measured inputs only (scores, spend, the ladder's session gains, the CPU pass's gain; never model text). Returns the tier
    (ladder | replan | none: what the rest of the router executes), its budget, and (b63) the decision `kind` (KINDS), the plateau flag
    and a reason string; every call is one decisions.jsonl line (contract §2). `spend` is the row's shared ledger (all sessions).
    policy=POLICY_V22: the 2026-10-18 gate (saturated / L-bound / climbing / re-plan when low and flat).
    policy=POLICY_V3 (plan §1.4-1.5): no open-ended re-plan (measured -0.42/row). ladder-continue while gain[-1] >= 0.30, or the CPU pass
    banked >= 0.05, or no compiling candidate yet (G < 60), or the plateau rule is off; on a plateau the order changes: an artifact route
    (`artifact` = {"kind": "repair" | "artifact-session", ...}, a compiled artifact with holes or a near-miss; none exist in the v3 launch
    set, item 16 is v4) would run first, else the ladder continues (reorder only, never stop); at the last checkpoint (`final`) the flex
    rule: a plateaued row at or above FLEX_SCORE leaves the rest unspent, below it the ladder continues. Budgets never pass the target.
    `dead` (the seed's auto-brief found no paying single edit) is recorded for the threshold fit, not used.
    b63 item 17: with `twins` (v3), at the flex point where the ladder would continue (final, plateau, G < FLEX_SCORE) a `c6` row or a row
    with a structurally different compiling candidate within 1.0 of the best (`diverse`, diverse_of) and room for two sessions gets kind
    "twin": tier "twin", `twin_budget`
    (floor of half the room, 4 decimals) for the twin session and `ladder_top` (the rest, floored to a cent) for the ladder lineage, so both
    together never pass the target (test_budget_cap.LedgerTests).
    b64 L0: `spend` is the row ledger at the CAP price (Argon review / REPAIR calls at their announced price, agent.cap_prices), so every
    budget here is sized against what the row could be billed at that price; `reserve` is the room left under the target for the review,
    which main() checks can hold at least one review call at the cap price (the startup check)."""
    target = round(cap * frac, 4)
    room = round(target - reserve - float(spend or 0), 4)
    if gains is None and last_gain is not None:
        gains = [last_gain]
    pl = plateau_of(spend, gains, cpu_gain)
    if last_gain is None and gains:
        last_gain = pl["gain1"]
    inputs = dict(G=G, L=L, H=H, spend=round(float(spend or 0), 4), cap=cap, target=target, reserve=reserve, room=room, gate=gate,
                  min_replan=min_replan, twins=twins, last_gain=last_gain, climb=climb, dead=dead, gain1=pl["gain1"], gain2=pl["gain2"],
                  cpu_gain=pl["cpu_gain"], plateau=pl["plateau"], artifact=(artifact or {}).get("kind") if artifact else None, final=bool(final),
                  c6=c6, diverse=bool(diverse))

    def out(tier, reason, budget=0.0, sessions=0, kind=None):
        kind = kind or {"ladder": "ladder-continue", "replan": "replan", "none": "polish-only"}[tier]
        return dict(policy=policy, tier=tier, kind=kind, plateau=pl["plateau"], reason=reason, budget=round(max(0.0, budget), 4),
                    sessions=sessions, inputs=inputs)
    if room < floor:
        return out("none", f"room ${room:.2f} < session floor ${floor:.2f}", kind="polish-only")
    if policy == POLICY_V3:
        why = None
        if G is not None and G >= gate:
            why = f"saturated: G {G:.2f} >= gate {gate:g}"
        elif H is not None and L is not None and H >= LBOUND_H and L <= LBOUND_L:
            why = f"L-bound: H {H:.1f} >= {LBOUND_H:g} and L {L:.1f} <= {LBOUND_L:g}"
        elif not pl["plateau"]:
            if pl["gain1"] is None:
                why = "no session gain recorded yet" if float(spend or 0) >= PLATEAU_SPEND else f"spend ${float(spend or 0):.2f} < ${PLATEAU_SPEND:.2f}"
            elif float(spend or 0) < PLATEAU_SPEND:
                why = f"spend ${float(spend or 0):.2f} < ${PLATEAU_SPEND:.2f}: common ladder"
            elif pl["gain1"] >= PLATEAU_G1:
                why = f"still climbing: last session +{pl['gain1']:.2f} >= {PLATEAU_G1:g}"
            elif pl["gain2"] is not None and pl["gain2"] >= PLATEAU_G2:
                why = f"an earlier session gained +{pl['gain2']:.2f} >= {PLATEAU_G2:g}"
            else:
                why = f"CPU pass banked +{pl['cpu_gain']:.2f} >= {PLATEAU_CPU:g} at this checkpoint"
            if G is None or G < NO_CANDIDATE:
                why += "; no compiling candidate of its own yet" if G is not None else "; no measured score yet"
        if why is not None:
            return out("ladder", why, room, 1) if ladder else out("none", why + " (no ladder in this mode)", kind="polish-only")
        # plateau: reorder (artifact route first), never stop
        if artifact and (artifact.get("kind") in ("repair", "artifact-session")) and room >= min_replan:
            return out("replan", f"plateau (gain[-1] +{pl['gain1']:.2f}, gain[-2] " + ("none" if pl["gain2"] is None else f"+{pl['gain2']:.2f}")
                       + f", cpu +{pl['cpu_gain']:.2f}): {artifact['kind']} route first", min(room, 1.0), 1, kind=artifact["kind"])
        base = (f"plateau (gain[-1] +{pl['gain1']:.2f}, gain[-2] " + ("none" if pl["gain2"] is None else f"+{pl['gain2']:.2f}")
                + f", cpu +{pl['cpu_gain']:.2f}), no artifact route")
        if final and flex and G is not None and G >= FLEX_SCORE:
            return out("none", base + f": flex unspent (G {G:.2f} >= {FLEX_SCORE:g})", kind="unspent")
        # review 2026-10-25: plan §1.4 lists "no compiling candidate yet (G < 60)" under ladder-continue, ahead of the flex rule: no twin there
        if final and flex and twins and ladder and G is not None and G >= NO_CANDIDATE and (c6 or diverse) and room >= 2 * floor - 1e-9:
            tb = math.floor(room / 2 * 1e4) / 1e4                       # the twin's session budget
            lt = math.floor((target - reserve - tb) * 100) / 100         # the ladder lineage's top (absolute rung): ladder + twin <= target - reserve
            d = out("twin", base + f": flex twin (G {G:.2f} < {FLEX_SCORE:g}; " + ("c6: short reference, cheap sessions" if c6 else "a compiling candidate of another class in the bank")
                    + f"): ladder lineage to ${lt:.2f} + twin ${tb:.4f} from the checkpoint best", room, 2, kind="twin")
            return d | {"twin_budget": tb, "ladder_top": lt}
        why = base + (f": flex, ladder continues (G {G:.2f} < {FLEX_SCORE:g})" if final and G is not None else ": reorder only, ladder continues")
        return out("ladder", why, room, 1) if ladder else out("none", why + " (no ladder in this mode)", kind="polish-only")
    if not replan:   # 2026-10-18 (set #3 panel): the A/B control arm; --gate 0 alone let a row with no measured score (G None) re-plan
        why = "re-plan disabled (control arm)"
    elif G is not None and G >= gate:
        why = f"saturated: G {G:.2f} >= gate {gate:g}"
    elif H is not None and L is not None and H >= LBOUND_H and L <= LBOUND_L:
        why = f"L-bound: H {H:.1f} >= {LBOUND_H:g} and L {L:.1f} <= {LBOUND_L:g}"
    elif last_gain is not None and last_gain >= climb:
        why = f"still climbing: last session +{last_gain:.2f} >= {climb:g}"
    elif room < min_replan:
        why = f"room ${room:.2f} < re-plan minimum ${min_replan:.2f}"
    else:
        n = 2 if twins and room >= 2 * min_replan else 1
        return out("replan", ("low (no ladder history)" if last_gain is None else "low and flat") + ": G " + ("none" if G is None else f"{G:.2f}")
                   + f" < gate {gate:g}" + ("" if last_gain is None else f", last session +{last_gain:.2f}"), room, n)
    return out("ladder", why, room, 1) if ladder else out("none", why + " (no ladder in this mode)", kind="polish-only")


class RowLedger:
    """b63 item 2: ONE spend ledger per row across every session kind (ladder rungs, re-plan / routed rounds, twins, the review): rows/<ws>.ledger.json
    {"sources": {label: usd}}. The ladder label carries the arm's state.json api_spend (monotone: fresh lineages are merged into it by hx_heldout);
    every other producer registers its own spend under its own label; total() is what decide() sees as `spend` and what the review budget is
    computed from, so the sum of all sessions of a row never passes the cap (test_budget_cap.LedgerTests, randomized)."""

    def __init__(self, run_dir: Path, name: str):
        self.path = run_dir / "rows" / f"{safe(name)}.ledger.json"
        try:
            self.d = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.d = {"problem": name, "sources": {}}

    def set(self, label: str, usd: float, monotone: bool = True) -> None:
        cur = float(self.d["sources"].get(label) or 0.0)
        self.d["sources"][label] = round(max(cur, float(usd or 0)) if monotone else float(usd or 0), 6)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp"); tmp.write_text(json.dumps(self.d, indent=1)); tmp.replace(self.path)

    def total(self) -> float:
        return round(sum(float(v or 0) for v in self.d["sources"].values()), 6)

    def set_sessions_total(self, total: float) -> None:
        """The fold's spend is the row's whole session spend (ladder + re-plan rounds + twins); the twins register their own labels, so the
        `sessions` label takes the rest (monotone), never counting a twin twice."""
        twins = sum(float(v or 0) for k, v in self.d["sources"].items() if str(k).startswith("twin:"))
        self.set("sessions", max(0.0, float(total or 0) - twins))

    def room(self, cap: float, frac: float = TARGET_FRAC, reserve: float = REVIEW_RESERVE) -> float:
        return round(cap * frac - reserve - self.total(), 4)


# ---------------------------------------------------------------------------------------------------------------- per-row record
class RowStore:
    """rows/<ws>.json: every finished step's output item and report; a resume skips finished steps."""

    def __init__(self, run_dir: Path, name: str):
        self.path = run_dir / "rows" / f"{safe(name)}.json"
        self.d = json.loads(self.path.read_text()) if self.path.exists() else {"problem": name, "steps": {}}

    def done(self, step):
        return step in self.d["steps"]

    def item(self, step):
        return self.d["steps"][step]["item"]

    def put(self, step, item, report=None):
        if _TERMINATING.is_set():   # b67: main's exit path reaped this step's compiles: not recorded (a restart re-runs the step)
            return
        self.d["steps"][step] = {"item": item, "report": report or {}, "at": now()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp"); tmp.write_text(json.dumps(self.d, ensure_ascii=False, indent=1)); tmp.replace(self.path)


def better(new: dict, cur: dict, min_gain: float = P.MIN_GAIN) -> dict:
    """Keep the higher verified proof; spend is monotone (the newest total always carries)."""
    spend = max(float(new.get("spend") or 0), float(cur.get("spend") or 0))
    ok = new.get("proof") and new.get("verified", True) and new.get("score") is not None
    if ok and (cur.get("score") is None or float(new["score"]) > float(cur["score"]) + min_gain - 1e-9):
        return dict(new, spend=spend)
    return dict(cur, spend=spend)


def _stage_summary(stages: dict) -> dict:
    keep = ("status", "gain", "compiles", "applied", "spend", "review_spend", "review_cap_spend", "best_score", "returncode", "run_id", "seconds",
            "error", "tail", "pin_unservable", "review_fallback", "r6", "stack_proofs", "r6_rounds")   # b72 R6: present only with R6 on
    return {s: {k: v for k, v in (r or {}).items() if k in keep} for s, r in (stages or {}).items()}


def pp_step(name, item, stages, A, evaluator, log, **over) -> tuple[dict, dict]:
    """One postpass.improve_row call with the router's per-step configuration (postpass defaults, then the overrides)."""
    cfg = P.build_parser().parse_args(["--input", "-", "--output", "-"])
    cfg.stages = list(stages); cfg.cap_usd = A.cap
    cfg.polish_model, cfg.polish_effort, cfg.polish_rounds, cfg.polish_k = A.review_model, A.review_effort, A.review_rounds, A.review_k
    cfg.polish_fallback_model = getattr(A, "review_fallback_model", None)   # b66 (A3): the review's stand-in after a confirmed pin
    cfg.polish_max_tokens = getattr(A, "review_max_tokens", REVIEW_MAX_TOKENS)
    cfg.polish_cap_price = getattr(A, "cap_price", "announced")   # b64 L0: the price every review call is gated at
    if review_r6_on(A):   # b72 R6 (off: cfg keeps postpass's defaults, repair 0 / stack off, and the review runs as before)
        cfg.polish_repair, cfg.polish_stack, cfg.polish_stack_eps = int(A.review_repair), bool(A.review_stack), float(A.review_stack_eps)
    cfg.rules_exclude = tuple(getattr(A, "rules_exclude", None) or ())   # B26: every rules stage of the run (checkpoint and final cleanups)
    if getattr(A, "clean_deadline_s", None) is not None:   # L5: the rules / oracle / certify wall limit per row (0 = none, as postpass)
        cfg.deadline_s = float(A.clean_deadline_s)
    for k, v in over.items():
        setattr(cfg, k, v)
    inp = {k: item[k] for k in ITEM_KEYS if item.get(k) is not None} | {"spend": float(item.get("spend") or 0)}
    r = P.improve_row(name, inp, cfg, evaluator, {}, log=log)
    out = dict(r["out"]); sp = out.pop("spend", None)
    sp = sp if isinstance(sp, dict) else {"total": sp}   # a rejected input comes back as the item itself (a float spend)
    out["spend"] = float(sp.get("total") if sp.get("total") is not None else inp["spend"])
    out = {k: out[k] for k in (*ITEM_KEYS, "spend", "measured_score") if out.get(k) is not None}   # measured_score: the reading behind a
    # stored-scale score (postpass, review 2026-10-21)
    rep = {k: r.get(k) for k in ("status", "stage", "score", "gain", "seconds", "final_check", "measured_input") if r.get(k) is not None}
    rep["spend_detail"] = sp; rep["stages"] = _stage_summary(r.get("stages"))
    return out, rep


# --------------------------------------------------------------------------------------------------------------- the arm (ladder)
def arm_set(A):
    """The arm's hx_heldout Set; its rows and reference heartbeats go into leantools' tables. 2026-10-27 (b66 closed package): the set's
    own rows file is the authority for its rows (it replaces the warm-up file's copy of a row of the same name): the final's rows file
    holds the warm-up rows too, and a row the organizers re-pinned must be read with ITS pins, never the warm-up file's (every other set
    is either the warm-up file itself or shares no name with it, so nothing changes there)."""
    import hx_heldout as H
    S = H.Set(A.set, A.arm)
    for r in S.rows:
        LT.ROWS[r["name"]] = r
    if S.hb_path.exists():
        for l in S.hb_path.open():
            if l.strip():
                h = json.loads(l); LT.HBS[h["name"]] = h["heartbeat"]
    return S


def work_root_items(S, names) -> dict:
    """The arm's bests keyed by the problem stored in each state.json (dir names are sanitized); a row without a proof starts from its seed."""
    items = {}
    for st in (S.wt / S.root).glob("*/state.json"):
        d = json.loads(st.read_text()); n = d.get("problem")
        if n not in names:
            continue
        b = d.get("best") or {}
        it = {k: b[k] for k in ("proof", "score", "tokens", "heartbeats", "L", "H", "Z", "compat") if b.get(k) is not None}
        it["spend"] = float(d.get("api_spend") or 0); it["state_path"] = str(st)
        items[n] = it
    for n in names:
        if not (items.get(n) or {}).get("proof"):
            items[n] = {"proof": LT.ROWS[n]["src"], "score": None, "spend": float((items.get(n) or {}).get("spend") or 0),
                        "state_path": (items.get(n) or {}).get("state_path"), "seed": True}
    return items


def write_back(state_path, item, log, min_gain=P.MIN_GAIN) -> bool:
    """adopt(): the cleaned proof becomes the ladder's stored best only when it beats it by more than the noise margin."""
    if not state_path or not item.get("verified", True):
        return False
    p = Path(state_path); d = json.loads(p.read_text()); b = d.get("best") or {}
    if b.get("proof") and float(item.get("score") or 0) <= float(b.get("score") or 0) + min_gain:
        return False
    d["best"] = {"score": item["score"], "proof": item["proof"].rstrip() + "\n"} | {k: item[k] for k in ("tokens", "heartbeats", "L", "H", "Z", "compat") if item.get(k) is not None}
    d.setdefault("router", []).append({"at": now(), "adopted": item.get("stage"), "score": item["score"], "from": b.get("score")})
    tmp = p.with_suffix(".router.tmp"); tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1)); tmp.replace(p)
    (p.parent / "best.lean").write_text(d["best"]["proof"]); (p.parent / "candidate.lean").write_text(d["best"]["proof"])
    log(f"{d.get('problem', '?')[:40]}: written back to the ladder's best ({b.get('score')} -> {item['score']})")
    return True


def bank_item(state_path, name: str, item: dict, source: str, parent: str | None = None) -> bool:
    """b63 item 1: a verified proof of the router's own (a cleanup output, a crossover child, the end output) into the row's bank.jsonl next
    to the ladder's state.json (harness/bank.py); nothing without a state path (generic mode) or a proof. Never raises."""
    if not state_path or not item.get("proof") or not item.get("verified", True):
        return False
    try:
        from harness import bank as BK
        row = LT.ROWS.get(name) or {}
        return BK.add(Path(state_path).parent, BK.entry(item["proof"], source, tokens=item.get("tokens"), heartbeats=item.get("heartbeats"),
                                                        Z=item.get("Z"), compat=item.get("compat"), score=item.get("measured_score", item.get("score")),
                                                        parent=BK.sha(parent) if parent and parent.strip() != item["proof"].strip() else None,
                                                        statement=row.get("statement")))
    except Exception:  # noqa: BLE001
        return False


CROSS_TOP = 6            # b63 item 3 (t13): crossover parents = the incumbent + the best 5 other compiling bank candidates (endstage.CROSS_TOP)
CROSS_MAX_KIDS = 12      # children measured per crossover step (fewest tokens first; endstage.splices orders them)
CROSS_FULL = 2           # children confirmed on every pin (the best by the primary reading)


def cross_step(name, rs: RowStore, item0: dict, A, evaluator, log, S=None) -> None:
    """b63 item 3 (t13 bank crossover BEFORE the review, plan §1.1 C1 / §4.1 item 3): endstage.splices over the row's whole bank (every
    step output, pool.jsonl and bank.jsonl of every root), CROSS_TOP parents, children read on the router's evaluator back to back with the
    incumbent (primary pin), the best CROSS_FULL confirmed on every pin, banked through scorer/accept.decide (no Z regression, a token or
    HB_EPS heartbeats). Records step `cross@pre`: the child when adopted (verified, stage "cross"), else the incumbent (report says why).
    $0; at most CROSS_MAX_KIDS + CROSS_FULL x pins compiles. Everything compiled goes to bank.jsonl (source crossover)."""
    E = importlib.import_module("harness.endstage")
    from scorer.accept import decide as accept
    cur = fold(rs, item0)
    row = LT.ROWS[name]; statement = row["statement"]
    seed = (row.get("src") or item0.get("proof") or "").strip()
    sp = next((st["item"].get("state_path") for st in rs.d["steps"].values() if (st.get("item") or {}).get("state_path")), None)
    cands = E.collect(name, steps=rs.d["steps"], pool_lines=end_pool(rs), seed=seed)
    others = [c for c in cands if c["proof"].strip() != (cur.get("proof") or "").strip() and c.get("score") is not None]
    rep = {"candidates": len(cands), "parents": 1 + min(len(others), CROSS_TOP - 1), "kids": 0, "compiles": 0, "adopted": False}
    if not cur.get("proof") or not others:
        rs.put("cross@pre", cur, dict(rep, status="fewer than two distinct compiling candidates")); return
    parents = [cur["proof"]] + [c["proof"] for c in others[:CROSS_TOP - 1]]
    kids = E.splices(parents, statement)[:CROSS_MAX_KIDS]
    rep["kids"] = len(kids)
    if not kids:
        rs.put("cross@pre", cur, dict(rep, status="no splice child")); return
    if A.dry_run:
        rs.put("cross@pre", cur, dict(rep, status="dry run: children not measured")); return
    versions = P.newest_first(row["version_info"])
    ev = (evaluator() if callable(evaluator) and not hasattr(evaluator, "bound") else evaluator).bound(name, versions)
    ex = lambda m, Z: exact_score(len_pct(row["proof_length"], int(m["tokens"])), hb_pct_local(name, int(m["heartbeats"]), LT.HBS.get(name)), float(Z))  # noqa: E731
    t0 = time.time()
    base = ev(cur["proof"], False); rep["compiles"] += int(base.get("compiles") or 1)
    if not base.get("ok") or base.get("heartbeats") is None:
        rs.put("cross@pre", cur, dict(rep, status="the incumbent does not read on the evaluator")); return
    Zc = float(cur.get("Z") if cur.get("Z") is not None else 100.0)
    inc = {"score": ex(base, Zc), "tokens": int(base["tokens"]), "heartbeats": int(base["heartbeats"]), "Z": Zc}
    passed = []
    for label, text in kids:
        m = ev(text, False); rep["compiles"] += int(m.get("compiles") or 1)
        if not m.get("ok") or m.get("heartbeats") is None:
            continue
        cand = {"score": ex(m, Zc), "tokens": int(m["tokens"]), "heartbeats": int(m["heartbeats"]), "Z": Zc}
        bank_item(sp, name, {"proof": text, "tokens": cand["tokens"], "heartbeats": cand["heartbeats"], "score": cand["score"]}, "crossover", parent=cur["proof"])
        ok, why = accept(inc, cand)
        if ok:
            passed.append((cand["score"], label, text, why))
    rep["passed_primary"] = len(passed)
    passed.sort(key=lambda x: -x[0])
    adopted = None
    for sc, label, text, why in passed[:CROSS_FULL]:
        full = ev(text, True); rep["compiles"] += int(full.get("compiles") or len(versions))
        if not P._valid(full, versions, True):
            continue
        Zf = float(full["Z"])
        cand = {"score": ex(full, Zf), "tokens": int(full["tokens"]), "heartbeats": int(full["heartbeats"]), "Z": Zf}
        # the incumbent re-read right after the child's confirmation (paired, as the end stage's attempt(); launch-set review 2026-10-25):
        # the decision is against the fresher of the two incumbent readings, never against a stale one
        i1 = ev(cur["proof"], False); rep["compiles"] += int(i1.get("compiles") or 1)
        paired = inc if not (i1.get("ok") and i1.get("heartbeats") is not None) else \
            {"score": ex(i1, Zc), "tokens": int(i1["tokens"]), "heartbeats": int(i1["heartbeats"]), "Z": Zc}
        ok, why2 = accept(paired, cand)
        if ok and cand["score"] > max(float(cur.get("score") or 0), float(paired["score"])) + P.MIN_GAIN:
            adopted = dict(cur, proof=text.rstrip() + "\n", score=round(cand["score"], 2), measured_score=cand["score"], tokens=cand["tokens"],
                           heartbeats=cand["heartbeats"], Z=Zf, compat=full.get("compat"), L=full.get("L"), H=full.get("H"), verified=True, stage="cross")
            rep.update(label=label, why=why2, gain=round(cand["score"] - float(paired["score"]), 4), paired=True)
            bank_item(sp, name, dict(adopted, score=cand["score"]), "crossover", parent=cur["proof"])
            break
    rep["seconds"] = round(time.time() - t0, 1)
    if adopted is not None:
        rep.update(adopted=True, status="adopted")
        rs.put("cross@pre", adopted, rep)
        if S is not None and getattr(A, "write_back", True):
            write_back(sp, adopted, log)
    else:
        rep["status"] = "no child beat the incumbent on every pin" if passed else "no child passed the primary reading"
        rs.put("cross@pre", cur, rep)
    log(f"{name[:40]}: crossover (pre-review): {rep['kids']} child(ren) of {rep['parents']} parents, {rep['compiles']} compiles: {rep['status']}"
        + (f" (+{rep['gain']:.3f})" if adopted is not None else ""))


_ROUTER_ENV: set = set()   # environment variables this router process set for its own $0 stages (--compile-slots)
# b65 (5): of those, the ladder subprocess gets the slot COUNT (hx_heldout passes it on to every container, b64-brief DOCKER_PASS_NAMES, so the
# brief's and the sessions' compiles honour --compile-slots); never the router's own scratch (its slot group stays the router's: a ladder
# compile does not queue behind the router's $0 stages, and a container could not reach that host path anyway)
LADDER_PASS_ENV = ("LRA_HBTOOL_SLOTS",)


def compile_slots_env(A, environ=None) -> dict:
    """--compile-slots N: {LRA_HBTOOL_SLOTS: N, LRA_HBTOOL_SCRATCH: <this run's own scratch>} (the scratch only when the environment has none:
    the default one is per checkout, so two routers from one checkout would share their slots); {} without the option."""
    environ = os.environ if environ is None else environ
    n = getattr(A, "compile_slots", None)
    if not n:
        return {}
    import hashlib
    out = {"LRA_HBTOOL_SLOTS": str(int(n))}
    if not environ.get("LRA_HBTOOL_SCRATCH"):
        out["LRA_HBTOOL_SCRATCH"] = str(ROOT / "probe/hbtool/.scratch" / f"router-{hashlib.sha256(str(A.run_dir).encode()).hexdigest()[:10]}")
    return out


def ladder_argv(A, rungs: list, problems: list | None) -> list:
    """hx_heldout's argv for one ladder phase (b66: with --preset-fallback once a ladder preset was CONFIRMED pinned in this run)."""
    fbm = ((getattr(A, "pin_fallback", None) or {}).get("map") or {})   # b66 (A3): the presets confirmed pinned in this run -> their stand-in
    return (["--set", A.set, "--arm", A.arm, "--ref", A.ref, "--rungs", ",".join(f"{r:.2f}" for r in rungs), *shlex.split(A.ladder_args or "")]
            + (["--problems", *problems] if problems else [])
            + (["--preset-fallback", ",".join(f"{x}:{y}" for x, y in sorted(fbm.items()))] if fbm else []))


# b67 (REAP in the module docstring; docs/b67_final.md section 4): tag-and-reap of everything this router invocation starts
REAP_ENV = "LRA_ROUTER_RUN"          # every process of this router invocation (set in main, inherited through fork and exec)
LADDER_REAP_ENV = "LRA_LADDER_RUN"   # every process of one ladder phase (set in ladder)
REAP_GRACE_S = 15.0                  # main's exit path: SIGTERM, then SIGKILL after this (systemd's stop timeout is 90 s)
LADDER_STOP_GRACE_S = 60.0           # a ladder phase past --ladder-timeout: SIGTERM (its sessions end, its brief container stops), then SIGKILL
_TERMINATING = threading.Event()     # main's exit path has begun: RowStore.put records nothing more (a step whose compiles were stopped)


def tagged_pids(var: str, tag: str, proc_root: Path = Path("/proc")) -> list[int]:
    """Pids of the processes (not this one) whose environment holds var=tag (/proc/<pid>/environ; another user's and a zombie's read as
    nothing)."""
    needle, me, out = f"{var}={tag}".encode(), os.getpid(), []
    try:
        entries = [d for d in proc_root.iterdir() if d.name.isdigit() and int(d.name) != me]
    except OSError:
        return out
    for d in entries:
        try:
            if needle in (d / "environ").read_bytes().split(b"\0"):
                out.append(int(d.name))
        except (OSError, ValueError):
            continue
    return out


def _signal_all(pids, sig) -> int:
    n = 0
    for pid in pids:
        try:
            os.kill(pid, sig); n += 1
        except OSError:
            pass
    return n


def reap_tagged(var: str, tag: str, grace: float = REAP_GRACE_S, proc_root: Path = Path("/proc"), poll: float = 0.25) -> dict:
    """b67: SIGTERM every process carrying var=tag, wait up to `grace` seconds for them to end, then SIGKILL what is left (re-read, so a
    process started meanwhile is included). SIGTERM first: a docker client forwards it to its container (agent.py ends and the container
    with it, so no session runs on), hx_heldout's handlers stop its brief container and post-pass steps, Lean ends. Returns
    {"term": processes signalled, "killed": processes still there after the grace}."""
    first = tagged_pids(var, tag, proc_root)
    if not first:
        return {"term": 0, "killed": 0}
    term = _signal_all(first, signal.SIGTERM)
    t_end = time.monotonic() + max(0.0, grace)
    left = first
    while left and time.monotonic() < t_end:
        time.sleep(poll)
        left = tagged_pids(var, tag, proc_root)
    left = tagged_pids(var, tag, proc_root)
    return {"term": term, "killed": _signal_all(left, signal.SIGKILL)}


def stop_containers(prefix: str | None, timeout: float = 90.0) -> list[str]:
    """b67: `docker stop` the running containers whose name starts with `prefix` (this arm's sessions and brief: hx_heldout.container_name);
    the names stopped ([] without docker or a prefix). Bounded."""
    if not prefix:
        return []
    try:
        names = subprocess.run(["docker", "ps", "--filter", f"name={prefix}", "--format", "{{.Names}}"], capture_output=True, text=True,
                               timeout=30).stdout.split()
        names = [n for n in names if n.startswith(prefix)]
        if names:
            subprocess.run(["docker", "stop", "-t", "10", *names], capture_output=True, timeout=timeout)
        return names
    except (OSError, subprocess.SubprocessError):
        return []


def container_prefix(A, S) -> str | None:
    """The name prefix of this arm's containers (hx_heldout.container_name of its run ids <prefix>-hx-<arm>-...), when its sessions run in
    docker; else None."""
    if S is None or not getattr(S, "prefix", None) or not (getattr(A, "agent_docker", None) or "--agent-docker" in (getattr(A, "ladder_args", "") or "")):
        return None
    return "lra-ag-" + re.sub(r"[^A-Za-z0-9_.-]", "_", f"{S.prefix}-hx-{A.arm}") + "-"


def ladder_cmd(A, rungs: list, problems: list | None) -> list:
    return [sys.executable, "-u", str(ROOT / "harness/hx_heldout.py"), *ladder_argv(A, rungs, problems)]


def run_phase(A, cmd: list, tag: str, say, label: str) -> int:
    """One hx_heldout phase process (b67; b68: factored out of ladder() unchanged, shared with the tail's tail_hx): its log
    ladder-<tag>.log, the router's own $0-stage environment kept out, LADDER_REAP_ENV on every process of the phase; past --ladder-timeout
    the phase is reaped (SIGTERM, LADDER_STOP_GRACE_S, SIGKILL; the arm's containers stopped) and the exit is 124; what a phase whose
    hx_heldout ended on its own left running is reaped the same way (b67 review); a BaseException in the router (SIGTERM: RouterTerminated)
    sends SIGTERM to every process of the phase and re-raises. `label` heads those lines ("ladder <tag>" for a ladder phase, as before)."""
    env = {k: v for k, v in os.environ.items() if k not in _ROUTER_ENV or k in LADDER_PASS_ENV} if _ROUTER_ENV else dict(os.environ)
    ltag = f"{os.getpid()}-{time.time_ns()}"
    env[LADDER_REAP_ENV] = ltag   # b67: every process of this phase (hx_heldout, its docker clients, host sessions, post-pass steps, compiles)
    with (A.run_dir / f"ladder-{tag}.log").open("a") as f:
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, env=env)
        try:
            rc = p.wait(timeout=A.ladder_timeout)
            if tagged_pids(LADDER_REAP_ENV, ltag):
                # b67 review: hx_heldout ended on its own (a crash, an OOM kill) while processes of its phase still ran: its sessions'
                # docker clients (the sessions going on in their containers, spending and writing the work root) and compiles in their own
                # sessions. A normal end leaves nothing (hx_heldout waits for its sessions; its brief and post-pass steps never outlive it).
                # Stopped as a timed-out phase is, before the router goes on; hx_heldout's exit code stays
                r = reap_tagged(LADDER_REAP_ENV, ltag, grace=LADDER_STOP_GRACE_S)
                cs = stop_containers(getattr(A, "container_prefix", None))
                say(f"{label}: {r['term']} process(es) of the phase were still running after hx_heldout ended (exit {rc}): SIGTERM"
                    + (f", SIGKILL to {r['killed']} after {LADDER_STOP_GRACE_S:.0f} s" if r["killed"] else "")
                    + (f"; {len(cs)} session container(s) stopped" if cs else ""))
        except subprocess.TimeoutExpired:
            # b67: was subprocess.run's SIGKILL of hx_heldout alone: its sessions ran on in their containers (spending, writing the work
            # root) and its compiles with no timeout while the router went on to the $0 stages and the review
            r = reap_tagged(LADDER_REAP_ENV, ltag, grace=LADDER_STOP_GRACE_S)
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill(); p.wait(timeout=30)
            cs = stop_containers(getattr(A, "container_prefix", None))
            rc = 124
            say(f"{label}: wall limit {A.ladder_timeout:g} s reached: stopped (SIGTERM to {r['term']} process(es) of the phase, SIGKILL "
                f"to {r['killed']} still there after {LADDER_STOP_GRACE_S:.0f} s" + (f"; {len(cs)} session container(s) stopped" if cs else "") + ")")
        except BaseException:
            # b67: the router is ending (SIGTERM: RouterTerminated): every process of the phase gets SIGTERM now (sessions end in their
            # containers, the brief container is stopped); main's finally reaps what is left once the outputs are written. Was: subprocess.run
            # SIGKILLed hx_heldout alone and its docker clients, steps and compiles lived on
            _signal_all(sorted(set(tagged_pids(LADDER_REAP_ENV, ltag)) | {p.pid}), signal.SIGTERM)
            raise
    return rc


def ladder(A, rungs: list, problems: list | None, tag: str, say) -> int:
    fbm = ((getattr(A, "pin_fallback", None) or {}).get("map") or {})
    cmd = ladder_cmd(A, rungs, problems)
    say(f"ladder {tag}: rungs {rungs} on {len(problems) if problems else 'all'} row(s)"
        + (f"; preset fallback {', '.join(f'{x} -> {y}' for x, y in sorted(fbm.items()))} (confirmed max_price pin)" if fbm else ""))
    rc = run_phase(A, cmd, tag, say, f"ladder {tag}")
    say(f"ladder {tag}: exit {rc}")
    if rc == pin_rc():   # b65 pin, CONFIRMED (b65-final: 2 rows, or 3 tries over 10 min, each $0): OpenRouter serves no endpoint under the pin
        say(f"ladder {tag}: FATAL: a CONFIRMED max_price pin (the FATAL line in {A.run_dir / f'ladder-{tag}.log'}): the pinned preset's "
            f"sessions move to another ladder preset of the run if one still answers (b66), else no further paid step: the router finishes the "
            f"run on its $0 path (cleanups, crossover, end stage), writes every output and exits {PIN_STOP_RC}")
    return rc


def code_hash() -> str:
    """B34 patch review: the router, postpass, review, hx_heldout and the scorer run from this checkout, not from --ref (which pins only the
    agent worktree), so a resume after main moved ran other code unnoticed. A content hash of harness/, scorer/ and llm/ (*.py, tests
    excluded) is frozen at the first start and checked on every resume; commits that do not change these files do not change it."""
    import hashlib
    h = hashlib.sha256()
    for d in ("harness", "scorer", "llm"):
        for f in sorted((ROOT / d).rglob("*.py")):
            if f.name.startswith("test_") or "__pycache__" in f.parts:
                continue
            h.update(str(f.relative_to(ROOT)).encode()); h.update(b"\0"); h.update(f.read_bytes()); h.update(b"\0")
    return h.hexdigest()[:16]


def pin_rc() -> int:
    """b65: agent.py's (and hx_heldout's) exit code for a CONFIRMED max_price pin (agent.PIN_FATAL_RC)."""
    from harness.agent import PIN_FATAL_RC   # noqa: E402
    return PIN_FATAL_RC


def pin_preset_of(A, S, tag: str) -> tuple:
    """(the CONFIRMED preset or None, its message) of a ladder phase that exited PIN_FATAL_RC: the ladder's out-dir marker (hx_heldout.pin_out;
    b66: it names the preset), else "preset X" in its message, else the FATAL line of the phase's log."""
    msg, preset = "", None
    try:
        j = json.loads((Path(S.out) / "pin_unservable.json").read_text())   # hx_heldout.pin_out's marker
        msg, preset = str(j.get("message") or ""), (j.get("preset") or None)
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    if not msg:
        try:
            msg = next((l.strip() for l in reversed((A.run_dir / f"ladder-{tag}.log").read_text(errors="replace").splitlines()) if "FATAL" in l), "")
        except OSError:
            msg = ""
    if not preset:
        m = re.search(r"preset ([\w.-]+)", msg)
        preset = m.group(1) if m else None
    return preset, msg


def pin_stop_note(A, S, tag: str, say) -> dict:
    """b65-final: a ladder phase exited PIN_FATAL_RC. Records <run>/pin_stop.json {"preset", "message", "phase", "at"} (the ladder's out dir
    marker says which pin; a restart reads the file and stays on the $0 path) and returns it. b66 (A3): only once no ladder preset of the
    run is left (pin_fallback_pick); the file then also lists the fallbacks taken before (`fallback`)."""
    preset, msg = pin_preset_of(A, S, tag)
    rec = {"preset": preset, "message": (msg or f"ladder {tag} exited {pin_rc()} (a CONFIRMED max_price pin)")[:600], "phase": tag, "at": now()}
    fbm = ((getattr(A, "pin_fallback", None) or {}).get("map") or {})
    if fbm:
        rec["fallback"] = dict(fbm)
    tmp = A.run_dir / f".{PIN_STOP_FILE}.tmp"; tmp.write_text(json.dumps(rec, indent=1)); tmp.replace(A.run_dir / PIN_STOP_FILE)
    say(f"PIN STOP after ladder {tag}: {rec['message'][:300]}; "
        + (f"no other ladder preset of the run is left (fallbacks taken: {', '.join(f'{x} -> {y}' for x, y in sorted(fbm.items()))}); " if fbm else
           "no other ladder preset of the run can take over; ")
        + f"every later paid step is skipped (no ladder phase, re-plan, twin or review); the cleanups, crossover and end stage run ($0); "
        f"exit {PIN_STOP_RC} with every output written")
    return rec


# b66 (retro A3, docs/b66_robust.md; the no-harm rule of 2026-10-27): a CONFIRMED max_price pin of ONE ladder preset no longer sends
# the whole run to its $0 path while another OpenRouter session preset of the run still answers (Sol-main <-> Terra-main under
# --preset-by-rung, or --pin-fallback-preset). The router moves every session configured for the pinned preset to the other one (hx_heldout
# --preset-fallback X:Y: gated at Y's cap price, with Y's session floor) and runs the same ladder phase again, which resumes the rows where
# the pin left them. "Still answering" = never pinned in this run and not CONFIRMED by its own pin events in the arm's run dirs
# (pinwatch.confirmed); a Y that is pinned too confirms at $0 in its own sessions (a 404 on 2 rows within seconds, a 503 streak in >= 10 min)
# and, with no preset left, the run takes the $0 path as before (pin_stop.json, exit PIN_STOP_RC). Persisted in <run>/pin_fallback.json (a
# restart keeps the substitution; a pinned preset is not re-probed in this run), one decisions.jsonl line per fallback (problem null,
# checkpoint "pin-fallback@<phase>", kind pin-fallback) and summary.json `pin_fallback` + the exit reason.
PIN_FALLBACK_FILE = "pin_fallback.json"


def ladder_presets(A) -> list:
    """b66 (A3): the run's ladder session presets, in order: --ladder-args' --preset, its --preset-by-rung presets, --first-preset (read by
    hx_heldout's own parser, as ladder_preset_by_rung reads them), then --pin-fallback-preset (comma-separated)."""
    out: list = []
    if A.set:
        import hx_heldout as H
        hp = H.build_parser()

        def _refuse(msg):
            raise ValueError(msg)
        hp.error = _refuse
        try:
            ns, _ = hp.parse_known_args(["--set", A.set, "--arm", A.arm or "-", *shlex.split(A.ladder_args or "")])
            out = [ns.preset] + [P for _R, (P, _E) in sorted(H.rung_presets(ns.preset_by_rung).items())] \
                + ([ns.first_preset] if getattr(ns, "first_preset", None) else [])
        except (ValueError, argparse.ArgumentError):
            out = []
    out += [p.strip() for p in str(getattr(A, "pin_fallback_preset", None) or "").split(",") if p.strip()]
    return list(dict.fromkeys(out))


def load_pin_fallback(A) -> dict:
    """b66 (A3): {"map": {pinned: stand-in}, "events": [...]} an earlier invocation of this run recorded (empty when none)."""
    try:
        d = json.loads((A.run_dir / PIN_FALLBACK_FILE).read_text())
    except (OSError, ValueError):
        d = {}
    return {"map": dict(d.get("map") or {}), "events": list(d.get("events") or [])}


def arm_run_dirs(S) -> list:
    """The arm's session run dirs (hx_heldout run ids <prefix>-hx-<arm>-r<k> / -f<k>): where its sessions' pin_events.jsonl are."""
    rp = getattr(S, "run_prefix", None) if S is not None else None
    if not rp:
        return []
    try:
        return [d for d in (Path(S.wt) / "probe/runs").glob(f"{rp[:-1]}*") if d.is_dir()]
    except OSError:
        return []


def pin_fallback_pick(A, S, pinned: str | None) -> str | None:
    """b66 (A3): the preset the pinned preset's sessions move to, or None (the $0 path): the first ladder preset of the run (ladder_presets)
    that was not pinned in this run, is an OpenRouter agent.py session preset on the pinned one's key, and whose own pin events do not
    already confirm it (pinwatch.confirmed over the arm's run dirs). An unknown pinned preset has no fallback."""
    if not pinned:
        return None
    from harness.agent import MODEL_PRESETS   # noqa: E402
    from harness import pinwatch as PW   # noqa: E402
    gone = set(((getattr(A, "pin_fallback", None) or {}).get("map") or {})) | {pinned}
    px = MODEL_PRESETS.get(pinned) or {}
    events = None
    for p in ladder_presets(A):
        pp = MODEL_PRESETS.get(p) or {}
        if p in gone or not pp or pp.get("anthropic_vertex") or "openrouter.ai" not in (pp.get("base_url") or ""):
            continue
        if px and px.get("key") != pp.get("key"):
            continue
        events = PW.read_events(arm_run_dirs(S)) if events is None else events
        if PW.confirmed(events, p):
            continue
        return p
    return None


def pin_fallback_note(A, S, tag: str, pinned: str, to: str, msg: str, say) -> None:
    """b66 (A3): record one fallback (pinned -> to; an earlier stand-in that is now pinned is replaced too) in A.pin_fallback, <run>/
    pin_fallback.json (atomic) and decisions.jsonl; the next ladder call passes it (ladder: --preset-fallback)."""
    fb = A.pin_fallback = getattr(A, "pin_fallback", None) or {"map": {}, "events": []}
    fb["map"] = {x: (to if y == pinned else y) for x, y in fb["map"].items()} | {pinned: to}
    ev = {"pinned": pinned, "to": to, "phase": tag, "at": now(), "message": (msg or "")[:600]}
    fb["events"].append(ev)
    tmp = A.run_dir / f".{PIN_FALLBACK_FILE}.tmp"; tmp.write_text(json.dumps(fb, indent=1)); tmp.replace(A.run_dir / PIN_FALLBACK_FILE)
    _decision_line(A, {"problem": None, "checkpoint": f"pin-fallback@{tag}", "tier": "ladder", "kind": "pin-fallback", "pinned": pinned,
                       "to": to, "budget": 0.0, "reason": f"a CONFIRMED max_price pin of {pinned} in ladder {tag}; {to} still answers: every "
                       f"session configured for {pinned} runs {to}, gated at {to}'s cap price ({(msg or '')[:200]})"})
    say(f"PIN FALLBACK after ladder {tag}: {pinned} is CONFIRMED pinned ({(msg or '')[:200]}); its sessions run {to} from here on (gated at "
        f"{to}'s cap price); ladder {tag} runs again on the rows' current state")


def fb_model(A, m: str | None) -> str | None:
    """b66 (A3): the preset a router-run session configured for `m` uses (a re-plan, twin or artifact session of a preset the ladder fell
    back from runs its stand-in), else `m`."""
    return (((getattr(A, "pin_fallback", None) or {}).get("map") or {}).get(m, m)) if m else m


def ladder_phase(A, S, rungs: list, problems: list | None, tag: str, say) -> int:
    """b65-final + b66 (A3): one ladder phase. A CONFIRMED pin (PIN_FATAL_RC) of a preset that another ladder preset of the run can take
    over runs the phase again with that fallback (bounded: each fallback removes a preset); with none left, the run's $0 path
    (A.pin_stop; the phase then returns 0: the rows stay as the ladder left them)."""
    rc = ladder(A, rungs, problems, tag, say)
    for _ in range(len(ladder_presets(A)) + 1):
        if rc != pin_rc():
            return rc
        pinned, msg = pin_preset_of(A, S, tag)
        to = pin_fallback_pick(A, S, pinned)
        if not to:
            break
        pin_fallback_note(A, S, tag, pinned, to, msg, say)
        rc = ladder(A, rungs, problems, tag, say)
    if rc == pin_rc():
        A.pin_stop = pin_stop_note(A, S, tag, say); rc = 0
    return rc


def load_pin_stop(A) -> dict | None:
    """b65-final: the pin stop an earlier invocation of this run recorded (the run stays on its $0 path), or None."""
    try:
        return json.loads((A.run_dir / PIN_STOP_FILE).read_text())
    except (OSError, ValueError):
        return None


def short_stop(rc, tag, rung, names, items, say, accept: bool = False, log_path=None) -> bool:
    """B34 adversarial review (2026-10-20): a ladder phase that exited non-zero (Azure 429s ending every session of a round, "no spend
    recorded", max rounds, a timeout) left rows below its rung. Cleaning and gating them (L phases), or writing ladder_top for them (TOP),
    froze the under-fill: a resume never refilled them, and clean2 and the review then ran on short rows, biasing the score down and
    inflating the run-to-run spread. Stop instead (exit 2): the next start re-runs that ladder phase. LRA_ROUTER_ACCEPT_SHORT=1 keeps the
    old behaviour (go on with the short rows), for a cause a resume cannot fix (max rounds)."""
    if not rc:
        return False
    short = [n for n in names if float((items.get(n) or {}).get("spend") or 0) + state_cap_extra((items.get(n) or {}).get("state_path"))
             + SESSION_FLOOR < rung - 1e-9]   # b64 planner: at the cap price, as hx_heldout fills the rung
    if not short:
        return False
    if accept or os.environ.get("LRA_ROUTER_ACCEPT_SHORT") == "1":
        say(f"ladder {tag}: exit {rc} with {len(short)} row(s) below ${rung - SESSION_FLOOR:.2f}; --accept-short: going on")
        return False
    # B34 patch review: hx_heldout counts rounds cumulatively, so after "max rounds" every restart stops again at once: say so
    tail = ""
    try:
        tail = Path(log_path).read_text()[-4000:] if log_path else ""
    except OSError:
        pass
    if "max rounds" in tail:
        say(f"ladder {tag}: exit {rc} at max rounds with {len(short)} row(s) below ${rung - SESSION_FLOOR:.2f}: a restart cannot refill "
            f"them; raise --max-rounds in --ladder-args (not frozen) and restart, or restart with --accept-short to finish them as they are")
    else:
        say(f"ladder {tag}: exit {rc} with {len(short)} row(s) below ${rung - SESSION_FLOOR:.2f}: stopping before any cleanup or gate "
            f"(a restart re-runs ladder {tag}; --accept-short finishes the short rows as they are)")
    return True


class DockerRunner:
    """The replan session in the arm's container (hx_heldout.agent_docker: the worktree read-only, its work roots read-write, the preset's
    one key, a private compile scratch): agent.py's shell is host bash, so a session on the host could read other lines' files."""

    def __init__(self, S, A):
        self.S, self.timeout = S, A.replan_timeout
        self.ns = types.SimpleNamespace(wt=S.wt, preset=fb_model(A, A.replan_model), agent_docker=A.agent_docker, agent_docker_memory=A.agent_docker_memory,
                                        agent_private_scratch=A.agent_private_scratch, agent_mask_strays=A.agent_mask_strays)

    def __call__(self, cmd, d):
        import hx_heldout as H
        i = next(k for k, c in enumerate(cmd) if str(c).endswith("harness/agent.py"))
        rest = list(cmd[i + 1:]); run_id = rest[rest.index("--run-id") + 1]
        dc = H.agent_docker(self.ns, run_id, ["python3", "-u", "harness/agent.py", *rest])
        try:
            r = subprocess.run(dc, cwd=self.S.wt, capture_output=True, text=True, timeout=self.timeout)
            return r.returncode, (r.stdout or "")[-1500:] + (r.stderr or "")[-500:]
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "stop", dc[dc.index("--name") + 1]], capture_output=True)
            return 124, "timeout"


def dry_runner(cmd, d):
    return 0, "dry run: no model call"


REPLAN_RUNNER = None   # tests inject a fake session here; None = postpass's host subprocess (generic mode)


def lineage_gains(S, name, checkpoint) -> list:
    """The ladder's per-session gains on or below this checkpoint, oldest first (hx_heldout lineage.json: per-session [rung, gain], sessions
    under $0.05 already left out there); [] if unknown. gain[-1] / gain[-2] of the plateau rule (plan F8; b63 item 2)."""
    try:
        g = (json.loads((S.out / "lineage.json").read_text()).get(name) or {}).get("gains") or []
    except (OSError, ValueError, AttributeError):
        return []
    return [float(x) for r, x in g if r <= checkpoint + 1e-9 and x is not None]


def lineage_gain(S, name, checkpoint):
    """The ladder's last session gain on or below this checkpoint; None if unknown."""
    g = lineage_gains(S, name, checkpoint)
    return g[-1] if g else None


def cpu_gain_at(rs: "RowStore", k: int) -> float:
    """What the checkpoint-k CPU pass banked (clean@k's gain on the row; 0.0 when nothing or unknown)."""
    g = ((rs.d["steps"].get(f"clean@{k}") or {}).get("report") or {}).get("gain")
    return round(float(g), 4) if isinstance(g, (int, float)) and math.isfinite(g) else 0.0


def write_route(rs: "RowStore", name: str, k: int, cp: float, dec: dict, item: dict) -> None:
    """rows/<ws>.route.json (contract §2): diagnose classes (c1..c6; None until harness/diagnose.py, plan item 9, exists), the computable
    features (F2 exchange rates from the row's reference numbers, F8 lineage gains / cpu gain), and the decided routes per checkpoint with
    the rule that fired. A stub where the diagnosis is not built; the keys are the contract's."""
    p = rs.path.with_name(rs.path.stem + ".route.json")
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        d = {"problem": name, "classes": {c: None for c in ("c1", "c2", "c3", "c4", "c5", "c6")}, "features": {}, "routes": [], "stub": True,
             "note": "classes/F1/F3-F7 need harness/diagnose.py (plan item 9, post-launch); F2 and F8 are computed"}
    row = LT.ROWS.get(name) or {}
    rt, rh = row.get("proof_length"), (LT.HBS.get(name) if isinstance(LT.HBS, dict) else None)
    f2 = {}
    if rt:
        f2["pts_per_token"] = round(100.0 / (3 * int(rt)), 4)
        if item.get("tokens") is not None:
            f2["L_headroom_pts"] = round(int(item["tokens"]) * 100.0 / (3 * int(rt)), 2)
    if rh:
        f2["pts_per_1000hb"] = round(1e5 / (3 * float(rh)), 3)
        if item.get("heartbeats") is not None:
            f2["H_headroom_pts"] = round(int(item["heartbeats"]) * 100.0 / (3 * float(rh)), 2)
    d["features"]["F2"] = f2
    d["features"]["F8"] = {"gain1": dec["inputs"].get("gain1"), "gain2": dec["inputs"].get("gain2"), "cpu_gain": dec["inputs"].get("cpu_gain"),
                           "diverse": dec["inputs"].get("diverse")}
    if dec["inputs"].get("c6") is not None:   # b63 item 17: the one class the router computes itself (reference length x session cost)
        d["classes"]["c6"] = 1.0 if dec["inputs"]["c6"] else 0.0
    d["routes"] = [x for x in d["routes"] if x.get("checkpoint") != k] + [{"checkpoint": k, "budget_at": cp, "kind": dec.get("kind"), "tier": dec["tier"],
                                                                           "plateau": dec.get("plateau"), "rule": dec["reason"], "budget": dec["budget"], "at": now(),
                                                                           **({"artifact_route": dec["route"]} if dec.get("route") else {})}]
    tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1)); tmp.replace(p)


def write_cpu_pass(rs: "RowStore", name: str, k: int, item_in: dict, out: dict, rep: dict) -> None:
    """rows/<ws>.cpu_pass.json (contract §2, C0/C1): the families the checkpoint's CPU pass ran (postpass stages and free passes), their order,
    wall per family where the report has it, the banked delta and the B0 score (the pass output) against the input. Until the C0 pre-session
    pass (plan item 6) exists, C0 is the checkpoint-0 cleanup on the ladder's first output (stub: true)."""
    p = rs.path.with_name(rs.path.stem + ".cpu_pass.json")
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        d = {"problem": name, "passes": {}, "stub": True, "note": "C0 pre-session pass not built (plan item 6); C<k> = the checkpoint-k cleanup"}
    stages = rep.get("stages") or {}
    fams = [st for st in stages if (stages[st] or {}).get("status") not in (None, "skipped")]
    d["passes"][f"C{k}"] = {"families": list(stages), "order": fams, "wall": {st: (stages[st] or {}).get("seconds") for st in stages},
                           "applied": {st: (stages[st] or {}).get("applied") for st in stages if (stages[st] or {}).get("applied")},
                           "banked_delta": rep.get("gain"), "seconds": rep.get("seconds"), "input_score": item_in.get("score"),
                           "B0" if k == 0 else "score": out.get("score"), "stage": out.get("stage"), "at": now()}
    tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1)); tmp.replace(p)


def seed_dead(S, A, name):
    """The auto-brief's $0-dead signature on the seed (no paying single edit), recorded with the decision for the threshold fit."""
    try:
        d = json.loads((S.wt / (A.auto_brief_dir or "") / f"{safe(name)}.json").read_text())
        base = float((d.get("sweep_base") or {}).get("score") or 0)
        return not any(e.get("ok") and e.get("score") is not None and float(e["score"]) > base + P.MIN_GAIN for e in d.get("edits") or [])
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def c6_of(S, name: str, item: dict) -> bool | None:
    """Plan §1.3 class c6 (variance / cheap): the reference proof is under C6_REF_TOKENS tokens and the row's ladder sessions cost at most
    C6_SESSION each (the arm's api_spend over the lineage's session count, hx_heldout lineage.json). None when either is unknown (generic
    mode, no session yet): then the twin needs the bank's class spread. Measured numbers only, never a name."""
    rt = (LT.ROWS.get(name) or {}).get("proof_length")
    if rt is None:
        return None
    if int(rt) >= C6_REF_TOKENS:
        return False
    try:
        n = int(((json.loads((S.out / "lineage.json").read_text()).get(name) or {}).get("sessions")) or 0)
    except (OSError, ValueError, AttributeError, TypeError):
        n = 0
    if n <= 0:
        return None
    return float(item.get("spend") or 0) / n <= C6_SESSION + 1e-9


def _tag(statement: str | None, proof: str) -> str:
    """bank.class_tag cut at the row's statement when the proof starts with it (as bank_item and agent.py tag the bank's entries), else at
    the first `:= by`. Review 2026-10-25: without the statement class_tag cuts INSIDE a statement that holds a `:= by` (an auto-param
    argument: 1 of the 15 warm-up statements; all 9 v2 router items of that row tagged differently), so one proof had two tags (the
    bank's, cut at the statement, and the router's) and `diverse` read a same-class bank entry as another class."""
    from harness import bank as BK
    return BK.class_tag(proof, statement if statement and proof.startswith(statement) else None)


def klass_of(name: str, proof: str) -> str:
    """The structural class of a proof of row `name` (one cut for every lineage and bank entry of the row)."""
    return _tag((LT.ROWS.get(name) or {}).get("statement"), proof)


def diverse_of(state_path, item: dict, name: str = "", within: float = TWIN_WITHIN) -> bool:
    """The twin's other trigger (plan §2 Variance: "a structurally different compiled artifact exists"): the row's bank holds a compiling,
    scored candidate (not the current best's own text) of ANOTHER structural class within `within` points of the current best (or above
    it): the candidate SELECT would keep as a runner-up (bank.runner_up's rule). Every tag through klass_of (the stored `klass` depends on
    the producer: cpu_pass tags without the statement). False without a bank.
    Review 2026-10-25: was "any other-class entry"; agent.py banks every compiling candidate of every session, so that fired on 29 of the
    30 rows of the live v3a/v3b banks (read-only count): twins on every plateaued row below 90, the fixed cost plan §2 rules out. With the
    SELECT criterion: 14 of 30."""
    if not state_path or not item.get("proof"):
        return False
    try:
        from harness import bank as BK
        es = BK.scored(BK.read(Path(state_path).parent))
        mine, msha = klass_of(name, item["proof"]), BK.sha(item["proof"])
        ref = float(item.get("measured_score", item.get("score")) or 0)
        return any(e.get("proof") and BK.sha(e["proof"]) != msha and ref - float(e["score"]) <= within + 1e-9
                   and klass_of(name, e["proof"]) != mine for e in es)
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------------------------------------------------- the row
def fold(rs: RowStore, item0: dict) -> dict:
    cur = dict(item0)
    for st in rs.d["steps"].values():
        cur = better(st["item"], cur)
    return cur


def _first_step(rs: RowStore, kind: str):
    """The row's first `<kind>@k` step (input@0 / clean@0 in a run from seed; input@<k0> in a checkpoint start), or None."""
    st = rs.d["steps"].get(f"{kind}@0")
    if st is None:
        ks = sorted(int(x.split("@")[1]) for x in rs.d["steps"] if re.fullmatch(kind + r"@\d+", x))
        st = rs.d["steps"].get(f"{kind}@{ks[0]}") if ks else None
    return st


def inp0(rs: RowStore) -> dict:
    return (_first_step(rs, "input") or {}).get("item") or {}


def last_clean(rs: RowStore):
    cleans = [k for k in rs.d["steps"] if k.startswith("clean")]
    return rs.item(cleans[-1]) if cleans else None


def harvest_artifacts(rs: "RowStore", name: str, item: dict, log) -> dict:
    """b63 item 16 (--routes): the row's artifacts into rows/<ws>.cpu_pass.json `artifacts` (harness/artifacts.py record shape): the sessions'
    skeletons.jsonl / near_misses.jsonl next to the arm's state.json (agent.py --pool writes them), plus whatever a C1 family wrote there
    already. Returns the stored artifacts; $0, no Lean."""
    AR = importlib.import_module("harness.artifacts")
    p = rs.path.with_name(rs.path.stem + ".cpu_pass.json")
    recs = []
    sp = item.get("state_path")
    if sp:
        try:
            recs = AR.collect_from_session(Path(sp).parent, statement=(LT.ROWS.get(name) or {}).get("statement"), best_text=item.get("proof"))
        except Exception as e:  # noqa: BLE001
            log(f"{name[:40]}: artifact harvest failed: {type(e).__name__}")
    try:
        return AR.write(p, recs) if recs else AR.read(p)
    except Exception as e:  # noqa: BLE001
        log(f"{name[:40]}: artifacts not written: {type(e).__name__}"); return {"skeletons": [], "near_misses": []}


def route_of(rs: "RowStore", name: str, item: dict, A, log) -> dict | None:
    """The artifact route for decide() (plan §1.4) or None without --routes: {"kind", "reason", "artifact", "near_misses", "candidates"}."""
    if not getattr(A, "routes", False):
        return None
    AR = importlib.import_module("harness.artifacts")
    arts = harvest_artifacts(rs, name, item, log)
    classes = None
    try:
        rp = rs.path.with_name(rs.path.stem + ".route.json")
        classes = json.loads(rp.read_text()).get("classes") if rp.exists() else None
    except (OSError, ValueError):
        classes = None
    best_sha = AR.sha(item["proof"]) if item.get("proof") else None
    return AR.route_for(arts, classes=classes if isinstance(classes, dict) else None, best_sha=best_sha)


def pre_row(name, item_k, k, A, evaluator, log, S=None) -> dict:
    """Checkpoint k: record the row as the ladder left it, clean it ($0), write a gain back to the ladder's best."""
    rs = RowStore(A.run_dir, name)
    if not rs.done(f"input@{k}"):
        rs.put(f"input@{k}", item_k)
    led_k = RowLedger(A.run_dir, name); led_k.set("sessions", float(item_k.get("spend") or 0))   # b63: the shared per-row ledger (contract §2)
    ladder_cap_extra(led_k, item_k.get("state_path"))   # b64 planner
    if not rs.done(f"clean@{k}"):
        fast = {"free_passes": list(CHECKPOINT_FREE_PASSES)} if getattr(A, "fast_checkpoint_cleanup", False) else {}
        inp = better(rs.item(f"input@{k}"), fold(rs, item_k))
        out, rep = pp_step(name, inp, A.clean_stages, A, evaluator, log, **fast)
        rs.put(f"clean@{k}", out, rep)
        try:
            write_cpu_pass(rs, name, k, inp, out, rep)
        except Exception as e:  # noqa: BLE001  (a log file, never the row)
            log(f"{name[:40]}: cpu_pass.json not written: {type(e).__name__}")
        if S is not None and not A.dry_run and A.write_back and out.get("stage") not in (None, "input"):
            write_back(item_k.get("state_path"), out, log)
        bank_item(item_k.get("state_path"), name, out, f"clean@{k}", parent=inp.get("proof"))
    return fold(rs, item_k)


MAX_REPLAN_ROUNDS = 6     # 2026-10-19 (Stage 2): a re-plan session stops at its turn cap after ~$0.40 of a ~$1.2-1.5 budget; further
MIN_ROUND_SPEND = 0.02    # sessions from the best proof fill the row's budget (equal spend with the ladder arm); a round that spent
                          # almost nothing ends the loop (a broken session never repeats)


def _rkeys(k: int) -> tuple[str, str]:
    return ("replan", "replan_started") if k == 1 else (f"replan#{k}", f"replan_started#{k}")


def _recover(name, rs, key, roots, cur, A, evaluator, log, k) -> None:
    """A round killed mid-session: count what its session(s) spent (agent.py persists api_spend per turn) and keep the session's best
    proof if it is better and passes a full check; never re-run the round."""
    spent, best = 0.0, None
    for r in roots:
        f = r / safe(name) / "state.json"
        if f.exists():
            st = json.loads(f.read_text()); spent += float(st.get("api_spend") or 0)
            b = st.get("best") or {}
            if b.get("proof") and (best is None or float(b.get("score") or 0) > float(best.get("score") or 0)):
                best = b
    spent = round(spent, 4); item = dict(cur, spend=round(float(cur.get("spend") or 0) + spent, 4)); kept = False
    if best and float(best.get("score") or 0) > float(cur.get("score") or 0) + P.MIN_GAIN and best["proof"].strip() != (cur.get("proof") or "").strip():
        out, _ = pp_step(name, {"proof": best["proof"], "spend": item["spend"]}, [], A, evaluator, log)   # a full measurement of the session's best
        if out.get("verified") and float(out.get("score") or 0) > float(cur.get("score") or 0) + P.MIN_GAIN:
            item, kept = dict(out, spend=item["spend"]), True
    rs.put(key, item, {"status": "interrupted", "spent": spent, "round": k, "kept_session_best": kept})
    log(f"{name[:40]}: replan round {k} was interrupted; its spend ${spent:.3f} counted" + ("; its best kept after a full check" if kept else ""))


def replan_rounds(name, rs, item0, A, evaluator, log, S, dec) -> bool:
    """Re-plan sessions until the decision's budget is used. Returns True when a new round ran in this call."""
    runner = dry_runner if A.dry_run else (DockerRunner(S, A) if (S is not None and A.agent_docker) else REPLAN_RUNNER)
    base = (S.wt / "harness/hwork" / f"{S.prefix}-{A.arm}-replan-{A.run_dir.name}") if S is not None else (A.run_dir / "replan")
    total, ran = float(dec["budget"]), False
    for k in range(1, MAX_REPLAN_ROUNDS + 1):
        key, skey = _rkeys(k)
        if rs.done(key):
            continue
        prior = [rs.d["steps"][_rkeys(j)[0]]["report"] for j in range(1, k) if rs.done(_rkeys(j)[0])]
        left = round(total - sum(float(r.get("spent") or 0) for r in prior), 4)
        if k > 1 and (not getattr(A, "replan_continue", True) or left < SESSION_FLOOR or float((prior[-1] if prior else {}).get("spent") or 0) < MIN_ROUND_SPEND):
            break
        cur = fold(rs, item0)
        n = max(1, int(dec.get("sessions") or 1)) if k == 1 else 1
        root = base if k == 1 else base.parent / f"{base.name}-r{k}"
        roots = [root / f"t{t + 1}" if n > 1 else root for t in range(n)]
        if rs.done(skey):
            _recover(name, rs, key, roots, cur, A, evaluator, log, k); ran = True
            continue
        rs.put(skey, cur, {"budget": left, "sessions": n, "roots": [str(r) for r in roots], "round": k})
        outs = []
        for t in range(n):
            o, rep = pp_step(name, dict(cur, spend=0.0), ["replan"], A, evaluator, log, replan_model=fb_model(A, A.replan_model),
                             replan_budget=math.floor(left / n * 1e4) / 1e4, replan_turns=A.replan_turns, replan_args=A.replan_args_full,   # floored: twins' halves never sum past the budget (b63 ledger test)
                             replan_root=str(roots[t]), replan_timeout=A.replan_timeout,
                             replan_runner=runner, cap_usd=0)   # the session's own gate is its budget; the row envelope is the decision's
            outs.append((o, rep))
        spent = round(sum(float(o["spend"]) for o, _ in outs), 4)
        best = max((o for o, _ in outs), key=lambda o: float(o.get("score") or 0))
        rs.put(key, dict(best, spend=round(float(cur.get("spend") or 0) + spent, 4)),
               {"sessions": [dict(rep, score=o.get("score"), spend=o.get("spend")) for o, rep in outs], "spent": spent, "round": k, "budget": left})
        RowLedger(A.run_dir, name).set("sessions", round(float(cur.get("spend") or 0) + spent, 4))
        ran = True
        log(f"{name[:40]}: replan round {k} x{n}: ${spent:.3f} of ${left:.2f}, {cur.get('score')} -> {best.get('score')}")
        for o, rep in outs:
            rc = ((rep.get("stages") or {}).get("replan") or {}).get("returncode")
            if rc not in (0, None):
                tail = (((rep.get("stages") or {}).get("replan") or {}).get("tail") or "").strip().splitlines()
                log(f"{name[:40]}: REPLAN SESSION FAILED rc={rc} (spend ${float(o.get('spend') or 0):.3f}): {tail[-1][:160] if tail else 'no output'}")
    return ran


# ------------------------------------------------------------------------------------------------------- the routed slice (b63 item 16)
def _decision_line(A, rec: dict) -> None:
    with (A.run_dir / "decisions.jsonl").open("a") as f:
        f.write(json.dumps(dict(rec, at=now())) + "\n")


def repair_step(name, rs: RowStore, cur: dict, A, evaluator, log, dec: dict, route: dict, k: int, budget: float) -> dict:
    """One REPAIR slice (harness/repair.py) on the row's current best; step `repair#k`. Every repair step is one decisions.jsonl line of kind
    REPAIR; the spend enters the row ledger under `routes`; a banked result is written back to the ladder's best."""
    key = f"repair#{k}"
    sp = cur.get("state_path")
    if A.dry_run:
        rs.put(key, cur, {"status": "dry run: no model call", "spent": 0.0, "route": dec.get("route")}); return cur
    rs.put(f"{key}_started", cur, {"budget": budget, "route": dec.get("route")})
    t0 = time.time()
    try:
        if REPAIR_RUNNER is not None:
            out = REPAIR_RUNNER(name, cur, route, budget, log)
        else:
            RP = importlib.import_module("harness.repair")
            out = RP.run_repair(name, cur, route, A.route_model, A.route_effort, budget, evaluator, log=log, max_steps=A.route_steps, state_path=sp,
                                run_id=f"repair-{A.run_dir.name}-{k}", shown_path=(Path(sp).parent / "shown.json") if sp else None,
                                trajectory_path=A.run_dir / "trajectories" / f"repair-{safe(name)}-{k}.jsonl",   # full per-call trajectory (house rule)
                                cap_price=getattr(A, "cap_price", "announced"))
    except Exception as e:  # noqa: BLE001  the whole slice budget is assumed spent (a failed call after a billed one cannot be bounded)
        out = {"status": f"error {type(e).__name__}: {str(e)[:160]}", "spend": budget, "item": None, "steps": [], "banked": 0, "holes_filled": 0}
        log(f"{name[:40]}: REPAIR failed ({type(e).__name__}); ${budget:.2f} assumed spent")
    spent = round(float(out.get("spend") or 0), 4)
    # b64 L0: the slice at the cap price; the part above its reported spend enters the row ledger (what decide() and the review budget read)
    extra = round(max(0.0, float(out.get("cap_spend") if out.get("cap_spend") is not None else spent) - spent), 6)
    if extra > 0:
        RowLedger(A.run_dir, name).set(f"cap_extra:repair#{k}", extra)
    for st in out.get("steps") or []:
        _decision_line(A, {"problem": name, "checkpoint": dec.get("checkpoint"), "kind": "REPAIR", "slice": k, "step": st.get("step"), "status": st.get("status"),
                           "spend": st.get("spend"), "banked": bool(st.get("banked")), "gain": st.get("gain"), "holes_filled": st.get("holes_filled"),
                           "edits": len(st.get("edits") or []), "artifact": (st.get("artifact") or {}).get("sha") if isinstance(st.get("artifact"), dict) else None})
    item = out.get("item")
    if item and item.get("proof") and float(item.get("score") or 0) > float(cur.get("score") or 0) + P.MIN_GAIN:
        full = dict(cur, **{k_: item.get(k_) for k_ in ITEM_KEYS if item.get(k_) is not None and k_ not in ("verified", "stage")}, verified=True, stage="repair")
        full["spend"] = round(float(cur.get("spend") or 0) + spent, 4)
        rs.put(key, full, {"status": out.get("status"), "spent": spent, "banked": out.get("banked"), "holes_filled": out.get("holes_filled"),
                           "steps": len(out.get("steps") or []), "seconds": round(time.time() - t0, 1), "gain": round(float(full["score"]) - float(cur.get("score") or 0), 4),
                           "adopted": out.get("adopted"), "route": dec.get("route")})
        if sp and getattr(A, "write_back", True):
            write_back(sp, full, log)
        bank_item(sp, name, full, f"repair#{k}", parent=cur.get("proof"))
        return full
    rs.put(key, dict(cur, spend=round(float(cur.get("spend") or 0) + spent, 4)),
           {"status": out.get("status"), "spent": spent, "banked": out.get("banked"), "holes_filled": out.get("holes_filled"), "steps": len(out.get("steps") or []),
            "seconds": round(time.time() - t0, 1), "adopted": out.get("adopted"), "route": dec.get("route"), "artifact_final": out.get("artifact_final")})
    return dict(cur, spend=round(float(cur.get("spend") or 0) + spent, 4))


def artifact_step(name, rs: RowStore, cur: dict, A, evaluator, log, S, dec: dict, route: dict, k: int, budget: float) -> dict:
    """One ARTIFACT-SESSION (agent.py --artifact; plan §1.1 P): the artifact record goes to <run dir>/artifacts/<ws>.artifact.json, the session
    runs through the re-plan machinery (postpass seed_workspace: best = the row's best, candidate.lean = the artifact) with <= --artifact-turns
    turns and the slice budget; its best is re-verified on every pin by pp_step; step `artifact#k`."""
    AR = importlib.import_module("harness.artifacts")
    key = f"artifact#{k}"
    art = route.get("artifact") or {}
    AR.write_record(A.run_dir / "artifacts", name, art)   # the run's record (logs, readout)
    # the session's copy: with an hx Set the session runs in the arm's container (DockerRunner), which mounts only the worktree, its
    # harness/hwork and probe/runs (hx_heldout.agent_docker): a path under the router's run dir is invisible there and agent.py --artifact
    # would fall back to a plain session (review 2026-10-25); the record goes under the worktree's hwork, beside the session's work root
    adir = (S.wt / "harness/hwork" / f"{S.prefix}-{A.arm}-artifacts-{A.run_dir.name}") if S is not None else (A.run_dir / "artifacts")
    if S is not None:
        AR.write_record(adir, name, art)
    runner = dry_runner if A.dry_run else (DockerRunner(S, A) if (S is not None and A.agent_docker) else REPLAN_RUNNER)
    base = (S.wt / "harness/hwork" / f"{S.prefix}-{A.arm}-artifact-{A.run_dir.name}") if S is not None else (A.run_dir / "artifact")
    root = base if k == 1 else base.parent / f"{base.name}-r{k}"
    if rs.done(f"{key}_started"):   # killed mid-session: its spend counts, its best is re-checked
        _recover(name, rs, key, [root], cur, A, evaluator, log, k); return fold(rs, inp0(rs))
    rs.put(f"{key}_started", cur, {"budget": budget, "root": str(root), "route": dec.get("route"), "artifact": art.get("sha")})
    args = (getattr(A, "artifact_args", ARTIFACT_ARGS) + (f" --auto-brief {A.auto_brief_dir}" if getattr(A, "auto_brief_dir", None) else "")
            + f" --artifact {adir if adir.is_absolute() else ROOT / adir}").strip()
    o, rep = pp_step(name, dict(cur, spend=0.0), ["replan"], A, evaluator, log, replan_model=fb_model(A, A.artifact_model or A.replan_model), replan_budget=math.floor(budget * 1e4) / 1e4,
                     replan_turns=A.artifact_turns, replan_args=args, replan_root=str(root), replan_timeout=A.replan_timeout, replan_runner=runner, cap_usd=0)
    spent = round(float(o.get("spend") or 0), 4)
    rec = {"session": dict(rep, score=o.get("score"), spend=o.get("spend")), "spent": spent, "budget": budget, "route": dec.get("route"), "artifact": art.get("sha"),
           "turns": A.artifact_turns}
    out = dict(o, spend=round(float(cur.get("spend") or 0) + spent, 4))
    rs.put(key, out, rec)
    _decision_line(A, {"problem": name, "checkpoint": dec.get("checkpoint"), "kind": "ARTIFACT-SESSION", "slice": k, "spend": spent, "artifact": art.get("sha"),
                       "holes": len(art.get("holes") or []), "score_in": cur.get("score"), "score_out": o.get("score"), "status": ((rep.get("stages") or {}).get("replan") or {}).get("returncode")})
    log(f"{name[:40]}: ARTIFACT-SESSION {k}: ${spent:.3f} of ${budget:.2f}, {cur.get('score')} -> {o.get('score')}")
    if o.get("stage") not in (None, "input") and cur.get("state_path") and getattr(A, "write_back", True) and float(o.get("score") or 0) > float(cur.get("score") or 0) + P.MIN_GAIN:
        write_back(cur.get("state_path"), out, log)
    bank_item(cur.get("state_path"), name, out, f"artifact#{k}", parent=cur.get("proof"))
    return out


def route_rounds(name, rs, item0, A, evaluator, log, S, dec) -> bool:
    """The routed paid slice (plan §1.1 P): one REPAIR or ARTIFACT-SESSION step at <= --route-budget, then a second routed step only if the first
    banked >= ROUTE_SECOND_GAIN and the room left is >= ROUTE_SECOND_ROOM (the artifacts re-read: the first step may have changed them).
    Returns True when a step ran in this call."""
    AR = importlib.import_module("harness.artifacts")
    ran = False
    total = float(dec.get("budget") or 0)
    led = RowLedger(A.run_dir, name)
    for k in (1, 2):
        key = f"{'repair' if dec.get('kind') == 'repair' else 'artifact'}#{k}"
        if rs.done(key) or rs.done(f"repair#{k}") or rs.done(f"artifact#{k}"):
            continue
        cur = fold(rs, item0)
        spent_so_far = sum(float((rs.d["steps"].get(x) or {}).get("report", {}).get("spent") or 0) for x in (f"repair#{j}" for j in (1, 2))) \
            + sum(float((rs.d["steps"].get(x) or {}).get("report", {}).get("spent") or 0) for x in (f"artifact#{j}" for j in (1, 2)))
        # b64 L0 review: the slice budget is in cap-price dollars; a REPAIR step's report holds its list spend, the ledger the difference
        spent_so_far += sum(float(led.d["sources"].get(f"cap_extra:repair#{j}") or 0) for j in (1, 2))
        room = round(min(total - spent_so_far, A.cap * A.target_frac - A.review_reserve - max(float(cur.get("spend") or 0), led.total())), 4)
        if k == 1:
            route = {"kind": dec.get("kind"), "reason": (dec.get("route") or {}).get("reason")}
            arts = AR.read(rs.path.with_name(rs.path.stem + ".cpu_pass.json"))
            full = AR.route_for(arts, best_sha=AR.sha(cur["proof"]) if cur.get("proof") else None)
            if full.get("kind") != dec.get("kind"):   # the artifacts changed since the decision (a resume): the decision's kind stands only with its artifact
                sel = {"artifact": next((s for s in arts.get("skeletons") or [] if s.get("sha") == (dec.get("route") or {}).get("artifact")), None),
                       "near_misses": [n for n in arts.get("near_misses") or [] if n.get("sha") in ((dec.get("route") or {}).get("near_misses") or [])]}
                if sel["artifact"] is None and not sel["near_misses"]:
                    rs.put(key, cur, {"status": "skipped: the decision's artifact is no longer in the row's artifacts", "spent": 0.0}); return ran
                route.update(sel)
            else:
                route = full
        else:
            prev = rs.d["steps"].get(f"repair#1") or rs.d["steps"].get("artifact#1") or {}
            started = rs.d["steps"].get("repair#1_started") or rs.d["steps"].get("artifact#1_started")
            if (prev.get("report") or {}).get("gain") is not None:
                gain = float(prev["report"]["gain"])
            elif started:
                gain = float((prev.get("item") or {}).get("score") or 0) - float((started.get("item") or {}).get("score") or 0)
            else:   # review 2026-10-25: the first step never started (skipped: no budget / its artifact gone); on a resume this read the
                gain = 0.0   # whole score as the first step's gain (score - 0) and could fund a second step the rule never allowed
            if gain < ROUTE_SECOND_GAIN or room < ROUTE_SECOND_ROOM:
                log(f"{name[:40]}: no second routed step (first gained +{gain:.2f}, room ${room:.2f})"); break
            arts = AR.read(rs.path.with_name(rs.path.stem + ".cpu_pass.json"))
            used = {(prev.get("report") or {}).get("route", {}).get("artifact")} | set((prev.get("report") or {}).get("route", {}).get("near_misses") or [])
            arts = {k_: [x for x in v_ if x.get("sha") not in used] for k_, v_ in arts.items()}   # the first step's artifact is spent
            route = AR.route_for(arts, best_sha=AR.sha(cur["proof"]) if cur.get("proof") else None)
            if not route.get("kind"):
                log(f"{name[:40]}: no second routed step (no artifact left)"); break
            dec = dict(dec, kind=route["kind"], route={"kind": route["kind"], "reason": route["reason"], "artifact": (route.get("artifact") or {}).get("sha"),
                                                       "near_misses": [x.get("sha") for x in route.get("near_misses") or []]})
            key = f"{'repair' if route['kind'] == 'repair' else 'artifact'}#{k}"
        budget = round(min(float(getattr(A, "route_budget", ROUTE_BUDGET)), room), 4)
        if (budget < SESSION_FLOOR and dec.get("kind") == "artifact-session") or budget < 0.05:
            rs.put(key, cur, {"status": f"skipped: ${budget:.2f} left for the routed step", "spent": 0.0}); break
        if dec.get("kind") == "repair":
            out = repair_step(name, rs, cur, A, evaluator, log, dec, route, k, budget)
        else:
            out = artifact_step(name, rs, cur, A, evaluator, log, S, dec, route, k, budget)
        # b64 L0 review: repair_step registers the slice's cap-price difference (cap_extra:repair#k) through its own RowLedger; re-read the
        # file, or this instance's older copy is written over it below and decide() / the review budget lose the difference
        led = RowLedger(A.run_dir, name)
        led.set("sessions", float(out.get("spend") or 0))   # the fold's spend carries the routed step (one shared ledger, contract §2)
        ran = True
    return ran


# ----------------------------------------------------------------------------------------------------------------- twins (b63 item 17)
MAX_TWIN_ROUNDS = 3       # twin sessions from the checkpoint best until the twin budget is used (a round that spent < MIN_ROUND_SPEND ends it)
TWIN_SLOTS = threading.Semaphore(1)   # review 2026-10-25: post_row runs --jobs rows at once (v3: 3); twin sessions run one at a time per
                                      # router (= per arm), as the ladder's --workers 1 (Azure: 2 Sol sessions in all for the two arms)


def twin_rounds(name, rs, item0, A, evaluator, log, S, dec) -> bool:
    """The second lineage (plan §4.1 item 17): agent.py sessions in a fresh work root seeded with the row's checkpoint best B0 (the item of
    step `twin_seed`; postpass.seed_workspace, NOT hx_heldout.fresh_round, which starts an empty workspace from the reference), the
    ladder's flags (--twin-args), the decision's `twin_budget` in all, each round's budget floored so the rounds never sum past it. Spend
    goes to the row's shared ledger under `twin:<k>`; the session's best is banked (bank.jsonl source `twin:<k>`) and recorded as step
    `twin#k` (verified after a full measurement, as a re-plan round). Returns True when a round ran in this call."""
    runner = dry_runner if A.dry_run else (DockerRunner(S, A) if (S is not None and A.agent_docker) else REPLAN_RUNNER)
    base = (S.wt / "harness/hwork" / f"{S.prefix}-{A.arm}-twin-{A.run_dir.name}") if S is not None else (A.run_dir / "twin")
    total, ran = float(dec.get("twin_budget") or 0), False
    seed = rs.item("twin_seed") if rs.done("twin_seed") else fold(rs, item0)
    led = RowLedger(A.run_dir, name)
    for k in range(1, MAX_TWIN_ROUNDS + 1):
        key, skey = f"twin#{k}", f"twin_started#{k}"
        if rs.done(key):
            continue
        prior = [rs.d["steps"][f"twin#{j}"]["report"] for j in range(1, k) if rs.done(f"twin#{j}")]
        left = math.floor((total - sum(float(r.get("spent") or 0) for r in prior)) * 1e4) / 1e4
        cur = fold(rs, item0)
        # review 2026-10-25: the twin budget was split at the decision; the ladder lineage ran its top phase since (a session can overshoot
        # its rung by one call), so the round is also bounded by the row's LIVE room (the fold's spend holds the ladder lineage and every
        # earlier twin round): ladder + twins never pass target - reserve, whatever the ladder did
        live = math.floor((A.cap * getattr(A, "target_frac", TARGET_FRAC) - getattr(A, "review_reserve", REVIEW_RESERVE)
                           - max(float(cur.get("spend") or 0), led.total())) * 1e4) / 1e4
        if live < left:
            log(f"{name[:40]}: twin round {k}: budget ${left:.4f} cut to the live room ${live:.4f}")
            left = live
        if left < SESSION_FLOOR or (k > 1 and float((prior[-1] if prior else {}).get("spent") or 0) < MIN_ROUND_SPEND):
            break
        start = seed if k == 1 else max((rs.item(f"twin#{j}") for j in range(1, k)), key=lambda o: float(o.get("score") or 0))   # the lineage resumes from its own best
        if float(start.get("score") or 0) < float(seed.get("score") or 0):
            start = seed
        root = base / f"t{k}"
        if rs.done(skey):   # killed mid-session: count what it spent, keep its best (against the lineage's own start) after a full check, never re-run it
            spent, best = 0.0, None
            f = root / safe(name) / "state.json"
            if f.exists():
                st = json.loads(f.read_text()); spent = round(float(st.get("api_spend") or 0), 4); best = st.get("best") or {}
            item, kept = dict(cur, spend=round(float(cur.get("spend") or 0) + spent, 4)), False
            if best and best.get("proof") and float(best.get("score") or 0) > float(start.get("score") or 0) + P.MIN_GAIN and best["proof"].strip() != (start.get("proof") or "").strip():
                out, _ = pp_step(name, {"proof": best["proof"], "spend": item["spend"]}, [], A, evaluator, log)   # a full measurement of the session's best
                if out.get("verified") and float(out.get("score") or 0) > float(start.get("score") or 0) + P.MIN_GAIN:
                    item, kept = dict(out, spend=item["spend"]), True
                    bank_item(seed.get("state_path") or cur.get("state_path"), name, out, f"twin:{k}", parent=start.get("proof"))
            rs.put(key, item, {"status": "interrupted", "spent": spent, "round": k, "kept_session_best": kept, "roots": [str(root)],
                               "seed_sha": _sha12(seed.get("proof")), "seed_score": seed.get("score"), "lineage": "twin"})
            led.set(f"twin:{k}", spent); ran = True
            log(f"{name[:40]}: twin round {k} was interrupted; its spend ${spent:.3f} counted" + ("; its best kept after a full check" if kept else ""))
            continue
        with TWIN_SLOTS:
            rs.put(skey, cur, {"budget": left, "sessions": 1, "roots": [str(root)], "round": k, "seed_sha": _sha12(seed.get("proof"))})
            o, rep = pp_step(name, dict(start, spend=0.0), ["replan"], A, evaluator, log, replan_model=fb_model(A, A.replan_model), replan_budget=left,
                             replan_turns=A.twin_turns, replan_args=A.twin_args_full, replan_root=str(root), replan_timeout=A.replan_timeout,
                             replan_runner=runner, cap_usd=0)
        spent = round(float(o.get("spend") or 0), 4)
        rs.put(key, dict(o, spend=round(float(cur.get("spend") or 0) + spent, 4)),
               {"sessions": [dict(rep, score=o.get("score"), spend=o.get("spend"))], "spent": spent, "round": k, "budget": left, "roots": [str(root)],
                "seed_sha": _sha12(seed.get("proof")), "seed_score": seed.get("score"), "lineage": "twin"})
        led.set(f"twin:{k}", spent)
        bank_item(seed.get("state_path") or cur.get("state_path"), name, o, f"twin:{k}", parent=start.get("proof"))
        ran = True
        log(f"{name[:40]}: twin round {k}: ${spent:.3f} of ${left:.2f}, B0 {seed.get('score')} -> {o.get('score')}")
        rc = ((rep.get("stages") or {}).get("replan") or {}).get("returncode")
        if rc not in (0, None):
            tail = (((rep.get("stages") or {}).get("replan") or {}).get("tail") or "").strip().splitlines()
            log(f"{name[:40]}: TWIN SESSION FAILED rc={rc} (spend ${spent:.3f}): {tail[-1][:160] if tail else 'no output'}")
    return ran


def _sha12(text) -> str | None:
    from harness import bank as BK
    return BK.sha(text) if text else None


def select_lineages(lineages: list, within: float = TWIN_WITHIN, statement: str | None = None) -> dict:
    """SELECT (plan §1.2; bank.runner_up): `lineages` = [{"label", "proof", "score", ...}] (the ladder lineage's best and each twin's best).
    The best by score goes on; the runner-up is kept only if it is within `within` points AND of another structural class (bank.class_tag,
    cut at the row's `statement`: _tag); every other lineage is dropped. Pure; reasons per lineage."""
    from harness import bank as BK
    ls = [dict(l, klass=_tag(statement, l["proof"])) for l in lineages if l.get("proof") and l.get("score") is not None]
    if not ls:
        return {"best": None, "kept": [], "dropped": [], "reasons": {}, "classes": {}}
    ls.sort(key=lambda l: (-float(l["score"]), l["label"]))
    best, reasons, kept = ls[0], {ls[0]["label"]: f"best ({float(ls[0]['score']):.2f}, {ls[0]['klass']})"}, []
    ru = None
    for l in ls[1:]:
        gap = float(best["score"]) - float(l["score"])
        if l["proof"].strip() == best["proof"].strip():
            reasons[l["label"]] = "same proof as the best"
        elif gap > within + 1e-9:
            reasons[l["label"]] = f"dropped: {gap:.2f} below the best > {within:g}"
        elif l["klass"] == best["klass"]:
            reasons[l["label"]] = f"dropped: same structural class as the best ({l['klass']}) at {gap:.2f} below"
        elif ru is not None:
            reasons[l["label"]] = f"dropped: a runner-up of another class is already kept ({ru['label']})"
        else:
            ru = l; reasons[l["label"]] = f"kept: runner-up {gap:.2f} below the best, class {l['klass']} vs {best['klass']}"
            kept.append(l)
    return {"best": best, "kept": kept, "dropped": [l for l in ls[1:] if l is not ru], "reasons": reasons,
            "classes": BK.class_spread([{"klass": l["klass"]} for l in ls])}


def select_step(name, rs: RowStore, item0: dict, A, log, dec) -> None:
    """After the twin rounds: the lineages' bests (the ladder lineage = step ladder_top, else the checkpoint best; each twin#k) through
    select_lineages; one decisions.jsonl line (kind select, the reasons) and step `select` (item = the best lineage's item; report = kept /
    dropped). A kept runner-up becomes step `select_runner_up` (verified, lower: the fold ignores it, the crossover and the end stage read
    it as a parent)."""
    if rs.done("select"):
        return
    seed = rs.item("twin_seed") if rs.done("twin_seed") else item0
    lad = rs.item("ladder_top") if rs.done("ladder_top") and (rs.item("ladder_top") or {}).get("proof") else seed
    lineages = [dict(lad, label="ladder")] + [dict(rs.item(k), label=k) for k in sorted(rs.d["steps"]) if re.match(r"twin#\d+$", k) and (rs.item(k) or {}).get("proof")]
    sel = select_lineages(lineages, TWIN_WITHIN, (LT.ROWS.get(name) or {}).get("statement"))
    best = sel["best"] or dict(seed, label="seed")
    # contract §2 (monitoring the equal-spend question on a live --twins run): what each lineage spent after the decision
    s0 = float(seed.get("spend") or 0)
    lspend = {"ladder": round(max(0.0, float((rs.item("ladder_top") if rs.done("ladder_top") else seed).get("spend") or 0) - s0), 4)}
    for k in sorted(rs.d["steps"]):
        if re.match(r"twin#\d+$", k):
            lspend[k] = round(float((rs.d["steps"][k].get("report") or {}).get("spent") or 0), 4)
    spend = round(max(float(fold(rs, item0).get("spend") or 0), RowLedger(A.run_dir, name).total()), 4)
    room = round(A.cap * getattr(A, "target_frac", TARGET_FRAC) - getattr(A, "review_reserve", REVIEW_RESERVE) - spend, 4)
    rep = {"best": best["label"], "kept": [l["label"] for l in sel["kept"]], "dropped": [l["label"] for l in sel["dropped"]], "reasons": sel["reasons"],
           "classes": sel["classes"], "within": TWIN_WITHIN, "scores": {l["label"]: l.get("score") for l in lineages},
           "seed_score": seed.get("score"), "seed_spend": round(s0, 4), "lineage_spend": lspend}
    item = {k: v for k, v in best.items() if k not in ("label", "klass")}
    rs.put("select", dict(item, spend=float(fold(rs, item0).get("spend") or 0)), rep)
    for l in sel["kept"]:
        rs.put("select_runner_up", {k: v for k, v in l.items() if k not in ("label", "klass")} | {"spend": float(fold(rs, item0).get("spend") or 0), "stage": "twin-runner-up"},
               {"label": l["label"], "reason": sel["reasons"][l["label"]]})
    line = {"problem": name, "checkpoint": "select", "budget_at": dec.get("budget_at"), "at": now(), "policy": dec.get("policy"), "tier": "none",
            "kind": "select", "plateau": dec.get("plateau"), "reason": "; ".join(f"{k}: {v}" for k, v in sel["reasons"].items()) or "no lineage with a proof",
            "budget": 0.0, "sessions": 0, "inputs": {"scores": rep["scores"], "classes": sel["classes"], "within": TWIN_WITHIN, "seed_score": seed.get("score"),
                                                     "spend": spend, "room": room, "lineage_spend": lspend}}
    with (A.run_dir / "decisions.jsonl").open("a") as f:
        f.write(json.dumps(line) + "\n")
    log(f"{name[:40]}: select: best {best['label']} ({best.get('score')}), kept {rep['kept']}, dropped {rep['dropped']}")


# ------------------------------------------------------------------------------------------------------------ the end stage (B62b)
def end_floors(rs: RowStore, item0: dict) -> dict:
    """{label: item}: the row's best after each checkpoint cleanup (the fold through clean@k) and the review output (the fold through every
    step). The end stage reads each on its meter and never returns below them there."""
    cur, out = dict(item0), {}
    for k, st in rs.d["steps"].items():
        cur = better(st["item"], cur)
        if CHECKPOINT_STEP.match(k):
            out[k] = cur
    out["review"] = cur
    return {k: {x: v[x] for x in ("proof", "score", "tokens", "heartbeats", "stage") if v.get(x) is not None} for k, v in out.items() if v.get("proof")}


def end_pool(rs: RowStore) -> list:
    """The run's own candidates, parsed: <arm work root>/<ws>/pool.jsonl (agent.py --pool, the ladder's sessions) and the same file in every
    re-plan round's root (golf sessions run there); [] in the generic mode or with the pool off."""
    files = []
    for st in rs.d["steps"].values():
        sp = (st.get("item") or {}).get("state_path")
        if sp:
            files += [Path(sp).parent / f for f in POOL_FILES]
        for r in (st.get("report") or {}).get("roots") or []:
            files += [Path(r) / safe(rs.d["problem"]) / f for f in POOL_FILES]
    lines = []
    for f in dict.fromkeys(files):
        try:
            text = f.read_text()
        except OSError:
            continue
        for l in text.splitlines():
            try:
                d = json.loads(l)
            except ValueError:
                continue
            if isinstance(d, dict):
                lines.append(d)
    return lines


def end_guard(name, cur, item, evaluator, end_meter: str | None = None) -> dict:
    """The router's own check that the end stage never lowers the final (its floors already include the review output on its meter): the
    review output and the end output read back to back on the router's evaluator, every pin. Passes when the end output compiles on every
    pin the review output does and its exact score is not lower by more than HB_EPS heartbeats are worth on this row (the meter's repeat
    spread, scorer/accept.py: a bank may be a few heartbeats); when the evaluator reads neither, the end stage's own meter (its lake
    fallback) decides. Two full measurements, only on a row whose end output differs from the review output."""
    if end_meter == "lake":   # review 2026-10-21: the self-test rejected the direct path, so the evaluator's verdict would contradict it
        return {"ok": True, "why": "the end stage ran on the lake meter (self-test fallback): its paired verdict decides", "delta": None}
    versions = P.newest_first(LT.ROWS[name]["version_info"])
    ev = (evaluator() if callable(evaluator) and not hasattr(evaluator, "bound") else evaluator).bound(name, versions)
    a, b = ev(cur["proof"], True), ev(item["proof"], True)
    va, vb = P._valid(a, versions, True), P._valid(b, versions, True)
    ref = local_reference_heartbeats(name) or LT.HBS.get(name)
    tol = HB_EPS * 100.0 / ref / 3.0 if ref else 0.0   # H is linear in heartbeats: (ref - hb) / ref x 100
    ex = lambda m: exact_score(len_pct(LT.ROWS[name]["proof_length"], int(m["tokens"])), hb_pct_local(name, int(m["heartbeats"]), LT.HBS.get(name)),
                               float(m["Z"]))   # noqa: E731  (unrounded: the evaluator's L/H are rounded to 0.01, coarser than tol on big rows)
    ea = eb = None
    if va and vb:
        ea, eb = ex(a), ex(b)
        ok = float(b["Z"]) >= float(a["Z"]) - 1e-9 and eb >= ea - tol - 1e-9
        why = f"back to back: end {eb:.4f} vs review {ea:.4f} (spread {tol:.4f})"
    elif vb:
        ok, why = True, "the review output fails the full check on the evaluator"
    elif not va:
        ok, why = True, "the evaluator reads neither: the end stage's meter decides"
    else:
        ok, why = False, "the end output fails the full check on the evaluator"
    return {"ok": ok, "why": why, "review": P._metrics(a), "end": P._metrics(b), "spread": round(tol, 6),
            "delta": None if ea is None else round(eb - ea, 6)}


def end_stage_kwargs(A, E) -> dict:
    """endstage.end_stage's method arguments: --end-k / --end-max-compiles (the B62b stage), or with --end-config (2026-10-22) the frozen
    config's families, budgets, caps, screening and t3 suggestions, mapped exactly as `endstage.py --config` maps them. The file must still
    have the sha256 frozen at the run's start."""
    if not getattr(A, "end_config", None):
        return {"k": A.end_k, "max_compiles": A.end_max_compiles}
    v, rec = E.load_config(A.end_config)
    if getattr(A, "end_config_sha256", None) and rec.get("config_sha256") != A.end_config_sha256:
        raise RuntimeError(f"--end-config {A.end_config} changed since the run started (sha {A.end_config_sha256[:12]})")
    ns = argparse.Namespace(**{**vars(E.build_parser().parse_args(["--run-dir", "x"])), **v})
    E.normalize_method(ns, E.families_for(ns.sweep, ns.tools))
    return {"k": ns.k, "sweep": ns.sweep, "crossover": ns.crossover, "max_compiles": ns.max_compiles, **E.end_kwargs(ns)}


def _cut_before(rs: RowStore, keys: tuple) -> "RowStore | None":
    """b65: a read-only view of the row's steps before the first of `keys` (its put() is never called); None when none of them ran."""
    order = list(rs.d["steps"])
    at = [order.index(k) for k in keys if k in rs.d["steps"]]
    if not at:
        return None
    v = RowStore.__new__(RowStore)
    v.path, v.d = None, {"problem": rs.d["problem"], "steps": {k: rs.d["steps"][k] for k in order[:min(at)]}}
    return v


def _end_meter(E, row: dict, seed: str, rlog):
    """The row's end-stage meter (the router's log, masked under --anon, also for its self-test)."""
    meter = E.Meter(row, dict(LT.HBS), **({"log": rlog} if "log" in inspect.signature(E.Meter).parameters else {}))
    if hasattr(meter, "self_test"):
        meter.self_test(seed)   # the run-start self-test: once per (source, pin) in the run, cached inside endstage
    return meter


def _verified(res: dict) -> bool:
    ok = bool(res["verified"]) if "verified" in res else res.get("stage") not in (None, "unmeasured")
    return ok and isinstance(res.get("proof"), str) and bool(res["proof"].strip())


def _reading(m: dict) -> dict | None:
    if not (isinstance(m, dict) and m.get("ok") and m.get("heartbeats") is not None and P._finite(m.get("score_exact"))):
        return None
    return {"score": float(m["score_exact"]), "tokens": int(m["tokens"]), "heartbeats": int(m["heartbeats"]), "Z": float(m.get("Z", 100.0))}


def dual_pick(res: dict, res_pre: dict, meter) -> tuple[dict, dict]:
    """b65 dual start: the end output from the review output (`res`) or the one from the review's input (`res_pre`). Ties go to `res`: the
    pre-review one is kept only when it is verified and either `res` is not, or both read back to back on the end stage's meter (all pins,
    `res` first) and scorer/accept.decide banks it over `res`. Returns (the kept result, a report)."""
    from scorer.accept import decide
    rep = {"pre_stage": res_pre.get("stage"), "pre_compiles": res_pre.get("compiles"), "picked": "review"}
    a, b = _verified(res), _verified(res_pre)
    if not b:
        return res, dict(rep, why="the pre-review start is not verified")
    if not a:
        return res_pre, dict(rep, picked="pre-review", why="the review start is not verified")
    if res["proof"].strip() == res_pre["proof"].strip():
        return res, dict(rep, why="both starts end on the same proof")
    if not hasattr(meter, "measure"):
        return res, dict(rep, why="the meter cannot read back to back: the review start stays")
    ra, rb = meter.measure(res["proof"], full=True), meter.measure(res_pre["proof"], full=True)
    rep["paired"] = {"review": ra.get("score_exact"), "pre": rb.get("score_exact"),
                     "compiles": int(ra.get("compiles") or 0) + int(rb.get("compiles") or 0)}
    ia, ib = _reading(ra), _reading(rb)
    if ib is None:
        return res, dict(rep, why="the pre-review output does not read on the meter")
    if ia is None:
        return res_pre, dict(rep, picked="pre-review", why="the review start's output does not read on the meter")
    ok, why = decide(ia, ib)
    return (res_pre, dict(rep, picked="pre-review", why=why)) if ok else (res, dict(rep, why=why))


def end_run(name, rs: RowStore, item0: dict, A, E, meter, rlog, dual: bool = False) -> tuple[dict, dict]:
    """One row's end stage from the row's steps (the B62b call), and with dual (b65, --end-dual-start) a second one from the review's input
    (the steps before review_started / review, pool lines the review or an end step banked left out, its own floors), kept by dual_pick.
    Returns (the end stage's result, the report's facts)."""
    row = LT.ROWS[name]
    seed = (row.get("src") or item0.get("proof") or "").strip()
    pool, floors = end_pool(rs), end_floors(rs, item0)
    cands = E.collect(name, steps=rs.d["steps"], pool_lines=pool, seed=seed)
    kw = end_stage_kwargs(A, E)
    res = dict(E.end_stage(row, seed, cands, meter, checkpoint_bests=floors, log=rlog, **kw) or {})
    rep = {"candidates": len(cands), "pool_lines": len(pool), "floors": list(floors)}
    if not dual:
        return res, rep
    pre = _cut_before(rs, ("review_started", "review"))
    rv = (rs.d["steps"].get("review") or {}).get("item") or {}
    if pre is None or not rv.get("proof"):
        return res, dict(rep, dual={"status": "no review output: one start"})
    p0 = fold(pre, item0)
    ps = rs.d["steps"].get("presweep") or {}   # the review's input (--sweep-before-review: the swept proof, also when the review was skipped)
    r_in = ((rs.d["steps"].get("review_started") or {}).get("item")
            or (ps.get("item") if (ps.get("report") or {}).get("adopted") else None) or p0)
    if (rv.get("proof") or "").strip() == (r_in.get("proof") or "").strip():
        return res, dict(rep, dual={"status": "the review left its input unchanged: one start"})
    pool_pre = [x for x in pool if not str(x.get("source") or "").startswith(("review", "end"))]
    cands_pre = E.collect(name, steps=pre.d["steps"], pool_lines=pool_pre, seed=seed)
    floors_pre = end_floors(pre, item0)
    if r_in.get("proof") and r_in["proof"].strip() != (p0.get("proof") or "").strip():   # below the fold's bar: still a floor of this start
        floors_pre["review_input"] = {x: r_in[x] for x in ("proof", "score", "tokens", "heartbeats", "stage") if r_in.get(x) is not None}
    res_pre = dict(E.end_stage(row, seed, cands_pre, meter, checkpoint_bests=floors_pre, log=lambda m: rlog(f"[pre-review start] {m}"),
                               **kw) or {})
    out, d = dual_pick(res, res_pre, meter)
    d.update(status="two starts", pre_candidates=len(cands_pre), pre_pool_lines=len(pool_pre))
    rlog(f"end: dual start: kept the {d['picked']} start ({d['why']})")
    return out, dict(rep, dual=d)


def end_step(name, rs: RowStore, item0: dict, A, evaluator, log) -> None:
    """B62b, after the review: one end stage on the row ($0). Records step `end`: the end stage's output when it is verified (an `unmeasured`
    pick is not) and end_guard passes (report adopted=True), else the review output (adopted=False); the report keeps the stage's
    decisions. A row whose end stage raises records nothing (guarded() logs it; a resume tries again). b65 --end-dual-start: end_run's
    second start from the review's input, the better of the two by the end stage's own meter (report "dual")."""
    E = importlib.import_module("harness.endstage")   # lazy: a run without --end-stage never imports it
    t_end0 = time.time()   # b84: the approach pick's cap sits inside the end stage's own clock, counted from here
    cur = fold(rs, item0)
    row = LT.ROWS[name]
    rlog = lambda m: log(f"{name[:40]}: {m}")   # noqa: E731  the router's log (masked under --anon), also for the meter's self-test
    meter = _end_meter(E, row, (row.get("src") or item0.get("proof") or "").strip(), rlog)
    res, facts = end_run(name, rs, item0, A, E, meter, rlog, dual=bool(getattr(A, "end_dual_start", False)))
    m = res["metrics"] if isinstance(res.get("metrics"), dict) else res
    item = {k: m[k] for k in (*ITEM_KEYS, "score_exact", "meter") if m.get(k) is not None and k not in ("proof", "stage", "verified")}
    verified = bool(res["verified"]) if "verified" in res else res.get("stage") not in (None, "unmeasured")
    item.update(proof=res.get("proof"), verified=verified, stage=f"end:{res.get('stage')}", spend=float(cur.get("spend") or 0))
    rep = {"stage": res.get("stage"), **facts,
           "end": json.loads(json.dumps({k: v for k, v in res.items() if k not in ("proof", "metrics")}, default=str))}
    if not (verified and isinstance(item["proof"], str) and item["proof"].strip() and P._finite(item.get("score"))):
        rep.update(adopted=False, status="not verified: the review output stays")
    elif item["proof"].strip() == (cur.get("proof") or "").strip():
        rep.update(adopted=False, status="the end stage kept the review output")
    else:
        g = end_guard(name, cur, item, evaluator, end_meter=res.get("meter"))
        rep.update(adopted=g["ok"], guard=g, status="adopted" if g["ok"] else "the review output stays: " + g["why"])
        if g["ok"] and g.get("delta") is not None and P._finite(cur.get("score")):
            # review 2026-10-21: the final leaves on the review output's (stored) scale plus the same-meter delta, like postpass
            item["measured_score"], item["score"] = item.get("score"), round(float(cur["score"]) + g["delta"], 2)
    end_item = item
    if approach_on(A):   # b84: after the incumbent's polish, the best-stored OTHER approach group polished and picked (accept-gated, $0)
        inc = item if rep["adopted"] else cur
        new, ap = approach_step(name, rs, item0, A, E, meter, evaluator, inc, cur, res, t_end0, rlog)
        rep["approach"] = ap
        if new is not None:
            rep.update(adopted=True, end_status=rep.get("status"), status=f"approach pick: {ap.get('status')}")
            item = new
        else:
            rlog(f"end: approach pick: {ap.get('status')}")   # an acceptance is logged by approach_step; the end line below says it too
    rs.put("end", item if rep["adopted"] else cur, rep)
    if rep["adopted"]:
        if item is not end_item and (rep.get("guard") or {}).get("ok"):   # the end output was adopted too: banked as before
            bank_item(cur.get("state_path"), name, end_item, f"end:{res.get('stage')}", parent=cur.get("proof"))
        bank_item(cur.get("state_path"), name, item, item.get("stage") or f"end:{res.get('stage')}", parent=cur.get("proof"))
    log(f"{name[:40]}: end {res.get('stage')}: {rep['status']} ({cur.get('score')} -> {item.get('score') if rep['adopted'] else cur.get('score')}, "
        f"{(rep['end'] or {}).get('compiles', '?')} compiles)")


# ---------------------------------------------------------------------------------------------------------------- approach pick (b84)
# docs/b84_polish_before_pick.md section 3 (2026-10-30: the 1-extra-approach variant with a time cap):
# --end-approach on adds harness/approach_pick.py to the end step: after the incumbent's polish, the best-stored OTHER approach group (g1)
# polished by the run's own $0 end stage in a child process under a hard per-row wall cap inside the end stage's clock, then picked over
# the incumbent only when it reads higher back to back on the end-stage meter and on the confirm read (Z 100, static check, axiom audit).
# Off by default: config.json gets no key and no code of the module runs.
APPROACH_GROUPS, APPROACH_SECONDS = 1, 1200.0


def approach_on(A) -> bool:
    return getattr(A, "end_approach", "off") == "on"


def approach_config(A) -> dict | None:
    """The pick's frozen settings (config.json "end_approach", written only when on: a run without it has no key)."""
    if not approach_on(A):
        return None
    return {"groups": int(A.end_approach_groups), "seconds": float(A.end_approach_seconds)}


def approach_args_check(A) -> str | None:
    """The approach-pick flags before the run dir or the config: the refusal text, else None."""
    g, sec = getattr(A, "end_approach_groups", APPROACH_GROUPS), getattr(A, "end_approach_seconds", APPROACH_SECONDS)
    if not approach_on(A):
        if g != APPROACH_GROUPS or sec != APPROACH_SECONDS:
            return "--end-approach-groups and --end-approach-seconds are --end-approach on options"
        return None
    if not getattr(A, "end_stage", False) or not getattr(A, "end_config", None):
        return "--end-approach on needs --end-stage with --end-config (the polish is the run's end stage)"
    if not (isinstance(g, int) and g >= 1):
        return f"--end-approach-groups {g}: an integer >= 1"
    if not (isinstance(sec, (int, float)) and math.isfinite(sec) and sec > 0):
        return f"--end-approach-seconds {sec}: a finite number of seconds > 0"
    return None


def end_clock_s(A, E) -> float | None:
    """The end stage's own wall clock for one row: the end config's sweep phase seconds + tool phase seconds (r10: 1800 + 1800); None when
    the config gives none."""
    try:
        kw = end_stage_kwargs(A, E)
    except Exception:  # noqa: BLE001
        return None
    a, b = kw.get("max_seconds"), kw.get("tools_max_seconds")
    b = a if b is None else b
    return float(a) + float(b) if P._finite(a) and P._finite(b) else None


def approach_step(name, rs: RowStore, item0: dict, A, E, meter, evaluator, inc: dict, cur: dict, res: dict, t_end0: float, rlog) -> tuple:
    """b84: the end step's approach pick (harness/approach_pick.py module docstring). `inc` is the end step's incumbent (its adopted output,
    else the review output `cur`), `res` the end stage's result. Returns (the accepted item, the report) or (None, the report): the
    incumbent stays. Never raises; no model call."""
    import harness.approach_pick as AP
    from scorer.accept import decide
    from harness import final_writer as FW
    cfg = approach_config(A)
    rep: dict = {"config": cfg, "accepted": False}
    t0 = time.time()
    try:
        row = LT.ROWS[name]
        seed = (row.get("src") or item0.get("proof") or "").strip()
        inc_proof = (inc.get("proof") or "").strip()
        if A.dry_run:
            return None, dict(rep, status="skipped (dry run)")
        if not inc_proof:
            return None, dict(rep, status="skipped: no incumbent proof")
        clock = end_clock_s(A, E)
        used = time.time() - t_end0
        cap = float(cfg["seconds"]) if clock is None else min(float(cfg["seconds"]), clock - used)
        rep.update(clock_s=clock, end_used_s=round(used, 1), cap_s=round(cap, 1))
        if cap < AP.MIN_SECONDS:
            return None, dict(rep, status=f"skipped: {max(0.0, cap):.0f} s left of the end stage's clock")
        cands = E.collect(name, steps=rs.d["steps"], pool_lines=end_pool(rs), seed=seed)
        pl = AP.plan(cands, row, inc_proof, [("end pick", AP.picked_sha(res)), ("end input", E.sha(cur["proof"]) if cur.get("proof") else None)],
                     cfg["groups"])
        rep["plan"] = {k: pl.get(k) for k in ("candidates", "groups", "incumbent", "how", "key_tokens", "status")}
        if not pl["jobs"]:
            return None, dict(rep, status=f"skipped: {pl['status']}")
        st = meter.test or {}
        keys = {f"{row['source']}@{v}" for v in meter.versions}
        with E._LOCK:
            tests = {k: v for k, v in E._RUN["tests"].items() if k in keys}
            fb = E._RUN["fallback"]
        base = {"row": row, "heartbeats": dict(LT.HBS), "seed": seed, "end_config": A.end_config, "end_config_sha256": A.end_config_sha256,
                "end_k": A.end_k, "end_max_compiles": A.end_max_compiles, "meter_tests": tests, "meter_fallback": fb, "meter_path": meter.path,
                "self_test_cached": bool(st.get("cached"))}
        wd = Path(A.run_dir) / "approach" / safe(name)
        best, runs = None, []
        for job in pl["jobs"]:
            left = cap - (time.time() - t0)
            if left < 1.0:
                runs.append({"gid": job["gid"], "n": job["n"], "best_stored": job["best"], "status": "not started: the cap is spent"}); continue
            r = AP.run_child(dict(base, gid=job["gid"], lines=job["lines"]), left, wd, stop=_TERMINATING)
            res_c = r.get("result") or {}
            m = res_c.get("metrics") or {}
            one = {"gid": job["gid"], "n": job["n"], "best_stored": job["best"], "status": r["status"], "seconds": r.get("seconds"),
                   **({"error": r["error"]} if r.get("error") else {}), **({"kill": r["kill"]} if r.get("kill") else {}),
                   **({"stage": res_c.get("stage"), "compiles": res_c.get("compiles"), "verified": res_c.get("verified"),
                       "score_exact": m.get("score_exact"), "tokens": m.get("tokens"), "heartbeats": m.get("heartbeats"), "Z": m.get("Z"),
                       "meter": res_c.get("meter")} if r["status"] == "done" else {})}
            runs.append(one)
            rlog(f"approach {job['gid']} ({job['n']} candidate(s), best stored {job['best']:.2f}): {r['status']} in {r.get('seconds')} s"
                 + (f" -> {res_c.get('stage')} {m.get('score_exact')}" if r["status"] == "done" else f" ({r.get('error') or ''})"))
            if r["status"] == "stopped":
                break
            if r["status"] != "done" or not res_c.get("verified") or not P._finite(m.get("score_exact")):
                continue
            if best is None or float(m["score_exact"]) > float(best[1]["metrics"]["score_exact"]):
                best = (job, res_c)
        rep["runs"] = runs
        rep["seconds"] = round(time.time() - t0, 1)
        if best is None:
            return None, dict(rep, status="the incumbent stays: no other group's polish finished verified" + (
                " (abandoned at the cap)" if any(x["status"] == "cap" for x in runs) else ""))
        job, rc = best
        cand = (rc.get("proof") or "").strip()
        rep["candidate"] = {"gid": job["gid"], "stage": rc.get("stage"), "score_exact": rc["metrics"].get("score_exact"),
                            "tokens": rc["metrics"].get("tokens"), "heartbeats": rc["metrics"].get("heartbeats"), "Z": rc["metrics"].get("Z")}
        if cand == inc_proof:
            return None, dict(rep, status="the incumbent stays: the other group polished to the incumbent's text")
        if float(rc["metrics"].get("Z") or 0) < 100.0 - 1e-9:
            return None, dict(rep, status=f"the incumbent stays: the polished proof is not Z 100 (Z {rc['metrics'].get('Z')})")
        why = FW.static_check(cand, row.get("statement"))
        if why:
            return None, dict(rep, status=f"the incumbent stays: static check ({why})")
        rm = res.get("metrics") if isinstance(res.get("metrics"), dict) else {}
        inc_read = (inc.get("score_exact") if inc.get("meter") and inc.get("meter") == rc.get("meter") else
                    rm.get("score_exact") if (res.get("proof") or "").strip() == inc_proof and rm.get("meter") == rc.get("meter") else None)
        if P._finite(inc_read) and float(rc["metrics"]["score_exact"]) <= float(inc_read):
            return None, dict(rep, status=f"the incumbent stays: {rc['metrics']['score_exact']:.4f} <= the incumbent's {float(inc_read):.4f} "
                                          "on the end-stage meter")
        # the pick: incumbent then candidate, back to back on the end stage's meter, every pin
        ra, rb = meter.measure(inc_proof, full=True), meter.measure(cand, full=True)
        ia, ib = _reading(ra), _reading(rb)
        rep["paired"] = {"incumbent": ia, "candidate": ib}
        if ib is None or float(ib["Z"]) < 100.0 - 1e-9:
            return None, dict(rep, status="the incumbent stays: the candidate does not read Z 100 on the end-stage meter")
        if ia is None:
            return None, dict(rep, status="the incumbent stays: the incumbent does not read on the end-stage meter (no comparison)")
        ok, why = decide(ia, ib)
        rep["decide"] = why
        if not ok:
            return None, dict(rep, status=f"the incumbent stays: {why}")
        st_a, why_a = FW.router_audit_fn({name: row})(name, cand)
        rep["audit"] = {"status": st_a, "why": why_a}
        if st_a not in ("clean", "skipped"):
            return None, dict(rep, status=f"the incumbent stays: axiom audit {st_a} ({why_a})")
        m = rb
        item = {k: m[k] for k in (*ITEM_KEYS, "score_exact", "meter") if m.get(k) is not None and k not in ("proof", "stage", "verified")}
        item.update(proof=cand, verified=True, stage=f"end:approach:{rc.get('stage')}", spend=float(cur.get("spend") or 0))
        g = end_guard(name, inc, item, evaluator, end_meter=meter.path)   # the confirm read (the router's evaluator, every pin)
        rep["confirm"] = g
        if not g["ok"] or (g.get("delta") is not None and not g["delta"] > 0):
            return None, dict(rep, status="the incumbent stays: the confirm read " + (g["why"] if not g["ok"] else f"is not above ({g['delta']:+.4f})"))
        d = g["delta"] if g.get("delta") is not None else float(ib["score"]) - float(ia["score"])
        if P._finite(inc.get("score")):
            item["measured_score"], item["score"] = item.get("score"), round(float(inc["score"]) + d, 2)
        rep.update(accepted=True, delta=round(float(d), 6), seconds=round(time.time() - t0, 1),
                   status=f"{job['gid']} accepted {float(ia['score']):.4f} -> {float(ib['score']):.4f} ({why}; confirm {d:+.4f})")
        rlog(f"approach pick: {rep['status']}")
        return item, rep
    except Exception as e:  # noqa: BLE001  (no harm on failure: the incumbent stays)
        rep.update(status=f"failed ({type(e).__name__}: {str(e)[:160]}): the incumbent stays", seconds=round(time.time() - t0, 1))
        try:
            rlog(f"approach pick {rep['status']}")
        except Exception:  # noqa: BLE001
            pass
        return None, rep


def approach_summary(names: list, first: dict) -> dict:
    """summary.json end.approach: the rows' outcomes and the pick's wall."""
    out = {"accepted": 0, "kept": 0, "skipped": 0, "cap": 0, "failed": 0, "delta_sum": 0.0, "seconds": []}
    for n in names:
        ap = ((first[n].d["steps"].get("end") or {}).get("report") or {}).get("approach")
        if not ap:
            continue
        st = str(ap.get("status") or "")
        if ap.get("accepted"):
            out["accepted"] += 1; out["delta_sum"] += float(ap.get("delta") or 0)
        elif st.startswith("skipped"):
            out["skipped"] += 1
        elif st.startswith("failed"):
            out["failed"] += 1
        else:
            out["kept"] += 1
        out["cap"] += sum(1 for r in ap.get("runs") or [] if r.get("status") == "cap")
        if P._finite(ap.get("seconds")):
            out["seconds"].append(float(ap["seconds"]))
    sec = sorted(out.pop("seconds"))
    out["seconds_p50"] = sec[len(sec) // 2] if sec else None
    out["seconds_max"] = sec[-1] if sec else None
    out["delta_sum"] = round(out["delta_sum"], 4)
    return out


def presweep_step(name, rs: RowStore, item0: dict, A, evaluator, log) -> dict:
    """b65 --sweep-before-review (docs/argon_review_value.md item 2): before the review, the end stage's sweep phase (its config's sweep,
    crossover, budgets; no tool phase) from the review's input alone (floor: that proof), so the review's edits go to sites the sweep
    cannot reach. Records step `presweep`: the swept proof when verified, different and end_guard passes (report adopted=True; its score is
    the input's stored score plus the guard's same-meter delta, like the end step), else the input. Returns the review's input: the
    adopted swept proof even when its gain is below the fold's bar (the fold keeps its own rule; the end stage reads both)."""
    E = importlib.import_module("harness.endstage")
    cur = fold(rs, item0)
    row = LT.ROWS[name]
    seed = (row.get("src") or item0.get("proof") or "").strip()
    rlog = lambda m: log(f"{name[:40]}: [pre-review sweep] {m}")   # noqa: E731
    meter = _end_meter(E, row, seed, rlog)
    kw = dict(end_stage_kwargs(A, E))
    if "tools" in kw:
        kw["tools"] = ()   # the sweep phase only
    one = {"presweep_input": {"item": cur}}
    cands = E.collect(name, steps=one, pool_lines=[], seed=seed)
    floor = {"review_input": {x: cur[x] for x in ("proof", "score", "tokens", "heartbeats", "stage") if cur.get(x) is not None}}
    res = dict(E.end_stage(row, seed, cands, meter, checkpoint_bests=floor, log=rlog, **kw) or {})
    m = res["metrics"] if isinstance(res.get("metrics"), dict) else res
    item = {k: m[k] for k in (*ITEM_KEYS, "score_exact", "meter") if m.get(k) is not None and k not in ("proof", "stage", "verified")}
    item.update(proof=res.get("proof"), verified=_verified(res), stage=f"presweep:{res.get('stage')}", spend=float(cur.get("spend") or 0))
    for k in ("state_path",):
        if cur.get(k):
            item[k] = cur[k]
    rep = {"stage": res.get("stage"), "compiles": res.get("compiles"), "adopted": False,
           "decisions": len(res.get("decisions") or []), "banked": sum(1 for d in (res.get("decisions") or []) if d.get("banked"))}
    if not (item["verified"] and P._finite(item.get("score"))):
        rep["status"] = "not verified: the review starts from its input"
    elif item["proof"].strip() == (cur.get("proof") or "").strip():
        rep["status"] = "the sweep kept the input"
    else:
        g = end_guard(name, cur, item, evaluator, end_meter=res.get("meter"))
        rep.update(adopted=g["ok"], guard=g, status="adopted" if g["ok"] else "the input stays: " + g["why"])
        if g["ok"] and g.get("delta") is not None and P._finite(cur.get("score")):
            item["measured_score"], item["score"] = item.get("score"), round(float(cur["score"]) + g["delta"], 2)
    rs.put("presweep", item if rep["adopted"] else cur, rep)
    if rep["adopted"]:
        bank_item(cur.get("state_path"), name, item, "presweep", parent=cur.get("proof"))
    log(f"{name[:40]}: pre-review sweep {res.get('stage')}: {rep['status']} ({res.get('compiles', '?')} compiles)")
    return dict(item, spend=float(cur.get("spend") or 0)) if rep["adopted"] else cur


def final_of(rs: RowStore, item0: dict) -> dict:
    """The row's final: the fold of its steps, or an adopted end step's output (B62b: gated on one meter by the end stage and end_guard; the
    fold's score comparison would mix meters)."""
    cur = fold(rs, item0)
    sw = rs.d["steps"].get(STYLE_RW_STEP)   # b85: an accepted style rewrite (gated on one meter by style_rw.confirm) is the final
    if sw and (sw.get("report") or {}).get("accepted"):
        return dict(sw["item"], spend=max(float(sw["item"].get("spend") or 0), float(cur.get("spend") or 0)))
    st = rs.d["steps"].get("end")
    if st and (st.get("report") or {}).get("adopted"):
        return dict(st["item"], spend=max(float(st["item"].get("spend") or 0), float(cur.get("spend") or 0)))
    return cur


def post_row(name, A, evaluator, log, S=None, dec=None, upto_review: bool = False) -> dict:
    """After the ladder: the re-plan rounds (if decided), $0 again on a changed proof, the review on every row, then (--end-stage) the $0 end
    stage, always last. upto_review (b68, --tail-preset only): stop after the review (the tail runs next; a second call does the rest)."""
    rs = RowStore(A.run_dir, name)
    item0 = inp0(rs)
    pin = getattr(A, "pin_stop", None)   # b65-final: a CONFIRMED pin of the ladder's preset: no paid step from here on (the run's $0 path)
    if pin and dec and dec["tier"] in ("twin", "replan"):
        log(f"{name[:40]}: {dec['tier']} skipped: confirmed max_price pin ({pin.get('phase')}); the row finishes on the $0 path")
    if dec and dec["tier"] == "twin" and not pin:   # b63 item 17: the twin lineage from the checkpoint best, then SELECT over both lineages
        twin_rounds(name, rs, item0, A, evaluator, log, S, dec)
        select_step(name, rs, item0, A, log, dec)
    if dec and dec["tier"] == "replan" and not pin:
        had_review = rs.done("review")
        ran = (route_rounds(name, rs, item0, A, evaluator, log, S, dec) if dec.get("kind") in ("repair", "artifact-session")
               else replan_rounds(name, rs, item0, A, evaluator, log, S, dec))
        if ran and had_review:
            for k in ("clean2", "presweep", "review_started", "review", "end"):   # new rounds after a finished review: keep the old steps (their spend and
                if rs.done(k):                                  # score stay in the fold) and run cleanup and review again, last
                    rs.d["steps"][k + "_v1"] = rs.d["steps"].pop(k)
            rs.put("_reordered", fold(rs, item0), {"note": "review re-run after new re-plan rounds"})
    cur = fold(rs, item0)
    lc = last_clean(rs)
    full_final = getattr(A, "fast_checkpoint_cleanup", False)   # the checkpoints skipped the slow passes: the full chain runs once, here
    if lc is not None and (full_final or cur.get("proof") != lc.get("proof")) and not rs.done("clean2"):
        out, rep = pp_step(name, cur, A.clean2_stages, A, evaluator, log, free_passes=None)
        rs.put("clean2", out, rep)
        bank_item(cur.get("state_path"), name, out, "clean2", parent=cur.get("proof"))
        cur = fold(rs, item0)
    if getattr(A, "cross", False) and not rs.done("cross@pre"):   # b63 item 3: t13 bank crossover before the review ($0)
        try:
            cross_step(name, rs, item0, A, evaluator, log, S)
        except Exception as e:  # noqa: BLE001  (a $0 step: the review still runs on the fold)
            log(f"{name[:40]}: crossover step failed: {type(e).__name__}: {str(e)[:160]}")
            rs.put("cross@pre", cur, {"status": f"failed: {type(e).__name__}", "adopted": False})
        cur = fold(rs, item0)
    if getattr(A, "sweep_before_review", False) and getattr(A, "end_stage", False) and not rs.done("review"):   # b65 item 2 ($0)
        if not rs.done("presweep"):
            try:
                cur = presweep_step(name, rs, item0, A, evaluator, log)
            except Exception as e:  # noqa: BLE001  (a $0 step: the review still runs on the fold)
                log(f"{name[:40]}: pre-review sweep failed: {type(e).__name__}: {str(e)[:160]}")
                rs.put("presweep", cur, {"status": f"failed: {type(e).__name__}", "adopted": False})
        else:
            ps = rs.d["steps"]["presweep"]
            cur = dict(ps["item"], spend=float(cur.get("spend") or 0)) if (ps.get("report") or {}).get("adopted") else cur
    led = RowLedger(A.run_dir, name)
    led.set_sessions_total(float(cur.get("spend") or 0))   # the fold's spend holds every re-plan / twin round's spend too (one shared ledger, contract §2)
    ladder_cap_extra(led, item0.get("state_path") or cur.get("state_path"))   # b64 planner
    if not rs.done("review"):
        # rounded DOWN (was: to the nearest 1e-4, which could round past the cap), with SPEND_MARGIN under the cap; b64 L0: the row's whole
        # room (--review-budget room), in cap-price dollars (the ledger holds the Argon calls at the cap price)
        budget = review_budget_usd(A.cap, max(float(cur.get("spend") or 0), led.total()), A.review_reserve, getattr(A, "review_budget", "room"))
        if rs.done("review_started"):   # killed mid-review: its spend is not persisted, so the whole budget is assumed spent
            b = float(rs.d["steps"]["review_started"]["report"].get("budget") or 0)
            rs.put("review", dict(cur, spend=round(float(cur.get("spend") or 0) + b, 4)), {"status": f"interrupted (spend assumed ${b:.2f})"})
            led.set("review", b, monotone=False)   # b64 L0: the ledger takes the assumed budget too
        elif A.dry_run or not A.review_model:
            rs.put("review", cur, {"status": "skipped (dry run)" if A.dry_run else "skipped (no review model)"})
        elif pin:   # b65-final: the run's $0 path after a confirmed pin of the ladder's preset ($0, nothing booked)
            rs.put("review", cur, {"status": f"skipped: confirmed max_price pin after ladder {pin.get('phase')} (the run's $0 path)", "pin_stop": True})
        elif budget < 0.05:
            rs.put("review", cur, {"status": f"skipped: ${budget:.2f} left under the cap"})
        else:
            rs.put("review_started", cur, {"budget": budget})
            out, rep = pp_step(name, cur, ["polish"], A, evaluator, log, polish_budget=budget)
            rs.put("review", out, rep)
            pst = (rep.get("stages") or {}).get("polish") or {}
            # b64 L0: the ledger (what every later gate reads) holds the review at the cap price; the item's spend (reported) the list price
            led.set("review", float(pst.get("review_cap_spend") if pst.get("review_cap_spend") is not None else (pst.get("review_spend") or 0)),
                    monotone=False)
            bank_item(cur.get("state_path"), name, out, "review", parent=cur.get("proof"))
            if review_r6_on(A):   # b72 R6: every stack verified on every pin above its round's base, into the row's bank: the end stage
                # reads it back to back with its incumbent (scorer.accept.decide), nothing else. b75: into the row's ladder workspace even
                # when the review's input item carries no state path (a crossover child or a cleanup output has none: the stacks were not
                # banked then, e.g. 2 of the fork A/B's 6 rows with verified stacks; docs/b75_stack.md)
                bank_review_stacks(dict(cur, state_path=cur.get("state_path") or row_state_path(rs)), name, pst, log)
            log(f"{name[:40]}: review {pst.get('status')}, ${float(pst.get('review_spend') or 0):.3f}, {cur.get('score')} -> {out.get('score')}")
    if upto_review:   # b68: the tail stage comes between the review and the end stage
        return final_of(rs, item0)
    if getattr(A, "end_stage", False) and not rs.done("end"):
        end_step(name, rs, item0, A, evaluator, log)
    if style_rw_on(A) and not rs.done(STYLE_RW_STEP):   # b85: the accept-only paid rewrite at the end of the end stage
        style_rw_step(name, rs, item0, A, evaluator, log)
    return final_of(rs, item0)


def cap_spend_of(run_dir: Path, name: str, item: dict) -> float:
    """b64 L0: a row's spend at the cap price, for the summary: its reported (list) spend plus every recorded cap-price difference (each
    review step's review_cap_spend - review_spend, a re-run's review_v1 included, and the REPAIR slices' cap_extra ledger labels). Not the
    ledger total: on a resume of a row that finished its review, post_row registers the fold's spend (which then holds the review at the list
    price) under `sessions` while the `review` label keeps it at the cap price, so the total counts the review twice (no gate reads the
    ledger after the review; the summary would flag every resumed row as over the cap)."""
    rs = RowStore(run_dir, name)
    extra = 0.0
    for k in ("review", "review_v1"):
        pst = ((((rs.d["steps"].get(k) or {}).get("report") or {}).get("stages") or {}).get("polish")) or {}
        if pst.get("review_cap_spend") is not None:
            extra += max(0.0, float(pst["review_cap_spend"]) - float(pst.get("review_spend") or 0))
    extra += sum(float(v or 0) for k, v in RowLedger(run_dir, name).d["sources"].items() if str(k).startswith("cap_extra:"))
    return round(float(item.get("spend") or 0) + extra, 4)



# ------------------------------------------------------------------------------------------------------------------ style_rw (b85)
# docs/b85_style_rw.md (2026-10-29, adopted after its validation replay): --style-rw on adds harness/style_rw.py's
# ACCEPT-ONLY paid rewrite step after every row's end step. Off by default: config.json gets no key and no code of the module runs.
STYLE_RW_STEP, STYLE_RW_START = "style_rw", "style_rw_started"
SRW_WALL_S = 900.0   # = harness/style_rw.STYLE_RW_WALL_S (the parser's default; kept here so a run without the flag imports nothing)


def style_rw_on(A) -> bool:
    return getattr(A, "style_rw", "off") == "on"


def style_rw_config(A) -> dict | None:
    """The step's frozen settings (config.json "style_rw", written only when on: a run without it has no key)."""
    if not style_rw_on(A):
        return None
    return {"usd": float(A.style_rw_usd), "preset": A.style_rw_preset, "effort": A.style_rw_effort, "exemplars": A.style_rw_exemplars,
            "wall_s": float(getattr(A, "style_rw_wall_s", SRW_WALL_S))}


def style_rw_args_check(A) -> str | None:
    """The style_rw flags before any spend: the refusal text, else None."""
    import harness.style_rw as SRW
    if not style_rw_on(A):
        if (getattr(A, "style_rw_usd", SRW.STYLE_RW_USD) != SRW.STYLE_RW_USD or getattr(A, "style_rw_preset", SRW.STYLE_RW_PRESET) != SRW.STYLE_RW_PRESET
                or getattr(A, "style_rw_effort", SRW.STYLE_RW_EFFORT) != SRW.STYLE_RW_EFFORT or getattr(A, "style_rw_exemplars", None)
                or float(getattr(A, "style_rw_wall_s", SRW.STYLE_RW_WALL_S)) != SRW.STYLE_RW_WALL_S):
            return ("--style-rw-usd, --style-rw-preset, --style-rw-effort, --style-rw-exemplars and --style-rw-wall-s are --style-rw on "
                    "options")
        return None
    from harness.agent import MODEL_PRESETS   # noqa: E402
    if not getattr(A, "end_stage", False) or not getattr(A, "end_config", None):
        return "--style-rw on needs --end-stage with --end-config (its $0 polish is the run's end stage)"
    if not tail_preset_ok(MODEL_PRESETS.get(A.style_rw_preset)):
        return f"--style-rw-preset {A.style_rw_preset}: not an OpenRouter agent.py preset (nor a list-priced Azure one)"
    if not (math.isfinite(A.style_rw_usd) and A.style_rw_usd >= 0):
        return f"--style-rw-usd {A.style_rw_usd:g}: a finite amount >= 0"
    w = float(getattr(A, "style_rw_wall_s", SRW.STYLE_RW_WALL_S))
    if not (math.isfinite(w) and w > 0):
        return f"--style-rw-wall-s {w:g}: a finite number of seconds > 0 (the step's hard wall cap per row)"
    if not A.style_rw_exemplars:
        return "--style-rw on needs --style-rw-exemplars <sha16 of harness/style_rw_exemplars.json>"
    miss = SRW.preflight()   # every module the step imports lazily, before any spend (a package missing a file fails here)
    if miss:
        return miss
    try:
        SRW.load_exemplars(A.style_rw_exemplars)
    except (OSError, ValueError, RuntimeError, KeyError) as e:
        return f"--style-rw-exemplars: {e}"
    return None


def style_rw_book_only(name: str, rs: "RowStore", cur: dict, budget: float, why: str, log, spent: float | None = None,
                       run_dir: Path | None = None, kind: str = "failed", extra: dict | None = None) -> None:
    """The step could not finish (kind "failed": an exception, an interrupted run; "abandoned": the wall cap): its spend is booked once
    (what the caller charged when known, else the whole budget assumed, as an interrupted review), the incumbent stays. Never raises."""
    try:
        d = float(budget) if spent is None else float(spent)
        spend1 = _ceil6(float(cur.get("spend") or 0) + d)
        rs.put(STYLE_RW_STEP, dict(cur, spend=spend1), {"status": f"{kind} ({why}): spend booked" + (" (the whole budget assumed)" if spent is None else "")
                                                        + "; the incumbent stays", "budget": budget, "spent": round(d, 6), "assumed": spent is None,
                                                        "accepted": False, "score_before": cur.get("score"), "score_after": cur.get("score"),
                                                        **(extra or {})})
        if run_dir is not None:
            RowLedger(run_dir, name).set(STYLE_RW_STEP, d)
        log(f"{name[:40]}: style_rw {kind} ({why}); ${d:.4f} booked" + (" (assumed)" if spent is None else "") + "; the incumbent stays")
    except Exception as e:  # noqa: BLE001
        log(f"{name[:40]}: style_rw spend not booked ({type(e).__name__}: {str(e)[:120]})")


def style_rw_end_clock(rs: "RowStore", A, E) -> dict:
    """b85 wall cap: the row's end-stage clock left = the end stage's wall budget per start (the frozen --end-config's phase limits: sweep
    min(max_seconds, backstop_s) + tools min(tools_max_seconds, tools_backstop_s), each defaulting as end_stage defaults them; r10: 1800 +
    1800 s) minus the seconds the row's end step's (kept) end stage used (its report "end"."seconds"; 0 when the row has no end report).
    {"budget_s", "used_s", "left_s"}: left_s is inf when a phase has no wall limit."""
    kw = end_stage_kwargs(A, E)

    def lim(*xs):
        v = [float(x) for x in xs if x]
        return min(v) if v else math.inf
    sweep = lim(kw.get("max_seconds"), kw.get("backstop_s"))
    tools = lim(kw.get("max_seconds") if kw.get("tools_max_seconds") is None else kw.get("tools_max_seconds"),
                kw.get("backstop_s") if kw.get("tools_backstop_s") is None else kw.get("tools_backstop_s"))
    budget = sweep + (tools if kw.get("tools") else 0.0)
    rep = (rs.d["steps"].get("end") or {}).get("report") or {}
    used = float(((rep.get("end") or {}).get("seconds")) or 0.0)
    return {"budget_s": budget, "used_s": round(used, 1), "left_s": max(0.0, budget - used)}


def style_rw_step(name, rs: "RowStore", item0: dict, A, evaluator, log) -> None:
    """b85: after the end step, harness/style_rw.Step on the row's final (module docstring there). Records step `style_rw_started` (the
    budget, the incumbent's sha, the wall cap) before the first call and `style_rw` after: the rewrite when accepted (confirm read >= +0.05
    on the end-stage meter, every pin; stage "style_rw", stored score + the same-meter delta, banked), else the incumbent with the spend.
    Every failure books the spend once and keeps the incumbent; a row interrupted inside the step books its whole budget on the resume.
    Wall cap (module docstring "wall"): the step's Lean and model work runs in a worker thread that this thread waits for at most cap_s =
    min(--style-rw-wall-s, style_rw_end_clock's left_s) from the step's start; still running then: abandoned (no later call is sent, the
    worker's result is never read, the incumbent stays byte-identical; booked: the calls' spend, or the whole budget when one was in
    flight). The worker never writes the row store; only this thread does."""
    import harness.style_rw as SRW
    t0 = time.time()
    if rs.done(STYLE_RW_STEP):   # a finished step is never run again (no double spend)
        return
    cur = final_of(rs, item0)
    cfg = style_rw_config(A)
    if rs.done(STYLE_RW_START):   # killed inside the step: its spend is not persisted, so the whole budget is assumed spent
        b = float(rs.d["steps"][STYLE_RW_START]["report"].get("budget") or 0)
        style_rw_book_only(name, rs, cur, b, "interrupted", log, run_dir=A.run_dir)
        return
    skip = None
    if A.dry_run:
        skip = "skipped (dry run)"
    elif getattr(A, "pin_stop", None):
        skip = f"skipped: confirmed max_price pin after ladder {A.pin_stop.get('phase')} (the run's $0 path)"
    elif not (cur.get("proof") or "").strip() or not cur.get("verified", True):
        skip = "skipped: no verified final"
    row = LT.ROWS[name]
    budget = SRW.budget_for(A.cap, cap_spend_of(A.run_dir, name, cur), cfg["usd"], SPEND_MARGIN)
    if skip is None and SRW.reference_heartbeats(name, LT.HBS) is None:
        skip = "skipped: no heartbeat reference for the row ($0)"
    if skip is None and budget < 0.01:
        skip = f"skipped: ${budget:.4f} left under the cap ($0)"
    E = importlib.import_module("harness.endstage")
    wall = {"wall_s": float(cfg["wall_s"])}
    if skip is None:
        try:
            clock = style_rw_end_clock(rs, A, E)
        except Exception as e:  # noqa: BLE001  (the end config cannot be read: no clock, no step)
            clock = {"error": f"{type(e).__name__}: {str(e)[:160]}", "left_s": 0.0}
        cap_s = min(float(cfg["wall_s"]), float(clock["left_s"]))
        wall.update(clock={k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in clock.items()}, cap_s=round(cap_s, 1))
        if cap_s < SRW.CALL_MIN_LEFT_S:
            skip = (f"skipped: wall cap {cap_s:.0f} s (min of --style-rw-wall-s {cfg['wall_s']:g} and the row's end-stage clock left) is below "
                    f"the {SRW.CALL_MIN_LEFT_S:g} s one call needs ($0)")
    if skip is not None:
        rs.put(STYLE_RW_STEP, cur, {"status": skip, "accepted": False, "budget": budget, "spent": 0.0, "score_before": cur.get("score"),
                                    "score_after": cur.get("score"), "wall": wall})
        log(f"{name[:40]}: style_rw {skip}")
        return
    deadline = t0 + cap_s
    wall["deadline"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(deadline))
    rlog = lambda m: log(f"{name[:40]}: {m}")   # noqa: E731
    rs.put(STYLE_RW_START, cur, {"budget": budget, "incumbent_sha": _sha12(cur.get("proof")), "preset": cfg["preset"], "wall": dict(wall)})
    gate = SRW.CallGate()   # made here, before the worker: closing it refuses every call the worker would send after the wall cap
    box: dict = {}

    def work():
        """Everything with Lean or the model; returns (rep, cand, confirm) and never writes the row store."""
        SRW.force_warn_sorry()
        seed = (row.get("src") or item0.get("proof") or "").strip()
        meter = _end_meter(E, row, seed, rlog)
        exs = SRW.exemplars_for(name, SRW.load_exemplars(cfg["exemplars"]))
        kw = end_stage_kwargs(A, E)
        from harness import final_writer as FW
        audit = FW.router_audit_fn(LT.ROWS)

        def polish(item, stop_at=None):
            one = {"style_rw_cand": {"item": item}}
            cands = E.collect(name, steps=one, pool_lines=[], seed=seed)
            floor = {"style_rw_cand": {x: item[x] for x in ("proof", "score", "tokens", "heartbeats", "stage") if item.get(x) is not None}}
            return dict(E.end_stage(row, seed, cands, meter, checkpoint_bests=floor, log=lambda m: rlog(f"[style_rw polish] {m}"), **kw,
                                    **({"stop_at": stop_at} if stop_at is not None else {})) or {})
        pool = end_pool(rs)
        others = SRW.other_units(name, cur["proof"], E.collect(name, steps=rs.d["steps"], pool_lines=pool, seed=seed), SRW.STYLE_RW_UNITS - 1)
        box["others"] = len(others); box["exs"] = [x["id"] for x in exs]
        caller = SRW.Caller(name, cfg["preset"], cfg["effort"], budget, getattr(A, "cap_price", "announced"), rlog, gate=gate,
                            trajectory=A.run_dir / "trajectories" / f"style_rw-{safe(name)}.jsonl")   # the full per-call trajectory
        box["caller"] = caller
        step = SRW.Step(name, row, dict(LT.HBS), {"proof": cur["proof"]}, exs, caller, meter, audit, polish, log, units=others, deadline=deadline)
        rep = step.run()
        cand = rep.pop("candidate", None)
        g = None
        if cand is not None:
            need = max(10.0, 2.0 * float(step.read_s or 0.0))
            if deadline - time.time() < need:   # the confirm read would cross the wall cap: nothing is accepted
                rep["wall_stop"] = f"no confirm read: {max(0.0, deadline - time.time()):.0f} s left before the wall cap (it needs ~{need:.0f} s)"
                rep["confirm_skipped"] = {k: cand.get(k) for k in ("label", "origin", "polished")}
                cand = None
            else:
                g = SRW.confirm(meter, cur["proof"], cand["proof"], rlog)
        return rep, cand, g

    def runner():
        try:
            box["out"] = work()
        except BaseException as e:  # noqa: BLE001  (handed to the waiting thread)
            box["exc"] = e
    th = threading.Thread(target=runner, name=f"style_rw:{name[:40]}", daemon=True)
    th.start()
    th.join(timeout=max(0.0, deadline - time.time()))
    caller = box.get("caller")
    if th.is_alive():   # the wall cap: abandon the worker (it stops on its own deadlines; its result is never read)
        inflight = gate.close()
        spent = None if inflight else (float(caller.spent_list()) if caller is not None else 0.0)
        wall.update(seconds=round(time.time() - t0, 1), abandoned=True, call_in_flight=inflight)
        style_rw_book_only(name, rs, cur, budget, f"the {cap_s:.0f} s wall cap reached" + (" with a call in flight" if inflight else ""), log,
                           spent=spent, run_dir=A.run_dir, kind="abandoned",
                           extra={"wall": wall, "calls": len([c for c in (caller.calls if caller is not None else []) if "skipped" not in c])})
        return
    gate.close()
    if "exc" in box:
        e = box["exc"]
        spent = float(caller.spent_list()) if caller is not None else 0.0   # no caller yet: no call could have been sent
        log(f"{name[:40]}: style_rw raised {type(e).__name__}: {str(e)[:200]}")
        wall.update(seconds=round(time.time() - t0, 1))
        style_rw_book_only(name, rs, cur, budget, f"{type(e).__name__}: {str(e)[:120]}", log, spent=spent, run_dir=A.run_dir, extra={"wall": wall})
        return
    try:
        rep, cand, g = box["out"]
        spent, spent_cap = float(rep.get("spent") or 0), float(rep.get("spent_cap") or 0)
        spend1 = _ceil6(float(cur.get("spend") or 0) + spent)
        wall.update(seconds=round(time.time() - t0, 1))
        rep.update(budget=budget, score_before=cur.get("score"), seconds=wall["seconds"], exemplars=box.get("exs"), other_units=box.get("others"),
                   wall=wall)
        item = dict(cur, spend=spend1)
        if cand is None:
            rep.update(accepted=False, status=rep.get("status") or ("no verified candidate" if not rep.get("error") else f"stopped: {rep['error']}; no verified candidate"))
            if rep.get("wall_stop") and not rep.get("error") and rep["status"] == "no verified candidate":
                rep["status"] = f"no candidate taken: {rep['wall_stop']}"
        else:
            rep.update(confirm=g, candidate={k: cand.get(k) for k in ("label", "origin", "polished", "polish_stage", "audit", "reading")})
            if g["ok"]:
                m = g["candidate"]
                item = {k: m[k] for k in ("tokens", "heartbeats", "L", "H", "Z", "compat") if m.get(k) is not None}
                item.update(proof=cand["proof"], verified=True, stage=STYLE_RW_STEP, spend=spend1, score_exact=m.get("score_exact"), meter=m.get("meter"))
                for k in ("state_path",):
                    if cur.get(k):
                        item[k] = cur[k]
                if g.get("delta") is not None and P._finite(cur.get("score")):
                    item["measured_score"], item["score"] = m.get("score_exact"), round(float(cur["score"]) + g["delta"], 2)
                else:
                    item["score"] = m.get("score_exact")
                rep.update(accepted=True, status="accepted: " + g["why"])
            else:
                rep.update(accepted=False, status="the incumbent stays: " + g["why"])
        rep["score_after"] = item.get("score") if rep.get("accepted") else cur.get("score")
        rep["spent_cap"] = round(spent_cap, 6)
        rs.put(STYLE_RW_STEP, item, rep)
        led = RowLedger(A.run_dir, name)
        led.set(STYLE_RW_STEP, spent)
        if spent_cap > spent + 1e-9:
            led.set("cap_extra:style_rw", spent_cap - spent)
        if rep["accepted"]:
            bank_item(cur.get("state_path") or row_state_path(rs), name, item, STYLE_RW_STEP, parent=cur.get("proof"))
        log(f"{name[:40]}: style_rw: ${spent:.4f} of ${budget:.4f} budget, {rep.get('calls', 0)} call(s), {rep.get('cands', 0)} candidate(s), "
            f"{rep.get('compiled', 0)} compiled, {wall['seconds']:.0f} s of the {cap_s:.0f} s wall cap; {cur.get('score')} -> {rep['score_after']} "
            f"({rep['status']})")
    except Exception as e:  # noqa: BLE001
        spent = float(caller.spent_list()) if caller is not None else 0.0
        log(f"{name[:40]}: style_rw raised {type(e).__name__}: {str(e)[:200]}")
        if not rs.done(STYLE_RW_STEP):
            style_rw_book_only(name, rs, cur, budget, f"{type(e).__name__}: {str(e)[:120]}", log, spent=spent, run_dir=A.run_dir, extra={"wall": wall})


def style_rw_summary(A, names: list) -> dict:
    """summary.json "style_rw" (only when on): the config and the rows' outcomes."""
    out = {"config": style_rw_config(A), "rows": len(names), "accepted": 0, "kept": 0, "skipped": 0, "failed": 0, "abandoned": 0, "missing": 0,
           "spend_total": 0.0, "spend_max": 0.0, "calls": 0, "delta_sum": 0.0, "seconds_max": 0.0}
    for n in names:
        rep = (RowStore(A.run_dir, n).d["steps"].get(STYLE_RW_STEP) or {}).get("report")
        if not rep:
            out["missing"] += 1; continue
        st = str(rep.get("status") or "")
        if rep.get("accepted"):
            out["accepted"] += 1; out["delta_sum"] += float(((rep.get("confirm") or {}).get("delta")) or 0)
        elif st.startswith("skipped"):
            out["skipped"] += 1
        elif st.startswith("failed"):
            out["failed"] += 1
        elif st.startswith("abandoned"):
            out["abandoned"] += 1
        else:
            out["kept"] += 1
        out["seconds_max"] = max(out["seconds_max"], float(((rep.get("wall") or {}).get("seconds")) or 0.0))
        sp = float(rep.get("spent") or 0)
        out["spend_total"] += sp; out["spend_max"] = max(out["spend_max"], sp); out["calls"] += int(rep.get("calls") or 0)
    out["spend_total"] = round(out["spend_total"], 6); out["spend_max"] = round(out["spend_max"], 6); out["delta_sum"] = round(out["delta_sum"], 4)
    return out


# ------------------------------------------------------------------------------------------------------------------ R6 (b72)
# docs/b72_r6.md: --review-repair N (one repair turn per review edit that failed to compile, at most N per row per round, the review's own
# model and meter) and --review-stack (every compiling edit within --review-stack-eps of the round base stacked in one full compile, greedy
# fallback; harness/review.py). Off by default: config.json gets no key, pp_step leaves postpass's defaults and the review runs as before.
REVIEW_STACK_EPS = 0.02


def review_r6_on(A) -> bool:
    return int(getattr(A, "review_repair", 0) or 0) > 0 or bool(getattr(A, "review_stack", False))


def review_r6_config(A) -> dict | None:
    """R6's frozen settings (config.json "review_r6", written only when on: a run without it has no key)."""
    if not review_r6_on(A):
        return None
    return {"repair": int(A.review_repair), "stack": bool(A.review_stack), "stack_eps": float(A.review_stack_eps)}


def review_r6_args_check(A) -> str | None:
    """The R6 flags before any spend: the refusal text, else None."""
    if int(getattr(A, "review_repair", 0) or 0) < 0:
        return "--review-repair must be >= 0"
    eps = getattr(A, "review_stack_eps", REVIEW_STACK_EPS)
    if not getattr(A, "review_stack", False) and eps != REVIEW_STACK_EPS:
        return "--review-stack-eps is a --review-stack option"
    if not (isinstance(eps, (int, float)) and math.isfinite(eps) and 0 <= eps <= 1.0):
        return f"--review-stack-eps {eps}: a finite margin in [0, 1]"
    if review_r6_on(A) and not getattr(A, "review_model", None):
        return "--review-repair / --review-stack need a --review-model"
    return None


def review_r6_summary(A, names: list, first: dict) -> dict:
    """summary.json "review_r6" (only with R6 on): the config, the review steps' R6 counts summed, and the rows whose end stage picked or
    banked a review stack (an end decision or pick whose origins name bank:review_stack)."""
    tot: dict = {}
    per = {}
    for n in names:
        rep = ((first[n].d["steps"].get("review") or {}).get("report") or {})
        r6 = (((rep.get("stages") or {}).get("polish") or {}).get("r6")) or {}
        for k, v in r6.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in ("repair", "stack_eps"):
                tot[k] = round(tot.get(k, 0) + v, 6)
        end = json.dumps(((first[n].d["steps"].get("end") or {}).get("report") or {}).get("end") or {}, default=str)
        per[n] = {k: r6.get(k) for k in ("repairs_sent", "repairs_compiled", "repairs_pay", "repair_cap_cost", "stacks_verified", "stacks_picked")
                  if r6.get(k) is not None} | ({"end_saw_stack": True} if "review_stack" in end else {})
    return {"config": review_r6_config(A), "totals": tot, "per_row": per}


def row_state_path(rs) -> str | None:
    """b75: the row's ladder workspace (the state.json of the first step item that carries one; cross_step's rule), whose bank.jsonl
    end_pool reads for the end stage; None in the generic mode."""
    return next((st["item"].get("state_path") for st in rs.d["steps"].values() if (st.get("item") or {}).get("state_path")), None)


def bank_review_stacks(cur: dict, name: str, pst: dict, log) -> int:
    """b72 R6: the review's verified stacks (pst["stack_proofs"]) into the row's bank as `review_stack` (harness/bank.py; nothing without a
    state path). Never raises; returns how many were added."""
    n = 0
    for sp in (pst or {}).get("stack_proofs") or []:
        try:
            if isinstance(sp, dict) and sp.get("proof") and bank_item(cur.get("state_path"), name, dict(sp, verified=True), "review_stack",
                                                                      parent=cur.get("proof")):
                n += 1
        except Exception:  # noqa: BLE001
            pass
    if n:
        log(f"{name[:40]}: R6: {n} verified review stack(s) banked for the end stage")
    return n


# ---------------------------------------------------------------------------------------------------------------- the tail (b68)
# docs/b68_tail.md. Opt-in (--tail-preset):
# after every row's review and before the end stage, each row whose room under the cap (cap - its metered spend at the cap price - margin)
# is at least --tail-min-room (and the tail preset's session floor) runs agent.py sessions of the tail preset in its own work root, from its
# current best (written back first) with its notes, pool and bank: ONE hx_heldout --tail invocation over those rows (harness/hx_heldout.py
# tail_ladder: the ladder's own session command, container and flags; one session in flight per row). Each session's --budget-usd is the
# row's TOP = its state's gate spend (api_spend + cap_extra) when planned + its room, so the existing per-call worst-case gate is the only
# cap mechanism: no call is sent whose worst case does not fit, and the row's metered spend stays <= cap - margin. The top is persisted in
# step `tail_started` before any session, so a restart continues to the same top (never a second room). Acceptance: the work root's best
# after the sessions, if the sessions changed it, is read back to back with the pre-tail best on the router's evaluator (every pin) and kept
# only when it compiles on every pin and is better by more than MIN_GAIN (step `tail`); the end stage then reads it with every other
# candidate on one meter and end_guard confirms it on every pin. A pin of the tail preset follows b66's fallback (pin_fallback_pick: Terra
# pinned -> Sol); with no preset left the tail stops at $0 (no run-wide pin stop: the run goes on to the end stage and exits as usual).
TAIL_STEP, TAIL_START = "tail", "tail_started"
TAIL_FILE, TAIL_TOPS = "tail.json", "tail_tops.json"
TAIL_MIN_ROOM, TAIL_EFFORT, TAIL_MAX_SESSIONS = 0.10, "medium", 3


def tail_on(A) -> bool:
    return bool(getattr(A, "tail_preset", None))


def tail_config(A) -> dict | None:
    """The tail's frozen settings (config.json "tail", written only when the tail is on: a run without it has no key)."""
    if not tail_on(A):
        return None
    return {"preset": A.tail_preset, "min_room": A.tail_min_room, "effort": A.tail_effort, "max_sessions": A.tail_max_sessions}


def tail_preset_ok(pp) -> bool:
    """A tail session preset: an OpenRouter agent.py preset (the final's path), or (b68 review, 2026-10-28: the dev probe on Azure) an
    Azure one metered at its list table (list_price: Azure reports no cost; the gate prices it at the same table)."""
    pp = pp or {}
    url = pp.get("base_url") or ""
    return bool(pp) and not pp.get("anthropic_vertex") and ("openrouter.ai" in url or (".azure.com" in url and bool(pp.get("list_price"))))


def tail_args_check(A) -> str | None:
    """The tail flags before any spend: the refusal text, else None."""
    if not tail_on(A):
        if (getattr(A, "tail_min_room", TAIL_MIN_ROOM) != TAIL_MIN_ROOM or getattr(A, "tail_effort", TAIL_EFFORT) != TAIL_EFFORT
                or getattr(A, "tail_max_sessions", TAIL_MAX_SESSIONS) != TAIL_MAX_SESSIONS):
            return "--tail-min-room, --tail-effort and --tail-max-sessions are --tail-preset options"
        return None
    from harness.agent import MODEL_PRESETS   # noqa: E402
    if not A.set:
        return "--tail-preset needs --set/--arm (the tail runs in the arm's work root)"
    if not tail_preset_ok(MODEL_PRESETS.get(A.tail_preset)):
        return f"--tail-preset {A.tail_preset}: not an OpenRouter agent.py session preset (nor a list-priced Azure one)"
    if not (math.isfinite(A.tail_min_room) and A.tail_min_room >= 0):
        return f"--tail-min-room {A.tail_min_room:g}: a finite amount >= 0"
    if A.tail_max_sessions < 1:
        return "--tail-max-sessions must be at least 1"
    return None


def _hx_ladder_ns(A):
    """--ladder-args as hx_heldout's own parser reads them (None when they do not parse)."""
    import hx_heldout as H
    hp = H.build_parser()

    def _refuse(msg):
        raise ValueError(msg)
    hp.error = _refuse
    try:
        ns, _ = hp.parse_known_args(["--set", A.set, "--arm", A.arm or "-", *shlex.split(A.ladder_args or "")])
        return ns
    except (ValueError, argparse.ArgumentError):
        return None


def tail_floor_usd(A) -> float:
    """The session floor hx_heldout gives a tail session (hx_heldout.tail_floor): --session-floor when the ladder args set one; with
    --agent-budget-reclaim the preset's own (reclaim_session_floor at the preset's cap prices, base SESSION_FLOOR); else SESSION_FLOOR. The
    preset is the tail preset's stand-in when the run recorded a fallback for it (fb_model)."""
    import hx_heldout as H
    from harness.agent import MODEL_PRESETS, RECLAIM_FLOOR, cap_prices   # noqa: E402
    ns = _hx_ladder_ns(A)
    if ns is not None and getattr(ns, "session_floor", None) is not None:
        return float(ns.session_floor)
    if ns is None or not getattr(ns, "agent_budget_reclaim", False):
        return SESSION_FLOOR
    pp = MODEL_PRESETS.get(fb_model(A, A.tail_preset)) or MODEL_PRESETS[A.tail_preset]
    return H.reclaim_session_floor(cap_prices(pp), int(pp.get("adaptive_min", 6000)) if pp.get("adaptive_cap") else RECLAIM_FLOOR, SESSION_FLOOR)


def tail_room(A, name: str, cur: dict) -> float:
    """The row's room under the cap in cap-price dollars: cap - its metered spend (cap_spend_of: the reported spend plus every recorded
    cap-price difference, as summary.json's cap_spend) - SPEND_MARGIN, rounded DOWN to 1e-4; never below 0."""
    return max(0.0, math.floor((A.cap - cap_spend_of(A.run_dir, name, cur) - SPEND_MARGIN) * 1e4) / 1e4)


def tail_state_path(S, name: str) -> str | None:
    """The row's state.json in the arm's work root (the problem stored in it must be the row), else None."""
    if S is None:
        return None
    p = Path(S.wt) / S.root / safe(name) / "state.json"
    try:
        return str(p) if json.loads(p.read_text()).get("problem") == name else None
    except (OSError, ValueError, AttributeError):
        return None


def _state_spend(sp: str) -> tuple[float, float, dict]:
    st = json.loads(Path(sp).read_text())
    return float(st.get("api_spend") or 0), float(st.get("cap_extra") or 0), st


def _ceil6(x: float) -> float:
    return math.ceil(round(float(x), 9) * 1e6) / 1e6


def tail_plan_row(name: str, A, S, floor: float, log) -> dict:
    """One row's tail decision, persisted once: step `tail` (skipped at $0, with the reason) or step `tail_started` (room, top, the state's
    spend and best at the start; the current best written back so the sessions start from it). A row with either step keeps it."""
    rs = RowStore(A.run_dir, name)
    if rs.done(TAIL_STEP):
        return {"status": "done"}
    if rs.done(TAIL_START):
        return {"status": "started", "top": float(rs.d["steps"][TAIL_START]["report"]["top"])}
    cur = fold(rs, inp0(rs))
    sp = tail_state_path(S, name)
    room = tail_room(A, name, cur)
    least = max(float(A.tail_min_room), float(floor))
    why = ("dry run (no model call)" if A.dry_run else
           "the run is on its $0 path (a confirmed pin of every ladder preset)" if getattr(A, "pin_stop", None) else
           "no finished review" if not rs.done("review") else
           "no work-root state" if not sp else
           f"room ${room:.4f} below the tail's minimum ${least:.2f} (--tail-min-room ${float(A.tail_min_room):.2f}, session floor ${floor:.2f})"
           if room < least - 1e-9 else None)
    if why:
        rs.put(TAIL_STEP, cur, {"status": f"skipped: {why}", "room": room, "spent": 0.0, "sessions": 0, "turns": 0, "accepted": False,
                                "score_before": cur.get("score"), "score_after": cur.get("score")})
        log(f"{name[:40]}: tail skipped ($0): {why}")
        return {"status": "skipped", "why": why, "room": room}
    _a, _c, st = _state_spend(sp)
    b = st.get("best") or {}
    wb = False
    if cur.get("proof") and cur.get("verified", True) and P._finite(cur.get("score")) and (cur["proof"].strip() != (b.get("proof") or "").strip()):
        wb = write_back(sp, cur, log, min_gain=-1e-9)   # the sessions start from the row's current best (not below the stored one)
    api0, cap0, st = _state_spend(sp)
    top = math.floor((api0 + cap0 + room) * 1e4) / 1e4
    rep = {"room": room, "top": top, "api0": api0, "cap0": cap0, "spend0": float(cur.get("spend") or 0),
           "cap_spend0": cap_spend_of(A.run_dir, name, cur), "score0": cur.get("score"), "preset": A.tail_preset, "floor": floor,
           "min_room": float(A.tail_min_room), "state_path": sp, "best_sha0": _sha12((st.get("best") or {}).get("proof")), "written_back": wb}
    rs.put(TAIL_START, cur, rep)
    log(f"{name[:40]}: tail planned: room ${room:.4f} (metered ${rep['cap_spend0']:.4f} of ${A.cap:.2f}), session budget top ${top:.4f} "
        f"(state spend ${api0 + cap0:.4f})" + ("; the current best written back first" if wb else ""))
    return {"status": "planned", "top": top, "room": room}


def tail_argv(A, rows: list, tops_path, rungs: list) -> list:
    """hx_heldout's argv for the tail: the ladder's own args (its --preset-by-rung needs the run's rungs to parse), the rows, --tail and the
    tail settings, and the run's recorded preset fallback (b66)."""
    fbm = ((getattr(A, "pin_fallback", None) or {}).get("map") or {})
    return (["--set", A.set, "--arm", A.arm, "--ref", A.ref, "--rungs", ",".join(f"{r:.2f}" for r in rungs), *shlex.split(A.ladder_args or "")]
            + ["--problems", *rows, "--tail", str(tops_path), "--tail-preset", A.tail_preset, "--tail-effort", str(A.tail_effort),
               "--tail-max-sessions", str(int(A.tail_max_sessions))]
            + (["--preset-fallback", ",".join(f"{x}:{y}" for x, y in sorted(fbm.items()))] if fbm else []))


def tail_hx(A, rows: list, tops_path, rungs: list, tag: str, say) -> int:
    """One hx_heldout --tail invocation through run_phase (as a ladder phase: its log ladder-<tag>.log, its processes tagged and reaped
    past --ladder-timeout or on the router's SIGTERM). Tests inject a fake here."""
    fbm = ((getattr(A, "pin_fallback", None) or {}).get("map") or {})
    cmd = [sys.executable, "-u", str(ROOT / "harness/hx_heldout.py"), *tail_argv(A, rows, tops_path, rungs)]
    say(f"tail: hx_heldout --tail over {len(rows)} row(s), preset {A.tail_preset}"
        + (f"; preset fallback {', '.join(f'{x} -> {y}' for x, y in sorted(fbm.items()))} (confirmed max_price pin)" if fbm else ""))
    rc = run_phase(A, cmd, tag, say, "tail")   # b67's process handling: reaped past --ladder-timeout, SIGTERM passed on
    say(f"tail: hx_heldout exit {rc}")
    return rc


def tail_run(A, S, rows: list, tops_path, rungs: list, say) -> dict:
    """The tail sessions with b66's preset fallback: a CONFIRMED pin of the preset the sessions run moves them to another OpenRouter session
    preset of the run that still answers (pin_fallback_pick / pin_fallback_note: pin_fallback.json, a decisions line, the summary) and runs
    the tail again (the rows resume to their same tops); with none left the tail stops ($0 from there). Never sets the run-wide pin stop."""
    tag = "tail"
    rc = tail_hx(A, rows, tops_path, rungs, tag, say)
    for _ in range(len(ladder_presets(A)) + 2):
        if rc != pin_rc():
            break
        pinned, msg = pin_preset_of(A, S, tag)
        to = pin_fallback_pick(A, S, pinned)
        if not to:
            break
        pin_fallback_note(A, S, tag, pinned, to, msg, say)
        rc = tail_hx(A, rows, tops_path, rungs, tag, say)
    res = {"rc": rc}
    if rc == pin_rc():
        pinned, msg = pin_preset_of(A, S, tag)
        res["pin_stop"] = {"preset": pinned, "message": (msg or f"tail exited {rc} (a CONFIRMED max_price pin)")[:600], "at": now()}
        say(f"TAIL PIN STOP: {pinned or 'the tail preset'} is CONFIRMED pinned and no other session preset of the run answers: no further "
            "tail session ($0 from here); the rows keep what their tail sessions banked; the end stage runs as usual")
    return res


def _exact_reading(name: str, m: dict) -> float:
    """end_guard's unrounded score of a full reading (L and H from tokens and heartbeats)."""
    return exact_score(len_pct(LT.ROWS[name]["proof_length"], int(m["tokens"])), hb_pct_local(name, int(m["heartbeats"]), LT.HBS.get(name)),
                       float(m["Z"]))


def tail_guard(name: str, cur: dict, cand: dict, evaluator) -> dict:
    """The tail's acceptance: the pre-tail best and the tail's best read back to back on the router's evaluator, every pin. ok = the tail
    best passes the full check and (when the pre-tail best does) has no lower Z and an exact score higher by more than MIN_GAIN."""
    versions = P.newest_first(LT.ROWS[name]["version_info"])
    ev = (evaluator() if callable(evaluator) and not hasattr(evaluator, "bound") else evaluator).bound(name, versions)
    a = ev(cur["proof"], True) if cur.get("proof") else {}
    b = ev(cand["proof"], True)
    va, vb = bool(cur.get("proof")) and P._valid(a, versions, True), P._valid(b, versions, True)
    if not vb:
        return {"ok": False, "why": "the tail best fails the full check on the router's evaluator (every pin)", "tail": P._metrics(b), "delta": None}
    if not va:
        return {"ok": True, "why": "the pre-tail best fails the full check; the tail best passes on every pin", "tail": P._metrics(b), "delta": None}
    ea, eb = _exact_reading(name, a), _exact_reading(name, b)
    ok = float(b["Z"]) >= float(a["Z"]) - 1e-9 and eb > ea + P.MIN_GAIN + 1e-9
    return {"ok": ok, "why": f"back to back: tail {eb:.4f} vs pre-tail {ea:.4f} (bar +{P.MIN_GAIN:g})", "pre": P._metrics(a), "tail": P._metrics(b),
            "delta": round(eb - ea, 6)}


def tail_session_lines(S, name: str) -> list:
    """The row's lines of <hx out>/tail_sessions.jsonl (hx_heldout.TAIL_LOG)."""
    out = []
    try:
        for l in (Path(S.out) / "tail_sessions.jsonl").read_text().splitlines():
            try:
                d = json.loads(l)
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("problem") == name:
                out.append(d)
    except OSError:
        pass
    return out


def tail_finish(name: str, A, S, evaluator, log, res: dict | None = None) -> dict:
    """A planned row after the tail sessions: what they spent (the state's api_spend + cap_extra over the start's, so the row is booked once,
    whatever restarts happened) goes into the row (step `tail`: its spend, the ledger's sessions label, cap_extra:ladder); the work root's
    best, when the sessions changed it, is kept only through tail_guard (stored-scale score + the same-meter delta, as the end step). A row
    with a finished `tail` step is never finished again."""
    rs = RowStore(A.run_dir, name)
    item0 = inp0(rs)
    if rs.done(TAIL_STEP):
        return rs.item(TAIL_STEP)
    if not rs.done(TAIL_START):
        return fold(rs, item0)
    r0 = rs.d["steps"][TAIL_START]["report"]
    cur = fold(rs, item0)
    sp = r0["state_path"]
    api1, cap1, st = _state_spend(sp)
    d_api, d_cap = max(0.0, api1 - float(r0["api0"])), max(0.0, cap1 - float(r0["cap0"]))
    spend1 = _ceil6(float(cur.get("spend") or 0) + d_api)
    sess = tail_session_lines(S, name)
    rep = {"room": r0["room"], "top": r0["top"], "spent": round(d_api + d_cap, 6), "spent_reported": round(d_api, 6), "sessions": len(sess),
           "turns": sum(int(x.get("turns") or 0) for x in sess), "presets": sorted({x.get("preset") for x in sess if x.get("preset")}),
           "score_before": cur.get("score"), "room_after": round(float(r0["room"]) - d_api - d_cap, 6)}
    if (res or {}).get("pin_stop"):
        rep["pin_stop"] = res["pin_stop"]
    b = st.get("best") or {}
    item = dict(cur, spend=spend1)
    if not b.get("proof") or _sha12(b["proof"]) == r0.get("best_sha0") or b["proof"].strip() == (cur.get("proof") or "").strip():
        rep.update(accepted=False, status="no new best from the tail sessions" if sess else "no tail session ran")
    else:
        cand = {k: b[k] for k in ("proof", "score", "tokens", "heartbeats", "L", "H", "Z", "compat") if b.get(k) is not None}
        g = tail_guard(name, cur, cand, evaluator)
        rep.update(agent_score=b.get("score"), guard=g)
        if g["ok"]:
            m = g["tail"]
            item = {k: m[k] for k in ITEM_KEYS if m.get(k) is not None and k not in ("proof", "verified", "stage")}
            item.update(proof=b["proof"], verified=True, stage="tail", spend=spend1, state_path=sp)
            if g.get("delta") is not None and P._finite(cur.get("score")):
                item["measured_score"], item["score"] = m.get("score"), round(float(cur["score"]) + g["delta"], 2)
            rep.update(accepted=True, status="accepted: " + g["why"])
        else:
            rep.update(accepted=False, status="the pre-tail best stays: " + g["why"])
    rep["score_after"] = item.get("score") if rep.get("accepted") else cur.get("score")
    rs.put(TAIL_STEP, item, rep)
    led = RowLedger(A.run_dir, name)
    led.set("sessions", spend1)
    ladder_cap_extra(led, sp)
    if rep.get("accepted"):
        bank_item(sp, name, item, "tail", parent=cur.get("proof"))
    log(f"{name[:40]}: tail: ${rep['spent']:.4f} of ${float(r0['room']):.4f} room, {rep['sessions']} session(s), {rep['turns']} turn(s); "
        f"{cur.get('score')} -> {rep['score_after']} ({rep['status']})")
    return item


def tail_book_only(name: str, A, why: str, log) -> None:
    """tail_finish failed for a planned row: its spend is still booked (from the state when it reads, else the whole room assumed spent, as an
    interrupted review's budget), the pre-tail best stays. Never raises."""
    try:
        rs = RowStore(A.run_dir, name)
        if rs.done(TAIL_STEP) or not rs.done(TAIL_START):
            return
        r0 = rs.d["steps"][TAIL_START]["report"]
        cur = fold(rs, inp0(rs))
        try:
            api1, cap1, _ = _state_spend(r0["state_path"])
            d_api, d_cap, assumed = max(0.0, api1 - float(r0["api0"])), max(0.0, cap1 - float(r0["cap0"])), False
        except Exception:  # noqa: BLE001
            d_api, d_cap, assumed = float(r0["room"]), 0.0, True
        spend1 = _ceil6(float(cur.get("spend") or 0) + d_api)
        rs.put(TAIL_STEP, dict(cur, spend=spend1), {"status": f"failed ({why}): spend booked" + (" (the whole room assumed)" if assumed else "")
                                                    + "; the pre-tail best stays", "room": r0["room"], "top": r0["top"],
                                                    "spent": round(d_api + d_cap, 6), "assumed": assumed, "accepted": False,
                                                    "score_before": cur.get("score"), "score_after": cur.get("score")})
        RowLedger(A.run_dir, name).set("sessions", spend1)
        log(f"{name[:40]}: tail failed ({why}); ${d_api + d_cap:.4f} booked" + (" (assumed)" if assumed else "") + "; the pre-tail best stays")
    except Exception as e:  # noqa: BLE001
        log(f"{name[:40]}: tail spend not booked ({type(e).__name__}: {str(e)[:120]}); the outputs read it from the state (tail_pending_spend)")


def tail_pending_spend(A, name: str) -> float | None:
    """A row inside its tail (step `tail_started`, no `tail` yet): its reported spend so far (the start's + the state's api_spend growth),
    for the outputs written on an exit before the row is finished; None otherwise."""
    try:
        rs = RowStore(A.run_dir, name)
        if rs.done(TAIL_STEP) or not rs.done(TAIL_START):
            return None
        r0 = rs.d["steps"][TAIL_START]["report"]
        try:
            api1, _c, _st = _state_spend(r0["state_path"])
            d = max(0.0, api1 - float(r0["api0"]))
        except Exception:  # noqa: BLE001
            d = float(r0["room"])
        return _ceil6(float(r0["spend0"]) + d)
    except Exception:  # noqa: BLE001
        return None


def _tail_record(A, rec: dict) -> None:
    try:
        old = json.loads((A.run_dir / TAIL_FILE).read_text())
    except (OSError, ValueError):
        old = {}
    old.setdefault("invocations", []).append(rec)
    old.update({k: v for k, v in rec.items() if k in ("rc", "pin_stop", "error", "at", "worst_case_usd", "rows", "preset", "floor")})
    tmp = A.run_dir / f".{TAIL_FILE}.tmp"; tmp.write_text(json.dumps(old, indent=1)); tmp.replace(A.run_dir / TAIL_FILE)


def tail_stage(A, S, names: list, rungs: list, evaluator, say) -> None:
    """The tail over the run's rows (see the section notes). Never raises an Exception: a failure is logged, every planned row is finished
    (tail_finish) or at least its spend booked (tail_book_only), and the run goes on to the end stage (the no-harm rule,
    2026-10-27). A row whose planning or finishing fails never stops another row."""
    rec: dict = {"at": now()}
    planned: list = []

    def plan_safe(n, floor):   # a failure plans nothing for the row (a $0 skip step)
        try:
            return tail_plan_row(n, A, S, floor, say)
        except Exception as e:  # noqa: BLE001
            say(f"{n[:40]}: tail not planned ({type(e).__name__}: {str(e)[:160]}); $0")
            try:
                rs = RowStore(A.run_dir, n)
                if not rs.done(TAIL_START) and not rs.done(TAIL_STEP):
                    rs.put(TAIL_STEP, fold(rs, inp0(rs)), {"status": f"skipped: planning failed ({type(e).__name__})", "spent": 0.0, "sessions": 0,
                                                          "turns": 0, "accepted": False})
            except Exception:  # noqa: BLE001
                pass
            return {"status": "failed"}

    def finish_safe(n):   # a failure still books the row's spend (tail_book_only)
        try:
            return tail_finish(n, A, S, evaluator, say, rec)
        except Exception as e:  # noqa: BLE001
            tail_book_only(n, A, f"{type(e).__name__}: {str(e)[:160]}", say)
            return None
    try:
        floor = tail_floor_usd(A)
        plans = dict(zip(names, _pmap(A.jobs, lambda n: plan_safe(n, floor), names)))
        planned = [n for n in names if plans[n]["status"] in ("planned", "started")]
        r0s = {n: RowStore(A.run_dir, n).d["steps"][TAIL_START]["report"] for n in planned}
        # b68 review: the worst case is every row the tail was ever planned on (a restart after some rows finished their tail still
        # reports the run's whole bound, not only the rows left: tail.json / summary.json "worst_case_usd" went to $0 on such a restart)
        every = {n: RowStore(A.run_dir, n).d["steps"][TAIL_START]["report"] for n in names if RowStore(A.run_dir, n).done(TAIL_START)}
        worst = round(sum(float(r["room"]) for r in every.values()), 4)
        rec.update(preset=A.tail_preset, floor=floor, rows=len(every), worst_case_usd=worst)
        say(f"tail: {len(every)} of {len(names)} row(s) with room >= ${max(float(A.tail_min_room), floor):.2f} (--tail-min-room "
            f"${float(A.tail_min_room):.2f}, session floor ${floor:.2f}); enforced worst case ${worst:.4f} (the rows' rooms)"
            + (f"; {len(planned)} of them still to finish" if len(planned) != len(every) else ""))
        if planned and not A.dry_run and not getattr(A, "pin_stop", None):
            tp = A.run_dir / TAIL_TOPS
            tmp = A.run_dir / f".{TAIL_TOPS}.tmp"; tmp.write_text(json.dumps({"tops": {n: float(r0s[n]["top"]) for n in planned}}, indent=1))
            tmp.replace(tp)
            rec.update(tail_run(A, S, planned, tp, rungs, say))
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        say(f"TAIL FAILED ({rec['error']}): every planned row is still finished or its spend booked; the end stage runs as usual")
    try:
        list(_pmap(A.jobs, finish_safe, [n for n in planned if not RowStore(A.run_dir, n).done(TAIL_STEP)]))
    except Exception as e:  # noqa: BLE001
        rec.setdefault("error", f"{type(e).__name__}: {str(e)[:300]}")
    for n in planned:   # belt and braces: a planned row without its tail step after all that is booked here
        try:
            if not RowStore(A.run_dir, n).done(TAIL_STEP):
                tail_book_only(n, A, rec.get("error") or "the row's tail step did not finish", say)
        except Exception:  # noqa: BLE001
            pass
    try:
        _tail_record(A, rec)
    except Exception as e:  # noqa: BLE001
        say(f"tail: {TAIL_FILE} not written ({type(e).__name__})")


def tail_summary(A, names: list) -> dict:
    """summary.json "tail" (only with the tail on)."""
    per = {}
    for n in names:
        r = ((RowStore(A.run_dir, n).d["steps"].get(TAIL_STEP) or {}).get("report") or {})
        per[n] = {"room": r.get("room"), "spent": r.get("spent"), "sessions": r.get("sessions"), "turns": r.get("turns"),
                  "before": r.get("score_before"), "after": r.get("score_after"), "accepted": bool(r.get("accepted")), "status": r.get("status")}
    try:
        rec = json.loads((A.run_dir / TAIL_FILE).read_text())
    except (OSError, ValueError):
        rec = {}
    ran = [n for n in names if (per[n]["sessions"] or 0) > 0]
    acc = [n for n in names if per[n]["accepted"]]
    spent = [float(per[n]["spent"] or 0) for n in names]
    return {"preset": A.tail_preset, "min_room": float(A.tail_min_room), "effort": A.tail_effort, "max_sessions": int(A.tail_max_sessions),
            "rows": len(names), "planned": sum(1 for n in names if RowStore(A.run_dir, n).done(TAIL_START)), "ran": len(ran), "accepted": len(acc),
            "spend": round(sum(spent), 4), "spend_max": round(max(spent or [0]), 4), "sessions": sum(int(per[n]["sessions"] or 0) for n in names),
            "turns": sum(int(per[n]["turns"] or 0) for n in names),
            "gain": round(sum(float(per[n]["after"] or 0) - float(per[n]["before"] or 0) for n in acc), 3),
            "worst_case_usd": rec.get("worst_case_usd"), "rc": rec.get("rc"), "pin_stop": rec.get("pin_stop"), "error": rec.get("error"),
            "per_row": per}

def guarded(fn, name, item0, log, *args, **kw) -> dict:
    """One row's failure never stops the others: the row keeps its best recorded item."""
    try:
        return fn(name, *args, **kw)
    except Exception as e:  # noqa: BLE001
        log(f"{name[:40]}: router step failed: {type(e).__name__}: {str(e)[:160]}")
        A = next(a for a in args if hasattr(a, "run_dir"))
        return final_of(RowStore(A.run_dir, name), item0)


# ------------------------------------------------------------------------------------------------------------- outputs (b65-final)
class RouterTerminated(BaseException):
    """b65-final: SIGTERM (systemd stop, a kill) in the router's main thread. A BaseException, so no `except Exception` on the way swallows it;
    it unwinds to main's finally, which writes the outputs (finals.json, submission.jsonl), then the router exits TERM_RC."""


def _on_sigterm(signum, frame):   # noqa: ARG001
    raise RouterTerminated(signum)


def _pmap(jobs: int, fn, names: list) -> list:
    """ThreadPoolExecutor.map over the rows. b65-final: on an exception in the main thread (SIGTERM included) it does not wait for the rows in
    flight (shutdown(wait=False), queued rows cancelled): main's finally writes the outputs at once (each row's steps are on disk)."""
    ex = ThreadPoolExecutor(max(1, jobs))
    ok = False
    try:
        out = list(ex.map(fn, names)); ok = True
        return out
    finally:
        ex.shutdown(wait=ok, cancel_futures=not ok)


def row_candidates(A, S, name: str, final: dict | None = None, wr: dict | None = None, base: dict | None = None) -> list:
    """b65-final: the submission writer's candidates of a row, in preference order: the router's final (`final`; else the provisional best:
    final_of its steps, or `base` before any step, then better() with the ladder's current work-root best `wr`), then the row's other verified
    step items and `wr`, by score."""
    rs = RowStore(A.run_dir, name)
    others = [(f"step:{k}", st.get("item") or {}) for k, st in rs.d["steps"].items()]
    others = [(k, it) for k, it in others if it.get("proof") and it.get("verified", True) and it.get("score") is not None]
    if wr and wr.get("proof") and not wr.get("seed"):
        others.append(("ladder", wr))
    if final is None:
        cur = final_of(rs, inp0(rs)) if rs.d["steps"] else dict(base or {})
        final = better(wr, cur) if wr and wr.get("proof") and not wr.get("seed") else cur
    others.sort(key=lambda x: -float(x[1].get("score") or 0))
    return [("final", final)] + others


class Outputs:
    """b65-final (audit C1 + C2): the router's outputs on every exit path. start(): the seed-only submission file; checkpoint() / row_done():
    one row's line (static checks; row_done compile-checks it); finish(): from main's finally, finals.json when the run did not reach OUT
    (each row's provisional best) with a partial summary.json, and every row's submission line."""

    def __init__(self, A, S, names: list, evaluator, say, base_of=None):
        from harness import final_writer as FW
        self.A, self.S, self.names, self.say, self.base_of = A, S, list(names), say, base_of or (lambda n: None)
        self.finals_written = False
        seeds = {n: (LT.ROWS.get(n) or {}).get("src") or (self.base_of(n) or {}).get("proof") for n in self.names}
        sts = {n: (LT.ROWS.get(n) or {}).get("statement") for n in self.names}
        rows = {n: LT.ROWS[n] for n in self.names if (LT.ROWS.get(n) or {}).get("version_info")}
        fn = FW.router_compile_fn(evaluator, rows)
        au = FW.router_audit_fn(rows)   # b71 R1: the final axiom audit on every pin (harness/final_writer.py module docstring)
        self.W = FW.Writer(A.run_dir, self.names, seeds, sts, compile_fn=lambda n, p: fn(n, p) if n in rows else ("unknown", "no pins listed"),
                           log=say, audit_fn=lambda n, p: au(n, p) if n in rows else ("unknown", "no pins listed"))

    def start(self) -> None:
        c = self.W.start()
        self.say(f"submission: {self.W.path} written at start ({c['seeded']} row(s) on their seed proof, {c['kept']} kept from an earlier "
                 "invocation); it is rewritten per row and on every exit path")

    def _row(self, name: str, item: dict, compile_ok: bool) -> None:   # never raises: a writer failure is logged, the row's old line stays
        try:
            self.W.row(name, row_candidates(self.A, self.S, name, final=item, base=self.base_of(name)), compile_ok=compile_ok)
        except Exception as e:  # noqa: BLE001
            self.say(f"{name[:40]}: submission line not updated ({type(e).__name__}: {str(e)[:120]})")

    def checkpoint(self, name: str, item: dict) -> None:   # the checkpoint cleanup's output (verified there): static checks only
        self._row(name, item, False)

    def row_done(self, name: str, item: dict) -> dict:   # a finished row's final: compile-checked
        self._row(name, item, True)
        return item

    def provisional(self) -> tuple[dict, dict]:
        """Each row's best so far (steps' fold + the ladder's current work-root best; its seed item when it has neither): finals.json on an
        exit before OUT. Returns (items, the work-root items)."""
        wr = {}
        if self.S is not None:
            try:
                wr = work_root_items(self.S, self.names)
            except Exception as e:  # noqa: BLE001
                self.say(f"outputs: the ladder's work root not read ({type(e).__name__}: {str(e)[:120]})")
        out = {}
        for n in self.names:
            try:
                out[n] = row_candidates(self.A, self.S, n, wr=wr.get(n), base=self.base_of(n))[0][1]
                if not (out[n] or {}).get("proof"):
                    out[n] = dict(wr.get(n) or self.base_of(n) or {})
                if tail_on(self.A):   # b68: a row inside its tail: the sessions' spend so far (the state's) is in its spend
                    pend = tail_pending_spend(self.A, n)
                    if pend is not None:
                        out[n] = dict(out[n], spend=max(float(out[n].get("spend") or 0), pend))
            except Exception as e:  # noqa: BLE001
                self.say(f"{n[:40]}: provisional final not read ({type(e).__name__}); its seed stands")
                out[n] = dict(self.base_of(n) or {})
        return out, wr

    def finish(self, rc, exc=None, term: bool = False) -> None:
        """main's finally. Never raises (an output failure is logged)."""
        A = self.A
        why = ("SIGTERM" if term else f"exception {type(exc).__name__}: {str(exc)[:160]}" if exc is not None
               else f"exit {rc}" if rc not in (0, 1, PIN_STOP_RC) or not self.finals_written else None)
        try:
            prov, wr = ({}, {}) if self.finals_written else self.provisional()
            if not self.finals_written:
                fin = {n: {k: v for k, v in (prov.get(n) or {}).items() if k not in ("state_path", "seed")} for n in self.names}
                (A.run_dir / ".finals.json.tmp").write_text(json.dumps(fin, ensure_ascii=False, indent=1))
                (A.run_dir / ".finals.json.tmp").replace(A.run_dir / "finals.json")
                sc = [float(fin[n].get("score") or 33.33) for n in self.names]
                summ = {"partial": True, "rows": len(self.names), "at": now(), "mean_final": round(sum(sc) / max(1, len(sc)), 3),
                        "spend_max": max([float(fin[n].get("spend") or 0) for n in self.names] or [0]),
                        "exit": {"code": TERM_RC if term else rc, "reason": why, "outputs_complete": True,
                                 "note": "the run stopped before OUT: finals.json holds each row's best so far (its recorded steps and the "
                                         "ladder's current best); submission.jsonl each row's verified pick or its seed; a restart resumes"},
                        "per_row": {n: {"final": fin[n].get("score"), "spend": fin[n].get("spend")} for n in self.names}}
                if getattr(A, "pin_stop", None):
                    summ["pin_unservable"] = {A.pin_stop.get("preset") or "ladder": A.pin_stop.get("message")}
                if ((getattr(A, "pin_fallback", None) or {}).get("map")):   # b66 (A3)
                    summ["pin_fallback"] = A.pin_fallback
                (A.run_dir / ".summary.json.tmp").write_text(json.dumps(summ, indent=1))
                (A.run_dir / ".summary.json.tmp").replace(A.run_dir / "summary.json")
                self.say(f"outputs ({why}): finals.json written from each row's best so far (mean {summ['mean_final']})")
            fins = json.loads((A.run_dir / "finals.json").read_text()) if self.finals_written else prov

            def cands(n):
                return row_candidates(A, self.S, n, final=dict(fins.get(n) or {}) or None, wr=wr.get(n), base=self.base_of(n))
            cnt = self.W.all_rows(cands, compile_ok=not term, jobs=max(1, int(getattr(A, "jobs", 1) or 1)))
            self.say(f"submission: {self.W.path} written ({len(self.names)} row(s): {', '.join(f'{v} {k}' for k, v in sorted(cnt.items()))})"
                     + (f" [{why}]" if why else ""))
        except BaseException as e:  # noqa: BLE001  (the outputs never mask the exit; the per-row lines written so far stay)
            try:
                self.say(f"outputs: not completed ({type(e).__name__}: {str(e)[:200]}); the submission file keeps its last complete write")
            except Exception:  # noqa: BLE001
                pass


def review_call_check(model: str, max_tokens: int, cap: float, top: float, reserve: float, budget_mode: str, cap_price: str) -> tuple:
    """The startup check of the review (2026-10-19; b64 L0). Returns (refusal text or None, note or None, numbers). Every call is priced at
    the CAP price (agent.cap_prices, `cap_price` mode) with the smallest input (INPUT_SLACK_TOKENS).
      reserve  (pre-L0 budget, at most the reserve): one full --review-max-tokens call must fit the reserve, as before (a call that does not
               fit is shrunk, so a reserve below it starves every review)
      room     (b64 L0: the budget is the row's room under the cap): a row reaches the review with at least `least_room` = the room the ladder
               top leaves (review_budget_usd at spend = top); the review is refused only when even the smallest call it sends
               (min(REVIEW_MIN_TOKENS, max_tokens) output tokens; review.PricedCaller shrinks a larger one to fit) does not fit that room, i.e.
               when every review of a row at the top would be skipped. A full call above it is a note: the first call of such a row is shrunk."""
    from harness.agent import MODEL_PRESETS, cap_prices
    from harness.review import INPUT_SLACK_TOKENS, REVIEW_MIN_TOKENS
    pr = cap_prices(model, cap_price) if model in MODEL_PRESETS else None
    if not pr:
        return None, None, {}

    def worst(n: int) -> float:
        return (n * pr[1] + INPUT_SLACK_TOKENS * max(pr[0], pr[3])) / 1e6   # the smallest input included
    full = worst(max_tokens)
    if budget_mode == "reserve":
        nums = {"full": full, "reserve": reserve, "prices": pr}
        if full > reserve + 1e-9:
            return (f"one review call's worst case ${full:.2f} ({max_tokens} tokens) exceeds the review reserve ${reserve:.2f}: "
                    "every review would be skipped; lower --review-max-tokens or raise --review-reserve"), None, nums
        return None, None, nums
    room = review_budget_usd(cap, top, reserve, "room")
    n_min = min(REVIEW_MIN_TOKENS, max_tokens)
    least = worst(n_min)
    nums = {"full": full, "least": least, "least_room": room, "min_tokens": n_min, "prices": pr}
    if least > room + 1e-9:
        return (f"the smallest review call's worst case ${least:.3f} ({n_min} output tokens at the {cap_price} price) exceeds the room "
                f"${room:.4f} a row at the ladder top ${top:.2f} brings to the review (cap ${cap:.2f}): every such review would be skipped; "
                "raise --review-reserve or lower --target-frac"), None, nums
    note = (f"review: one full {max_tokens}-token call's worst case ${full:.3f} (at the {cap_price} price, ${pr[0]:g} / ${pr[1]:g} per 1M) "
            f"exceeds the ${room:.4f} room a row at the ladder top brings to the review: such a row's first call is shrunk to fit (b64 L0)"
            if full > room + 1e-9 else None)
    return None, note, nums


def fallback_args_check(A) -> str | None:
    """b66 (A3): --review-fallback-model is a preset other than --review-model; every --pin-fallback-preset is an OpenRouter agent.py
    session preset. The refusal text, else None."""
    from harness.agent import MODEL_PRESETS   # noqa: E402
    rf = getattr(A, "review_fallback_model", None)
    if rf and (rf == A.review_model or rf not in MODEL_PRESETS):
        return f"--review-fallback-model {rf}: not a preset of harness/agent.py other than --review-model"
    for p in [x.strip() for x in str(getattr(A, "pin_fallback_preset", None) or "").split(",") if x.strip()]:
        pp = MODEL_PRESETS.get(p) or {}
        if not pp or pp.get("anthropic_vertex") or "openrouter.ai" not in (pp.get("base_url") or ""):
            return f"--pin-fallback-preset {p}: not an OpenRouter agent.py session preset"
    if getattr(A, "pin_fallback_preset", None) and not A.set:
        return "--pin-fallback-preset needs --set/--arm (a ladder)"
    return None


def resumed_mode(A, key: str):
    """The value of a frozen option this run will use: a run dir whose config.json predates the option keeps LEGACY (main() applies it after
    the freeze check; the startup checks before it need the same value)."""
    rd = Path(A.run_dir); rd = rd if rd.is_absolute() else ROOT / rd
    try:
        frozen = json.loads((rd / "config.json").read_text())
    except (OSError, ValueError):
        return getattr(A, key)
    return LEGACY[key] if key in LEGACY and key not in frozen else getattr(A, key)


# ----------------------------------------------------------------------------------------------------------------------- driver
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, help="the router's own directory (state, decisions, outputs); a rerun resumes it")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--set", help="hx_heldout set key (with --arm): ladder tiers available")
    src.add_argument("--input", help="finals JSON {problem: {proof, score, spend, ...}}: no ladder tiers")
    ap.add_argument("--arm"); ap.add_argument("--ref", default=None, help="git ref for the ladder worktree (frozen at the first start)")
    ap.add_argument("--ladder-args", default="", help="the arm's hx_heldout flags (preset, effort, workers, docker, auto-brief ...), quoted")
    ap.add_argument("--checkpoints", default=None, help="ladder budgets at which the gate runs (default: --policy v3 "
                    + ",".join(f"{c:.2f}" for c in V3_CHECKPOINTS) + "; v2.2 " + ",".join(f"{c:.2f}" for c in CHECKPOINTS) + ")")
    ap.add_argument("--policy", dest="gate_policy", choices=["v3", "v2.2"], default="v3", help="b63 item 2 (docs/adaptive_plan_93.md §1.4-1.5): v3 = plateau-as-order "
                    "+ decision kinds + flex rule, no open-ended re-plan; v2.2 = the 2026-10-18 gate (saturated / L-bound / climbing / re-plan). Frozen")
    ap.add_argument("--no-cross", dest="cross", action="store_false", help="b63 item 3: skip the $0 bank crossover before the review (default: run "
                    "it; endstage.splices over the row's whole bank, CROSS_TOP parents, accept.decide, all pins). Frozen")
    ap.add_argument("--no-flex", dest="flex", action="store_false", help="b63 item 2: a plateaued row at or above 90 at the last checkpoint keeps "
                    "the ladder (default: flex rule, its rest unspent). Frozen")
    ap.add_argument("--routes", action="store_true", help="b63 item 16 (docs/adaptive_plan_93.md §1.4; harness/artifacts.py, harness/repair.py, "
                    "agent.py --artifact): with --policy v3, at every checkpoint the row's compiled artifacts (skeletons with holes, near-misses: "
                    "the sessions' skeletons.jsonl / near_misses.jsonl and the C1 pass's records in rows/<ws>.cpu_pass.json) decide the paid "
                    "route on a plateau: REPAIR (Argon over the review client, <= --route-budget) or ARTIFACT-SESSION (agent.py --artifact, "
                    "<= --artifact-turns turns, <= --route-budget); no artifact -> polish-only / ladder as without the flag. Persisted in "
                    "route.json and decisions.jsonl (kinds repair / artifact-session, REPAIR step lines). OFF by default: v3 runs are unaffected")
    ap.add_argument("--route-model", default="gemini-4-argon-vertex", help="--routes: the REPAIR model (through harness/review.PricedCaller)")
    ap.add_argument("--route-effort", default="medium")
    ap.add_argument("--route-budget", type=float, default=ROUTE_BUDGET, help="--routes: the cap of one routed step (plan §1.1 P: <= $0.50)")
    ap.add_argument("--route-steps", type=int, default=REPAIR_STEPS, help="--routes: REPAIR steps per routed slice (<= 10)")
    ap.add_argument("--artifact-model", default=None, help="--routes: the ARTIFACT-SESSION preset (default --replan-model)")
    ap.add_argument("--artifact-turns", type=int, default=ARTIFACT_TURNS, help="--routes: ARTIFACT-SESSION turns (12-16)")
    ap.add_argument("--artifact-args", default=ARTIFACT_ARGS, help="--routes: the ARTIFACT-SESSION's agent.py flags (default: the v3 ladder's "
                    "per-session flags; never the re-plan's --brief restructure), plus --auto-brief and --artifact")
    ap.add_argument("--skip-l1", action="store_true", help="the arm already ran to the first checkpoint")
    ap.add_argument("--ladder-timeout", type=int, default=86400)
    ap.add_argument("--cap", type=float, default=3.0, help="hard per-row inference cap (USD; b65 default $3.00, the rule's cap, used whole: "
                    "ladder top = cap x --target-frac - --review-reserve = $2.75, the review gets the row's room under the cap)")
    ap.add_argument("--target-frac", type=float, default=TARGET_FRAC, help="ladder top = target x cap - review reserve (at most 1.0; "
                    "2026-10-22: 1.0 approved within the cap; b65: the default, was 0.90)")
    ap.add_argument("--allow-lineage-rule", action="store_true", help="lever 2 guard: let a '-clean' set run with --ladder-args that keep "
                    "hx_heldout's lineage rule on or carry --rescue > 0 (not the final pipeline's measured ladder); not frozen, logged")
    ap.add_argument("--gate", type=float, default=GATE)
    ap.add_argument("--climb", type=float, default=CLIMB, help="last ladder session gain at or above which a row stays on the ladder")
    ap.add_argument("--review-reserve", type=float, default=REVIEW_RESERVE)
    ap.add_argument("--min-replan", type=float, default=MIN_REPLAN)
    ap.add_argument("--twins", action="store_true", help="v2.2: re-plan rows run two half-budget sessions from the same start (kill rule ~$0.8/pt). "
                    "v3 (b63 item 17, off until PB3-G3 passes): at the flex point a c6 row (reference < 80 tokens, sessions <= $0.20) or a row "
                    "whose bank holds a compiling candidate of another structural class within 1.0 of the best splits the room between the ladder lineage and a twin "
                    "session from the checkpoint best (postpass.seed_workspace); SELECT keeps a runner-up only within 1.0 and of another class. Frozen")
    ap.add_argument("--twin-args", default=TWIN_ARGS, help="agent.py flags of a twin session (default: the v3 ladder session's flags); frozen")
    ap.add_argument("--twin-turns", type=int, default=TWIN_TURNS, help="turns of a twin session (default: as the ladder's sessions); frozen")
    # 2026-10-20: development runs use Sol on Azure and Argon on Vertex, metered at the OpenRouter list prices; the final package
    # and its rehearsal pass the OpenRouter presets (gpt-6.1-sol-main, gemini-4-argon) explicitly
    ap.add_argument("--replan-model", default="sol-azure")
    ap.add_argument("--replan-turns", type=int, default=40)
    ap.add_argument("--replan-args", default=REPLAN_ARGS, help="extra agent.py flags for the re-plan session")
    ap.add_argument("--replan-timeout", type=int, default=5400)
    ap.add_argument("--auto-brief-dir", default=None, help="agent.py --auto-brief DIR for the re-plan (default with --set: <arm root>/_autobrief)")
    ap.add_argument("--review-model", default="gemini-4-argon-vertex")
    ap.add_argument("--review-fallback-model", default=None, help="b66 (retro A3): after a CONFIRMED max_price pin of --review-model, that "
                    "row's review goes on on this preset (its remaining rounds and budget, every call gated at THIS preset's cap price) "
                    "instead of being skipped at $0; unset (default) = skipped as before. Frozen; runs started before the option keep none")
    ap.add_argument("--pin-fallback-preset", default=None, metavar="P[,P2]", help="b66 (retro A3): an extra OpenRouter session preset the "
                    "ladder falls back to after a CONFIRMED max_price pin of its own presets (they come first: --preset, --preset-by-rung, "
                    "--first-preset in --ladder-args); used only then, gated at its own cap price. Unset (default): the run's own presets "
                    "only. Frozen; runs started before the option keep none")
    ap.add_argument("--review-effort", default="medium"); ap.add_argument("--review-rounds", type=int, default=3)
    ap.add_argument("--review-k", type=int, default=5)
    ap.add_argument("--review-max-tokens", type=int, default=REVIEW_MAX_TOKENS)
    ap.add_argument("--review-repair", type=int, default=0, help="b72 R6 (docs/b72_r6.md; off by default): one repair turn per review edit "
                    "that failed to compile, at most N per row per review round: the review model gets only the edit, the error and the local "
                    "goal; priced, gated and booked as the review's calls. Frozen (config.json review_r6)")
    ap.add_argument("--review-stack", action="store_true", help="b72 R6 (off by default): after each review round, every compiling edit "
                    "within --review-stack-eps of the round base stacked in ONE full compile (greedy fallback); a stack verified on every pin "
                    "goes into the row's bank for the end stage's acceptance. Frozen")
    ap.add_argument("--review-stack-eps", type=float, default=REVIEW_STACK_EPS, help=f"--review-stack: admission margin under the round base "
                    f"(default {REVIEW_STACK_EPS})")
    ap.add_argument("--review-budget", choices=REVIEW_BUDGET_MODES, default="room", help="b64 L0 (cap safety): room = the review's budget is "
                    "the row's whole room under the cap (cap - spend - margin; at least the reserve the ladder top leaves), reserve = at most "
                    "--review-reserve (the pre-L0 rule). Frozen; runs started before the option keep reserve")
    ap.add_argument("--cap-price", choices=CAP_PRICE_MODES, default="announced", help="b64 L0 (cap safety): the price every paid Argon call "
                    "(review, REPAIR) is GATED at: announced = a preset's announced price (agent.cap_prices: Gemini 4 Argon $4 / $20, cached "
                    "$0.20), list = its metered table (the pre-L0 gate). Spend is reported at the list table either way. Frozen; runs started "
                    "before the option keep list")
    ap.add_argument("--agent-docker", default=None); ap.add_argument("--agent-docker-memory", default="48g")
    ap.add_argument("--agent-private-scratch", default=None); ap.add_argument("--agent-mask-strays", action="store_true")
    ap.add_argument("--clean-stages", default=",".join(CLEAN_STAGES), help="the $0 postpass stages at every checkpoint")
    ap.add_argument("--clean2-stages", default=",".join(CLEAN2_STAGES), help="the $0 postpass stages after a paid tier changed a row")
    ap.add_argument("--clean-deadline-s", type=float, default=CLEAN_DEADLINE_S,
                    help="L5: the wall limit (seconds per row and stage) of the cleanups' rules / oracle / certify stages, which stop on "
                         f"their compile budget (postpass --max-compiles) first; default {CLEAN_DEADLINE_S:g} = postpass --deadline-s (unchanged). "
                         "A count-budget launch passes a generous backstop instead (probe/b63/r9_candidate.json _router). Frozen")
    ap.add_argument("--rules-exclude", default="", help="B26: rules-stage kind labels never offered in any cleanup (postpass --rules-exclude: "
                    "comma list or @FILE, e.g. @probe/b26/in/literal_kinds.txt; a relative FILE is read from the repository root); frozen in "
                    "config.json as the sorted label list")
    ap.add_argument("--rows"); ap.add_argument("--heartbeats")
    ap.add_argument("--problems", nargs="*")
    ap.add_argument("--jobs", type=int, default=6, help="rows processed at once (2026-10-19: 3 -> 6; the host sat at load ~9 of 20 cores)")
    ap.add_argument("--compile-slots", type=int, default=None, help="2026-10-26 (b63-speed2, probe/b63/fast_iteration.md): physical "
                    "compiles at once in the $0 stages (cleanups, crossover, end stage: harness/hb_tool_eval.Evaluator). Default: 3 per "
                    "scratch directory, shared by ALL rows of the run (and by every router started from the same checkout), so --jobs "
                    "above 3 adds rows, not compiles. N sets $LRA_HBTOOL_SLOTS=N and a scratch of this run's own "
                    "(probe/hbtool/.scratch/router-<hash of --run-dir>) unless $LRA_HBTOOL_SCRATCH is set; the ladder's subprocess "
                    "inherits the slot count (b65: hx_heldout passes it to its containers), never that scratch. The unit's memory gate still admits each compile (8 GB claim + 8 GB reserve inside MemoryMax). "
                    "Not frozen (a speed knob)")
    ap.add_argument("--no-fast-checkpoint-cleanup", dest="fast_checkpoint_cleanup", action="store_false", help="run every free pass at "
                    "every checkpoint (the pre-2026-10-19 behaviour)")
    ap.add_argument("--dry-run", action="store_true", help="no model call anywhere: ladder phases skipped, replan and review stubbed")
    ap.add_argument("--accept-short", action="store_true", help="a ladder phase that exited non-zero with rows below its rung goes on with "
                    "them (default: stop with exit 3 so a restart refills them); not frozen")
    ap.add_argument("--accept-code-change", action="store_true", help="resume although harness/, scorer/ or llm/ differ from the code the "
                    "run started with (default: refuse); not frozen, logged")
    ap.add_argument("--no-replan-continue", dest="replan_continue", action="store_false", help="one re-plan session only (the pre-2026-10-19 "
                    "behaviour); default: further sessions from the best proof until the row's re-plan budget is used")
    ap.add_argument("--no-replan", dest="replan", action="store_false", help="never re-plan: the A/B control arm (identical to the router "
                    "in every other step, so the paired difference isolates the re-plan branch)")
    ap.add_argument("--no-write-back", dest="write_back", action="store_false", help="keep checkpoint clean gains in the router only "
                    "(the A/B control arm: today's pipeline, whose ladder never sees them)")
    ap.add_argument("--anon", action="store_true", help="log rows as row#k (sealed sets: names never reach a log or the console)")
    ap.add_argument("--end-stage", action="store_true", help="B62b: the $0 end stage after the review on every row (harness/endstage.py: "
                    "one meter, back to back, sweep + crossover, scorer/accept.decide); frozen; off for runs started before the option")
    ap.add_argument("--end-k", type=int, default=END_K, help="end stage: candidates re-measured besides the seed and the floors")
    ap.add_argument("--end-max-compiles", type=int, default=END_MAX_COMPILES, help="end stage: compiles per row (self-test excluded)")
    ap.add_argument("--end-config", default=None, help="2026-10-22: with --end-stage, a frozen end-stage config (harness/endstage.py --config format, e.g. probe/b62/r3_frozen.json: tool families, budgets, caps, screening, t3 suggestions) instead of --end-k / --end-max-compiles; its sha256 is frozen with the run")
    ap.add_argument("--end-dual-start", action=argparse.BooleanOptionalAction, default=True, help="b65 (docs/argon_review_value.md item 1, "
                    "2026-10-27): with --end-stage, a second end stage from the review's INPUT (the steps before the review, the "
                    "review's bank lines left out) next to the one from the review output; the two outputs are read back to back on the end "
                    "stage's meter and the pre-review one is kept only when scorer/accept.decide banks it over the other (ties: the review "
                    "output's); skipped when the review left the proof unchanged. Default on for new runs; frozen; off for runs started "
                    "before the option")
    # b84 (docs/b84_polish_before_pick.md section 3): the end step's approach pick; OFF by default (config.json without an "end_approach" key)
    ap.add_argument("--end-approach", choices=["on", "off"], default="off", help="b84: with --end-stage --end-config, after the end stage "
                    "has settled the row's incumbent, the best-stored OTHER approach group of the row's candidates (harness/approach_pick.py: "
                    "lemma tokens + top-level splits, complete-link Jaccard 0.5) is polished by the same $0 end stage in a child process under "
                    "a hard wall cap, and replaces the incumbent only when it reads higher back to back on the end-stage meter and on the "
                    "confirm read (Z 100, static check, axiom audit); else the incumbent stays byte-identical. Frozen (config.json end_approach)")
    ap.add_argument("--end-approach-groups", type=int, default=APPROACH_GROUPS, help=f"--end-approach on: other groups polished, best stored "
                    f"first (default {APPROACH_GROUPS})")
    ap.add_argument("--end-approach-seconds", type=float, default=APPROACH_SECONDS, help=f"--end-approach on: the hard wall cap per row "
                    f"(default {APPROACH_SECONDS:g} s), never more than what is left of the end config's sweep + tool phase seconds")
    ap.add_argument("--sweep-before-review", action="store_true", help="b65 (docs/argon_review_value.md item 2; default off until measured): "
                    "with --end-stage, the end stage's sweep phase (no tool phase) on the review's input first (step `presweep`, $0, "
                    "end_guard-checked like the end step), the review on the swept proof, then the full end stage; frozen")
    # 2026-10-26 (e2e iterations that start from a checkpoint; harness/ckpt_start.py)
    ap.add_argument("--start-from", default=None, help="a finished (or running) router run dir of the same set (read-only): every row's work root "
                    "is seeded from that run's state at --start-at (proof, stored score, spend so far; history cut back to the checkpoint), "
                    "the ladder phases up to it are skipped, and the router goes on as if its own ladder had just reached it: the checkpoint's "
                    "$0 step and gate, the next rungs, cross@pre, the review, the end stage. Needs --set/--arm (a NEW arm). Frozen")
    ap.add_argument("--start-at", type=float, default=None, help="--start-from: the checkpoint (one of the source's and of this run's --checkpoints)")
    ap.add_argument("--start-item", choices=["input", "clean"], default="input", help="--start-from: the source row's input@k (what its ladder "
                    "left, before the source's checkpoint cleanup; default: this run's own checkpoint step then runs) or clean@k. Frozen")
    ap.add_argument("--start-history", choices=["restore", "none"], default="restore", help="--start-from: restore the source work root cut "
                    "back to the checkpoint (runs, attempts, winning edits, notes.md, scratch files; checked against the source's next "
                    "opening) or none (best + spend only, as postpass.seed_workspace). Frozen")
    ap.add_argument("--start-hx", default=None, help="--start-from: the source arm's hx worktree (default from its config: ~/source/lra-ab/<prefix>-<arm>-hx)")
    ap.add_argument("--start-heldout", default=None, help="--start-from: the source arm's heldout dir with lineage.json and jobs.log (default: "
                    "<source repository>/probe/heldout/<prefix>-hx-<arm>)")
    ap.add_argument("--stop-at", type=float, default=None, help="b65 steps (probe/b65/steps_tests.md): end the run once its ladder reached "
                    "this budget, one of --checkpoints (before that checkpoint's $0 step and gate) or the ladder top (before the re-plan, "
                    "clean2, cross, review and end stage); finals.json = the ladder's items there. Needs --set/--arm; after --start-at. "
                    "Frozen; off by default")
    ap.add_argument("--plan-only", action="store_true", help="--start-from: list the rows, the checkpoint items, inherited spend, the remaining "
                    "budget, the worst case and each row's restore check (no worktree, no compile, no spend; <run-dir>/start_plan.json), then exit")
    # b68 (docs/b68_tail.md): the tail stage; OFF by default (no --tail-preset: every path as before, config.json without a "tail" key)
    ap.add_argument("--tail-preset", default=None, help="b68: after every row's review and before the end stage, rows whose room under the cap "
                    "(cap - metered spend at the cap price - $0.001) is at least --tail-min-room and the preset's session floor run agent.py "
                    "sessions of this OpenRouter preset (e.g. gpt-6.1-terra-main; a list-priced Azure preset such as terra-azure for a dev "
                    "run) in their own work root from their current best, budgeted "
                    "to that room through agent.py's worst-case pre-call gate (hx_heldout --tail); a better proof (back to back, every pin, "
                    "> MIN_GAIN) enters the row before the end stage. Pins: b66's fallback, else the tail stops at $0. Frozen; off by default")
    ap.add_argument("--tail-min-room", type=float, default=TAIL_MIN_ROOM, help=f"--tail-preset: the least room for a tail (default "
                    f"${TAIL_MIN_ROOM:.2f}; the preset's session floor applies too)")
    ap.add_argument("--tail-effort", default=TAIL_EFFORT, help=f"--tail-preset: the sessions' --reasoning-effort (default {TAIL_EFFORT})")
    ap.add_argument("--tail-max-sessions", type=int, default=TAIL_MAX_SESSIONS, help=f"--tail-preset: sessions per row at most (default "
                    f"{TAIL_MAX_SESSIONS})")
    # b85 (docs/b85_style_rw.md): the accept-only style rewrite at the end of the end stage; OFF by default (config.json without a "style_rw" key)
    ap.add_argument("--style-rw", choices=["on", "off"], default="off", help="b85: after every row's end step, harness/style_rw.py's ACCEPT-ONLY "
                    "paid rewrite into the scoring dialect (r1 / repair / r2 calls, every candidate on every pin, the axiom audit, the run's "
                    "$0 end-stage polish, a single confirm read >= +0.05, else the incumbent stays byte-identical). Frozen (config.json style_rw)")
    ap.add_argument("--style-rw-usd", type=float, default=0.30, help="--style-rw on: the step's budget per row, min(this, the row's room under --cap)")
    ap.add_argument("--style-rw-preset", default="gpt-6.1-sol-main", help="--style-rw on: the rewrite model (an OpenRouter agent.py preset, or a "
                    "list-priced Azure one)")
    ap.add_argument("--style-rw-effort", default="medium", help="--style-rw on: the model's reasoning effort")
    ap.add_argument("--style-rw-exemplars", default=None, help="--style-rw on: the sha16 of harness/style_rw_exemplars.json (refused when the file differs)")
    ap.add_argument("--style-rw-wall-s", type=float, default=SRW_WALL_S, help="--style-rw on: the step's HARD wall cap per row in seconds (calls, "
                    "compiles, the polish and the confirm read), min'd with the row's end-stage clock left; what runs past it is abandoned "
                    f"and the incumbent stays (default {SRW_WALL_S:g})")
    return ap


FROZEN = ("set", "arm", "input", "ref", "checkpoints", "clean_stages", "clean2_stages", "cap", "target_frac", "gate", "climb", "gate_policy", "cross", "flex",
          "review_reserve", "min_replan", "twins", "twin_args", "twin_turns", "replan_model", "replan_turns", "replan_args", "review_model", "review_effort",
          "review_rounds", "review_k", "dry_run", "write_back", "replan", "review_max_tokens", "replan_continue", "review_budget", "cap_price",
          "fast_checkpoint_cleanup", "rules_exclude", "end_stage", "end_k", "end_max_compiles", "end_config_sha256",
          "routes", "route_model", "route_effort", "route_budget", "route_steps", "artifact_model", "artifact_turns", "artifact_args",
          "start_from", "start_at", "start_item", "start_history", "start_sha", "clean_deadline_s", "end_dual_start", "sweep_before_review",
          "stop_at", "review_fallback_model", "pin_fallback_preset")


def main(argv=None, evaluator=None) -> int:
    """The router (module docstring). b65-final (audit C1 + C2): every exit path after the run's outputs exist (Outputs, created before the
    first ladder phase) goes through the finally below: finals.json (when the run did not reach OUT) and submission.jsonl are written there.
    SIGTERM is turned into RouterTerminated (exit TERM_RC after the outputs)."""
    ctx: dict = {}
    rc, exc, term, prev = None, None, False, None
    from scorer import memgate as MG
    # b67 (REAP): this invocation's tag, inherited by every process it starts; a fresh invocation (a test driver calling main again) starts
    # with admission open and steps recorded
    tag, prev_tag = f"{os.getpid()}-{time.time_ns()}", os.environ.get(REAP_ENV)
    os.environ[REAP_ENV] = tag
    os.environ.pop(MG.CLOSED_ENV, None); _TERMINATING.clear()
    try:
        prev = signal.signal(signal.SIGTERM, _on_sigterm)
    except ValueError:   # not the main thread (a test driver): no handler
        prev = None
    try:
        rc = _main(argv, evaluator, ctx)
        return rc
    except RouterTerminated:
        term, rc = True, TERM_RC
        return rc
    except BaseException as e:
        exc = e
        raise
    finally:
        if prev is not None:
            try:
                signal.signal(signal.SIGTERM, prev)
            except ValueError:
                pass
        if term:   # b67: SIGTERM: no compile starts from here (the outputs compile nothing on this path) and no step is recorded
            os.environ[MG.CLOSED_ENV] = "1"; _TERMINATING.set()
        if ctx.get("out") is not None:
            ctx["out"].finish(rc, exc, term)
        _reap_at_exit(ctx, tag, ending=term or exc is not None)
        if prev_tag is None:
            os.environ.pop(REAP_ENV, None)
        else:
            os.environ[REAP_ENV] = prev_tag
        if term:
            print(f"[router] SIGTERM: outputs written; exit {TERM_RC}", flush=True)


def _reap_at_exit(ctx: dict, tag: str, ending: bool) -> None:
    """b67 (REAP): main's exit path, after the outputs. Compile admission closes for this process and steps stop being recorded; every
    process tagged with this invocation gets SIGTERM, then SIGKILL after REAP_GRACE_S; this arm's session containers still running are
    stopped. `ending` (SIGTERM or an exception: the process ends, rows may still be in flight): admission stays closed and steps unrecorded;
    else (a normal return: nothing is in flight) both are restored for an in-process caller. Never raises."""
    from scorer import memgate as MG
    say = ctx.get("say") or (lambda m: print(f"[router] {m}", flush=True))
    try:
        os.environ[MG.CLOSED_ENV] = "1"; _TERMINATING.set()
        r = reap_tagged(REAP_ENV, tag)
        # the container sweep when the exit was not a normal one or something was still running (a normal end has no session in flight:
        # every ladder phase waited for its sessions); a docker call on every normal exit is noise (the drivers' fake docker records it)
        cs = stop_containers(ctx.get("containers")) if (ending or r["term"]) else []
        if r["term"] or cs:
            say(f"exit: {r['term']} process(es) this run started were still running (Lean compiles, ladder processes): SIGTERM"
                + (f", SIGKILL to {r['killed']} after {REAP_GRACE_S:.0f} s" if r["killed"] else "")
                + (f"; {len(cs)} session container(s) stopped" if cs else ""))
    except BaseException as e:  # noqa: BLE001  (the exit is never masked)
        try:
            say(f"exit: reaping failed ({type(e).__name__}: {str(e)[:160]})")
        except Exception:  # noqa: BLE001
            pass
    finally:
        if not ending:
            os.environ.pop(MG.CLOSED_ENV, None); _TERMINATING.clear()


def _main(argv, evaluator, ctx: dict) -> int:
    ap = build_parser(); A = ap.parse_args(argv)
    if A.set and not A.arm:
        ap.error("--set needs --arm")
    if A.set and A.set.endswith("-clean") and not A.allow_lineage_rule:   # lever 2 guard: before the run dir, the config or any spend
        bad = ladder_flag_problems(A)
        if bad:
            ap.error(f"--set {A.set}: the ladder is not the final pipeline's measured ladder: {'; '.join(bad)} "
                     "(--ladder-args needs --no-lineage-rule and --rescue 0; --allow-lineage-rule to run it anyway)")
    if A.set and A.ladder_args and ladder_rungs_override(A) is not None:   # before the run dir, the config or any spend
        ap.error(f"--ladder-args sets --rungs {ladder_rungs_override(A)}: the router sets the ladder's rungs (checkpoints + top = cap x "
                 "target - review reserve); a --rungs there would override them and pass the top")
    if not 0 < A.target_frac <= 1.0:
        ap.error(f"--target-frac {A.target_frac:g}: must be in (0, 1]: above 1.0 the ladder top passes cap - review reserve")
    if A.clean_deadline_s is not None and not (A.clean_deadline_s >= 0 and math.isfinite(A.clean_deadline_s)):   # L5: 0 = none (postpass)
        ap.error(f"--clean-deadline-s {A.clean_deadline_s:g}: must be a finite number >= 0 (0 = no wall limit; a negative one stops at once)")
    for k in ("clean_stages", "clean2_stages"):
        v = [x.strip() for x in getattr(A, k).split(",") if x.strip()]
        err = P.check_stages(v, False) or (f"--{k.replace('_', '-')}: only $0 stages here" if set(v) & {"polish", "replan", "pool"} else None)
        if err:
            ap.error(err)
    spec = A.rules_exclude or ""
    if spec.startswith("@") and not Path(spec[1:]).is_absolute():
        spec = "@" + str(ROOT / spec[1:])
    try:   # B26: validated and normalized before the frozen check, so config.json holds the labels themselves, never a file path
        A.rules_exclude = sorted(P.parse_rules_exclude(spec))
    except (ValueError, OSError) as e:
        ap.error(str(e))
    if A.agent_docker and not A.agent_private_scratch:
        ap.error("--agent-docker needs --agent-private-scratch (the container's own compile scratch)")
    if A.checkpoints is None:
        A.checkpoints = ",".join(f"{c:.2f}" for c in (V3_CHECKPOINTS if A.gate_policy == "v3" else CHECKPOINTS))
    cps = [float(x) for x in A.checkpoints.split(",") if x.strip()]
    top = round(A.cap * A.target_frac - A.review_reserve, 2)
    if not cps or cps != sorted(cps) or cps[-1] >= top:
        ap.error(f"--checkpoints must rise and stay below the ladder top ${top:.2f}")
    if A.stop_at is not None and (not A.set or not any(abs(A.stop_at - x) < 1e-9 for x in cps + [top])
                                  or (A.start_at is not None and A.stop_at <= A.start_at + 1e-9)):   # b65 steps
        ap.error(f"--stop-at {A.stop_at:g}: one of the checkpoints {cps} or the ladder top ${top:.2f}, above --start-at, with --set/--arm")
    A.preset_by_rung = ladder_preset_by_rung(A)   # b65 steps: frozen below (written only when set)
    if A.preset_by_rung and not all(any(abs(float(R) - x) < 1e-9 for x in cps + [top]) for R in A.preset_by_rung):
        ap.error(f"--ladder-args --preset-by-rung {sorted(A.preset_by_rung)}: every rung must be a checkpoint {cps} or the ladder top ${top:.2f}")
    review_note = None
    if A.review_model and not A.dry_run:   # 2026-10-19: refuse a configuration whose every review would be skipped (b64 L0: at the cap price)
        why, review_note, _ = review_call_check(A.review_model, A.review_max_tokens, A.cap, top, A.review_reserve,
                                                resumed_mode(A, "review_budget"), resumed_mode(A, "cap_price"))
        if why:
            ap.error(why)
    fb_err = fallback_args_check(A)   # b66 (A3): the review's and the ladder's stand-ins, before any spend
    if fb_err:
        ap.error(fb_err)
    tail_err = tail_args_check(A)   # b68: before the run dir, the config or any spend
    if tail_err:
        ap.error(tail_err)
    r6_err = review_r6_args_check(A)   # b72 R6: before the run dir, the config or any spend
    if r6_err:
        ap.error(r6_err)
    srw_err = style_rw_args_check(A)   # b85: before the run dir, the config or any spend
    if srw_err:
        ap.error(srw_err)
    if getattr(A, "review_fallback_model", None) and A.review_model and not A.dry_run:
        why, _n, _ = review_call_check(A.review_fallback_model, A.review_max_tokens, A.cap, top, A.review_reserve,
                                       resumed_mode(A, "review_budget"), resumed_mode(A, "cap_price"))
        if why:
            ap.error(f"--review-fallback-model {A.review_fallback_model}: {why}")
    A.run_dir = Path(A.run_dir); A.run_dir = A.run_dir if A.run_dir.is_absolute() else ROOT / A.run_dir
    A.start_sha, start_plan, start_src, CK = None, None, None, None
    if A.start_from or A.start_at is not None or A.plan_only:   # 2026-10-26: a checkpoint start (harness/ckpt_start.py); refused before any spend
        if not A.start_from or A.start_at is None:
            ap.error("--start-from and --start-at go together (--plan-only needs both)")
        if not A.set:
            ap.error("--start-from needs --set/--arm: the new arm's hx work root is what gets seeded")
        CK = importlib.import_module("harness.ckpt_start")
        try:
            start_src = CK.Source(A.start_from, hx=A.start_hx, heldout=A.start_heldout)
        except CK.Refused as e:
            ap.error(str(e))
        A.start_from = str(start_src.run_dir)
        if start_src.set != A.set:
            ap.error(f"--start-from: the source ran set {start_src.set!r}, this run --set {A.set!r}")
        if CK.checkpoint_index(cps, A.start_at) is None:
            ap.error(f"--start-at {A.start_at:g} is not one of this run's checkpoints {cps}")
        if CK.checkpoint_index(start_src.checkpoints, A.start_at) is None:
            ap.error(f"--start-at {A.start_at:g} is not one of the source's checkpoints {start_src.checkpoints}")
        S0 = arm_set(A)
        if (Path(S0.wt) / S0.root).resolve() == start_src.work.resolve():
            ap.error(f"--arm {A.arm}: that is the source's own work root ({start_src.work}); a checkpoint start needs a new arm")
        tags = {n: f"row#{k:02d}" for k, n in enumerate(S0.names)}
        names0 = [n for n in S0.names if not A.problems or n in A.problems]
        start_plan = CK.plan(start_src, names0, A.start_at, A.start_item, A.cap, top, A.start_history, check=A.plan_only)
        if start_plan["refused"]:
            ap.error("--start-from: refused before any spend: " + "; ".join(f"{tags.get(n, 'row#?')}: {why}" for n, why in start_plan["refused"].items()))
        A.start_sha = CK.items_sha(start_plan)
        if A.plan_only:
            anon_plan = dict(start_plan, rows={tags[n]: r for n, r in start_plan["rows"].items()}, refused={}, start_sha=A.start_sha, at=now())
            A.run_dir.mkdir(parents=True, exist_ok=True)
            (A.run_dir / "start_plan.json").write_text(json.dumps(anon_plan, indent=1))
            print(f"[router] checkpoint start plan: {len(start_plan['rows'])} row(s) from {start_src.arm} ({A.start_from}) at ${A.start_at:.2f}, item "
                  f"{A.start_item}, history {A.start_history}; cap ${A.cap:.2f}, ladder top ${top:.2f}", flush=True)
            for n, r in start_plan["rows"].items():
                rr = r.get("restore") or {}
                print(f"  {tags[n]}  {r['step']:8s} score {r['score']}  inherited ${r['inherited']:.4f}  to top ${r['to_top']:.4f}  to cap ${r['to_cap']:.4f}"
                      f"  lineage {r['lineage']['sessions']} session(s), last gain {r['lineage']['last_gain']}"
                      + (f"  restore: digest {'match' if rr.get('digest_match') else ('n/a' if rr.get('digest_match') is None else 'DIFF')}, "
                         f"notes {str(rr.get('notes', '?')).split(' (')[0]}, {rr.get('attempts_kept', 0)}+{rr.get('attempts_placeholders', 0)} attempts, "
                         f"{rr.get('scratch_files', 0)} scratch file(s)" if rr else ""), flush=True)
            print(f"[router] inherited ${start_plan['inherited_usd']:.2f} in all; worst case (cap - inherited, summed) ${start_plan['worst_case_usd']:.2f}; "
                  f"digest check {start_plan['digest_match']}; plan written to {A.run_dir / 'start_plan.json'}", flush=True)
            return 0
    A.run_dir.mkdir(parents=True, exist_ok=True)
    if getattr(A, "compile_slots", None) is not None and A.compile_slots < 1:
        ap.error("--compile-slots must be at least 1")
    for k, v in compile_slots_env(A).items():   # before any Evaluator exists (each reads the scratch at construction, the slots per compile)
        os.environ[k] = v; _ROUTER_ENV.add(k)
    # 2026-10-20 price-trace audit: every review call and failed attempt (tokens, cache, reasoning, metered list $) as one line in the run dir;
    # the rows' review steps keep only each row's review total
    os.environ["LRA_REVIEW_LEDGER"] = str(A.run_dir / "review_calls.jsonl")
    if A.ref is None:
        A.ref = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if A.end_stage:   # B62b: fail before the config is frozen, not on the first finished row
        if A.end_k < 0 or A.end_max_compiles < 1:
            ap.error("--end-k must be >= 0 and --end-max-compiles >= 1")
        try:
            importlib.import_module("harness.endstage")
        except ImportError as e:
            ap.error(f"--end-stage: harness/endstage.py cannot be imported ({e})")
    if A.sweep_before_review and not A.end_stage:   # b65: the pre-review pass is the end stage's sweep phase
        ap.error("--sweep-before-review needs --end-stage")
    A.end_config_sha256 = None
    if A.end_config:   # 2026-10-22: the frozen tool stack (held-out check passed, docs/tools_build_plan.md) in the router's end stage
        if not A.end_stage:
            ap.error("--end-config needs --end-stage")
        try:
            _ev, _erec = importlib.import_module("harness.endstage").load_config(A.end_config)
        except (OSError, ValueError) as e:
            ap.error(f"--end-config: {e}")
        A.end_config = str(Path(A.end_config).resolve())
        A.end_config_sha256 = _erec.get("config_sha256")
    ap_err = approach_args_check(A)   # b84: before the config is frozen
    if ap_err:
        ap.error(ap_err)
    cfgp = A.run_dir / "config.json"
    A.first_session = ladder_first_session(A)   # b64 planner: frozen below (written only when set)
    if cfgp.exists():   # frozen at the first start: a resume runs the same policy (run-freeze rule)
        frozen = json.loads(cfgp.read_text())
        diff = {k: (frozen.get(k), getattr(A, k)) for k in FROZEN if k != "ref" and k in frozen and frozen.get(k) != getattr(A, k)}
        if diff:
            ap.error(f"{cfgp} was started with other settings {diff}; use a new --run-dir")
        if frozen.get("first_session") != A.first_session:   # b64 planner: absent = None (a run started without the first-session flags)
            ap.error(f"{cfgp} was started with first session {frozen.get('first_session')}; --ladder-args now give {A.first_session} "
                     "(--first-preset / --first-effort / --first-budget are frozen); use a new --run-dir")
        if frozen.get("preset_by_rung") != A.preset_by_rung:   # b65 steps: absent = None
            ap.error(f"{cfgp} was started with presets by rung {frozen.get('preset_by_rung')}; --ladder-args now give {A.preset_by_rung} "
                     "(--preset-by-rung is frozen); use a new --run-dir")
        if frozen.get("tail") != tail_config(A):   # b68: absent = None (a run started without the tail keeps it off)
            ap.error(f"{cfgp} was started with tail {frozen.get('tail')}; the flags now give {tail_config(A)} (--tail-preset, --tail-min-room, "
                     "--tail-effort and --tail-max-sessions are frozen); use a new --run-dir")
        if frozen.get("end_approach") != approach_config(A):   # b84: absent = None (a run started without it keeps it off)
            ap.error(f"{cfgp} was started with end_approach {frozen.get('end_approach')}; the flags now give {approach_config(A)} "
                     "(--end-approach, --end-approach-groups and --end-approach-seconds are frozen); use a new --run-dir")
        if frozen.get("review_r6") != review_r6_config(A):   # b72 R6: absent = None (a run started without it keeps it off)
            ap.error(f"{cfgp} was started with review_r6 {frozen.get('review_r6')}; the flags now give {review_r6_config(A)} (--review-repair, "
                     "--review-stack and --review-stack-eps are frozen); use a new --run-dir")
        if frozen.get("style_rw") != style_rw_config(A):   # b85: absent = None (a run started without it keeps it off)
            ap.error(f"{cfgp} was started with style_rw {frozen.get('style_rw')}; the flags now give {style_rw_config(A)} (--style-rw, "
                     "--style-rw-usd, --style-rw-preset, --style-rw-effort, --style-rw-exemplars and --style-rw-wall-s are frozen); use a new --run-dir")
        if frozen.get("ref") and A.ref and A.ref != frozen["ref"] and A.ref != subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                                                             capture_output=True, text=True).stdout.strip():
            print(f"[router] --ref {A.ref[:12]} ignored: this run is frozen at ref {frozen['ref'][:12]}", flush=True)
        A.ref = frozen.get("ref") or A.ref
        if frozen.get("code_hash") and frozen["code_hash"] != code_hash():
            if not A.accept_code_change:
                ap.error(f"{cfgp}: harness/, scorer/ or llm/ changed since this run started (code {frozen['code_hash']} -> {code_hash()}); "
                         f"restore that code (git checkout {frozen.get('code_ref', '?')[:12]} -- harness scorer llm) or pass --accept-code-change")
            print(f"[router] --accept-code-change: resuming on code {code_hash()} (started on {frozen['code_hash']})", flush=True)
        for k, v in LEGACY.items():   # an option added after this run started: keep the behaviour the run started with
            if k not in frozen:
                if k == "end_stage" and A.end_stage:
                    print("[router] --end-stage ignored: this run started before the option (no end stage)", flush=True)
                setattr(A, k, v)
    else:
        cfgp.write_text(json.dumps({k: getattr(A, k) for k in FROZEN} | {"policy": POLICY_V3 if A.gate_policy == "v3" else POLICY_V22, "started": now(), "code_hash": code_hash(),
                                    "code_ref": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()}
                                   | ({"first_session": A.first_session} if A.first_session else {})   # b64 planner
                                   | ({"preset_by_rung": A.preset_by_rung} if A.preset_by_rung else {})   # b65 steps
                                   | ({"tail": tail_config(A)} if tail_on(A) else {})   # b68
                                   | ({"end_approach": approach_config(A)} if approach_on(A) else {})   # b84
                                   | ({"review_r6": review_r6_config(A)} if review_r6_on(A) else {})   # b72 R6
                                   | ({"style_rw": style_rw_config(A)} if style_rw_on(A) else {}),   # b85
                                   indent=1))
    A.clean_stages = [x.strip() for x in A.clean_stages.split(",") if x.strip()]
    A.clean2_stages = [x.strip() for x in A.clean2_stages.split(",") if x.strip()]
    lock = threading.Lock()
    anon: dict = {}
    masked = [lambda m: m]

    def say(m):
        m = masked[0](m)
        line = f"[{time.strftime('%H:%M:%S')}] {m}"
        with lock:
            print(line, flush=True)
            with (A.run_dir / "router.log").open("a") as f:
                f.write(line + "\n")
    S = None
    ctx["say"] = say   # b67 (REAP): main's exit path logs there
    if A.set:
        S = arm_set(A)
        names = [n for n in S.names if not A.problems or n in A.problems]
        A.auto_brief_dir = A.auto_brief_dir or f"{S.root}/_autobrief"
        A.container_prefix = ctx["containers"] = container_prefix(A, S)   # b67 (REAP)
    else:
        if A.rows:
            LT.ROWS.update({json.loads(l)["name"]: json.loads(l) for l in open(ROOT / A.rows) if l.strip()})
            if A.heartbeats:
                LT.HBS.update({json.loads(l)["name"]: json.loads(l)["heartbeat"] for l in open(ROOT / A.heartbeats) if l.strip()})
        finals = json.loads(Path(A.input).read_text())
        names = [n for n in finals if n in LT.ROWS and (not A.problems or n in A.problems)]
        cps = cps[:1]   # no ladder: one gate
    if A.anon:
        masked[0] = masker(names, {n: f"row#{k:02d}" for k, n in enumerate(names)})
    A.replan_args_full = A.replan_args + (f" --auto-brief {A.auto_brief_dir}" if A.auto_brief_dir else "")
    A.twin_args_full = getattr(A, "twin_args", TWIN_ARGS) + (f" --auto-brief {A.auto_brief_dir}" if A.auto_brief_dir else "")
    A.twin_turns = getattr(A, "twin_turns", TWIN_TURNS)
    if evaluator is None:
        from harness.hb_tool_eval import Evaluator
        rows_all, hbs_all = LT.ROWS, LT.HBS
        evaluator = lambda: Evaluator(dict(rows_all), dict(hbs_all), max_compiles=1 << 30)   # noqa: E731  one per row (compile counter)
    if A.allow_lineage_rule and A.set and A.set.endswith("-clean") and ladder_flag_problems(A):
        say(f"--allow-lineage-rule: the ladder is NOT the final pipeline's measured ladder: {'; '.join(ladder_flag_problems(A))}")
    if review_note and A.review_budget == "room":   # b64 L0
        say(review_note)
    say(cap_arithmetic(A.cap, A.target_frac, A.review_reserve, top, resumed_mode(A, "review_budget")))   # b65 (4): the derivation, once per start
    say(f"{POLICY_V3 if A.gate_policy == 'v3' else POLICY_V22}: {len(names)} row(s), cap ${A.cap:.2f}, target {A.target_frac:.0%} (ladder top ${top:.2f}), checkpoints {cps}, "
        f"gate {A.gate:g}, climb {A.climb:g}, reserve ${A.review_reserve:.2f}" + (f", rules exclude {len(A.rules_exclude)} kind(s)" if A.rules_exclude else "")
        + (f", end stage k {A.end_k} / {A.end_max_compiles} compiles" if A.end_stage else "") + (" [DRY RUN]" if A.dry_run else ""))
    k0 = 0
    if A.start_from:   # 2026-10-26: seed the new arm's work root from the source's checkpoint state (once per row; a resume keeps it)
        k0 = CK.checkpoint_index(cps, A.start_at)
        try:
            res = CK.seed_all(start_src, S, names, start_plan, A, say, lambda n: RowStore(A.run_dir, n), lambda n: RowLedger(A.run_dir, n))
        except CK.Refused as e:
            say(f"checkpoint start refused before any spend: {e}"); return 2
        dm = [((RowStore(A.run_dir, n).d.get("start_from") or {}).get("restore") or {}).get("digest_match") for n in names]
        say(f"checkpoint start: {len(names)} row(s) from {start_src.arm} at ${A.start_at:.2f} ({A.start_item}@{CK.checkpoint_index(start_src.checkpoints, A.start_at)}, "
            f"history {A.start_history}): {len(res['seeded'])} seeded, {len(res['kept'])} already seeded, {res['briefs']} brief(s) copied; inherited "
            f"${start_plan['inherited_usd']:.2f}, worst case ${start_plan['worst_case_usd']:.2f}; ladder phases up to checkpoint {k0 + 1} skipped"
            + (f"; restore digest check: {dm.count(True)} match, {dm.count(False)} differ, {dm.count(None)} n/a" if A.start_history == "restore" else ""))
        for n in names:
            rr = (RowStore(A.run_dir, n).d.get("start_from") or {}).get("restore") or {}
            if rr.get("digest_match") is False:
                say(f"{n[:40]}: WARNING the restored work root's opening digest differs from the source's next session ({rr.get('digest_diff_lines')} line(s))")

    # b65-final (audit C1 + C2): the run's outputs exist from here on, on every exit path (main's finally)
    A.pin_stop = load_pin_stop(A)
    if A.pin_stop:
        say(f"PIN STOP recorded by an earlier invocation (after ladder {A.pin_stop.get('phase')}): this run stays on its $0 path, exit {PIN_STOP_RC}")
    A.pin_fallback = load_pin_fallback(A)   # b66 (A3)
    if A.pin_fallback["map"] and not A.pin_stop:
        say("PIN FALLBACK recorded by an earlier invocation: " + ", ".join(f"{x} -> {y}" for x, y in sorted(A.pin_fallback["map"].items()))
            + " (the pinned presets' sessions run their stand-ins; not re-probed in this run)")
    base_of = (lambda n: None) if S is not None else (lambda n: {k: v for k, v in finals[n].items() if k != "state_path"})
    outs = ctx["out"] = Outputs(A, S, names, evaluator, say, base_of)
    outs.start()
    dp = A.run_dir / "decisions.jsonl"
    decisions: dict = {}   # (row, checkpoint index) -> decision, immutable once written
    if dp.exists():
        for l in dp.read_text().splitlines():
            if l.strip():
                d = json.loads(l); decisions.setdefault((d["problem"], d["checkpoint"]), d)
    say(f"$0 stages: {A.jobs} row(s) at once, {os.environ.get('LRA_HBTOOL_SLOTS') or 3} compile slot(s) in "
        f"{os.environ.get('LRA_HBTOOL_SCRATCH') or 'the checkout default scratch (shared by every router of this checkout)'}")
    final_dec = {}
    active = list(names)
    for k, cp in enumerate(cps):
        if k < k0:   # a checkpoint start: the source's ladder ran these rungs (its state at checkpoint k0 is the seed)
            continue
        if not active:
            break
        rc = 0
        if S is not None and not A.dry_run and not (k == 0 and A.skip_l1) and not (A.start_from and k == k0) and not A.pin_stop:
            # b65-final: a CONFIRMED pin: the rows as the ladder left them, no further paid step (the $0 path); b66 (A3): only once no
            # other ladder preset of the run answers (ladder_phase falls back first)
            rc = ladder_phase(A, S, cps[:k + 1], active if (k or A.problems) else None, f"l{k + 1}", say)
        items = work_root_items(S, active) if S is not None else \
            {n: {"proof": finals[n]["proof"], "score": finals[n].get("score"), "spend": float(finals[n].get("spend") or 0),
                 **({"state_path": finals[n]["state_path"]} if finals[n].get("state_path") else {})} for n in active}   # b63 item 16: a snapshot's work dir (artifacts, bank, write-back)
        if short_stop(rc, f"l{k + 1}", cp, active, items, say, A.accept_short, A.run_dir / f"ladder-l{k + 1}.log"):
            return 3
        if A.stop_at is not None and abs(cp - A.stop_at) < 1e-9:   # b65 steps: before this checkpoint's $0 step and gate
            rc_ = stop_out(A, S, names, cp, say); outs.finals_written = True
            return rc_
        cur = dict(zip(active, _pmap(A.jobs, lambda n: guarded(pre_row, n, items[n], say, items[n], k, A, evaluator, say, S), active)))
        for n in active:   # b65-final: the submission file follows each checkpoint cleanup (statically checked; verified by the cleanup)
            outs.checkpoint(n, cur[n])
        last = k == len(cps) - 1
        with dp.open("a") as f:
            for n in active:
                if (n, k) not in decisions:
                    c = cur[n]
                    rs_n = RowStore(A.run_dir, n)
                    led = RowLedger(A.run_dir, n); led.set("sessions", float(c.get("spend") or 0))
                    ladder_cap_extra(led, (items.get(n) or {}).get("state_path"))   # b64 planner
                    # generic mode (--input): a final may carry its ladder's session gains (`gains`: [g1, g2, ...], oldest first; the G8 paired
                    # harness replays a snapshot's lineage this way), else no plateau evidence
                    gains = lineage_gains(S, n, cp) if S is not None else [float(x) for x in (finals[n].get("gains") or []) if x is not None]
                    route = route_of(rs_n, n, c, A, say)   # b63 item 16 (--routes): the artifact route, or None
                    d = decide(c.get("score"), c.get("L"), c.get("H"), max(float(c.get("spend") or 0), led.total()), cap=A.cap, frac=A.target_frac,
                               reserve=A.review_reserve, gate=A.gate, min_replan=A.min_replan, twins=A.twins, ladder=S is not None, climb=A.climb,
                               last_gain=(gains[-1] if gains else None), dead=seed_dead(S, A, n) if S is not None else None, replan=A.replan,
                               policy=POLICY_V3 if getattr(A, "gate_policy", "v3") == "v3" else POLICY_V22, gains=gains, cpu_gain=cpu_gain_at(rs_n, k),
                               final=last, flex=getattr(A, "flex", True), artifact=route if (route and route.get("kind")) else None,
                               c6=c6_of(S, n, c) if S is not None else None, diverse=diverse_of(c.get("state_path"), c, n))
                    d = {"problem": n, "checkpoint": k, "budget_at": cp, "at": now()} | d
                    if route is not None:   # persisted with its reason (contract §2); the text stays in cpu_pass.json
                        d["route"] = {"kind": route.get("kind"), "reason": route.get("reason"), "artifact": (route.get("artifact") or {}).get("sha"),
                                      "artifact_kind": (route.get("artifact") or {}).get("kind"), "holes": len((route.get("artifact") or {}).get("holes") or []),
                                      "near_misses": [x.get("sha") for x in route.get("near_misses") or []], "candidates": route.get("candidates")}
                    if d["tier"] == "twin":   # the checkpoint best B0 both lineages start from (the twin seeds from this item, never a later one)
                        rs_n.put("twin_seed", c, {"checkpoint": k, "budget_at": cp, "sha": _sha12(c.get("proof")), "twin_budget": d.get("twin_budget"), "ladder_top": d.get("ladder_top")})
                    decisions[(n, k)] = d; f.write(json.dumps(d) + "\n")
                    try:
                        write_route(rs_n, n, k, cp, d, c)
                    except Exception as e:  # noqa: BLE001
                        say(f"{n[:40]}: route.json not written: {type(e).__name__}")
                    say(f"{n[:40]}: gate @${cp:.2f} -> {d['tier']} [{d.get('kind')}{', plateau' if d.get('plateau') else ''}] ({d['reason']}; budget ${d['budget']:.2f})")
        for n in list(active):
            d = decisions[(n, k)]
            if d["tier"] != "ladder" or last:
                final_dec[n] = d
            if d["tier"] != "ladder":
                active.remove(n)
    # TOP: rows still on the ladder after the last checkpoint; twin rows' ladder lineage to its own (lower) top, one phase per distinct top
    twin_tops: dict = {}
    for n, d in final_dec.items():
        if d["tier"] == "twin" and S is not None and not RowStore(A.run_dir, n).done("ladder_top"):
            twin_tops.setdefault(round(float(d["ladder_top"]), 2), []).append(n)
    phases = ([(top, [n for n in active if not RowStore(A.run_dir, n).done("ladder_top")], "top")] if S is not None and active else []) \
        + [(t, rows, f"top-twin-{t:.2f}") for t, rows in sorted(twin_tops.items())]
    for ptop, todo, tag in phases:
        rc = 0
        if todo and not A.dry_run and not A.pin_stop:
            rc = ladder_phase(A, S, cps + [ptop], todo, tag, say)   # b65-final / b66 (A3): the fallback, else the $0 path
        after = work_root_items(S, todo) if todo else {}
        if short_stop(rc, tag, ptop, todo, after, say, A.accept_short, A.run_dir / f"ladder-{tag}.log"):
            return 3   # ladder_top not written: a resume runs the top again for these rows, then clean2 and the review
        for n in todo:
            it = dict(after[n]); it.setdefault("verified", True); it["stage"] = "ladder"
            if it.get("seed"):
                it = {"spend": it["spend"]}   # no proof from the ladder: only its spend carries
            RowStore(A.run_dir, n).put("ladder_top", it, {"spend": it.get("spend"), "score": it.get("score"), "dry_run": A.dry_run, "top": ptop,
                                                          "lineage": "ladder" if tag.startswith("top-twin") else None}
                                       | ({"pin_stop": True} if A.pin_stop else {}))
    if A.stop_at is not None:   # b65 steps: at the ladder top (or every row left the ladder before --stop-at), before the paid steps
        rc_ = stop_out(A, S, names, A.stop_at, say); outs.finals_written = True
        return rc_
    if tail_on(A) and S is not None:   # b68: every row through its review, then the tail ($0 when nothing fits), then the rest below
        pre = dict(zip(names, _pmap(A.jobs, lambda n: guarded(post_row, n, inp0(RowStore(A.run_dir, n)), say, A, evaluator, say, S,
                                                               final_dec.get(n), upto_review=True), names)))
        for n in names:   # the submission file follows each row's review output (statically checked)
            outs.checkpoint(n, pre[n])
        tail_stage(A, S, names, cps + [top], evaluator, say)
    # REPLAN / CLEAN2 / REVIEW (b65-final: each finished row's final goes into the submission file, compile-checked)
    final = dict(zip(names, _pmap(A.jobs, lambda n: outs.row_done(n, guarded(post_row, n, inp0(RowStore(A.run_dir, n)), say, A, evaluator, say, S,
                                                                            final_dec.get(n))), names)))

    # OUT
    out = {n: {k: v for k, v in final[n].items() if k not in ("state_path", "seed")} for n in names}
    tmp = A.run_dir / ".finals.json.tmp"; tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1)); tmp.replace(A.run_dir / "finals.json")
    outs.finals_written = True
    mean = lambda xs: round(sum(xs) / max(1, len(xs)), 3)   # noqa: E731
    sc = lambda it: float(it.get("score") or 33.33)   # noqa: E731
    over = [n for n in names if float(out[n].get("spend") or 0) > A.cap + 1e-9]
    # b64 L0: each row's spend at the cap price (Argon calls at the announced price) next to the reported one (cap_spend_of)
    capx = {n: cap_spend_of(A.run_dir, n, out[n]) for n in names}
    first = {n: RowStore(A.run_dir, n) for n in names}
    summ = {"policy": POLICY_V3 if A.gate_policy == "v3" else POLICY_V22, "rows": len(names), "dry_run": A.dry_run, "at": now(), "checkpoints": cps, "ladder_top": top,
            "mean_input": mean([sc(inp0(first[n])) for n in names]),
            "mean_clean0": mean([sc((_first_step(first[n], "clean") or {}).get("item") or inp0(first[n])) for n in names]),
            "mean_final": mean([sc(out[n]) for n in names]),
            "tiers": {t: sum(1 for n in names if (final_dec.get(n) or {}).get("tier") == t) for t in ("none", "ladder", "replan", "twin")},
            "twins": {"rows": sum(1 for n in names if (final_dec.get(n) or {}).get("tier") == "twin"),
                      "select_best": {b: sum(1 for n in names if ((RowStore(A.run_dir, n).d["steps"].get("select") or {}).get("report") or {}).get("best") == b)
                                      for b in ("ladder", "twin#1", "twin#2", "twin#3")},
                      "runner_up_kept": sum(1 for n in names if RowStore(A.run_dir, n).done("select_runner_up"))},
            "kinds": {t: sum(1 for n in names if (final_dec.get(n) or {}).get("kind") == t) for t in KINDS if any((final_dec.get(n) or {}).get("kind") == t for n in names)},
            "plateau_rows": sum(1 for n in names if (final_dec.get(n) or {}).get("plateau")),
            "cross": {"adopted": sum(1 for n in names if ((RowStore(A.run_dir, n).d["steps"].get("cross@pre") or {}).get("report") or {}).get("adopted")),
                      "ran": sum(1 for n in names if RowStore(A.run_dir, n).done("cross@pre"))},
            "spend_mean": mean([float(out[n].get("spend") or 0) for n in names]), "spend_max": max([float(out[n].get("spend") or 0) for n in names] or [0]),
            "over_cap": over, "per_row": {n: {"tier": (final_dec.get(n) or {}).get("tier"), "at": (final_dec.get(n) or {}).get("budget_at"),
                                              "input": inp0(first[n]).get("score"), "final": out[n].get("score"),
                                              "spend": out[n].get("spend"), "cap_spend": capx[n]} for n in names},
            "cap_price": getattr(A, "cap_price", None), "review_budget": getattr(A, "review_budget", None),
            "cap_spend_max": max(capx.values() or [0]), "over_cap_at_cap_price": [n for n in names if capx[n] > A.cap + 1e-9]}
    if A.start_from:   # 2026-10-26: the checkpoint start (the readout pairs these finals with the source's)
        sf = {n: first[n].d.get("start_from") or {} for n in names}
        summ["start"] = {"source": A.start_from, "source_arm": start_src.arm if start_src else None, "start_at": A.start_at, "item": A.start_item,
                         "history": A.start_history, "start_sha": A.start_sha,
                         "inherited_mean": mean([float(sf[n].get("inherited") or 0) for n in names]),
                         "start_score_mean": mean([float(sf[n].get("score") or 33.33) for n in names]),
                         "spend_after_start_mean": mean([float(out[n].get("spend") or 0) - float(sf[n].get("inherited") or 0) for n in names]),
                         "digest_match": sum(1 for n in names if (sf[n].get("restore") or {}).get("digest_match") is True)}
    if tail_on(A):   # b68
        summ["tail"] = tail_summary(A, names)
    if review_r6_on(A):   # b72 R6
        summ["review_r6"] = review_r6_summary(A, names, first)
    if style_rw_on(A):   # b85
        summ["style_rw"] = style_rw_summary(A, names)
    if A.end_stage:   # B62b: rows whose end output became the final, rows that kept the review output, rows without a finished end step
        ends = [(first[n].d["steps"].get("end") or {}).get("report") for n in names]
        summ["end"] = {"adopted": sum(1 for r in ends if r and r.get("adopted")), "kept": sum(1 for r in ends if r and not r.get("adopted")),
                       "missing": sum(1 for r in ends if not r)}
        if approach_on(A):   # b84
            summ["end"]["approach"] = approach_summary(names, first)
    # b65-final (audit C3): every CONFIRMED pin of this run: the ladder's (A.pin_stop: no paid step after it, exit PIN_STOP_RC) and this
    # process's review calls' (agent.PINS: the affected rows' reviews skipped at $0, the run went on)
    from harness.agent import PINS   # noqa: E402
    pins = {h["preset"]: h["message"] for h in PINS.history}
    fbl = (getattr(A, "pin_fallback", None) or {"map": {}, "events": []})   # b66 (A3): the ladder presets moved to a stand-in
    for ev in fbl["events"]:
        pins.setdefault(ev.get("pinned") or "ladder", ev.get("message"))
    if A.pin_stop:
        pins[A.pin_stop.get("preset") or "ladder"] = A.pin_stop.get("message")
    if tail_on(A) and (summ.get("tail") or {}).get("pin_stop"):   # b68: the tail's own stop (the run went on; no run-wide pin stop)
        pins.setdefault(summ["tail"]["pin_stop"].get("preset") or "tail", summ["tail"]["pin_stop"].get("message"))
    _pol = lambda n: ((((first[n].d["steps"].get("review") or {}).get("report") or {}).get("stages") or {}).get("polish") or {})   # noqa: E731
    rskip = [n for n in names if _pol(n).get("pin_unservable")]
    rfb = {n: _pol(n)["review_fallback"] for n in names if _pol(n).get("review_fallback")}   # b66 (A3): reviews that went on on the fallback
    if pins or rskip:
        summ["pin_unservable"] = pins
        summ["pin_review_skipped"] = len(rskip)
    if fbl["map"]:
        summ["pin_fallback"] = fbl
    if rfb:
        summ["review_fallback"] = {"rows": len(rfb), "to": sorted({v.get("to") for v in rfb.values() if v.get("to")})}
    code = PIN_STOP_RC if A.pin_stop else (1 if over else 0)
    summ["exit"] = {"code": code, "outputs_complete": True,
                    "reason": (f"a CONFIRMED max_price pin of {A.pin_stop.get('preset') or 'the ladder preset'} after ladder {A.pin_stop.get('phase')}: "
                               "no paid step after it; the run finished on its $0 path" if A.pin_stop else
                               f"over the cap: {over}" if over else "done")
                    + "".join(f"; ladder preset {ev.get('pinned')} CONFIRMED pinned in ladder {ev.get('phase')}: its sessions ran {ev.get('to')} "
                              "from there" for ev in fbl["events"])
                    + (f"; {len(rfb)} review(s) went on on {', '.join(summ['review_fallback']['to'])} after a confirmed pin of the review preset"
                       if rfb else "")
                    + (f"; {len(rskip)} review(s) skipped at $0 on a confirmed pin of the review preset" if rskip else "")}
    tmp = A.run_dir / ".summary.json.tmp"; tmp.write_text(json.dumps(summ, indent=1)); tmp.replace(A.run_dir / "summary.json")
    for p_, m_ in pins.items():
        say(f"FATAL (max_price pin of {p_}, CONFIRMED): {m_}")
    if rskip:
        say(f"PIN: {len(rskip)} row(s) kept their pre-review best: the review preset's pin was confirmed unservable (review spend $0 there)")
    for ev in fbl["events"]:   # b66 (A3)
        say(f"PIN FALLBACK: ladder preset {ev.get('pinned')} CONFIRMED pinned in ladder {ev.get('phase')}; its sessions ran {ev.get('to')} from there")
    if rfb:
        say(f"PIN FALLBACK: {len(rfb)} review(s) went on on {', '.join(summ['review_fallback']['to'])} after a confirmed pin of the review preset")
    if A.pin_stop:
        say(f"STOPPED PAID WORK on the CONFIRMED max_price pin of {A.pin_stop.get('preset') or 'the ladder preset'} after ladder "
            f"{A.pin_stop.get('phase')}: finals.json and submission.jsonl are complete (the rows' bests on the $0 path); exit {PIN_STOP_RC}")
        return PIN_STOP_RC
    say(f"done: mean {summ['mean_input']} -> clean {summ['mean_clean0']} -> final {summ['mean_final']}; tiers {summ['tiers']}; "
        f"spend mean ${summ['spend_mean']:.2f} max ${summ['spend_max']:.2f}" + (f"; OVER CAP {over}" if over else "")
        + (f"; at the cap price max ${summ['cap_spend_max']:.2f}" if summ["cap_spend_max"] > summ["spend_max"] + 1e-6 else "")
        + (f"; OVER CAP AT THE CAP PRICE {summ['over_cap_at_cap_price']}" if summ["over_cap_at_cap_price"] else ""))
    return 1 if over else 0


def _entry() -> None:
    """The command line. b65-final: on SIGTERM main returns TERM_RC once the outputs are written; the rows still in flight (their steps are
    on disk) are not waited for. b67 review: the same on an exception (a BaseException in the main thread, e.g. KeyboardInterrupt, or one a
    row raised): main's finally has written the outputs and reaped, and compile admission stays closed with no step recorded (REAP), so a
    row thread still in flight would run on for the rest of its row (paid review calls included) with every compile refused and nothing
    recorded, and the interpreter waited for it before exiting. The exception is printed and the process ends at once (exit 1, or the
    SystemExit code); a restart re-runs those steps."""
    try:
        rc = main()
    except BaseException as e:  # noqa: BLE001
        if not _TERMINATING.is_set():
            raise
        code = e.code if isinstance(e, SystemExit) else 1
        if not isinstance(e, SystemExit):
            traceback.print_exc()
        elif code is not None and not isinstance(code, int):
            print(code, file=sys.stderr)
        sys.stdout.flush(); sys.stderr.flush()
        os._exit(code if isinstance(code, int) else (0 if code is None else 1))
    if rc == TERM_RC:
        sys.stdout.flush(); sys.stderr.flush(); os._exit(rc)
    sys.exit(rc)


if __name__ == "__main__":
    _entry()
