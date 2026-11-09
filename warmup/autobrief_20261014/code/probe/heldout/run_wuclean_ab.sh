#!/usr/bin/env bash
# Auto-brief A/B (2026-10-14; docs/auto_brief_plan.md M3): one clean Sol
# ladder over the 15 warm-up rows with the best pipeline we can field: auto-brief from round 1 (measured start candidate + brief), the junk
# guard from round 1, and NO fresh restarts or rescue (clean runs: 27 restarts per run, 3-4 adopted, ~$6 each; rescue adopted 0). Same
# clean conditions otherwise (own whitelist worktree, container, stray masks, pattern cards, rungs $1/$2/$2.85). Floor guard over all runs.
set -euo pipefail
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
REF="$(git -C "$MAIN" rev-parse HEAD)"
U=lra-hx-wuclean-ab1
if systemctl --user is-active --quiet "$U"; then echo "$U already running"; exit 0; fi
systemctl --user reset-failed "$U" 2>/dev/null || true
systemd-run --user --unit "$U" -p MemoryMax=4G -p RuntimeMaxSec=50400 --working-directory="$MAIN" -E PATH -E HOME \
  python3 -u harness/hx_heldout.py --set warmup-clean --arm solab1 --ref "$REF" --preset gpt-6.1-sol --effort medium \
    --rungs 1.0,2.0,2.85 --workers 4 --max-rounds 20 --rescue 0 --no-lineage-rule --agent-pattern-cards \
    --agent-auto-brief --auto-brief-budget 80 --auto-brief-timeout 5400 \
    --agent-docker lra-agent:1 --agent-docker-memory 40g --agent-private-scratch "$HOME/source/lra-ab/scratch-wuclean-solab1" \
    --agent-mask-strays > /dev/null
echo "started $U at $REF"
G=lra-hx-wuclean-ab-guard
if ! systemctl --user is-active --quiet "$G"; then
  systemctl --user reset-failed "$G" 2>/dev/null || true
  systemd-run --user --unit "$G" --collect -p MemoryMax=256M -p RuntimeMaxSec=54000 --working-directory="$MAIN" -E PATH -E HOME \
    python3 -u probe/heldout/wuclean_guard.py --units lra-hx-wuclean1,lra-hx-wuclean2,$U --log probe/heldout/wuclean-ab-guard.log > /dev/null
  echo "started $G"
fi
