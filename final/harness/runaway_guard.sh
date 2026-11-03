#!/usr/bin/env bash
# Runaway-compile guard (2026-10-22, speed/memory review): Lean's -M16000 is not enforced, and a heartbeat-measurement compile with
# maxHeartbeats 0 (PutnamBench rows; a grind closer) grew ~53 MB/s to 49 GB before its 900 s timeout. In a unit with systemd's default
# OOMPolicy=stop a kernel OOM kill of such a compile stops the whole run. This guard enforces the documented per-compile cap: a `lean`
# process in one of the GUARD_UNITS cgroups whose anonymous memory passes LIMIT_MB is killed (SIGKILL from a user process is not an OOM
# kill, so the unit keeps running; the caller sees a failed compile, the same outcome the timeout would give). Legitimate compiles measured
# 0.3-0.4 GB anon (+ ~5 GB shared .olean page cache); the heaviest documented compile peaks at 6.1 GB RSS. Containers are not touched.
#   systemd-run --user --unit lra-runaway-guard -p MemoryMax=128M -p RuntimeMaxSec=86400 --working-directory=$PWD -E PATH -E HOME \
#     -E GUARD_UNITS="lra-b62-regen-w.service" bash harness/runaway_guard.sh
set -u
LOG="${GUARD_LOG:-$(cd "$(dirname "$0")/.." && pwd)/probe/runaway_guard.log}"
# 2026-10-24: no per-compile cap by default.
# The guard acts only under host memory pressure: when MemAvailable < MIN_AVAIL_MB it kills the ONE lean with the largest anonymous
# memory in the guarded units/containers (a host-wide OOM would take the paid runs down with it; that is what happened on Oct 11).
# LIMIT_MB > 0 restores the old fixed per-compile cap (off by default).
LIMIT_MB="${LIMIT_MB:-0}"
MIN_AVAIL_MB="${MIN_AVAIL_MB:-12000}"
UNITS="${GUARD_UNITS:-lra-b62-regen-w.service}"
# GUARD_DOCKER: container-name prefixes (space separated) resolved to their docker-<id>.scope cgroups every pass, so per-round
# containers that come and go (ladder rounds, auto-brief) are covered without restarting the guard.
DPREFIX="${GUARD_DOCKER:-}"
echo "[$(date -u -Is)] start: pressure mode (kill the largest guarded lean when MemAvailable < ${MIN_AVAIL_MB} MB); fixed per-compile cap ${LIMIT_MB} MB (0 = off); units: ${UNITS}; containers: ${DPREFIX:-none}" >> "$LOG"
while true; do
  SCOPES=""
  if [ -n "$DPREFIX" ]; then
    for pre in $DPREFIX; do for id in $(docker ps -q --no-trunc --filter "name=^$pre" 2>/dev/null); do SCOPES="$SCOPES docker-$id.scope"; done; done
  fi
  best_pid=""; best_anon=0; best_cg=""
  for pid in $(pgrep -x lean || true); do
    cg=$(cat /proc/$pid/cgroup 2>/dev/null) || continue
    hit=0; for u in $UNITS $SCOPES; do case "$cg" in *"/$u"*) hit=1;; esac; done
    [ "$hit" = 1 ] || continue
    anon=$(awk '/^RssAnon:/ {print int($2/1024)}' /proc/$pid/status 2>/dev/null) || continue
    [ -n "$anon" ] || continue
    if [ "$LIMIT_MB" -gt 0 ] && [ "$anon" -gt "$LIMIT_MB" ]; then   # optional fixed cap (off by default)
      age=$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d ' '); f=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | awk '{print $NF}')
      kill -9 "$pid" 2>/dev/null && echo "[$(date -u -Is)] KILL lean $pid: ${anon} MB anon > ${LIMIT_MB} MB, age ${age}s, unit ${cg##*/}, file ${f##*/}" >> "$LOG"
      continue
    fi
    if [ "$anon" -gt "$best_anon" ]; then best_pid=$pid; best_anon=$anon; best_cg=$cg; fi
  done
  avail=$(awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo)
  if [ -n "$best_pid" ] && [ "$avail" -lt "$MIN_AVAIL_MB" ]; then   # host pressure: free the biggest compile, then let memory settle
    age=$(ps -o etimes= -p "$best_pid" 2>/dev/null | tr -d ' '); f=$(tr '\0' ' ' < /proc/$best_pid/cmdline 2>/dev/null | awk '{print $NF}')
    kill -9 "$best_pid" 2>/dev/null && echo "[$(date -u -Is)] KILL lean $best_pid: host MemAvailable ${avail} MB < ${MIN_AVAIL_MB} MB; largest guarded lean ${best_anon} MB anon, age ${age}s, unit ${best_cg##*/}, file ${f##*/}" >> "$LOG"
    sleep 5
  fi
  sleep 3
done
