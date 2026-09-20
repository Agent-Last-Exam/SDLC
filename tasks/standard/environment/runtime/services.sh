#!/usr/bin/env bash
# Full runtime profile for saleor 3.23.0: starts every service the target
# compose pin declares (minus jaeger), all on 127.0.0.1 in one container.
set -Eeuo pipefail

log() { printf '[entrypoint] %s\n' "$*"; }

LOGDIR=/workspace/logs
mkdir -p "$LOGDIR"

# --- PostgreSQL 15 ---
log "starting PostgreSQL 15"
pg_ctlcluster 15 main start
until pg_isready -h 127.0.0.1 -p 5432 -U postgres >/dev/null 2>&1; do sleep 1; done

# CREATEDB is required by pytest-xdist workers, which each create their own
# test_saleor_gw* database.
su - postgres -c "psql -v ON_ERROR_STOP=1 -c \"ALTER USER postgres PASSWORD 'postgres';\""
su - postgres -c "psql -v ON_ERROR_STOP=1 -tc \"SELECT 1 FROM pg_roles WHERE rolname='saleor'\" | grep -q 1 \
  || psql -v ON_ERROR_STOP=1 -c \"CREATE USER saleor WITH PASSWORD 'saleor' CREATEDB SUPERUSER;\""
su - postgres -c "psql -v ON_ERROR_STOP=1 -tc \"SELECT 1 FROM pg_database WHERE datname='saleor'\" | grep -q 1 \
  || createdb -O saleor saleor"

# replica_user.sql from the platform repo. DATABASE_URL_REPLICA points at this
# role, and saleor reads django_site through the replica connection during
# migrations (saleor/site/patch_sites.py new_get_current), so the role must
# exist AND hold SELECT on tables the migrations create later.
#
# It must be run AS saleor, not as postgres: ALTER DEFAULT PRIVILEGES only
# affects objects created by the role that issued it, and migrations create
# their tables as saleor. Compose gets this for free because the postgres
# image runs init SQL as POSTGRES_USER=saleor.
su - postgres -c "psql -v ON_ERROR_STOP=1 -tc \"SELECT 1 FROM pg_roles WHERE rolname='saleor_read_only'\" | grep -q 1 \
  || PGPASSWORD=saleor psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U saleor -d saleor -f /workspace/replica_user.sql"

# --- Valkey 8.1 (compose: cache) ---
log "starting valkey 8.1"
mkdir -p /var/lib/valkey
valkey-server --port 6379 --bind 127.0.0.1 --daemonize yes \
  --dir /var/lib/valkey --save '' --appendonly no
until valkey-cli -h 127.0.0.1 ping 2>/dev/null | grep -q PONG; do sleep 1; done

# --- Mailpit (compose: mailpit) ---
log "starting mailpit"
# 0.0.0.0 so the EXPOSEd ports are reachable from the host; in-container
# clients still use 127.0.0.1.
mailpit --listen 0.0.0.0:8025 --smtp 0.0.0.0:1025 \
  >"$LOGDIR/mailpit.log" 2>&1 &

# --- Database schema + sample data ---
cd /workspace/saleor
if [ "${SALEOR_SKIP_INIT:-0}" != "1" ]; then
  log "running migrations"
  python manage.py migrate --noinput

  # populatedb is idempotent-ish; guard on the superuser existing so restarts
  # don't re-seed.
  if ! python manage.py shell -c \
      "from saleor.account.models import User; import sys; sys.exit(0 if User.objects.filter(email='admin@example.com').exists() else 1)" \
      >/dev/null 2>&1; then
    log "seeding sample data (populatedb --createsuperuser)"
    python manage.py populatedb --createsuperuser >"$LOGDIR/populatedb.log" 2>&1
  else
    log "sample data already present, skipping populatedb"
  fi
fi

# --- Saleor API (compose: api) ---
log "starting saleor API on :8000"
# Dashboard VariantUpdate sends four root mutations. Scope the deployment limit
# to the API process; pytest retains upstream settings and validator coverage.
GRAPHQL_MUTATION_COUNT_LIMIT=4 uvicorn saleor.asgi:application --host 0.0.0.0 --port 8000 \
  >"$LOGDIR/api.log" 2>&1 &

# --- Celery worker (compose: worker) ---
log "starting celery worker"
celery -A saleor --app=saleor.celeryconf:app worker --loglevel=info --concurrency=1 -B --schedule="$LOGDIR/celerybeat-schedule" \
  >"$LOGDIR/celery.log" 2>&1 &

# --- Dashboard via nginx (compose: dashboard) ---
log "starting nginx for dashboard on :9000"
nginx -g 'daemon off;' >"$LOGDIR/nginx.log" 2>&1 &

# --- Readiness ---
log "waiting for API /health/"
for _ in $(seq 1 120); do
  curl -fsS http://127.0.0.1:8000/health/ >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS http://127.0.0.1:8000/health/ >/dev/null

log "waiting for dashboard"
for _ in $(seq 1 60); do
  curl -fsS -o /dev/null http://127.0.0.1:9000/ && break
  sleep 2
done

cleanup() {
  nginx -s quit 2>/dev/null || true
  pkill -f 'celery -A saleor' 2>/dev/null || true
  pkill -f 'uvicorn saleor.asgi' 2>/dev/null || true
  pkill mailpit 2>/dev/null || true
  valkey-cli -h 127.0.0.1 shutdown nosave 2>/dev/null || true
  pg_ctlcluster 15 main stop 2>/dev/null || true
}
trap cleanup EXIT INT TERM

log "full runtime profile ready: api=8000 dashboard=9000 pg=5432 valkey=6379 smtp=1025 mailpit-ui=8025"
tail -f /dev/null &
wait "$!"
