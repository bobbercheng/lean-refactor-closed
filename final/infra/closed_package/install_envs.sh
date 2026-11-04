#!/usr/bin/env bash
# b66 closed package (retro A1 item 3; 2026-10-27): install everything a benchmark rows file needs on a fresh Ubuntu host (x86-64 or
# aarch64), from the repository root's copy of this script. Modelled on infra/vast/harness_setup.sh (the A100 harness setup, run on vast.ai
# hosts) with the env list derived from the ROWS instead of the warm-up file, LeanPool included:
#   1. tools: git curl zstd ripgrep jq (apt, when missing and apt works), python3 `requests`, elan (no default toolchain: each env's
#      lean-toolchain file installs its own on first use)
#   2. envs/final_envs.json = infra/closed_package/envs_from_rows.py --rows ROWS (one entry per (project, pinned toolchain))
#   3. optional RESTORE=1: infra/sync/restore_envs.sh first (our public Kaggle archives of the warm-up pins, anonymous HTTPS, ~20 min on a
#      fast disk instead of hours of builds); whatever it does not cover is built in step 4
#   4. per repository in parallel, its envs in sequence: an env that is built at its pin and whose modules are up to date
#      (`lake build --no-build`) is kept ("ENV OK <env> (present)"); otherwise the upstream clone (blobless for mathlib4 and LeanPool),
#      a worktree at the pinned commit, Mathlib's prebuilt cache (`lake exe cache get`, one at a time: parallel gets race on
#      ~/.cache/mathlib/curl.cfg), then `lake build` of the rows' modules (PutnamBench: `lake env true`, nothing to build)
#   5. python3 harness/final_rows.py check --rows ROWS --envs: every pin resolves to a built env at its commit
# Re-runnable: finished envs are skipped. Logs: envs/logs/install-*.log (INSTALL_LOGS=DIR puts them elsewhere); the last lines are "INSTALL DONE ok=N failed=M" and the check.
#   infra/closed_package/install_envs.sh ROWS.jsonl            (CHECK_ONLY=1: steps 2, 4's presence check and 5 only, nothing built)
# Disk: the 15 warm-up envs take ~117 GB plus ~30 GB of toolchains; LeanPool's env ~25 GB. Wall: a Mathlib-based env is minutes with the
# cache; LeanPool's TauCeti dependency ~16 min on 48 threads (infra/azure/leanpool_vm.sh); LEAN_NUM_THREADS bounds a build's threads.
set -u
# the rows path is resolved against the CALLER's directory, before the cd (review 2026-10-27: it was resolved after it, so a relative
# ROWS given from any directory but the repository root named a file that does not exist: "INSTALL FAILED: no env list")
ROWS=${1:?usage: install_envs.sh ROWS.jsonl}; ROWS=$(cd "$(dirname "$ROWS")" && pwd)/$(basename "$ROWS") || exit 2
[ -f "$ROWS" ] || { echo "no rows file $ROWS"; exit 2; }
cd "$(dirname "$0")/../.." || exit 2
ROOT=$PWD
export PATH="$HOME/.elan/bin:$PATH"; CHECK_ONLY=${CHECK_ONLY:-0}
PY=${PYTHON:-python3}
LOGS=${INSTALL_LOGS:-envs/logs}; mkdir -p "$LOGS"   # INSTALL_LOGS: another log directory
log() { echo "[$(date -u -Is)] $*"; }

if [ "$CHECK_ONLY" != 1 ]; then
  SUDO=""; [ "$(id -u)" = 0 ] || SUDO="sudo -n"
  missing=""; for b in git curl zstd rg jq; do command -v "$b" > /dev/null || missing="$missing $b"; done
  if [ -n "$missing" ]; then
    pk=${missing/rg/ripgrep}; log "apt:$pk"
    ($SUDO apt-get install -y -qq $pk || { $SUDO apt-get update -qq && $SUDO apt-get install -y -qq $pk; }) > $LOGS/install-apt.log 2>&1 \
      || log "WARNING: could not install$pk (no root?): install them by hand"
  fi
  # review 2026-10-27: a fresh Ubuntu 24.04 has no pip module for its python3 (and PEP 668 refuses a system install): apt's python3-requests
  $PY -c "import requests" 2> /dev/null || { log "pip: requests"; $PY -m pip install -q requests > $LOGS/install-pip.log 2>&1 || $PY -m pip install -q --break-system-packages requests >> $LOGS/install-pip.log 2>&1 \
    || $SUDO apt-get install -y -qq python3-requests >> $LOGS/install-pip.log 2>&1 || { $SUDO apt-get update -qq && $SUDO apt-get install -y -qq python3-requests; } >> $LOGS/install-pip.log 2>&1; $PY -c "import requests" 2> /dev/null || log "WARNING: python requests missing for $PY: install it by hand"; }
  if [ ! -x "$HOME/.elan/bin/elan" ]; then
    log "elan"; curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y --default-toolchain none > $LOGS/install-elan.log 2>&1
  fi
fi
export ENVS_JSON=${ENVS_JSON:-envs/final_envs.json}
$PY infra/closed_package/envs_from_rows.py --rows "$ROWS" --out "$ENVS_JSON" || { log "INSTALL FAILED: no env list"; exit 1; }
if [ "${RESTORE:-0}" = 1 ] && [ "$CHECK_ONLY" != 1 ]; then
  log "restore from the public Kaggle archives (infra/sync/restore_envs.sh)"; bash infra/sync/restore_envs.sh 8 > $LOGS/install-restore.log 2>&1
  log "restore: $(tail -1 $LOGS/install-restore.log)"
fi

build_env() {   # env commit cache mods... (one env; its log is the caller's redirect); never exits the caller
  local env=$1 commit=$2 cache=$3; shift 3; local mods="$*" head rc
  log "env $env @ ${commit:0:12}"
  if [ -f "envs/$env/.lra_envfix.json" ]; then   # closed run 2: the reference step's `... in` edits (infra/refhb/envfix.py) are undone first
    for f in $($PY -c "import json,sys; print(' '.join(json.load(open(sys.argv[1]))))" "envs/$env/.lra_envfix.json"); do git -C "envs/$env" checkout -q -- "$f" 2>/dev/null; done
    rm -f "envs/$env/.lra_envfix.json"; log "env $env: restored the reference step's edits; re-run infra/refhb/make_ref_heartbeats.py after the install"
  fi
  head=$(git -C "envs/$env" rev-parse HEAD 2>/dev/null || true)
  if [ "$head" = "$commit" ] && { [ -f "envs/$env/lakefile.lean" ] || [ -f "envs/$env/lakefile.toml" ]; }; then
    if [ -n "$mods" ]; then (cd "envs/$env" && lake build --no-build $mods > /dev/null 2>&1); else (cd "envs/$env" && lake env true > /dev/null 2>&1); fi \
      && { echo "ENV OK $env (present)"; return 0; }
    log "present but not up to date: building"
  fi
  [ "$CHECK_ONLY" = 1 ] && { echo "ENV MISSING $env (head ${head:0:12})"; return 0; }
  if [ ! -d "$CLONE/.git" ]; then
    log "clone $URL"
    if [ "$BLOB" = 1 ]; then git clone -q --filter=blob:none "$URL" "$CLONE"; else git clone -q "$URL" "$CLONE"; fi || { echo "ENV FAILED $env (clone)"; return 0; }
  fi
  if [ ! -e "envs/$env" ]; then
    (cd "$CLONE" && { git cat-file -e "$commit^{commit}" 2>/dev/null || git fetch -q origin "$commit"; } && git worktree add -q -f "$ROOT/envs/$env" "$commit") \
      || { echo "ENV FAILED $env (worktree at the pin)"; return 0; }
  fi
  [ "$(git -C "envs/$env" rev-parse HEAD)" = "$commit" ] || { echo "ENV FAILED $env (envs/$env exists at another commit: move it away)"; return 0; }
  if [ "$cache" = 1 ]; then
    mkdir -p "$HOME/.cache"; for t in 1 2 3; do (cd "envs/$env" && flock "$HOME/.cache/mathlib-cache.lock" lake exe cache get) && break; log "cache get attempt $t failed"; sleep 15; done
  fi
  if [ -n "$mods" ]; then (cd "envs/$env" && lake build $mods); rc=$?; else (cd "envs/$env" && lake env true); rc=$?; fi
  if [ $rc = 0 ]; then echo "ENV OK $env (built)"; else echo "ENV FAILED $env (lake build rc=$rc)"; fi
}

build_repo() {   # $1 = repo key in $ENVS_JSON: its envs in sequence (one clone, worktrees off it)
  local repo=$1
  read -r URL BLOB < <($PY -c "import json,sys; d=json.load(open('$ENVS_JSON')); v=next(v for v in d.values() if v['repo']==sys.argv[1]); print(v['url'], int(v.get('blobless', False)))" "$repo")
  if [ "$repo" = mathlib4 ]; then CLONE=envs/mathlib4; else CLONE=envs/$repo.git-main; fi
  export URL BLOB CLONE
  $PY -c "import json,sys; d=json.load(open('$ENVS_JSON')); [print(k, v['commit'], int(v['cache']), ' '.join(v['modules'])) for k, v in sorted(d.items()) if v['repo']==sys.argv[1]]" "$repo" |
  while read -r env commit cache mods; do
    build_env "$env" "$commit" "$cache" $mods >> "$LOGS/install-$env.log" 2>&1
    tail -n 1 "$LOGS/install-$env.log"
  done
}
export -f build_env build_repo log; export ROOT PY CHECK_ONLY LOGS
rm -f $LOGS/install-repo-*.log
log "environments of $ROWS ($($PY -c "import json; print(len(json.load(open('$ENVS_JSON'))))" ) env(s))"
for repo in $($PY -c "import json; print(' '.join(sorted({v['repo'] for v in json.load(open('$ENVS_JSON')).values()})))"); do
  build_repo "$repo" > "$LOGS/install-repo-$repo.log" 2>&1 &
done
wait
OK=$(cat $LOGS/install-repo-*.log | grep -c "^ENV OK"); BAD=$(cat $LOGS/install-repo-*.log | grep -c "^ENV \(FAILED\|MISSING\)")
grep -h "^ENV \(FAILED\|MISSING\)" $LOGS/install-repo-*.log
log "INSTALL DONE ok=$OK failed=$BAD"
$PY harness/final_rows.py check --rows "$ROWS" --envs | tail -n 1
[ "$BAD" = 0 ]
