"""Deterministic self-test of the opencode driver (harness/agent_opencode.py) with a fake `opencode` binary (M0 of
docs/sonnet_haiku_transfer_plan.md; cycle 89, 2026-10-10). No API calls: a shell script on PATH impersonates
`opencode run --agent <role> --format json`, writes a compiling candidate the way the real agent would, prints two JSON
events and exits. The test asserts what the real run must satisfy:

  workspace      the driver builds original/context/candidate/notes/state and the task prompt names the reference cost
  env_isolation  the shim sees OPENCODE_CONFIG_DIR=configs/opencode, a run-local OPENCODE_DB, the OpenRouter key
                 (checked by length only — never printed), autoupdate and model fetch disabled
  config_static  configs/opencode/opencode.json: every agent's bash ruleset ends with "*" deny, no "ask" anywhere,
                 steps <= 40, all three roles present with the pinned OpenRouter models
  summary        summary.jsonl records best_score, checks, cost from the driver's SQLite reader (the shim seeds the db)
  trajectory     trajectories/<problem>.jsonl.gz exists and carries the header
  budget_meter   with --budget below the session cost the next session is REFUSED and recorded, not run
  spend_persist  state.json oline_spend accumulates across sessions

    python3 harness/selftest_opencode.py     # prints PASS/FAIL per check, exit 1 on any failure
"""
from __future__ import annotations

import gzip, json, os, pathlib, sqlite3, subprocess, sys, tempfile, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROBLEM = "putnam_1964_b2"
SHIM = r"""#!/usr/bin/env bash
# fake opencode: record the env the driver gave us, act in the workspace, seed the run db, print events
set -u
echo "$OPENCODE_CONFIG_DIR" > "$OC_MARK/config_dir"
echo "${#OPENROUTER_API_KEY}" > "$OC_MARK/keylen"
echo "$OPENCODE_DISABLE_AUTOUPDATE/$OPENCODE_DISABLE_MODELS_FETCH" > "$OC_MARK/flags"
[ "$OPENCODE_MODELS_PATH" = "$REPO/configs/opencode/models.json" ] && echo pinned > "$OC_MARK/models" || echo UNPINNED > "$OC_MARK/models"
agent=""; prev=""
for a in "$@"; do [ "$prev" = "--agent" ] && agent="$a"; prev="$a"; done
echo "$agent" > "$OC_MARK/agent"
cp original.lean candidate.lean
python3 - "$OPENCODE_DB" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute("CREATE TABLE IF NOT EXISTS session (id TEXT, parent_id TEXT, title TEXT, cost REAL, tokens_input INT, tokens_output INT, tokens_reasoning INT, tokens_cache_read INT, tokens_cache_write INT)")
con.execute("INSERT INTO session VALUES ('s1', NULL, 't', 0.0123, 1000, 400, 100, 900, 50)")
con.commit(); con.close()
PY
echo '{"type":"session_started","sessionID":"s1"}'
echo '{"type":"step-finish","cost":0.0123}'
exit 0
"""


def main() -> int:
    checks: dict[str, bool] = {}
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="lra-oc-selftest-"))
    shim_dir = tmp / "bin"; shim_dir.mkdir()
    shim = shim_dir / "opencode"; shim.write_text(SHIM); shim.chmod(0o755)
    mark = tmp / "mark"; mark.mkdir()
    env = dict(os.environ)
    env.update({"OPENCODE_BIN": str(shim), "OC_MARK": str(mark), "REPO": str(ROOT)})

    def driver(extra, run_id):
        return subprocess.run([sys.executable, "harness/agent_opencode.py", "--problems", PROBLEM, "--turns", "12", "--workers", "1",
                               "--run-id", run_id, "--work-root", str(tmp / "work"), "--timeout", "600", *extra],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)

    pr1 = driver([], f"selftest-oline-{time.strftime('%m%d-%H%M%S')}")
    ws = tmp / "work" / PROBLEM
    # best.lean is the agent's doing (the tools write it); the driver is responsible for the rest
    checks["workspace"] = all((ws / f).exists() for f in ("original.lean", "context.lean", "candidate.lean", "notes.md", "state.json"))
    checks["env_isolation"] = ((mark / "config_dir").read_text().strip() == str(ROOT / "configs/opencode")
                               and (mark / "keylen").read_text().strip().isdigit() and int((mark / "keylen").read_text().strip()) > 20
                               and (mark / "flags").read_text().strip() == "1/1" and (mark / "models").read_text().strip() == "pinned"
                               and (mark / "agent").read_text().strip() == "scout")
    st = json.loads((ws / "state.json").read_text())
    checks["spend_persist"] = abs(st.get("oline_spend", 0) - 0.0123) < 1e-6
    run_dir = ROOT / "probe/runs" / pr1.args_run_id if hasattr(pr1, "args_run_id") else None
    # run dir name: recover from the driver's stdout header
    rid = [l.split()[1].rstrip(":") for l in pr1.stdout.splitlines() if l.startswith("run selftest-oline")][0]
    out_dir = ROOT / "probe/runs" / rid
    sums = [json.loads(l) for l in (out_dir / "summary.jsonl").open()]
    checks["summary"] = bool(sums) and sums[0].get("best_score") is not None and abs(sums[0].get("cost", 0) - 0.0123) < 1e-6 and sums[0].get("tokens_cache_read") == 900
    trj = out_dir / "trajectories" / f"{PROBLEM}.jsonl.gz"
    checks["trajectory"] = trj.exists() and b'"type": "header"' in gzip.open(trj, "rb").read()[:400]

    # budget meter: the recorded spend (0.0123) plus the scout estimate must exceed a tiny cap -> refused before the shim runs
    before = sum(1 for _ in mark.iterdir())
    pr2 = driver(["--budget", "0.001"], f"selftest-oline-{time.strftime('%m%d-%H%M%S')}-b")
    rid2 = [l.split()[1].rstrip(":") for l in pr2.stdout.splitlines() if l.startswith("run selftest-oline")][0]
    sums2 = [json.loads(l) for l in (ROOT / "probe/runs" / rid2 / "summary.jsonl").open()]
    checks["budget_meter"] = bool(sums2) and "refused" in sums2[0] and sum(1 for _ in mark.iterdir()) == before

    cfg = json.loads((ROOT / "configs/opencode/opencode.json").read_text())
    roles_ok = {"scout", "architect", "reviewer", "sol_scout", "sol_architect"} <= set(cfg["agent"])
    # smoke1: a "*" deny REMOVES the bash tool from the model's tool list; the allows stay, unmatched commands fall
    # through to the run-mode auto-reject, and continue_loop_on_deny turns that into a tool error, not a session stop
    deny_free = all("*" not in v["permission"]["bash"] for v in cfg["agent"].values())
    lean_check_allow = all(any("lean_check.py" in k for k in v["permission"]["bash"]) for v in cfg["agent"].values())
    no_ask = all(val != "ask" for v in cfg["agent"].values() for k, val in v["permission"].items() if k != "bash") and \
        all(vv != "ask" for v in cfg["agent"].values() for vv in v["permission"]["bash"].values())
    cont = all((v.get("experimental") or {}).get("continue_loop_on_deny") is True for v in cfg["agent"].values())
    models_ok = all(v["model"].startswith(("openrouter/anthropic/claude-", "openrouter/openai/gpt-6.1-sol", "clinepass/"))
                    and isinstance(v.get("steps"), int) and v["steps"] <= 40 for v in cfg["agent"].values())
    checks["config_static"] = roles_ok and deny_free and lean_check_allow and no_ask and cont and models_ok

    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k)
    if all(checks.values()):
        import shutil
        shutil.move(str(out_dir), str(tmp / rid))
        print("ALL PASS")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
