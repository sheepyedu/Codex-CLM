#!/bin/bash
set -u
task_base=/mount-data/Codex-CLM/experiments/workbuddy-codex-20261118
task_target="$task_base/formal-66"
export PATH="/mount-data/yangyang-h20-2gpu-train-20261107/env/skill100-20261110/runtime/usr/bin:$PATH"
export DOCKER_HOST=unix:///var/docker/proxy/docker-proxy.sock
export DOCKER_CONFIG=/mount-data/Claude-code-CLM/experiments/workbuddy-20261118/docker-config
export PYTHONPATH="$task_base/source-environment-v5/benchmarks/workbuddy:$task_base/source-environment-v5/benchmarks:$task_base/source-environment-v5:$task_base/framework"
exec 9>"$task_base/resume66.owner.lock"
if ! flock -n 9; then
  printf '%s\n' 'Another owner holds the exact resume66 lock.'
  exit 75
fi
printf '%s\n' "$$" > "$task_base/resume66.owner.pid"
/mount-data/Claude-code-CLM/experiments/workbuddy-20261118/.venv/bin/python \
  "$task_base/resume_after_user_confirmed_access.py" \
  "$task_base/formal-65" "$task_target" "$task_base/USER_PROVIDER_CONFIRMATION_01.json" \
  > "$task_base/formal66-controller.log" 2>&1 &
task_child_pid=$!
printf '%s\n' "$task_child_pid" > "$task_base/resume66.child.pid"
wait "$task_child_pid"
task_exit_status=$?
printf '%s\n' "$task_exit_status" > "$task_base/resume66.owner.exit"
if [ -d "$task_target" ]; then
  printf '%s\n' "$task_exit_status" > "$task_target/controller.exit"
fi
exit "$task_exit_status"
