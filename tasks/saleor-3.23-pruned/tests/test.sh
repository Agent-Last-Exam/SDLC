#!/usr/bin/env bash
set -euo pipefail
export TEST_SUITE=target
export SALEOR_E2E_SEEDER=/tests/seed_e2e_fixtures.py

VERIFIER_DIR=/logs/verifier
mkdir -p "$VERIFIER_DIR"

grade_mode=$(python3 -c 'import json; print("grade" if json.load(open("/tests/config.json"))["status"] == "frozen" else "diagnose")')
if [ "$grade_mode" = grade ]; then
  python3 /tests/grader.py check
fi

finish() {
  if [ "$grade_mode" = grade ] && [ ! -s "$VERIFIER_DIR/reward.json" ] && [ ! -s "$VERIFIER_DIR/reward.txt" ]; then
    echo -1 > "$VERIFIER_DIR/reward.txt"
  fi
}
trap finish EXIT

run_phase() {
  local phase="$1"
  shift
  mkdir -p "$VERIFIER_DIR/$phase"
  set +e
  bash /opt/runtime/run-suite.sh "$phase" "$@"
  local status=$?
  set -e
  local suite
  for suite in "$@"; do
    mv "$VERIFIER_DIR/$suite-$phase" "$VERIFIER_DIR/$phase/$suite"
  done
  echo "[verifier] $phase rc=$status"
}

# C and D both start from the same base + E commit and use the same T.
python3 /tests/prepare.py pre
run_phase pre core-unit core-e2e dash-unit dash-e2e

# The runner starts D with a fresh database and no reused service processes.
python3 /tests/prepare.py post
run_phase post core-unit core-e2e dash-unit dash-e2e

python3 /tests/grader.py "$grade_mode"
