#!/usr/bin/env python3
"""B62b end stage ($0, docs/scaffold_panel.md "Rulings on contested points" and "Beyond golf"): after the review, on every row, the best of
the row's own verified proofs, re-measured back to back on ONE meter, then a generic sweep and a crossover over them, banked by the paired
unrounded rule (scorer/accept.decide). Router checkpoints keep their 0.05 bar (accept.SIGNAL_GAIN); this rule runs here only.

Why (Rung 0, 2026-10-20): the router's final is chosen by stored 2-decimal scores from different meters. postpass.py:541
compared a free chain's lake-meter result with max(direct re-measure, stored score), so the effective bar was 0.05 plus the meter offset;
on held-out 5 rows lost 0.06-0.07 each ABOVE the bar. The discard census found in-band discards (final, final + 0.05] on 8-9 rows of the
held-out 42 rules arms. Both are recovered by one meter, back-to-back readings and a small-gain rule with a confirmation compile.

  Meter       one meter per run: the direct lean path (harness/hb_tool_eval.Evaluator: installed binary, built libraries, no Lake). Run-start
              self-test: the seed measured on the direct path and on the lake path (scorer.compile, what the scorer runs) per (source, pin);
              if the direct path fails or the paths disagree on validity, the whole run falls back to the lake path and says so (recorded).
  collect     the row's distinct candidate proofs (sha of the stripped text): the seed, every router step's output, the run pool
              (<work root>/<ws>/pool.jsonl, agent.py _pool_add), extras; origin labels and stored scores (they only order candidates).
  end_stage   pick: the seed, every checkpoint best and the top k by stored score, read on the primary pin back to back; pins confirmed in
              upper-bound order (Z <= 100), so the pick is the exact argmax with all pins and never below the seed or a checkpoint best
              read on this meter. Then sweep (harness.sweep.candidates, imported lazily; skipped with a note when absent) and crossover
              (head/tail splices at shared top-level tactic blocks; per shared `have` name the cheapest block), each candidate read on the
              primary pin, decided against the incumbent RE-MEASURED right after it (paired), a pass confirmed by a fresh full measurement
              (all pins; the worse heartbeat reading counts) before it is banked. Greedy: one more sweep pass on a new incumbent while
              compiles remain. Every decision is returned (op, score delta, tokens/heartbeats saved, banked, reason).
Nothing here is mined from the warm-up (harness/leak_scan.py ENTRY): the exchange rate given to the sweep is the row's own reference
heartbeats / reference tokens, computed at run time.

  families    (docs/tools_build_plan.md, opt-in) FAMILIES maps a family to its generator module (the harness.sweep.candidates contract,
              harness/tools/__init__.py). The default is ("sweep",), exactly the B62b stage; end_stage(..., tools=("t1", "t2", "t3")) or
              --tools t1,t2,t3 adds a TOOL PHASE after it (round R2, 2026-10-22; R1 ran the families in one loop on one budget and the
              tools starved the sweep's second pass):
                sweep phase  the pick, the sweep and the crossover exactly as the control runs them (max_compiles / max_seconds, the
                             control's failure-cache setting, greedy passes to the fixpoint): with tools given, every decision of this
                             phase is the control's on the same input and meter, so the tools can only add banks.
                tool phase   its own budget (tools_max_compiles / tools_max_seconds, default: the sweep phase's values; family_caps per
                             family), the tool families in registry order with the cheap tier (t1, t2) before t3, each generating on the
                             incumbent at its start; after a family pass that banked, one more sweep pass on the new incumbent inside the
                             tool budget (recorded as family "sweep+"); greedy passes while the incumbent changes. Records carry
                             "phase": "tools".
              Batch screening (tool phase, on by default when the meter offers it; harness/batch_screen.py): a family's candidates are
              compiled K (screen_k, 24) at a time in one Lean file on the primary pin through the meter's path; only those whose copy has
              no error go on to attempt() (screen, paired decide, confirmation compile); a screen fail is a record with "at": "batch",
              "compiled": False and reject no_compile / hb_bound / timeout. The sweep path never screens.
              Candidate records carry "family", "fop" ("<family>:<op>"), "compiled" (primary pin; None: never compiled), "reject"
              (statement / no_compile / timeout / meter / Z / noise / below_bar / other / confirmation_failed / stale / cached / budget /
              family_cap) and "at" (screen / paired / confirmation); the result's "families" sums them per family (family_summary).
  budgets     max_compiles per row (as before) and max_seconds (wall; it stops the search, never the pick, bounded by k and max_compiles)
              for the sweep phase; tools_max_compiles / tools_max_seconds for the tool phase (screen compiles count: one per batch);
              family_caps {family: compiles}: a family over its cap is skipped for the rest of the row; passes: greedy re-passes while
              the incumbent changes (2, as before), per phase. A candidate with "timeout_s" (t3 marks non-cheap closers) is compiled
              with that wall timeout (a timeout is a reject, not a meter failure; the incumbent's paired reading keeps the default).
  t3 suggest  (round R3, opt-in: t3_suggest=True / --t3-suggest [rule|try?|hint|both], needs t3 in the tools) before T3 generates on an
              incumbent, its top spans are probed with Lean's suggestion tactic (harness/tools/t3_suggest.py; rule: `hint` with Mathlib,
              else `try?`; "both": `hint` and `try?` on a Mathlib row) in batch files on
              the batch screen's layout and the meter's path (one compile per file, charged to the tool phase and to T3's family cap;
              once per incumbent; several probe tactics ("both") each in files of their own); the suggestions reach T3 as
              ctx["suggestions"] (with ctx["suggestions_for"]) and become op t3:hint, screened and measured like every candidate. T3's
              stats carry probe_batches / probe_compiles / probe_seconds / probe (the probe's counters, per tactic in probe.by_tactic:
              probes, judged, timeout, crash, skipped, hb_out, ...). A `try?` probe is bounded only by its file's wall timeout from Lean
              v4.26.0 on (harness/tools/t3_suggest.py, "batch"). Off by default: without it nothing here changes.
  t4 probe    (opt-in family t4, harness/tools/t4_nameless.py; NOT adopted: not in DEFAULT_FAMILIES nor in probe/b62/r3_frozen.json
              until the held-out check) before T4 generates on an incumbent, its sites are probed with `trace_state` in batch files on
              the batch screen's layout and the meter's path (t3_suggest.batch_compiler; at most t4_nameless.PROBE_MAX_FILES files per
              round, two rounds; charged to the tool phase and to T4's family cap; once per incumbent); the names Lean printed reach T4
              as ctx["t4_probe"] (with ctx["t4_probe_for"]). T4's stats carry probe_batches / probe_compiles / probe_seconds / probe.
  t5 search   (opt-in family t5, harness/tools/t5_joint.py, b63 build step D; NOT adopted: not in DEFAULT_FAMILIES nor in
              probe/b62/r4_frozen.json; probe/b63/r5_candidate.json = r4 + t5 is the candidate) before T5 generates on an incumbent,
              t5_joint.search() reads joint (multi-site) edits on the one-process Lean workbench (harness/workbench.py) on the meter's
              primary pin: started at T5's first search on the row (the `workbench` argument: an object, a factory (row, meter), or
              None: a Workbench on meter.versions[0] in the meter's scratch), closed when the tool phase ends (an injected object is
              not closed); once per incumbent; bounded by t5_joint.SEARCH_SECONDS of workbench wall time per row over all passes
              (charged to T5's stats probe_seconds and to the tool phase's wall budget, not to its compile count), MAX_CHECKS readings
              per search and the tool phase's deadline. Its survivors reach T5 as ctx["t5_found"] (with ctx["t5_found_for"]) and skip
              the batch screen (the workbench read them on the primary pin already); the meter measures each one, banked only through
              accept.decide + the all-pin confirmation, within T5's family cap. No workbench (it could not start) or a search fault:
              a note, and T5 proposes its site variants unscreened (they go through the batch screen). phases.tools.workbench records
              the workbench's info() (load seconds, restarts, peak RSS, counts) or its start error.
  caches     the visited set (proof hashes already read) as before; a failure cache keyed by (op, the edited lines with one line of
              context, whitespace-normalised, edit_key): an edit that failed on a region that has not changed is not compiled again in a
              later pass; on in the tool phase (fail_cache=None), off in the sweep phase unless fail_cache=True (the control's setting).
              Screen verdicts by candidate hash. `cache` ({"failed", "visited", "screen"}) carries them across calls on one row.
  ops (R3)    family_ops {family: [ops]}: a per-family op allow-list (--ops, the config's "ops"). The family's generator gets it as
              ctx["ops"] (T1 reads it as its op set, opt-in ops included only when listed; T3 keeps its op order and drops the ops not
              listed) and the end stage keeps only the generated candidates whose "<family>:<op>" is listed (a generator that ignores
              ctx["ops"] is filtered all the same; the dropped count is the note's suffix and the family's "ops_dropped"). A family's
              known ops are its module's ALL_OPS when it has one (T3: t3:hint included), else its OPS (known_ops()); the sweep takes no
              allow-list (the sweep phase is the control's). family_ctx {family: {key: value}}: keys merged into that family's ctx only
              (after ctx, before ctx_fn's keys): --opt-in t1:field gives t1 {"opt_in": ["t1:field"]} (T1's opt-in ops:
              harness/tools/t1_compress.OPT_IN_OPS); a config file may set only the keys of CONFIG_CTX_KEYS (op names, no Lean token:
              T3's op order "t3_ops"). Neither given (the default): the R2 calls. Before the call and the record, normalize_method()
              drops what equals the code's default (an allow-list equal to the family's default op set, --screen-depth SCREEN_DEPTH,
              empty opt-in lists), so a flag given at its default value resumes a run started without it; a tool run records each
              tool family's effective op set in end_config.json ("op_sets", effective_ops()).

CLI, the Rung 1 replay on a finished router run ($0; compiles go through the memory gate: run it in a memory-capped unit):
    python3 harness/endstage.py --run-dir probe/router/<tag> [--rows R.jsonl --heartbeats H.jsonl] [--problems ...] [--k 6]
        [--max-compiles 60] [--no-sweep] [--no-crossover] [--prefer direct|lake] [--jobs 1] [--anon] [--out DIR, default <run-dir>/end]
        [--tools t1,t2,t3] [--max-seconds S] [--family-cap t3=200 ...] [--passes 2] [--max-per-op N] [--fail-cache | --no-fail-cache]
        [--tools-max-compiles N] [--tools-max-seconds S] [--no-screen] [--screen-k 24] [--scratch DIR] [--resume-anyway]
        [--t3-suggest [rule|try?|hint|both]] [--ops FAMILY=OP[,OP..] ...] [--opt-in FAMILY:OP ...] [--screen-depth 2] [--config FILE]
        [--backstop-s S] [--tools-backstop-s S] [--search-budget FAMILY=CHECKS[:S] ...] [--screen-sweep]   (L5, "count budgets")
writes <out>/finals.json (router finals format), <out>/report.jsonl (one line per row with its decisions and per-family summary; rows
already there are skipped: resumable), <out>/meter.json (the self-test record; a resume keeps the run's meter) and <out>/end_config.json
(families, budgets, the sweep's table status and the code identity), and prints a summary. Rows default to the run's set (config.json)
or the pipeline's registered rows.
  resume    (R2 review 2026-10-22) rows already in report.jsonl are kept only when the new call's end_config equals the old one: the same
            families, every other key, and the same code identity (code_identity(): sha256 of the end stage's, the sweep's, the tools',
            the screen's, the meter's and the scorer's files and of every table; git HEAD and a dirty flag are recorded, not compared,
            so committing unchanged code does not block a resume). Otherwise the call is refused; --resume-anyway runs it and records
            the difference in end_config.json ("resumed_anyway"). Each report row carries the identity's digest ("code").
  tables    a sweep table that is missing or unreadable (harness/sweep.TABLES_STATUS) refuses the start: addwr / hr:specialize would
            otherwise drop out of the control silently.
  config    (R3, the frozen config of the held-out check) --config FILE: a JSON file that sets the method (load_config(): "families"
            (tool families), "sweep", "crossover", "k", "prefer", "budgets" {"sweep": {"compiles", "seconds", "backstop_s"}, "tools":
            {"compiles", "seconds", "backstop_s"}, "passes", "max_per_op", "search" {family: {"checks", "backstop_s"}}}, "caps" {family:
            compiles}, "fail_cache", "screen" {"on", "k", "depth", "sweep"}, "ops" {family: [ops]}, "opt_in" [ops], "t3_suggest" (false
            or null: off; true or "rule", "try?", "hint", "both": the --t3-suggest mode),
            "ctx" {family: {key: [op names]}} (only the keys of CONFIG_CTX_KEYS: no Lean token can enter a family's ctx from a file);
            "name", "description" and keys starting with "_" are documentation; any other key refuses the file). A key the file leaves
            out keeps the code's default (the code identity pins it). With --config, a method flag on the command line is refused
            (--t3-suggest included; only the run's own flags are allowed: --run-dir, --rows, --heartbeats, --problems, --jobs, --anon,
            --out, --scratch, --resume-anyway). end_config.json records "config_sha256" (sha256
            of the file's bytes), "config_name", "config_file" and the parsed "config_body"; the resume guard compares the sha (the path
            and the body are information), so a run resumes only under the same file content, and a run started without --config does
            not resume under one (or the other way round). An op of "ops" / "opt_in" / "ctx" that the family module does not list
            (known_ops(); OPT_IN_OPS for an opt-in), an allow-list for the sweep, or a family-specific key for a family that is not run
            refuses the start (check_ops()).
  speed     (b63, 2026-10-25; the coordinator's overhead analysis: ~85 % of a family measurement's wall was overhead) the replay takes a
            finals.json entry's own reading as read when it is complete and on this run's meter path (final_reading(): sha, meter, every
            pin in compat, Z == compat, score_exact == the metrics recomputed now, statement / forbidden check), 0 compiles; an entry an
            end stage wrote ("stage": "end:*", picked over the seed on that meter) carries the seed's floor too, so the seed is not read
            (report "input_reused" / "seed_read"; decisions note it). Every later decision is still paired: the incumbent is re-read
            right after each candidate, and banks are confirmed on every pin (nothing stored is ever compared with a fresh reading).
            --no-reuse-readings restores the former 2-4 compiles per row. --jobs auto (the default): auto_jobs() from the box's cores
            and load; the sharing rule between units is their CPUWeight (work-conserving; 2026-10-22), not a fixed row
            count. The run-start meter self-test compiles what it compiled before, at once (run_self_tests(): the serial loop's cache
            rule decides which rows compile, their (row, pin) pairs run on --jobs threads with each pin's direct and lake compile back to
            back, and the records are assembled in row order, so the run's tests, the first failing row's fallback and the seed readings
            are the serial loop's; serial, it took 134 of 375 s and 117 of 229 s of the two t6 abpool arms; --serial-self-test restores the loop). A search
            family whose module has search_precheck(proof, statement) (a reason its search() stops before any workbench reading, no
            Lean; t6: no site) is searched without starting the row's workbench (t5_probe: a sentinel that raises on any use; a search
            that uses it anyway gets its counters back and runs again on a started workbench; phases.tools.workbench {"started": false,
            "not_needed", "lazy_misses"}); 15 of 42 abpool rows loaded a workbench t6 never read (64 row-seconds). The workbench stays
            one process per row: measured 2026-10-25 on the six slowest abpool rows, the library imports cost 0.1-1.5 s of a 1.3-9.7 s
            load; the rest is the row's own file prefix (which differs per row), so a per-(library, pin) warm pool would save ~1 s/row
            and was not built.
  slots     compiles wait for one of 3 compile slots per scratch directory (harness/hb_tool_eval.Evaluator; $LRA_HBTOOL_SLOTS sets the count,
            2026-10-26: a --jobs above 3 runs more rows than there are slots unless it is raised). Two arms on one scratch
            share 3 slots and each arm's wall budget then depends on the other's load (the R1 A/B did). The default scratch is
            per --out: <LRA_HBTOOL_SCRATCH or probe/hbtool/.scratch>/end-<hash of --out> (--scratch DIR uses DIR as given): size each
            arm's unit for its own 3 compiles (48G for --jobs 3). The seconds a row waited for a slot are recorded per phase
            ("slot_wait_s"); meter.json records the scratch.
  count budgets (L5, docs/plateau_levers.md L5, 2026-10-26; opt-in, every default keeps the calls above) the wall budgets above make a
            row's result depend on the host's speed: on the 7 finished router runs the 1800 s budgets stopped 24 of 105 sweep phases and
            10 tool phases while no compile budget was ever reached (probe/b63/l5_census.json). With count budgets the phases end on their
            compile budgets (max_compiles / tools_max_compiles) and a search family on its per-row workbench readings (search_budgets:
            each search gets max_checks = min(MAX_CHECKS, the row's readings left)); a generous wall BACKSTOP (backstop_s /
            tools_backstop_s per phase, a search budget's backstop_s per row; config budgets.<phase>.backstop_s and budgets.search) only
            guards a stuck or very slow host, and a stop on it is recorded as "wall backstop ... reached". screen_sweep (config
            screen.sweep, --screen-sweep) batch-screens the sweep's candidates as the tool phase screens a family's (70% of 5,871 sweep
            tries on those runs did not compile): only the copies that compile reach attempt(), in the same order, so on a host where no
            budget binds the decisions and the final proof are the unscreened run's. Per-compile timeouts stay as they are (not
            budgets): the meter's 900 s, a batch file's (from the incumbent's own compile time) and a workbench reading's (from the
            incumbent's reading).
  final families (b71 R2, 2026-10-28; docs/b71_final.md) a family with "final" in FAMILIES (FINAL_FAMILIES; tier 2: c2) is left out of
            the tool phase's greedy passes and runs ONCE after them, inside the tool phase's budget and deadline, on the incumbent the
            passes left (no sweep+ after it): every decision of the other families is the one they make without it, so it can only add
            banks on top. A search family whose module has query(proof, statement, run, ...) (c2) first runs that env query (env_query():
            plain compiles of a fixed Lean text after the row's file prefix through Meter.command on the meter's path, each charged as a
            compile to the tool phase and to the family's cap; once per incumbent); its keys reach the search's ctx and its precheck
            (a precheck that takes ctx), and without a query result the family proposes nothing. c2 (harness/tools/c2_lemvar.py):
            class-namespace lemma variants screened on the workbench, the disjoint winners stacked in one reading (greedy fallback),
            every survivor banked only through attempt() (paired decide, all-pin confirmation), a stack on its own compiles.
"""
from __future__ import annotations

import argparse, copy, hashlib, importlib, json, math, re, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scorer.accept import HB_EPS, decide, exact_score  # noqa: E402
from scorer.forbidden import check_forbidden  # noqa: E402
from scorer.score import compat_pct, hb_pct_local, len_pct  # noqa: E402
from scorer.tokenize import count_tokens, split_declaration  # noqa: E402
from probe.verify_candidates import newest_first  # noqa: E402

K = 6                  # candidates re-measured besides the seed and the checkpoint bests
MAX_COMPILES = 60      # per row, self-test excluded (a run-start cost)
CROSS_TOP = 6          # crossover parents: the incumbent and the best other measured candidates (b63 item 3: 4 -> 6, the whole per-row bank)
CROSS_MAX = 24         # crossover children tried per row (fewest tokens first; the compile budget bounds the rest)
SCREEN_HB = 2 * HB_EPS   # cost guard, not an acceptance rule: a candidate that cannot pass decide() even against the incumbent's last
SCREEN_FRAC = 0.0005     # reading made this much worse is rejected without the paired incumbent compile (Rung 1 spread <= 2 on >= 95% rows)

PASSES = 2             # greedy: one more pass on a new incumbent (B62b); more only on request (iteration rounds)
FAMILIES = {           # end-stage families: generator module (harness.sweep.candidates contract) and tier (cheap 0 first, expensive 1 after)
    "sweep": {"module": "harness.sweep", "tier": 0},
    "t1": {"module": "harness.tools.t1_compress", "tier": 0},
    "t2": {"module": "harness.tools.t2_schedule", "tier": 0},
    "t3": {"module": "harness.tools.t3_reclose", "tier": 1},
    "t4": {"module": "harness.tools.t4_nameless", "tier": 1},   # opt-in, not adopted: held-out check first (module docstring, "t4 probe")
    "t5": {"module": "harness.tools.t5_joint", "tier": 1},      # opt-in (b63 D): joint edits screened on the workbench ("t5 search")
    "t6": {"module": "harness.tools.t6_transpile", "tier": 1, "search": True},    # b63 item 13 (r6): nameless transpiler, screened likewise
    "t7": {"module": "harness.tools.t7_defer", "tier": 1, "search": True},      # b63 item 15 (r7, bar A): defer / let-collapse / swaps joint set
    "t8": {"module": "harness.tools.t8_pin", "tier": 1, "search": True},        # b63 T10 (r7, bar A): instance pin, screened on the workbench
    "t11": {"module": "harness.tools.t11_template", "tier": 1, "search": True},  # b63 T10 (r7, bar A): relation template, screened likewise
    "golf": {"module": "harness.tools.golf_ops", "tier": 0},    # b65 item 3: Sol's mechanical golf blind spots; every op opt-in by name (bar A each)
    "c2": {"module": "harness.tools.c2_lemvar", "tier": 2, "search": True, "final": True},   # b71 R2: class-namespace lemma variants +
    # a compile-gated stack; a FINAL family (module docstring, "final families"): one pass after every other tool family's passes
    # t9 (fold), t10 (rebuild) live on their b63-<name> branches: NOT YET (0/42 fired; docs/b63_build_log.md, 2026-10-25 reviews)
}
SEARCH_FAMILIES = ("t5",) + tuple(f for f, v in FAMILIES.items() if v.get("search"))   # families with the t5 search contract
FINAL_FAMILIES = tuple(f for f, v in FAMILIES.items() if v.get("final"))   # b71: run once after the tool phase's passes (module docstring)
DEFAULT_FAMILIES = ("sweep",)
CACHEABLE = frozenset({"statement", "no_compile", "timeout", "Z", "noise", "below_bar", "other", "confirmation_failed",
                       "hb_bound"})   # candidate faults
SCREEN_K = 24          # tool-phase batch screen: candidates per Lean file (harness/batch_screen.py)
SCREEN_DEPTH = 2       # halvings of a batch that timed out, crashed or left copies unknown
SCREEN_REJECT = {"fail": "no_compile", "hb_bound": "hb_bound", "timeout": "timeout"}   # screen verdict -> reject category
SEARCH_BACKSTOP_FACTOR = 4.0   # L5 count budgets: a search family's per-row wall backstop when its budget names none (x its SEARCH_SECONDS)

_RUN = {"fallback": None, "tests": {}}   # the run's meter: one decision per process (restored from <out>/meter.json on a resume)
_LOCK = threading.Lock()


def sha(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()[:16]


def run_state() -> dict:
    with _LOCK:
        return {"path": "lake" if _RUN["fallback"] else "direct", "fallback": _RUN["fallback"], "tests": dict(_RUN["tests"])}


def restore_run_state(d: dict | None) -> None:
    with _LOCK:
        _RUN["fallback"] = (d or {}).get("fallback")
        _RUN["tests"] = dict((d or {}).get("tests") or {})


def reset_run_state() -> None:
    restore_run_state(None)


def _ok_reading(r: dict | None) -> bool:
    return bool(r) and bool(r.get("ok")) and r.get("heartbeats") is not None and r.get("tokens") is not None


class _NeedWorkbench(BaseException):
    """A search used the workbench that the lazy path did not start (end_stage's t5_probe; module docstring, "speed"). A BaseException,
    so a search's own `except Exception` cannot swallow it and go on without the workbench."""


class _UnstartedWorkbench:
    """Handed to a search whose module's search_precheck() said it stops before any workbench reading: any attribute use raises
    _NeedWorkbench (not AttributeError, so getattr(wb, x, default) raises too), and the end stage then starts the real workbench."""
    __slots__ = ()

    def __getattr__(self, name):
        raise _NeedWorkbench(name)

    def __repr__(self):
        return "<workbench not started>"


_UNSTARTED_WB = _UnstartedWorkbench()


def _search_precheck(mod, proof: str, statement: str, ctx: dict | None = None) -> str | None:
    """The module's search_precheck(proof, statement) -> a reason the search stops before any workbench reading (no Lean), else None; a
    module without one, or a precheck that raises or answers anything but a non-empty string: None (the workbench is started as before).
    b71: a precheck that takes `ctx` gets the search's ctx (c2: the env query's result)."""
    pre = getattr(mod, "search_precheck", None)
    if not callable(pre):
        return None
    try:
        why = pre(proof, statement, **_kwargs_for(pre, {"ctx": ctx})) if ctx is not None else pre(proof, statement)
    except Exception:  # noqa: BLE001
        return None
    return why if isinstance(why, str) and why else None


# ------------------------------------------------------------------------------------------------------------------------------ meter
class Meter:
    """One row's measurements on the run's meter. `path` is "direct" (Evaluator) unless the run fell back (or prefer="lake"); it is frozen
    at the row's first measurement, so one row never mixes meters. Readings carry unrounded L, H and score_exact."""

    def __init__(self, row: dict, heartbeats: dict, versions: list[str] | None = None, prefer: str = "direct", log=print, timeout: int = 900):
        self.row, self.name, self.statement = row, row["name"], row["statement"]
        self.heartbeats, self.ref_hb = heartbeats, heartbeats.get(row["name"])
        self.versions = list(versions or newest_first(row["version_info"]))
        self.prefer, self.log, self.timeout = prefer, log, timeout
        self.compiles = 0
        self.test = None
        self._cand_timeout = None   # a candidate's own wall timeout (seconds) while measure()/pins() run it; None: self.timeout
        self.scratch = None         # the Evaluator's compile-slot directory (None: its default; the CLI sets one per run, module docstring)
        self._path = None
        self._ev = None
        self._readings: dict = {}   # sha -> full reading of the seed from the self-test (reused when nothing else is compared)

    @property
    def path(self) -> str:
        if self._path:
            return self._path
        return "lake" if self.prefer == "lake" or _RUN["fallback"] else "direct"

    def freeze(self) -> str:
        self._path = self.path
        return self._path

    def _evaluator(self):
        if self._ev is None:
            from harness.hb_tool_eval import Evaluator
            self._ev = Evaluator({self.name: self.row}, self.heartbeats, max_compiles=1 << 30, timeout=self.timeout, scratch_root=self.scratch)
        return self._ev

    @property
    def slot_wait_s(self) -> float:
        """Seconds this row's compiles waited for a compile slot (direct path; 0 before the first compile)."""
        return float(getattr(self._ev, "slot_wait_s", 0.0) or 0.0) if self._ev is not None else 0.0

    def cost(self, full: bool = True) -> int:
        """Compiles reserved for one measurement (the Evaluator's conservative estimate, the same on both paths)."""
        try:
            return int(self._evaluator().cost(self.name, self.versions, full))
        except Exception:  # noqa: BLE001  (a missing environment: the measurement itself will say so)
            return 1 + (len(self.versions) - 1 if full else 0)

    def metrics(self, tokens: int, heartbeats: int, Z: float) -> dict:
        L = len_pct(self.row["proof_length"], tokens)
        H = hb_pct_local(self.name, heartbeats, self.ref_hb)
        return {"L": L, "H": H, "score_exact": exact_score(L, H, Z)}

    def _one(self, decl: str, version: str, count: bool, path: str):
        """One compile on one pin: (CompileResult, physical compiles charged)."""
        from scorer import compile as C
        ev, n0 = None, 0
        to = self.timeout if not self._cand_timeout else max(1, min(int(self.timeout), int(math.ceil(float(self._cand_timeout)))))
        try:
            if path == "direct":
                ev = self._evaluator(); n0 = ev.compiles
                t_ev, ev.timeout = ev.timeout, to   # one row's Evaluator, readings back to back: restored right after this compile
                try:
                    r = ev._compile(self.row, decl, version, count=count)
                finally:
                    ev.timeout = t_ev
                n = ev.compiles - n0
            elif self.row["source"] == "putnambench":
                r, n = C.compile_putnam(self.row["header"], decl, version, count=count, timeout=to), 1
            else:
                r = C.compile_project(self.row, decl, version, count=count, timeout=to)
                n = self._evaluator().cost(self.name, [version], False) if count else 1
        except Exception as e:  # noqa: BLE001  (a meter that cannot run fails closed; on the direct path the self-test then falls back)
            r = C.CompileResult(False, None, 0.0, [f"environment: {type(e).__name__}: {e}"[:300]])
            n = (ev.compiles - n0) if ev is not None else 0
        self.compiles += n
        return r, n

    def command(self, text: str, version: str | None = None, timeout: float | None = None):
        """b71 (c2's env query): `text` compiled PLAINLY after the row's file prefix on `version` (default: the primary pin) through this
        meter's path, as a validity compile places a declaration (no measurement, no statement check): (CompileResult with the Lean
        messages, physical compiles charged)."""
        path = self.freeze()
        self._cand_timeout = timeout
        try:
            return self._one(text, version or self.versions[0], False, path)
        finally:
            self._cand_timeout = None

    def _check(self, decl: str) -> str | None:
        body = split_declaration(decl, self.statement)
        if body is None:
            return "statement differs"
        bad = check_forbidden(body)
        return f"forbidden: {bad}" if bad else None

    def _reading(self, decl, prim, compat: dict | None, Z, path, n) -> dict:
        tokens = count_tokens(split_declaration(decl, self.statement))
        out = {"ok": bool(prim.ok) and prim.heartbeats is not None, "tokens": tokens, "heartbeats": prim.heartbeats, "meter": path, "compiles": n,
               "error": (prim.errors[0][:300] if prim.errors else None)}
        if isinstance(getattr(prim, "seconds", None), (int, float)):
            out["seconds"] = round(float(prim.seconds), 2)   # the primary pin's wall time (the tools' ctx["compile_s"])
        if getattr(prim, "timed_out", False):
            out["timed_out"] = True
        if prim.ok and prim.heartbeats is None:
            out["error"] = "compiled without a heartbeat reading"
        if out["ok"]:
            full = compat is not None
            compat = compat if full else {self.versions[0]: True}
            Zv = compat_pct(compat) if full else (100.0 if Z is None else float(Z))
            out.update(self.metrics(tokens, prim.heartbeats, Zv), Z=Zv, compat=compat, Z_assumed=not full)
            out["score"] = round(out["score_exact"], 2)
        return out

    def measure(self, decl: str, full: bool = True, Z: float | None = None, timeout: float | None = None) -> dict:
        """{"ok", "tokens", "heartbeats", "Z", "L", "H", "score_exact", "compat", "meter", "seconds", ...}. full=False: the primary pin only,
        Z assumed from the caller (Z, default 100, flagged Z_assumed). timeout: this candidate's wall timeout per compile (capped by the
        meter's own; a timeout reads as a failed compile, "timed_out")."""
        decl = decl.strip()
        path = self.freeze()
        bad = self._check(decl)
        if bad:
            return {"ok": False, "error": bad, "compiles": 0, "meter": path}
        n0 = self.compiles
        self._cand_timeout = timeout
        try:
            prim, _ = self._one(decl, self.versions[0], True, path)
            compat = None
            if full and prim.ok and prim.heartbeats is not None:
                compat = {self.versions[0]: True}
                for v in self.versions[1:]:
                    compat[v] = bool(self._one(decl, v, False, path)[0].ok)
        finally:
            self._cand_timeout = None
        return self._reading(decl, prim, compat, Z, path, self.compiles - n0)

    def pins(self, decl: str, timeout: float | None = None) -> dict:
        """The non-primary pins only (validity, unmeasured): {"compat": {pin: ok}, "compiles"}; the primary counts as passed."""
        decl = decl.strip()
        path = self.freeze()
        n0 = self.compiles
        compat = {self.versions[0]: True}
        self._cand_timeout = timeout
        try:
            for v in self.versions[1:]:
                compat[v] = bool(self._one(decl, v, False, path)[0].ok)
        finally:
            self._cand_timeout = None
        return {"compat": compat, "compiles": self.compiles - n0}

    def screener(self, k: int = SCREEN_K, max_depth: int = SCREEN_DEPTH, cache: dict | None = None, log=None):
        """The tool phase's batch screen on this meter's path and primary pin (harness/batch_screen.py)."""
        from harness.batch_screen import BatchScreener, meter_compile_fn
        return BatchScreener(self.row, meter_compile_fn(self), version=self.versions[0], timeout=self.timeout, k=k, max_depth=max_depth,
                             cache=cache, log=log)

    def reading(self, decl: str) -> dict | None:
        """A full reading of `decl` taken by the self-test on this meter's path, if any."""
        r = self._readings.get(sha(decl))
        return dict(r) if r and r.get("meter") == self.path else None

    def _test_pin(self, seed: str, version: str, count: bool, private: bool = False) -> tuple:
        """One pin of the self-test: the seed on the direct path, then on the lake path, back to back -> (direct, lake, compiles).
        private=True (a non-primary pin, run_self_tests): on a private Meter of the same row (its own Evaluator and counter), so the pins
        of one row can run at once; a non-primary pin is compiled unmeasured (count=False), which teaches the Evaluator nothing the row's
        later compiles use (its measure-import memo is learned on the measured pin only)."""
        m = self
        if private:
            m = Meter(self.row, self.heartbeats, versions=self.versions, prefer=self.prefer, log=self.log, timeout=self.timeout)
            m.scratch = self.scratch
        n0 = m.compiles
        rd, _ = m._one(seed, version, count, "direct")
        rl, _ = m._one(seed, version, count, "lake")
        return rd, rl, m.compiles - n0

    def self_test(self, seed: str, pin_results: dict | None = None) -> dict:
        """The seed on the direct path and on the lake path, pin by pin back to back (primary measured, the others for validity, as a full
        measurement does). A direct-path failure, a validity disagreement or a missing direct heartbeat reading sets the run's fallback to
        the lake path. (source, pin) pairs already tested in this run are not compiled again. pin_results {pin: (direct, lake, compiles)}
        (run_self_tests, b63 speed): those pins were compiled already (_test_pin, at once with other rows' pins); the record is assembled
        from them exactly as from the loop's own compiles (their compiles are added to this meter's)."""
        seed = seed.strip()
        if self.prefer == "lake":
            self.test = {"cached": False, "path": "lake", "fallback": None, "pins": {}, "compiles": 0, "skipped": "prefer lake"}
            return self.test
        src = self.row["source"]
        keys = {v: f"{src}@{v}" for v in self.versions}
        with _LOCK:
            known = {k: _RUN["tests"][k] for k in keys.values() if k in _RUN["tests"]}
        if len(known) == len(keys):
            self.test = {"cached": True, "path": self.path, "fallback": _RUN["fallback"], "pins": known, "compiles": 0}
            return self.test
        n0 = self.compiles
        pre_compiles = 0
        bad = self._check(seed)
        pins, reasons, res = {}, [], {}
        for i, v in enumerate(self.versions):
            count = i == 0
            if bad:
                pins[keys[v]] = {"direct_ok": False, "lake_ok": False, "error": bad}
                continue
            if pin_results is not None and v in pin_results:
                rd, rl, n_pre = pin_results[v]
                pre_compiles += int(n_pre or 0)
            else:
                rd, rl, _ = self._test_pin(seed, v, count)
            res[v] = (rd, rl)
            e = {"direct_ok": bool(rd.ok), "lake_ok": bool(rl.ok), "measured": count}
            if count:
                e.update(direct_hb=rd.heartbeats, lake_hb=rl.heartbeats,
                         hb_delta=(rd.heartbeats - rl.heartbeats) if rd.heartbeats is not None and rl.heartbeats is not None else None)
            if not rd.ok and rd.errors:
                e["direct_error"] = rd.errors[0][:200]
            if not rl.ok and rl.errors:
                e["lake_error"] = rl.errors[0][:200]
            if str((rd.errors or [""])[0]).startswith("environment:"):
                reasons.append(f"{keys[v]}: the direct path cannot run ({rd.errors[0][:120]})")
            elif rd.ok != rl.ok:
                reasons.append(f"{keys[v]}: " + (f"the direct path fails ({(rd.errors or ['?'])[0][:120]})" if rl.ok else
                                                  "the paths disagree on validity (the lake path fails)"))
            elif count and rd.ok and rd.heartbeats is None and rl.heartbeats is not None:
                reasons.append(f"{keys[v]}: no heartbeat reading on the direct path")
            elif not rd.ok and not rl.ok:
                e["note"] = "the seed fails on both paths"
            pins[keys[v]] = e
        fallback = "; ".join(dict.fromkeys(reasons)) or None
        with _LOCK:
            _RUN["tests"].update(pins)
            if fallback and not _RUN["fallback"]:
                _RUN["fallback"] = fallback
        path = self.path
        if fallback:
            self.log(f"meter: FALLBACK to the lake path for the whole run: {fallback}")
        if not bad and res:
            k = 0 if path == "direct" else 1
            prim = res[self.versions[0]][k]
            compat = {v: bool(res[v][k].ok) for v in self.versions} if prim.ok else None
            r = self._reading(seed, prim, compat, None, path, 0)
            if _ok_reading(r):
                self._readings[sha(seed)] = r
        hd = (pins.get(keys[self.versions[0]]) or {}).get("hb_delta")
        self.test = {"cached": False, "path": path, "fallback": _RUN["fallback"], "pins": pins, "compiles": self.compiles - n0 + pre_compiles,
                     "seed_sha": sha(seed), "this_row_failed": bool(fallback)}
        if not fallback:
            self.log(f"meter self-test: direct and lake agree on {len(pins)} pin(s) (primary heartbeat delta {hd}); meter {path}")
        return self.test


# ---------------------------------------------------------------------------------------------------------------------------- collect
def _entry(proof: str, origin: str, score=None, tokens=None, heartbeats=None) -> dict:
    return {"sha": sha(proof), "proof": proof.strip(), "origins": [origin], "score": score, "tokens": tokens, "heartbeats": heartbeats}


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def collect(problem: str, steps: dict | None, pool_lines: list[dict] | None, seed: str, extra: list[dict] | None = None) -> list[dict]:
    """Distinct candidate proofs of one row (by sha of the stripped text), seed always included, best stored score first (stored scores
    are from different meters and Z assumptions: they only order the candidates). Each: {sha, proof, origins, score, tokens, heartbeats,
    seed}."""
    found: dict[str, dict] = {}

    def add(e):
        if not e["proof"]:
            return
        cur = found.get(e["sha"])
        if cur is None:
            found[e["sha"]] = e
            return
        for o in e["origins"]:
            if o not in cur["origins"]:
                cur["origins"].append(o)
        if e["score"] is not None and (cur["score"] is None or e["score"] > cur["score"]):
            cur.update(score=e["score"], tokens=e["tokens"], heartbeats=e["heartbeats"])

    add(_entry(seed, "seed"))
    for key, st in (steps or {}).items():
        it = (st or {}).get("item") or {}
        if isinstance(it.get("proof"), str) and it.get("verified", True) is not False:
            add(_entry(it["proof"], key, _num(it.get("score")), it.get("tokens"), it.get("heartbeats")))
    for ln in pool_lines or []:   # pool.jsonl lines (score_exact, run_id) and bank.jsonl lines (harness/bank.py: score, source; b63 item 1)
        if isinstance(ln, dict) and isinstance(ln.get("proof"), str):
            origin = f"bank:{ln.get('source')}" if ln.get("source") else f"pool:{ln.get('run_id') or '?'}"
            add(_entry(ln["proof"], origin, _num(ln.get("score_exact") if ln.get("score_exact") is not None else ln.get("score")),
                       ln.get("tokens"), ln.get("heartbeats")))
    for x in extra or []:
        if isinstance(x, dict) and isinstance(x.get("proof"), str) and x.get("problem", problem) == problem:
            add(_entry(x["proof"], str(x.get("label") or x.get("origin") or "extra"), _num(x.get("score")), x.get("tokens"), x.get("heartbeats")))
    s0 = sha(seed)
    for e in found.values():
        e["seed"] = e["sha"] == s0
    return sorted(found.values(), key=lambda e: (e["score"] is None, -(e["score"] or 0.0)))


# -------------------------------------------------------------------------------------------------------------------------- crossover
def _indent(l: str) -> int:
    return len(l) - len(l.lstrip(" "))


def _parse(text: str, statement: str) -> dict | None:
    """Top-level tactic blocks of a `by` proof (harness/golf.instrument's top-level steps): head lines, blocks (lists of lines), tail
    clause lines (termination_by / decreasing_by / where), base indentation. None for a term proof or a one-line proof."""
    from harness.golf import instrument
    try:
        r = instrument(text, statement, top_only=True)
    except Exception:  # noqa: BLE001
        return None
    if not r or len(r[1]) < 2:
        return None
    lines, idx = text.split("\n"), r[1]
    starts, end = idx[:-1], idx[-1]
    return {"head": lines[:starts[0]], "blocks": [lines[a:b] for a, b in zip(starts, starts[1:] + [end])], "tail": lines[end:],
            "base": _indent(lines[starts[0]])}


def _key(block: list[str], base: int) -> str:
    ls = [l[base:] if not l[:base].strip() else l.lstrip() for l in block]
    while ls and not ls[-1].strip():
        ls.pop()
    return "\n".join(l.rstrip() for l in ls)


def _shift(block: list[str], frm: int, to: int) -> list[str]:
    if frm == to:
        return list(block)
    return [(" " * (to - frm) + l if to > frm else l[min(frm - to, _indent(l)):]) if l.strip() else l for l in block]


def _join(head, blocks, tail) -> str:
    return "\n".join(list(head) + [l for b in blocks for l in b] + list(tail)).strip()


_HAVE = re.compile(r"^(?:have|haveI)\s+([^\s:(\[{⟨]+)")


def splices(texts: list[str], statement: str) -> list[tuple[str, str]]:
    """Crossover children of texts[0] (the incumbent) with the other texts: (label, declaration). Head/tail splices only at shared
    top-level boundaries (a block of A identical to a block of B, up to indentation: A up to it + B after it, and B up to it + A after it);
    per `have` name shared by several texts, the incumbent's block replaced by the cheapest (fewest tokens) version, one name at a time
    and all at once. Children equal to a parent are dropped; have swaps first, then splices by token count."""
    parsed = [_parse(t.strip(), statement) for t in texts]
    A = parsed[0]
    if A is None:
        return []
    parents = {t.strip() for t in texts}
    have, sp = [], []
    groups: dict = {}
    for t, P in enumerate(parsed):
        for b in (P or {}).get("blocks", []):
            m = _HAVE.match(b[0].strip())
            if m:
                k = _key(b, P["base"])
                groups.setdefault(_have_head(b[0]), []).append((count_tokens(k), k, t, b, P["base"]))
    swaps = {}
    for i, b in enumerate(A["blocks"]):
        m = _HAVE.match(b[0].strip())
        if not m or len(groups.get(_have_head(b[0]), [])) < 2:   # review 2026-10-21: same name AND type (`h`, `this` recur with other types)
            continue
        tok, k, t, bb, base = min(groups[_have_head(b[0])], key=lambda g: (g[0], g[2]))
        if k != _key(b, A["base"]):
            swaps[i] = (m.group(1), t, _shift(bb, base, A["base"]))
    for i, (n, t, nb) in swaps.items():
        have.append((f"have {n} from #{t}", _join(A["head"], A["blocks"][:i] + [nb] + A["blocks"][i + 1:], A["tail"])))
    if len(swaps) > 1:
        have.append((f"have x{len(swaps)} cheapest", _join(A["head"], [swaps[i][2] if i in swaps else b for i, b in enumerate(A["blocks"])],
                                                           A["tail"])))
    akeys = [_key(b, A["base"]) for b in A["blocks"]]
    for t, B in enumerate(parsed[1:], 1):
        if B is None:
            continue
        Bt = [_shift(b, B["base"], A["base"]) for b in B["blocks"]]
        bkeys = [_key(b, B["base"]) for b in B["blocks"]]
        for i, ak in enumerate(akeys):
            for j, bk in enumerate(bkeys):
                if not ak or ak != bk:
                    continue
                sp.append((f"A[:{i + 1}]+#{t}[{j + 1}:]", _join(A["head"], A["blocks"][:i + 1] + Bt[j + 1:], A["tail"])))
                sp.append((f"#{t}[:{j + 1}]+A[{i + 1}:]", _join(A["head"], Bt[:j + 1] + A["blocks"][i + 1:], A["tail"])))

    def ntok(s):
        b = split_declaration(s, statement)
        return count_tokens(b) if b is not None else 1 << 30
    out, seen = [], set(parents)
    for label, s in have + sorted(sp, key=lambda x: ntok(x[1])):
        if s not in seen and s.startswith(statement):
            seen.add(s)
            out.append((label, s))
    return out


def _atomic(path: Path, text: str) -> None:
    """Write via a temporary file and rename (a killed run never leaves a truncated meter.json or finals.json)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def _have_head(line: str) -> str:
    """A `have` line's header up to `:=` with whitespace normalised: the key under which blocks from different parents are compared."""
    return re.sub(r"\s+", " ", line.split(":=", 1)[0]).strip()


def rebase(base: str, cand: str, new_base: str) -> str | None:
    """`cand`'s edit of `base` (the smallest changed span, widened to whole lines) applied to `new_base`, or None when that block of
    `base` does not occur exactly once in `new_base` (greedy stacking of independent edits)."""
    if base == new_base:
        return cand
    p = 0
    while p < min(len(base), len(cand)) and base[p] == cand[p]:
        p += 1
    s = 0
    while s < min(len(base), len(cand)) - p and base[-1 - s] == cand[-1 - s]:
        s += 1
    a = base.rfind("\n", 0, p) + 1
    e = base.find("\n", len(base) - s)
    e = len(base) if e < 0 else e
    old, new = base[a:e], cand[a:len(cand) - (len(base) - e)]
    nb = "\n" + new_base + "\n"   # review 2026-10-21: whole lines only (a raw substring could land inside another line)
    if not old.strip() or nb.count("\n" + old + "\n") != 1:
        return None
    return nb.replace("\n" + old + "\n", "\n" + new + "\n", 1)[1:-1]


# ------------------------------------------------------------------------------------------------------------------------------ sweep
def _apply_edits(body: str, edits) -> str:
    for pos, dl, ins in sorted(edits, key=lambda e: e[0], reverse=True):
        body = body[:pos] + ins + body[pos + dl:]
    return body


def _items(raw, base: str, statement: str, default: str = "sweep") -> list[dict]:
    """sweep_items with each candidate's op and end-stage hints kept: [{"label" (op: note, 60 chars), "full" (the whole label), "text",
    "op" (None when the generator gives none), and "timeout_s" / "cost" / "span" when the generator gives them}]."""
    body0 = split_declaration(base, statement)
    head = base[:len(base) - len(body0)] if body0 is not None else None
    out = []
    for x in raw or []:
        label, op, text, body, edits, hints = default, None, None, None, None, {}
        if isinstance(x, str):
            text = x
        elif isinstance(x, dict):
            op = x.get("op") or x.get("label") or x.get("kind")
            label = str(op or label) + (f": {x['note']}" if x.get("note") else "")
            text = x.get("proof") or x.get("decl") or x.get("text") or x.get("candidate")
            body, edits = x.get("body"), x.get("edits")
            hints = {k_: x[k_] for k_ in ("cost", "span") if x.get(k_) is not None}
            to = x.get("timeout_s")
            if isinstance(to, (int, float)) and not isinstance(to, bool) and math.isfinite(to) and to > 0:
                hints["timeout_s"] = to
        elif isinstance(x, (tuple, list)):
            strs = [s for s in x if isinstance(s, str)]
            text = next((s for s in strs if s.startswith(statement)), None)
            op = next((s for s in strs if s is not text), None)
            label = op or label
        else:
            op = getattr(x, "op", None) or getattr(x, "kind", None) or getattr(x, "label", None)
            label = str(op or label)
            text = getattr(x, "proof", None) or getattr(x, "decl", None) or getattr(x, "text", None)
            body, edits = getattr(x, "body", None), getattr(x, "edits", None)
        if not isinstance(text, str) and head is not None:
            if isinstance(body, str):
                text = head + body
            elif edits:
                try:
                    text = head + _apply_edits(body0, edits)
                except (TypeError, ValueError):
                    text = None
        if isinstance(text, str) and text.startswith(statement):
            out.append({"label": label[:60], "full": label, "text": text.strip(), "op": str(op) if op else None, **hints})
    return out


def sweep_items(raw, base: str, statement: str) -> list[tuple[str, str]]:
    """(label, declaration) from whatever harness.sweep.candidates yields: declarations, (label, declaration) pairs, dicts or objects with
    proof / decl / text / body / edits (body edits as (pos, deleted, inserted)) and op / kind / label."""
    return [(d["label"], d["text"]) for d in _items(raw, base, statement)]


def _fop(family: str, op) -> str:
    """'<family>:<op>' (an op already prefixed with its family id, as the tool modules' ops are, is kept as it is)."""
    if not op:
        return family
    op = str(op)
    return op if op.startswith(family + ":") else f"{family}:{op}"


def _norm_line(line: str) -> str:
    t = line.rstrip()
    ind = len(t) - len(t.lstrip(" "))
    return t[:ind] + " ".join(t.split())


def edit_key(fop: str, base: str, cand: str) -> str | None:
    """The failure-cache key of `cand` as an edit of `base`: the op, the changed lines of `base` (the smallest changed span widened to
    whole lines, as rebase() takes it), their replacement and one line of context on each side, whitespace inside lines normalised
    (indentation kept). None when nothing changed. Equal keys: the same op made the same edit on a region that has not changed."""
    if base == cand:
        return None
    p = 0
    while p < min(len(base), len(cand)) and base[p] == cand[p]:
        p += 1
    s_ = 0
    while s_ < min(len(base), len(cand)) - p and base[-1 - s_] == cand[-1 - s_]:
        s_ += 1
    a = base.rfind("\n", 0, p) + 1
    e = base.find("\n", len(base) - s_)
    e = len(base) if e < 0 else e
    old, new = base[a:e], cand[a:len(cand) - (len(base) - e)]
    before = base[:a - 1].rsplit("\n", 1)[-1] if a > 0 else ""
    after = base[e + 1:].split("\n", 1)[0] if e < len(base) else ""
    norm = lambda t: "\n".join(_norm_line(l) for l in t.split("\n"))   # noqa: E731
    return hashlib.sha256("\x00".join([fop, norm(before), norm(old), norm(new), norm(after)]).encode()).hexdigest()[:20]


def _load_sweep():
    try:
        return importlib.import_module("harness.sweep"), None
    except ImportError as e:   # ModuleNotFoundError included (B62b ships before or without the sweep port)
        return None, f"{type(e).__name__}: {e}"[:200]


def _load_family(name: str):
    """(module, None) or (None, why) for a family of FAMILIES (the sweep through _load_sweep, as B62b imports it)."""
    if name == "sweep":
        return _load_sweep()
    try:
        return importlib.import_module(FAMILIES[name]["module"]), None
    except ImportError as e:
        return None, f"{type(e).__name__}: {e}"[:200]


def families_for(sweep: bool = True, tools=()) -> tuple[str, ...]:
    """The end stage's families in run order: the sweep (unless sweep=False) and `tools` (names of FAMILIES; a comma-separated string is
    accepted), in FAMILIES order with the cheap tier first, whatever order they are given in (an arm is its set of families). Unknown names
    raise ValueError. families_for() == DEFAULT_FAMILIES."""
    if isinstance(tools, str):
        tools = tools.split(",")
    names = list(dict.fromkeys((["sweep"] if sweep else []) + [str(t).strip() for t in (tools or ()) if str(t).strip()]))
    bad = [n for n in names if n not in FAMILIES]
    if bad:
        raise ValueError(f"unknown end-stage family: {', '.join(bad)} (known: {', '.join(FAMILIES)})")
    order = list(FAMILIES)
    return tuple(sorted(names, key=lambda n: (FAMILIES[n]["tier"], order.index(n))))


def parse_caps(specs) -> dict:
    """{family: compiles} from "t3=200" items (several per item with commas), or from a {family: compiles} dict (R3, the config file);
    a cap may also name "crossover"."""
    out = {}
    if isinstance(specs, dict):
        specs = [f"{f}={n}" for f, n in specs.items()]
    for spec in ([specs] if isinstance(specs, str) else list(specs or [])):
        for part in str(spec).split(","):
            if not part.strip():
                continue
            name, _, n = part.partition("=")
            name = name.strip()
            if name not in FAMILIES and name != "crossover":
                raise ValueError(f"--family-cap: unknown family {name!r} (known: {', '.join(FAMILIES)}, crossover)")
            out[name] = int(n)
    return out


def parse_search_budgets(specs) -> dict:
    """L5 (module docstring, "count budgets"): {family: {"checks": N, "backstop_s": S or None}} from "FAMILY=N[:S]" items (repeatable, or
    comma-separated) or from a {family: {"checks": N, "backstop_s": S}} dict (the config's budgets.search; "_" keys are documentation).
    Only the search families (SEARCH_FAMILIES) take one; N >= 1 readings per row over all the family's searches, S > 0 seconds of the row's
    search wall time (None: SEARCH_BACKSTOP_FACTOR x the module's SEARCH_SECONDS). ValueError names the first bad item."""
    out: dict = {}
    if isinstance(specs, dict):
        items = []
        for f, d in specs.items():
            if str(f).startswith("_"):
                continue
            if not isinstance(d, dict):
                raise ValueError(f"budgets.search.{f}: want an object {{\"checks\": N, \"backstop_s\": S}}, got {d!r}")
            extra = [k_ for k_ in d if k_ not in ("checks", "backstop_s") and not str(k_).startswith("_")]
            if extra:
                raise ValueError(f"budgets.search.{f}: unknown key(s) {', '.join(map(str, extra))} (known: checks, backstop_s)")
            items.append((str(f), d.get("checks"), d.get("backstop_s")))
    else:
        items = []
        for spec in ([specs] if isinstance(specs, str) else list(specs or [])):
            for part in str(spec).split(","):
                if not part.strip():
                    continue
                name, eq, rest = part.partition("=")
                if not eq:
                    raise ValueError(f"--search-budget: want FAMILY=CHECKS[:SECONDS], got {part!r}")
                n, _, s_ = rest.partition(":")
                try:
                    items.append((name.strip(), int(n), float(s_) if s_.strip() else None))
                except ValueError:
                    raise ValueError(f"--search-budget: want FAMILY=CHECKS[:SECONDS], got {part!r}") from None
    for f, n, s_ in items:
        if f not in SEARCH_FAMILIES:
            raise ValueError(f"search budget: {f!r} is not a search family (search families: {', '.join(SEARCH_FAMILIES)})")
        if not _is_int(n, 1):
            raise ValueError(f"search budget {f}: checks must be an integer >= 1, got {n!r}")
        if not (s_ is None or _is_num(s_)):
            raise ValueError(f"search budget {f}: backstop_s must be a number > 0 or null, got {s_!r}")
        out[f] = {"checks": int(n), "backstop_s": float(s_) if s_ is not None else None}
    return out


def parse_ops(specs) -> dict:
    """{family: [ops]} op allow-lists (module docstring, "ops") from "FAMILY=OP[,OP..]" items (one family per item, repeatable) or from a
    {family: [ops] or "op,op"} dict (the config file's "ops"); each op as "<family>:<op>" (_fop), given order kept, duplicates dropped; an
    empty list runs none of the family's ops. Unknown families and the sweep (its phase is the control's) raise ValueError (unknown ops:
    check_ops())."""
    if isinstance(specs, dict):
        pairs = list(specs.items())
    else:
        pairs = []
        for spec in ([specs] if isinstance(specs, str) else list(specs or [])):
            name, eq, ops = str(spec).partition("=")
            if not eq:
                raise ValueError(f"--ops: want FAMILY=OP[,OP..], got {spec!r}")
            pairs.append((name.strip(), ops))
    out: dict = {}
    for name, ops in pairs:
        if name not in FAMILIES or name == "sweep":
            raise ValueError(f"--ops: want a tool family ({', '.join(f for f in FAMILIES if f != 'sweep')}), got {name!r}"
                             + (" (the sweep phase is the control's: no allow-list)" if name == "sweep" else ""))
        L = out.setdefault(name, [])
        for o in (ops.split(",") if isinstance(ops, str) else list(ops or [])):
            f = _fop(name, str(o).strip()) if str(o).strip() else None
            if f and f not in L:
                L.append(f)
    return out


def parse_opt_in(specs) -> dict:
    """{family: [ops]} from "FAMILY:OP" items (repeatable or comma-separated; the config file's "opt_in" list): the opt-in ops to add
    to a tool family's default op set (passed as its ctx["opt_in"]). A name without a tool family prefix raises ValueError."""
    out: dict = {}
    for spec in ([specs] if isinstance(specs, str) else list(specs or [])):
        for o in str(spec).split(","):
            o = o.strip()
            if not o:
                continue
            fam, sep, rest = o.partition(":")
            if not sep or not rest or fam not in FAMILIES or fam == "sweep":
                raise ValueError(f"--opt-in: want <tool family>:<op> ({', '.join(f for f in FAMILIES if f != 'sweep')}), got {o!r}")
            L = out.setdefault(fam, [])
            if o not in L:
                L.append(o)
    return out


def family_ctx_of(a) -> dict:
    """{family: ctx keys} from the CLI namespace (module docstring, "ops"): the config file's "ctx", then --opt-in ({"opt_in": [..]});
    families without a key are left out ({} when none is given). The t3 probe mode is not a ctx key: it is end_stage's t3_suggest."""
    out: dict = {}
    for f, d in (getattr(a, "family_ctx_extra", None) or {}).items():
        if d:
            out.setdefault(f, {}).update(dict(d))
    oi = getattr(a, "opt_in", None)
    for f, ops in (oi if isinstance(oi, dict) else parse_opt_in(oi)).items():
        if ops:
            out.setdefault(f, {})["opt_in"] = list(ops)
    return out


def known_ops(fam: str, mod=None) -> list[str] | None:
    """The ops a family module declares, as "<family>:<op>": its ALL_OPS (every op it can generate, opt-in ones included) when it has
    one, else its OPS; None for a module without either (a fake, or one being written: not checked)."""
    mod = mod if mod is not None else _load_family(fam)[0]
    known = getattr(mod, "ALL_OPS", None) or getattr(mod, "OPS", None)
    return None if known is None else [_fop(fam, o) for o in known]


def effective_ops(fam: str, fctx: dict | None = None, allow=None, t3_suggest=False, mod=None) -> list[str] | None:
    """The ops a tool family runs under its family ctx `fctx` and allow-list `allow` (module docstring, "ops"): the module's ops_for(ctx)
    when it has one (T1: DEFAULT_OPS plus its opt-ins, or the allow-list; T3: its op order, t3:hint first when the probe is on), else
    known_ops(); then only the ops in `allow`. None when the module is absent or declares no ops."""
    mod = mod if mod is not None else _load_family(fam)[0]
    if mod is None:
        return None
    c = dict(fctx or {})
    if allow is not None:
        c["ops"] = list(allow)
    if hasattr(mod, "ops_for"):
        ops = [_fop(fam, o) for o in mod.ops_for(c, **_kwargs_for(mod.ops_for, {"has_suggestions": bool(t3_suggest)}))]
    else:
        ops = known_ops(fam, mod)
        if ops is None:
            return None
    return [o for o in ops if allow is None or o in set(allow)]


def normalize_method(a, fams) -> None:
    """In place on the CLI namespace (module docstring, "ops"): t3_suggest True -> "rule", None -> False; --screen-depth SCREEN_DEPTH ->
    unset; empty opt-in lists dropped; an allow-list equal (as a set) to its family's default op set under the same family ctx dropped
    (the family then runs exactly as without it). The call and end_config.json then carry only what differs from the code's default."""
    a.t3_suggest = "rule" if getattr(a, "t3_suggest", False) is True else (getattr(a, "t3_suggest", False) or False)
    if getattr(a, "screen_depth", None) == SCREEN_DEPTH:
        a.screen_depth = None
    oi = getattr(a, "opt_in", None) or {}
    a.opt_in = {f: list(v) for f, v in (oi if isinstance(oi, dict) else parse_opt_in(oi)).items() if v}
    fc = family_ctx_of(a)
    keep = {}
    for f, allow in (getattr(a, "family_ops", None) or {}).items():
        if f in fams:
            dflt = effective_ops(f, fc.get(f), None, a.t3_suggest)
            if dflt is not None and set(allow) == set(dflt):
                continue
        keep[f] = list(allow)
    a.family_ops = keep


CONFIG_CTX_KEYS = {"t3": ("t3_ops",)}   # R3: the family ctx keys a config file may set (op names only; module docstring, "config")
T3_SUGGEST_MODES = ("rule", "try?", "hint", "both")   # --t3-suggest / the config's t3_suggest (harness/tools/t3_suggest.MODES)


def check_ops(fams, family_ops: dict | None, opt_in: dict | None, extra: dict | None = None) -> list[str]:
    """Why a run's op settings cannot start (empty: they can): a family-specific setting for a family that is not run; an op that the
    family module does not declare (known_ops(): ALL_OPS, else OPS), in an allow-list or in a CONFIG_CTX_KEYS value of `extra`; an
    opt-in op that its OPT_IN_OPS does not list (or a module without opt-in ops). A module without ops (a fake, or one being written) is
    not checked."""
    bad = []
    for what, d in (("--ops", family_ops), ("--opt-in", opt_in), ("ctx", extra)):
        for f in (d or {}):
            if f not in fams:
                bad.append(f"{what}: family {f} is not run (families: {', '.join(fams) or 'none'})")
    ctx_ops = {f: [_fop(f, o) for k_, v in (d or {}).items() if k_ in CONFIG_CTX_KEYS.get(f, ()) for o in (v or [])]
               for f, d in (extra or {}).items()}
    for what, d in (("--ops", family_ops), ("--opt-in", opt_in), ("ctx", ctx_ops)):
        for f, ops in (d or {}).items():
            if f not in fams:
                continue
            mod = _load_family(f)[0]
            known = known_ops(f, mod)
            if known is None:
                continue
            unk = [o for o in ops if o not in known]
            if unk:
                bad.append(f"{what}: unknown {f} op(s) {', '.join(unk)} (known: {', '.join(known)})")
            if what == "--opt-in":
                oi = [_fop(f, o) for o in (getattr(mod, "OPT_IN_OPS", None) or ())]
                no = [o for o in ops if o in known and o not in oi]
                if no:
                    bad.append(f"--opt-in: {', '.join(no)} is not an opt-in op of {f} (its opt-in ops: {', '.join(oi) or 'none'})")
    return bad


def _kwargs_for(fn, kw: dict) -> dict:
    """The keyword arguments of `kw` that `fn` accepts (a generator without ctx / max_per_op gets the call it was written for)."""
    import inspect
    try:
        ps = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}
    if any(q.kind is inspect.Parameter.VAR_KEYWORD for q in ps.values()):
        return dict(kw)
    return {k_: v for k_, v in kw.items() if k_ in ps}


def _why(reason: str) -> str:
    """The reject category of a scorer.accept.decide reason."""
    r = reason or ""
    return "Z" if "fewer toolchains" in r else "noise" if "saves no token" in r else "below_bar" if "below the bar" in r else "other"


def family_summary(decisions: list[dict], stats: dict | None = None) -> dict:
    """Per family, from the candidate records (those with "fop"): candidates logged, tried (a compile was attempted, a batch screen
    included), compiled (primary pin), banked, compiles (batch screens included), the banked d_score / tokens / heartbeats summed, rejects
    by category and per op (candidates, compiled, banked); with batch screening (tool phase): screened (went into a batch), screen_passed,
    screen_failed, screen_unknown (left to the measurement), measured (read on the meter after the screen or without one); plus the run
    counters in `stats` (generated, visited, passes, seconds, capped, skipped, screen_batches, screen_compiles, screen_seconds,
    measure_seconds)."""
    out: dict = {}

    def fam(f):
        return out.setdefault(f, {"candidates": 0, "tried": 0, "compiled": 0, "banked": 0, "compiles": 0, "d_score": 0.0, "tokens_saved": 0,
                                  "hb_saved": 0, "rejects": {}, "ops": {}})
    for f in stats or {}:   # run order first
        fam(f)
    for d in decisions:
        if not d.get("fop") or not d.get("family"):
            continue
        F = fam(d["family"])
        o = F["ops"].setdefault(d["fop"], {"candidates": 0, "compiled": 0, "banked": 0})
        F["candidates"] += 1
        o["candidates"] += 1
        F["compiles"] += int(d.get("compiles") or 0)
        if d.get("compiled") is not None:
            F["tried"] += 1
            if d.get("at") != "batch":
                F["measured"] = F.get("measured", 0) + 1
        sv = d.get("screen")
        if sv and sv != "unscreened":
            F["screened"] = F.get("screened", 0) + 1
            k_ = "screen_passed" if sv == "pass" else "screen_unknown" if sv == "unknown" else "screen_failed"
            F[k_] = F.get(k_, 0) + 1
        if d.get("compiled"):
            F["compiled"] += 1
            o["compiled"] += 1
        if d.get("banked"):
            F["banked"] += 1
            o["banked"] += 1
            F["d_score"] += float(d.get("d_score") or 0.0)
            F["tokens_saved"] += int(d.get("d_tokens") or 0)
            F["hb_saved"] += int(d.get("d_heartbeats") or 0)
        elif d.get("reject"):
            F["rejects"][d["reject"]] = F["rejects"].get(d["reject"], 0) + 1
    for f, st in (stats or {}).items():
        fam(f).update({k_: (round(v, 1) if isinstance(v, float) else v) for k_, v in st.items()})
        fam(f)["compiles"] += int(st.get("screen_compiles") or 0) + int(st.get("probe_compiles") or 0)
    for F in out.values():
        F["d_score"] = round(F["d_score"], 6)
    return out


# ------------------------------------------------------------------------------------------------------------------------- end stage
class _Budget(Exception):
    pass   # bare: max_compiles; with a message: the wall budget


class _FamilyCap(Exception):
    pass


def _wall(start: float, budget_s, budget_label: str, backstop, phase: str) -> tuple:
    """(deadline, message) of a phase (L5): the earlier of its wall budget (`budget_label` {s} reached, the message it always had) and its
    wall backstop (count budgets: the phase is meant to end on its compile counts; the backstop only guards a stuck or very slow host);
    (None, None) when it has neither."""
    opts = []
    if budget_s:
        opts.append((start + float(budget_s), f"{budget_label} {budget_s:g} reached"))
    if backstop:
        opts.append((start + float(backstop), f"wall backstop {backstop:g} s reached ({phase} phase; its compile budget did not stop it)"))
    return min(opts, key=lambda o: o[0]) if opts else (None, None)


def _stop_at(wall: tuple, stop_at) -> tuple:
    """b85: (deadline, message) of a phase under the caller's absolute deadline `stop_at` (None: `wall` unchanged)."""
    if stop_at is None:
        return wall
    if wall[0] is not None and wall[0] <= float(stop_at):
        return wall
    return float(stop_at), "stop_at reached (the caller's wall deadline)"


def _stats_since(stats: dict, snap: dict) -> dict:
    """A screener's counters since `snap` (numbers subtracted; anything else, e.g. "broken", as it is now)."""
    out = {}
    for k_, v in stats.items():
        b = snap.get(k_)
        out[k_] = (v - b) if isinstance(v, (int, float)) and not isinstance(v, bool) and isinstance(b, (int, float)) else v
    return out


def _search_used(pst: dict | None) -> int:
    """A search family's workbench readings on this row so far (its stats' "checks" (t5) or "readings" (t6, t7, t8, t11))."""
    p = pst or {}
    return int(p.get("checks", p.get("readings", 0)) or 0)


def end_stage(row: dict, seed: str, cands: list[dict], meter, *, k: int = K, sweep: bool = True, crossover: bool = True,
              max_compiles: int = MAX_COMPILES, checkpoint_bests: dict | None = None, log=print, tools=(), max_seconds: float | None = None,
              family_caps: dict | None = None, passes: int = PASSES, max_per_op: int | None = None, fail_cache: bool | None = None,
              cache: dict | None = None, ctx: dict | None = None, ctx_fn=None, tools_max_compiles: int | None = None,
              tools_max_seconds: float | None = None, screen: bool | None = None, screen_k: int = SCREEN_K, screen_depth: int = SCREEN_DEPTH,
              screener=None, t3_suggest=False, family_ops: dict | None = None, family_ctx: dict | None = None,
              workbench=None, known_readings: dict | None = None, floor_sha: str | None = None, lazy_workbench: bool = True,
              backstop_s: float | None = None, tools_backstop_s: float | None = None, search_budgets: dict | None = None,
              screen_sweep: bool = False, stop_at: float | None = None) -> dict:
    """One row's end stage on `meter` (see the module docstring). `cands`: collect() entries (or dicts with proof / origins / score);
    `checkpoint_bests`: {label: item with proof, or a proof string}, always measured. Returns {"proof", "metrics", "stage" (pick, the
    family that banked last (sweep, t1, ..., sweep+), crossover; unmeasured when nothing could be read or the budget ran out before the
    seed and every checkpoint best were read: the last checkpoint best, else the best stored candidate, comes back unchanged),
    "picked_from", "decisions", "compiles" (this row; the run-start self-test is reported in "self_test"), "measured", "meter", "families"
    (the per-family summary), "tools" (the families run), "phases" (compiles and seconds of the sweep phase and the tool phase, the
    screen's counters)}.
    Families and budgets (module docstring): tools (a tool phase after the sweep phase; sweep=False drops the sweep), max_compiles /
    max_seconds (the sweep phase: pick, sweep, crossover; wall, search only), tools_max_compiles / tools_max_seconds (the tool phase;
    None: the sweep phase's values), family_caps {family: compiles}, passes (per phase), max_per_op (passed to the non-sweep generators;
    None: their default), fail_cache (None: off in the sweep phase, as the control runs it, on in the tool phase), cache (a dict carried
    across calls on one row: "failed" edit keys, "visited" proof hashes, "screen" verdicts), ctx (row-level keys merged into the
    generators' ctx after "source", "pins", "compile_s") and ctx_fn(proof) -> dict (proof-level keys such as a heartbeat "profile" or
    "goals" of the incumbent the family is about to edit); screen (None: batch screening in the tool phase when the meter offers
    screener(); False: off), screen_k (candidates per batch), screen_depth (halvings), screener (a ready harness.batch_screen
    BatchScreener, for tests), t3_suggest (R3: probe T3's spans with Lean's suggestion tactic before T3 generates; False: off; True or
    "rule": harness/tools/t3_suggest.PROBE_RULE; "try?" / "hint" / "both": t3_suggest.probe_tactics; module docstring), family_ops
    {family: [ops]} (an op allow-list per tool family: its generator's ctx["ops"] and a filter on what it returns) and family_ctx {family:
    {key: value}} (keys of that family's ctx only), module docstring "ops" (R3; None: the R2 calls); workbench (t5 only, module
    docstring "t5 search": a ready harness.workbench.Workbench-like object, or a callable (row, meter) -> one; None: a Workbench on the
    meter's primary pin, started at T5's first search and closed before this call returns).
    known_readings {sha: reading} (b63 speed, 2026-10-25): full readings (ok, tokens, heartbeats, Z, compat on every pin, score_exact,
    "meter" == this meter's path) already taken on this meter's path, e.g. the finals.json entry an earlier end stage wrote on the same
    meter; the pick takes them as read and confirmed (0 compiles) instead of compiling the same text again. The caller vouches for the
    path and the pins (replay_row checks sha, meter, pins, statement and recomputes the metrics). floor_sha: the sha of a known reading
    that an end stage on this meter already picked over the seed (finals "stage": "end:*"): the seed is then not read at all (its floor
    is carried by that reading); without it the seed is read as always. lazy_workbench (b63 speed, default True): a search family whose
    module has search_precheck() is searched without starting a workbench when the precheck names a reason (module docstring "speed");
    False starts it before every search as before (the records are the same either way).
    L5 count budgets (module docstring, "count budgets"; every default keeps the call above): backstop_s / tools_backstop_s (None: the
    sweep phase's) a phase's wall BACKSTOP next to (or instead of) max_seconds / tools_max_seconds: the earlier of the two stops the phase,
    a backstop stop is recorded as such; search_budgets {family: {"checks": N, "backstop_s": S}} a search family's per-row budget in
    workbench readings over all its searches (each search gets max_checks = min(the module's MAX_CHECKS, what is left)) with S (None:
    SEARCH_BACKSTOP_FACTOR x SEARCH_SECONDS) as its per-row wall backstop instead of the module's SEARCH_SECONDS; screen_sweep batch-screens
    the sweep's candidates (sweep phase and sweep+) like a tool family's (one compile per batch; only the copies that compile are measured).
    stop_at (b85, docs/b85_style_rw.md; None: unchanged): an absolute wall deadline (time.time()) for both phases: a phase's deadline is the
    earlier of its own and stop_at (a stop there is recorded as "stop_at reached"); like max_seconds it stops the search, never the pick.
    Only the style_rw step's polish passes it; every other call keeps its phases' own clocks."""
    t0 = time.time()
    statement = row["statement"]
    known = {h: dict(r) for h, r in (known_readings or {}).items() if _ok_reading(r) and r.get("compat")}
    decisions: list[dict] = []
    spent = [0]
    waited = lambda: float(getattr(meter, "slot_wait_s", 0.0) or 0.0)   # noqa: E731  (compile-slot waits, per phase)
    w0 = waited()
    fams = families_for(sweep, tools)
    tool_fams = tuple(f for f in fams if f != "sweep")
    caps = parse_caps([f"{f}={n}" for f, n in (family_caps or {}).items()])
    allow_l = parse_ops(family_ops) if family_ops else {}   # R3: per-family op allow-lists ("<family>:<op>")
    allow = {f: frozenset(v) for f, v in allow_l.items()}
    deadline, time_msg = _stop_at(_wall(t0, max_seconds, "max_seconds", backstop_s, "sweep"), stop_at)
    if getattr(meter, "test", None) is None and hasattr(meter, "self_test"):
        meter.self_test(seed)   # normally done at run start by the caller; its compiles are the run's, not this row's
    st = getattr(meter, "test", None)
    path = meter.freeze() if hasattr(meter, "freeze") else getattr(meter, "path", None)
    # the current phase's budget: the sweep phase is the control's stage (its compile budget counts the pick, its failure cache is off
    # unless asked); the tool phase gets its own (set below)
    ph = {"phase": None, "max": max_compiles, "base": 0, "deadline": deadline, "screen": None, "sweep_screen": None,
          "fcache": bool(fail_cache) if fail_cache is not None else False,
          "time_msg": time_msg, "count_msg": f"max_compiles {max_compiles} reached"}

    def afford(n):
        return spent[0] - ph["base"] + n <= ph["max"]

    def meas(text, full, Z=None, timeout=None):
        r = meter.measure(text, full=full, Z=Z, **({"timeout": timeout} if timeout else {}))
        spent[0] += int(r.get("compiles") or 0)
        return r

    def pins(text, timeout=None):
        if hasattr(meter, "pins"):
            p = meter.pins(text, **({"timeout": timeout} if timeout else {}))
            spent[0] += int(p.get("compiles") or 0)
            return p["compat"]
        r = meas(text, True, timeout=timeout)
        return r.get("compat") if r.get("ok") else None

    # ---- candidates: the seed, the checkpoint bests, the top k by stored score ----
    pool: dict[str, dict] = {}
    for c in cands or []:
        if isinstance(c, dict) and isinstance(c.get("proof"), str) and c["proof"].strip():
            e = dict(c, sha=c.get("sha") or sha(c["proof"]), proof=c["proof"].strip(), origins=list(c.get("origins") or [c.get("label") or "cand"]))
            pool.setdefault(e["sha"], e)
    s0 = sha(seed)
    pool.setdefault(s0, _entry(seed, "seed"))
    if "seed" not in pool[s0]["origins"]:
        pool[s0]["origins"].append("seed")
    ck = []
    for label, it in (checkpoint_bests or {}).items():
        text = it if isinstance(it, str) else (it or {}).get("proof")
        if not isinstance(text, str) or not text.strip():
            continue
        h = sha(text)
        if h not in pool:
            pool[h] = _entry(text, label, _num((it or {}).get("score") if isinstance(it, dict) else None))
        elif label not in pool[h]["origins"]:
            pool[h]["origins"].append(label)
        ck.append(h)
    rank = sorted(pool.values(), key=lambda e: (e.get("score") is None, -(e.get("score") or 0.0)))
    order = list(dict.fromkeys([s0] + sorted(dict.fromkeys(ck), key=lambda h: [e["sha"] for e in rank].index(h))
                               + [e["sha"] for e in rank if e["sha"] != s0 and e["sha"] not in ck][:max(0, k)]))
    known = {h: r for h, r in known.items() if h in pool and r.get("meter") == path}
    seed_skipped = bool(floor_sha) and floor_sha in known and floor_sha != s0
    if seed_skipped:   # the seed's floor is carried by a known reading an end stage on this meter already picked over it
        order = [h for h in order if h != s0]

    # ---- pick: primary readings back to back, pins confirmed in upper-bound order ----
    readings: dict[str, dict] = {}
    confirmed: dict[str, dict] = {}
    cached = meter.reading(pool[s0]["proof"]) if len(order) == 1 and order == [s0] and hasattr(meter, "reading") else None
    if cached:
        readings[s0] = confirmed[s0] = cached
        decisions.append({"op": "note", "banked": False, "reason": "only the seed to compare: the self-test reading of the seed is reused"})
    else:
        for h in order:
            if h in known:
                readings[h] = confirmed[h] = dict(known[h], compiles=0, reused=True)
                continue
            if not afford(meter.cost(False)):
                decisions.append({"op": "budget", "banked": False, "reason": f"max_compiles {max_compiles} reached while reading candidates"})
                break
            readings[h] = meas(pool[h]["proof"], False)
    if any(r.get("reused") for r in readings.values()):
        decisions.append({"op": "note", "banked": False, "reason": f"{sum(1 for r in readings.values() if r.get('reused'))} known reading(s) "
                          f"on this meter ({path}) reused, 0 compiles" + ("; the seed is not read: its floor is carried by the known reading "
                          "an end stage on this meter picked over it" if seed_skipped else "")})
    valid = sorted((h for h in readings if _ok_reading(readings[h])),
                   key=lambda h: (-readings[h]["score_exact"], readings[h]["tokens"], readings[h]["heartbeats"]))
    best = None
    for h in valid:
        r = readings[h]
        if h not in confirmed:
            if best is not None and r["score_exact"] <= confirmed[best]["score_exact"]:
                break   # Z <= 100: no later upper bound can beat the best confirmed score
            if not afford(meter.cost(True) - meter.cost(False)):
                decisions.append({"op": "budget", "banked": False, "reason": f"max_compiles {max_compiles} reached while confirming pins"})
                break
            compat = pins(pool[h]["proof"])
            if not compat:
                continue
            Zv = compat_pct(compat)
            confirmed[h] = dict(r, compat=compat, Z=Zv, Z_assumed=False, **meter.metrics(r["tokens"], r["heartbeats"], Zv))
            confirmed[h]["score"] = round(confirmed[h]["score_exact"], 2)
        c = confirmed[h]
        if best is None or (c["score_exact"], -c["tokens"], -c["heartbeats"]) > (confirmed[best]["score_exact"], -confirmed[best]["tokens"],
                                                                                 -confirmed[best]["heartbeats"]):
            best = h
    measured = [{"sha": h, "origins": pool[h]["origins"], "stored": pool[h].get("score"), "ok": _ok_reading(readings[h]),
                 "confirmed": h in confirmed, "score_exact": (confirmed.get(h) or readings[h]).get("score_exact"),
                 "tokens": readings[h].get("tokens"), "heartbeats": readings[h].get("heartbeats"), "Z": (confirmed.get(h) or {}).get("Z"),
                 "error": None if _ok_reading(readings[h]) else (readings[h].get("error") or "")[:160],
                 **({"reused": True} if readings[h].get("reused") else {})} for h in readings]
    # the floor: the seed and every checkpoint best must be read, and confirmed unless their upper bound is already beaten (one that does
    # not compile on this meter sets no floor); otherwise the last checkpoint best (the caller's current best) comes back unchanged
    bs = confirmed[best]["score_exact"] if best is not None else None
    short = [h for h in dict.fromkeys(([] if seed_skipped else [s0]) + ck) if h not in readings
             or (_ok_reading(readings[h]) and h not in confirmed and (bs is None or readings[h]["score_exact"] > bs))]
    if best is None or short:
        top = pool[ck[-1]] if ck else rank[0]
        why = ("no candidate could be read on this meter" if best is None else
               f"the compile budget ran out before {len(short)} floor candidate(s) (the seed, checkpoint bests) were read and confirmed")
        decisions.append({"op": "pick", "banked": False, "reason": f"{why}: {'+'.join(top['origins'])[:60]} is kept unmeasured"})
        log(f"end: {why} ({spent[0]} compiles); {'+'.join(top['origins'])[:60]} kept")
        return {"proof": top["proof"], "metrics": {k_: top.get(k_) for k_ in ("score", "tokens", "heartbeats")}, "stage": "unmeasured",
                "picked_from": top["origins"], "decisions": decisions, "compiles": spent[0], "measured": measured, "meter": path,
                "self_test": st, "seconds": round(time.time() - t0, 1), "families": {}, "tools": list(fams)}
    if ck and ck[-1] in confirmed and best != ck[-1]:   # review 2026-10-21: the current best stays unless the argmax passes the bank rule
        fl, bc = confirmed[ck[-1]], confirmed[best]
        ok_, why_ = decide({"score": fl["score_exact"], "tokens": fl["tokens"], "heartbeats": fl["heartbeats"], "Z": fl["Z"]},
                           {"score": bc["score_exact"], "tokens": bc["tokens"], "heartbeats": bc["heartbeats"], "Z": bc["Z"]})
        if not ok_:
            decisions.append({"op": "note", "banked": False, "reason": f"pick: {'+'.join(pool[best]['origins'])[:60]} does not pass the bank rule "
                                                                        f"against the current best ({why_}); the current best stays"})
            best = ck[-1]
    seed_r = confirmed.get(s0) or readings.get(s0)
    inc = {"proof": pool[best]["proof"], "sha": best, "reading": confirmed[best], "op": "pick", "origins": pool[best]["origins"]}
    decisions.append({"op": "pick", "banked": True, "sha": best, "label": "+".join(inc["origins"])[:80],
                      "d_score": None if not _ok_reading(seed_r) else round(inc["reading"]["score_exact"] - seed_r["score_exact"], 6),
                      "reason": f"best of {len(valid)} compiling of {len(readings)} read ({len(confirmed)} confirmed on all pins); d_score vs the seed"
                      + ("; the seed was not read (floor carried by the reused finals reading)" if seed_skipped else "")})
    log(f"end: pick {inc['reading']['score_exact']:.4f} from {'+'.join(inc['origins'])[:60]} ({len(readings)} read, {spent[0]} compiles)")
    tried = set(readings)   # the visited set: proof hashes already read on this meter
    failed_keys: set = set()   # the failure cache (edit_key of edits that failed), used when the phase's fcache is on
    screen_cache: dict = {}    # batch-screen verdicts by candidate hash (tool phase)
    if isinstance(cache, dict):
        tried = cache["visited"] = set(cache.get("visited") or ()) | tried
        failed_keys = cache["failed"] = set(cache.get("failed") or ())
        screen_cache = cache.setdefault("screen", {})
    banks = [0]
    failed_edits: list = []
    fam_spent: dict = {}
    stats: dict = {}
    exhausted: set = set()
    last = [None]

    def over_time():
        return ph["deadline"] is not None and time.time() > ph["deadline"]

    # ---- one paired, confirmed decision ----
    def attempt(op, label, text, family=None, fop=None, timeout=None, extra=None):
        text = text.strip()
        h = sha(text)
        last[0] = None
        if h in tried:
            return False
        tried.add(h)
        rec = {"op": op, "label": label, "sha": h, "banked": False}
        if family:
            rec.update(family=family, fop=fop or family)
        if extra:
            rec.update(extra)
        if timeout:
            rec["timeout_s"] = timeout
        last[0] = rec
        decisions.append(rec)
        n_start = spent[0]
        fam = family or op

        def need(n):   # before each compile: the wall budget, the phase's compile budget, the family's cap
            if over_time():
                raise _Budget(ph["time_msg"])
            if not afford(n):
                raise _Budget
            cap = caps.get(fam)
            if cap is not None and fam_spent.get(fam, 0) + (spent[0] - n_start) + n > cap:
                raise _FamilyCap(fam)
        try:
            body = split_declaration(text, statement)
            if body is None:
                rec.update(reason="statement differs", reject="statement")
                return False
            I = inc["reading"]
            rec["d_tokens"] = I["tokens"] - count_tokens(body)   # known before any compile (the same count the reading takes)
            z_inc = float(I["Z"])
            z_scr = z_inc
            need(meter.cost(False))
            c1 = meas(text, False, Z=z_scr, timeout=timeout)
            if not _ok_reading(c1):
                err = c1.get("error") or "?"
                rec.update(reason=f"does not compile on the primary pin: {err[:140]}", compiled=False,
                           reject="timeout" if c1.get("timed_out") or err == "timeout" else "no_compile")
                return False
            rec["compiled"] = True
            if z_inc < 100.0:   # review 2026-10-21: the incumbent misses a pin, so the candidate's own pins decide (not an assumed Z 100)
                need(meter.cost(True) - meter.cost(False))
                cp = pins(text, timeout=timeout)
                z_scr = compat_pct(cp) if cp else z_inc
                c1 = dict(c1, Z=z_scr, **meter.metrics(c1["tokens"], c1["heartbeats"], z_scr))
            cand = {"score": c1["score_exact"], "tokens": c1["tokens"], "heartbeats": c1["heartbeats"], "Z": z_scr}
            m = SCREEN_HB + math.ceil(SCREEN_FRAC * I["heartbeats"])
            stale = {"score": meter.metrics(I["tokens"], I["heartbeats"] + m, z_inc)["score_exact"], "tokens": I["tokens"],
                     "heartbeats": I["heartbeats"] + m, "Z": z_inc}
            ok, why = decide(stale, cand)
            rec.update(d_score=round(cand["score"] - I["score_exact"], 6), d_tokens=I["tokens"] - cand["tokens"],
                       d_heartbeats=I["heartbeats"] - cand["heartbeats"])
            if not ok:
                rec.update(reason=f"screen (incumbent's last reading + {m}): {why}", reject=_why(why), at="screen")
                return False
            need(meter.cost(False))
            i1 = meas(inc["proof"], False, Z=z_inc)   # the incumbent re-measured right after the candidate (paired), default timeout
            if not _ok_reading(i1):
                rec.update(reason=f"the incumbent's paired reading failed: {(i1.get('error') or '?')[:120]}", reject="meter")
                return False
            paired = {"score": i1["score_exact"], "tokens": i1["tokens"], "heartbeats": i1["heartbeats"], "Z": z_inc}
            ok, why = decide(paired, cand)
            rec.update(d_score=round(cand["score"] - paired["score"], 6), d_tokens=paired["tokens"] - cand["tokens"],
                       d_heartbeats=paired["heartbeats"] - cand["heartbeats"], paired=True)
            if not ok:
                rec.update(reason=f"paired: {why}", reject=_why(why), at="paired")
                return False
            need(meter.cost(True))
            c2 = meas(text, True, timeout=timeout)   # fresh confirmation on every pin; the worse heartbeat reading counts
            if not _ok_reading(c2) or not c2.get("compat"):
                rec.update(reason=f"confirmation failed: {(c2.get('error') or '?')[:140]}", at="confirmation",
                           reject="timeout" if c2.get("timed_out") else "confirmation_failed")
                return False
            hb = max(int(c1["heartbeats"]), int(c2["heartbeats"]))
            fin = dict(c2, heartbeats=hb, **meter.metrics(c2["tokens"], hb, c2["Z"]))
            fin["score"] = round(fin["score_exact"], 2)
            final = {"score": fin["score_exact"], "tokens": fin["tokens"], "heartbeats": hb, "Z": fin["Z"]}
            ok, why = decide(paired, final)
            rec.update(d_score=round(final["score"] - paired["score"], 6), d_tokens=paired["tokens"] - final["tokens"],
                       d_heartbeats=paired["heartbeats"] - hb, confirmed_hb=(c1["heartbeats"], c2["heartbeats"]))
            if not ok:
                rec.update(reason=f"confirmation: {why}", reject=_why(why), at="confirmation")
                return False
            rec.update(banked=True, reason=why)
            inc.update(proof=text, sha=h, reading=fin, op=op, origins=[f"{op}:{label}"])
            banks[0] += 1
            log(f"end: {op} banked {why} -> {fin['score_exact']:.4f} ({label[:40]})")
            return True
        except _Budget as e:
            rec.update(reason=str(e) or ph["count_msg"], reject="budget")
            tried.discard(h)   # not decided: a later call sharing `cache` may read it (this call's search ends here)
            raise
        except _FamilyCap:
            rec.update(reason=f"family cap {caps.get(fam)} compiles reached", reject="family_cap")
            tried.discard(h)   # not decided: another family proposing the same proof may still read it
            raise
        finally:
            rec["compiles"] = spent[0] - n_start
            if family:
                fam_spent[family] = fam_spent.get(family, 0) + rec["compiles"]

    ex = (meter.ref_hb / row["proof_length"]) if getattr(meter, "ref_hb", None) and row.get("proof_length") else None

    ctx_memo: dict = {}

    def fam_ctx(base, fam=None):
        c = {"source": row.get("source"), "pins": list(getattr(meter, "versions", None) or [])}
        cs = (inc["reading"] or {}).get("seconds")
        if isinstance(cs, (int, float)) and cs > 0:
            c["compile_s"] = cs
        c.update(ctx or {})
        if fam is not None:   # R3: this family's own keys and op allow-list
            c.update(dict((family_ctx or {}).get(fam) or {}))
            if fam in allow_l:
                c["ops"] = list(allow_l[fam])
        if ctx_fn is not None:   # once per incumbent (a profiler's own compiles are the caller's, not this row's budget)
            h = sha(base)
            if h not in ctx_memo:
                ctx_memo[h] = dict(ctx_fn(base) or {})
            c.update(ctx_memo[h])
        return c

    def prep(it, lab, base):
        """A generated item rebased onto the incumbent: (label, fop, text, key), or None after logging it stale / cached."""
        label, fop = it["label"], _fop(lab, it.get("op"))
        text = rebase(base, it["text"], inc["proof"])
        if text is None:
            decisions.append({"op": lab, "label": label, "banked": False, "reason": "stale: its block changed under an earlier bank",
                              "family": lab, "fop": fop, "reject": "stale"})
            return None
        key = edit_key(fop, inc["proof"], text.strip()) if ph["fcache"] else None
        if key is not None and key in failed_keys and sha(text) not in tried:
            decisions.append({"op": lab, "label": label, "sha": sha(text), "banked": False, "family": lab, "fop": fop,
                              "reason": "cached: the same edit of an unchanged region failed earlier", "reject": "cached", "compiles": 0})
            return None
        return label, fop, text, key

    def extra_of(it, label):
        extra = {k_: it[k_] for k_ in ("cost", "span") if k_ in it}
        if it.get("full") and it["full"] != label:
            extra["note"] = it["full"][:300]
        return extra

    def try_one(it, lab, label, fop, text, key, stt, screen_v=None):
        before = inc["proof"]
        extra = extra_of(it, label)
        if screen_v:
            extra["screen"] = screen_v
        tm = time.time()
        try:
            ok = attempt(lab, label, text, family=lab, fop=fop, timeout=it.get("timeout_s"), extra=extra or None)
        finally:
            if ph["phase"]:
                stt["measure_seconds"] = stt.get("measure_seconds", 0.0) + time.time() - tm
        if not ok:
            failed_edits.append((before, text))
            if last[0] is None:
                stt["visited"] += 1
            elif key is not None and last[0].get("reject") in CACHEABLE:
                failed_keys.add(key)

    def screened_loop(items, lab, base, stt, scr):
        """The tool phase's loop: chunks of screen_k candidates rebased onto the incumbent, one batch screen each (cached by hash), then
        the copies that compiled (or that the screen could not judge) through attempt() in order; after a bank inside a chunk the rest
        of it is rebased onto the new incumbent and screened again."""
        from harness.batch_screen import hb_bound

        def need(n):
            if over_time():
                raise _Budget(ph["time_msg"])
            if not afford(n):
                raise _Budget
            cap = caps.get(lab)
            if cap is not None and fam_spent.get(lab, 0) + n > cap:
                raise _FamilyCap(lab)

        def charge(n):
            spent[0] += n
            fam_spent[lab] = fam_spent.get(lab, 0) + n
            stt["screen_compiles"] = stt.get("screen_compiles", 0) + n
            stt["screen_batches"] = stt.get("screen_batches", 0) + 1
        queue = list(items)
        while queue:
            chunk = []
            while queue and len(chunk) < max(1, int(screen_k)):
                it = queue.pop(0)
                p = prep(it, lab, base)
                if p is None:
                    continue
                label, fop, text, key = p
                text = text.strip()
                h = sha(text)
                if h in tried or any(c[4] == h for c in chunk):   # visited (attempt() would skip it the same way)
                    failed_edits.append((inc["proof"], text))
                    stt["visited"] += 1
                    continue
                chunk.append((it, label, fop, text, h, key))
            if not chunk:
                break
            ts = time.time()
            try:
                v = scr.screen([{"key": c[4], "text": c[3], "timeout_s": c[0].get("timeout_s")} for c in chunk], need=need, charge=charge,
                               hb_cap=hb_bound(meter.metrics, inc["reading"]), compile_s=(inc["reading"] or {}).get("seconds"),
                               control=inc["proof"])
            except _Budget:
                decisions.append({"op": lab, "banked": False, "reason": f"{lab}: budget reached while screening {len(chunk)} candidate(s)"})
                raise
            except _FamilyCap:
                raise
            except Exception as e:  # noqa: BLE001  (a screen fault never costs the row: this chunk and the rest are measured unscreened)
                why = f"{type(e).__name__}: {str(e)[:160]}"
                decisions.append({"op": lab, "banked": False, "reason": f"{lab}: the batch screen failed ({why}); screening stops for this row"})
                log(f"end: batch screen failed ({why}); screening stops for this row")
                if hasattr(scr, "broken"):
                    scr.broken = f"the screen failed: {why}"
                for k_ in ("screen", "sweep_screen"):   # the screen that failed stops (the tool families' or the sweep's, L5)
                    if ph.get(k_) is scr:
                        ph[k_] = None
                v = {}
            finally:
                stt["screen_seconds"] = stt.get("screen_seconds", 0.0) + time.time() - ts
            inc0 = inc["sha"]
            for j, (it, label, fop, text, h, key) in enumerate(chunk):
                if inc["sha"] != inc0:
                    queue[:0] = [c[0] for c in chunk[j:]]
                    break
                vd = v.get(h) or {"verdict": "unscreened"}
                if vd["verdict"] in SCREEN_REJECT:
                    rec = {"op": lab, "label": label, "sha": h, "banked": False, "family": lab, "fop": fop, "compiled": False, "at": "batch",
                           "screen": vd["verdict"], "reject": SCREEN_REJECT[vd["verdict"]], "compiles": 0,
                           "reason": f"batch screen ({vd.get('batch')} in the file{', cached' if vd.get('cached') else ''}): "
                                     f"{str(vd.get('error') or '?')[:160]}", **extra_of(it, label)}
                    if it.get("timeout_s"):
                        rec["timeout_s"] = it["timeout_s"]
                    tried.add(h)
                    decisions.append(rec)
                    failed_edits.append((inc["proof"], text))
                    if key is not None and rec["reject"] in CACHEABLE:
                        failed_keys.add(key)
                    continue
                try_one(it, lab, label, fop, text, key, stt, screen_v=vd["verdict"])

    probe_memo: dict = {}

    def t3_probe(mod, base, lab, stt):
        """ctx keys {"suggestions", "suggestions_for"} for T3 on `base` (module docstring, "t3 suggest"), or None (no probe possible or
        it failed: T3 runs as without the flag). Budget and family-cap stops propagate."""
        key = sha(base)
        if key in probe_memo:
            return probe_memo[key]
        probe_memo[key] = None
        if not hasattr(mod, "suggest"):
            decisions.append({"op": "note", "banked": False, "reason": f"{lab} suggest skipped: {FAMILIES['t3']['module']} has no suggest()"})
            return None
        scr = ph["screen"] or screener
        if scr is None and hasattr(meter, "screener"):
            try:   # only its layout and compile path (screening may be off)
                scr = meter.screener(k=screen_k, max_depth=screen_depth, cache=None, log=log)
            except Exception:  # noqa: BLE001
                scr = None
        if getattr(scr, "broken", None):   # the incumbent's own copy failed in a batch file: the layout does not hold on this row
            decisions.append({"op": "note", "banked": False, "reason": f"{lab} suggest skipped: {scr.broken}"[:300]})
            return None
        L = scr._lay() if scr is not None and hasattr(scr, "_lay") else None
        if L is None:
            decisions.append({"op": "note", "banked": False, "reason": f"{lab} suggest skipped: no batch layout on this meter"})
            return None
        from harness.tools import t3_suggest as SG

        def need(n):
            if over_time():
                raise _Budget(ph["time_msg"])
            if not afford(n):
                raise _Budget
            cap = caps.get(lab)
            if cap is not None and fam_spent.get(lab, 0) + n > cap:
                raise _FamilyCap(lab)

        def charge(n):
            spent[0] += n
            fam_spent[lab] = fam_spent.get(lab, 0) + n
            stt["probe_compiles"] = stt.get("probe_compiles", 0) + n
            stt["probe_batches"] = stt.get("probe_batches", 0) + 1
        R = inc["reading"] or {}
        pst = stt.setdefault("probe", {})
        cb = SG.batch_compiler(statement, scr.compile_fn, L, hb_cap=SG.probe_hb_cap(R.get("heartbeats")), compile_s=R.get("seconds"),
                               timeout=int(getattr(scr, "timeout", 900) or 900), need=need, charge=charge, stats=pst, log=log)
        ts, c0 = time.time(), stt.get("probe_compiles", 0)
        try:
            sg = mod.suggest(base, statement, None, cb, ctx=fam_ctx(base, "t3"), stats=pst, log=log,
                             **_kwargs_for(mod.suggest, {"mode": "rule" if t3_suggest is True else t3_suggest}))
        except (_Budget, _FamilyCap):
            raise
        except Exception as e:  # noqa: BLE001  (a probe fault never costs the row: T3 runs without suggestions)
            why = f"{type(e).__name__}: {str(e)[:160]}"
            decisions.append({"op": "note", "banked": False, "reason": f"{lab} suggest failed ({why}); T3 runs without suggestions"})
            log(f"end: t3 suggest failed ({why})")
            return None
        finally:
            stt["probe_seconds"] = stt.get("probe_seconds", 0.0) + time.time() - ts
        per = "; ".join(f"`{t}` judged {B.get('judged', 0)} of {B.get('probes', 0)}"
                        + "".join(f", {w} {B[w]}" for w in ("timeout", "crash", "skipped", "hb_out") if B.get(w))
                        for t, B in (pst.get("by_tactic") or {}).items())   # review R3: what each probe tactic actually covered
        msg = (f"{lab} suggest (`{pst.get('fallback') or pst.get('tactic')}`{', fallback' if pst.get('fallback') else ''}): "
               f"{len(sg)} span(s) with {sum(len(v) for v in sg.values())} suggestion(s); {stt.get('probe_compiles', 0) - c0} probe "
               f"compile(s), {time.time() - ts:.0f} s" + (f" ({per})" if per else ""))
        decisions.append({"op": "note", "banked": False, "reason": msg})
        log(f"end: {msg}")
        probe_memo[key] = {"suggestions": sg, "suggestions_for": SG.proof_key(base)} if sg else None
        return probe_memo[key]

    def t4_probe(mod, base, lab, stt):
        """ctx keys {"t4_probe", "t4_probe_for"} for T4 on `base` (module docstring, "t4 probe"), or None (no probe possible or it
        failed: T4 then proposes only its bare forms). Budget and family-cap stops propagate."""
        key = ("t4", sha(base))
        if key in probe_memo:
            return probe_memo[key]
        probe_memo[key] = None
        if not hasattr(mod, "probe"):
            decisions.append({"op": "note", "banked": False, "reason": f"{lab} probe skipped: {FAMILIES['t4']['module']} has no probe()"})
            return None
        scr = ph["screen"] or screener
        if scr is None and hasattr(meter, "screener"):
            try:   # only its layout and compile path (screening may be off)
                scr = meter.screener(k=screen_k, max_depth=screen_depth, cache=None, log=log)
            except Exception:  # noqa: BLE001
                scr = None
        if getattr(scr, "broken", None):
            decisions.append({"op": "note", "banked": False, "reason": f"{lab} probe skipped: {scr.broken}"[:300]})
            return None
        L = scr._lay() if scr is not None and hasattr(scr, "_lay") else None
        if L is None:
            decisions.append({"op": "note", "banked": False, "reason": f"{lab} probe skipped: no batch layout on this meter"})
            return None
        from harness.tools import t3_suggest as SG

        def need(n):
            if over_time():
                raise _Budget(ph["time_msg"])
            if not afford(n):
                raise _Budget
            cap = caps.get(lab)
            if cap is not None and fam_spent.get(lab, 0) + n > cap:
                raise _FamilyCap(lab)

        def charge(n):
            spent[0] += n
            fam_spent[lab] = fam_spent.get(lab, 0) + n
            stt["probe_compiles"] = stt.get("probe_compiles", 0) + n
            stt["probe_batches"] = stt.get("probe_batches", 0) + 1
        R = inc["reading"] or {}
        pst = stt.setdefault("probe", {})
        cb = SG.batch_compiler(statement, scr.compile_fn, L, hb_cap=mod.probe_hb_cap(R.get("heartbeats")), compile_s=R.get("seconds"),
                               timeout=int(getattr(scr, "timeout", 900) or 900), k=getattr(mod, "PROBE_K", SG.PROBE_K), need=need,
                               charge=charge, stats=pst.setdefault("batch", {}), log=log,
                               max_files=getattr(mod, "PROBE_MAX_FILES", SG.PROBE_MAX_FILES))
        ts, c0 = time.time(), stt.get("probe_compiles", 0)
        p0 = {c: pst.get(c, 0) for c in ("sites", "verified", "round2")}   # pst sums over the row's probes; the note is this call's
        try:
            got = mod.probe(base, statement, cb, ctx=fam_ctx(base, lab), stats=pst, log=log)
        except (_Budget, _FamilyCap):
            raise
        except Exception as e:  # noqa: BLE001  (a probe fault never costs the row: T4 runs without names)
            why = f"{type(e).__name__}: {str(e)[:160]}"
            decisions.append({"op": "note", "banked": False, "reason": f"{lab} probe failed ({why}); T4 proposes bare forms only"})
            log(f"end: t4 probe failed ({why})")
            return None
        finally:
            stt["probe_seconds"] = stt.get("probe_seconds", 0.0) + time.time() - ts
        d = {c: pst.get(c, 0) - p0[c] for c in p0}
        msg = (f"{lab} probe: {d['sites']} site(s), {d['verified']} verified, round 2 {d['round2']}; "
               f"{stt.get('probe_compiles', 0) - c0} probe compile(s), {time.time() - ts:.0f} s")
        decisions.append({"op": "note", "banked": False, "reason": msg})
        log(f"end: {msg}")
        probe_memo[key] = got or None
        return probe_memo[key]

    def env_query(mod, base, lab, stt):
        """b71 (c2): ctx keys of a search family whose module has query() (module docstring, "final families"): its env query on `base`,
        plain compiles after the row's file prefix through the meter's path (Meter.command), each charged as a compile to the tool phase
        and to the family's cap. None when the meter has no command() or the query failed (the family then proposes nothing). Budget and
        family-cap stops propagate."""
        key = ("q", lab, sha(base))
        if key in probe_memo:
            return probe_memo[key]
        probe_memo[key] = None
        if not hasattr(meter, "command"):
            decisions.append({"op": "note", "banked": False, "reason": f"{lab} query skipped: this meter has no command()"})
            return None

        def need(n):
            if over_time():
                raise _Budget(ph["time_msg"])
            if not afford(n):
                raise _Budget
            cap = caps.get(lab)
            if cap is not None and fam_spent.get(lab, 0) + n > cap:
                raise _FamilyCap(lab)

        def run(text, version=None):
            need(1)
            r, n = meter.command(text, version, timeout=getattr(mod, "QUERY_TIMEOUT", None))
            spent[0] += int(n)
            fam_spent[lab] = fam_spent.get(lab, 0) + int(n)
            stt["probe_compiles"] = stt.get("probe_compiles", 0) + int(n)
            return r
        pst = stt.setdefault("probe", {})
        ts, c0 = time.time(), stt.get("probe_compiles", 0)
        try:
            got = mod.query(base, statement, run, versions=list(getattr(meter, "versions", None) or []), ctx=fam_ctx(base, lab), stats=pst,
                            log=log)
        except (_Budget, _FamilyCap):
            raise
        except Exception as e:  # noqa: BLE001  (a query fault never costs the row: the family proposes nothing)
            why = f"{type(e).__name__}: {str(e)[:160]}"
            decisions.append({"op": "note", "banked": False, "reason": f"{lab} query failed ({why}); the family proposes nothing"})
            errs = pst.setdefault("errors", {})
            errs[f"query_fault:{type(e).__name__}"] = errs.get(f"query_fault:{type(e).__name__}", 0) + 1
            log(f"end: {lab} query failed ({why})")
            return None
        finally:
            stt["query_seconds"] = stt.get("query_seconds", 0.0) + time.time() - ts
        qs = pst.get("query") or {}
        msg = (f"{lab} query: {qs.get('ids', 0)} identifier(s), {qs.get('used', 0)} resolved, {qs.get('vars', 0)} variant(s), "
               f"{qs.get('class_vars', 0)} in a class namespace; {stt.get('probe_compiles', 0) - c0} compile(s), {time.time() - ts:.0f} s"
               + (f" ({qs['skip']})" if qs.get("skip") else ""))
        decisions.append({"op": "note", "banked": False, "reason": msg[:300]})
        log(f"end: {msg}")
        probe_memo[key] = got or None
        return probe_memo[key]

    wbh = {"wb": None, "err": None, "own": False}   # T5's workbench: started at its first search, closed when the tool phase ends

    def t5_workbench():
        if wbh["wb"] is not None or wbh["err"] is not None:
            return wbh["wb"]
        try:
            if workbench is not None and not callable(workbench):
                wbh["wb"] = workbench
            elif workbench is not None:
                wbh["wb"], wbh["own"] = workbench(row, meter), True
            else:
                from harness.workbench import Workbench
                from harness.tools import t5_joint as T5
                vs = list(getattr(meter, "versions", None) or [])
                wbh["wb"] = Workbench(row, version=vs[0] if vs else None, heartbeats=getattr(meter, "heartbeats", None) or {},
                                      workers=T5.WORKERS, scratch=getattr(meter, "scratch", None), log=log)
                wbh["own"] = True
        except Exception as e:  # noqa: BLE001  (no workbench: T5 proposes its site variants unscreened)
            wbh["err"] = f"{type(e).__name__}: {str(e)[:200]}"
        return wbh["wb"]

    def t5_probe(mod, base, lab, stt, fam="t5", pre_ctx=None):
        """ctx keys {"<fam>_found", "<fam>_found_for"} for a search family on `base` (module docstring, "t5 search"; t8 / t11 follow the
        same contract), or None (no workbench, the row's search time used up, or the search failed: the family then proposes its
        variants unscreened). pre_ctx (b71, c2): the env query's keys, merged into the search's ctx and given to its precheck."""
        key = (fam, sha(base))
        if key in probe_memo:
            return probe_memo[key]
        probe_memo[key] = None
        if not hasattr(mod, "search"):
            decisions.append({"op": "note", "banked": False, "reason": f"{lab} search skipped: {FAMILIES[fam]['module']} has no search()"})
            return None
        sb = (search_budgets or {}).get(fam)
        mc = None   # max_checks of this search: passed only under a count budget (the call is otherwise the one it always was)
        if sb:   # L5 count budget: the row's workbench readings over all its searches; the wall is only the backstop
            used = _search_used(stt.get("probe"))
            n_left = int(sb["checks"]) - used
            if n_left <= 0:
                decisions.append({"op": "note", "banked": False, "reason": f"{lab} search skipped: the row's search readings are used up "
                                                                            f"({used} of {int(sb['checks'])})"})
                return None
            mc = min(int(getattr(mod, "MAX_CHECKS", n_left)), n_left)
            wall = float(sb.get("backstop_s") or SEARCH_BACKSTOP_FACTOR * float(getattr(mod, "SEARCH_SECONDS", 210.0)))
            left = wall - float(stt.get("probe_seconds", 0.0))
            if left < 5.0:
                decisions.append({"op": "note", "banked": False, "reason": f"{lab} search skipped: the row's search wall backstop "
                                                                            f"({wall:g} s) is used up"})
                return None
        else:
            left = float(getattr(mod, "SEARCH_SECONDS", 210.0)) - float(stt.get("probe_seconds", 0.0))
            if left < 5.0:
                decisions.append({"op": "note", "banked": False, "reason": f"{lab} search skipped: the row's search time is used up"})
                return None
        ts = time.time()
        # b63 speed (module docstring, "speed"): a module whose search_precheck() says the search stops before any workbench reading is
        # searched without starting the row's workbench (the load is the row's file prefix, 2-15 s); a search that touches it anyway
        # gets its counters back and runs again on a started workbench, its deadline counted from the start as before
        lazy = (_search_precheck(mod, base, statement, pre_ctx) if lazy_workbench and wbh["wb"] is None and wbh["err"] is None
                and (workbench is None or callable(workbench)) else None)
        pst = stt.setdefault("probe", {}) if lazy else None   # (created after the workbench start otherwise, as before)
        snap = copy.deepcopy(pst) if lazy else None

        def call(wb_):
            dl = time.time() + left
            if ph["deadline"] is not None:
                dl = min(dl, ph["deadline"])
            c = dict(fam_ctx(base, lab), t5_family_ops={f: list(v) for f, v in allow_l.items()}, **(pre_ctx or {}))
            return mod.search(base, statement, wb_, meter_reading=inc["reading"], exchange=ex, ctx=c, stats=stt.setdefault("probe", {}),
                              log=log, deadline=dl, **({"max_checks": mc} if mc is not None else {}))
        try:
            if lazy:
                try:
                    got = call(_UNSTARTED_WB)
                    wbh["not_needed"] = wbh.get("not_needed", 0) + 1
                except _NeedWorkbench:
                    pst.clear()
                    pst.update(snap)
                    wbh["lazy_misses"] = wbh.get("lazy_misses", 0) + 1
                    lazy = None
            if not lazy:
                wb = t5_workbench()
                if wb is None:
                    decisions.append({"op": "note", "banked": False, "reason": f"{lab} search skipped: no workbench ({wbh['err']}); its site "
                                                                                "variants go unscreened to the batch screen"[:300]})
                    return None
                pst = stt.setdefault("probe", {})
                got = call(wb)
        except Exception as e:  # noqa: BLE001  (a search fault never costs the row: T5 proposes its site variants unscreened)
            pst = stt.setdefault("probe", {})
            why = f"{type(e).__name__}: {str(e)[:160]}"
            decisions.append({"op": "note", "banked": False, "reason": f"{lab} search failed ({why}); site variants unscreened"})
            errs = pst.setdefault("errors", {})   # logging contract §1: a search fault is an error class of the family's stats
            errs[f"search_fault:{type(e).__name__}"] = errs.get(f"search_fault:{type(e).__name__}", 0) + 1
            log(f"end: {lab} search failed ({why})")
            return None
        finally:
            stt["probe_seconds"] = stt.get("probe_seconds", 0.0) + time.time() - ts
        n = len((got or {}).get(f"{fam}_found") or [])
        msg = (f"{lab} search: {n} survivor(s) of {pst.get('checks', pst.get('readings', 0))} workbench reading(s) so far on this row "
               f"({time.time() - ts:.0f} s this search, {stt['probe_seconds']:.0f} s on this row)")
        decisions.append({"op": "note", "banked": False, "reason": msg})
        log(f"end: {msg}")
        probe_memo[key] = got if got else None
        return probe_memo[key]

    def run_family(fam, npass, label=None):
        """One pass of one family on the current incumbent (`label`: its name in the records, "sweep+" for the tool phase's sweep).
        True when it ran (False: skipped, None: its generator failed)."""
        lab = label or fam
        if lab in exhausted:
            return False
        stt = stats.setdefault(lab, {"generated": 0, "visited": 0, "passes": 0, "seconds": 0.0})
        mod, err = _load_family(fam)
        mname = FAMILIES[fam]["module"]
        if mod is None or not hasattr(mod, "candidates"):
            note = f"{lab} skipped: {mname} is absent ({err})" if mod is None else f"{lab} skipped: {mname} has no candidates()"
            decisions.append({"op": lab, "banked": False, "reason": note})
            log(f"end: {note}")
            exhausted.add(lab)
            stt["skipped"] = note
            return False
        base = inc["proof"]
        t1 = time.time()
        b0 = banks[0]
        try:
            extra_ctx = None
            if t3_suggest and fam == "t3":   # R3, opt-in: Lean's suggestions at T3's spans (module docstring, "t3 suggest")
                try:
                    extra_ctx = t3_probe(mod, base, lab, stt)
                except _FamilyCap:
                    exhausted.add(lab)
                    stt["capped"] = True
                    note = f"{lab}: family cap {caps.get(lab)} compiles reached while probing; its candidates are skipped for this row"
                    decisions.append({"op": lab, "banked": False, "reason": note})
                    log(f"end: {note}")
                    return True
            if fam in SEARCH_FAMILIES:   # opt-in families: the search on the workbench (module docstring, "t5 search"; t8, t11 likewise)
                pre = None
                if hasattr(mod, "query"):   # b71 c2: the env query first (its compiles charged like a probe's)
                    try:
                        pre = env_query(mod, base, lab, stt)
                    except _FamilyCap:
                        exhausted.add(lab)
                        stt["capped"] = True
                        note = f"{lab}: family cap {caps.get(lab)} compiles reached while querying; its candidates are skipped for this row"
                        decisions.append({"op": lab, "banked": False, "reason": note})
                        log(f"end: {note}")
                        return True
                    if pre is None:   # no query: nothing to propose (the module's candidates() needs the env)
                        decisions.append({"op": lab, "banked": False, "reason": f"{lab}: no env query on this proof; nothing proposed"})
                        stt["passes"] += 1
                        return True
                found = t5_probe(mod, base, lab, stt, fam, pre_ctx=pre)
                extra_ctx = dict(pre, **(found or {})) if pre else found
            if fam == "t4":   # opt-in family: Lean's names for its nameless forms (module docstring, "t4 probe")
                try:
                    extra_ctx = t4_probe(mod, base, lab, stt)
                except _FamilyCap:
                    exhausted.add(lab)
                    stt["capped"] = True
                    note = f"{lab}: family cap {caps.get(lab)} compiles reached while probing; its candidates are skipped for this row"
                    decisions.append({"op": lab, "banked": False, "reason": note})
                    log(f"end: {note}")
                    return True
            dropped = 0
            try:
                if fam == "sweep":   # the B62b call (+ ctx since b63 item 4: the row's environment for hr:genform; ignored by an older sweep)
                    raw = mod.candidates(base, statement, **_kwargs_for(mod.candidates, {"exchange": ex, "ctx": fam_ctx(base)}))
                else:
                    kw = {"exchange": ex, "ctx": fam_ctx(base, fam)}
                    if extra_ctx:
                        kw["ctx"] = dict(kw["ctx"], **extra_ctx)
                    if max_per_op is not None:
                        kw["max_per_op"] = int(max_per_op)
                    raw = mod.candidates(base, statement, **_kwargs_for(mod.candidates, kw))
                items = _items(raw, base, statement, default=lab)
                if fam in allow and fam != "sweep":   # R3: the family's op allow-list (also applied to a generator that ignores ctx["ops"])
                    kept = [it for it in items if _fop(fam, it.get("op")) in allow[fam]]
                    dropped, items = len(items) - len(kept), kept
                    stt["ops_dropped"] = stt.get("ops_dropped", 0) + dropped
            except Exception as e:  # noqa: BLE001
                decisions.append({"op": lab, "banked": False, "reason": f"{lab} pass {npass} failed: {type(e).__name__}: {str(e)[:160]}"})
                return None
            stt["passes"] += 1
            stt["generated"] += len(items)
            for b0_, t0_ in failed_edits:   # review 2026-10-21: an earlier pass's failed edit, carried onto the new incumbent, is not retried
                r0 = rebase(b0_, t0_, inc["proof"])
                if r0 is not None:
                    tried.add(sha(r0.strip()))
            decisions.append({"op": "note", "banked": False, "reason": f"{lab} pass {npass}: {len(items)} candidate(s)"
                              + (f" ({dropped} outside the op allow-list dropped)" if dropped else "")})
            if fam != "sweep":
                scr = ph["screen"]
            elif screen_sweep:   # L5: the sweep screened too (its own screener in the sweep phase; sweep+ the tool phase's when it has one)
                scr = ph["screen"] if ph["phase"] and ph["screen"] is not None else ph["sweep_screen"]
            else:
                scr = None   # the sweep path never screens (the default)
            if fam in SEARCH_FAMILIES and extra_ctx and (f"{fam}_found" in extra_ctx or not hasattr(mod, "query")):
                scr = None   # the workbench search already read every survivor on the primary pin
            try:
                if scr is not None:
                    screened_loop(items, lab, base, stt, scr)
                else:
                    for it in items:
                        p = prep(it, lab, base)
                        if p is not None:
                            try_one(it, lab, *p, stt)
            except _FamilyCap:
                exhausted.add(lab)
                stt["capped"] = True
                note = f"{lab}: family cap {caps.get(lab)} compiles reached; its other candidates are skipped for this row"
                decisions.append({"op": lab, "banked": False, "reason": note})
                log(f"end: {note}")
            return True
        finally:
            stt["seconds"] += time.time() - t1
            if ph["phase"]:   # the tool phase: the family's running totals (screened / passed / measured / banked, seconds)
                F = family_summary([d for d in decisions if d.get("family") == lab], {}).get(lab, {})
                log(f"end: {lab} after pass {npass}: generated {stt['generated']}; screened {F.get('screened', 0)} in "
                    f"{stt.get('screen_batches', 0)} batch(es) ({stt.get('screen_seconds', 0.0):.0f} s): passed {F.get('screen_passed', 0)}, "
                    f"failed {F.get('screen_failed', 0)}, unknown {F.get('screen_unknown', 0)}; measured {F.get('measured', 0)} "
                    f"({stt.get('measure_seconds', 0.0):.0f} s); banked {F.get('banked', 0)} ({banks[0] - b0} this pass)"
                    + (f"; probes {stt['probe_compiles']} compile(s) ({stt.get('probe_seconds', 0.0):.0f} s)" if stt.get("probe_compiles") else ""))

    def run_crossover():
        others = [h for h in sorted(confirmed, key=lambda h: -confirmed[h]["score_exact"]) if h != inc["sha"]]
        others += [h for h in valid if h not in confirmed and h != inc["sha"]]
        parents = [inc["proof"]] + [pool[h]["proof"] for h in others][:CROSS_TOP - 1]
        if len(parents) < 2:
            decisions.append({"op": "crossover", "banked": False, "reason": "fewer than two distinct compiling candidates"})
            return
        base = inc["proof"]
        kids = splices(parents, statement)[:CROSS_MAX]
        decisions.append({"op": "note", "banked": False, "reason": f"crossover: {len(kids)} child(ren) of {len(parents)} parents"})
        stt = stats.setdefault("crossover", {"generated": 0, "visited": 0, "passes": 0, "seconds": 0.0})
        stt["generated"] += len(kids)
        stt["passes"] += 1
        t1 = time.time()
        try:
            for label, text in kids:
                text = rebase(base, text, inc["proof"])
                if text is None:
                    decisions.append({"op": "crossover", "label": label, "banked": False, "reason": "stale: its block changed under an earlier bank",
                                      "family": "crossover", "fop": "crossover", "reject": "stale"})
                    continue
                attempt("crossover", label, text, family="crossover", fop="crossover")
                if last[0] is None:
                    stt["visited"] += 1
        except _FamilyCap:
            stt["capped"] = True
            decisions.append({"op": "crossover", "banked": False, "reason": f"crossover: family cap {caps.get('crossover')} compiles reached"})
        finally:
            stt["seconds"] += time.time() - t1

    def run_pass(npass, families):
        ran = False
        for fam in families:
            if over_time():
                raise _Budget(ph["time_msg"])
            ran = bool(run_family(fam, npass)) or ran
        return ran

    # ---- the sweep phase: exactly the control's stage (the families of the sweep phase are the sweep alone) ----
    sweep_fams = tuple(f for f in fams if f == "sweep")
    sw_snap = sw_obj = None
    if screen_sweep and sweep_fams:   # L5: the sweep's batch screen (the tool phase's screener when one is injected, else the meter's)
        try:
            ph["sweep_screen"] = screener if screener is not None else (
                meter.screener(k=screen_k, max_depth=screen_depth, cache=screen_cache, log=log) if hasattr(meter, "screener") else None)
        except Exception as e:  # noqa: BLE001  (no screen: the sweep is measured as without it)
            decisions.append({"op": "note", "banked": False, "reason": f"sweep screen unavailable ({type(e).__name__}: {str(e)[:120]}); "
                                                                        "the sweep is measured unscreened"})
            ph["sweep_screen"] = None
        sw_obj = ph["sweep_screen"]
        if sw_obj is not None and hasattr(sw_obj, "stats"):
            sw_snap = dict(sw_obj.stats)
    try:
        start = inc["sha"]
        ran = run_pass(1, sweep_fams)
        if crossover:
            run_crossover()
        for npass in range(2, max(1, int(passes)) + 1):
            if not (ran and inc["sha"] != start):   # greedy: once more on the new incumbent
                break
            if not afford(meter.cost(False)):
                raise _Budget
            start = inc["sha"]
            ran = run_pass(npass, sweep_fams)
    except _Budget as e:
        decisions.append({"op": "budget", "banked": False, "reason": (f"{e} ({spent[0]} compiles, {time.time() - t0:.0f} s)" if str(e) else
                                                                      f"max_compiles {max_compiles} reached ({spent[0]} spent)")})
    phases = {"sweep": {"compiles": spent[0], "seconds": round(time.time() - t0, 1), "banks": banks[0], "slot_wait_s": round(waited() - w0, 1)}}
    if backstop_s:
        phases["sweep"]["budget"] = {"compiles": max_compiles, "seconds": max_seconds, "backstop_s": backstop_s}
    if sw_snap is not None:   # this phase's share of the sweep screen's counters
        phases["sweep"]["screen"] = _stats_since(sw_obj.stats, sw_snap)

    # ---- the tool phase: its own budget, cheap families first, a sweep pass after a family pass that banked ----
    if tool_fams:
        iB, tB, cB, bB, wB = len(decisions), time.time(), spent[0], banks[0], waited()
        tmc = int(max_compiles if tools_max_compiles is None else tools_max_compiles)
        tms = max_seconds if tools_max_seconds is None else tools_max_seconds
        tbs = backstop_s if tools_backstop_s is None else tools_backstop_s   # L5: the tool phase's wall backstop (None: none)
        scr = None
        if screen is None or screen:
            scr = screener
            if scr is None and hasattr(meter, "screener"):
                scr = meter.screener(k=screen_k, max_depth=screen_depth, cache=screen_cache, log=log)
        t_snap = dict(scr.stats) if scr is not None and scr is sw_obj and hasattr(scr, "stats") else None   # one screener, two phases
        tdl, tmsg = _stop_at(_wall(tB, tms, "tools_max_seconds", tbs, "tool"), stop_at)
        ph.update(phase="tools", max=tmc, base=spent[0], deadline=tdl, screen=scr,
                  fcache=True if fail_cache is None else bool(fail_cache), time_msg=tmsg,
                  count_msg=f"tools_max_compiles {tmc} reached")
        decisions.append({"op": "note", "banked": False, "reason": f"tool phase: {', '.join(tool_fams)}; budget {tmc} compiles"
                          + (f", {tms:g} s" if tms else "") + (f", wall backstop {tbs:g} s" if tbs else "")
                          + (f"; batch screening, {int(screen_k)} per file" if scr is not None else "; no batch screening")})
        try:
            for npass in range(1, max(1, int(passes)) + 1):
                start = inc["sha"]
                ran = False
                for fam in tool_fams:
                    if fam in FINAL_FAMILIES:   # b71: a final family runs once, after these passes (below)
                        continue
                    if over_time():
                        raise _Budget(ph["time_msg"])
                    b0 = banks[0]
                    ran = bool(run_family(fam, npass)) or ran
                    if banks[0] > b0 and "sweep" in fams:   # the sweep once more on what the tool banked, inside the tool budget
                        if over_time():
                            raise _Budget(ph["time_msg"])
                        run_family("sweep", npass, label="sweep+")
                if not (ran and inc["sha"] != start):
                    break
                if npass < max(1, int(passes)) and not afford(meter.cost(False)):
                    raise _Budget
            for fam in tool_fams:   # b71 final families (module docstring): once, on the incumbent the passes above left
                if fam not in FINAL_FAMILIES:
                    continue
                if over_time():
                    raise _Budget(ph["time_msg"])
                run_family(fam, 1)
        except _Budget as e:
            decisions.append({"op": "budget", "banked": False, "reason": f"{str(e) or ph['count_msg']} (tool phase: {spent[0] - cB} compiles, "
                                                                          f"{time.time() - tB:.0f} s)"})
        finally:   # T5's workbench (module docstring, "t5 search"): closed here when this call started it
            if wbh["wb"] is not None:
                try:
                    wbh["info"] = wbh["wb"].info() if hasattr(wbh["wb"], "info") else None
                    if wbh["own"] and hasattr(wbh["wb"], "close"):
                        wbh["wb"].close()
                except Exception:  # noqa: BLE001
                    pass
        for d in decisions[iB:]:
            d.setdefault("phase", "tools")
        phases["tools"] = {"compiles": spent[0] - cB, "seconds": round(time.time() - tB, 1), "banks": banks[0] - bB,
                           "slot_wait_s": round(waited() - wB, 1),
                           "budget": dict({"compiles": tmc, "seconds": tms}, **({"backstop_s": tbs} if tbs else {})),
                           "screen": (dict(scr.stats) if t_snap is None else _stats_since(scr.stats, t_snap))
                           if scr is not None and hasattr(scr, "stats") else None}
        if wbh["wb"] is not None or wbh["err"] is not None:
            phases["tools"]["workbench"] = wbh.get("info") if wbh["wb"] is not None else {"error": wbh["err"]}
            if isinstance(phases["tools"]["workbench"], dict) and (wbh.get("not_needed") or wbh.get("lazy_misses")):
                phases["tools"]["workbench"] = dict(phases["tools"]["workbench"], not_needed=wbh.get("not_needed", 0),
                                                    lazy_misses=wbh.get("lazy_misses", 0))
        elif wbh.get("not_needed") or wbh.get("lazy_misses"):   # b63 speed: every search on this row stopped before a reading
            phases["tools"]["workbench"] = {"started": False, "not_needed": wbh.get("not_needed", 0), "lazy_misses": wbh.get("lazy_misses", 0)}
        if phases["tools"]["screen"]:
            phases["tools"]["screen"]["seconds"] = round(phases["tools"]["screen"].get("seconds", 0.0), 1)
    R = inc["reading"]
    metrics = {k_: R.get(k_) for k_ in ("score", "score_exact", "tokens", "heartbeats", "L", "H", "Z", "compat", "meter")}
    log(f"end: {inc['op']} {metrics['score_exact']:.4f} ({banks[0]} bank(s), {spent[0]} compiles)")
    return {"proof": inc["proof"], "metrics": metrics, "stage": inc["op"], "picked_from": inc["origins"], "decisions": decisions,
            "compiles": spent[0], "measured": measured, "meter": path, "self_test": st, "seconds": round(time.time() - t0, 1),
            "families": family_summary(decisions, stats), "tools": list(fams), "phases": phases}


# ------------------------------------------------------------------------------------------------------------------------------- CLI
def checkpoint_bests_from(steps: dict, min_gain: float = 0.05) -> dict:
    """The router's best at each step, in step order (router.fold: a later item replaces the best only when it is verified and higher by
    more than the checkpoint bar): {step: item}, distinct proofs only."""
    cur, out = None, {}
    for key, st in (steps or {}).items():
        it = (st or {}).get("item") or {}
        if not isinstance(it.get("proof"), str) or it.get("verified", True) is False or _num(it.get("score")) is None:
            continue
        if cur is None or float(it["score"]) > float(cur["score"]) + min_gain - 1e-9:
            cur = it
            if all(sha(v["proof"]) != sha(it["proof"]) for v in out.values()):
                out[key] = it
    return out


def _safe(n: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", n)


POOL_FILES = ("pool.jsonl", "bank.jsonl")   # the run pool (agent.py --pool) and the per-row bank (harness/bank.py, b63 item 1)


def pool_files(name: str, steps: dict) -> list[Path]:
    """The run pools and banks of a row: next to the ladder's state.json (input@k state_path) and in every re-plan root."""
    fs = []
    for st in (steps or {}).values():
        sp = ((st or {}).get("item") or {}).get("state_path")
        if sp:
            fs += [Path(sp).parent / f for f in POOL_FILES]
        for r in ((st or {}).get("report") or {}).get("roots") or []:
            fs += [Path(r) / _safe(name) / f for f in POOL_FILES]
    return [f for f in dict.fromkeys(fs) if f.is_file()]


def read_pool(files) -> list[dict]:
    out = []
    for f in files:
        try:
            for l in Path(f).read_text().splitlines():
                try:
                    d = json.loads(l)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    out.append(d)
        except OSError:
            continue
    return out


CODE_FILES = ("harness/endstage.py", "harness/sweep.py", "harness/hb_rewrite.py", "harness/lint_delete.py", "harness/normalize.py",
              "harness/hb_polish.py", "harness/gap_rules.py", "harness/batch_screen.py", "harness/hb_tool_eval.py", "harness/workbench.py",
              "harness/tools/*.py",
              "harness/tools/tables/*.json", "scorer/*.py")


def code_identity(root: Path = ROOT) -> dict:
    """{"digest", "files" {path: sha256[:16]}, "git_head", "git_dirty"}: what produced a run's rows (module docstring, "resume").
    The digest covers the files of CODE_FILES (scorer tests excluded); git HEAD and the dirty flag are information only."""
    import subprocess
    files = {}
    for pat in CODE_FILES:
        for p in sorted(Path(root).glob(pat)):
            if p.is_file() and not p.name.startswith("test_"):
                files[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    head = dirty = None
    try:
        g = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20)
        head = g.stdout.strip() or None
        g = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", *sorted(files)], capture_output=True, text=True, timeout=20)
        dirty = bool(g.stdout.strip()) if g.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        pass
    return {"digest": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16], "files": files, "git_head": head,
            "git_dirty": dirty}


def config_diff(prev: dict, cur: dict) -> list[str]:
    """The end_config keys whose values differ between a run's earlier call and this one (families included; the code identity by its
    digest; the config file by its sha256 (R3: its path and parsed body are information); the resume-anyway history and git HEAD / dirty
    never count)."""
    def norm(c):
        c = {k_: v for k_, v in (c or {}).items() if k_ not in ("resumed_anyway", "config_file", "config_body")}
        c["code"] = (c.get("code") or {}).get("digest") if isinstance(c.get("code"), dict) else c.get("code")
        return c
    p, q = norm(prev), norm(cur)
    return sorted(k_ for k_ in set(p) | set(q) if p.get(k_) != q.get(k_))


def _rows_for(a, cfg: dict) -> tuple[dict, dict]:
    if a.rows:
        from harness.hb_tool_eval import load_dataset
        if not a.heartbeats:
            raise SystemExit("--rows needs --heartbeats")
        return load_dataset(a.rows, a.heartbeats)
    if cfg.get("set"):
        sys.path.insert(1, str(ROOT / "harness"))
        import hx_heldout as H
        S = H.Set(cfg["set"], cfg.get("arm") or "end")
        hbs = {}
        if S.hb_path.exists():
            hbs = {d["name"]: d["heartbeat"] for d in (json.loads(l) for l in S.hb_path.open() if l.strip())}
        from harness import leantools as LT
        return {**LT.ROWS, **{r["name"]: r for r in S.rows}}, {**LT.HBS, **hbs}
    from harness import leantools as LT
    return dict(LT.ROWS), dict(LT.HBS)


def end_kwargs(a) -> dict:
    """end_stage's family and budget arguments from the CLI namespace (defaults: the B62b stage)."""
    caps = getattr(a, "family_caps", None)
    return {"tools": tuple(getattr(a, "tools", None) or ()), "max_seconds": getattr(a, "max_seconds", None),
            "family_caps": caps if isinstance(caps, dict) else parse_caps(caps), "passes": getattr(a, "passes", PASSES),
            "max_per_op": getattr(a, "max_per_op", None), "fail_cache": getattr(a, "fail_cache", None),
            "tools_max_compiles": getattr(a, "tools_max_compiles", None), "tools_max_seconds": getattr(a, "tools_max_seconds", None),
            "screen": getattr(a, "screen", None), "screen_k": getattr(a, "screen_k", SCREEN_K),
            "t3_suggest": "rule" if getattr(a, "t3_suggest", False) is True else (getattr(a, "t3_suggest", False) or False), **_r3_kwargs(a),
            **_l5_kwargs(a)}


def _l5_kwargs(a) -> dict:
    """The L5 arguments of end_stage (module docstring, "count budgets"), only those set: none given, end_kwargs is the call it was."""
    kw = {}
    for k_ in ("backstop_s", "tools_backstop_s"):
        if getattr(a, k_, None) is not None:
            kw[k_] = float(getattr(a, k_))
    sb = getattr(a, "search_budgets", None)
    sb = sb if isinstance(sb, dict) else parse_search_budgets(sb)
    if sb:
        kw["search_budgets"] = sb
    if getattr(a, "screen_sweep", False):
        kw["screen_sweep"] = True
    return kw


def _r3_kwargs(a) -> dict:
    """The R3 arguments of end_stage besides t3_suggest, only those set (none given: end_kwargs is the R2 call)."""
    kw = {}
    fo = getattr(a, "family_ops", None)
    fo = fo if isinstance(fo, dict) else parse_ops(fo)
    if fo:
        kw["family_ops"] = fo
    fc = family_ctx_of(a)
    if fc:
        kw["family_ctx"] = fc
    if getattr(a, "screen_depth", None) is not None:
        kw["screen_depth"] = int(a.screen_depth)
    return kw


# ---- the frozen config file (R3; module docstring, "config")
CONFIG_DOC = ("name", "description")   # documentation keys (and every key starting with "_")
RUN_DESTS = frozenset({"run_dir", "rows", "heartbeats", "problems", "jobs", "anon", "out", "scratch", "resume_anyway", "config", "help",
                       "reuse_readings", "serial_self_test", "lazy_workbench"})

AUTO_JOBS_MAX, AUTO_JOBS_MIN, AUTO_JOBS_CORES_PER_ROW = 6, 2, 4   # --jobs auto (b63 speed): rows at once from the box's cores and load


def auto_jobs(cores: int | None = None, load1: float | None = None) -> int:
    """Rows at once for --jobs auto: min(AUTO_JOBS_MAX, cores // AUTO_JOBS_CORES_PER_ROW), reduced to the free cores ((cores - load1) //
    AUTO_JOBS_CORES_PER_ROW; a row = a Lean compile or a workbench of up to 3 worker threads, ~4 cores), never below AUTO_JOBS_MIN (the
    drivers' former fixed default) and never above the core rule. Priority between units is their CPUWeight (work-conserving), so a loaded
    box only lowers this count; memory is the unit's MemoryMax (plan ~8 GB per row: pass --jobs N when the unit is smaller)."""
    import os
    cores = int(cores if cores is not None else (os.cpu_count() or 1))
    if load1 is None:
        try:
            load1 = os.getloadavg()[0]
        except (OSError, AttributeError):
            load1 = 0.0
    by_cores = max(1, cores // AUTO_JOBS_CORES_PER_ROW)
    free = max(0.0, cores - float(load1))
    n = min(AUTO_JOBS_MAX, by_cores, int(free // AUTO_JOBS_CORES_PER_ROW))
    return max(min(AUTO_JOBS_MIN, by_cores, AUTO_JOBS_MAX), n)


def run_self_tests(meters: dict, order: list, seeds: dict, jobs: int, after=None, log=print) -> dict:
    """The run-start meter self-tests of the rows in `order` (b63 speed; module docstring, "speed"). The serial loop called
    meters[n].self_test(seeds[n]) row by row; this computes the same records with the compiles at once:
      1. which rows compile: the serial loop's cache rule replayed on the (source, pin) keys (a row compiles unless an earlier row or the
         resumed run tested every pin of it; a row with a statement or forbidden fault compiles nothing but still covers its keys);
      2. their (row, pin) pairs on `jobs` threads, each pin's direct and lake compile back to back as in the loop (the primary pin on the
         row's own meter, the others on a private meter: Meter._test_pin);
      3. every row's record assembled in `order` with Meter.self_test(seed, pin_results=...), so the run's tests, the first failing row's
         fallback reason, the seed readings and each record are what the serial loop writes; `after(n)` runs after each row (meter.json).
    A meter without _test_pin (a test double) or prefer="lake", jobs <= 1, or a pair that raised: that row's self_test runs as before.
    Returns {"rows", "compiled_rows", "pairs", "threads", "seconds"}."""
    t0 = time.time()
    covered = set(run_state()["tests"])
    need = []
    for n in order:
        m = meters[n]
        if getattr(m, "prefer", "direct") == "lake" or not hasattr(m, "_test_pin"):
            continue
        keys = {f"{m.row['source']}@{v}" for v in m.versions}
        if keys <= covered:
            continue
        covered |= keys
        if m._check(seeds[n].strip()) is None:
            need.append(n)
    pairs = [(n, v, i == 0) for n in need for i, v in enumerate(meters[n].versions)]
    threads = max(1, min(int(jobs), len(pairs)))
    res: dict = {}
    if threads > 1:
        from concurrent.futures import ThreadPoolExecutor
        pairs.sort(key=lambda p: -len(meters[p[0]].versions))   # rows with the most pins first (the longest row bounds the phase)
        with ThreadPoolExecutor(threads) as ex_:
            futs = {(n, v): (ex_.submit(meters[n]._test_pin, seeds[n].strip(), v, c, not c), c) for n, v, c in pairs}
        for (n, v), (f, c) in futs.items():
            try:
                rd, rl, k = f.result()
            except Exception as e:  # noqa: BLE001  (that row's self-test then runs as the serial loop runs it)
                log(f"[endstage] self-test pair {n} @ {v} raised {type(e).__name__}: {str(e)[:120]}; the row is tested serially")
                res[n] = None
                continue
            if n in res and res[n] is None:
                continue
            if not c:
                meters[n].compiles += k   # a private meter's compiles count on the row's meter, as in the serial loop
            res.setdefault(n, {})[v] = (rd, rl, k)
    for n in order:
        got = res.get(n)
        if got is not None and len(got) != len(meters[n].versions):
            got = None
        if got is None:
            meters[n].self_test(seeds[n])
        else:
            meters[n].self_test(seeds[n], pin_results=got)
        if after is not None:
            after(n)
    return {"rows": len(order), "compiled_rows": len(need), "pairs": len(pairs), "threads": threads if pairs else 0,
            "seconds": round(time.time() - t0, 1)}


def _jobs_arg(v: str):
    v = str(v).strip().lower()
    if v == "auto":
        return "auto"
    n = int(v)
    if n < 1:
        raise argparse.ArgumentTypeError("--jobs: 1 or more, or auto")
    return n


def _is_int(v, low=0):
    return isinstance(v, int) and not isinstance(v, bool) and v >= low


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0


def load_config(path) -> tuple[dict, dict]:
    """(values {argparse dest: value}, record {"config_sha256", "config_name", "config_file", "config_body"}) of a frozen config file;
    ValueError names the first key that is unknown or of the wrong type (module docstring, "config")."""
    p = Path(path)
    raw = p.read_bytes()
    try:
        cfg = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise ValueError(f"--config {p}: not a JSON file ({e})") from None
    if not isinstance(cfg, dict):
        raise ValueError(f"--config {p}: the file must hold one JSON object")
    v: dict = {}

    def cfg_get(key):
        d = cfg
        for part in key.split("."):
            d = d.get(part) if isinstance(d, dict) else None
        return d

    def bad(key, want):
        raise ValueError(f"--config {p}: {key} must be {want}, got {cfg_get(key)!r}")

    def sub(key, allowed):
        d = cfg_get(key)
        if d is None:
            return {}
        if not isinstance(d, dict):
            bad(key, "an object")
        extra = [k_ for k_ in d if k_ not in allowed and not str(k_).startswith("_")]
        if extra:
            raise ValueError(f"--config {p}: unknown key(s) {', '.join(f'{key}.{x}' for x in extra)} (known: {', '.join(allowed)})")
        return d

    def doc_free(d):   # nested objects ("caps", "ops", "ctx") may carry "_" documentation keys too
        return {k_: x for k_, x in d.items() if not str(k_).startswith("_")} if isinstance(d, dict) else d
    top = ("families", "sweep", "crossover", "k", "prefer", "budgets", "caps", "fail_cache", "screen", "ops", "opt_in", "t3_suggest", "ctx")
    unknown = [k_ for k_ in cfg if k_ not in top and k_ not in CONFIG_DOC and not str(k_).startswith("_")]
    if unknown:
        raise ValueError(f"--config {p}: unknown key(s) {', '.join(map(str, unknown))} (known: {', '.join(top + CONFIG_DOC)}, _*)")
    if "families" in cfg:
        f = cfg["families"]
        if not (isinstance(f, list) and all(isinstance(x, str) for x in f)):
            bad("families", "a list of tool family names")
        v["tools"] = tuple(x.strip() for x in f if x.strip())
    for key, dest in (("sweep", "sweep"), ("crossover", "crossover")):
        if key in cfg:
            if not isinstance(cfg[key], bool):
                bad(key, "true or false")
            v[dest] = cfg[key]
    if "k" in cfg:
        if not _is_int(cfg["k"]):
            bad("k", "an integer >= 0")
        v["k"] = cfg["k"]
    if "prefer" in cfg:
        if cfg["prefer"] not in ("direct", "lake"):
            bad("prefer", '"direct" or "lake"')
        v["prefer"] = cfg["prefer"]
    B = sub("budgets", ("sweep", "tools", "passes", "max_per_op", "search"))
    for ph, cd, sd, bd, need in (("sweep", "max_compiles", "max_seconds", "backstop_s", True),
                                 ("tools", "tools_max_compiles", "tools_max_seconds", "tools_backstop_s", False)):
        if ph in B:
            P = sub(f"budgets.{ph}", ("compiles", "seconds", "backstop_s"))
            if "compiles" in P:
                if not (_is_int(P["compiles"], 1) or (P["compiles"] is None and not need)):
                    bad(f"budgets.{ph}.compiles", "an integer >= 1" + ("" if need else " or null"))
                v[cd] = P["compiles"]
            if "seconds" in P:
                if not (P["seconds"] is None or _is_num(P["seconds"])):
                    bad(f"budgets.{ph}.seconds", "a number > 0 or null")
                v[sd] = P["seconds"]
            if "backstop_s" in P:   # L5: the phase's wall backstop (count budgets)
                if not (P["backstop_s"] is None or _is_num(P["backstop_s"])):
                    bad(f"budgets.{ph}.backstop_s", "a number > 0 or null")
                v[bd] = P["backstop_s"]
    if "search" in B:   # L5: per-row workbench-reading budgets of the search families
        try:
            sbv = parse_search_budgets(sub("budgets.search", tuple(SEARCH_FAMILIES)))
        except ValueError as e:
            raise ValueError(f"--config {p}: {e}") from None
        run = set(v.get("tools") or ())
        off = [f for f in sbv if f not in run]
        if off:
            raise ValueError(f"--config {p}: budgets.search names {', '.join(off)}, not among the families run ({', '.join(sorted(run)) or 'none'})")
        v["search_budgets"] = sbv
    if "passes" in B:
        if not _is_int(B["passes"], 1):
            bad("budgets.passes", "an integer >= 1")
        v["passes"] = B["passes"]
    if "max_per_op" in B:
        if not (B["max_per_op"] is None or _is_int(B["max_per_op"], 1)):
            bad("budgets.max_per_op", "an integer >= 1 or null")
        v["max_per_op"] = B["max_per_op"]
    if "caps" in cfg:
        c = doc_free(cfg["caps"])
        if not (isinstance(c, dict) and all(_is_int(n) for n in c.values())):
            bad("caps", "an object {family: compiles}")
        v["family_caps"] = parse_caps(c)
    if "fail_cache" in cfg:
        if cfg["fail_cache"] is not None and not isinstance(cfg["fail_cache"], bool):
            bad("fail_cache", "true, false or null")
        v["fail_cache"] = cfg["fail_cache"]
    S = sub("screen", ("on", "k", "depth", "sweep"))
    if "on" in S:
        if not isinstance(S["on"], bool):
            bad("screen.on", "true or false")
        v["screen"] = S["on"]
    if "sweep" in S:   # L5: batch-screen the sweep's candidates too
        if not isinstance(S["sweep"], bool):
            bad("screen.sweep", "true or false")
        v["screen_sweep"] = S["sweep"]
    for key, dest in (("k", "screen_k"), ("depth", "screen_depth")):
        if key in S:
            if not _is_int(S[key], 1 if key == "k" else 0):
                bad(f"screen.{key}", "an integer")
            v[dest] = S[key]
    if "ops" in cfg:
        o = doc_free(cfg["ops"])
        if not (isinstance(o, dict) and all(isinstance(x, list) and all(isinstance(y, str) for y in x) for x in o.values())):
            bad("ops", "an object {family: [op, ..]}")
        v["family_ops"] = parse_ops(o)
    if "opt_in" in cfg:
        o = cfg["opt_in"]
        if not (isinstance(o, list) and all(isinstance(x, str) for x in o)):
            bad("opt_in", 'a list of "<family>:<op>"')
        v["opt_in"] = parse_opt_in(o)
    if "t3_suggest" in cfg:
        ts = cfg["t3_suggest"]
        if not (ts is None or isinstance(ts, bool) or (isinstance(ts, str) and ts in T3_SUGGEST_MODES)):
            bad("t3_suggest", "false, null, true or one of " + ", ".join(f'"{m}"' for m in T3_SUGGEST_MODES))
        v["t3_suggest"] = "rule" if ts is True else (ts or False)
    if "ctx" in cfg:
        c = doc_free(cfg["ctx"])
        if not (isinstance(c, dict) and all(f in FAMILIES and isinstance(d, dict) for f, d in c.items())):
            bad("ctx", f"an object {{family: {{key: [op names]}}}} over the families {', '.join(FAMILIES)}")
        fx: dict = {}
        for f, d in c.items():
            d = doc_free(d)
            ok = CONFIG_CTX_KEYS.get(f, ())
            no = [k_ for k_ in d if k_ not in ok]
            if no:   # review R3: a family's ctx from a file never carries Lean tokens (suggestions, scope, profile, ...)
                raise ValueError(f"--config {p}: ctx.{f} may not set {', '.join(map(str, no))} (a config may set only "
                                 + ("; ".join(f"ctx.{g}: {', '.join(ks)}" for g, ks in CONFIG_CTX_KEYS.items()) or "nothing") + ")")
            for k_, x in d.items():
                if not (isinstance(x, list) and all(isinstance(y, str) and y.strip() for y in x)):
                    bad(f"ctx.{f}.{k_}", "a list of op names")
                fx.setdefault(f, {})[k_] = list(dict.fromkeys(_fop(f, y.strip()) for y in x))
        v["family_ctx_extra"] = fx
    rec = {"config_sha256": hashlib.sha256(raw).hexdigest(), "config_name": cfg.get("name"), "config_file": str(p.resolve()),
           "config_body": cfg}
    return v, rec


def explicit_dests(argv) -> set:
    """The argparse dests given on the command line (not defaulted)."""
    p = build_parser()
    for act in p._actions:
        act.default = argparse.SUPPRESS
        act.required = False
    return set(vars(p.parse_args(argv)))


def final_reading(final: dict | None, meter: Meter) -> dict | None:
    """b63 speed (2026-10-25): the full reading a finals.json entry carries, if it was taken on this meter's path and is complete:
    proof, meter == the meter's path, tokens / heartbeats ints, Z, compat over exactly the meter's pins (bools), score_exact equal to
    the metrics recomputed now from tokens / heartbeats / Z (the same reference heartbeats and exchange rate), and the proof passes the
    meter's statement / forbidden check, and its tokens equal the current tokenizer's count of the proof (speed review 2026-10-25: an
    entry counted by an older lexer would otherwise carry stale tokens and score into the pick, the screen and the reported delta). None
    otherwise (the end stage then reads the proof as before). On the t6 abpool-42 run the re-read of the input equalled the stored
    reading on 40/42 rows and differed by 1 heartbeat on 2 (within HB_EPS)."""
    f = final or {}
    proof = f.get("proof")
    if not isinstance(proof, str) or not proof.strip() or f.get("meter") != meter.path:
        return None
    tokens, hb, Z, compat, se = f.get("tokens"), f.get("heartbeats"), f.get("Z"), f.get("compat"), f.get("score_exact")
    if not (isinstance(tokens, int) and isinstance(hb, int) and not isinstance(tokens, bool) and not isinstance(hb, bool)):
        return None
    if _num(Z) is None or _num(se) is None or not isinstance(compat, dict) or set(compat) != set(meter.versions):
        return None
    if not all(isinstance(v, bool) for v in compat.values()) or not compat.get(meter.versions[0]):
        return None
    chk = getattr(meter, "_check", None)   # the real Meter's statement / forbidden check (a test meter may have none)
    if abs(compat_pct(compat) - float(Z)) > 1e-6 or (chk is not None and chk(proof.strip()) is not None):
        return None
    stmt = getattr(meter, "statement", None)   # the real Meter: tokens re-counted now (no Lean), as Meter._reading counts them
    if chk is not None and isinstance(stmt, str) and count_tokens(split_declaration(proof.strip(), stmt)) != tokens:
        return None
    M = meter.metrics(tokens, hb, float(Z))
    if abs(M["score_exact"] - float(se)) > 1e-6:
        return None
    r = {"ok": True, "tokens": tokens, "heartbeats": hb, "meter": meter.path, "compiles": 0, "error": None, **M, "Z": float(Z),
         "compat": dict(compat), "Z_assumed": False, "reused": True}
    r["score"] = round(r["score_exact"], 2)
    return r


def replay_row(name: str, rec: dict, row: dict, final: dict | None, meter: Meter, a, log) -> dict:
    steps = rec.get("steps") or {}
    seed = row["src"].strip()
    files = pool_files(name, steps)
    lines = read_pool(files)
    ck = checkpoint_bests_from(steps)
    inp = final if (final or {}).get("proof") else (list(ck.values())[-1] if ck else {"proof": seed, "score": None})
    ck = dict(ck, finals=inp) if inp.get("proof") and inp["proof"].strip() != seed else ck
    cands = collect(name, steps, lines, seed, extra=[dict(inp, label="finals")] if inp.get("proof") else None)
    t0 = time.time()
    known, floor = {}, None   # b63 speed: the finals entry's own reading on this meter is taken as read (final_reading); an entry an end
    fr = final_reading(final, meter) if getattr(a, "reuse_readings", True) else None   # stage wrote ("end:*") carries the seed's floor too
    if fr:
        known[sha(final["proof"])] = fr
        if str(final.get("stage") or "").startswith("end:"):
            floor = sha(final["proof"])
    r = end_stage(row, seed, cands, meter, k=a.k, sweep=a.sweep, crossover=a.crossover, max_compiles=a.max_compiles, checkpoint_bests=ck,
                  log=log, known_readings=known or None, floor_sha=floor, lazy_workbench=getattr(a, "lazy_workbench", True), **end_kwargs(a))
    si = sha(inp["proof"]) if inp.get("proof") else None
    im = next((m for m in r["measured"] if m["sha"] == si), None)
    keep = {k_: v for k_, v in (final or {}).items() if k_ not in ("proof", "score", "score_exact", "tokens", "heartbeats", "L", "H", "Z", "compat",
                                                                 "stage", "picked_from", "meter", "verified")}   # b63 speed: score_exact was kept
    # from the INPUT entry before (2026-10-25 fix; an entry written on top of an end-stage final carried the input's score_exact)
    if r["stage"] == "unmeasured":
        out = dict(final or inp, end="unmeasured")
    else:
        M = r["metrics"]
        out = {"proof": r["proof"], **{k_: M[k_] for k_ in ("score", "score_exact", "tokens", "heartbeats", "L", "H", "Z", "compat") if M.get(k_) is not None},
               **keep, "verified": True, "stage": f"end:{r['stage']}", "picked_from": r["picked_from"], "meter": r["meter"]}
    ein = (im or {}).get("score_exact")
    eout = r["metrics"].get("score_exact")
    return {"problem": name, "input": {k_: inp.get(k_) for k_ in ("score", "tokens", "heartbeats", "stage")},
            "input_measured": im, "end": {**{k_: r["metrics"].get(k_) for k_ in ("score", "score_exact", "tokens", "heartbeats", "Z")},
                                          "stage": r["stage"], "picked_from": r["picked_from"]},
            "delta": round(eout - ein, 6) if ein is not None and eout is not None else None,
            "delta_stored": round(float(out.get("score") or 0) - float(inp.get("score") or 0), 4) if inp.get("score") is not None else None,
            "compiles": r["compiles"], "candidates": len(cands), "pool_lines": len(lines), "checkpoints": list(ck),
            "decisions": r["decisions"], "meter": r["meter"], "tools": r.get("tools"), "families": r.get("families"), "phases": r.get("phases"),
            "self_test": {k_: (meter.test or {}).get(k_) for k_ in ("cached", "path", "fallback", "compiles")},
            "input_reused": bool(fr), "seed_read": not bool(floor),
            "seconds": round(time.time() - t0, 1), "out": out}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, help="a finished (or running) router run directory: rows/<ws>.json, finals.json, config.json")
    ap.add_argument("--rows", help="rows JSONL (default: the run's set from config.json, else the pipeline's registered rows)")
    ap.add_argument("--heartbeats", help="their reference heartbeats JSONL (with --rows)")
    ap.add_argument("--problems", nargs="*", help="restrict to these rows")
    ap.add_argument("--k", type=int, default=K, help="candidates re-measured besides the seed and the checkpoint bests")
    ap.add_argument("--max-compiles", type=int, default=MAX_COMPILES, help="per row (the run-start self-test is not counted)")
    ap.add_argument("--no-sweep", dest="sweep", action="store_false")
    ap.add_argument("--no-crossover", dest="crossover", action="store_false")
    ap.add_argument("--prefer", default="direct", choices=["direct", "lake"], help="the meter (direct falls back to lake on a failed self-test)")
    ap.add_argument("--jobs", type=_jobs_arg, default="auto",
                    help="rows at once (each row's readings stay back to back); an integer, or auto (the default, b63 speed 2026-10-25): "
                         f"auto_jobs() = min({AUTO_JOBS_MAX}, cores // {AUTO_JOBS_CORES_PER_ROW}), reduced to the free cores (cores - load1) "
                         f"// {AUTO_JOBS_CORES_PER_ROW}, never below {AUTO_JOBS_MIN}; the sharing rule between units is their CPUWeight "
                         "(work-conserving), not this count")
    ap.add_argument("--no-reuse-readings", dest="reuse_readings", action="store_false", default=True,
                    help="b63 speed: read the finals.json proof (and the seed) again even when the entry carries a complete reading on "
                         "this meter's path (default: reuse it, final_reading(); the seed is not read when an end stage wrote the entry)")
    ap.add_argument("--serial-self-test", action="store_true",
                    help="b63 speed: the run-start meter self-test row by row, pin by pin (default: run_self_tests(), the (row, pin) pairs "
                         "on --jobs threads, each pin's direct and lake compile back to back, the records assembled in row order)")
    ap.add_argument("--no-lazy-workbench", dest="lazy_workbench", action="store_false", default=True,
                    help="b63 speed: start the row's workbench before every search (default: not for a search whose module's "
                         "search_precheck() says it stops before any reading; the records are the same)")
    ap.add_argument("--anon", action="store_true", help="log rows as row#k")
    ap.add_argument("--out", help="output directory (default <run-dir>/end)")
    ap.add_argument("--tools", type=lambda v: tuple(t.strip() for t in v.split(",") if t.strip()), default=(),
                    help=f"tool families added after the sweep, comma-separated ({', '.join(f for f in FAMILIES if f != 'sweep')}); default none")
    ap.add_argument("--max-seconds", type=float, help="per row wall budget of the search (never cuts the pick); default none")
    ap.add_argument("--family-cap", dest="family_caps", action="append", default=[], metavar="FAMILY=N",
                    help="compiles per row for one family (repeatable, or comma-separated: t3=200,t1=100; crossover too)")
    ap.add_argument("--passes", type=int, default=PASSES, help="greedy passes while the incumbent changes (default 2, the B62b stage)")
    ap.add_argument("--max-per-op", type=int, help="candidates per op for the tool families (default: each module's own)")
    ap.add_argument("--fail-cache", dest="fail_cache", action="store_true", default=None,
                    help="skip edits that failed on an unchanged region (default: on in the tool phase, off in the sweep phase)")
    ap.add_argument("--no-fail-cache", dest="fail_cache", action="store_false")
    ap.add_argument("--tools-max-compiles", type=int, help="the tool phase's compile budget per row (default: --max-compiles)")
    ap.add_argument("--tools-max-seconds", type=float, help="the tool phase's wall budget per row (default: --max-seconds)")
    ap.add_argument("--backstop-s", type=float, default=None,
                    help="L5 count budgets: the sweep phase's wall backstop per row (a stop recorded as a backstop; default none)")
    ap.add_argument("--tools-backstop-s", type=float, default=None, help="L5: the tool phase's wall backstop per row (default: --backstop-s)")
    ap.add_argument("--search-budget", dest="search_budgets", action="append", default=[], metavar="FAMILY=CHECKS[:SECONDS]",
                    help="L5: a search family's per-row budget in workbench readings (its searches get max_checks from it) and its "
                         f"per-row wall backstop (default {SEARCH_BACKSTOP_FACTOR:g} x the module's SEARCH_SECONDS) instead of SEARCH_SECONDS; "
                         "repeatable or comma-separated")
    ap.add_argument("--screen-sweep", action="store_true", default=False,
                    help="L5: batch-screen the sweep's candidates too (sweep phase and sweep+; default: the sweep is never screened)")
    ap.add_argument("--no-screen", dest="screen", action="store_false", default=None,
                    help="no batch screening of the tool families' candidates (default: on with --tools)")
    ap.add_argument("--screen-k", type=int, default=SCREEN_K, help=f"candidates per batch-screen file (default {SCREEN_K})")
    ap.add_argument("--scratch", help="compile-slot / memory-gate directory inside the worktree, used as given (default: "
                                      "<LRA_HBTOOL_SCRATCH or probe/hbtool/.scratch>/end-<hash of --out>: one slot group per run, so two "
                                      "arms never share compile slots)")
    ap.add_argument("--t3-suggest", nargs="?", const="rule", default=False, choices=T3_SUGGEST_MODES,
                    help="R3, opt-in: probe T3's spans with Lean's suggestion tactic and add its suggestions as op t3:hint (needs t3 in "
                         "--tools); rule (the default value): hint with Mathlib, else try?; both: hint and try? on a Mathlib row")
    ap.add_argument("--resume-anyway", action="store_true",
                    help="resume although end_config.json (families, budgets, tables, code identity) differs; recorded in it")
    ap.add_argument("--ops", dest="family_ops", action="append", default=[], metavar="FAMILY=OP[,OP..]",
                    help="R3: a family's op allow-list (repeatable, one family each; ops with or without the family prefix); default: "
                         "every op the family generates by default")
    ap.add_argument("--opt-in", dest="opt_in", action="append", default=[], metavar="FAMILY:OP",
                    help="R3: add an opt-in op to a tool family's default op set (repeatable or comma-separated), e.g. t1:field")
    ap.add_argument("--screen-depth", type=int, default=None, help=f"R3: halvings of a batch screen (default {SCREEN_DEPTH})")
    ap.add_argument("--config", help="R3: a frozen config JSON file that sets the method (module docstring, \"config\"); method flags "
                                     "are then refused; its sha256 is recorded in end_config.json and compared on a resume")
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    crec = None
    if a.config:   # R3: the frozen config sets the method; a method flag next to it is refused
        clash = sorted(explicit_dests(argv) - RUN_DESTS)
        if clash:
            ap.error(f"--config {a.config} sets the method; drop {', '.join('--' + c.replace('_', '-') for c in clash)} (or the file)")
        try:
            vals, crec = load_config(a.config)
        except OSError as e:
            ap.error(f"--config {a.config}: {e}")
        except ValueError as e:
            ap.error(str(e))
        for k_, v_ in vals.items():
            setattr(a, k_, v_)
    try:
        fams = families_for(a.sweep, a.tools)
        a.family_caps = parse_caps(a.family_caps)
        a.family_ops = a.family_ops if isinstance(a.family_ops, dict) else parse_ops(a.family_ops)
        a.opt_in = a.opt_in if isinstance(a.opt_in, dict) else parse_opt_in(a.opt_in)
        a.search_budgets = a.search_budgets if isinstance(a.search_budgets, dict) else parse_search_budgets(a.search_budgets)
    except ValueError as e:
        ap.error(str(e))
    off = [f for f in a.search_budgets if f not in fams]
    if off:
        ap.error(f"--search-budget names {', '.join(off)}, not among the families run ({', '.join(fams)})")
    for k_ in ("backstop_s", "tools_backstop_s"):   # L5: a backstop is a number > 0 (as the config's _is_num); 0 or less would stop at once
        if getattr(a, k_, None) is not None and not _is_num(getattr(a, k_)):
            ap.error(f"--{k_.replace('_', '-')} {getattr(a, k_)!r}: want a number > 0 (leave it out for no backstop)")
    if a.t3_suggest and "t3" not in fams:
        ap.error("--t3-suggest" + (" (the config's t3_suggest)" if a.config else "") + " needs t3 in the tool families (--tools)")
    run_dir = Path(a.run_dir)
    run_dir = run_dir if run_dir.is_absolute() or run_dir.exists() else ROOT / run_dir
    out = Path(a.out) if a.out else run_dir / "end"
    cfgp = run_dir / "config.json"
    cfg = json.loads(cfgp.read_text()) if cfgp.exists() else {}
    rows, hbs = _rows_for(a, cfg)
    finals = json.loads((run_dir / "finals.json").read_text()) if (run_dir / "finals.json").exists() else {}
    recs = {}
    for f in sorted((run_dir / "rows").glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except ValueError:
            continue
        n = d.get("problem")
        if n and (not a.problems or n in a.problems):
            recs[n] = d
    names = [n for n in recs if n in rows]
    out.mkdir(parents=True, exist_ok=True)
    import os
    base_s = Path(os.environ.get("LRA_HBTOOL_SCRATCH") or ROOT / "probe/hbtool/.scratch")   # one slot group per --out under it
    scratch = Path(a.scratch) if a.scratch else base_s / f"end-{hashlib.sha256(str(out.resolve()).encode()).hexdigest()[:12]}"
    scratch = (scratch if scratch.is_absolute() else ROOT / scratch).resolve()
    if not scratch.is_relative_to(ROOT):
        ap.error(f"--scratch must be inside this worktree ({ROOT})")
    try:
        from harness import sweep as _SW
        tables = {n: {k_: s.get(k_) for k_ in ("ok", "sha256")} for n, s in getattr(_SW, "TABLES_STATUS", {}).items()}
    except ImportError:   # no sweep module: the sweep is skipped with a note (_load_sweep), there are no tables to check
        tables = {}
    if a.sweep and not all(s["ok"] for s in tables.values()):
        print(f"[endstage] refused: sweep table(s) missing or unreadable {[n for n, s in tables.items() if not s['ok']]} "
              f"(their ops would drop out of the sweep silently); restore harness/tools/tables/", flush=True)
        return 2
    for f in fams:   # import the run's code now, so the identity below hashes what runs (a file edited later cannot reach this run)
        _load_family(f)
    probs = check_ops(fams, a.family_ops, a.opt_in, getattr(a, "family_ctx_extra", None))
    if probs:
        ap.error("; ".join(probs))
    normalize_method(a, fams)   # review R3: what equals the code's default is neither passed nor recorded
    for mname in ("harness.batch_screen", "harness.hb_tool_eval", "scorer.compile"):
        try:
            importlib.import_module(mname)
        except ImportError:
            pass
    ident = code_identity()
    repp, mp = out / "report.jsonl", out / "meter.json"
    done: dict = {}
    if repp.exists():
        for l in repp.read_text().splitlines():
            try:   # review 2026-10-21: a torn last line (a killed replay) is skipped, the row is redone
                r = json.loads(l) if l.strip() else None
            except ValueError:
                r = None
            if r and r.get("out"):
                done[r["problem"]] = r
    if mp.exists():
        try:
            prev = json.loads(mp.read_text())
        except ValueError:
            prev = None
        if prev is not None:
            if prev.get("prefer", "direct") != a.prefer:   # a resume keeps the run's meter
                print(f"[endstage] refused: this run was started with --prefer {prev.get('prefer', 'direct')}; resume with the same", flush=True)
                return 2
            restore_run_state(prev)
    tools_on = any(f != "sweep" for f in fams)
    cfg_end = {"families": list(fams), "k": a.k, "crossover": a.crossover, "max_compiles": a.max_compiles, "max_seconds": a.max_seconds,
               "family_caps": a.family_caps, "passes": a.passes, "max_per_op": a.max_per_op,
               "fail_cache": tools_on if a.fail_cache is None else a.fail_cache, "prefer": a.prefer, "tables": tables, "code": ident}
    if tools_on:   # the tool phase (R2): its own budget and the batch screen; a sweep-only run keeps the B62b config
        cfg_end.update(order="sweep phase, then tool phase", fail_cache_sweep_phase=bool(a.fail_cache),
                       tools_max_compiles=a.max_compiles if a.tools_max_compiles is None else a.tools_max_compiles,
                       tools_max_seconds=a.max_seconds if a.tools_max_seconds is None else a.tools_max_seconds,
                       screen=a.screen is not False, screen_k=a.screen_k)
        if a.t3_suggest:   # R3: recorded only when on, so a run without it keeps the R2 config
            from harness.tools import t3_suggest as _SG
            cfg_end.update(t3_suggest=a.t3_suggest, t3_suggest_rule=_SG.PROBE_RULE)
        if a.screen_depth is not None:   # R3 keys: only when they differ from the code's default (normalize_method)
            cfg_end["screen_depth"] = a.screen_depth
        fcx = family_ctx_of(a)
        ops_eff = {f: effective_ops(f, fcx.get(f), a.family_ops.get(f), a.t3_suggest) for f in fams if f != "sweep"}
        cfg_end["op_sets"] = {f: v for f, v in ops_eff.items() if v is not None}   # review R3: the op sets in effect, per tool family
    fc = {f: d for f, d in family_ctx_of(a).items() if f in fams}
    cfg_end.update(_l5_kwargs(a))   # L5: recorded only when set, so a run without them keeps its end_config (and resumes)
    if a.family_ops:
        cfg_end["family_ops"] = a.family_ops
    if fc:
        cfg_end["family_ctx"] = fc
    if crec:
        cfg_end.update(crec)
    cp = out / "end_config.json"
    if cp.exists():
        try:
            prev_cfg = json.loads(cp.read_text())
        except ValueError:
            prev_cfg = {}
        if done and prev_cfg.get("families") is not None and prev_cfg["families"] != cfg_end["families"]:   # one arm per out directory
            print(f"[endstage] refused: {out} holds rows of families {prev_cfg['families']}; this call runs {cfg_end['families']} "
                  f"(use another --out)", flush=True)
            return 2
        diff = config_diff(prev_cfg, cfg_end)
        if done and diff:   # R2 review: rows made under another config or other code are never mixed silently
            pc = (prev_cfg.get("code") or {}) if isinstance(prev_cfg.get("code"), dict) else {}
            what = ", ".join(diff) + (f" (code {pc.get('digest')} -> {ident['digest']})" if "code" in diff else "")
            if not a.resume_anyway:
                print(f"[endstage] refused: {out} holds {len(done)} row(s) made under another end_config ({what}); use another --out, "
                      f"or --resume-anyway to mix them (recorded)", flush=True)
                return 2
            print(f"[endstage] WARNING: resuming anyway over {len(done)} row(s) made under another end_config ({what})", flush=True)
            cfg_end["resumed_anyway"] = list(prev_cfg.get("resumed_anyway") or []) + [
                {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rows_before": len(done), "differs": diff,
                 "previous": {k_: prev_cfg.get(k_) for k_ in diff if k_ != "code"}, "previous_code": pc.get("digest")}]
        elif prev_cfg.get("resumed_anyway"):
            cfg_end["resumed_anyway"] = prev_cfg["resumed_anyway"]
    _atomic(cp, json.dumps(cfg_end, indent=1))
    todo = [n for n in names if n not in done]
    idx = {n: i for i, n in enumerate(names)}
    tag = (lambda n: f"row#{idx[n]:02d}") if a.anon else (lambda n: n[:40])
    plock = threading.Lock()

    def logger(n):
        def log(m):
            with plock:
                print(f"[{time.strftime('%H:%M:%S')}] {tag(n)}: {m}", flush=True)
        return log
    if a.jobs == "auto":
        import os
        _cores = os.cpu_count() or 1
        try:
            _load = os.getloadavg()[0]
        except (OSError, AttributeError):
            _load = 0.0
        a.jobs = auto_jobs(_cores, _load)
        jobs_note = f"jobs {a.jobs} (auto: {_cores} cores, load1 {_load:.1f})"
    else:
        jobs_note = f"jobs {a.jobs}"
    print(f"[endstage] {len(names)} row(s), {len(done)} already in the report, {len(todo)} to do; {jobs_note}; out {out}", flush=True)
    meters = {}
    for n in todo:   # run start: the meter self-test, once per (source, pin), recorded before any row's end stage
        meters[n] = Meter(rows[n], hbs, prefer=a.prefer, log=logger(n))
        meters[n].scratch = scratch   # this run's own compile slots (module docstring, "slots")

    def write_meter(_n=None):
        _atomic(mp, json.dumps(dict(run_state(), prefer=a.prefer, code=ident["digest"], git_head=ident["git_head"],
                                    scratch=str(scratch.relative_to(ROOT))), indent=1))
    if a.prefer == "direct" and todo and not getattr(a, "serial_self_test", False):   # b63 speed: the pins at once, the records in row order
        sti = run_self_tests(meters, todo, {n: rows[n]["src"] for n in todo}, a.jobs, after=write_meter, log=print)
        print(f"[endstage] meter self-test: {sti['compiled_rows']} of {sti['rows']} row(s) compiled {sti['pairs']} pin pair(s) on "
              f"{sti['threads']} thread(s) in {sti['seconds']} s", flush=True)
    else:
        for n in todo:
            if a.prefer == "direct":
                meters[n].self_test(rows[n]["src"])
            write_meter(n)

    def one(n):
        try:
            r = replay_row(n, recs[n], rows[n], finals.get(n), meters[n], a, logger(n))
        except Exception as e:  # noqa: BLE001  (one row failing never stops the others; it is retried on the next start)
            logger(n)(f"end stage failed: {type(e).__name__}: {str(e)[:160]}")
            return n, None
        r["code"] = ident["digest"]
        with plock:
            with repp.open("a") as fh:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        logger(n)(f"{r['input'].get('score')} -> {r['out'].get('score')} ({r['end']['stage']}, paired delta {r['delta']}, {r['compiles']} compiles)")
        return n, r
    if a.jobs > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(a.jobs) as ex_:
            res = list(ex_.map(one, todo))
    else:
        res = [one(n) for n in todo]
    for n, r in res:
        if r is not None:
            done[n] = r
    result = {n: dict(v) for n, v in finals.items()}
    for n, r in done.items():
        result[n] = r["out"]
    _atomic(out / "finals.json", json.dumps(result, ensure_ascii=False, indent=1))
    _atomic(mp, json.dumps(dict(run_state(), prefer=a.prefer, code=ident["digest"], git_head=ident["git_head"],
                                scratch=str(scratch.relative_to(ROOT))), indent=1))
    rs = [done[n] for n in names if n in done]
    mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None   # noqa: E731
    stages: dict = {}
    for r in rs:
        stages[r["end"]["stage"]] = stages.get(r["end"]["stage"], 0) + 1
    st = run_state()
    fam_tot: dict = {}
    for r in rs:
        for f, F in (r.get("families") or {}).items():
            T = fam_tot.setdefault(f, {"rows_banked": 0, "banked": 0, "d_score": 0.0, "tried": 0, "compiled": 0, "compiles": 0})
            T["rows_banked"] += 1 if F.get("banked") else 0
            for k_ in ("banked", "tried", "compiled", "compiles"):
                T[k_] += int(F.get(k_) or 0)
            T["d_score"] = round(T["d_score"] + float(F.get("d_score") or 0.0), 6)
    print(json.dumps({"rows": len(rs), "mean_before": mean([float(r["input"].get("score") or 0) for r in rs]),
                      "mean_after": mean([float(r["out"].get("score") or 0) for r in rs]),
                      "mean_delta_paired": mean([r["delta"] for r in rs if r.get("delta") is not None]),
                      "changed": sum(1 for r in rs if r["end"]["stage"] not in ("unmeasured",) and sha(r["out"].get("proof") or "")
                                     != sha(((finals.get(r["problem"]) or {}).get("proof")) or "")),
                      "stages": stages, "compiles": sum(int(r.get("compiles") or 0) for r in rs), "meter": st["path"],
                      "fallback": st["fallback"], "failed_rows": sum(1 for _, r in res if r is None), "families": fam_tot}), flush=True)
    return 0 if all(r is not None for _, r in res) else 1


if __name__ == "__main__":
    sys.exit(main())
