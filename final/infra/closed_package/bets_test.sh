#!/usr/bin/env bash
# Bets test launcher (bet-backend-replay, 2026-11-02; a "sharper test" of the systematic bets before the next official run):
# TWO arms of the closed pipeline on the same test rows on ONE machine, both on the TEST backend (run_final.py --backend azure-vertex: Sol and
# Terra on Azure, Argon on Vertex, metered at the OpenRouter list tables under the same $3.00 cap), each with half the host
# (--host-share 0.5) and half the Azure Sol quota (--azure-sol-sessions), their own --out, --tag, units, scratch and hx worktrees:
#   control  every bet off (the 1350c858 pipeline exactly, on the test backend)
#   bets     the same command plus the bets given with --bets: a bet list (closed-bets: "B2,B3,R2,R3,D1,D2,D3,D4,D4P,D4S", any subset,
#            D4P / D4S only with D4, passed as run_final --bets) or run_final flags (a value starting with "-", e.g. "--end-dialect on" or
#            "--end-d4 on --end-d4-pointfree on"), and optionally --bet-router-extra /
#            --bet-ladder-extra (router / hx_heldout flags appended to the frozen command; allowed on the test backend only)
# Bounded: a driver unit lra-<tag>-bt waits at most --hours (every shard unit also has RuntimeMaxSec = hours + 0.5 h), restarts an arm's
# unfinished shards once, stops what still runs at the deadline (the routers write their outputs on SIGTERM), merges both arms and writes the
# paired readout (infra/closed_package/bets_readout.py: per-row d = bets - control, mean, median, wins, bootstrap / t CI, sign test, and
# both arms against closed run 1's finals).
#
#   bash infra/closed_package/bets_test.sh start --rows ROWS.jsonl --heartbeats HB.jsonl --test-rows TEST_ROWS.json --out OUT \
#        [--bets "B2,B3,..." | --bets "RUN_FINAL FLAGS"] [--bet-router-extra "FLAGS"] [--bet-ladder-extra "FLAGS"] [--tag TAG] [--hours 14] [--sol-sessions 6] \
#        [--shards 1] [--scratch-root DIR] [--run1 RUN1_FINALS_OR_OUT] [--run1-hb RUN1_HB.jsonl] [--dry]
#   bash infra/closed_package/bets_test.sh status|stop|readout --out OUT
# --dry: write OUT/test.env and both arms' `run_final.py plan` output (preflight included, nothing staged, launched or spent), then exit.
# Keys (read by the presets on the machine, never copied or printed): ~/.config/vexorium/azure_ai.json (deployments "sol", "terra"), the
# key files it names (run_final's preflight lists them), ~/.config/vexorium/vertex/proxy_key, and the Vertex proxy unit (lra-vertex-proxy,
# harness/vertex_proxy.py, gcloud `default` login). No OpenRouter key is read.
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); CO=$(cd "$HERE/../.." && pwd)
PY=$(command -v "${PYTHON:-python3}" || echo python3)   # absolute: the driver unit runs it (run_final needs python >= 3.11 + requests)
export PATH=$HOME/.elan/bin:$PATH PYTHONUNBUFFERED=1
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)} DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}
cmd=${1:-}; shift || true
ROWS= HB= TEST_ROWS= OUT= BETS= BET_RX= BET_LX= TAG= HOURS=14 SOL=6 SHARDS=1 SCR= RUN1= RUN1_HB= DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --rows) ROWS=$2; shift 2 ;; --heartbeats) HB=$2; shift 2 ;; --test-rows) TEST_ROWS=$2; shift 2 ;; --out) OUT=$2; shift 2 ;;
    --bets) BETS=$2; shift 2 ;; --bet-router-extra) BET_RX=$2; shift 2 ;; --bet-ladder-extra) BET_LX=$2; shift 2 ;;
    --tag) TAG=$2; shift 2 ;; --hours) HOURS=$2; shift 2 ;; --sol-sessions) SOL=$2; shift 2 ;; --shards) SHARDS=$2; shift 2 ;;
    --scratch-root) SCR=$2; shift 2 ;; --run1) RUN1=$2; shift 2 ;; --run1-hb) RUN1_HB=$2; shift 2 ;; --dry) DRY=1; shift ;;
    *) echo "bets_test: unknown argument $1" >&2; exit 2 ;;
  esac
done
[ -n "$OUT" ] || { echo "bets_test: --out is required" >&2; exit 2; }
OUT=$(mkdir -p "$OUT" && cd "$OUT" && pwd)
log() { echo "[bets_test $(date -u +%FT%TZ)] $*" | tee -a "$OUT/bets_test.log"; }

arm_args() {   # arm_args ctl|bet -> the run_final arguments of that arm (into the array ARGS)
  local arm=$1 suf; [ "$arm" = ctl ] && suf=c || suf=b
  ARGS=(--rows "$OUT/in/rows.jsonl" --heartbeats "$OUT/in/heartbeats.jsonl" --out "$OUT/$arm" --tag "${TAG}${suf}" --shards "$SHARDS"
        --runner systemd --backend azure-vertex --host-share 0.5 --azure-sol-sessions $(( SOL / 2 > 0 ? SOL / 2 : 1 ))
        --runtime-hours "$(awk -v h="$HOURS" 'BEGIN{print h + 0.5}')")
  [ -n "$SCR" ] && ARGS+=(--scratch-root "$SCR/$arm")
  if [ "$arm" = bet ]; then
    # shellcheck disable=SC2206
    case "$BETS" in
      "") ;;
      -*) ARGS+=($BETS) ;;           # run_final flags
      *) ARGS+=(--bets "$BETS") ;;   # a bet list (run_final --bets)
    esac
    [ -n "$BET_RX" ] && ARGS+=(--router-extra "$BET_RX")
    [ -n "$BET_LX" ] && ARGS+=(--ladder-extra "$BET_LX")
  fi
  return 0
}

state() { "$PY" "$CO/infra/closed_package/bets_readout.py" state --out "$OUT/$1"; }
jfield() { "$PY" -c "import json,sys; print(json.loads(sys.stdin.read()).get('$1'))"; }

do_readout() {
  for arm in ctl bet; do (cd "$CO" && "$PY" -u infra/closed_package/run_final.py merge --out "$OUT/$arm") >> "$OUT/bets_test.log" 2>&1; done
  local ra=(readout --ctl "$OUT/ctl" --bet "$OUT/bet" --json "$OUT/readout.json" --test-rows "$OUT/in/test_rows.json")
  [ -n "$RUN1" ] && ra+=(--run1 "$RUN1"); [ -n "$RUN1_HB" ] && ra+=(--run1-hb "$RUN1_HB")
  "$PY" "$CO/infra/closed_package/bets_readout.py" "${ra[@]}" | tee "$OUT/readout.txt"
}

case "$cmd" in
  start)
    for v in ROWS HB TEST_ROWS; do [ -n "${!v}" ] || { echo "bets_test start: --${v,,} is required" >&2; exit 2; }; done
    [ -e "$OUT/test.env" ] && { echo "bets_test: $OUT already holds a test (test.env); use a new --out" >&2; exit 2; }
    TAG=${TAG:-bt$(date -u +%m%d%H%M)}
    [ -z "$BETS$BET_RX$BET_LX" ] && echo "bets_test: WARNING: no bet given: both arms run the same command (an A/A test)" >&2
    { for v in ROWS HB TEST_ROWS OUT BETS BET_RX BET_LX TAG HOURS SOL SHARDS SCR RUN1 RUN1_HB; do printf '%s=%q\n' "$v" "${!v}"; done
      printf 'PYBIN=%q\n' "$PY"; printf 'CODE=%q\n' "$(git -C "$CO" rev-parse HEAD)"; printf 'STARTED=%q\n' "$(date -u +%s)"; } > "$OUT/test.env"
    "$PY" "$CO/infra/closed_package/bets_readout.py" subset --rows "$ROWS" --heartbeats "$HB" --test-rows "$TEST_ROWS" --out "$OUT/in" || exit 2
    cp "$TEST_ROWS" "$OUT/in/test_rows.json"
    for arm in ctl bet; do mkdir -p "$OUT/$arm"; cp "$OUT/in/heartbeats.jsonl" "$OUT/$arm/heartbeats.jsonl"; done
    if [ "$DRY" = 1 ]; then
      for arm in ctl bet; do arm_args $arm; log "dry: $arm: run_final.py plan ${ARGS[*]}"
        (cd "$CO" && "$PY" -u infra/closed_package/run_final.py plan "${ARGS[@]}") 2>&1 | tee -a "$OUT/plan_$arm.txt"; done
      rm -f "$OUT/test.env"; log "dry: done (nothing staged, launched or spent; test.env removed)"; exit 0
    fi
    U="lra-${TAG}-bt"; systemctl --user reset-failed "$U" 2>/dev/null || true
    RT=$(awk -v h="$HOURS" 'BEGIN{printf "%d", (h + 1) * 3600}')
    systemd-run --user --unit "$U" -p MemoryMax=2G -p RuntimeMaxSec="$RT" --working-directory="$CO" -E PATH="$PATH" -E HOME="$HOME" \
      -p StandardOutput=append:"$OUT/driver.log" -p StandardError=append:"$OUT/driver.log" /bin/bash "$HERE/bets_test.sh" _drive --out "$OUT" \
      || { echo "bets_test: driver unit $U did not start" >&2; exit 2; }
    log "driver unit $U started (tag $TAG, $HOURS h, rows $(wc -l < "$OUT/in/rows.jsonl"), Sol sessions $SOL over both arms); log $OUT/driver.log" ;;
  _drive)
    # shellcheck disable=SC1091
    . "$OUT/test.env"
    PY=$PYBIN
    deadline=$(( STARTED + $(awk -v h="$HOURS" 'BEGIN{printf "%d", h * 3600}') ))
    log "drive: control then bets (code $CODE; deadline $(date -u -d @$deadline +%FT%TZ))"
    first=1
    for arm in ctl bet; do
      arm_args $arm
      [ $first = 1 ] && ARGS+=(--force-stage); first=0   # the first arm stages the test rows into this checkout's data/final; the second finds them
      log "drive: $arm: run_final.py run ${ARGS[*]} --no-wait"
      (cd "$CO" && "$PY" -u infra/closed_package/run_final.py run "${ARGS[@]}" --no-wait) >> "$OUT/launch_$arm.log" 2>&1
      rc=$?
      if [ $rc -ne 0 ]; then
        log "drive: $arm refused or failed at launch (exit $rc, $OUT/launch_$arm.log): stopping the test"
        for a2 in ctl bet; do (cd "$CO" && "$PY" infra/closed_package/run_final.py stop --out "$OUT/$a2") >> "$OUT/bets_test.log" 2>&1; done
        exit 2
      fi
    done
    declare -A restarts=([ctl]=0 [bet]=0)
    while :; do
      done_all=1
      for arm in ctl bet; do
        s=$(state $arm); ad=$(echo "$s" | jfield all_done); ar=$(echo "$s" | jfield any_running)
        if [ "$ad" != True ]; then
          done_all=0
          if [ "$ar" != True ] && [ "${restarts[$arm]}" -lt 1 ] && [ "$(date -u +%s)" -lt "$deadline" ]; then
            restarts[$arm]=$(( ${restarts[$arm]} + 1 )); arm_args $arm
            log "drive: $arm ended unfinished ($s): resume ${restarts[$arm]}/1"
            (cd "$CO" && "$PY" -u infra/closed_package/run_final.py run "${ARGS[@]}" --no-wait) >> "$OUT/launch_$arm.log" 2>&1
          fi
        fi
      done
      [ $done_all = 1 ] && { log "drive: both arms finished"; break; }
      if [ "$(date -u +%s)" -ge "$deadline" ]; then
        log "drive: deadline reached: stopping what still runs (outputs are written on SIGTERM)"
        break
      fi
      sleep 120
    done
    # every unit of both arms down (the routers that still run write their outputs on SIGTERM; the guards of finished shards end here)
    for arm in ctl bet; do (cd "$CO" && "$PY" infra/closed_package/run_final.py stop --out "$OUT/$arm") >> "$OUT/bets_test.log" 2>&1; done
    do_readout
    log "drive: readout in $OUT/readout.txt / readout.json" ;;
  status)
    for arm in ctl bet; do echo "== $arm"; (cd "$CO" && "$PY" infra/closed_package/run_final.py status --out "$OUT/$arm"); done
    tail -n 5 "$OUT/bets_test.log" 2>/dev/null ;;
  stop)
    # shellcheck disable=SC1091
    [ -e "$OUT/test.env" ] && . "$OUT/test.env"
    [ -n "$TAG" ] && systemctl --user stop "lra-${TAG}-bt" 2>/dev/null
    for arm in ctl bet; do (cd "$CO" && "$PY" infra/closed_package/run_final.py stop --out "$OUT/$arm"); done
    log "stopped (run \`readout\` for what exists)" ;;
  readout)
    # shellcheck disable=SC1091
    [ -e "$OUT/test.env" ] && . "$OUT/test.env"
    do_readout ;;
  *) sed -n '2,26p' "$0"; exit 2 ;;
esac
