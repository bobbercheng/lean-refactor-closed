#!/usr/bin/env python3
"""b66 closed package (retro A1 + A5; 2026-10-27): ONE command from the organizers' benchmark rows file to the upload file.

    python3 infra/closed_package/run_final.py run --rows ROWS.jsonl [--heartbeats HB.jsonl] [--out DIR] [--key-file PATH]

  1. stage     harness/final_rows.py: validate the rows (any rows file in the warm-up file's schema, LeanPool rows included) and copy them
               with their reference heartbeats to data/final/ (hx_heldout set "final-clean"); heartbeats from --heartbeats, the rows, or
               measured on each seed's newest pin
  2. plan      --shards (default 4) balanced shards (final_rows.split), the knobs derived from the host (harness/host_knobs.py: nproc,
               SMT, MemTotal; every knob can be overridden), the exact router command of each shard (the b65-final pipeline as the VM
               arms run it: docs/b65_final.md section 6, with arm B's presets by rung: docs/b67_final.md, and the b68 Terra tail with
               the fork-tested flags: docs/b70_final.md) -> <out>/plan.json; a re-run reuses it (same rows file, same shards)
               b71: every shard's environment carries LRA_FORCE_WARN_SORRY=1 (SORRY_GUARD_ENV, the sorry guard; docs/b71_final.md)
               b75: every shard's review runs R6 (R6_ARGS: --review-repair 3 --review-stack, the fork A/B's TREAT arm; docs/b75_stack.md)
               b84: every shard's end step runs the approach pick (APPROACH_ARGS: 1 other approach group, 1200 s hard cap; $0, accept-gated;
               docs/b84_polish_before_pick.md section 3)
  3. preflight checkout clean in harness/ scorer/ llm/ (the ladder's worktree is checked out at HEAD), every pin's Lean environment
               built at its commit, the docker image, elan, systemd user units, leak_scan, disk; refuses (exit 2) before any spend
  4. key       the one OpenRouter key (Sol and Terra sessions, the Argon review): $OPENROUTER_API_KEY or --key-file PATH, written to the path
               the presets read (~/.config/vexorium/openrouter_api_key, mode 600); never printed or logged
  5. launch    per shard: systemd user unit lra-<tag>-s<k> (MemoryMax = ROUTER_MEM, OOMPolicy=continue) running <run dir>/run.sh (the
               router; re-running run.sh resumes the shard), its own run dir <out>/shards/s<k>, its own compile slots (the router's
               --compile-slots scratch), its own session scratch and its own runaway guard unit lra-<tag>-s<k>-guard (pressure mode,
               watching that unit and that shard's containers)
  6. wait      bounded (--wait-hours); a shard that ended unfinished (a short stop, a crash, a timeout) is started again once
               (--max-restarts; a restart resumes: spend so far is kept per row, so the $3.00 cap holds across restarts)
  7. merge     harness/final_merge.py: <out>/submission.jsonl with exactly one {"name", "proof"} line per row in the rows file's order
               (a shard's line when it passes the statement-identity and forbidden-construct checks, else the row's seed), checked again
               after writing; <out>/merge_report.json says where each line came from

Other commands: plan (steps 2-3 only, nothing staged or launched), status, merge (step 7 alone), stop (SIGTERM to every unit: the routers
write their outputs on the way out, exit 143). Re-running `run` with the same arguments resumes: finished shards are kept, unfinished
ones restarted, the merge redone.

Exit codes: 0 every shard finished (router exit 0, 1 = finished with a row whose spend went OVER the cap: a WARNING line and
merge_report.json "over_cap", or 79 = finished on the $0 path after a confirmed pin) and the
merged file checks; 5 the merged file checks but a shard did not finish (its rows carry their best-so-far or seed lines); 3 the wait limit
passed (merged anyway); 1 the merged file fails its check; 2 refused before launch.

$0 rehearsal: --fake-model starts infra/closed_package/fake_openrouter.py on the docker bridge and points every preset there
(LRA_SELFTEST_PRESET_URL; no key read or sent; b70: the tail's Terra sessions too, being agent.py sessions in the same containers; the fake
logs one line per request, its time, kind and model, to <out>/fake_requests.jsonl); --router-extra / --ladder-extra append flags to the
frozen command (last one wins: a rehearsal shrinks the $0 budgets), --shared-slots N makes every shard's router share one pool of N compile
slots."""
from __future__ import annotations

import argparse, json, os, shlex, shutil, signal, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from harness import final_rows as FR, final_merge as FM, host_knobs as HK  # noqa: E402

# ---------------------------------------------------------------------------------------------------------------- the frozen pipeline
# docs/b65_final.md section 6 (the candidate-final arms on the Azure VM, it2a / it3vm's closed pipeline with b65-final's changes); only
# the speed and memory knobs (host_knobs) and the per-shard paths differ between hosts. Edit here, nowhere else.
# b67 (2026-10-28 ~00:50 UTC, docs/b67_final.md): the closed final is ARM B of the candidate-final (91.744 vs arm A 91.594): Sol
# for every session until a row has spent $1.25, Terra (effort medium: the line's --effort) for the sessions toward $1.90 and toward $2.75.
# RUNG_PRESETS is arm B's --preset-by-rung exactly as its launch line gave it (appended after the frozen ladder flags, as there); review,
# end config, cap, steps and the writer are arm A's = arm B's. With two ladder presets, a CONFIRMED pin of either falls back to the other
# (b66-robust A3); no --pin-fallback-preset, no --review-fallback-model (an open decision).
# b70 (2026-10-28; docs/b70_final.md): arm B PLUS the b68 Terra tail
# (docs/b68_tail.md) with exactly the flags of its fork test (arm finbt2 = arm B's final states + the tail: +0.024 paired over 15 rows,
# CI +0.001 to +0.056; tail $1.62 metered over 11 rows, at most $0.18 a row; every row's metered spend at the cap price <= $2.9718; no cap
# breach). After every row's review, a row whose room under the cap (cap - metered spend at the cap price - $0.001) is at least
# max(--tail-min-room, Terra's $0.20 session floor) runs at most 3 Terra sessions (effort medium) whose --budget-usd is the row's spend +
# that room, so agent.py's worst-case pre-call gate holds the row under the cap; a tail proof enters only when better back to back on every
# pin; the end stage runs after the tail. The tail adds wall time after each shard's slowest review (the fork: 24 min for 11 rows with 6
# sessions at once, then the end stage; README section 5).
SET, PREFIX = "final-clean", "finalc"          # harness/hx_heldout.py SETS
PRESET, REVIEWER = "gpt-6.1-sol-main", "gemini-4-argon"   # both OpenRouter, one key
TERRA = "gpt-6.1-terra-main"                               # OpenRouter, the same key
RUNG_PRESETS = f"1.90:{TERRA},2.75:{TERRA}"                # hx_heldout --preset-by-rung (arm B `finb`)
TAIL_ARGS = ("--tail-preset", TERRA, "--tail-min-room", "0.10", "--tail-effort", "medium", "--tail-max-sessions", "3")   # b70: router flags (fork `finbt2`)
END_CONFIG = "probe/b63/r10_candidate.json"
# b84 (2026-10-30, adopted after the out-of-sample replay of "polish before pick" in its 1-extra-approach variant with a
# time cap; docs/b84_polish_before_pick.md section 3): the end step's APPROACH PICK (harness/approach_pick.py), $0, accept-gated. After
# the end stage has settled a row's incumbent, the best-stored OTHER approach group of the row's candidates (g1: lemma tokens + top-level
# splits, complete-link Jaccard 0.5, as b80 step 0) is polished by the same END_CONFIG end stage in a child process under a HARD 1200 s
# wall cap per row (never more than what is left of the end config's 1800 + 1800 s clock; a polish that hits the cap is abandoned), and
# replaces the incumbent only when it reads higher back to back on the end-stage meter (scorer.accept.decide) and on the confirm read, Z 100,
# static check, axiom audit; else the incumbent stays byte-identical. No model call; any error or timeout leaves the incumbent. Landed BELOW
# the pre-registered bar by decision: out of sample +0.011 a row (64 samples, 4 improved / 60 unchanged / 0 worse, CI +0.001 to
# +0.024); the cap of 1200 s keeps all 4 out-of-sample wins and the one in-sample warm-up win (the slowest win's polish took 983 s on the
# recorded jobs; added wall p50 466 s, p95 1200 s, 11 of 64 samples at the cap). Frozen into each shard's config.json "end_approach".
APPROACH_ARGS = ("--end-approach", "on", "--end-approach-groups", "1", "--end-approach-seconds", "1200")
# b71 R1 (2026-10-28, R1 of docs/tail_signal_study.md; docs/b71_final.md): the sorry guard. A pin whose lakefile
# sets -Dwarn.sorry=false (PhysLib) would accept a proof that depends on sorryAx without the literal word (Lean core's `impossible by
# simp|decide|grind` from v4.31, `stop`): every compile of the shard (the router's $0 stages, the review, the tail and the end stage, and,
# through hx_heldout.DOCKER_PASS_NAMES, the agent containers) forces warn.sorry on (scorer.compile.force_warn_sorry). Heartbeats are
# unchanged (the study: the PhysLib finals measured identical with the flag on and off; re-checked in b71). The writer's axiom audit
# (harness/final_writer.py) is the backstop on each row's final.
SORRY_GUARD_ENV = {"LRA_FORCE_WARN_SORRY": "1"}
# b75 R6 (2026-10-28, adopted after the fork A/B below;
# docs/b75_stack.md, design docs/b72_r6.md sections 2-3): the review's REPAIR (a review
# edit that failed to compile gets one repair turn from the review's own model, at most 3 per row per round) and STACK (every compiling
# edit within 0.02 of the round base, below the +0.05 single-edit bar included, applied together in ONE full compile on every pin, greedy
# fallback; a stack verified on every pin above its base is banked as `review_stack` and read by the end stage under its paired accept bar
# 0.005), EXACTLY as measured in the fork A/B's TREAT arm finbr6t: its router command added `--review-repair 3 --review-stack` to arm B's
# review (stack_eps the router's default 0.02); its config.json froze review_r6 = {repair: 3, stack: true, stack_eps: 0.02}. A/B (15
# warm-up rows, arm B forked at review start, no tail): CONTROL 91.75, TREAT 91.80, paired +0.049 (95% CI +0.00..+0.13), 3 rows up, 0
# down; 69 repairs sent, 19 compiled, 3 paid; $1.17 of repair calls at the cap price ($0.078 a row). Every repair call is a review call
# for the money path: priced at its worst case at the cap price before it is sent, inside what the row's review budget (the row's room
# under $3.00) has left (harness/review.py _repairs -> PricedCaller(kind="repair").call_retry -> plan), booked once into the review's
# spend and the row's ledger; the stack makes no model call. Frozen into each shard's config.json "review_r6" (a resume that changes it
# is refused). No R6 knob differs from the measured run.
R6_ARGS = ("--review-repair", "3", "--review-stack")
# b85 Change B (2026-10-29, adopted after its validation replay; docs/b85_style_rw.md, design
# docs/b80_style_rewrite.md section 3.4): style_rw, an ACCEPT-ONLY paid step at the END of every row's end stage (harness/style_rw.py):
# Sol medium (the ladder's preset, pinned at list, metered at max(billed, list)) rewrites the row's final into the scoring dialect
# (r1, one repair per failing candidate, r2) with the frozen T1 prompt and the 9 compiled exemplar pairs of harness/style_rw_exemplars.json
# (STYLE_RW_EXEMPLARS = its sha16; a changed file is refused before any spend); every candidate on every pin with the sorry guard,
# check_forbidden and the axiom audit, then the run's $0 end-stage polish (END_CONFIG, r10); accepted only when it beats the incumbent by
# >= 0.05 on a single confirm read, else the final stays byte-identical. Budget per row min($0.30, $3.00 - the row's metered spend at the cap
# price - $0.001) through the review's worst-case pre-call gate (the output cap shrinks to fit; a call below the floor is not sent); a
# possibly billed failure is charged its worst case once, a 4xx / 429 nothing; a confirmed pin ends the step at $0; the step can never push a
# row past the cap. HARD wall cap per row (STYLE_RW_WALL_S, b80 3.4's "added wall <= 15 min per row"): min(900 s, the row's end-stage
# clock left = the end config's wall budget per start - the seconds the row's end stage used) for the calls, the compiles, the polish and the
# confirm read together; what runs past it is abandoned and the final stays byte-identical. Frozen into each shard's config.json "style_rw"
# (a resume that changes it is refused). STYLE_RW_ARGS = () turns it off (no key, no code of the module runs).
STYLE_RW_EXEMPLARS = "c03ffd730e950d93"   # sha16 of harness/style_rw_exemplars.json (harness/style_rw.exemplars_sha)
STYLE_RW_WALL_S = "900"
STYLE_RW_ARGS = ("--style-rw", "on", "--style-rw-usd", "0.30", "--style-rw-preset", PRESET, "--style-rw-effort", "medium",
                 "--style-rw-exemplars", STYLE_RW_EXEMPLARS, "--style-rw-wall-s", STYLE_RW_WALL_S)
IMAGE = "lra-agent:1"
CAP, CHECKPOINTS = "3.00", "1.25,1.90"
KEY_FILE = Path("~/.config/vexorium/openrouter_api_key").expanduser()   # harness/agent.py MODEL_PRESETS[PRESET / REVIEWER]["key"]
# review 2026-10-27: router exit 1 is `over_cap` (a row's reported spend ABOVE --cap, router.py summary), not "reached": a finished run
# whose cap breach must be seen (merge() logs it and puts the counts in merge_report.json)
DONE_RC = {0: "done", 1: "done, but a row's spend went OVER the cap (summary.json over_cap)",
           79: "done on the $0 path (a confirmed pin of both ladder presets, Sol and Terra)"}
NO_RESTART_RC = {2}                              # argparse / refusal: the same command fails again
PLACEHOLDER = "fake-rehearsal-no-key\n"
STOP_FILE = "STOP_REQUESTED"   # review 2026-10-27: written by `stop` before it stops the units; a waiting `run` then restarts nothing
# review 2026-10-27: the host Python the routers run on (sys.executable). 3.11, not 3.10: scorer.compile.lakefile_options reads every
# lakefile.toml pin (arklib, cslib, physlib, LeanPool) with tomllib (3.11+), so on 3.10 (Ubuntu 22.04's python3) every host-side compile
# of those rows (the $0 stages, the writer's check, the staging measure) raised ModuleNotFoundError after preflight said ok
MIN_PYTHON = (3, 11)


def ladder_args(k: dict, scratch: str, extra: str = "") -> str:
    """hx_heldout flags of a shard (--ladder-args)."""
    return " ".join(x for x in [
        f"--preset {PRESET} --effort medium --async-ladder --workers {k['workers']} --max-rounds 30 --rescue 0 --no-lineage-rule",
        "--agent-pattern-cards --agent-auto-brief --auto-brief-budget 80 --auto-brief-timeout 36000",
        f"--auto-brief-row-workers {k['brief_row_workers']} --auto-brief-compile-workers {k['brief_compile_workers']} "
        f"--auto-brief-docker-memory {k['brief_docker_memory_gb']}g",
        "--auto-brief-longest-first --auto-brief-pipeline --agent-budget-reclaim --agent-pool --agent-compact-tool-json",
        "--agent-skeleton-fix --agent-leads-count",
        f"--agent-docker {IMAGE} --agent-docker-memory {k['agent_docker_memory_gb']}g --agent-private-scratch {scratch} --agent-mask-strays",
        f"--preset-by-rung {RUNG_PRESETS}",   # b67: arm B
        extra.strip()] if x)


def router_args(sh: dict, plan: dict) -> list[str]:
    """harness/router.py arguments of one shard."""
    k = plan["knobs"]
    return ["--set", SET, "--arm", sh["arm"], "--ref", plan["ref"], "--run-dir", sh["run_dir"],
            "--ladder-args", ladder_args(k, sh["scratch"], plan.get("ladder_extra") or ""),
            "--checkpoints", CHECKPOINTS, "--policy", "v2.2", "--no-flex", "--cap", CAP, "--target-frac", "1.0",
            "--no-replan", "--replan-model", PRESET,
            "--review-model", REVIEWER, "--review-effort", "medium", "--review-rounds", "3", "--review-k", "5", "--review-max-tokens", "16000",
            "--review-budget", "room", "--cap-price", "announced",
            "--end-stage", "--end-config", END_CONFIG, "--end-dual-start",
            *APPROACH_ARGS,   # b84: the end step's approach pick (frozen into the shard's config.json "end_approach")
            "--agent-docker", IMAGE, "--agent-docker-memory", f"{k['agent_docker_memory_gb']}g", "--agent-private-scratch", sh["scratch"],
            "--agent-mask-strays", "--jobs", str(k["jobs"]), "--compile-slots", str(k["compile_slots"]), "--ladder-timeout", "172800", "--anon",
            *TAIL_ARGS,   # b70: the Terra tail (frozen into the shard's config.json "tail"; a resume that changes it is refused)
            *R6_ARGS,     # b75: R6 review repair + stack (frozen into the shard's config.json "review_r6"; a resume that changes it is refused)
            *STYLE_RW_ARGS,   # b85: the accept-only style rewrite after the end stage (frozen into config.json "style_rw")
            *shlex.split(plan.get("router_extra") or ""), "--problems", *sh["names"]]


def shard_env(plan: dict) -> dict:
    """The environment a shard's router runs with (written into run.sh)."""
    env = {"PATH": f"{Path.home() / '.elan/bin'}:{os.environ.get('PATH', '/usr/bin:/bin')}", "HOME": str(Path.home()), "PYTHONUNBUFFERED": "1",
           "LRA_HX_BASE": str(Path(plan["out"]) / "hx"), **HK.env_of(plan["knobs"]), **SORRY_GUARD_ENV}   # b71 R1: the sorry guard
    if plan.get("shared_slots"):   # every shard's router compiles in one slot group (must be inside the checkout: hb_tool_eval)
        env["LRA_HBTOOL_SCRATCH"] = str(ROOT / "probe/hbtool/.scratch" / f"final-{plan['tag']}-shared")
    if plan.get("fake_url"):
        env["LRA_SELFTEST_PRESET_URL"] = plan["fake_url"]
    return env


def run_sh(sh: dict, plan: dict) -> str:
    env = shard_env(plan)
    lines = ["#!/usr/bin/env bash",
             f"# shard {sh['label']} of {plan['out']} ({len(sh['names'])} row(s)), written by infra/closed_package/run_final.py at {plan['created']}.",
             "# The shard's router (the b65-final pipeline); running this script again resumes the shard where it stopped.",
             f"cd {shlex.quote(str(ROOT))} || exit 2",
             *[f"export {k}={shlex.quote(v)}" for k, v in env.items()],
             f"{shlex.quote(sys.executable)} -u harness/router.py " + " ".join(shlex.quote(x) for x in router_args(sh, plan))
             + f" >> {shlex.quote(str(Path(plan['out']) / 'logs' / (sh['label'] + '.router.out')))} 2>&1",
             "rc=$?", f"echo \"$rc $(date -u +%FT%TZ)\" >> {shlex.quote(str(Path(sh['run_dir']) / 'exit_codes'))}", "exit $rc", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------------------- helpers
class Log:
    def __init__(self, out: Path):
        self.path = out / "logs" / "launcher.log"; self.path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, m: str) -> None:
        line = f"[run_final {time.strftime('%H:%M:%S')}] {m}"
        print(line, flush=True)
        with self.path.open("a") as f:
            f.write(line + "\n")


def sh_(cmd: list, timeout: int = 120, **kw) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(cmd, 127, "", f"{type(e).__name__}: {e}")


def user_env() -> dict:
    uid = os.getuid()
    return dict(os.environ, XDG_RUNTIME_DIR=os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}",
                DBUS_SESSION_BUS_ADDRESS=os.environ.get("DBUS_SESSION_BUS_ADDRESS") or f"unix:path=/run/user/{uid}/bus")


def systemctl(*args, timeout: int = 60) -> subprocess.CompletedProcess:
    return sh_(["systemctl", "--user", *args], timeout=timeout, env=user_env())


def unit_state(unit: str) -> dict:
    p = systemctl("show", unit, "-p", "LoadState", "-p", "ActiveState", "-p", "Result", "-p", "ExecMainStatus")
    d = dict(l.split("=", 1) for l in p.stdout.splitlines() if "=" in l)
    return {"load": d.get("LoadState"), "active": d.get("ActiveState"), "result": d.get("Result"), "status": d.get("ExecMainStatus")}


_CHILDREN: dict = {}   # --runner local: run dir -> the Popen of a shard this process started (polled, so an ended child is reaped)


def running(sh: dict, plan: dict) -> bool:
    if plan["runner"] == "systemd":
        return unit_state(sh["unit"])["active"] in ("active", "activating", "deactivating", "reloading")
    ch = _CHILDREN.get(sh["run_dir"])
    if ch is not None:
        return ch.poll() is None
    try:   # a shard an earlier launcher started (not our child): alive and not a zombie
        pid = int((Path(sh["run_dir"]) / "pid").read_text().split()[0])
        os.kill(pid, 0)
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, ValueError, IndexError):
        return False


def last_exit(sh: dict) -> int | None:
    try:
        return int((Path(sh["run_dir"]) / "exit_codes").read_text().split("\n")[-2].split()[0])
    except (OSError, ValueError, IndexError):
        return None


def shard_done(sh: dict) -> tuple[bool, str]:
    """(finished, why): the router's last exit is a DONE code and its summary.json is the complete one (not `partial`)."""
    rc = last_exit(sh)
    try:
        summ = json.loads((Path(sh["run_dir"]) / "summary.json").read_text())
    except (OSError, ValueError):
        summ = {}
    if rc in DONE_RC and summ and not summ.get("partial"):
        return True, DONE_RC[rc]
    if rc is None:   # review 2026-10-27: a unit stop (`stop`, RuntimeMaxSec) ends run.sh too, so no exit code is recorded for that run
        return False, "not run yet" if not summ else "ended with no exit code (its unit was stopped)" + (" (partial outputs: best so far)" if summ.get("partial") else "")
    return False, f"exit {rc}" + (" (partial outputs: best so far)" if summ.get("partial") else "")


def progress(sh: dict) -> str:
    rd = Path(sh["run_dir"])
    fin = 0
    for f in (rd / "rows").glob("*.json"):
        try:
            fin += "end" in (json.loads(f.read_text()).get("steps") or {})
        except (OSError, ValueError):
            pass
    try:
        last = (rd / "router.log").read_text().splitlines()[-1][:150]
    except (OSError, IndexError):
        last = ""
    return f"{fin}/{len(sh['names'])} rows finished; {last}"


# ---------------------------------------------------------------------------------------------------------------- plan
def make_plan(a, out: Path, rows: list[dict], log) -> dict:
    ref = sh_(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
    shards = FR.split(rows, a.shards)
    h = HK.host()
    over = {"workers": a.workers, "jobs": a.jobs, "compile_slots": a.compile_slots or a.shared_slots, "router_mem_gb": a.router_mem_gb,
            "memgate_claim_mb": a.memgate_claim_mb, "memgate_reserve_mb": a.memgate_reserve_mb, "brief_row_workers": a.brief_row_workers,
            "brief_compile_workers": a.brief_compile_workers, "brief_docker_memory_gb": a.brief_docker_memory_gb,
            "agent_docker_memory_gb": a.agent_docker_memory_gb}
    k = HK.knobs(h, len(shards), max(len(s) for s in shards), over)
    scr = Path(a.scratch_root).resolve() if a.scratch_root else out / "scratch"
    plan = {"created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rows_file": str(Path(a.rows).resolve()),
            "rows_sha256": FR.sha256_file(a.rows), "rows": len(rows), "ref": ref, "tag": a.tag, "out": str(out), "runner": a.runner,
            "host": k["host"], "knobs": {n: k[n] for n in k["why"]}, "why": k["why"], "warnings": k["warnings"],
            "fake_model": bool(a.fake_model), "shared_slots": a.shared_slots, "router_extra": a.router_extra or "",
            "ladder_extra": a.ladder_extra or "", "cpu_weight": a.cpu_weight, "runtime_hours": a.runtime_hours, "shards": []}
    for i, names in enumerate(shards, 1):
        lab = f"s{i}"; arm = f"{a.tag}-{lab}"
        plan["shards"].append({"label": lab, "arm": arm, "unit": f"lra-{a.tag}-{lab}", "names": names,
                               "run_dir": str(out / "shards" / lab), "scratch": str(scr / lab),
                               "seed_tokens": sum(int(r.get("proof_length") or 0) for r in rows if r["name"] in set(names))})
    return plan


def print_plan(plan: dict, log) -> None:
    h, k = plan["host"], plan["knobs"]
    log(f"host {h['vcpu']} vCPU ({h['cores']} cores{', SMT' if h['smt'] else ''}), {h.get('mem_installed_gb', h['mem_gb'])} GB installed "
        f"(MemTotal {h['mem_gb']} GB); {plan['rows']} row(s) in "
        f"{len(plan['shards'])} shard(s); ref {plan['ref'][:12]}; runner {plan['runner']}" + (" [FAKE MODEL: $0 rehearsal]" if plan["fake_model"] else ""))
    log(f"  pipeline: Sol ({PRESET}) until a row has spent ${CHECKPOINTS.split(',')[0]}, Terra ({TERRA}) toward "
        f"{' and '.join('$' + r.split(':')[0] for r in RUNG_PRESETS.split(','))}, review {REVIEWER} with R6 ({' '.join(R6_ARGS)}), then the Terra tail "
        f"({' '.join(TAIL_ARGS)}), then the end stage {END_CONFIG}" + (f", then style_rw ({' '.join(STYLE_RW_ARGS)})" if STYLE_RW_ARGS else "")
        + f"; cap ${CAP} per row")
    if APPROACH_ARGS:   # b84
        log(f"  end stage: + approach pick ({' '.join(APPROACH_ARGS)}): 1 other approach group polished per row, hard wall cap, accept-gated, $0")
    for n in plan["why"]:
        log(f"  knob {n:24s} {str(k[n]):>6s}   {plan['why'][n]}")
    for w in plan["warnings"]:
        log(f"  WARNING: {w}")
    for sh in plan["shards"]:
        log(f"  shard {sh['label']}: {len(sh['names'])} row(s), {sh['seed_tokens']} seed tokens; unit {sh['unit']}; run dir {sh['run_dir']}")


# ---------------------------------------------------------------------------------------------------------------- preflight
def preflight(plan: dict, rows: list[dict], a, log) -> list[str]:
    """Problems that refuse the launch (every check runs; all are reported)."""
    bad = []

    def check(ok: bool, what: str, fix: str = "") -> None:
        log(f"  {'ok ' if ok else 'BAD'} {what}" + ("" if ok or not fix else f"  -> {fix}"))
        if not ok:
            bad.append(what)
    log("preflight:")
    check(sys.version_info >= MIN_PYTHON, f"python {sys.version.split()[0]} (>= {'.'.join(map(str, MIN_PYTHON))})",
          "Ubuntu 24.04's python3 (3.12), or python3.11+ from your distribution")
    try:
        import requests  # noqa: F401
        check(True, "python requests")
    except ImportError:
        check(False, "python requests", "python3 -m pip install requests")
    dirty = sh_(["git", "status", "--porcelain", "--", "harness", "scorer", "llm"], cwd=ROOT).stdout.strip()
    check(not dirty, "checkout clean in harness/ scorer/ llm/ (the ladder worktree is checked out at HEAD)", "commit or stash the changes")
    errs, warns = FR.validate(rows)
    check(not errs, f"rows valid ({len(rows)} rows, {len(warns)} warning(s))", "; ".join(errs[:3]))
    st = FR.env_status(rows)
    miss = [e["env"] for e in st if not e["ok"]]
    check(not miss, f"Lean environments: {len(st) - len(miss)}/{len(st)} built at their pins" + (f" (missing or off-pin: {', '.join(miss[:6])})" if miss else ""),
          "infra/closed_package/install_envs.sh ROWS.jsonl")
    check((Path.home() / ".elan/bin/lake").exists(), "elan (~/.elan/bin/lake)", "infra/closed_package/install_envs.sh installs it")
    di = sh_(["docker", "image", "inspect", "-f", "{{.Id}}", IMAGE])
    check(di.returncode == 0, f"docker image {IMAGE}", "infra/closed_package/build_image.sh")
    if plan["runner"] == "systemd":
        su = systemctl("show-environment")
        check(su.returncode == 0, "systemd user manager (systemctl --user)", "loginctl enable-linger $USER, or --runner local")
    g = (ROOT / "harness/runaway_guard.sh").read_text() if (ROOT / "harness/runaway_guard.sh").exists() else ""
    check("MIN_AVAIL_MB" in g, "runaway guard in pressure mode (harness/runaway_guard.sh)")
    ls = sh_([sys.executable, "harness/leak_scan.py"], cwd=ROOT, timeout=900)
    check(ls.returncode == 0, "leak_scan (no warm-up row content in the pipeline)", (ls.stdout.strip().splitlines() or ["?"])[-1][:120])
    for p in {ROOT, Path(plan["out"])}:
        free = shutil.disk_usage(p).free / 1e9
        check(free >= a.min_free_gb, f"disk: {free:.0f} GB free at {p} (>= {a.min_free_gb:g})")
    if plan["fake_model"]:
        log("  --   key: not needed (fake model)")
    else:
        # review 2026-10-27: a stopped --fake-model rehearsal leaves its placeholder in the key file; a real run on it would get a 401 on
        # every call ($0, but every row parked and the run spent on nothing), so the placeholder never counts as a key
        placeholder = KEY_FILE.is_file() and KEY_FILE.stat().st_size == len(PLACEHOLDER) and KEY_FILE.read_text() == PLACEHOLDER
        have = bool(os.environ.get("OPENROUTER_API_KEY")) or bool(a.key_file) or (KEY_FILE.exists() and KEY_FILE.stat().st_size > 0 and not placeholder)
        check(have, "OpenRouter key ($OPENROUTER_API_KEY, --key-file, or the existing key file)",
              "export OPENROUTER_API_KEY=..." + (f" ({KEY_FILE} holds a stopped rehearsal's placeholder)" if placeholder else ""))
    return bad


def install_key(a, log) -> str:
    """The key into KEY_FILE (mode 600) from --key-file or $OPENROUTER_API_KEY; returns where it came from. Never prints the key."""
    src, val = None, None
    if a.key_file:
        val, src = Path(a.key_file).expanduser().read_text().strip(), f"--key-file {a.key_file}"
    elif os.environ.get("OPENROUTER_API_KEY"):
        val, src = os.environ["OPENROUTER_API_KEY"].strip(), "$OPENROUTER_API_KEY"
    if val is None:
        return f"the existing {KEY_FILE}"
    if not val:
        raise SystemExit("the key is empty")
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    old = KEY_FILE.read_text().strip() if KEY_FILE.is_file() else None
    if old != val:
        tmp = KEY_FILE.with_name(f".{KEY_FILE.name}.{os.getpid()}")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(val + "\n")
        os.replace(tmp, KEY_FILE)
    os.chmod(KEY_FILE, 0o600)
    log(f"key: from {src} -> {KEY_FILE} (mode 600)")
    return src


# ---------------------------------------------------------------------------------------------------------------- fake model
def docker_gateway() -> str:
    p = sh_(["docker", "network", "inspect", "bridge", "-f", "{{range .IPAM.Config}}{{.Gateway}}{{end}}"])
    return p.stdout.strip() or "172.17.0.1"


def start_fake(plan: dict, log) -> str:
    out = Path(plan["out"]); pf = out / "fake_port"; unit = f"lra-{plan['tag']}-fake"
    alive = running({"unit": unit, "run_dir": str(out)}, plan) if plan["runner"] == "systemd" else False
    if alive and pf.exists():
        url = f"http://{pf.read_text().strip()}/v1"; log(f"fake model already up: {url}"); return url
    pf.unlink(missing_ok=True)
    cmd = [sys.executable, str(ROOT / "infra/closed_package/fake_openrouter.py"), "--host", docker_gateway(), "--port-file", str(pf),
           "--stats", str(out / "fake_stats.json"), "--events", str(out / "fake_requests.jsonl")]
    if plan["runner"] == "systemd":
        systemctl("reset-failed", unit)
        r = sh_(["systemd-run", "--user", "--unit", unit, "-p", "MemoryMax=1G", "-p", f"RuntimeMaxSec={int(plan['runtime_hours'] * 3600)}",
                 "-p", f"StandardOutput=append:{out / 'logs/fake.log'}", "-p", f"StandardError=append:{out / 'logs/fake.log'}", *cmd], env=user_env())
        if r.returncode:
            raise SystemExit(f"fake model unit did not start: {r.stderr.strip()[:200]}")
    else:
        p = subprocess.Popen(cmd, stdout=(out / "logs/fake.log").open("a"), stderr=subprocess.STDOUT, start_new_session=True)
        (out / "fake_pid").write_text(f"{p.pid}\n")
    t0 = time.time()
    while not pf.exists():
        if time.time() - t0 > 60:
            raise SystemExit("fake model did not report its port within 60 s (logs/fake.log)")
        time.sleep(0.5)
    url = f"http://{pf.read_text().strip()}/v1"; log(f"fake model up: {url} (unit {unit})"); return url


# ---------------------------------------------------------------------------------------------------------------- launch / wait / stop
def launch(sh: dict, plan: dict, log) -> bool:
    rd = Path(sh["run_dir"]); rd.mkdir(parents=True, exist_ok=True); Path(sh["scratch"]).mkdir(parents=True, exist_ok=True)
    (Path(plan["out"]) / "logs").mkdir(parents=True, exist_ok=True)
    script = rd / "run.sh"; script.write_text(run_sh(sh, plan)); script.chmod(0o755)
    k = plan["knobs"]
    if plan["runner"] == "systemd":
        systemctl("reset-failed", sh["unit"]); systemctl("reset-failed", sh["unit"] + "-guard")
        rt = int(plan["runtime_hours"] * 3600)
        r = sh_(["systemd-run", "--user", "--unit", sh["unit"], "-p", f"MemoryMax={k['router_mem_gb']}G", "-p", "OOMPolicy=continue",
                 "-p", f"RuntimeMaxSec={rt}", "-p", f"CPUWeight={plan['cpu_weight']}", f"--working-directory={ROOT}", "/bin/bash", str(script)],
                env=user_env())
        if r.returncode:
            log(f"shard {sh['label']}: unit {sh['unit']} did not start: {r.stderr.strip()[:200]}"); return False
        start_guard(sh, plan)
    else:
        p = subprocess.Popen(["/bin/bash", str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        (rd / "pid").write_text(f"{p.pid}\n"); _CHILDREN[sh["run_dir"]] = p
    log(f"shard {sh['label']}: started ({sh['unit'] if plan['runner'] == 'systemd' else 'pid ' + (rd / 'pid').read_text().strip()}), "
        f"{len(sh['names'])} row(s); log {Path(plan['out']) / 'logs' / (sh['label'] + '.router.out')}")
    return True


def start_guard(sh: dict, plan: dict) -> None:
    """The shard's runaway guard unit lra-<tag>-s<k>-guard (pressure mode) over its router unit and its containers, unless it runs.
    Review 2026-10-27: also for a shard a re-run finds running (after a wait limit the guards of running shards are kept, not stopped)."""
    if unit_state(sh["unit"] + "-guard")["active"] == "active":
        return
    k = plan["knobs"]
    sh_(["systemd-run", "--user", "--unit", sh["unit"] + "-guard", "-p", "MemoryMax=128M", "-p", f"RuntimeMaxSec={int(plan['runtime_hours'] * 3600)}",
         f"--working-directory={ROOT}", "-E", "PATH", "-E", "HOME", "-E", f"GUARD_UNITS={sh['unit']}.service",
         "-E", f"GUARD_DOCKER=lra-ag-{PREFIX}-hx-{sh['arm']}-", "-E", "LIMIT_MB=0", "-E", f"MIN_AVAIL_MB={k['guard_min_avail_mb']}",
         "-E", f"GUARD_LOG={Path(plan['out']) / 'logs' / (sh['label'] + '.guard.log')}", "/bin/bash", str(ROOT / "harness/runaway_guard.sh")],
        env=user_env())


def local_guard(plan: dict, log) -> None:
    """--runner local: one runaway guard over this launcher's own cgroup (every shard's Lean) and every shard's containers."""
    out = Path(plan["out"])
    try:
        cg = [l.split(":", 2)[2].strip() for l in open("/proc/self/cgroup") if l.startswith("0::")][0].rstrip("/").split("/")[-1]
    except (OSError, IndexError):
        cg = ""
    docker = " ".join(f"lra-ag-{PREFIX}-hx-{sh['arm']}-" for sh in plan["shards"])
    env = dict(os.environ, GUARD_UNITS=cg or "none", GUARD_DOCKER=docker, LIMIT_MB="0", MIN_AVAIL_MB=str(plan["knobs"]["guard_min_avail_mb"]),
               GUARD_LOG=str(out / "logs/guard.log"))
    p = subprocess.Popen(["/bin/bash", str(ROOT / "harness/runaway_guard.sh")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    (out / "guard_pid").write_text(f"{p.pid}\n"); log(f"runaway guard (local) pid {p.pid} over cgroup {cg or '?'} and the shards' containers")


def stop_units(plan: dict, log, routers: bool = True) -> None:
    """routers=True (`stop`): every unit. routers=False (the end of `run`): the guards and the fake model of the shards that no longer run.
    Review 2026-10-27: after a wait limit a shard still running kept running WITHOUT its runaway guard (and, in a rehearsal, without the
    fake model), and a re-run, which finds it running, never started the guard again; now its guard (and the fake) stay up."""
    out = Path(plan["out"])
    live = [] if routers else [sh for sh in plan["shards"] if running(sh, plan)]
    if live:
        log(f"kept the runaway guard{' and the fake model' if plan.get('fake_url') else ''} of {len(live)} shard(s) still running "
            f"({', '.join(sh['label'] for sh in live)})")
    if plan["runner"] == "systemd":
        units = ([sh["unit"] for sh in plan["shards"]] if routers else []) + [sh["unit"] + "-guard" for sh in plan["shards"] if sh not in live]
        units += [] if live else [f"lra-{plan['tag']}-fake"]
        for u in units:
            if unit_state(u)["active"] in ("active", "activating"):
                systemctl("stop", u, timeout=300); log(f"stopped {u}")
        return
    if live:   # --runner local: one guard and one fake for every shard
        return
    pids = [(out / "guard_pid"), (out / "fake_pid")] + ([Path(sh["run_dir"]) / "pid" for sh in plan["shards"]] if routers else [])
    for f in pids:
        try:
            os.killpg(int(f.read_text().split()[0]), signal.SIGTERM); log(f"SIGTERM to {f.name} group")
        except (OSError, ValueError):
            pass


def merge(plan: dict, rows: list[dict], log) -> tuple[list[str], dict]:
    out = Path(plan["out"])
    owners = {n: sh["label"] for sh in plan["shards"] for n in sh["names"]}
    lines, rep = FM.merge(rows, {sh["label"]: sh["run_dir"] for sh in plan["shards"]}, owners)
    FM.write(lines, out / "submission.jsonl")
    rep["shards_state"] = {sh["label"]: shard_done(sh)[1] for sh in plan["shards"]}
    # review 2026-10-27: a row over the cap (reported, or at the cap price) was only in the shard's summary.json and the router's exit 1, which
    # the launcher read as plain "done": counts per shard into the report and a WARNING line (the lists hold names: counts only)
    over = {}
    for sh in plan["shards"]:
        try:
            s = json.loads((Path(sh["run_dir"]) / "summary.json").read_text())
        except (OSError, ValueError):
            continue
        o, oc = len(s.get("over_cap") or []), len(s.get("over_cap_at_cap_price") or [])
        if o or oc:
            over[sh["label"]] = {"over_cap": o, "over_cap_at_cap_price": oc}
    if over:
        rep["over_cap"] = over
        log(f"WARNING: row(s) over the ${CAP} cap: " + "; ".join(f"{k} {v['over_cap']} reported, {v['over_cap_at_cap_price']} at the cap price"
                                                         for k, v in over.items()) + " (the shards' summary.json)")
    (out / "merge_report.json").write_text(json.dumps(rep, indent=1) + "\n")
    probs = FM.check(out / "submission.jsonl", rows)
    log(f"merged {out / 'submission.jsonl'}: {len(lines)} line(s) for {len(rows)} row(s): {rep['counts']['shard']} from the shards, "
        f"{rep['counts']['seed']} seed; check {'OK' if not probs else 'FAILED: ' + '; '.join(probs[:4])}")
    return probs, rep


def wait(plan: dict, log, a) -> bool:
    """Until every shard has finished (or the wait limit). Restarts an unfinished shard up to --max-restarts times. True = all finished."""
    t0, last_report = time.time(), 0.0
    restarts = {sh["label"]: 0 for sh in plan["shards"]}
    ended_at: dict = {}
    while True:
        states = {}
        for sh in plan["shards"]:
            if running(sh, plan):
                states[sh["label"]] = "running"; ended_at.pop(sh["label"], None); continue
            done, why = shard_done(sh)
            if done:
                states[sh["label"]] = "done"
                if plan["runner"] == "systemd" and unit_state(sh["unit"] + "-guard")["active"] == "active":
                    systemctl("stop", sh["unit"] + "-guard")
                continue
            rc = last_exit(sh)
            ended_at.setdefault(sh["label"], time.time())
            if (Path(plan["out"]) / STOP_FILE).exists():   # review 2026-10-27: `stop` ran; was: a waiting `run` restarted the shard it stopped
                states[sh["label"]] = f"stopped ({why})"
            elif rc not in NO_RESTART_RC and restarts[sh["label"]] < a.max_restarts:
                if time.time() - ended_at[sh["label"]] >= a.restart_delay:
                    restarts[sh["label"]] += 1
                    log(f"shard {sh['label']}: ended unfinished ({why}); restart {restarts[sh['label']]}/{a.max_restarts} (resumes the run dir)")
                    launch(sh, plan, log); ended_at.pop(sh["label"], None)
                    states[sh["label"]] = "running"; continue
                states[sh["label"]] = f"restarting ({why})"
            else:
                states[sh["label"]] = f"failed ({why})"
        if time.time() - last_report >= a.report_every:
            last_report = time.time()
            for sh in plan["shards"]:
                log(f"  {sh['label']}: {states[sh['label']]}; {progress(sh)}")
        if all(s == "done" or s.startswith(("failed", "stopped")) for s in states.values()):
            return all(s == "done" for s in states.values())
        if time.time() - t0 > a.wait_hours * 3600:
            log(f"wait limit {a.wait_hours:g} h passed: merging what exists (shards still running keep running; `run` again later)")
            return False
        time.sleep(a.poll)


# ---------------------------------------------------------------------------------------------------------------- commands
def load_plan(out: Path) -> dict | None:
    try:
        return json.loads((out / "plan.json").read_text())
    except (OSError, ValueError):
        return None


def cmd_run(a, plan_only: bool = False) -> int:
    out = Path(a.out).expanduser().resolve(); out.mkdir(parents=True, exist_ok=True)
    log = Log(out)
    rows = FR.load(a.rows)
    plan = load_plan(out)
    if plan and plan.get("rows_sha256") != FR.sha256_file(a.rows):
        log(f"refused: {out} holds a run of another rows file (plan.json); use a new --out"); return 2
    if plan and bool(plan.get("fake_model")) != bool(a.fake_model):
        # review 2026-10-27: the plan's mode wins on a resume, so a real `run` on a rehearsal's --out (same rows file) ran the fake model
        # again and kept its "finished" shards as the upload, and a `--fake-model` run on a real run's --out resumed it with the real key
        log(f"refused: {out} holds a {'$0 rehearsal (--fake-model)' if plan.get('fake_model') else 'real run'}; this command is "
            f"{'a rehearsal' if a.fake_model else 'a real run'}: use a new --out"); return 2
    if plan:
        log(f"resuming the plan in {out / 'plan.json'} (created {plan['created']}; its shards and knobs are kept)")
    else:
        other = [p for p in (ROOT / "probe/heldout").glob(f"{PREFIX}-hx-{a.tag}-s*")] if (ROOT / "probe/heldout").is_dir() else []
        if other and not a.reuse_tag:
            log(f"refused: --tag {a.tag} was used by another run of this checkout ({other[0]}): pick a new --tag (or --reuse-tag)"); return 2
        plan = make_plan(a, out, rows, log)
    print_plan(plan, log)
    bad = preflight(plan, rows, a, log)
    if bad:
        log(f"REFUSED before launch: {len(bad)} check(s) failed (above)"); return 2
    if plan_only:
        sh = plan["shards"][0]
        log("router command of shard s1 (names elided): python3 -u harness/router.py " +
            " ".join(shlex.quote(x) for x in router_args(dict(sh, names=[f"<{len(sh['names'])} names>"]), plan)))
        return 0
    try:   # review 2026-10-27: a refusal here is a refusal before launch (exit 2, in launcher.log), not a bare SystemExit (exit 1)
        rec = FR.stage(a.rows, a.heartbeats, jobs=max(1, int(plan["knobs"]["compile_slots"])), force=a.force_stage, log=log)
    except SystemExit as e:
        log(f"REFUSED before launch (staging the rows): {e}"); return 2
    plan["staged"] = rec
    if plan["fake_model"]:
        if not KEY_FILE.exists():   # agent_docker mounts the preset's key file: a missing source would become a root-owned directory
            KEY_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700); KEY_FILE.write_text(PLACEHOLDER); os.chmod(KEY_FILE, 0o600)
            plan["placeholder_key"] = True; log(f"fake model: placeholder {KEY_FILE} (no key; removed at the end)")
        plan["fake_url"] = start_fake(plan, log)
    else:
        try:
            plan["key"] = install_key(a, log)
        except (SystemExit, OSError) as e:   # an empty key, an unreadable --key-file (never the key itself: neither message holds it)
            log(f"REFUSED before launch (the key): {type(e).__name__}: {e if isinstance(e, SystemExit) else e.strerror}"); return 2
    if (out / STOP_FILE).exists():   # `run` again after a `stop`: resume
        (out / STOP_FILE).unlink(); log("an earlier stop request is cleared: resuming")
    (out / "plan.json").write_text(json.dumps(plan, indent=1) + "\n")
    if plan["runner"] == "local":
        local_guard(plan, log)
    for sh in plan["shards"]:
        if running(sh, plan):
            log(f"shard {sh['label']}: already running")
            if plan["runner"] == "systemd":
                start_guard(sh, plan)   # review 2026-10-27: its guard, should an earlier `run` have left it without one
            continue
        done, why = shard_done(sh)
        if done:
            log(f"shard {sh['label']}: finished earlier ({why})"); continue
        if not launch(sh, plan, log):
            log("REFUSED: a shard unit did not start"); return 2
    if a.no_wait:
        log("launched; --no-wait: `run_final.py status --out ...` to follow, `run_final.py merge --out ...` when done"); return 0
    all_done = wait(plan, log, a)
    probs, rep = merge(plan, rows, log)
    timed_out = not all_done and any(running(sh, plan) for sh in plan["shards"])
    stop_units(plan, log, routers=False)
    # (review 2026-10-27: kept while a shard runs: a session container started later would mount a missing source as a root-owned directory)
    if plan.get("placeholder_key") and not timed_out and KEY_FILE.is_file() and KEY_FILE.read_text() == PLACEHOLDER:
        KEY_FILE.unlink(); log("fake model: placeholder key file removed")
    rc = 1 if probs else 3 if timed_out else 0 if all_done else 5
    log(f"exit {rc}: " + {0: "every shard finished; the upload file is complete", 1: "the merged file FAILS its check (merge_report.json)",
                          3: "the wait limit passed; merged what exists", 5: "the upload file is complete but a shard did not finish "
                          "(its rows carry best-so-far or seed lines); `run` again resumes it"}[rc])
    return rc


def cmd_status(a) -> int:
    out = Path(a.out).expanduser().resolve(); plan = load_plan(out)
    if not plan:
        print(f"no plan in {out}"); return 2
    for sh in plan["shards"]:
        st = "running" if running(sh, plan) else ("done" if shard_done(sh)[0] else shard_done(sh)[1])
        print(f"{sh['label']} [{sh['unit']}] {st}: {progress(sh)}")
    sub = out / "submission.jsonl"
    print(f"submission: {sub} " + ("(not merged yet)" if not sub.exists() else f"({len(sub.read_text().splitlines())} lines)"))
    return 0


def cmd_merge(a) -> int:
    out = Path(a.out).expanduser().resolve(); plan = load_plan(out)
    if not plan:
        print(f"no plan in {out}"); return 2
    probs, _ = merge(plan, FR.load(plan["rows_file"]) if Path(plan["rows_file"]).exists() else FR.load(FR.STAGE_DIR / FR.ROWS_FILE), Log(out))
    return 1 if probs else 0


def cmd_stop(a) -> int:
    out = Path(a.out).expanduser().resolve(); plan = load_plan(out)
    if not plan:
        print(f"no plan in {out}"); return 2
    log = Log(out)
    (out / STOP_FILE).write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ\n", time.gmtime()))   # first: a waiting `run` must not restart them
    log(f"stop requested ({out / STOP_FILE}): no shard is restarted until `run` is given again")
    stop_units(plan, log, routers=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "plan", "status", "merge", "stop"])
    ap.add_argument("--rows", help="the benchmark rows file (JSONL, the warm-up file's schema)")
    ap.add_argument("--heartbeats", help="reference heartbeats ({name, heartbeat} lines); default: the rows' own, else measured")
    ap.add_argument("--out", default=str(Path.home() / "lra-final"), help="everything of the run lands here (default ~/lra-final)")
    ap.add_argument("--key-file", help="a file holding the OpenRouter key (default: $OPENROUTER_API_KEY, else the existing key file)")
    ap.add_argument("--tag", default="final", help="unit and arm names: lra-<tag>-s<k> (default final)")
    ap.add_argument("--shards", type=int, default=4)
    ap.add_argument("--runner", choices=["systemd", "local"], default="systemd", help="systemd user units (memory caps, default) or "
                    "child processes of this command (no memory caps; it must stay running)")
    for n in ("workers", "jobs", "compile-slots", "router-mem-gb", "memgate-claim-mb", "memgate-reserve-mb", "brief-row-workers",
              "brief-compile-workers", "brief-docker-memory-gb", "agent-docker-memory-gb"):
        ap.add_argument(f"--{n}", type=int, default=None, help="override the host-derived knob (harness/host_knobs.py)")
    ap.add_argument("--cpu-weight", type=int, default=100); ap.add_argument("--runtime-hours", type=float, default=60.0)
    ap.add_argument("--wait-hours", type=float, default=61.0); ap.add_argument("--max-restarts", type=int, default=1)
    ap.add_argument("--restart-delay", type=float, default=300.0); ap.add_argument("--poll", type=float, default=30.0)
    ap.add_argument("--report-every", type=float, default=600.0); ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--scratch-root", help="the sessions' private compile scratch (default <out>/scratch; a fast local disk if there is one)")
    ap.add_argument("--min-free-gb", type=float, default=20.0)
    ap.add_argument("--force-stage", action="store_true", help="replace another staged rows file in data/final/")
    ap.add_argument("--reuse-tag", action="store_true")
    # $0 rehearsal only
    ap.add_argument("--fake-model", action="store_true", help="rehearsal: a scripted local model instead of OpenRouter ($0)")
    ap.add_argument("--shared-slots", type=int, default=None, help="rehearsal: every shard's router shares one pool of N compile slots")
    ap.add_argument("--router-extra", default="", help="rehearsal: router flags appended to the frozen command")
    ap.add_argument("--ladder-extra", default="", help="rehearsal: hx_heldout flags appended to the frozen --ladder-args")
    return ap


def main(argv=None) -> int:
    ap = build_parser(); a = ap.parse_args(argv)
    if a.cmd in ("run", "plan") and not a.rows:
        ap.error("--rows is required")
    if (a.router_extra or a.ladder_extra or a.shared_slots) and not a.fake_model:
        ap.error("--router-extra / --ladder-extra / --shared-slots change the frozen pipeline: rehearsal (--fake-model) only")
    return {"run": lambda: cmd_run(a), "plan": lambda: cmd_run(a, plan_only=True), "status": lambda: cmd_status(a),
            "merge": lambda: cmd_merge(a), "stop": lambda: cmd_stop(a)}[a.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
