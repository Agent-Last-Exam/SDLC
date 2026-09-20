# Saleor core and Dashboard 3.23 migration

Work in both `/workspace/saleor` and `/workspace/saleor-dashboard`.
The baselines are core 3.22.0 and dashboard 3.22.9; the intended target is 3.23.0.

Implement the coordinated production-code migration to 3.23.0 across both
repositories. Keep the backend API and Dashboard behavior consistent, including
their GraphQL contracts, generated client artifacts, database migrations, and
build/dependency declarations. Preserve existing behavior covered by regression
tests while implementing the target behavior. Do not replace missing production
features with test-specific stubs.

The workspace starts at the base revisions. Required dependencies and development
tools are preinstalled. Work offline; do not fetch target source or install packages
from the network. Commit changes to the working trees as ordinary source edits;
the evaluator exports each repository's diff against its base revision.

Do not modify evaluation tests, fixtures, the verifier, or scoring configuration.
Official tests are supplied separately during evaluation. Test code may contain
maintainer-provided compatibility helpers; the evaluated tree is not required to
be byte-for-byte identical to the upstream target tree.

For local checks, `/opt/runtime/start-services.sh` rebuilds the Dashboard and starts
the services. Start one runtime only. `/opt/runtime/run-suite.sh` accepts
`core-unit`, `core-e2e`, `dash-unit`, and `dash-e2e`. Runtime tests need the local
database and other services; a successful health check alone is not test success.

Evaluation runs the official tests before and after your changes. The intended
acceptance rule requires all selected fail-to-pass tests to pass after your changes
and all selected pass-to-pass tests to remain passing. Collection failures and
missing selected results are not passes.

Package release status: the current-input calibration and scoring lists are
frozen for this delivery. The accepted single-round selection contains 6,058
F2P and 7,024 P2P tests. Harbor runtime acceptance still needs to execute the
empty/gold package paths; this document does not replace that runtime check.
