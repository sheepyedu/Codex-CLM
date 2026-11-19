#!/bin/bash
set -u
task_base=/mount-data/Codex-CLM/experiments/workbuddy-codex-20261118
export PATH="/mount-data/yangyang-h20-2gpu-train-20261107/env/skill100-20261110/runtime/usr/bin:$PATH"
export DOCKER_HOST=unix:///var/docker/proxy/docker-proxy.sock
export DOCKER_CONFIG=/mount-data/Claude-code-CLM/experiments/workbuddy-20261118/docker-config
export PYTHONPATH="$task_base/source-environment-v6/benchmarks/workbuddy:$task_base/source-environment-v6/benchmarks:$task_base/source-environment-v6:$task_base/framework"
exec 9>"$task_base/resume68.owner.lock"
if ! flock -n 9; then exit 75; fi
printf '%s\n' "$$" > "$task_base/resume68.owner.pid"
/mount-data/Claude-code-CLM/experiments/workbuddy-20261118/.venv/bin/python \
 "$task_base/resume_after_provider_feedback.py" \
 "$task_base/formal-67" "$task_base/formal-68" "$task_base/USER_PROVIDER_FEEDBACK_RETRY_02.json" \
 > "$task_base/formal68-controller.log" 2>&1 &
task_pid=$!
printf '%s\n' "$task_pid" > "$task_base/resume68.child.pid"
wait "$task_pid"
task_status=$?
printf '%s\n' "$task_status" > "$task_base/resume68.owner.exit"
if [ -d "$task_base/formal-68" ]; then printf '%s\n' "$task_status" > "$task_base/formal-68/controller.exit"; fi
exit "$task_status"
