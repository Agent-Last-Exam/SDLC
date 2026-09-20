#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier/post
trap 'rc=$?; if [ "$rc" -ne 0 ]; then echo -1 > /logs/verifier/reward.txt; fi' EXIT
python3 /tests/prepare.py
bash /opt/runtime/start-services.sh
for suite in core-unit core-e2e dash-unit dash-e2e; do
  set +e
  bash /opt/runtime/run-suite.sh "$suite" post
  result=$?
  set -e
  # pytest/Jest/Playwright report test failures with nonzero codes. Missing or
  # malformed reports remain verifier errors in the grader, never passes.
  mv "/logs/verifier/$suite-post" "/logs/verifier/post/$suite"
  echo "$result" > "/logs/verifier/post/$suite/exit-code.txt"
done
python3 /tests/grader.py
