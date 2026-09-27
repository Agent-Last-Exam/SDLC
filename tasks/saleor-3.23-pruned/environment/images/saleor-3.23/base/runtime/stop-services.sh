#!/usr/bin/env bash
set -euo pipefail

pid_file=/workspace/logs/services.pid
if [ ! -s "$pid_file" ]; then exit 0; fi

service_pid=$(cat "$pid_file")
kill "$service_pid" 2>/dev/null || true
for _ in $(seq 1 30); do
  if ! kill -0 "$service_pid" 2>/dev/null; then break; fi
  sleep 1
done
rm -f "$pid_file"
