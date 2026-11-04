#!/usr/bin/env bash
# VM1 -> VM2 copy for closed run 3 (read-only on VM1; lowest priority): the 17 envs run 2 uses (real dirs in /workspace/final2/envs,
# envfix edits and markers included) -> VM2:/scratch/envs-pool/; ~/.elan -> VM2:~/.elan; run 2's rows + reference heartbeats -> VM2:/workspace/final3-in;
# docker image lra-agent:1 (save | load). Published copy: the destination and the key are variables (DEST, KEY); ours were a
# temporary key and firewall rule, both removed after the copy.
set -uo pipefail
export PATH=$HOME/miniconda3/bin:/usr/local/bin:/usr/bin:/bin
D=${DEST:?DEST=user@run-3-host}; KEY=${KEY:?KEY=a temporary ssh key the run-3 host accepts}; SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -o ServerAliveInterval=30"
log() { echo "[$(date -u +%T)] $*"; }
ENVS=$(python3 /workspace/final2-in/final2_envs.py /workspace/final2 /workspace/final2-in/rows.jsonl)
log "envs: $(echo $ENVS | wc -w)"
$SSH $D 'sudo mkdir -p /scratch/envs-pool && sudo chown lra:lra /scratch/envs-pool; mkdir -p /workspace/final3-in'
scp -q -i $KEY /workspace/final2-in/rows.jsonl /workspace/final2-in/heartbeats.jsonl /workspace/final2-in/heartbeats.jsonl.meta.json /workspace/final2-in/final2_envs.py $D:/workspace/final3-in/ && log "rows + heartbeats copied"
docker save lra-agent:1 | $SSH $D 'docker load' && log "docker image loaded"
echo "$ENVS" | xargs -P 4 -I{} sh -c "rsync -aH --exclude='LRAScratch/*' -e '$SSH' /workspace/final2/envs/{}/ $D:/scratch/envs-pool/{}/ && echo \"[\$(date -u +%T)] env {} done\" || echo \"[\$(date -u +%T)] env {} FAILED\""
rsync -aH -e "$SSH" $HOME/.elan/ $D:/home/lra/.elan/ && log "elan done" || log "elan FAILED"
log "XFER DONE"
