"""Prompt v2 of the Claude Code driver (docs/cc_driver_v2.md §3; `harness/agent_claude_code.py --prompt v2`, default v1 stays byte-identical:
Codex and opencode import SYSTEM / task_prompt / with_extras, and the set #3 Opus line runs from a frozen worktree).

SYSTEM_V2 is static (one cached prefix for every problem of a checkout): the v1 SYSTEM core unchanged, the TOOL MAP (every v2 tool, file
arguments only), a Claude Code version of agent.py's BATCH line, TOKEN_RULES (imported), CLOSED_LESSONS (verbatim copy of agent.py's
literal, drift-tested), a Claude Code version of the LENGTH line, the NOTES rule (the gate can stop a session at any moment) and "never cd".
build_prompt_v2() writes the user prompt in agent.py's order: task header + digest, original.lean and candidate.lean inline, the upstream
digest, technique cards, LIBRARY LEADS (lemma search; injectable so tests run no Lean), REPO_BRIEFS (--repo-cards), the scout / blind-target
/ restructure brief (--from-reference), LEVER_REVIEW on a resume, and the relay/brief extras last.

Round 2 (2026-10-12, docs/cc_driver_v2.md §7-§9, docs/opus_pass2_deep_dive.md R1-R5/R7/R8): the TOOL MAP names every tool with when to use it
(normalize_check.py added); SYSTEM_V2 adds HEARTBEAT_CC (axis, heartbeat prices, the small-reference rule) and STOP_RULE; the digest is
cc_levers.digest_v2 (notes head + tail, the v2 claim filter; a facts sheet instead of notes and diffs in a from-reference session); the user
prompt adds the HEARTBEAT MAP (heartbeat_profile, cached per sha; shown when >= 2 H points are left), RUN TECHNIQUES (<work-root>/
_run_techniques.json, harness/inrun.py, capped) and the heartbeat levers after LEVER_REVIEW.

Reviewer (2026-10-12, docs/cc_driver_v2.md §11): REVIEW_SYSTEM (static) and build_review_prompt() for
agent_claude_code.py --review (everything precomputed on the CPU: the reference, the best with its numbers and axis, the cached heartbeat map,
the facts; one message, no tool calls); review_for() finds <ws>/review.md for the stored best's sha, not yet used by an executor session, and
build_prompt_v2(review=...) shows it as REVIEW (fresh eyes) with the one-batch instruction. A fresh lineage's lineage_facts.md (hx
--claude-fresh-facts) is shown after the digest.

Exemplars (2026-10-13, docs/cc_driver_v2.md §13; agent_claude_code.py --exemplars): build_prompt_v2(exemplars=...) shows the workspace's
exemplars file (harness/exemplars.py, <work root>/_exemplars/<ws>.md: the strongest rows' style against this best, retrieved transformations of
other problems; this best's hot families added from the profile cached now) as WHAT WORKED ON THE STRONGEST ROWS after the REVIEW block, while
the best is below the file's target (a file built for an earlier best says so), never in a from-reference session.

Heartbeat-first (2026-10-13, agent_claude_code.py --heartbeat-first, off by default): system_v2(heartbeat_first=True) and
build_prompt_v2(heartbeat_first=True) add harness/cards.py's HEARTBEAT_FIRST card and its heartbeat-aware rewrites (cards.HB_REWRITES).

Failed moves (2026-10-13, agent_claude_code.py --failed-moves, off by default): build_prompt_v2(failed_moves=True) adds cc_levers'
REFUTED MOVES block after the inline files."""
from __future__ import annotations

import hashlib
from pathlib import Path

from harness.agent import TOKEN_RULES, LEVER_REVIEW  # noqa: F401  (LEVER_REVIEW is part of this module's API)
from harness.agent_claude_code import ROOT, SYSTEM, TOOLS_DIR
from harness import cc_levers as LV
from harness.leantools import HBS
from probe.verify_candidates import newest_first

# ---- verbatim copies of agent.py run_problem literals (drift test: harness/selftest_cc.py prompt_drift, ast.literal_eval of agent.py) ----
# agent.py --closed-lessons (cycle 80, default on since cycle 89)
CLOSED_LESSONS = ("\n\nFIVE HABITS OF THE STRONGEST PROVERS (general, not about this problem):\n"
            "1. Let simp prove side conditions: `simp (disch := omega) only [h]` for arithmetic side goals, or put the lemmas that prove them into the "
            "same `simp only [...]` list (with `(maxDischargeDepth := 4)` if they nest), instead of `h 0 (by decide)` arguments or a typed `have` per "
            "side condition. Flash proofs carry such hand-written side proofs; the strongest provers almost never do.\n"
            "2. Write each piece once: when cases or steps repeat the same tactic run, close them together (`all_goals`, `<;>`, `case A | B => tac`) "
            "instead of repeating it; about a fifth of the tokens in Flash's best proofs sit in repeated runs. `<;> first | A | B` is shorter as "
            "`any_goals A` then `all_goals B` (2 tokens fewer).\n"
            "3. For a goal about a recursive definition `f`, try `fun_induction f` (its cases come split by `f`'s equations) instead of `induction x` "
            "followed by `unfold f` / `split`; first drop hypotheses the goal does not need (`rintro -`), so the induction hypotheses stay simple.\n"
            "4. Before expensive closers, run a cheap reducible pre-pass: `any_goals with_reducible apply Or.inl` (or `with_reducible exact h`) closes "
            "the syntactically easy goals and fails fast on the rest; closers that fail at default transparency cost many heartbeats.\n"
            "5. On simple or-splits and membership-in-append goals, a syntactic closer (`refine Or.imp ?_ ?_`, the `List.mem_append` lemmas) "
            "costs about 30 heartbeats per goal against about 110 for `grind`.")
REPO_BRIEFS = {
        "strata": "REPO AUTOMATION (Strata): NO Mathlib, NO Batteries, NO Aesop — only core tactics (grind, simp, omega, decide, cases/induction, "
                  "rfl, exact?) plus Strata's own macros (elim_err, split_contra, solve_beq, term_by_mem). Never write aesop/linarith/positivity/fun_prop/norm_num here.",
        "cslib": "REPO AUTOMATION (CSLib): built around grind — 583 `@[grind]` annotations, ~2,200 grind uses. First try `grind` with the "
                 "constructors/lemmas your proof already names as hints, e.g. `grind [→ Foo.bar, Baz.qux]`; `all_goals grind [...]` after induction/cases.",
        "physlib": "REPO AUTOMATION (PhysLib): built around simp and fun_prop (211 `@[fun_prop]` lemmas; no grind annotations). Differentiability/"
                   "continuity side goals → `fun_prop`; algebra → `simp [defs]`/`ring`; prefer `simp_all`/`simp only [...]` over long rw chains.",
        "arklib": "REPO AUTOMATION (ArkLib): omega-heavy (~1,600 uses), plus simp and aesop. Index/arithmetic side goals → `omega`; "
                  "structural goals → `simp_all`/`aesop`.",
        "putnambench": "REPO AUTOMATION (PutnamBench): full Mathlib + Aesop; nlinarith/positivity/norm_num/field_simp/ring for real-analysis "
                       "inequalities, `decide`/`omega` for finite/integer facts, `exact?` for library lemmas.",
    }
SCOUT_BRIEFS = {
        "restructure": ("SCOUT C — RESTRUCTURE. Change the proof architecture, not the spelling: a different induction/cases variable or order, symmetric cases merged, a stronger "
                        "intermediate statement via `suffices`/`have` so the cases collapse, `match`/`nomatch`/`nofun` for impossible cases, `obtain`/`rcases` patterns instead of nested "
                        "cases, `calc` collapsed to `_` steps. Batch 2-4 architectures with lean_check_variants and keep the one with the fewest tokens, then cut heartbeats."),
    }

# ---- v2-only system text ({tools} = harness/tools of this checkout) --------------------------------------------------------------------
TOOL_MAP = ("\n\nTOOL MAP (driver v2). Run each with Bash exactly as shown, from the workspace, one command per Bash call. The tools read the "
            "problem from the environment: pass workspace FILE names only, never the problem name. SHELL RULE (2026-10-12 smoke): every Bash call is ONE "
            "simple command (a tool above or grep/rg/ls/cat/head/tail/sed -n/wc/cp/diff); loops, `;`/`&&` chains, redirects (`>`), heredocs, `python3 -c` and "
            "`cd` are refused and waste a turn. Create and change files only with Write/Edit (notes.md included); copies for a batch: variants.py.\n"
            "  python3 {tools}/lean_check.py [FILE]               -> compile, score and bank FILE (default candidate.lean); compatibility on every listed toolchain when it improves; "
            "`axis`: points left on length (L) and heartbeats (H, against the floor) and this row's exchange rate; `progress`: checks since your last new best\n"
            "  python3 {tools}/lean_check_variants.py F1 .. F6    -> up to 6 full candidate files in one call, each scored and banked like lean_check; the best one that beats the stored best is copied to candidate.lean\n"
            "  python3 {tools}/lean_run.py SNIPPET                -> a scratch snippet after the problem's imports/context (`sorry` allowed): `#check`, `example : goal := by exact?`, `simp?` / `grind?` certificates\n"
            "  python3 {tools}/heartbeat_profile.py [FILE]        -> heartbeats per block of a COMPILING proof and the floor (1-3 min, cached per proof; default candidate.lean); later checks measure H against that floor\n"
            "  python3 {tools}/goal_map.py [FILE] [--depth 2]     -> the goal before every step (depth 2: one level into bullets / `=>` arms), ~5-10 s\n"
            "  python3 {tools}/lean_mine.py [FILE]                -> mechanical length cutter for a COMPILING candidate (1-3 min): every block/tail/the whole proof tried as one closer; the result is banked as mined.lean and copied to candidate.lean on a new best\n"
            "  python3 {tools}/lemma_search_cli.py [FILE] [--probes] -> up to 10 ranked library leads for the goals with signatures (--probes also runs exact? at each step: 1-2 min)\n"
            "  python3 {tools}/skeleton_check.py FILE             -> a draft with `sorry` holes: the goal at every hole plus real errors (nothing banked)\n"
            "  python3 {tools}/tok_count.py [FILE ...]            -> proof-body token count with the scorer's lexer, no compile\n"
            "  python3 {tools}/variants.py N [FILE]               -> copies FILE (default candidate.lean) to v1.lean .. vN.lean (N <= 6) in one call, for a batch\n"
            "  python3 {tools}/normalize_check.py [FILE]          -> $0 mechanical post-pass of a COMPILING file (several minutes: up to ~20 compiles; run it alone): lexer rewrites "
            "(`λx`, `$`, layout) and the heartbeat polish (bare `simp` / `simp_all` / `grind` -> their `?`-certificate `only` lists, unused `only` lemmas pruned), each kept "
            "only where strictly better with Z unchanged, then checked and banked like lean_check (copied to candidate.lean on a new best)\n"
            "WHEN TO USE WHICH: heartbeat-heavy row (`axis.points_left_heartbeats` >= 2, or a HEARTBEAT MAP in the task): heartbeat_profile.py first, then "
            "goal_map.py on the costliest block, then targeted variants of that block. Length: lean_mine.py once after every new compiling skeleton; "
            "lemma_search_cli.py when a block wants a library lemma. Two to six alternatives: always ONE lean_check_variants.py call. A new architecture: "
            "skeleton_check.py with `sorry` holes first. Counting without a compile: tok_count.py. Names and closers: lean_run.py probes. Once, before you "
            "stop: normalize_check.py (it is slow: not after every new best).")
# review 2026-10-12: Claude Code's Edit (and Write on an existing file) refuses a file not Read in this session, even one shown in the prompt
BATCH_CC = ("\n\nBATCH YOUR ALTERNATIVES: when you can think of 2-6 plausible rewrites of the same spot (different closers, different case structures, with/without "
            "a `have`), write each as a FULL candidate file and check them all in ONE `python3 {tools}/lean_check_variants.py v1.lean v2.lean ...` call "
            "rather than one lean_check per turn; every compiling variant is scored and banked, and the best one lands in candidate.lean. A local change: "
            "`python3 {tools}/variants.py N` (or one `cp candidate.lean v1.lean`), Read each vK.lean, then Edit it (Edit refuses a file you have not Read in this session, and one a tool rewrote since "
            "your last Read). A new architecture: Write a new file (a new file needs no Read).")
# review 2026-10-12: agent.py's "LENGTH IS THE MISSING AXIS" (warm-up numbers) contradicted R1 on rows whose points are in heartbeats
LENGTH_CC = ("\n\nLENGTH (when `axis.work_on` is tokens, i.e. fewer than 2 heartbeat points are left; otherwise HEARTBEAT FIRST below comes first): "
             "after any new compiling skeleton, run `python3 {tools}/lean_mine.py` once: it finds which blocks a single automation call closes and banks "
             "the result. Then rewrite the remaining long blocks and lean_check them.")
# round 2 (2026-10-12; docs/opus_pass2_deep_dive.md R1): set #3 pass 1 had H 65.3 vs L 75.4 and pass-2 gains came from H, yet v1 called the
# heartbeat profiler 0 times in 65 warm-up sessions; prices measured on the closed lines (deep dive R1, technique cards)
HEARTBEAT_CC = ("\n\nHEARTBEAT FIRST: every lean_check.py result carries `axis`: the points left on length (L) and on heartbeats (H, measured against "
                "the floor once heartbeat_profile.py has run) and this row's exchange rate (one token = N heartbeats). When `points_left_heartbeats` "
                "is 2 or more, the points are in heartbeats: run heartbeat_profile.py, then goal_map.py on the costliest block, and replace that "
                "block's closers. HEARTBEAT PRICES (measured on the closed lines): one `grind` call ~231 hb; `simp_all` ~1.4k; each `set` ~165; `•` "
                "inside a lambda 302 vs 46; a syntactic closer (`exact h`, `refine Or.imp ?_ ?_`, the `List.mem_append` lemmas) ~30 per goal vs ~110 "
                "for `grind`; a failed `apply` ~27. SMALL-REFERENCE RULE (it overrides the one-closer advice of TOKEN COUNTING above): when the "
                "reference costs under about 3-4k heartbeats, no blanket `grind` / `simp_all` finishers (one call can cost a tenth of the whole "
                "reference): `simp only [...]`, `exact`, `omega`, `decide` instead. "
                "A token-saving edit that costs some heartbeats can still win: the score prices the trade (read `axis`).")
# round 2 (R2): v1 stopped itself 0-3 checks after its last best, after ~13 of 60 minutes and ~$2.68 of the gate
STOP_RULE = ("\n\nSTOP RULE: the budget gate ends this session; spend it on checks. Do not finish while the stored best still has 2 or more "
             "heartbeat points left (`axis.points_left_heartbeats`), and not before 8 consecutive checks without a new best "
             "(`progress.checks_since_new_best`; `progress.may_finish` says when both hold). Until then batch the next 2-6 ideas into ONE "
             "lean_check_variants.py call: other closers, a lever from the review, a structural rewrite. Before you finish: normalize_check.py on "
             "candidate.lean, then notes.md.")
NOTES_RULE = ("\n\nNOTES: this session is metered and can be stopped at any moment once its budget is spent, with no last turn. Update notes.md after "
              "every new best and after every few checks: what worked, what failed and why, lemma names confirmed to exist or not, the next idea. Tag "
              "every negative claim with the check that showed it: `[tested: <what> -> <result>]`. Never write that a proof is optimal, minimal or "
              "as short as possible unless a compiled check shows it (every claimed optimum on the warm-up was beaten later). Mark a note "
              "`GENERAL:` only when it is a technique that holds on other problems too, written without this problem's names or code: later "
              "sessions of this run on other problems see such notes.")
NO_CD = "\n\nYou are already in the workspace directory: never `cd`. Use workspace file names as given, absolute paths for the project sources."
# round 2 (R3): the lever review on every resume, with the heartbeat levers (agent.py's LEVER_REVIEW names token levers only)
LEVER_HB = ("\n\nHEARTBEAT LEVERS (add them to the review): the costliest block of the HEARTBEAT MAP (or of heartbeat_profile.py) first; a bare "
            "`simp` / `simp_all` / `grind` whose `?` certificate (`simp?`, `grind?` in lean_run.py) gives an `only` list (normalize_check.py tries "
            "this mechanically); a `grind` / `simp_all` / `aesop` closer where `exact`, `simp only [...]`, `omega` or `decide` compiles (prices in the "
            "system prompt); `set` / `let` / `have` scaffolding used once; `•` or coercions inside lambdas.")


# the reviewer's block in the NEXT executor session (docs/cc_driver_v2.md §11): it replaces steps (1)-(2) of the lever review
REVIEW_BLOCK = ("\n\nREVIEW (fresh eyes): a separate reviewer read the stored best (now candidate.lean, sha {sha}) with its numbers, axis and your "
                "facts (and its heartbeat map when one was measured), and named the levers below, ranked by expected gain. They are hypotheses to test, not facts. FIRST test them in ONE "
                "lean_check_variants.py call: `python3 {tools}/variants.py N` (N = the number of levers, at most 6), Read each vK.lean, apply one lever "
                "per variant with Edit, then `python3 {tools}/lean_check_variants.py v1.lean .. vN.lean`. This batch replaces steps (1)-(2) of a lever "
                "review (add levers of your own only to fill it up to 6). Then combine the winners in a second batch, write in notes.md which levers "
                "won or failed (`[tested: lever K -> result]`), and continue with your own ideas under the stop rule.\nREVIEW:\n")
# harness/exemplars.py's block (docs/cc_driver_v2.md §13, 2026-10-13): the rows at or above the target transfer practices, never proofs
EXEMPLARS_BLOCK = ("\n\nWHAT WORKED ON THE STRONGEST ROWS (built on the CPU after the last batch for best sha {sha}, from this line's "
                   "and the listed lines' measured bests and check histories on OTHER problems, never this one): their tactic style against yours, "
                   "the families of your costliest blocks, and measured transformations as abstract patterns ($A, $B stand for names of your own "
                   "proof). Counts and patterns, not proofs, and hypotheses, not facts: where one fits a costly block, test it as one variant of "
                   "a lean_check_variants.py batch (`axis` says which axis holds the points).\n")


def _t(s: str) -> str:
    return s.replace("{tools}", str(TOOLS_DIR))


# harness/cards.py names agent.py's in-process tools (an `axis` field in lean_check, lean_profile, lean_goals); none exists under Claude Code,
# where a call to an unknown script is denied under dontAsk (a wasted paid turn). The v2 user prompt names the v2 scripts instead
# (review 2026-10-12); cards.py itself stays unchanged (agent.py uses it).
# Round 2 (2026-10-12): the v2 lean_check.py now returns `axis` too (harness/inrun.py), so the card names it again, on the v2 script.
CARD_V2 = (("read `axis` in lean_check (exchange rate, points left) and run lean_profile",
            "read `axis` in the lean_check.py result (exchange rate, points left) and run heartbeat_profile.py (heartbeats per block and the floor)"),
           ("lean_goals", "goal_map.py"), ("lean_profile", "heartbeat_profile.py"))


def cards_v2(text: str) -> str:
    for a, b in CARD_V2:
        text = text.replace(a, b)
    return text


SYSTEM_V2 = (SYSTEM.format(tools=TOOLS_DIR) + _t(TOOL_MAP) + _t(BATCH_CC) + TOKEN_RULES + CLOSED_LESSONS + _t(LENGTH_CC) + HEARTBEAT_CC + STOP_RULE
             + NOTES_RULE + NO_CD)
_GIT_HINT = (" — e.g. `git -C <clone> log -p --follow -- <file> | head -400` to see how upstream later simplified this very proof", "grep/rg/git log/git show/", " and git history")


def system_v2(upstream_history: bool = True, heartbeat_first: bool = False) -> str:
    """SYSTEM_V2, or without the upstream-history hints (--no-upstream-history, the R2 compliance switch). heartbeat_first (2026-10-13,
    agent_claude_code.py --heartbeat-first): TOKEN COUNTING's one-closer line and CLOSED_LESSONS habit 2 made axis-conditional
    (cards.heartbeat_aware; one static prefix per run, the per-problem gate is in build_prompt_v2)."""
    if heartbeat_first:
        from harness import cards as _cards
        return _cards.heartbeat_aware(system_v2(upstream_history))
    if upstream_history:
        return SYSTEM_V2
    return SYSTEM_V2.replace(_GIT_HINT[0], "").replace(_GIT_HINT[1], "grep/rg/").replace(_GIT_HINT[2], "")


def source_trees(row: dict, primary: str) -> list[Path]:
    """Read-only source trees of a problem (never an env root: those hold every run's LRAScratch): the project's own top-level source
    directory and its .lake/packages (dependencies incl. Mathlib), or Mathlib for PutnamBench."""
    if row["source"] == "putnambench":
        return [ROOT / "envs" / f"mathlib-{primary}" / "Mathlib"]
    env = ROOT / "envs" / f"{row['source']}-{primary}"
    return [env / row["file_path"].split("/")[0], env / ".lake" / "packages"]


def git_main(row: dict) -> Path:
    return ROOT / "envs" / f"{row['source']}.git-main"


def _default_leads(name: str, decl: str) -> list[dict]:
    from harness import lemma_search as _ls   # compiles (exact? probes): never called by the selftests
    return _ls.search(name, decl, top=10, probes=True, budget=120.0).get("suggestions") or []


def _default_upstream(row: dict, primary: str) -> str:
    from harness.leantools import upstream_digest
    return upstream_digest(row, primary)


def _default_profile(name: str, decl: str) -> dict:
    from harness import profile as _prof   # compiles (<= 1 + 8 cuts + the floor, each bounded by profile's compile timeout)
    return _prof.profile(name, decl, max_cuts=8)


def _default_techniques(ws) -> str:
    from harness import inrun
    return inrun.render(inrun.load(ws.root.parent), exclude=ws.root.name)   # leave-one-out: never the viewer's own GENERAL notes (review 2026-10-12)


def _default_exemplars(ws) -> tuple[str, str, bool] | None:
    from harness import exemplars as EX
    return EX.exemplars_for(ws.root, ws.state)   # (text, the sha it was built for, stale) while the stored best is below the file's target


def heartbeat_map_for(name: str, ws, decl: str, hbmap, log=lambda *a: None) -> str:
    """R1: the HEARTBEAT MAP of `decl` (the session's candidate.lean): the cached heartbeat_profile result for its sha (state.json
    profile_cache, shared with the v2 tool and agent.py's lean_profile) or a new profile (hbmap: "default" = harness/profile.py, or a callable
    (name, decl) -> profile dict), cached with the floor; "" when it leaves < 2 H points."""
    decl = decl.rstrip(); sha = hashlib.sha256(decl.encode()).hexdigest()[:12]
    cache = ws.state.setdefault("profile_cache", {}); prof = cache.get(sha)
    if prof is None:
        prof = (_default_profile if hbmap == "default" else hbmap)(name, decl)
        if prof:
            cache[sha] = prof
            while len(cache) > 6:
                cache.pop(next(iter(cache)))
            if prof.get("floor"):
                ws.state["hb_floor"] = prof["floor"]
            ws.save()
            log(f"heartbeat profile at session start: total {prof.get('total')} hb, floor {prof.get('floor')}")
    return LV.heartbeat_map(prof)


def build_prompt_v2(name: str, row: dict, primary: str, ws, *, upstream_history: bool = True, repo_cards: bool = False,
                    from_reference: bool = False, lever_review: bool = False, gate_usd: float | None = None, leads="default",
                    upstream="default", extras: str = "", facts: bool = False, hbmap=None, techniques=None, current_run: str | None = None,
                    review: str | None = None, review_sha: str | None = None, exemplars=None, heartbeat_first: bool = False,
                    failed_moves: bool = False, log=lambda *a: None) -> tuple[str, list[str]]:
    """The v2 user prompt and the list of sections it carries. `leads` / `upstream`: callables (name, decl) -> suggestions and (row, primary)
    -> text, or None to skip; "default" runs the real lemma search (Lean) / upstream digest (git). `extras` is with_extras("", ...) computed
    by the driver BEFORE this call (the relay seed may replace candidate.lean), appended last. Round 2: `facts` (a from-reference session with
    history: the facts sheet replaces the notes and the winning-edit diffs), `hbmap` (None, "default" = harness/profile.py, or a callable:
    the HEARTBEAT MAP), `techniques` (None, "default" = <work root>/_run_techniques.json, or a callable ws -> text), `current_run` (the
    session's own run id, left out of the earlier-run count). Reviewer (§11): `review` (review_for()'s body, for the best `review_sha`) is shown
    as REVIEW (fresh eyes) after the lever review, never in a from-reference session; a workspace's lineage_facts.md (a fresh lineage under hx
    --claude-fresh-facts) is shown after the digest. Exemplars (§13): `exemplars` (None, "default" = <work root>/_exemplars/<ws>.md through
    exemplars.exemplars_for, with this best's hot families, or a callable ws -> (text, sha[, stale]) | None) is shown as WHAT WORKED ON THE
    STRONGEST ROWS after the REVIEW block, never in a from-reference session (its hot blocks are lines of the stored best). heartbeat_first
    (2026-10-13, --heartbeat-first): when cards.heartbeat_first_on passes for the stored best's axis (after the map, so a floor it measured
    counts; always without a measured best), the HEARTBEAT_FIRST card joins the technique cards (section 'heartbeat_first') and the cards,
    the repo card, the restructure brief and the lever review take the heartbeat-aware wording (cards.HB_REWRITES); False leaves every byte as before.
    failed_moves (2026-10-13, --failed-moves): cc_levers.failed_moves_block against the candidate as shown (REFUTED MOVES, section
    'failed_moves') right after the inline files; nothing when no move is refuted; False leaves every byte as before."""
    versions = newest_first(row["version_info"]); sections = ["header"] + (["facts"] if facts else [])
    ctx_txt = (ws.root / "context.lean").read_text() if (ws.root / "context.lean").exists() else ""
    if row["source"] == "putnambench":
        src_note = f"Mathlib sources (read-only) for grep/rg: {source_trees(row, primary)[0]}. "
    else:
        a, b = source_trees(row, primary); gm = git_main(row)
        src_note = (f"Project sources (read-only) for grep/rg: {a} (dependencies incl. Mathlib: {b}) ; the problem's file is {row['file_path']}"
                    + (f" ; full git history of the project (newer commits may contain a simplified version of this very proof — "
                       f"`git -C {gm} log -p --follow -- {row['file_path']} | head -400`) is in {gm}" if upstream_history else "") + ". ")
    budget = ("This session is metered at list price and is stopped without warning once it reaches its budget"
              + (f" (about ${gate_usd:.2f} for this session)" if gate_usd is not None else "") + ": keep candidate.lean compiling and notes.md current. ")
    p = (f"Problem `{name}` from the {row['source']} corpus. Reference proof body: {row['proof_length']} tokens, {HBS.get(name)} heartbeats. "
         f"Toolchains: {', '.join(versions)}. Workspace files: original.lean, context.lean "
         f"({'imports/header' if row['source'] == 'putnambench' else 'surrounding file prefix, ' + str(ctx_txt.count(chr(10))) + ' lines'}), "
         f"candidate.lean, notes.md. " + src_note + budget
         + "Keep durable insights (what worked, what failed and why, lemma names that exist) in notes.md so later runs can continue.\n\n"
         + LV.digest_v2(ws, facts=facts, current_run=current_run)
         + ("\n\nBoth original.lean and candidate.lean are shown below, so plan from them; Read candidate.lean once before your first Edit (Edit "
            "refuses a file not Read in this session)." if not ws.state["attempts"] else
            "\n\nStart from candidate.lean (the reference, shown below; Read it once before your first Edit); the facts above say what the earlier "
            "sessions learned." if facts else
            "\n\nContinue from candidate.lean (shown below; Read it once before your first Edit); notes.md is summarised above."))
    try:   # hx --claude-fresh-facts (§11): a fresh lineage's view of the main lineage (facts sheet, no proof text)
        lf = (ws.root / "lineage_facts.md").read_text().strip()
    except OSError:
        lf = ""
    if lf:
        p += "\n\n" + lf[:LV.FACTS_CAP + 400]; sections.append("lineage_facts")
    for fn, lbl in (("original.lean", "original.lean (the REFERENCE proof)"),
                    ("candidate.lean", "candidate.lean (reset to the reference for this run)" if from_reference else "candidate.lean (your current best)")):
        try:
            txt = (ws.root / fn).read_text().rstrip()
        except OSError:
            continue
        if txt:
            p += f"\n\n{lbl}:\n```lean\n{txt[:12000]}\n```" + ("\n(truncated: Read the file for the rest)" if len(txt) > 12000 else "")
            sections.append(fn)
    cur = (ws.root / "candidate.lean").read_text() if (ws.root / "candidate.lean").exists() else (ws.state["best"].get("proof") or row["src"])
    if failed_moves:   # 2026-10-13: edits refuted by >= 2 real compiles whose lines are still in the candidate shown above
        try:
            fm = LV.failed_moves_block(ws.state, base=cur)
            if fm:
                p += "\n\n" + fm; sections.append("failed_moves")
        except Exception as e:  # noqa: BLE001
            log(f"refuted moves failed: {e}")
    if hbmap:
        try:
            hm = heartbeat_map_for(name, ws, cur, hbmap, log)
            if hm:
                p += "\n\n" + hm; sections.append("heartbeat_map")
        except Exception as e:  # noqa: BLE001
            log(f"heartbeat map failed: {e}")
    if upstream_history and upstream:
        try:
            up = (_default_upstream if upstream == "default" else upstream)(row, primary)
            if up:
                p += "\n\n" + up; sections.append("upstream")
        except Exception as e:  # noqa: BLE001
            log(f"upstream digest failed: {e}")
    hbf = False
    if heartbeat_first:
        from harness import cards as _cards
        hbf = _cards.gate(name, row, ws.state, HBS.get(name), log=log)
    hbw = _cards.heartbeat_aware if hbf else (lambda s: s)
    try:
        from harness import cards as _cards
        p += "\n\n" + cards_v2(_cards.cards_for(row["statement"], cur, ctx_txt, heartbeat_first=hbf)); sections.append("cards")
        if hbf:
            sections.append("heartbeat_first")
    except Exception as e:  # noqa: BLE001
        log(f"technique cards failed: {e}")
    if leads:
        try:
            sg = (_default_leads if leads == "default" else leads)(name, cur.rstrip())
            if sg:
                p += ("\n\nLIBRARY LEADS for the current proof (lemma search: exact? at each goal, names ranked by match with the goal and statement, "
                      "same-file lemmas the reference does not use, @[simp]/@[grind]/@[to_fun] lemmas, induction principles). Leads, not answers: "
                      "check a lead's signature against the goal (goal_map.py) before building on it; lemma_search_cli.py re-runs it after a restructure.\n"
                      + "\n".join(f"  - {s.get('name')} [{s.get('source')}{', line ' + str(s['line']) if s.get('line') else ''}]: "
                                  f"{(s.get('signature') or '')[:180]}  -- {(s.get('why') or '')[:140]}" for s in sg[:10]))
                sections.append("leads")
        except Exception as e:  # noqa: BLE001
            log(f"lemma search failed: {e}")
    if techniques:
        try:
            tt = (_default_techniques if techniques == "default" else techniques)(ws)
            if tt:
                p += "\n\n" + tt[:1500]; sections.append("techniques")
        except Exception as e:  # noqa: BLE001
            log(f"run techniques failed: {e}")
    if repo_cards and row["source"] in REPO_BRIEFS:
        p += "\n\n" + hbw(REPO_BRIEFS[row["source"]]); sections.append("repo_card")
    if from_reference:
        best = ws.state.get("best") or {}
        p += ("\n\nSCOUT RUN: candidate.lean holds the ORIGINAL reference proof. Produce a compiling candidate of your own architecture early (within 4 checks), "
              "then shorten it; everything that compiles is scored and banked, and the stored best is kept unless you beat it.")
        if float(best.get("score") or 33.33) > 33.34 and best.get("tokens"):
            p += (f" BLIND TARGET: the stored best has {best.get('tokens')} tokens and {best.get('heartbeats') or '?'} heartbeats "
                  f"(score {best.get('score')}); a structurally different proof that beats it is the goal.")
            sections.append("blind_target")
        p += "\n\n" + hbw(SCOUT_BRIEFS["restructure"]); sections += ["scout", "restructure"]
    if lever_review and not from_reference:
        p += hbw(LEVER_REVIEW) + LEVER_HB; sections += ["lever_review", "hb_levers"]   # hbw: identity unless the heartbeat-first gate passed
    if review and not from_reference:
        p += _t(REVIEW_BLOCK).replace("{sha}", review_sha or "?") + review[:LV.REVIEW_CAP]; sections.append("review")
    if exemplars and not from_reference:
        try:
            ex = (_default_exemplars if exemplars == "default" else exemplars)(ws)
            if ex and ex[0]:
                p += EXEMPLARS_BLOCK.replace("{sha}", ex[1]) + ex[0][:1500]; sections.append("exemplars")   # exemplars.BLOCK_CAP
        except Exception as e:  # noqa: BLE001
            log(f"exemplars failed: {e}")
    if extras:
        p += extras; sections.append("extras")
    return p, sections


# ---- the reviewer (agent_claude_code.py --review; 2026-10-12, docs/cc_driver_v2.md §11; docs/opus_pass2_deep_dive.md
# R3: a fresh review naming concrete edits beat the Opus line on 10/10 targeted warm-up problems) --------------------------------------------
_CHECKLIST = LEVER_REVIEW[LEVER_REVIEW.index("a hypothesis the goal never uses"):LEVER_REVIEW.index(" (2) Test ALL")].rstrip()
_HB_PRICES = HEARTBEAT_CC[HEARTBEAT_CC.index("HEARTBEAT PRICES"):]
REVIEW_SYSTEM = ("You are a fresh-eyes REVIEWER of one Lean 4 proof that another agent is optimizing for score = mean(length_reduction%, "
                 "heartbeat_reduction%, compatibility%), where length = token count of the proof body (every bracket/operator is a token, dotted "
                 "names are one token, comments don't count), heartbeats = elaboration cost, compatibility = fraction of listed toolchains on which "
                 "it compiles unchanged. You write no proof and no file and you compile nothing: the task message holds the reference, the current "
                 "best with its numbers and axis, the heartbeat map when one was measured, and the facts from the agent's records. Your final message "
                 "is saved verbatim as review.md; the agent's next session tests your levers in one batch of compiles, one lever per variant, and "
                 "combines the winners.\n\nWHAT TO LOOK FOR (the closed lines' lever checklist): " + _CHECKLIST + TOKEN_RULES + CLOSED_LESSONS
                 + "\n\n" + _HB_PRICES
                 + "\n\nREVIEW RULES: 3 to 6 levers, each one concrete edit that one compile can test on its own, ranked by expected score gain; "
                 "locations by best.lean line number; no Lean block longer than 2 lines (longer blocks are removed from the saved review: describe "
                 "the edit, quote at most 2 lines); never write that the proof is optimal, minimal or cannot be improved (such lines are removed: "
                 "every claimed optimum on the warm-up was beaten); no tool calls and no file writes (everything is in the task message); answer in "
                 "ONE message holding only the numbered levers.")
REVIEW_FORMAT = ("N. <title> (expected: ~+X score; tokens -T, heartbeats -H)\n"
                 "   - location: best.lean line(s) and the tactic(s) there\n"
                 "   - change: the exact edit, as inline code (at most 2 lines of Lean)\n"
                 "   - why: which axis it moves and by how much (the prices, the map, the exchange rate)\n"
                 "   - risk: what may break (a side goal, an older toolchain, more heartbeats)")


def build_review_prompt(name: str, row: dict, primary: str, root: Path, state: dict, gate_usd: float | None = None, ws=None, hbmap=None,
                        log=lambda *a: None) -> tuple[str, list[str], str]:
    """The reviewer's task message, precomputed before the session ($0 API): the reference, best.lean (line-numbered) with its score / L / H / Z
    / tokens / heartbeats and sha, the AXIS (cc_levers.axis on the scorer's local reference and the measured floor), the HEARTBEAT MAP of the
    best (state.json profile_cache), the facts (cc_levers.review_facts) and the task (heartbeat-first when >= 2 H points are left). Returns
    (prompt, sections, best sha). Review 2026-10-12: with `ws` (its .state is `state`) and `hbmap` (as build_prompt_v2: "default" =
    harness/profile.py, or a callable), a best with >= 2 H points left (upper bound) and no cached profile is profiled first, cached under its
    sha (the next executor session's map of the same best then costs no compile); without a map the task does not point to one."""
    from scorer.score import local_reference_heartbeats
    b = state.get("best") or {}; proof = (b.get("proof") or "").rstrip(); sha = LV.proof_sha(proof)
    rh = local_reference_heartbeats(name) or HBS.get(name)
    ax = LV.axis(row["proof_length"], rh, b.get("tokens"), b.get("heartbeats"), state.get("hb_floor"))
    if hbmap and ws is not None and proof and ax and ax["points_left_heartbeats"] >= LV.H_FIRST:
        try:
            heartbeat_map_for(name, ws, proof, hbmap, log)
        except Exception as e:  # noqa: BLE001
            log(f"heartbeat map failed: {e}")
    fl = state.get("hb_floor")   # the profile may have measured it
    ax = LV.axis(row["proof_length"], rh, b.get("tokens"), b.get("heartbeats"), fl)
    hb_first = bool(ax and ax["points_left_heartbeats"] >= LV.H_FIRST)
    p = (f"Problem `{name}` from the {row['source']} corpus. Toolchains: {', '.join(newest_first(row['version_info']))}. Reference proof body: "
         f"{row['proof_length']} tokens, {HBS.get(name)} heartbeats. "
         + (f"This review is metered at list price and stopped at about ${gate_usd:.2f}: " if gate_usd is not None else "")
         + "answer in ONE message without tool calls (everything you need is below; a tool call costs a second request).")
    sections = ["header"]
    try:
        orig = (root / "original.lean").read_text().rstrip()
    except OSError:
        orig = row["src"].rstrip()
    p += f"\n\noriginal.lean (the REFERENCE proof):\n```lean\n{orig[:12000]}\n```" + ("\n(truncated)" if len(orig) > 12000 else "")
    numbered = "\n".join(f"{i:>3}| {line}" for i, line in enumerate(proof.split("\n"), 1))
    lmh = f"L {b.get('L')}, H {b.get('H')}, Z {b.get('Z')}; " if b.get("L") is not None else ""
    p += (f"\n\nbest.lean (the CURRENT BEST, = candidate.lean when the next session starts; score {b.get('score')}: {lmh}{b.get('tokens')} tokens, "
          f"{b.get('heartbeats')} heartbeats; sha {sha}; line numbers added for your locations, they are not part of the file):\n```lean\n"
          f"{numbered[:14000]}\n```" + ("\n(truncated)" if len(numbered) > 14000 else ""))
    sections.append("best.lean")
    if ax:
        p += (f"\n\nAXIS of the best: about {ax['points_left_length']} L points and {ax['points_left_heartbeats']} H points left (upper bounds; H "
              + (f"against the measured floor {fl} hb" if fl else "without a measured floor") + f"); one token = {ax['one_token_equals_heartbeats']} "
              f"heartbeats on this row; {ax['points_per_token']} points per token, {ax['points_per_1k_heartbeats']} points per 1k heartbeats; "
              f"work on: {ax['work_on']}.")
        sections.append("axis")
    hm = LV.heartbeat_map((state.get("profile_cache") or {}).get(sha))
    if hm:
        p += "\n\n" + hm.replace("heartbeat_profile at session start", "heartbeat_profile, cached").replace("candidate.lean", "best.lean")
        sections.append("heartbeat_map")
    try:
        notes = (root / "notes.md").read_text()
    except OSError:
        notes = ""
    p += "\n\n" + LV.review_facts(state, notes); sections.append("facts")
    order = (f"HEARTBEATS FIRST: the best has {ax['points_left_heartbeats']} H points left (2 or more), so levers that cut heartbeats ("
             + ("the costliest blocks of the map" if hm else "the costliest blocks by the HEARTBEAT PRICES (no map was measured for this best)")
             + ", an expensive closer where a cheap one compiles, `set` / coercion scaffolding) rank above token-only levers"
             if hb_first else "fewer than 2 H points are left, so token levers come first (whole blocks into one closer, the TOKEN COUNTING "
             "rewrites), then heartbeat levers")
    p += (f"\n\nYOUR REVIEW: name 3 to 6 concrete, testable LEVERS for best.lean, ranked by expected score gain; {order}. Write each lever exactly "
          f"as:\n{REVIEW_FORMAT}\nEach lever must compile on its own (the next session applies one lever per variant, then combines the winners). "
          "Do not repeat a tested negative from the facts without a new reason. Never write that the proof is optimal, minimal or cannot be "
          "improved. No Lean block longer than 2 lines. Output only the numbered levers.")
    sections.append("task")
    return p, sections, sha


def review_for(root: Path, state: dict, current_run: str | None = None) -> tuple[str, str] | None:
    """(body, sha) of <ws>/review.md when it reviewed the stored best (its sha) and no executor session other than current_run came after it
    (the NEXT session only); None otherwise (no review, another best, or already used). "After" is the order of runs[] (every session appends
    its entry when it starts): the entries after the review's own; without that entry, the ones started after the review was written."""
    try:
        parsed = LV.parse_review((root / "review.md").read_text())
    except OSError:
        return None
    if not parsed:
        return None
    meta, body = parsed; sha = LV.proof_sha((state.get("best") or {}).get("proof"))
    if not body or meta.get("best_sha") != sha or not (state.get("best") or {}).get("proof"):
        return None
    runs = state.get("runs") or []
    i = next((k for k in range(len(runs) - 1, -1, -1) if runs[k].get("run_id") == meta.get("run") and runs[k].get("kind") == "review"), None)
    later = runs[i + 1:] if i is not None else [r for r in runs if str(r.get("started") or "") > (meta.get("t") or "")]
    if any(r.get("kind") != "review" and not r.get("skipped") and r.get("run_id") != current_run for r in later):
        return None
    return body, sha


def drift_nodes(agent_src: str) -> dict:
    """The agent.py literals this module copies (ast.literal_eval of run_problem's nodes): closed lessons, REPO_BRIEFS, SCOUT_BRIEFS."""
    import ast
    fn = next(n for n in ast.parse(agent_src).body if isinstance(n, ast.FunctionDef) and n.name == "run_problem")
    out = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Attribute) and node.test.attr == "closed_lessons":
            out["CLOSED_LESSONS"] = ast.literal_eval(node.body[0].value)
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ("REPO_BRIEFS", "SCOUT_BRIEFS"):
            out[node.targets[0].id] = ast.literal_eval(node.value)
    return out
