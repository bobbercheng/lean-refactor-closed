#!/usr/bin/env bash
# Restore the Lean toolchains and environments from the public Kaggle datasets instead of building them (pairs with pack_envs.sh and
# publish_envs_kaggle.sh; 2026-10-09). No credentials: public dataset files download anonymously over HTTPS and arrive as the
# raw .tar.zst. Every file in infra/vast/envs_kaggle.tsv is fetched (PAR at a time), checked against its sha256 and unpacked: elan-home
# into ~, toolchains into ~/.elan/toolchains, envs and git clones into envs/. Worktree links are repaired when the repo root is not
# /workspace/lra, where the envs were built. Then `lake build --no-build` proves every env's modules are up to date (nothing to rebuild).
#   infra/sync/restore_envs.sh [PAR=8]        from the repo root; last line "RESTORE DONE ..." or "RESTORE FAILED ..."
set -u -o pipefail
cd "$(dirname "$0")/../.." || exit 2
PAR=${1:-8}; T0=$(date +%s); export ROOT=$PWD DL=$PWD/.envs-download OWNER=${KAGGLE_OWNER:-bobber}
mkdir -p envs "$HOME/.elan/toolchains" "$DL"
missing=""; for b in curl tar sha256sum zstd; do command -v "$b" > /dev/null || missing="$missing $b"; done   # 2026-10-09: the vLLM image has no zstd
[ -n "$missing" ] && { apt-get install -y -qq $missing || { apt-get update -qq && apt-get install -y -qq $missing; }; } > /dev/null 2>&1
command -v zstd > /dev/null || { echo "RESTORE FAILED: zstd missing and could not be installed"; exit 1; }
fetch() {   # dataset file sha256
  local ds=$1 f=$2 sum=$3 t dest ok=0; t=$(date +%s)
  case "$f" in elan-home.*) dest=$HOME ;; leanprover--*) dest=$HOME/.elan/toolchains ;; *) dest=$ROOT/envs ;; esac
  for a in 1 2 3; do
    [ -f "$DL/$f" ] && echo "$sum  $DL/$f" | sha256sum -c --quiet - 2>/dev/null && { ok=1; break; }   # already downloaded and intact
    curl -sSfL --retry 3 -o "$DL/$f" "https://www.kaggle.com/api/v1/datasets/download/$OWNER/$ds/$f" &&
      echo "$sum  $DL/$f" | sha256sum -c --quiet - && { ok=1; break; }
    echo "retry $a: $f"; sleep 5
  done
  [ "$ok" = 1 ] && zstd -dc -T0 -q "$DL/$f" | tar -xf - -C "$dest" && rm -f "$DL/$f" && echo "restored $f ($(( $(date +%s) - t ))s)" || echo "FAILED $f"
}
export -f fetch
tail -n +2 infra/vast/envs_kaggle.tsv | xargs -P "$PAR" -L 1 bash -c 'fetch "$0" "$1" "$3"' | tee "$DL/restore.log"
T1=$(date +%s); BAD=$(grep -c "^FAILED" "$DL/restore.log")
export PATH="$HOME/.elan/bin:$PATH"
python3 - <<'EOF' > "$DL/plan.txt"
import json
for k, v in sorted(json.load(open("infra/vast/harness_envs.json")).items()):
    print(k, "mathlib4" if v["repo"] == "mathlib4" else f"{v['repo']}.git-main", " ".join(v["modules"]))
EOF
while read -r env clone mods; do
  [ "$ROOT" != /workspace/lra ] && git -C "envs/$clone" worktree repair "$ROOT/envs/$env" > /dev/null 2>&1
  if [ -n "$mods" ]; then (cd "envs/$env" && lake build --no-build $mods > /dev/null 2>&1); else (cd "envs/$env" && lake env true > /dev/null 2>&1); fi ||
    { echo "NOT UP TO DATE: $env"; BAD=$((BAD + 1)); }
done < "$DL/plan.txt"
echo "download+unpack $(( T1 - T0 ))s, check $(( $(date +%s) - T1 ))s"
[ "$BAD" = 0 ] && echo "RESTORE DONE: $(( $(wc -l < infra/vast/envs_kaggle.tsv) - 1 )) archives, $(( $(date +%s) - T0 ))s" || echo "RESTORE FAILED: $BAD problems, $(( $(date +%s) - T0 ))s"
