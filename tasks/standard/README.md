# Saleor 3.23 Standard Harbor Delivery (Self-Contained Build)

This package is self-contained. `environment/` is the complete base-image build
context, and `tests/Dockerfile` builds the verifier image from the local base
image. Neither Dockerfile uses an ACR image as `FROM`. ACR publishing is an
optional later step after local validation.

The package uses these unique local tags for reproducible manual builds:

```text
sdlcbench/saleor-3.23-base:standard-a-20260920
sdlcbench/saleor-3.23-test:standard-a-20260920
```

Harbor does not use the manual test tag when the task is run. Because
`task.toml` selects a separate verifier without a fixed
`[verifier.environment].docker_image`, Harbor builds the verifier from
`tests/Dockerfile` for the job. The manual test tag is useful for validating the
Dockerfile independently.

This is the self-contained exported delivery package for the Saleor 3.23 task.
Its image-build source is represented in this package under `environment/`; the
task and verifier source is exported from the current frozen standard inputs.
The package contains no application source tree, C adapter, or reference solution
source beyond the reference patch files required by Harbor's gold path.

The single C/D calibration run was accepted as sufficient for this release. The frozen lists contain **6,058 F2P** and **7,024 P2P** IDs in `tests/config.json`. The selection evidence is preserved at `trajectories/saleor/3.22.0__3.23.0/exp-20260918-seed-fix/artifacts/cd-selection-final-20260920`.

The previous ACR release used these digests (kept for provenance only):

- Base: `ai4se-registry-vpc.ap-northeast-1.cr.aliyuncs.com/swe/saleor-3.23@sha256:8e1ccef8e5e017a2462876cea21627195b91bc7a26a18c4635ba4ab9646134a8`
- Test: `ai4se-registry-vpc.ap-northeast-1.cr.aliyuncs.com/swe/saleor-3.23@sha256:4c7403f4334f4fa7b896400683cd0244e06ffed9b27e7f7dc5be571983b9a5e1`

The agent environment uses the locally built base image. Harbor builds the
separate verifier from `tests/Dockerfile`; that image applies the official test
patches and carries the test-only fixture support. The verifier runs post only:
it prepares the candidate, starts the runtime once, runs core unit, core E2E,
Dashboard unit, and Dashboard Playwright suites, then scores the post reports.
C adapter execution remains a build/calibration concern and is absent from this
package.

The solution directory contains the reference code patches for Harbor's gold path.
The tests directory contains verifier files, test patches, the frozen ID
configuration, and the test-only fixture seeder. `environment/` contains the
complete build context so the package can rebuild both runtime images without
using an ACR image as a build input.

`manifest.json` records the SHA-256 hash of every exported file except itself.
`release.json` records the release inputs and build mode. The release is frozen
according to the single-round decision; Harbor empty/gold execution remains the
runtime acceptance step.

## Prerequisites

The commands below assume Linux, Docker Engine with BuildKit, and at least 8
CPUs, 16 GiB memory, and 40 GiB free Docker storage. The base build needs
network access to fetch the pinned Saleor repositories, Python and Node
dependencies, Mailpit, and Playwright browsers. The resulting Harbor runtime is
configured with `network_mode = "no-network"`.

Harbor is already vendored in this repository under `tools/harbor-framework`
with its virtual environment in `tools/harbor-venv`. The reliable repository
local entry point is:

```bash
cd /home/river/sdlcbench
export HARBOR="tools/harbor-venv/bin/python -m harbor.cli.main"
```

If Harbor is installed globally, replace `$HARBOR` with `harbor` in the
commands below.

## Build Images

Set the package path and tags once. Use an absolute package path when invoking
Docker so the commands are independent of the current directory:

```bash
export PACKAGE_DIR=/home/river/sdlcbench/build/artifacts/saleor-3.23/standard
export BASE_TAG=sdlcbench/saleor-3.23-base:standard-a-20260920
export TEST_TAG=sdlcbench/saleor-3.23-test:standard-a-20260920
```

Build the base image first. This is the image used by the agent environment and
also the `FROM` image for the test Dockerfile:

```bash
docker build --progress=plain \
  --tag "$BASE_TAG" \
  "$PACKAGE_DIR/environment"
```

Then build the verifier image directly, if an independent Dockerfile check is
needed:

```bash
docker build --progress=plain \
  --tag "$TEST_TAG" \
  "$PACKAGE_DIR/tests"
```

The test build copies the verifier files into `/tests`, applies both official
test patches to the base checkouts, and checks that `tests/test.sh` is
executable. It must run after the base tag exists. Harbor builds an equivalent
verifier image automatically during a normal separate-verifier job, so this
second command is optional for Harbor itself.

Before a long build, Docker can validate the syntax without executing the
build steps:

```bash
docker build --check "$PACKAGE_DIR/environment"
docker build --check "$PACKAGE_DIR/tests"
```

## Start A Local Environment

`task start-env` is useful for an interactive check of the agent environment.
It uses the base tag from `task.toml`; `--all` makes the package's solution and
tests available to the environment setup:

```bash
$HARBOR task start-env \
  --path "$PACKAGE_DIR" \
  --env docker \
  --all \
  --non-interactive
```

This command only starts the environment. It does not constitute a verifier
score and it does not run the four post suites.

## Run Harbor Smoke

The smallest end-to-end Harbor wiring check uses the built-in `nop` agent. It
starts the agent environment, runs the collect hook, builds the separate
verifier from `tests/Dockerfile`, executes `tests/test.sh`, and invokes the
grader. It does not apply the reference code patch, so it checks the package
and test layer rather than the gold solution score:

```bash
cd /home/river/sdlcbench
$HARBOR run \
  --agent nop \
  --path "$PACKAGE_DIR" \
  --n-concurrent 1 \
  --jobs-dir /home/river/sdlcbench/jobs/saleor-standard-smoke
```

The command may run for a long time because `tests/test.sh` executes all four
post suites: `core-unit`, `core-e2e`, `dash-unit`, and `dash-e2e`. Use one
concurrent trial on this host to avoid multiplying the Saleor service memory
footprint. Results are stored below the job directory in a timestamped trial
directory. The most useful files are:

```text
job.log                         Harbor lifecycle and build errors
<task>/trial.log                Per-trial lifecycle
<task>/verifier/test-stdout.txt Raw verifier output
<task>/verifier/post/*          Suite reports and exit codes
result.json                     Job completion and trial counts
```

A successful wiring smoke has `n_errored_trials = 0`, a completed trial, a
verifier `test-stdout.txt`, and a grader result. Individual test failures are
reported by the grader and are different from a Harbor environment or verifier
startup error.

## Run An Agent Evaluation

Replace `nop` with an installed Harbor agent to evaluate an actual trajectory:

```bash
$HARBOR run \
  --agent <agent-name> \
  --path "$PACKAGE_DIR" \
  --n-concurrent 1 \
  --jobs-dir /home/river/sdlcbench/jobs/saleor-standard-agent
```

The reference code patches are under `solution/` for a gold-path run or local
inspection. The verifier always restores the recorded base commits before
applying the candidate model patch and the official test patches, so test files
cannot be used as the candidate implementation.

## Troubleshooting

- If Docker tries to pull an old `:runtime` image, check that `task.toml` and
  `tests/Dockerfile` both reference `standard-a-20260920` and rebuild the base
  tag explicitly.
- If Harbor reports `pull access denied` for a test image, do not add a fixed
  verifier `docker_image` just to bypass it. This package intentionally lets
  Harbor build `tests/Dockerfile`; inspect the verifier build output instead.
- If the host becomes memory constrained, stop the smoke job and rerun with one
  trial after removing stale containers from an earlier failed job. Keep the
  16 GiB verifier limit in `task.toml`.
