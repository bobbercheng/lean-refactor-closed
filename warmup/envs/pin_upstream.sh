#!/usr/bin/env bash
# Pin the upstream clones envs/<repo>.git-main to the HEADs the warm-up Sol run saw (recorded in its trajectories). Their HEAD drives
# the "UPSTREAM" digest in every opening message (harness/leantools.py upstream_digest) and what the model sees via git log/show;
# a clone made later shows newer upstream simplifications. Run after envs/setup_projects.sh.
set -euo pipefail
cd "$(dirname "$0")"
declare -A PIN=(
  [strata]=02f873ed7a89099aacae18e7b78e74ca5d4ef8db    # 2026-10-05
  [cslib]=ea16de32af9cd93796505668672297df9c422052     # 2026-10-05
  [physlib]=bae4db68ef61fc01a190fd232f82d2ad6508164e   # 2026-10-05
  [arklib]=35ddcaa83f683011f944f58904be779495a5709a    # 2026-10-04
)
for r in "${!PIN[@]}"; do
  d="$r.git-main"; [ -d "$d" ] || { echo "missing $d (run setup_projects.sh first)"; exit 1; }
  git -C "$d" cat-file -e "${PIN[$r]}^{commit}" 2>/dev/null || git -C "$d" fetch -q origin "${PIN[$r]}" || git -C "$d" fetch -q origin
  git -C "$d" checkout -q --detach "${PIN[$r]}" && echo "$r pinned at ${PIN[$r]:0:12}"
done
