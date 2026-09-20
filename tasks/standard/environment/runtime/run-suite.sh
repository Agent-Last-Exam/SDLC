#!/usr/bin/env bash
set -euo pipefail
suite=$1
round=${2:-1}
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
    exec pytest "${args[@]}"
    ;;
  dash-unit)
    cd /workspace/saleor-dashboard
    args=(--maxWorkers=2 --json --outputFile="$out/results.json")
    if [ "$TEST_SUITE" = base ]; then
      args+=(--transformIgnorePatterns 'node_modules/(?!\.pnpm|chroma-js|zod|popper\.js)')
    fi
    exec node_modules/.bin/jest "${args[@]}"
    ;;
  dash-setup|dash-e2e)
    cd /workspace/saleor
    python /workspace/seed_e2e_fixtures.py >"$out/seed.log" 2>&1
    cd /workspace/saleor-dashboard
    rm -rf playwright/.auth
    curl -fsS http://localhost:8000/health/ >"$out/health.txt"
    curl -fsS http://localhost:9000/ -o /dev/null
    export PLAYWRIGHT_JSON_OUTPUT_FILE="$out/results.json"
    args=(--max-failures=0 --workers=2 --reporter=list,json)
    if [ "$suite" = dash-setup ]; then args+=(--project=setup); else args+=(--grep '#e2e'); fi
    exec node_modules/.bin/playwright test "${args[@]}"
    ;;
  *) echo "Unknown suite: $suite" >&2; exit 2 ;;
esac
