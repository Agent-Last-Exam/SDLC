#!/usr/bin/env bash
set -euo pipefail

round=$1
shift

export SECRET_KEY=${SECRET_KEY:-sdlcbench-local-test-key}
export E2E_USER_PASSWORD=${E2E_USER_PASSWORD:-admin}
export E2E_PERMISSIONS_USERS_PASSWORD=${E2E_PERMISSIONS_USERS_PASSWORD:-password}
export RUNTIME_LOG_DIR="/logs/verifier/runtime-$round"
export RUNTIME_STATE_DIR
RUNTIME_STATE_DIR=$(mktemp -d /tmp/sdlcbench-runtime.XXXXXX)
chmod 755 "$RUNTIME_STATE_DIR"
mkdir -p "$RUNTIME_LOG_DIR"

run_suite() (
  suite=$1
  out="/logs/verifier/$suite-$round"
  mkdir -p "$out"
  export OUT="$out"
  case "$suite" in
  core-smoke|core-unit|core-e2e)
    cd /workspace/saleor
    unset CELERY_BROKER_URL EMAIL_URL
    if [ "$TEST_SUITE" = base ]; then unset CACHE_URL; fi
    args=(--continue-on-collection-errors --maxfail=0 --allow-hosts localhost,127.0.0.1,::1,cache -n 2 --junitxml="$out/results.xml" -o junit_family=legacy)
    case "$suite" in
      core-smoke) args+=(saleor/core/tests/test_core.py saleor/core/tests/test_weight.py) ;;
      core-unit) args+=(-m 'not e2e') ;;
      core-e2e) args+=(-m e2e) ;;
    esac
    pytest "${args[@]}"
    ;;
  dash-unit)
    cd /workspace/saleor-dashboard
    args=(--maxWorkers=2 --json --outputFile="$out/results.json")
    if [ "$TEST_SUITE" = base ]; then
      args+=(--transformIgnorePatterns 'node_modules/(?!\.pnpm|chroma-js|zod|popper\.js)')
    fi
    node_modules/.bin/jest "${args[@]}"
    ;;
  dash-setup|dash-e2e)
    cd /workspace/saleor
    python "${SALEOR_E2E_SEEDER:-/workspace/seed_e2e_fixtures.py}" >"$out/seed.log" 2>&1
    cd /workspace/saleor-dashboard
    rm -rf playwright/.auth
    curl -fsS http://localhost:8000/health/ >"$out/health.txt"
    curl -fsS http://localhost:9000/ -o /dev/null
    export PLAYWRIGHT_JSON_OUTPUT_FILE="$out/results.json"
    args=(--max-failures=0 --workers=2 --reporter=list,json)
    if [ "$suite" = dash-setup ]; then args+=(--project=setup); else args+=(--grep '#e2e'); fi
    node_modules/.bin/playwright test "${args[@]}"
    ;;
  *) echo "Unknown suite: $suite" >&2; exit 2 ;;
  esac
)

finish() {
  trap - EXIT INT TERM
  bash /opt/runtime/stop-services.sh
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

bash /opt/runtime/start-services.sh
status=0
for suite in "$@"; do
  set +e
  run_suite "$suite"
  suite_status=$?
  set -e
  echo "[runner] $round/$suite rc=$suite_status"
  if [ "$suite_status" -ne 0 ]; then status=1; fi
done
exit "$status"
