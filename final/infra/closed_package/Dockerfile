# b66 closed package (retro A1 item 3; 2026-10-27): the agent session container (lra-agent:1) in one file. It is exactly the two images the
# runs used, infra/codex/Dockerfile (lra-codex:1: python:3.13-slim + git, ripgrep, ca-certificates, curl) and infra/agent/Dockerfile (+ requests
# 2.32.3 for llm/openai_compat.py); harness/test_b66_package.py keeps the RUN lines identical to theirs. Tools only: no key, no repository.
# hx_heldout.py --agent-docker mounts the line's worktree read-only, its work roots and records read-write, the envs read-only with a private
# compile scratch, ~/.elan read-only and the preset's one key file read-only (at the container's HOME=/tmp).
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ripgrep ca-certificates curl && apt-get clean
RUN pip install --no-cache-dir requests==2.32.3
