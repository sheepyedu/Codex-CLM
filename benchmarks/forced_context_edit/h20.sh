#!/usr/bin/env bash
set -euo pipefail
umask 077
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
export PATH="/mount-data/yangyang-h20-2gpu-train-20261107/env/skill100-20261110/runtime/usr/bin:$PATH"
export DOCKER_HOST=unix:///var/docker/proxy/docker-proxy.sock
export DOCKER_CONFIG=/mount-data/Claude-code-CLM/experiments/workbuddy-20261118/docker-config
export DOCKER_BUILDKIT=0 PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$here:$repo/benchmarks/workbuddy:$repo/benchmarks:$repo:/mount-data/Codex-CLM/experiments/workbuddy-codex-20261118/framework"
python_bin=/mount-data/Claude-code-CLM/experiments/workbuddy-20261118/.venv/bin/python
if [[ "${1:-}" == smoke ]]; then shift; exec "$python_bin" "$here/smoke.py" "$@"; fi
exec "$python_bin" "$here/runner.py" "$@"
