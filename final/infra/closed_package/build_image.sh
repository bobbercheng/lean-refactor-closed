#!/usr/bin/env bash
# b66 closed package (2026-10-27): build the agent session image (default tag lra-agent:1, what the run's --agent-docker names) from
# infra/closed_package/Dockerfile, then smoke it: python, requests, git and rg inside, and the host's Lean toolchain mounted the way
# hx_heldout.agent_docker mounts it (read-only ~/.elan, HOME=/tmp) answers `lean --version`.
#   infra/closed_package/build_image.sh            IMAGE=<tag> to build another tag (the tests do)
set -euo pipefail
cd "$(dirname "$0")"
IMAGE=${IMAGE:-lra-agent:1}
docker build -q -t "$IMAGE" -f Dockerfile . > /dev/null
echo "built $IMAGE ($(docker image inspect -f '{{.Id}}' "$IMAGE" | cut -c1-19))"
docker run --rm "$IMAGE" sh -c 'python3 -c "import requests, sys; print(\"python\", sys.version.split()[0], \"requests\", requests.__version__)" && git --version && rg --version | head -1'
TC=$(ls -d "$HOME"/.elan/toolchains/*/ 2>/dev/null | head -1 || true)
if [ -n "$TC" ]; then
  docker run --rm --user "$(id -u):$(id -g)" -v "$HOME/.elan:$HOME/.elan:ro" -e HOME=/tmp -e ELAN_HOME="$HOME/.elan" "$IMAGE" "${TC}bin/lean" --version
else
  echo "no Lean toolchain under ~/.elan yet (install_envs.sh installs them): Lean smoke skipped"
fi
echo "IMAGE OK $IMAGE"
