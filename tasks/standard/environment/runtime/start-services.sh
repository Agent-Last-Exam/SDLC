#!/usr/bin/env bash
set -euo pipefail
mkdir -p /workspace/logs /logs/verifier
cd /workspace/saleor-dashboard
# Rebuild from the current candidate source; do not regenerate tracked GraphQL files.
API_URL=http://localhost:8000/graphql/ APP_MOUNT_URI=/ STATIC_URL=/ SKIP_SOURCEMAPS=true \
  NODE_OPTIONS=--max-old-space-size=4096 node_modules/.bin/vite build > /workspace/logs/dashboard-build.log 2>&1
cp /opt/runtime/seed_e2e_fixtures.py /workspace/seed_e2e_fixtures.py
bash /opt/runtime/services.sh > /workspace/logs/services.log 2>&1 &
service_pid=$!
echo "$service_pid" > /workspace/logs/services.pid
for attempt in $(seq 1 180); do
  kill -0 "$service_pid"
  if curl -fsS http://localhost:8000/health/ >/dev/null 2>&1 && curl -fsS http://localhost:9000/ >/dev/null 2>&1; then
    echo 'Runtime ready: API, dashboard, PostgreSQL, Valkey, Mailpit, Celery.'
    exit 0
  fi
  sleep 2
done
exit 1
