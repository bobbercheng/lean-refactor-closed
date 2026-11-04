#!/usr/bin/env python3
"""G0a self-test of the Claude Code driver v2 (docs/cc_driver_v2.md, 2026-10-12): NO model call and NO Lean.

A fake `claude` (a Python script on a temp PATH that holds no real claude; checked before anything runs) records its argv / env / workspace
view and replays scripted stream-json sessions with partial messages. harness/agent_claude_code.py runs end to end against it on a
PutnamBench warm-up row (its workspace needs no Lean environment) in temp work roots; the tool scripts run under stubs of every Lean-facing
function. Run directories the driver writes under probe/runs/selftest-cc-* are moved into the temp dir.
    python3 harness/selftest_cc.py [--keep]      # PASS/FAIL per check, exit 1 on any failure

Checks:
  units          harness/test_cc_meter.py and harness/test_prompt_v2.py (meter rules, replay, drift, v1 golden hashes) pass
  v1_identity    plain v1 (and --sealed): argv (prompt, system prompt, flags), env and cwd equal the pre-v2 driver's (commit BASE, exec'd)
  v1_gated       v1 + --budget-usd: exactly + [--include-partial-messages --max-budget-usd G] and CLAUDE_CODE_MAX_OUTPUT_TOKENS=32000,
                 CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK=1, CLAUDE_CODE_DISABLE_FAST_MODE=1; --cache-ttl 5m adds FORCE_PROMPT_CACHING_5M=1; the
                 ledger charges the result's total_cost_usd
  v2_flags       --prompt v2: Read,Edit,Write,Bash, dontAsk, per-script Bash rules (no tools/* glob), LRAScratch denies, SYSTEM_V2, v2 env,
                 .lra_env.json present during the session and removed after; v2-only flags refused under v1; --sealed refuses briefs
  v2_sealed      --prompt v2 --sealed: the sealed flags, ONE --disallowedTools list carrying the find denies, no API-key env
  normal         v2 + gate, 3 calls with duplicate assistant ids: spend = total_cost_usd, meter within 1e-6, modelUsage stored, $1.0
                 milestone crossed live with a workspace snapshot (spend at the crossing), turn events sum to the charge, best_so_far rises
  big_output     one 30k-output call (thinking events + text): metered exactly, not killed
  hang_timeout   no events after message_start: killed at --timeout, charged S + c_in + 20e-6·max(2·out_live, 2000)
  kill_a         over-budget streaming call: killed by rule (a) at the first event where what a kill charges passes G - M, charge within G
  kill_c         a tool_result whose next-call reserve does not fit: killed by rule (c) before the next request, charged S + R_next
                 (round-2 review: the kill may race that request; flag c-reserve-booked)
  no_result      a session that ends without a result event: charged S, flagged
  skip           a problem whose ledger leaves less than the opening reserve: no session, "budget reached"
  (review 2026-10-12) pre-charge (spend0 + G and a pending entry while claude runs); orphan (a detached and a double-forked "compile" that
                 read state.json are killed with the tree, the ledger survives); sigterm (the driver kills and charges the session, exit 143);
                 stale (a pending entry from a dead driver: flagged driver-died, its gate kept); trunc (> 200 checks after a new best:
                 best_so_far from the live best); hx (hx_heldout session_cmd for claude, curve() over the driver's turn events)
  tools_v1       every tool script without LRA_CHECK_V2: stdout and workspace byte-identical to the pre-v2 scripts (stubbed Lean)
  tools_v2       LRA_CHECK_V2=1: files only (a problem name is refused), problem from env or .lra_env.json, variants winner copied,
                 candidate.lean itself winning (no SameFileError), lean_mine banks mined.lean and copies it, heartbeat_profile default
                 candidate.lean, lemma search probes off by default, tok_count body tokens, two parallel lean_checks both recorded under
                 the state lock
  (round 2, 2026-10-12, docs/cc_driver_v2.md §9)
  units          + harness/test_cc_levers.py, harness/test_inrun.py, harness/test_hb_polish.py (+ harness/test_transfer.py, §12)
  r2_session     normal: HEARTBEAT MAP from a cached profile (no Lean), RUN TECHNIQUES from the work root, lever review + heartbeat levers,
                 best_before / best_after in the run entry; escalate: a previous session that gained < 0.5 over >= 4 checks -> from the
                 reference with a facts sheet (no Lean block > 2 lines, no stored-best text), mode escalated, best kept; afterscout: no second
                 escalation in a row; --no-heartbeat-map refused under v1
  r2_tools       the ledger win (an edit) and `axis` / `progress` on a v2 check; heartbeat_profile cached per sha with the floor (later
                 checks measure H against it); variants report the best's axis; normalize_check banks a strictly better proof and copies it,
                 banks nothing otherwise, and refuses without LRA_CHECK_V2
  r2_hx          cc_after_batch commands (polish, discover --ledger-only over runs with records, --allow-mixed with a polish run, techniques),
                 in-run default on for v2 / off for v1, the Phase A argv still parses (run_phase_a.sh bash -n), and the real discover
                 --ledger-only + inrun.py on a temp line: ledger written, techniques file in the work root, counts-only log lines
                 (round-2 review 2026-10-12) runs by exact name (no other arm's), a damaged gzip trajectory counted (no traceback), recovery
                 of a dead ladder's unmerged fresh lineage, a SIGTERM during a post-batch step kills the step
  (reviewer, A4 and ceiling, 2026-10-12, docs/cc_driver_v2.md §11)
  review         --review: Read-only argv (no Bash / Edit / Write rule, no --add-dir; REVIEW_SYSTEM; gate $0.30), every workspace file
                 byte-identical (review.md the only new file), the gate pre-charged and charged to the ledger (runs[] kind review), review.md
                 linted (no Lean block over 2 lines, no optimality claim) and bound to the best's sha; the next executor session shows the REVIEW
                 block and does not escalate, the one after it no longer shows it; no result event: text saved flagged partial; review_text's
                 sources; skipped without a stored best, effort high by default; refusals; --ceiling lifts the $2.85 cap to the rung;
                 (review 2026-10-12) the executor session shown the review moves review.md out of the workspace; the reviewer's heartbeat map
                 (cached profile of the best) and a task that names no map without one
  hx_review      hx --claude-review end to end with the fake claude: round 1, ONE reviewer batch for round 2's rows (charged before it), round
                 2 at the next rung (--round-per-rung) with the REVIEW block, no review after the last round, the reviews' spend in the turn
                 events; next_plan's cases; --claude-fresh-facts (lineage_facts.md, no proof text; the sheet's code from the line's worktree);
                 --claude-ceiling in both commands
  scripts        bash -n of run_phase_a.sh, run_ceiling.sh, run_after_opus.sh; the ladder argv the runners print (LRA_PRINT_ARGV=1, nothing
                 run) parsed and accepted by hx's checks: A1-A3 unchanged, A4, the ceiling arm; refused combinations; (review 2026-10-12)
                 phase_a_audit.py on a temp line: fresh lineages' sessions and unmerged spend, --since
  (exemplar transfer, 2026-10-13, docs/cc_driver_v2.md §13)
  units          + harness/test_exemplars.py
  exemplars      --exemplars refused under v1; with it the executor prompt shows <work root>/_exemplars/<ws>.md (WHAT WORKED ON THE STRONGEST
                 ROWS) while the best is below the file's target (runs[] exemplars_seen, the trajectory header's sections), a file of an earlier
                 best marked stale (exemplars_stale); never without the flag, never a first-version <ws>/exemplars.md; Read on _exemplars denied"""
from __future__ import annotations

import gzip, hashlib, json, os, shutil, signal, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = "ad8cd6ffee45acae1c3a9dfb06cfa8b219c3976a"   # the last commit before driver v2 (the spec commit): the v1 reference
PROBLEM = "putnam_1964_b2"
RESULTS: list = []

FAKE = r'''#!PYTHON
"""Fake `claude` for harness/selftest_cc.py (never calls a model): records argv, env and the workspace view, then replays the scripted
stream-json session named by LRA_FAKE_CC (CLI 2.1.296 shapes, partial messages included)."""
import json, os, pathlib, sys, time
D = pathlib.Path(os.environ["LRA_FAKE_CC_DIR"]); D.mkdir(parents=True, exist_ok=True)
SC = os.environ.get("LRA_FAKE_CC", "record"); cwd = pathlib.Path.cwd(); lra = cwd / ".lra_env.json"; stp = cwd / "state.json"
(D / f"{SC}-{os.getpid()}.json").write_text(json.dumps({"argv": sys.argv[1:], "env": dict(os.environ), "cwd": str(cwd),
                                                        "lra_env_json": lra.read_text() if lra.exists() else None,
                                                        "state_at_start": json.loads(stp.read_text()) if stp.exists() else None}))


def emit(d, pause=0.0):
    sys.stdout.write(json.dumps(d) + "\n"); sys.stdout.flush()
    if pause:
        time.sleep(pause)


def usage(inp=2, w1=0, w5=0, cr=0, out=1, geo="global"):
    return {"input_tokens": inp, "cache_creation_input_tokens": w1 + w5, "cache_read_input_tokens": cr, "output_tokens": out, "inference_geo": geo,
            "cache_creation": {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": w1}, "service_tier": "standard", "speed": "standard"}


def cost(u):   # list price written out independently of harness/cc_meter.py
    g = 1.1 if u["inference_geo"] == "us" else 1.0; c = u["cache_creation"]
    return g * (4 * u["input_tokens"] + 5 * c["ephemeral_5m_input_tokens"] + 8 * c["ephemeral_1h_input_tokens"] + 0.2 * u["cache_read_input_tokens"]
                + 20 * u["output_tokens"]) / 1e6


TOTAL = {"cost": 0.0, "usage": {}}


def call(mid, u, out, think=0, text="", stop="tool_use", pause=0.0, dup=2, content="x"):
    emit({"type": "stream_event", "event": {"type": "message_start", "message": {"id": mid, "usage": u}}, "parent_tool_use_id": None})
    for k in range(think // 100):
        emit({"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 100 * (k + 1), "estimated_tokens_delta": 100}, pause)
    if text:
        emit({"type": "stream_event", "event": {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": text}}})
    for _ in range(dup):   # the CLI repeats one message id per content block, with the stale message_start usage
        emit({"type": "assistant", "message": {"id": mid, "usage": u, "content": [{"type": "text", "text": content}]}})
    emit({"type": "stream_event", "event": {"type": "message_delta", "delta": {"stop_reason": None}, "usage": {"output_tokens": out // 2}}})
    emit({"type": "stream_event", "event": {"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {"output_tokens": out}}})
    emit({"type": "stream_event", "event": {"type": "message_stop"}})
    fu = dict(u, output_tokens=out); TOTAL["cost"] += cost(fu)
    for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"):
        TOTAL["usage"][k] = TOTAL["usage"].get(k, 0) + fu[k]


def tool_result(pause=0.0):
    emit({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_x", "content": "ok"}]}}, pause)


def bank(score):   # what the stubbed lean_check would leave: an attempt of this run, and a new best
    sp = cwd / "state.json"; st = json.loads(sp.read_text())
    st["attempts"].append({"sha": f"s{score}", "ok": True, "score": score, "tokens": 5, "heartbeats": 100, "run_id": os.environ["LRA_RUN_ID"],
                           "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    if score > float(st["best"].get("score") or 0):
        st["best"] = {"score": score, "proof": "stub proof", "tokens": 5, "heartbeats": 100}
    sp.write_text(json.dumps(st, indent=1))


def result(text="done"):
    emit({"type": "result", "subtype": "success", "is_error": False, "num_turns": 3, "duration_ms": 1234, "total_cost_usd": TOTAL["cost"],
          "usage": TOTAL["usage"], "modelUsage": {"claude-opus-5-5": {"costUSD": TOTAL["cost"]}}, "terminal_reason": "completed", "result": text})


# the reviewer's answer (§11): three levers, a 2-line Lean block (kept), a 4-line one and an optimality claim (both removed from review.md)
RV = ("1. Replace the closer (expected: ~+1.0 score; heartbeats -900)\n   - location: best.lean line 2 (`simp`)\n   - change: `simp only [h]`\n"
      "   - why: a bare simp costs more\n   - risk: low\n2. Merge the cases (expected: ~+0.5)\n   - change:\n```lean\n  all_goals omega\n  exact h\n```\n"
      "3. Rewrite the step (expected: ~+2)\n```lean\n  intro x\n  induction x\n  · simp\n  · omega\n```\nThe proof is already near-optimal on tokens.\n")


emit({"type": "system", "subtype": "init", "cwd": str(cwd), "tools": ["Read", "Edit", "Write", "Bash"], "mcp_servers": [], "model": "claude-opus-5-5",
      "apiKeySource": "none", "claude_code_version": "2.1.296-fake"})
emit({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "rateLimitType": "five_hour", "utilization": 0.1, "resetsAt": 0}})
if SC == "record":
    call("msg_rec", usage(2, w1=4000, cr=12000), 50, stop="end_turn", dup=1); result()
elif SC == "normal":
    call("msg_n1", usage(2, w1=6000, cr=12000), 900, think=300, text="checking"); bank(50.0); tool_result()
    call("msg_n2", usage(2, w1=1500, cr=18000), 1200, think=500); bank(52.0); tool_result()
    call("msg_n3", usage(2, w5=500, cr=19500, geo="us"), 300, stop="end_turn"); result()
elif SC == "big":
    call("msg_big", usage(2, w1=8000, cr=12000), 30000, think=30000, text="y" * 3000, stop="end_turn"); result()
elif SC == "hang":
    emit({"type": "stream_event", "event": {"type": "message_start", "message": {"id": "msg_hang", "usage": usage(2, w1=5000, cr=12000)}}})
    for k in range(5):
        emit({"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 100 * (k + 1), "estimated_tokens_delta": 100})
    time.sleep(120)
elif SC == "kill_a":
    call("msg_a1", usage(2, w1=12500), 2000); tool_result()
    call("msg_a2", usage(2, w1=15000), 40000, think=40000, pause=0.02, stop="end_turn"); result()
elif SC == "kill_c":
    call("msg_c1", usage(2, w1=12500), 2000); tool_result(pause=1.5)
    call("msg_c2", usage(2, w1=500, cr=13000), 100, stop="end_turn"); result()
elif SC == "noresult":
    call("msg_r1", usage(2, w1=3000, cr=12000), 400); tool_result()
    call("msg_r2", usage(2, w1=700, cr=15000), 250, stop="end_turn")
elif SC == "orphan":   # CLI 2.1.296 runs each Bash command detached (own session): a "lean_check" that read state.json, still compiling
    import subprocess  # at the gate kill, would write its stale copy back after the ledger. k=0: a detached child; k=1: double-forked away
    code = ("import os, sys, time\np, mk, fork = sys.argv[1], sys.argv[2], sys.argv[3] == '1'\n"
            "if fork and os.fork():\n    os._exit(0)\n"
            "s = open(p).read(); time.sleep(2.5); open(p, 'w').write(s); open(mk, 'w').write('survived')\n")
    kids = [subprocess.Popen([sys.executable, "-c", code, str(stp), str(D / f"orphan-{k}-survived"), str(k)], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for k in (0, 1)]   # own pipes, as the CLI's Bash: EOF at claude's death
    kids[1].wait(); time.sleep(0.4)   # both read state.json (pre-charged) before the kill
    call("msg_o1", usage(2, w1=12500), 2000); tool_result(pause=1.5)
    call("msg_o2", usage(2, w1=500, cr=13000), 100, stop="end_turn"); result()
elif SC == "trunc":   # a new best, then > 200 checks: leantools keeps the last 200 attempts, so the best's scored attempt is gone
    call("msg_t1", usage(2, w1=6000, cr=12000), 500); bank(60.0)
    st = json.loads(stp.read_text())
    st["attempts"] = (st["attempts"] + [{"sha": f"x{k}", "ok": False, "run_id": os.environ["LRA_RUN_ID"],
                                         "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} for k in range(205)])[-200:]
    stp.write_text(json.dumps(st, indent=1)); tool_result()
    call("msg_t2", usage(2, w1=800, cr=18000), 200, stop="end_turn"); result()
elif SC == "review":   # the reviewer (§11): one message, no tool call
    call("msg_rv", usage(2, w5=9000, cr=12000), 1500, think=300, text=RV, stop="end_turn", dup=1, content=RV); result(RV)
elif SC == "review_cut":   # a reviewer whose session ends without a result event: its complete text block is saved, flagged partial
    call("msg_rc", usage(2, w5=9000, cr=12000), 1500, think=300, text=RV, stop="end_turn", dup=1, content=RV)
(D / f"{SC}-end").write_text("the fake reached the end of its script")
'''

# Tool-script runner with every Lean-facing function stubbed: argv = ROOT MODE(old|new) TOOL ARGS...; old = the BASE source exec'd with the
# real script's __file__ (env STUB_OLD_SRC), new = the working tree's script.
TOOLRUN = r'''
import hashlib, json, os, re, runpy, sys, time, types
ROOT, MODE, TOOL, ARGS = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
sys.path.insert(0, ROOT)
import harness.leantools as LT
STMT = LT.ROWS["putnam_1964_b2"]["statement"]


def lean_check(name, decl, state, prov, vpath):
    time.sleep(float(os.environ.get("STUB_SLEEP", "0")))
    m = re.search(r"-- SCORE ([0-9.]+)", decl); ok = m is not None and "FAIL" not in decl
    att = {"sha": hashlib.sha256(decl.encode()).hexdigest()[:12], "tokens": len(decl.split()), "heartbeats": 100, "ok": ok,
           "error": None if ok else "stub error", "run_id": prov.get("run_id"), "t": "2026-10-12T00:00:00Z"}
    state.setdefault("attempts", []).append(att)
    res = {"ok": ok, "tokens": att["tokens"], "heartbeats": 100, "errors": [] if ok else ["stub error"], "stub_problem": name, "stub_mode": prov.get("mode"),
           "stub_model": prov.get("model")}
    if "-- AUTOFIX" in decl:
        res.update({"auto_fixed": "stub fix", "fixed_decl": decl.replace("-- AUTOFIX", "-- FIXED")})
    if ok:
        sc = float(m.group(1)); res["predicted_score_if_compatible"] = sc
        if sc > state.setdefault("best", {"score": 33.33}).get("score", 33.33):
            state["best"] = {"score": sc, "proof": decl, "tokens": att["tokens"], "heartbeats": 100}; att["score"] = sc
            res.update({"score": sc, "new_best": True})
    return res


LT.lean_check = lean_check


def mod(name, **fns):
    m = types.ModuleType(name); m.__dict__.update(fns); sys.modules[name] = m


mod("goals", goal_map=lambda name, decl, depth=1, from_line=0, **k: {"stub": "goal_map", "problem": name, "depth": depth, "from_line": from_line, "head": decl[:40]},
    skeleton_check=lambda name, draft, **k: {"stub": "skeleton", "problem": name, "head": draft[:40]}, instrument=lambda *a, **k: None)
mod("profile", profile=lambda name, decl, max_cuts=12: {"stub": "profile", "problem": name, "max_cuts": max_cuts, "head": decl[:40], "ok": True,
                                                       "total": 100, "floor": 40, "reference": 1000, "blocks": []})


def _norm(name, decl, log=print):   # round 2 stubs: the lexer normalizer and the heartbeat polish, keyed by markers in the proof
    b = {"ok": True, "score": 50.0, "Z": 100.0}
    if "-- NORM" in decl:
        return {"status": "improved", "before": b, "after": dict(b, score=60.0), "applied": {"lam": 1}, "gain": 10.0,
                "proof": decl.replace("-- NORM", "-- NORMED")}
    return {"status": "no sites", "before": b, "after": b, "proof": decl}


def _pol(name, decl, base=None, **k):
    if "simp_all" in decl and "simp_all only" not in decl:
        return {"status": "improved", "before": base, "after": dict(base or {}, score=88.0), "applied": {"simp_all only": 1}, "gain": 1.0,
                "proof": decl.replace("simp_all", "simp_all only [h]").replace("SCORE 70", "SCORE 88")}
    return {"status": "no gain", "before": base, "after": base, "proof": decl}


mod("normalize", normalize=_norm)
mod("hb_polish", polish=_pol)
mod("lemma_search", search=lambda name, decl, top=10, probes=True, budget=180.0, **k: {
    "suggestions": [{"name": "Stub.lemma", "signature": "Stub.lemma : True", "source": "stub", "line": 1, "why": "stub", "extra": 1}],
    "runtime_s": 0.0, "stub_probes": probes, "stub_problem": name, "debug": {"x": 1}})
mod("mine", mine=lambda name, decl, jobs=6, log=print, **k: {"base_tokens": 10, "blocks": 2, "block_hits": {"0": ["grind", 5]}, "suffix_ok": [[1, 3]],
    "whole_ok": [], "best": {"proof": STMT + " := by\n  grind -- SCORE 70", "how": "block 1 -> grind"}, "stub_jobs": jobs, "stub_problem": name})
real = os.path.join(ROOT, "harness", "tools", TOOL + ".py")
sys.argv = [real] + ARGS
if MODE == "old":
    exec(compile(open(os.environ["STUB_OLD_SRC"]).read(), real, "exec"), {"__name__": "__main__", "__file__": real})
else:
    runpy.run_path(real, run_name="__main__")
'''


def check(name: str, cond, detail="") -> bool:
    RESULTS.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'} {name}" + (f"  [{detail}]" if detail and not cond else ""), flush=True)
    return bool(cond)


def git_show(path: str) -> str | None:
    p = subprocess.run(["git", "-C", str(ROOT), "show", f"{BASE}:{path}"], capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def price(inp=2, w1=0, w5=0, cr=0, out=0, g=1.0) -> float:
    return g * (4 * inp + 5 * w5 + 8 * w1 + 0.2 * cr + 20 * out) / 1e6


class World:
    def __init__(self, T: Path):
        self.T = T; self.bin = T / "bin"; self.dump = T / "dump"; self.runs = T / "runs"; self.wr = T / "wr"
        for d in (self.bin, self.dump, self.runs, self.wr):
            d.mkdir(parents=True, exist_ok=True)
        fake = self.bin / "claude"; fake.write_text(FAKE.replace("#!PYTHON", "#!" + sys.executable)); fake.chmod(0o755)
        (T / "toolrun.py").write_text(TOOLRUN)
        (T / "run_old.py").write_text("import sys\nsrc, real = sys.argv[1], sys.argv[2]\nsys.argv = [real] + sys.argv[3:]\n"
                                      "exec(compile(open(src).read(), real, 'exec'), {'__name__': '__main__', '__file__': real})\n")
        base = {k: v for k, v in os.environ.items() if not k.startswith(("LRA_", "CLAUDE"))}
        self.env = dict(base, PATH=f"{self.bin}:/usr/bin:/bin", LRA_FAKE_CC_DIR=str(self.dump), PYTHONDONTWRITEBYTECODE="1")
        self.fake = fake

    def safe(self) -> bool:
        """The driver runs claude with PATH = ~/.elan/bin + ours: the first claude on it must be the fake, never the real CLI."""
        found = shutil.which("claude", path=f"{Path.home()}/.elan/bin:{self.env['PATH']}")
        return found is not None and Path(found).resolve() == self.fake.resolve()

    def seed(self, label: str, **state) -> Path:
        d = self.wr / label / PROBLEM; d.mkdir(parents=True, exist_ok=True)
        st = {"problem": PROBLEM, "best": {"score": 40.0, "proof": None, "tokens": 300, "heartbeats": None}, "attempts": [], "runs": [], **state}
        (d / "state.json").write_text(json.dumps(st, indent=1)); (d / "notes.md").write_text("# Notes (yours to keep; persisted across runs)\n")
        return d

    def driver(self, label: str, scenario: str, extra: list, old: bool = False, run_id: str | None = None, fresh: bool = True, timeout: int = 180):
        for f in self.dump.glob("*"):
            f.unlink()
        run_id = run_id or f"selftest-cc-{label}"
        args = ["--problems", PROBLEM, "--workers", "1", "--work-root", str(self.wr / label), "--run-id", run_id, "--effort", "xhigh",
                *(["--fresh"] if fresh else []), *extra]
        cmd = ([sys.executable, str(self.T / "run_old.py"), str(self.T / "old_driver.py"), str(ROOT / "harness/agent_claude_code.py")] if old
               else [sys.executable, str(ROOT / "harness/agent_claude_code.py")]) + args
        src = ROOT / "probe/runs" / run_id; dst = self.runs / (label + ("-old" if old else ""))
        try:
            p = subprocess.run(cmd, cwd=ROOT, env=dict(self.env, LRA_FAKE_CC=scenario), capture_output=True, text=True, timeout=timeout)
        finally:
            if src.exists():
                shutil.rmtree(dst, ignore_errors=True); shutil.move(str(src), str(dst))
        dumps = sorted(self.dump.glob(f"{scenario}-[0-9]*.json"))
        if p.returncode != 0 and "error:" not in p.stderr:
            print(p.stdout[-1500:], p.stderr[-3000:], sep="\n")
        return p, (json.loads(dumps[0].read_text()) if dumps else None), dst, (self.dump / f"{scenario}-end").exists()

    def state(self, label: str) -> dict:
        return json.loads((self.wr / label / PROBLEM / "state.json").read_text())

    def traj(self, run_dir: Path) -> list:
        f = run_dir / "trajectories" / f"{PROBLEM}.jsonl.gz"
        return [json.loads(l) for l in gzip.open(f, "rt") if l.strip().startswith("{")] if f.exists() else []


def run_units() -> None:
    for t in ("harness/test_cc_meter.py", "harness/test_prompt_v2.py", "harness/test_cc_levers.py", "harness/test_inrun.py", "harness/test_hb_polish.py",
              "harness/test_transfer.py", "harness/test_exemplars.py",
              "harness/test_heartbeat_first.py"):   # 2026-10-13 --heartbeat-first: card + rewrites on, every default prompt byte-identical
        p = subprocess.run([sys.executable, str(ROOT / t)], capture_output=True, text=True, timeout=600)
        check(f"units {t}", p.returncode == 0, p.stdout[-800:] + p.stderr[-800:])


def runs_entry(st: dict, run_id: str) -> dict:
    return next((r for r in reversed(st.get("runs", [])) if r.get("run_id") == run_id), {})


def test_v1(W: World) -> None:
    old = git_show("harness/agent_claude_code.py")
    if old is None:
        print(f"SKIP v1_identity: commit {BASE[:8]} not in this clone"); return
    (W.T / "old_driver.py").write_text(old)
    for label, extra in (("v1id", []), ("v1sealed", ["--sealed"])):
        po, do, _, _ = W.driver(label, "record", extra, old=True, run_id=f"selftest-cc-{label}")
        pn, dn, _, _ = W.driver(label, "record", extra, run_id=f"selftest-cc-{label}")
        ok = do is not None and dn is not None
        check(f"v1_identity {label} both ran", ok and po.returncode == 0 and pn.returncode == 0, (po.stderr + pn.stderr)[-500:])
        if ok:
            check(f"v1_identity {label} argv (prompt, system, flags)", do["argv"] == dn["argv"],
                  str([x for x in dn["argv"] if x not in do["argv"]])[:300] + " / " + str([x for x in do["argv"] if x not in dn["argv"]])[:300])
            check(f"v1_identity {label} env", do["env"] == dn["env"], str(set(do["env"].items()) ^ set(dn["env"].items()))[:300])
            check(f"v1_identity {label} cwd", do["cwd"] == dn["cwd"] and do["lra_env_json"] is None and dn["lra_env_json"] is None)
            if label == "v1id":
                ref = do
    if "ref" not in locals():
        return
    # v1 + gate: the reference plus exactly the gate flags and the output cap
    p, d, rd, _ = W.driver("v1gated", "record", ["--budget-usd", "2.85"], run_id="selftest-cc-v1id")
    check("v1_gated argv = v1 + gate flags", d and d["argv"] == ref["argv"] + ["--include-partial-messages", "--max-budget-usd", "2.8500"],
          str(d and d["argv"][-6:]))
    ws_of = lambda label: {"LRA_WORKSPACE": str(W.wr / label / PROBLEM)}   # each gated run has its own work root
    gate_env = {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "32000", "CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK": "1", "CLAUDE_CODE_DISABLE_FAST_MODE": "1"}
    check("v1_gated env = v1 + output cap, no non-streaming fallback, no fast mode", d and d["env"] == {**ref["env"], **ws_of("v1gated"), **gate_env},
          str(d and set(d["env"].items()) ^ set(ref["env"].items())))
    st = W.state("v1gated"); r = runs_entry(st, "selftest-cc-v1id"); rec = price(2, w1=4000, cr=12000, out=50)
    check("v1_gated ledger = total_cost_usd", abs(float(st.get("api_spend", -1)) - round(rec, 6)) < 1e-9 and abs(r.get("spend_usd_list", -1) - round(rec, 6)) < 1e-9,
          f"{st.get('api_spend')} {r.get('spend_usd_list')} {rec}")
    check("v1_gated run entry", r.get("flags") == [] and r.get("modelUsage") == {"claude-opus-5-5": {"costUSD": rec}} and r.get("minutes") is not None
          and r.get("ended") and (r.get("driver") or {}).get("prompt") == "v1" and (r.get("rate_limit") or {}).get("utilization") == 0.1, str(r)[:400])
    tr = W.traj(rd); turns = [e for e in tr if e.get("type") == "turn"]
    check("v1_gated turn events", len(turns) == 1 and turns[0]["price_basis"] == "list" and abs(turns[0]["cost"] - round(rec, 6)) < 1e-9, str(turns))
    p, d, _, _ = W.driver("v1gated5m", "record", ["--budget-usd", "2.85", "--cache-ttl", "5m"], run_id="selftest-cc-v1id")
    check("v1_gated --cache-ttl 5m env", d and d["env"] == {**ref["env"], **ws_of("v1gated5m"), **gate_env, "FORCE_PROMPT_CACHING_5M": "1"})


def test_v2_flags(W: World) -> None:
    from harness.agent_claude_code import TOOLS_DIR, V2_TOOLS, SEALED_FIND
    from harness import prompt_v2 as pv
    p, d, rd, _ = W.driver("v2flags", "record", ["--prompt", "v2", "--no-library-leads", "--no-heartbeat-map"])
    if not check("v2_flags ran", d is not None and p.returncode == 0, p.stderr[-500:]):
        return
    a = d["argv"]; e = d["env"]
    allow = a[a.index("--allowedTools") + 1:a.index("--disallowedTools")]
    deny = a[a.index("--disallowedTools") + 1:a.index("--permission-mode")] if "--add-dir" not in a else a[a.index("--disallowedTools") + 1:a.index("--add-dir")]
    check("v2_flags tools / permission mode", a[a.index("--tools") + 1] == "Read,Edit,Write,Bash" and a[a.index("--permission-mode") + 1] == "dontAsk")
    check("v2_flags per-script Bash rules, no tools/* glob", all(f"Bash(python3 {TOOLS_DIR}/{t}*)" in allow for t in V2_TOOLS)
          and f"Bash(python3 {TOOLS_DIR}/*)" not in a and not any(x.startswith("Bash(git") for x in allow), str(allow)[:400])
    check("v2_flags workspace-scoped Read/Edit/Write, denies", any(x.startswith("Edit(//") and PROBLEM in x for x in allow)
          and any("LRAScratch" in x for x in deny) and any("/bank/**" in x for x in deny) and any("/probe/**" in x for x in deny), str(deny))
    check("v2_flags system prompt = SYSTEM_V2", a[a.index("--system-prompt") + 1] == pv.system_v2(True))
    prompt = a[a.index("-p") + 1]
    check("v2_flags user prompt v2 sections", "original.lean (the REFERENCE proof)" in prompt and "TECHNIQUE CARDS" in prompt
          and "LIBRARY LEADS" not in prompt and "LEVER REVIEW" not in prompt)
    check("v2_flags env", all(e.get(k) == v for k, v in {"LRA_CHECK_V2": "1", "LRA_MODE": "agent-cc-v2", "LRA_AGENT_TAG": "claude-code",
          "BASH_DEFAULT_TIMEOUT_MS": "900000", "BASH_MAX_TIMEOUT_MS": "1800000", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
          "LRA_PROBLEM": PROBLEM}.items()) and "CLAUDE_CODE_MAX_OUTPUT_TOKENS" not in e and "--include-partial-messages" not in a)
    lra = json.loads(d["lra_env_json"] or "{}")
    check("v2_flags .lra_env.json during the session, removed after", lra.get("LRA_PROBLEM") == PROBLEM and lra.get("LRA_MODE") == "agent-cc-v2"
          and not (W.wr / "v2flags" / PROBLEM / ".lra_env.json").exists())
    hd = next((x for x in W.traj(rd) if x.get("type") == "header"), {})
    check("v2_flags trajectory header", hd.get("prompt_version") == "v2" and "cards" in (hd.get("sections") or []))
    # sealed v2: the sealed flags, one deny list carrying the find denies, no API-key env
    p, d, _, _ = W.driver("v2sealed", "record", ["--prompt", "v2", "--no-library-leads", "--no-heartbeat-map", "--sealed"])
    if check("v2_sealed ran", d is not None and p.returncode == 0, p.stderr[-500:]):
        a = d["argv"]
        check("v2_sealed flags", all(x in a for x in ("--no-session-persistence", "--strict-mcp-config")) and a.count("--disallowedTools") == 1
              and all(x in a[a.index("--disallowedTools"):] for x in SEALED_FIND) and d["env"].get("CLAUDE_CODE_DISABLE_AUTO_MEMORY") == "1"
              and not any(k.startswith("ANTHROPIC_") for k in d["env"]))
    # refusals: v2-only flags under v1, briefs under --sealed (argparse errors, no claude started)
    for label, extra in (("refuse-v1", ["--repo-cards"]), ("refuse-sealed", ["--prompt", "v2", "--sealed", "--brief-dir", str(W.T)]),
                         ("refuse-v1-r2", ["--no-heartbeat-map"]), ("refuse-v1-ex", ["--exemplars"])):
        p, d, _, _ = W.driver(label, "record", extra)
        check(f"v2_flags refuses {' '.join(extra[:3])}", p.returncode == 2 and d is None, p.stderr[-300:])


def test_sessions(W: World) -> None:
    # normal: v2 + gate + 5 m cache, ledger seeded at $0.95 with one earlier run (LEVER_REVIEW), 3 calls with duplicate assistant ids; round 2:
    # a cached heartbeat profile of the session's candidate (the reference: no best yet) gives the HEARTBEAT MAP without Lean, and the line's
    # run techniques file is shown
    from harness.leantools import ROWS
    sha = hashlib.sha256(ROWS[PROBLEM]["src"].rstrip().encode()).hexdigest()[:12]
    prof = {"ok": True, "total": 120000, "floor": 9000, "reference": 134548, "points_left_heartbeats": 27.5,
            "blocks": [{"lines": "5-9", "heartbeats": 80000, "text": "nlinarith [stub]"}]}
    W.seed("normal", api_spend=0.95, runs=[{"run_id": "earlier", "model": "x"}], profile_cache={sha: prof})
    (W.wr / "normal" / "_run_techniques.json").write_text(json.dumps({"patterns": [{"pattern": "simp -> simp only", "problems": 2, "wins": 3, "d_score": 0.5,
                                                                                   "d_tokens": 4, "d_heartbeats": -250, "example": ""}],
                                                                     "ops": [], "notes": ["prefer omega on Nat goals"], "closer_prices": {}}))
    p, d, rd, end = W.driver("normal", "normal", ["--prompt", "v2", "--no-library-leads", "--budget-usd", "2.85", "--cache-ttl", "5m"], fresh=False)
    c1 = price(2, w1=6000, cr=12000, out=900); c2 = price(2, w1=1500, cr=18000, out=1200); c3 = price(2, w5=500, cr=19500, out=300, g=1.1)
    tot = c1 + c2 + c3
    st = W.state("normal"); r = runs_entry(st, "selftest-cc-normal")
    if check("normal ran", d is not None and p.returncode == 0 and end, p.stderr[-500:]):
        a = d["argv"]
        check("normal gate flags + env", a[-3:] == ["--include-partial-messages", "--max-budget-usd", "1.9000"]
              and d["env"].get("FORCE_PROMPT_CACHING_5M") == "1" and d["env"].get("CLAUDE_CODE_MAX_OUTPUT_TOKENS") == "32000", str(a[-3:]))
        check("normal lever review on a resume", "LEVER REVIEW FIRST" in a[a.index("-p") + 1])
        s0 = d.get("state_at_start") or {}; r0 = runs_entry(s0, "selftest-cc-normal")
        check("normal pre-charge during the session (spend0 + G, pending entry)", abs(s0.get("api_spend", -1) - 2.85) < 1e-9 and r0.get("pending") is True
              and r0.get("gate_usd") == 1.9, f"{s0.get('api_spend')} {r0}")
    check("normal spend = total_cost_usd", abs(r.get("spend_usd_list", -1) - round(tot, 6)) < 1e-9 and abs(st.get("api_spend", -1) - round(0.95 + tot, 6)) < 1e-9,
          f"{r.get('spend_usd_list')} vs {tot}; {st.get('api_spend')}")
    m = r.get("meter") or {}
    check("normal meter (dedupe, cumulative out, 5m/1h, geo)", m.get("calls") == 3 and abs(m.get("metered_usd", -1) - tot) < 1e-6, str(m))
    check("normal run entry", r.get("flags") == [] and r.get("modelUsage") == {"claude-opus-5-5": {"costUSD": tot}} and "pending" not in r
          and (r.get("driver") or {}).get("cache_ttl") == "5m" and (r.get("driver") or {}).get("gate_usd") == 1.9, str(r)[:500])
    ms = st.get("budget_milestones") or {}
    snap = W.wr / "normal" / PROBLEM / "snapshots" / "1"
    sst = json.loads((snap / "state.json").read_text()) if (snap / "state.json").exists() else {}
    check("normal $1.0 milestone + live snapshot", set(ms) == {"1"} and ms["1"].get("turn") == 0 and abs(ms["1"]["spend"] - round(0.95 + c1, 6)) < 1e-9
          and ms["1"].get("snapshot") == "snapshots/1" and (snap / "candidate.lean").exists() and (snap / "notes.md").exists()
          and abs(sst.get("api_spend", -1) - round(0.95 + c1, 6)) < 1e-9, str(ms))
    tr = W.traj(rd); turns = [e for e in tr if e.get("type") == "turn"]; bs = [e["best_so_far"] for e in turns]
    check("normal turn events", len(turns) == 3 and abs(sum(e["cost"] for e in turns) - round(tot, 6)) < 1e-9 and all(e["price_basis"] == "list" for e in turns)
          and bs == sorted(bs) and bs[-1] == 52.0 and bs[0] >= 40.0, str(turns)[:500])
    check("normal milestone + end events", any(e.get("type") == "budget_milestone" and e.get("usd") == 1.0 for e in tr)
          and any(e.get("type") == "end" and abs(e.get("spend_usd_list", -1) - round(tot, 6)) < 1e-9 for e in tr))
    check("normal .lra_env.json removed", d is not None and d["lra_env_json"] and not (W.wr / "normal" / PROBLEM / ".lra_env.json").exists())
    check("normal snapshot carries no pending marker", "pending" not in runs_entry(sst, "selftest-cc-normal") and runs_entry(sst, "selftest-cc-normal").get("forked_live"))
    pr = d["argv"][d["argv"].index("-p") + 1] if d else ""; sy = d["argv"][d["argv"].index("--system-prompt") + 1] if d else ""
    hd = next((x for x in tr if x.get("type") == "header"), {})
    check("r2_session normal: HEARTBEAT MAP (cached profile), RUN TECHNIQUES, lever review + heartbeat levers",
          "HEARTBEAT MAP of candidate.lean" in pr and "lines 5-9: 80000 hb" in pr and "RUN TECHNIQUES" in pr and "simp -> simp only: 2 problems" in pr
          and "LEVER REVIEW FIRST" in pr and "HEARTBEAT LEVERS" in pr and "STOP RULE" in sy and "normalize_check.py" in sy
          and all(x in (hd.get("sections") or []) for x in ("heartbeat_map", "techniques", "lever_review", "hb_levers")) and hd.get("escalated") is False,
          str(hd.get("sections")))
    check("r2_session normal: best_before / best_after in the run entry", r.get("best_before") == 40.0 and r.get("best_after") == 52.0, str(r)[:300])
    test_hx(W, rd)
    test_escalation(W)

    # big output: one 30k-output call
    p, d, rd, end = W.driver("big", "big", ["--budget-usd", "2.85"])
    big = price(2, w1=8000, cr=12000, out=30000); r = runs_entry(W.state("big"), "selftest-cc-big")
    check("big_output metered, not killed", end and r.get("flags") == [] and abs(r.get("spend_usd_list", -1) - round(big, 6)) < 1e-9
          and abs((r.get("meter") or {}).get("metered_usd", -1) - big) < 1e-6, str(r.get("meter")))

    # hang: no events after message_start -> killed at --timeout, charged S + c_in + 20e-6·max(2·out_live, 2000); seeded at $0.95, so only
    # the final charge crosses the $1.0 milestone (recorded at the end, turn None, snapshot taken)
    W.seed("hang", api_spend=0.95)
    t0 = time.time()
    p, d, rd, end = W.driver("hang", "hang", ["--budget-usd", "2.85", "--timeout", "3"], fresh=False)
    hang = price(2, w1=5000, cr=12000) + 20e-6 * max(2 * 1.5 * 500, 2000); st = W.state("hang"); r = runs_entry(st, "selftest-cc-hang")
    check("hang_timeout killed and charged", not end and time.time() - t0 < 60 and "stopped:timeout" in (r.get("flags") or []) and "no-result" in (r.get("flags") or [])
          and abs(r.get("spend_usd_list", -1) - round(hang, 6)) < 1e-9 and abs(st.get("api_spend", -1) - round(0.95 + hang, 6)) < 1e-9,
          f"{r.get('flags')} {r.get('spend_usd_list')} vs {hang}")
    tr = W.traj(rd); turns = [e for e in tr if e.get("type") == "turn"]
    check("hang_timeout charge in the turn events", len(turns) == 1 and turns[0].get("adjust") and abs(turns[0]["cost"] - round(hang, 6)) < 1e-9, str(turns))
    ms = (st.get("budget_milestones") or {}).get("1") or {}
    check("hang_timeout end-of-session milestone", ms.get("turn") is None and abs(ms.get("spend", -1) - round(0.95 + hang, 6)) < 1e-9
          and (W.wr / "hang" / PROBLEM / "snapshots" / "1" / "state.json").exists() and any(e.get("type") == "budget_milestone" for e in tr), str(ms))

    # rule (a): gate 0.40; call 2 streams thinking until what a kill would charge, S + c_in + 20e-6·2·1.5·think, + 0.05 >= 0.40 (think = 1500)
    p, d, rd, end = W.driver("kill_a", "kill_a", ["--budget-usd", "0.40"])
    r = runs_entry(W.state("kill_a"), "selftest-cc-kill_a"); k = ((r.get("meter") or {}).get("kill") or {})
    s_in = price(2, w1=12500, out=2000) + price(2, w1=15000)
    check("kill_a killed by rule (a) at the first event past G - M", not end and "stopped:gate:a" in (r.get("flags") or [])
          and k.get("exposure", 0) + 0.05 >= 0.40 and k.get("exposure", 1) + 0.05 < 0.40 + 20e-6 * 2 * 1.5 * 100 + 1e-9, str(k))
    chg = r.get("spend_usd_list", 9)
    check("kill_a charge within G (the gate tests what a kill charges)", s_in + 20e-6 * 2 * 1.5 * 1500 - 1e-9 <= chg <= 0.40 + 1e-9, f"charge {chg}")

    # rule (c): gate 0.30; after call 1 (S = 0.140) the next-call reserve max(0.10, 1.25·0.100) does not fit
    p, d, rd, end = W.driver("kill_c", "kill_c", ["--budget-usd", "0.30"])
    r = runs_entry(W.state("kill_c"), "selftest-cc-kill_c")
    # round-2 review (2026-10-12): the kill fires on the tool_result the CLI emits as it sends the next request, so it may lose that race: the
    # charge is S plus the reserve R_next = max(0.10, 1.25 * 0.100), flagged c-reserve-booked, and still within G
    s1 = price(2, w1=12500, out=2000); rn = max(0.10, 1.25 * price(2, w1=12500, out=0)); chg = r.get("spend_usd_list", -1)
    check("kill_c killed by rule (c) before the next request, charged S + the raced reserve", not end and "stopped:gate:c" in (r.get("flags") or [])
          and "c-reserve-booked" in (r.get("flags") or []) and (r.get("meter") or {}).get("calls") == 1
          and abs(chg - round(s1 + rn, 6)) < 1e-6 and chg <= 0.30, str(r)[:400])

    # no result event: charged S, flagged
    p, d, rd, end = W.driver("noresult", "noresult", ["--budget-usd", "2.85"])
    r = runs_entry(W.state("noresult"), "selftest-cc-noresult")
    nr = price(2, w1=3000, cr=12000, out=400) + price(2, w1=700, cr=15000, out=250)
    check("no_result charged S and flagged", end and r.get("flags") == ["no-result"] and abs(r.get("spend_usd_list", -1) - round(nr, 6)) < 1e-9,
          f"{r.get('flags')} {r.get('spend_usd_list')} vs {nr}")

    # skip: $2.80 already spent -> no session
    W.seed("skip", api_spend=2.80)
    p, d, rd, end = W.driver("skip", "record", ["--budget-usd", "2.85"], fresh=False)
    st = W.state("skip")
    check("skip: budget reached, no session", d is None and "budget reached" in p.stdout and st.get("runs") == [] and st.get("api_spend") == 2.80, p.stdout[-300:])

    # orphaned tools (review 2026-10-12): two detached "compiles" that read state.json, one still a child of claude, one double-forked away;
    # the rule (c) kill must take both before they write their stale copy back over the ledger
    p, d, rd, end = W.driver("orphan", "orphan", ["--budget-usd", "0.30"])
    time.sleep(3.5)   # past the moment a survivor would write
    st = W.state("orphan"); r = runs_entry(st, "selftest-cc-orphan"); c1 = price(2, w1=12500, out=2000)
    surv = sorted(f.name for f in W.dump.glob("orphan-*-survived"))
    check("orphan: detached tool processes killed with the session tree", d is not None and not surv and "stopped:gate:c" in (r.get("flags") or []), str(surv))
    rn = ((r.get("meter") or {}).get("kill") or {}).get("r_next") or 0   # round-2 review: a tool_result kill books the reserve it raced
    check("orphan: ledger intact after the kill (api_spend, ended, no pending)", abs(st.get("api_spend", -1) - round(c1 + rn, 6)) < 1e-9 and r.get("ended")
          and "pending" not in r and rn > 0, f"{st.get('api_spend')} vs {c1} + {rn}; {r}")

    # SIGTERM to the driver (an arm `timeout` signals the driver's group, not claude's session): the session is killed and charged
    W.seed("sigterm")
    for f in W.dump.glob("*"):
        f.unlink()
    cmd = [sys.executable, str(ROOT / "harness/agent_claude_code.py"), "--problems", PROBLEM, "--workers", "1", "--work-root", str(W.wr / "sigterm"),
           "--run-id", "selftest-cc-sigterm", "--effort", "xhigh", "--budget-usd", "2.85", "--timeout", "120"]
    q = subprocess.Popen(cmd, cwd=ROOT, env=dict(W.env, LRA_FAKE_CC="hang"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    t0 = time.time()
    while not list(W.dump.glob("hang-[0-9]*.json")) and time.time() - t0 < 30:
        time.sleep(0.1)
    time.sleep(1.0); q.send_signal(signal.SIGTERM)
    try:
        qo, qe = q.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        q.kill(); qo, qe = q.communicate()
    src = ROOT / "probe/runs/selftest-cc-sigterm"
    if src.exists():
        shutil.rmtree(W.runs / "sigterm", ignore_errors=True); shutil.move(str(src), str(W.runs / "sigterm"))
    st = W.state("sigterm"); r = runs_entry(st, "selftest-cc-sigterm")
    hang = price(2, w1=5000, cr=12000) + 20e-6 * max(2 * 1.5 * 500, 2000)
    check("sigterm: driver exits 143 after killing and charging the session", q.returncode == 143 and "stopped:signal" in (r.get("flags") or [])
          and abs(r.get("spend_usd_list", -1) - round(hang, 6)) < 1e-9 and abs(st.get("api_spend", -1) - round(hang, 6)) < 1e-9 and "pending" not in r
          and time.time() - t0 < 80, f"rc {q.returncode} {r.get('flags')} {r.get('spend_usd_list')} vs {hang}; {qo[-300:]} {qe[-300:]}")

    # a session whose driver died (no end, pending pre-charge): its gate stays booked, the entry is flagged, the gate shrinks accordingly
    W.seed("stale", api_spend=1.20, runs=[{"run_id": "dead", "model": "x", "pending": True, "gate_usd": 1.0}])
    p, d, rd, end = W.driver("stale", "record", ["--budget-usd", "2.85"], fresh=False)
    st = W.state("stale"); dead = runs_entry(st, "dead"); rec = price(2, w1=4000, cr=12000, out=50)
    check("stale pending entry: flagged driver-died, kept charged, next gate from it", dead.get("pending") is False and "driver-died" in (dead.get("flags") or [])
          and dead.get("spend_usd_list") == 1.0 and abs(st.get("api_spend", -1) - round(1.20 + rec, 6)) < 1e-9 and d is not None
          and d["argv"][d["argv"].index("--max-budget-usd") + 1] == "1.6500", f"{dead} {st.get('api_spend')}")

    # > 200 checks after a new best: best_so_far comes from the live best at each call's close, not the truncated attempts
    p, d, rd, end = W.driver("trunc", "trunc", ["--budget-usd", "2.85"])
    st = W.state("trunc"); turns = [e for e in W.traj(rd) if e.get("type") == "turn"]
    check("trunc: best_so_far survives the 200-attempt cap", st["best"]["score"] == 60.0 and not any(a.get("score") for a in st["attempts"])
          and len(turns) == 2 and turns[-1]["best_so_far"] == 60.0, str([t.get("best_so_far") for t in turns]))


def test_escalation(W: World) -> None:
    """R3: a resume whose previous session gained < 0.5 over >= 4 checks starts from the reference with a facts sheet (best kept, no stored
    proof text, no Lean block over 2 lines); right after such a session the next one resumes with the lever review instead."""
    from harness.leantools import ROWS
    stmt = ROWS[PROBLEM]["statement"]
    best = {"score": 40.2, "proof": stmt + " := by\n  simp -- STOREDBEST", "tokens": 10, "heartbeats": 100}
    att = [{"sha": f"e{k}", "ok": False, "error": "4:2: unsolved goals ⊢ x", "run_id": "earlier", "t": "2026-10-12T00:00:0%dZ" % k} for k in range(5)]
    notes = "# Notes\n## Failed\n- grind in the step case [tested: lean_check -> FAIL]\n```lean\n  have h := 1\n  simp at h\n  exact h\n```\n## Next\n- try fun_induction\n"
    # round-2 review (2026-10-12): afterfresh = an adopted fresh lineage merged after that session (no runs[] entry): no escalation either
    for label, prev, esc, more in (("escalate", {"run_id": "earlier", "model": "x", "best_before": 40.0, "best_after": 40.2}, True, {}),
                                   ("afterscout", {"run_id": "earlier", "model": "x", "best_before": 40.0, "best_after": 40.2, "mode": "escalated"}, False, {}),
                                   ("afterfresh", {"run_id": "earlier", "model": "x", "best_before": 40.0, "best_after": 40.2, "ended": "2026-10-12T01:00:00Z"},
                                    False, {"fresh_lineages": [{"run_id": "x-f2", "score": 40.2, "adopted": True, "t": "2026-10-12T02:00:00Z"}]})):
        W.seed(label, best=best, attempts=att, runs=[prev], ledger={"wins": [{"run_id": "earlier", "check": 2, "d_score": 0.2, "d_tokens": -1,
                                                                             "d_heartbeats": 0, "diff": "-  omega\n+  simp -- STOREDBEST"}]}, **more)
        (W.wr / label / PROBLEM / "notes.md").write_text(notes)
        p, d, rd, _ = W.driver(label, "record", ["--prompt", "v2", "--no-library-leads", "--no-heartbeat-map"], fresh=False)
        if not check(f"r2_session {label} ran", d is not None and p.returncode == 0, p.stderr[-500:]):
            continue
        pr = d["argv"][d["argv"].index("-p") + 1]; st = W.state(label); r = runs_entry(st, f"selftest-cc-{label}")
        hd = next((x for x in W.traj(rd) if x.get("type") == "header"), {})
        if esc:
            check("r2_session escalate: from the reference with a facts sheet, best kept", "SCOUT RUN" in pr and "FACTS SHEET" in pr
                  and "[Lean block of 3 lines omitted]" in pr and "STOREDBEST" not in pr and "LEVER REVIEW FIRST" not in pr and "try fun_induction" in pr
                  and "unsolved goals: 5" in pr and r.get("mode") == "escalated" and hd.get("escalated") is True and "facts" in (hd.get("sections") or [])
                  and st["best"]["score"] == 40.2 and "STOREDBEST" in st["best"]["proof"] and "escalation:" in p.stdout
                  and r.get("best_before") == 40.2 and r.get("best_after") == 40.2, str(r)[:300] + p.stdout[-300:])
        else:
            check(f"r2_session {label}: " + ("no second escalation in a row" if label == "afterscout" else "no escalation right after a fresh lineage")
                  + " (lever review)", "SCOUT RUN" not in pr and "LEVER REVIEW FIRST" in pr
                  and "HEARTBEAT LEVERS" in pr and "STOREDBEST" in pr and not r.get("mode") and hd.get("escalated") is False, str(r)[:300])


def test_exemplars_session(W: World) -> None:
    """§13 --exemplars with the fake claude (no Lean): the executor prompt shows <work root>/_exemplars/<ws>.md as WHAT WORKED ON THE STRONGEST
    ROWS while the stored best is below the file's target (runs[] exemplars_seen = the sha it was built for, the trajectory header's sections);
    a file of an earlier best is shown marked stale (exemplars_stale); nothing without the flag or at the target; a first-version
    <ws>/exemplars.md is never shown; every v2 session denies Read on <work root>/_exemplars (review 2026-10-13)."""
    from harness import exemplars as EX, cc_levers as LV
    from harness.leantools import ROWS
    best = {"score": 61.0, "proof": ROWS[PROBLEM]["statement"] + " := by\n  simp -- EXBEST", "tokens": 10, "heartbeats": 100}
    sha = LV.proof_sha(best["proof"]); seen = {}
    for label, file_sha, flag, score in (("ex-on", sha, True, 61.0), ("ex-other", "0" * 12, True, 61.0), ("ex-off", sha, False, 61.0),
                                         ("ex-at", sha, True, 90.0)):
        d = W.seed(label, best=dict(best, score=score)); fp = EX.path_for(d); fp.parent.mkdir(exist_ok=True)
        fp.write_text(EX.header(file_sha, "t", 90, 2, 1) + "\nSTRONGEST ROWS STYLE (x):\n- EXMARK simp_all: 0.0 there vs 4.2 here\n")
        (d / EX.FILE).write_text(EX.header(sha, "t", 90, 2, 1) + "\nLEGACYMARK\n")
        p, dd, rd, _ = W.driver(label, "record", ["--prompt", "v2", "--no-library-leads", "--no-heartbeat-map", *(["--exemplars"] if flag else [])],
                                fresh=False)
        a = dd["argv"] if dd else []; pr = a[a.index("-p") + 1] if dd else ""
        deny = a[a.index("--disallowedTools") + 1:a.index("--add-dir") if "--add-dir" in a else a.index("--permission-mode")] if dd else []
        hd = next((x for x in W.traj(rd) if x.get("type") == "header"), {}); r = runs_entry(W.state(label), f"selftest-cc-{label}")
        seen[label] = ("WHAT WORKED ON THE STRONGEST ROWS" in pr and "EXMARK" in pr, r.get("exemplars_seen"), r.get("exemplars_stale"),
                       "exemplars" in (hd.get("sections") or []), "LEGACYMARK" in pr, any(x.endswith(f"/{EX.XDIR}/**)") for x in deny), p.returncode)
    check("exemplars: the block and runs[] exemplars_seen below the target only with --exemplars, a file of an earlier best marked stale, "
          "never the first version's <ws>/exemplars.md, Read on _exemplars denied",
          seen == {"ex-on": (True, sha, None, True, False, True, 0), "ex-other": (True, "0" * 12, True, True, False, True, 0),
                   "ex-off": (False, None, None, False, False, True, 0), "ex-at": (False, None, None, False, False, True, 0)}, str(seen))


def test_hx(W: World, normal_run: Path) -> None:
    """hx_heldout --driver claude: the session argv, and curve() over the trajectory the driver wrote (turn events)."""
    import types
    from harness import hx_heldout as hx
    a = types.SimpleNamespace(driver="claude", claude_model="claude-opus-5-5", claude_prompt="v2", claude_cache="5m", claude_sealed=True)
    c = hx.session_cmd(a, 2.85, "harness/hwork/x", "abpool-hx-t-r1", [PROBLEM], 2, "xhigh", True, [])
    arg = lambda k: c[c.index(k) + 1]
    check("hx session_cmd claude v2 (gate, prompt, cache, effort, restructure, sealed)", c[:2] == ["python3", "harness/agent_claude_code.py"]
          and arg("--budget-usd") == "2.85" and arg("--prompt") == "v2" and arg("--cache-ttl") == "5m" and arg("--effort") == "xhigh"
          and arg("--workers") == "2" and "--from-reference" in c and "--sealed" in c and c[-2:] == ["--problems", PROBLEM], str(c))
    a.claude_prompt, a.claude_sealed = "v1", False
    c = hx.session_cmd(a, 2.0, "harness/hwork/x", "abpool-hx-t-r1", [PROBLEM], 2, "high", True, [])
    check("hx session_cmd claude v1 (no --from-reference, not sealed)", "--from-reference" not in c and "--sealed" not in c and arg("--budget-usd") == "2.0")
    cw = W.T / "cw"; dd = cw / "probe/runs/selftest-cc-hx-r1/trajectories"; dd.mkdir(parents=True, exist_ok=True)
    shutil.copy(normal_run / "trajectories" / f"{PROBLEM}.jsonl.gz", dd / f"{PROBLEM}.jsonl.gz")
    C = hx.curve(types.SimpleNamespace(names=[PROBLEM], wt=cw, run_prefix="selftest-cc-hx-r"), [0.001, 2.85])
    check("hx curve() reads the driver's turn events", C[PROBLEM][2.85] == 52.0 and C[PROBLEM][0.001] == 33.33, str(C))


def test_hx_r2(W: World) -> None:
    """hx_heldout --driver claude after every batch (round 2): the commands, the defaults, the Phase A argv, and a real run of discover
    --ledger-only and inrun.py on a temp line (records under probe/runs/selftest-cc-disc-r1, removed at the end like every selftest run)."""
    import types
    from harness import hx_heldout as hx
    from harness.leantools import ROWS
    NS = types.SimpleNamespace
    cw = W.T / "hxr2"
    # round-2 review (2026-10-12): other arms whose names extend this one (x-rerun, x-fast, x-pass2) are never this line's runs
    for rid, ver in (("ab-hx-x-r1", True), ("ab-hx-x-f1", False), ("ab-hx-x-p1", True), ("ab-hx-x-r2", False), ("ab-hx-x-rerun-r1", True),
                     ("ab-hx-x-fast-r1", True), ("ab-hx-x-pass2-r1", True), ("ab-hx-x-pass2-r2", False)):
        (cw / "probe/runs" / rid).mkdir(parents=True, exist_ok=True)
        if ver:
            (cw / "probe/runs" / rid / "verified.jsonl").write_text("{}\n")
    S = NS(wt=cw, root="harness/hwork/ab-x", run_prefix="ab-hx-x-r"); got = []
    run = lambda cmd, cwd, timeout, say, tag: got.append((cmd, cwd, timeout, tag)) or 0
    hx.cc_after_batch(S, NS(claude_prompt="v2", claude_inrun=None, claude_polish=True, post_timeout=1200), 2, [PROBLEM], print, run=run)
    c = [g[0] for g in got]
    check("r2_hx after-batch commands (polish, ledger-only discover over runs with records, techniques)",
          [x[1] for x in c] == ["harness/hb_polish.py", "harness/discover.py", "harness/inrun.py"] and c[0][c[0].index("--run-id") + 1] == "ab-hx-x-p2"
          and c[0][-2:] == ["--problems", PROBLEM] and c[1][c[1].index("--runs") + 1] == "ab-hx-x-r1,ab-hx-x-p1" and "--ledger-only" in c[1]
          and "--allow-mixed" in c[1] and c[2][c[2].index("--runs") + 1] == "ab-hx-x-r1,ab-hx-x-f1,ab-hx-x-p1,ab-hx-x-r2"
          and c[1][c[1].index("--work-root") + 1] == S.root and all(g[1] == cw for g in got) and got[0][2] == 1200, str(c))
    check("r2_hx line runs by exact name (no other arm's runs)", [p.name for p in hx.rounds(S)] == ["ab-hx-x-r1", "ab-hx-x-r2"]
          and [p.name for p in hx.fresh_rounds(S)] == ["ab-hx-x-f1"] and [p.name for p in hx.polish_rounds(S)] == ["ab-hx-x-p1"],
          str([p.name for p in hx.line_runs(S)]))
    got.clear(); hx.cc_after_batch(S, NS(claude_prompt="v1", claude_inrun=None, claude_polish=False), 2, [PROBLEM], print, run=run)
    check("r2_hx in-run learning off by default under v1, on when asked", not got and hx.inrun_on(NS(claude_prompt="v1", claude_inrun=True))
          and not hx.inrun_on(NS(claude_prompt="v2", claude_inrun=False)) and hx.inrun_on(NS(claude_prompt="v2", claude_inrun=None)))
    sh = subprocess.run(["bash", "-n", str(ROOT / "probe/abpool/run_phase_a.sh")], capture_output=True, text=True, timeout=60)
    pa = ["--set", "abpool", "--arm", "ccA2", "--ref", "HEAD", "--driver", "claude", "--claude-sealed", "--claude-prompt", "v2", "--claude-effort", "xhigh",
          "--claude-cache", "5m", "--problems", PROBLEM, "--rungs", "2.85", "--max-rounds", "1", "--no-lineage-rule", "--workers", "2"]
    n2 = hx.build_parser().parse_args(pa); n1 = hx.build_parser().parse_args([x if x != "v2" else "v1" for x in pa])
    check("r2_hx Phase A argv parses: in-run on for the v2 arms only, no polish", sh.returncode == 0 and hx.inrun_on(n2) and not hx.inrun_on(n1)
          and not n2.claude_polish and n2.post_timeout == 3600, sh.stderr[-300:])
    # the real tools on a temp line: two verified records (the first best, then an edit) -> one ledger win; a techniques file in the work root
    wr = W.T / "hxline"; d = wr / PROBLEM; d.mkdir(parents=True)
    stmt = ROWS[PROBLEM]["statement"]; p1 = stmt + " := by\n  simp\n  omega"; p2 = stmt + " := by\n  simp\n  grind"
    rid = "selftest-cc-disc-r1"; vd = ROOT / "probe/runs" / rid; vd.mkdir(parents=True, exist_ok=True)
    rec = lambda proof, sc, k: {"problem": PROBLEM, "proof": proof, "score": sc, "tokens": 3, "heartbeats": 900 - 100 * k,
                                "provenance": {"kind": "closed-dev-only", "model": "claude-opus-5-5@claude-code", "run_id": rid, "mode": "agent-cc-v2", "check": k}}
    (vd / "verified.jsonl").write_text(json.dumps(rec(p1, 50.0, 1)) + "\n" + json.dumps(rec(p2, 52.0, 2)) + "\n")
    (d / "state.json").write_text(json.dumps({"problem": PROBLEM, "best": {"score": 52.0, "proof": p2}, "attempts": [], "runs": []}))
    for f, t in (("original.lean", ROWS[PROBLEM]["src"]), ("context.lean", ROWS[PROBLEM]["header"]), ("notes.md", "# Notes\n- GENERAL: prefer omega\n")):
        (d / f).write_text(t)
    # round-2 review: a truncated gzip trajectory (a driver killed mid-append) is read up to the damage and counted, never a traceback
    (vd / "trajectories").mkdir(exist_ok=True); dmg = vd / "trajectories" / "zz_damaged.jsonl.gz"
    with gzip.open(dmg, "wt") as h:
        for k in range(3000):
            h.write(json.dumps({"type": "header", "problem": "none"} if k == 0 else {"type": "user", "k": k, "pad": "x" * 60}) + "\n")
    dmg.write_bytes(dmg.read_bytes()[: dmg.stat().st_size // 2])
    logs: list = []
    hx.cc_after_batch(NS(wt=ROOT, root=str(wr), run_prefix="selftest-cc-disc-r"), NS(claude_prompt="v2", claude_inrun=None, claude_polish=False), 1,
                      [PROBLEM], logs.append)
    wins = (json.loads((d / "state.json").read_text()).get("ledger") or {}).get("wins") or []
    tf = wr / "_run_techniques.json"
    check("r2_hx real discover --ledger-only + run techniques on a temp line (counts-only log lines)", len(wins) == 1 and wins[0]["diff"] == "-  omega\n+  grind"
          and tf.exists() and json.loads(tf.read_text()).get("notes") == ["prefer omega"] and any("mined chains end at the stored best" in x for x in logs)
          and any("run techniques:" in x for x in logs) and not any(PROBLEM in x for x in logs), "\n".join(logs)[-1200:])
    check("r2_hx damaged trajectory: both steps go on and count it; ledger written atomically under the lock",
          any("1 damaged trajectory file(s)" in x for x in logs) and any("1 unreadable trajectory file(s) skipped" in x for x in logs)
          and not any("Traceback" in x for x in logs) and not list(d.glob(".state.json.tmp*")), "\n".join(logs)[-1200:])
    test_hx_recovery(W, hx, NS)


def test_hx_recovery(W: World, hx, NS) -> None:
    """Round-2 review (2026-10-12): a fresh lineage left unmerged by a dead ladder is merged at start-up (spend kept, best if higher) and
    archived; a SIGTERM to the ladder during a post-batch step kills the step (its own session) and then takes the default action."""
    cw = W.T / "hxrec"; root = "harness/hwork/ab-rec"
    m = cw / root / "P1"; f = cw / f"{root}-fresh" / "P1"; m.mkdir(parents=True); f.mkdir(parents=True)
    (m / "state.json").write_text(json.dumps({"problem": PROBLEM, "best": {"score": 50.0, "proof": "M"}, "attempts": [], "runs": [], "api_spend": 1.2}))
    (f / "state.json").write_text(json.dumps({"problem": PROBLEM, "best": {"score": 55.0, "proof": "F"}, "attempts": [], "api_spend": 2.7,
                                              "runs": [{"run_id": "ab-hx-rec-f3", "pending": True, "gate_usd": 1.5}], "lineage": "fresh"}))
    logs: list = []
    k = hx.recover_fresh(NS(wt=cw, root=root), logs.append)
    st = json.loads((m / "state.json").read_text()); fl = (st.get("fresh_lineages") or [{}])[-1]
    check("r2_hx recovery: a dead ladder's fresh lineage merged (spend incl. its pre-charge, best), archived",
          k == 1 and st["api_spend"] == 2.7 and st["best"]["proof"] == "F" and fl.get("recovered") and fl.get("run_id") == "ab-hx-rec-f3"
          and not (cw / f"{root}-fresh").exists() and len(list(cw.glob("harness/hwork/ab-rec-fresh.done-recovered-*"))) == 1
          and hx.recover_fresh(NS(wt=cw, root=root), logs.append) == 0, f"{k} {st} {logs}")
    line = f"selftest-line-{os.getpid()}"
    code = ("import os, signal, sys, threading; sys.path.insert(0, %r); from harness import hx_heldout as hx; hx._LINE[0] = %r; "
            "threading.Timer(1.5, lambda: os.kill(os.getpid(), signal.SIGTERM)).start(); "
            "hx._bounded(['sleep', '60'], %r, 120, print, 't'); print('NOT KILLED')") % (str(ROOT), line, str(W.T))
    t0 = time.time(); p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=90)
    time.sleep(0.3); left = hx._kill_marked(f"LRA_POSTPASS_LINE={line}")
    check("r2_hx SIGTERM during a post-batch step: the step is killed with the ladder (default action kept)",
          p.returncode == -signal.SIGTERM and "NOT KILLED" not in p.stdout and left == 0 and time.time() - t0 < 30, f"rc {p.returncode} left {left} {p.stdout[-200:]}")


def test_review(W: World) -> None:
    """§11 the reviewer (agent_claude_code.py --review): no proof file written (Read-only argv; every workspace file byte-identical, review.md the
    only new file), its own gate pre-charged and charged to the problem's ledger (runs[] kind review), review.md linted and bound to the best's
    sha; the next executor session shows the REVIEW block and does not escalate, the one after it no longer shows it; a session without a result
    event saves its complete text flagged partial; no stored best: skipped, effort high by default; refusals; --ceiling lifts the $2.85 cap."""
    from harness import prompt_v2 as pv, cc_levers as LV
    from harness.leantools import ROWS
    proof = ROWS[PROBLEM]["statement"] + " := by\n  simp -- STOREDBEST"; sha = LV.proof_sha(proof)
    att = [{"sha": f"e{k}", "ok": False, "error": "4:2: unsolved goals ⊢ x", "run_id": "earlier", "t": "2026-10-12T00:00:0%dZ" % k} for k in range(5)]
    prev = {"run_id": "earlier", "model": "x", "best_before": 40.0, "best_after": 40.2, "started": "2026-10-12T00:00:00Z", "ended": "2026-10-12T00:30:00Z"}
    d = W.seed("review", best={"score": 40.2, "proof": proof, "tokens": 10, "heartbeats": 100}, attempts=att, runs=[prev], api_spend=1.20)
    for f, t in (("candidate.lean", "-- a work in progress, not the best\n"), ("best.lean", proof + "\n"), ("v1.lean", "-- a variant\n"),
                 ("original.lean", ROWS[PROBLEM]["src"].rstrip() + "\n"), ("context.lean", ROWS[PROBLEM]["header"]),
                 ("notes.md", "# Notes\n## Next\n- try omega in the step case\n")):
        (d / f).write_text(t)
    before = {f.name: f.read_bytes() for f in d.iterdir() if f.is_file() and f.name != "state.json"}
    p, dd, rd, end = W.driver("review", "review", ["--prompt", "v2", "--review", "--budget-usd", "2.85", "--cache-ttl", "5m"], fresh=False)
    cost = price(2, w5=9000, cr=12000, out=1500)
    if not check("review ran", dd is not None and p.returncode == 0 and end, p.stdout[-500:] + p.stderr[-500:]):
        return
    a = dd["argv"]; allow = a[a.index("--allowedTools") + 1:a.index("--disallowedTools")]; pr = a[a.index("-p") + 1]
    check("review argv: Read only on the workspace (no Bash / Edit / Write rule, no --add-dir), dontAsk, REVIEW_SYSTEM, gate $0.30",
          a[a.index("--tools") + 1] == "Read" and allow and all(x.startswith("Read(/") for x in allow) and any(PROBLEM in x for x in allow)
          and "--add-dir" not in a and a[a.index("--permission-mode") + 1] == "dontAsk" and a[a.index("--system-prompt") + 1] == pv.REVIEW_SYSTEM
          and a[a.index("--max-budget-usd") + 1] == "0.3000" and dd["env"].get("LRA_MODE") == "agent-cc-v2-review" and "LRA_CHECK_V2" not in dd["env"]
          and dd["lra_env_json"] is None, str(allow) + str(a[-8:]))
    check("review prompt: reference, the line-numbered best with its sha, facts, task (the reviewer sees the best)",
          "original.lean (the REFERENCE proof)" in pr and "best.lean (the CURRENT BEST" in pr and "STOREDBEST" in pr and f"sha {sha}" in pr
          and "FACTS from this problem's records" in pr and "try omega in the step case" in pr and "YOUR REVIEW" in pr)
    after = {f.name: f.read_bytes() for f in d.iterdir() if f.is_file() and f.name not in ("state.json", ".state.lock")}   # the ledger's lock file
    check("review writes no proof file: every workspace file byte-identical, review.md the only new file",
          {k: v for k, v in after.items() if k != "review.md"} == before and set(after) - set(before) == {"review.md"}, str(set(after) ^ set(before)))
    s0 = dd.get("state_at_start") or {}; r0 = runs_entry(s0, "selftest-cc-review")
    check("review gate pre-charged in the ledger during the session (spend0 + $0.30, pending, kind review)",
          abs(s0.get("api_spend", -1) - 1.50) < 1e-9 and r0.get("pending") is True and r0.get("gate_usd") == 0.3 and r0.get("kind") == "review", str(r0))
    st = W.state("review"); r = runs_entry(st, "selftest-cc-review")
    check("review charged to the problem's ledger (runs[] kind review, review_of the best's sha, lint counts)",
          abs(st.get("api_spend", -1) - round(1.20 + cost, 6)) < 1e-9 and abs(r.get("spend_usd_list", -1) - round(cost, 6)) < 1e-9
          and r.get("kind") == "review" and r.get("review_of") == sha and r.get("review_saved") is True and "pending" not in r and r.get("flags") == []
          and r.get("review_lint") == {"levers": 3, "blocks_removed": 1, "claims_removed": 1, "truncated": False}
          and (r.get("driver") or {}).get("gate_usd") == 0.3, str(r)[:600])
    meta, body = LV.parse_review((d / "review.md").read_text()) or ({}, "")
    check("review.md: bound to the best's sha, Lean blocks over 2 lines and the optimality claim removed, the 2-line block kept",
          meta.get("best_sha") == sha and meta.get("run") == "selftest-cc-review" and meta.get("partial") == "0" and "[Lean block of 4 lines omitted]" in body
          and "  all_goals omega\n  exact h" in body and "induction x" not in body and LV.CLAIM_MARK in body and "near-optimal" not in body
          and LV.lean_block_lines(body) <= 2 and LV.lean_block_lines(LV.reindent(body)) <= 2, body[:600])
    tr = W.traj(rd); hd = next((x for x in tr if x.get("type") == "header"), {}); turns = [e for e in tr if e.get("type") == "turn"]
    check("review trajectory: header kind review, turn events sum to the charge", hd.get("kind") == "review" and hd.get("review_of") == sha
          and "task" in (hd.get("sections") or []) and abs(sum(e["cost"] for e in turns) - round(cost, 6)) < 1e-9, str(hd)[:300])
    # the next executor session: the REVIEW block; the escalation rule would fire (gain 0.2 over 5 checks, gate $1.57) but the review comes first
    p, dd, rd, _ = W.driver("review", "record", ["--prompt", "v2", "--no-library-leads", "--no-heartbeat-map", "--budget-usd", "2.85"],
                            run_id="selftest-cc-review-r2", fresh=False)
    pr = dd["argv"][dd["argv"].index("-p") + 1] if dd else ""; r2 = runs_entry(W.state("review"), "selftest-cc-review-r2")
    hd = next((x for x in W.traj(rd) if x.get("type") == "header"), {})
    check("review shown to the next executor session (REVIEW block after the lever review, no escalation)", "REVIEW (fresh eyes)" in pr
          and "1. Replace the closer" in pr and f"sha {sha}" in pr and "SCOUT RUN" not in pr and "LEVER REVIEW FIRST" in pr
          and pr.index("LEVER REVIEW FIRST") < pr.index("REVIEW (fresh eyes)") and "review" in (hd.get("sections") or [])
          and hd.get("escalated") is False and r2.get("review_seen") == sha and not r2.get("mode")
          and "a fresh review of the stored best is waiting" in p.stdout, p.stdout[-600:])
    arch = rd / "reviews" / f"{PROBLEM}.md"
    check("review leaves the workspace with the session that is shown it (kept in that run's reviews/)", not (d / "review.md").exists()
          and arch.exists() and (LV.parse_review(arch.read_text()) or ({}, ""))[0].get("best_sha") == sha)
    p, dd, _, _ = W.driver("review", "record", ["--prompt", "v2", "--no-library-leads", "--no-heartbeat-map", "--budget-usd", "2.85"],
                           run_id="selftest-cc-review-r3", fresh=False)
    pr = dd["argv"][dd["argv"].index("-p") + 1] if dd else "x"
    check("review not shown again once an executor session has used it", dd is not None and "REVIEW (fresh eyes)" not in pr
          and not runs_entry(W.state("review"), "selftest-cc-review-r3").get("review_seen"))
    # a reviewer session without a result event: the complete text block saved, flagged partial; no-result in the ledger
    d = W.seed("review_cut", best={"score": 40.2, "proof": proof, "tokens": 10, "heartbeats": 100})
    p, dd, _, _ = W.driver("review_cut", "review_cut", ["--prompt", "v2", "--review"], fresh=False)
    r = runs_entry(W.state("review_cut"), "selftest-cc-review_cut"); meta = (LV.parse_review((d / "review.md").read_text()) or ({}, ""))[0] if (d / "review.md").exists() else {}
    check("review without a result event: text saved flagged partial, no-result in the ledger, gate default cap $2.85",
          meta.get("partial") == "1" and meta.get("best_sha") == sha and r.get("review_partial") is True and "no-result" in (r.get("flags") or [])
          and dd is not None and dd["argv"][dd["argv"].index("--max-budget-usd") + 1] == "0.3000", str(r)[:400])
    # review 2026-10-12: a best with >= 2 H points left: the reviewer gets its HEARTBEAT MAP (here from the profile cache: no Lean) and the task
    # points to it; with --no-heartbeat-map and no cached profile the task does not point to a map
    prof = {"ok": True, "total": 60000, "floor": 9000, "reference": 134548, "points_left_heartbeats": 12.6,
            "blocks": [{"lines": "2-2", "heartbeats": 50000, "text": "simp -- STOREDBEST"}]}
    W.seed("review_map", best={"score": 45.0, "proof": proof, "tokens": 10, "heartbeats": 60000}, profile_cache={sha: prof})
    W.seed("review_nomap", best={"score": 45.0, "proof": proof, "tokens": 10, "heartbeats": 60000})
    _, dm, rdm, _ = W.driver("review_map", "review", ["--prompt", "v2", "--review"], fresh=False)
    _, dn, _, _ = W.driver("review_nomap", "review", ["--prompt", "v2", "--review", "--no-heartbeat-map"], fresh=False)
    pm = dm["argv"][dm["argv"].index("-p") + 1] if dm else ""; pn = dn["argv"][dn["argv"].index("-p") + 1] if dn else ""
    hm = next((x for x in W.traj(rdm) if x.get("type") == "header"), {})
    check("review heartbeat map: shown when >= 2 H points are left (cached profile of the best), the task points to it; without one it does not",
          "HEARTBEAT MAP of best.lean (heartbeat_profile, cached" in pm and "lines 2-2: 50000 hb" in pm and "blocks of the map" in pm
          and "heartbeat_map" in (hm.get("sections") or []) and "HEARTBEATS FIRST" in pn and "HEARTBEAT MAP" not in pn and "blocks of the map" not in pn
          and "no map was measured" in pn and W.state("review_nomap").get("profile_cache") in (None, {}), pm[-400:] + pn[-400:])
    # the answer's source: the result text; an errored session never; without a result the last message's complete text blocks (API error
    # messages left out)
    from harness.agent_claude_code import review_text
    ev = lambda mid, t, **x: json.dumps({"type": "assistant", "message": {"id": mid, "content": [{"type": "text", "text": t}]}, **x})
    out = "\n".join([ev("m1", "first"), ev("m2", "1. lever"), ev("m2", "2. lever"), ev("m3", "usage limit reached", isApiErrorMessage=True)])
    check("review_text: result text, nothing from an errored session, else the last message's blocks (partial), API errors ignored",
          review_text(out, {"result": "1. x"}) == ("1. x", False) and review_text(out, {"is_error": True, "result": "usage limit"}) == ("", False)
          and review_text(out, None) == ("1. lever\n2. lever", True) and review_text("", None) == ("", True))
    # no stored best: skipped before any session; effort high by default
    W.seed("review_none")
    for f in W.dump.glob("*"):
        f.unlink()
    q = subprocess.run([sys.executable, str(ROOT / "harness/agent_claude_code.py"), "--problems", PROBLEM, "--workers", "1", "--work-root",
                        str(W.wr / "review_none"), "--run-id", "selftest-cc-review-none", "--prompt", "v2", "--review"], cwd=ROOT,
                       env=dict(W.env, LRA_FAKE_CC="record"), capture_output=True, text=True, timeout=120)
    check("review skipped without a stored best (no session), effort high by default", q.returncode == 0 and "review skipped: no stored best" in q.stdout
          and "effort high" in q.stdout and "REVIEWER (gate $0.30" in q.stdout and not list(W.dump.glob("record-*.json"))
          and W.state("review_none").get("runs") == [], q.stdout[-400:] + q.stderr[-300:])
    for label, extra in (("refuse-review-v1", ["--review"]), ("refuse-review-seed", ["--prompt", "v2", "--review", "--seed-dir", str(W.T)]),
                         ("refuse-ceiling", ["--ceiling"])):
        p, dd, _, _ = W.driver(label, "record", extra, fresh=False)
        check(f"review / ceiling refuses {' '.join(extra[:4])}", p.returncode == 2 and dd is None, p.stderr[-300:])
    # --ceiling: the gate is the rung minus the ledger, beyond $2.85 (a ceiling measurement); without it the $2.85 cap holds
    W.seed("ceiling", api_spend=2.0); W.seed("capped", api_spend=2.0)
    p, dd, _, _ = W.driver("ceiling", "record", ["--budget-usd", "4.5", "--ceiling"], fresh=False)
    p2, dd2, _, _ = W.driver("capped", "record", ["--budget-usd", "4.5"], fresh=False)
    check("ceiling: --ceiling lifts the cap to the rung ($4.50 - $2.00), recorded in the run entry; capped otherwise ($2.85 - $2.00)",
          dd is not None and dd["argv"][dd["argv"].index("--max-budget-usd") + 1] == "2.5000" and dd2 is not None
          and dd2["argv"][dd2["argv"].index("--max-budget-usd") + 1] == "0.8500"
          and (runs_entry(W.state("ceiling"), "selftest-cc-ceiling").get("driver") or {}).get("ceiling") is True
          and "CEILING measurement" in p.stdout, p.stdout[-300:] + p2.stdout[-300:])


def test_hx_review(W: World) -> None:
    """hx --claude-review end to end with the fake claude (§11): round 1 (an executor batch at $0.90), then ONE reviewer batch for round 2's
    rows (run -v2, its spend charged to the row before round 2), then round 2 at $1.80 (--round-per-rung) whose prompt carries the REVIEW block;
    no review after the last round; the reviews' spend in the turn events; next_plan's cases. setup_worktree is stubbed, the work root is a temp
    dir, the driver runs with the fake claude (leads and heartbeat map off: no Lean)."""
    from harness import hx_heldout as hx, cc_levers as LV
    from harness.leantools import ROWS
    import types
    T = W.T / "hxrev"; root = T / "work"; out = T / "out"

    class TSet:
        def __init__(self, key, arm):
            self.rows_rel = "selftest"; self.rows = [ROWS[PROBLEM]]; self.names = [PROBLEM]; self.hb_path = None; self.prefix = "selftest-cc"
            self.ref_log = None; self.wt = ROOT; self.root = str(root); self.run_prefix = f"selftest-cc-hx-{arm}-r"; self.out = out
    real_run = subprocess.run; calls: list = []; order = iter(["normal", "review", "record"])

    def fake_run(cmd, *a, **k):
        if isinstance(cmd, list) and cmd[:2] == ["python3", "harness/agent_claude_code.py"]:
            sc = next(order, "record"); calls.append((sc, list(cmd)))
            c = [sys.executable, str(ROOT / "harness/agent_claude_code.py"), *cmd[2:]]
            if "--review" not in c:
                i = c.index("--problems"); c[i:i] = ["--no-library-leads", "--no-heartbeat-map"]
            return real_run(c, *a, **dict(k, cwd=ROOT, env=dict(W.env, LRA_FAKE_CC=sc)))
        return real_run(cmd, *a, **k)
    for f in W.dump.glob("*"):
        f.unlink()
    saved = (hx.Set, hx.setup_worktree, sys.argv)
    hx.Set, hx.setup_worktree, subprocess.run = TSet, (lambda *x, **y: None), fake_run
    sys.argv = ["hx_heldout.py", "--set", "abpool", "--arm", "rv", "--driver", "claude", "--claude-prompt", "v2", "--claude-effort", "xhigh",
                "--claude-cache", "5m", "--rungs", "0.9,1.8", "--max-rounds", "2", "--round-per-rung", "--no-lineage-rule", "--claude-review",
                "--no-claude-inrun", "--workers", "1"]
    try:
        rc = hx.main()
    except SystemExit as e:
        rc = e.code
    finally:
        subprocess.run = real_run; hx.Set, hx.setup_worktree, sys.argv = saved
    arg = lambda c, k: c[c.index(k) + 1] if k in c else None
    sc = [s for s, _ in calls]; cm = [c for _, c in calls]
    check("hx --claude-review: round 1, ONE reviewer batch for round 2's rows, round 2 at the next rung (--round-per-rung), rc 0",
          rc == 0 and sc == ["normal", "review", "record"] and arg(cm[0], "--budget-usd") == "0.9" and arg(cm[0], "--run-id") == "selftest-cc-hx-rv-r1"
          and "--review" in cm[1] and arg(cm[1], "--budget-usd") == "1.8" and arg(cm[1], "--review-budget") == "0.3" and arg(cm[1], "--effort") == "high"
          and arg(cm[1], "--run-id") == "selftest-cc-hx-rv-v2" and arg(cm[1], "--cache-ttl") == "5m" and cm[1][-2:] == ["--problems", PROBLEM]
          and arg(cm[2], "--budget-usd") == "1.8" and arg(cm[2], "--run-id") == "selftest-cc-hx-rv-r2" and "--review" not in cm[2], f"rc {rc} {sc} {cm}")
    st = json.loads((root / PROBLEM / "state.json").read_text()) if (root / PROBLEM / "state.json").exists() else {}
    runs = st.get("runs") or []; sha = LV.proof_sha((st.get("best") or {}).get("proof"))
    rvf = ROOT / "probe/runs/selftest-cc-hx-rv-r2/reviews" / f"{PROBLEM}.md"   # round 2 moved it out of the workspace (review 2026-10-12)
    meta = (LV.parse_review(rvf.read_text()) or ({}, ""))[0] if rvf.exists() else {}
    rec = next((json.loads(f.read_text()) for f in W.dump.glob("record-*.json")), {}); pr = rec.get("argv", ["-p", ""])
    parts = {"runs": [r.get("run_id") for r in runs], "kind": runs[1].get("kind") if len(runs) > 1 else None,
             "spend": [st.get("api_spend"), sum(r.get("spend_usd_list") or 0 for r in runs)], "meta_sha": meta.get("best_sha"), "sha": sha,
             "seen": runs[2].get("review_seen") if len(runs) > 2 else None, "block": "REVIEW (fresh eyes)" in pr[pr.index("-p") + 1],
             "in_ws": (root / PROBLEM / "review.md").exists()}
    check("hx --claude-review: review charged between the rounds, review.md for the best, round 2 shows it (and moves it out of the workspace)",
          parts["runs"] == ["selftest-cc-hx-rv-r1", "selftest-cc-hx-rv-v2", "selftest-cc-hx-rv-r2"] and parts["kind"] == "review"
          and abs(parts["spend"][0] - parts["spend"][1]) < 1e-5 and parts["meta_sha"] == sha and parts["seen"] == sha and parts["block"]
          and not parts["in_ws"], str(parts))
    log = (out / "jobs.log").read_text() if (out / "jobs.log").exists() else ""
    S = TSet("abpool", "rv"); tot = 0.0
    for rd in hx.rounds(S) + hx.review_rounds(S):
        for e in hx._events(rd / "trajectories" / f"{PROBLEM}.jsonl.gz"):
            tot += e.get("cost") or 0
    check("hx --claude-review: counts in the ladder log, no review after the last round, the reviews' spend in the curve's runs",
          "review before round 2 (rung $1.80): 1 row(s), 0 skipped" in log and "1 of 1 saved review.md" in log and "round 2: the last round, no review" in log
          and [p.name for p in hx.review_rounds(S)] == ["selftest-cc-hx-rv-v2"] and abs(tot - st.get("api_spend", -1)) < 1e-5
          and hx.curve(S, [10.0])[PROBLEM][10.0] == 52.0, log[-800:])
    NS = types.SimpleNamespace
    base = dict(max_rounds=5, round_per_rung=False, stop_at=None, stop_rung=0.9, lineage_rule=False)
    wf = lambda n, s: True
    np_ = lambda r=1, rung=0.9, **kw: hx.next_plan(S, NS(**dict(base, **kw)), [0.9, 1.8, 2.85], rung, r, wf)
    check("hx next_plan: breadth-first on the rung, --round-per-rung climbs, last round, fresh rows left out, the stop-at rule",
          np_() == (0.9, [PROBLEM]) and np_(round_per_rung=True) == (1.8, [PROBLEM]) and np_(max_rounds=1) is None
          and np_(lineage_rule=True) == (0.9, []) and np_(rung=1.8, round_per_rung=True, stop_at=10.0, stop_rung=1.8) is None
          and np_(rung=1.8, round_per_rung=True) == (2.85, [PROBLEM]) and np_(rung=2.85) == (2.85, [PROBLEM])
          and np_(rung=2.85, round_per_rung=True) is None, str([np_(), np_(round_per_rung=True)]))
    # --claude-fresh-facts: a fresh lineage's workspace holds the main lineage's facts sheet (no proof text) when its session starts;
    # --claude-ceiling reaches both the session and the review commands
    seen: dict = {}

    def no_run(cmd, *a, **k):
        f = Path(f"{root}-fresh") / PROBLEM / "lineage_facts.md"
        seen.update({"facts": f.read_text() if f.exists() else None, "cmd": list(cmd)})
        return subprocess.CompletedProcess(cmd, 0)
    a = NS(driver="claude", claude_fresh_facts=True, claude_model="claude-opus-5-5", claude_prompt="v2", claude_cache="5m", claude_sealed=False,
           claude_ceiling=True, claude_review_budget=0.3, claude_review_effort="high", workers=1)
    subprocess.run = no_run
    try:
        hx.fresh_round(S, [PROBLEM], 1.8, "selftest-cc-hx-rv-f9", "xhigh", False, [], a, 1, lambda m: None)
    finally:
        subprocess.run = real_run
    fx = seen.get("facts") or ""
    check("hx --claude-fresh-facts: the fresh lineage gets the main lineage's facts sheet (numbers, no proof); --claude-ceiling in both commands",
          fx.startswith("FACTS SHEET (the MAIN lineage") and "score 52.0" in fx and "stub proof" not in fx and "--ceiling" in seen.get("cmd", [])
          and "--ceiling" in hx.review_cmd(a, 4.5, "r", "x-v2", [PROBLEM], 1) and "--ceiling" not in hx.review_cmd(NS(**dict(vars(a), claude_ceiling=False)), 4.5, "r", "x-v2", [PROBLEM], 1),
          fx[:300] + str(seen.get("cmd")))
    # review 2026-10-12: the sheet's code is the line's worktree copy (at --ref), not the main checkout's
    wtr = W.T / "wtref"; (wtr / "harness").mkdir(parents=True, exist_ok=True)
    (wtr / "harness/cc_levers.py").write_text("FRESH_FACTS_HEAD = 'REF COPY'\n\n\ndef facts_sheet(state, notes, head=None):\n"
                                              "    return head + ' ' + str(state.get('problem'))\n")
    mp = root / PROBLEM / "state.json"
    check("hx --claude-fresh-facts: the facts sheet's code comes from the line's worktree (--ref), not the main checkout",
          hx.lineage_facts(NS(wt=wtr), mp) == f"REF COPY {PROBLEM}" and hx.lineage_facts(S, mp).startswith("FACTS SHEET (the MAIN lineage"))


def test_scripts(W: World) -> None:
    """The runners (§11): bash -n of run_phase_a.sh, run_ceiling.sh and run_after_opus.sh; their ladder argv (LRA_PRINT_ARGV=1: printed, nothing
    run) parsed and checked by hx_heldout: A1-A3 as before, A4 = v2 / xhigh / 5m, $1.50 then $2.85 with the reviewer between; the ceiling = the 8
    rows, uncapped rungs to $8, review + polish + fresh facts, lineage rule on, 8 rounds, 2 workers, sealed, pinned REF."""
    from harness import hx_heldout as hx
    for s in ("run_phase_a.sh", "run_ceiling.sh", "run_after_opus.sh"):
        q = subprocess.run(["bash", "-n", str(ROOT / "probe/abpool" / s)], capture_output=True, text=True, timeout=60)
        check(f"scripts bash -n {s}", q.returncode == 0, q.stderr[-300:])
    marks = {d: (ROOT / d).exists() for d in ("probe/abpool/phase_a", "probe/abpool/ceiling")}
    get = lambda s: [l.rstrip("\x1f").split("\x1f") for l in subprocess.run(["bash", str(ROOT / "probe/abpool" / s)], env=dict(W.env, LRA_PRINT_ARGV="1"),
                                                                           capture_output=True, text=True, timeout=60).stdout.splitlines() if l.strip()]
    dev = [l.strip() for l in (ROOT / "data/abpool/dev24.txt").read_text().splitlines() if l.strip()]
    c8 = [l.strip() for l in (ROOT / "data/abpool/ceiling8.txt").read_text().splitlines() if l.strip()]
    arms = get("run_phase_a.sh"); ce = get("run_ceiling.sh")
    ref = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def parsed(argv):   # hx's own checks; provider env of the shell running the selftest set aside (the runners refuse it themselves)
        import contextlib, io
        ap = hx.build_parser(); n = ap.parse_args(argv[2:])
        prov = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith(("ANTHROPIC_", "AWS_BEARER_TOKEN_BEDROCK", "CLAUDE_CODE_USE_"))}
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                hx.check_args(ap, n)
            return n
        except SystemExit:
            return None
        finally:
            os.environ.update(prov)
    P = {x[x.index("--arm") + 1]: parsed(x) for x in arms}
    old = lambda arm, p, e, c: ["python3", "harness/hx_heldout.py", "--set", "abpool", "--arm", arm, "--ref", ref, "--driver", "claude", "--claude-sealed",
                                "--claude-prompt", p, "--claude-effort", e, "--claude-cache", c, "--problems", *dev, "--rungs", "2.85", "--max-rounds", "1",
                                "--no-lineage-rule", "--workers", "2"]
    check("scripts Phase A argv: A1-A3 unchanged (one session at $2.85), every arm passes hx's checks",
          [x[x.index("--arm") + 1] for x in arms] == ["ccA1", "ccA2", "ccA3", "ccA4"] and arms[0] == old("ccA1", "v1", "xhigh", "1h")
          and arms[1] == old("ccA2", "v2", "xhigh", "5m") and arms[2] == old("ccA3", "v2", "high", "5m") and all(P.values()), str(arms)[:600])
    a4 = P.get("ccA4")
    check("scripts A4 argv: v2 / xhigh / 5m, $1.50 then $2.85 (--round-per-rung, 2 rounds) with the reviewer between, no lineage rule, sealed",
          a4 is not None and a4.claude_prompt == "v2" and a4.claude_effort == "xhigh" and a4.claude_cache == "5m" and a4.rungs == "1.5,2.85"
          and a4.max_rounds == 2 and a4.round_per_rung and a4.claude_review and not a4.lineage_rule and a4.claude_sealed and a4.workers == 2
          and a4.problems == dev and a4.ref == ref and a4.claude_review_budget == 0.3 and a4.claude_review_effort == "high" and hx.inrun_on(a4)
          and not a4.claude_ceiling and not a4.claude_polish, str(a4))
    c = parsed(ce[0]) if len(ce) == 1 else None
    check("scripts ceiling argv: the 8 rows (dev24, < 7k hb), arm ceil, v2 / xhigh / 5m, uncapped rungs to $8, review + polish + fresh facts, "
          "lineage rule on, 8 rounds, 2 workers, sealed, pinned REF",
          c is not None and c.arm == "ceil" and c.set == "abpool" and c.problems == c8 and len(c8) == 8 and set(c8) <= set(dev) and c.rungs == "1.5,3,4.5,6,8"
          and c.max_rounds == 8 and c.workers == 2 and c.claude_review and c.claude_polish and c.claude_fresh_facts and c.claude_ceiling
          and c.lineage_rule and c.claude_sealed and c.claude_prompt == "v2" and c.claude_effort == "xhigh" and c.claude_cache == "5m"
          and c.ref == ref and not c.round_per_rung, str(c))
    check("scripts print mode runs nothing (no output folder created)", all((ROOT / d).exists() == v for d, v in marks.items()))
    ap = hx.build_parser()
    for bad in (["--set", "abpool", "--arm", "x", "--driver", "claude", "--claude-review"], ["--set", "abpool", "--arm", "x", "--claude-ceiling"],
                ["--set", "abpool", "--arm", "x", "--driver", "claude", "--claude-prompt", "v2", "--claude-review", "--claude-review-budget", "0"]):
        check(f"scripts hx refuses {' '.join(bad[4:])}", parsed(["python3", "hx", *bad]) is None)
    # review 2026-10-12: the audit (the runners' limit guard) counts fresh lineages' sessions (live, unmerged or archived: the merge does not copy
    # runs[]) and their unmerged spend; --since leaves out an earlier launch's flags. A temp line: no real state is read.
    import contextlib, importlib.util, io, types
    spec = importlib.util.spec_from_file_location("selftest_phase_a_audit", ROOT / "probe/abpool/phase_a_audit.py")
    PA = importlib.util.module_from_spec(spec); spec.loader.exec_module(PA)
    T = W.T / "audit"; rt = "harness/hwork/abpool-x"

    def put(rel, d):
        (T / rel).mkdir(parents=True, exist_ok=True); (T / rel / "state.json").write_text(json.dumps(d))
    put(f"{rt}/p1", {"problem": "p1", "best": {"score": 50}, "api_spend": 2.0,
                     "runs": [{"run_id": "r1", "started": "2026-10-12T10:00:00Z", "ended": "x", "spend_usd_list": 1.0, "flags": ["usage-limit"]}]})
    put(f"{rt}/p2", {"problem": "p2", "best": {"score": 60}, "api_spend": 1.0, "runs": []})
    put(f"{rt}-fresh/p1", {"problem": "p1", "best": {"score": 40}, "api_spend": 3.5, "runs": [{"run_id": "f3", "started": "2026-10-13T10:00:00Z", "pending": True}]})
    put(f"{rt}-fresh.done-x-f2/p2", {"problem": "p2", "best": {"score": 40}, "api_spend": 1.0, "runs": [
        {"run_id": "f2", "started": "2026-10-13T09:00:00Z", "ended": "x", "spend_usd_list": 0.5, "flags": ["rate-limit-rejected"]}]})
    (T / "rows.txt").write_text("p1\np2\n"); PA.Set = lambda key, arm: types.SimpleNamespace(wt=T, root=rt)

    def audit(*extra):
        saved = sys.argv; sys.argv = ["phase_a_audit.py", "x", "--problems-file", str(T / "rows.txt"), "--uncapped", *extra]; buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = PA.main()
        finally:
            sys.argv = saved
        return rc, buf.getvalue()
    a1 = audit(); a2 = audit("--since", "2026-10-13T00:00:00Z")
    put(f"{rt}-fresh.done-x-f2/p2", {"problem": "p2", "best": {"score": 40}, "api_spend": 1.0, "runs": []})
    a3 = audit("--since", "2026-10-13T00:00:00Z")
    check("scripts audit: fresh lineages' sessions and unmerged spend counted; --since leaves out an earlier launch's flags",
          a1[0] == 3 and "total $4.50" in a1[1] and "usage-limit 1" in a1[1] and "rate-limit-rejected 1" in a1[1] and a2[0] == 3
          and "usage-limit 1" not in a2[1] and "rate-limit-rejected 1" in a2[1] and a3[0] == 0 and "sessions without an end: 1" in a3[1],
          str([a1, a2, a3])[:900])


def test_tools(W: World) -> None:
    from harness.leantools import ROWS
    from scorer.tokenize import split_declaration, count_tokens
    stmt = ROWS[PROBLEM]["statement"]
    files = {"original.lean": ROWS[PROBLEM]["src"].rstrip() + "\n", "candidate.lean": stmt + " := by\n  simp -- SCORE 45\n",
             "cand.lean": stmt + " := by\n  grind -- SCORE 55\n", "a.lean": stmt + " := by\n  omega -- SCORE 60\n",
             "b.lean": stmt + " := by\n  aesop -- SCORE 80\n", "c.lean": stmt + " := by\n  FAIL\n", "d.lean": stmt + " := by\n  simp_all -- AUTOFIX -- SCORE 85\n",
             "bad.lean": "theorem other : True := by\n  trivial\n", "notes.md": "# Notes\n"}
    ws = W.T / "tws" / PROBLEM

    def reset(extra_state=None):
        shutil.rmtree(ws, ignore_errors=True); ws.mkdir(parents=True)
        for k, v in files.items():
            (ws / k).write_text(v)
        (ws / "state.json").write_text(json.dumps({"problem": PROBLEM, "best": {"score": 40.0, "proof": None}, "attempts": [], "runs": [], **(extra_state or {})}, indent=1))

    def snap():
        return {f.name: f.read_bytes() for f in sorted(ws.iterdir()) if f.is_file()}

    def tool(mode, name, args, v2=False, env_extra=None, use_env=True):
        env = dict(W.env, **({"LRA_WORKSPACE": str(ws), "LRA_PROBLEM": PROBLEM, "LRA_RUN_ID": "selftest-cc-tools", "LRA_MODEL": "claude-opus-5-5"} if use_env else {}),
                   **({"LRA_CHECK_V2": "1"} if v2 else {}), **(env_extra or {}))
        if mode == "old":
            src = git_show(f"harness/tools/{name}.py")
            (W.T / f"old_{name}.py").write_text(src or ""); env["STUB_OLD_SRC"] = str(W.T / f"old_{name}.py")
        return subprocess.run([sys.executable, str(W.T / "toolrun.py"), str(ROOT), mode, name, *args], cwd=ws, env=env, capture_output=True, text=True, timeout=120)

    # v1: byte-identical to the BASE scripts (stdout, exit code, every workspace file)
    if git_show("harness/tools/lean_check.py") is None:
        print(f"SKIP tools_v1: commit {BASE[:8]} not in this clone")
    else:
        cases = [("lean_check", ["cand.lean"]), ("lean_check_variants", ["a.lean", "b.lean", "c.lean", "d.lean", "missing.lean"]), ("tok_count", ["cand.lean"]),
                 ("goal_map", [PROBLEM, "cand.lean", "--depth", "2"]), ("heartbeat_profile", [PROBLEM, "cand.lean"]), ("lemma_search_cli", [PROBLEM, "cand.lean"]),
                 ("skeleton_check", [PROBLEM, "cand.lean"]), ("lean_mine", [PROBLEM, "cand.lean"])]
        for name, args in cases:
            reset(); po = tool("old", name, args); so = snap()
            reset(); pn = tool("new", name, args); sn = snap()
            check(f"tools_v1 {name} byte-identical", (po.stdout, po.returncode, so) == (pn.stdout, pn.returncode, sn) and po.returncode == 0,
                  (po.stderr or pn.stderr)[-300:])
    # v2
    J = lambda p: json.loads(p.stdout[p.stdout.index("{"):]) if "{" in p.stdout else {}
    reset(); p = tool("new", "lean_check", ["cand.lean"], v2=True); j = J(p); st = json.loads((ws / "state.json").read_text())
    check("tools_v2 lean_check (locked path, env provenance)", j.get("new_best") and j.get("stub_mode") == "agent-cc-v2" and j.get("stub_model") == "claude-opus-5-5@claude-code"
          and st["best"]["score"] == 55.0 and (ws / "best.lean").read_text() == files["cand.lean"] and st["attempts"][-1]["run_id"] == "selftest-cc-tools", p.stdout[-300:] + p.stderr[-300:])
    reset(); p = tool("new", "lean_check_variants", ["a.lean", "b.lean", "c.lean", "d.lean", "missing.lean"], v2=True); j = J(p)
    check("tools_v2 variants: winner (auto-fixed) copied to candidate.lean", (ws / "candidate.lean").read_text() == files["d.lean"].replace("-- AUTOFIX", "-- FIXED")
          and "d.lean" in j.get("note", "") and j.get("best_after", {}).get("score") == 85.0 and any(r.get("error") == "no such file in the workspace" for r in j.get("variants", [])),
          p.stdout[-400:] + p.stderr[-300:])
    reset({"best": {"score": 90.0, "proof": "x"}}); p = tool("new", "lean_check_variants", ["a.lean", "b.lean"], v2=True); j = J(p)
    check("tools_v2 variants: no new best, candidate unchanged", (ws / "candidate.lean").read_text() == files["candidate.lean"] and "unchanged" in j.get("note", ""))
    p = tool("new", "lean_check_variants", [f"v{i}.lean" for i in range(7)], v2=True)
    check("tools_v2 variants cap 6", "only the first 6 run" in p.stdout and len(J(p).get("variants", [])) == 6)
    reset(); (ws / "candidate.lean").write_text(stmt + " := by\n  decide -- SCORE 75\n")   # candidate.lean itself is the winning variant
    p = tool("new", "lean_check_variants", ["a.lean", "candidate.lean"], v2=True); j = J(p)
    check("tools_v2 variants: candidate.lean as the winner (no SameFileError)", p.returncode == 0 and j.get("best_after", {}).get("score") == 75.0
          and "candidate.lean" in j.get("note", "") and (ws / "candidate.lean").read_text().endswith("SCORE 75\n"), p.stdout[-300:] + p.stderr[-300:])
    reset(); p = tool("new", "lean_mine", [], v2=True); j = J(p); st = json.loads((ws / "state.json").read_text())
    mined = stmt + " := by\n  grind -- SCORE 70\n"
    check("tools_v2 lean_mine banks mined.lean and copies it", (ws / "mined.lean").read_text() == mined and (ws / "candidate.lean").read_text() == mined
          and st["best"]["score"] == 70.0 and j.get("mined", {}).get("new_best") and len(st["attempts"]) == 1, p.stdout[-300:] + p.stderr[-300:])
    reset({"best": {"score": 95.0, "proof": "x"}}); p = tool("new", "lean_mine", ["cand.lean"], v2=True)
    check("tools_v2 lean_mine below the best: banked, candidate unchanged", (ws / "candidate.lean").read_text() == files["candidate.lean"] and "banked" in J(p).get("note", ""))
    reset(); p = tool("new", "goal_map", ["candidate.lean", "--depth", "2"], v2=True); j = J(p)
    check("tools_v2 goal_map: file only, problem from env", j.get("problem") == PROBLEM and j.get("depth") == 2 and j.get("head") == files["candidate.lean"][:40])
    p = tool("new", "goal_map", [PROBLEM], v2=True)
    check("tools_v2 a problem name is refused (files only)", p.returncode == 2 and "no such file in the workspace" in p.stdout)
    p = tool("new", "heartbeat_profile", [], v2=True)
    check("tools_v2 heartbeat_profile defaults to candidate.lean", J(p).get("head") == files["candidate.lean"].rstrip()[:40])
    p = tool("new", "lemma_search_cli", [], v2=True); p2 = tool("new", "lemma_search_cli", ["cand.lean", "--probes"], v2=True)
    check("tools_v2 lemma_search probes off by default", J(p).get("probes") is False and J(p2).get("probes") is True and "debug" not in p.stdout
          and J(p)["suggestions"][0]["name"] == "Stub.lemma")
    p = tool("new", "skeleton_check", ["bad.lean"], v2=True); p2 = tool("new", "skeleton_check", ["cand.lean"], v2=True)
    check("tools_v2 skeleton_check statement guard", "statement differs" in p.stdout and J(p2).get("stub") == "skeleton")
    p = tool("new", "tok_count", ["cand.lean", "bad.lean"], v2=True); j = J(p)
    check("tools_v2 tok_count counts body tokens", j.get("cand.lean") == count_tokens(split_declaration(files["cand.lean"].rstrip(), stmt))
          and j.get("cand.lean") != count_tokens(files["cand.lean"]) and "error" in (j.get("bad.lean") or {}), p.stdout)
    reset(); (ws / ".lra_env.json").write_text(json.dumps({"LRA_PROBLEM": PROBLEM, "LRA_WORKSPACE": str(ws), "LRA_RUN_ID": "from-json", "LRA_MODE": "agent-cc-v2"}))
    p = tool("new", "lean_check", ["cand.lean"], v2=True, use_env=False); j = J(p)
    check("tools_v2 problem from .lra_env.json", j.get("stub_problem") == PROBLEM and json.loads((ws / "state.json").read_text())["attempts"][-1]["run_id"] == "from-json",
          p.stdout[-300:] + p.stderr[-300:])
    # the state lock: two lean_checks in parallel (each holds its compile 0.6 s) both land in state.json
    reset()
    env = dict(W.env, LRA_WORKSPACE=str(ws), LRA_PROBLEM=PROBLEM, LRA_RUN_ID="selftest-cc-lock", LRA_CHECK_V2="1", STUB_SLEEP="0.6")
    ps = [subprocess.Popen([sys.executable, str(W.T / "toolrun.py"), str(ROOT), "new", "lean_check", f], cwd=ws, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True) for f in ("cand.lean", "a.lean")]
    for q in ps:
        q.communicate(timeout=60)
    st = json.loads((ws / "state.json").read_text())
    check("tools_v2 state lock: parallel checks both recorded", len(st["attempts"]) == 2 and st["best"]["score"] == 60.0, str(st["attempts"]))

    # round 2: the ledger win, axis / progress, the profile cache + floor, variants' axis, normalize_check
    prev = stmt + " := by\n  simp\n  omega -- SCORE 50\n"
    reset({"best": {"score": 50.0, "proof": prev.rstrip(), "tokens": 8, "heartbeats": 100}})
    (ws / "e.lean").write_text(stmt + " := by\n  simp\n  grind -- SCORE 52\n")
    p = tool("new", "lean_check", ["e.lean"], v2=True); j = J(p); st = json.loads((ws / "state.json").read_text())
    wins = (st.get("ledger") or {}).get("wins") or []
    check("r2_tools ledger win on a new best (edit, discover's diff + sha)", j.get("new_best") and len(wins) == 1 and wins[0]["kind"] == "edit"
          and wins[0]["diff"] == "-  omega -- SCORE 50\n+  grind -- SCORE 52" and wins[0]["d_score"] == 2.0 and wins[0]["run_id"] == "selftest-cc-tools"
          and wins[0]["check"] == 1, str(wins) + p.stderr[-300:])
    ax = j.get("axis") or {}
    check("r2_tools axis + progress in the check result", ax.get("one_token_equals_heartbeats") and ax.get("points_left_length") is not None
          and ax.get("heartbeat_floor") is None and (j.get("progress") or {}).get("checks_since_new_best") == 0, str(j)[-500:])
    p = tool("new", "heartbeat_profile", [], v2=True); p2 = tool("new", "heartbeat_profile", [], v2=True); st = json.loads((ws / "state.json").read_text())
    sha = hashlib.sha256((ws / "candidate.lean").read_text().rstrip().encode()).hexdigest()[:12]
    check("r2_tools heartbeat_profile cached per sha, floor stored", J(p).get("floor") == 40 and not J(p).get("cached") and J(p2).get("cached") is True
          and st.get("hb_floor") == 40 and sha in (st.get("profile_cache") or {}), p.stdout[-300:] + p2.stdout[-300:])
    p = tool("new", "lean_check", ["a.lean"], v2=True); j = J(p)
    check("r2_tools later checks measure H against the floor", (j.get("axis") or {}).get("heartbeat_floor") == 40, str(j.get("axis")))
    p = tool("new", "lean_check_variants", ["b.lean", "c.lean"], v2=True); j = J(p)
    check("r2_tools variants report the best's axis and progress", (j.get("axis_of_best") or {}).get("heartbeat_floor") == 40
          and "checks_since_new_best" in (j.get("progress") or {}), str(j)[-400:])
    reset(); (ws / "n.lean").write_text(stmt + " := by\n  simp_all -- NORM -- SCORE 70\n")
    p = tool("new", "normalize_check", ["n.lean"], v2=True); j = J(p); st = json.loads((ws / "state.json").read_text())
    want = stmt + " := by\n  simp_all only [h] -- NORMED -- SCORE 88\n"
    check("r2_tools normalize_check: normalized + polished, banked, copied to candidate.lean", (ws / "normalized.lean").read_text() == want
          and (ws / "candidate.lean").read_text() == want and st["best"]["score"] == 88.0 and (j.get("checked") or {}).get("new_best")
          and j["normalize"]["status"] == "improved" and j["hb_polish"]["status"] == "improved" and len(st["attempts"]) == 1, p.stdout[-500:] + p.stderr[-300:])
    reset(); p = tool("new", "normalize_check", ["cand.lean"], v2=True); j = J(p); st = json.loads((ws / "state.json").read_text())
    check("r2_tools normalize_check: nothing strictly better -> nothing banked", "nothing banked" in j.get("note", "") and not st["attempts"]
          and not (ws / "normalized.lean").exists() and (ws / "candidate.lean").read_text() == files["candidate.lean"], p.stdout[-300:])
    p = tool("new", "normalize_check", ["cand.lean"], v2=False)
    check("r2_tools normalize_check is v2 only", p.returncode == 2 and "driver v2 tool" in p.stdout, p.stdout[-200:])


def main() -> int:
    keep = "--keep" in sys.argv
    T = Path(tempfile.mkdtemp(prefix="lra-selftest-cc-"))
    W = World(T)
    if not W.safe():
        print(f"FATAL: the first `claude` on the driver's PATH is not the fake ({shutil.which('claude', path=W.env['PATH'])}); nothing was run")
        return 2
    t0 = time.time()
    try:
        run_units()
        test_v1(W)
        test_v2_flags(W)
        test_sessions(W)
        test_review(W)
        test_exemplars_session(W)
        test_tools(W)
        test_hx_r2(W)
        test_hx_review(W)
        test_scripts(W)
    finally:
        for d in (ROOT / "probe/runs").glob("selftest-cc-*"):   # never leave selftest records in the repository
            shutil.rmtree(d, ignore_errors=True)
        if not keep:
            shutil.rmtree(T, ignore_errors=True)
    bad = [n for n, ok in RESULTS if not ok]
    print(f"{len(RESULTS) - len(bad)}/{len(RESULTS)} checks passed in {time.time() - t0:.0f} s" + (f" (kept {T})" if keep else ""))
    if bad:
        print("FAILED: " + "; ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
