#!/usr/bin/env bash
# CLOSED RUN 3 (2026-11-02 ~19:30 UTC: run 3 on a second VM, D4C/D4N in, upload the better whole run): closed-bets-d4 402c44d2 in CO=/scratch/final3 on lra-cpu2 (eastus2); run 2 = lra-cpu1 /workspace/final2-in/final2.sh.
#   bash /workspace/final3-in/final3.sh plan|fixenvs|checkenvs|run|launch|status|stop
# The exact command (scale-test review settings, no knob overrides; host defaults 4 workers, jobs 15, 8 slots, 96G, memgate 4000/4000):
#   python3 infra/closed_package/run_final.py run --rows ROWS --heartbeats HB --out OUT --tag final3 --scratch-root /scratch/work/final3 --shards 4 --runner systemd
# 2026-11-02 (env-link trap, docs/closed_run2.md 02:28 entry): the agent containers mount only the fully resolved parent of each worktree
# env link (harness/hx_heldout.py agent_docker), and the worktree links point into $CO/envs. A row's env must therefore be a REAL directory
# in $CO/envs, or the first hop breaks inside the container (bt1102: every session rc 1 in 1 s). `fixenvs` turns each env the rows use
# into a hardlinked real copy of its target (cp -al: no extra data, the reference step's edited files and marker kept); `run` and `launch`
# refuse while any of them is still a symlink.
# 2026-11-02 19:58: the launcher unit's MemoryMax 2G -> 48G: under 2G the scorer's memgate held envfix's reference compiles (claim 8 GB > the
# unit's room) until its 1800 s give-up, which delayed run 2's shards by 30 min; the shard routers have their own units (unchanged). The launcher used to call $IN/final.sh (run 1's name): fixed to this file.
set -uo pipefail
export PATH=$HOME/.elan/bin:$HOME/miniconda3/bin:/usr/local/bin:/usr/bin:/bin HOME=$HOME PYTHONUNBUFFERED=1
export XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
CO=/scratch/final3; IN=/workspace/final3-in; OUT=/home/lra/lra-final3; SELF=$IN/final3.sh
# 2026-11-02 13:36 UTC: code closed-bets-d4 0ea568e2; bets frozen from the Azure bet test (B2/B3/D1 dropped: no gain) and the $0 replays on
# closed run 1's 60 finals (D2 +0.044/row, D3 +0.000 but accept-gated, D4 +0.068, D4P +1.56/row on 11 rows, D4S +0.93 on Q5 without D4P);
# 12:55 UTC: D4, D4P and D4S ship where the test data supports them. docs/closed_run2.md.
# run 3: + D4C (closerprep) and D4N (simpnorm), decided 2026-11-02 ~19:30; code closed-bets-d4 402c44d2.
BETS=D2,D3,D4,D4P,D4S,D4C,D4N
COMMON=(--rows $IN/rows.jsonl --heartbeats $IN/heartbeats.jsonl --out $OUT --tag final3 --scratch-root /scratch/work/final3 --shards 4 --runner systemd --bets $BETS)
needed() { python3 $IN/final2_envs.py $CO $IN/rows.jsonl; }   # env dirs (relative to $CO/envs) of every pin of every row
checkenvs() {
  local n bad=0 e; n=$(needed) || { echo "ENVS CHECK FAILED: cannot list the rows' envs"; return 1; }
  for e in $n; do
    if [ -L "$CO/envs/$e" ]; then echo "SYMLINK (container trap): envs/$e -> $(readlink "$CO/envs/$e")"; bad=1
    elif [ ! -d "$CO/envs/$e" ]; then echo "MISSING: envs/$e"; bad=1; fi
  done
  [ $bad = 0 ] && echo "ENVS OK: $(echo $n | wc -w) env(s), all real directories in $CO/envs" || { echo "ENVS NOT READY: run $SELF fixenvs"; return 1; }
}
case "${1:-}" in
  plan)   cd $CO && python3 -u infra/closed_package/run_final.py plan "${COMMON[@]}" ;;
  fixenvs)
    n=$(needed) || exit 1
    for e in $n; do
      p=$CO/envs/$e; tmp=$CO/envs/.$e.new
      [ -L "$p" ] || { [ -d "$p" ] && echo "already real: $e" || echo "MISSING: $e"; continue; }
      t=$(readlink -f "$p"); [ -d "$t" ] || { echo "MISSING target: $e -> $t"; exit 1; }
      [ -e "$tmp" ] && { echo "leftover $tmp: move it away first"; exit 1; }
      nice -n 10 ionice -c3 cp -al "$t" "$tmp" && rm "$p" && mv "$tmp" "$p" && echo "real dir: $e (hardlinks of $t)" || { echo "FAILED: $e"; exit 1; }
    done
    checkenvs ;;
  checkenvs) checkenvs ;;
  run)    checkenvs || exit 1; cd $CO && python3 -u infra/closed_package/run_final.py run "${COMMON[@]}" ;;
  launch)
    checkenvs || exit 1
    systemctl --user reset-failed lra-final3-launch 2>/dev/null || true
    systemd-run --user --unit lra-final3-launch -p MemoryMax=48G -p RuntimeMaxSec=230000 --working-directory=$CO \
      -p StandardOutput=append:$IN/launch.log -p StandardError=append:$IN/launch.log /bin/bash $SELF run
    echo "launcher lra-final3-launch started $(date -u +%FT%TZ)" ;;
  status) cd $CO && python3 infra/closed_package/run_final.py status --out $OUT ;;
  stop)   cd $CO && python3 infra/closed_package/run_final.py stop --out $OUT; systemctl --user stop lra-final3-launch 2>/dev/null || true ;;
  *) echo "usage: $0 plan|fixenvs|checkenvs|run|launch|status|stop"; exit 2 ;;
esac
