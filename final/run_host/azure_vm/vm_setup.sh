#!/usr/bin/env bash
# One-time base setup of the Azure CPU VM (Ubuntu 24.04 x86-64, admin user lra). Run as lra (uses sudo). Idempotent.
# Installs: build tools, git, curl, zstd, jq, ripgrep, mdadm, perf + sysstat, docker.io (+ buildx), Miniconda (Python 3.13, like our dev host's
# ~/miniconda3) with the harness's Python packages pinned to our development host's versions, user lingering for systemd --user units, /workspace.
# No credentials of any kind are installed here.
set -eu
log() { echo "[$(date -u -Is)] $*"; }
export DEBIAN_FRONTEND=noninteractive
log "apt"
sudo -E apt-get update -qq
sudo -E apt-get install -y -qq build-essential git curl wget ca-certificates zstd pigz pv jq ripgrep mdadm unzip htop tmux sqlite3 \
  docker.io docker-buildx rsync lsof psmisc sysstat linux-tools-azure "linux-tools-$(uname -r)" > /dev/null
sudo usermod -aG docker "$USER"
sudo systemctl enable --now docker > /dev/null 2>&1
sudo loginctl enable-linger "$USER"
# a run box: no unattended apt upgrades (needrestart would restart dockerd and kill the agent containers mid-run)
sudo systemctl disable --now apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service > /dev/null 2>&1 || true
sudo mkdir -p /workspace && sudo chown "$USER:$USER" /workspace
if ! "$HOME/miniconda3/bin/python3" -c "import sys; assert sys.version_info[:2] == (3, 13)" 2> /dev/null; then   # 3.13 like our development host (Miniconda latest is 3.14)
  [ -d "$HOME/miniconda3" ] && mv "$HOME/miniconda3" "$HOME/miniconda3.unused-$(date +%s)"
  log "miniconda"
  curl -sSfL -o /tmp/miniconda.sh https://repo.anaconda.com/miniconda/Miniconda3-py313_26.9.4-0-Linux-x86_64.sh
  bash /tmp/miniconda.sh -b -p "$HOME/miniconda3" > /dev/null && rm -f /tmp/miniconda.sh
fi
log "python packages"
"$HOME/miniconda3/bin/python3" -m pip install -q requests==2.34.2 anthropic==0.96.0 pytest==9.0.3 httpx==0.28.1 psutil==6.1.1 PyYAML==6.0.3
grep -q 'miniconda3/bin' "$HOME/.bashrc" || echo 'export PATH="$HOME/.elan/bin:$HOME/miniconda3/bin:$PATH"' >> "$HOME/.bashrc"
sudo install -m 755 "$(dirname "$0")/nvme_scratch.sh" /usr/local/sbin/lra-nvme-scratch.sh 2>/dev/null || true
log "SETUP DONE python=$("$HOME/miniconda3/bin/python3" --version 2>&1) docker=$(docker --version 2>/dev/null | cut -d, -f1)"
