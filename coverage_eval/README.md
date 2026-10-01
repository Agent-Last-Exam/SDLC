# Configurable Harbor coverage evaluation

The evaluator runs official and candidate-authored tests separately on the
candidate production code. It produces supplemental coverage reports and can
invoke the task's existing grader. The frozen source task is not edited.

Built-in test runners are **pytest**, **Jest**, and a legacy **command** runner.
Coverage readers are **Coverage.py JSON** and **Istanbul JSON**. Other languages
and frameworks require adapters; they are not automatically supported.

## Structure

- `config.py`, `models.py`: validated project profiles and adapter contracts.
- `orchestrator.py`, `workspace.py`: candidate/test-layer preparation and execution.
- `attribution.py`: case ownership from baseline IDs and changed source spans.
- `runners/`: framework-specific discovery, locations and exact selection.
- `readers/`: coverage formats, independent of the test framework.
- `metrics.py`, `reporting.py`: line unions, source comparison and reports.
- `integrations/harbor.py`: CLI boundary. `runner.py` retains the existing entry point.
- `profiles/saleor.yaml`: Saleor paths, suites, hooks and replay image.

One repository can have multiple suites and runners. Repository and suite names
are configuration values; the core contains no Saleor paths or suite names.

## Build and run with Harbor

```bash
python3 -m coverage_eval.package \
  --task tasks/standard \
  --profile coverage_eval/profiles/saleor.yaml \
  --output jobs/coverage-task

harbor run --agent <agent-name> --path jobs/coverage-task \
  --n-concurrent 1 --jobs-dir jobs/coverage-harbor-run
```

`--task` and `--profile` default to the existing standard task and Saleor profile.
The packager keeps the source task's image, Dockerfiles, verifier collection
hooks and assets, saves `tests/test.original.sh`, and installs the coverage entry
point. Local `environment/repos/` checkouts are excluded. The source task must
already collect the configured model patches and supply runner dependencies.
If its grading logic should continue to run, configure `grader` explicitly.
The generated task modifies its name, metadata status and optional verifier
timeout. Output directories must be fresh.

YAML profiles require PyYAML **on the packaging host**. JSON profiles have the
same schema and use only the standard library. Packaging compiles either format
to `/tests/coverage-profile.json`, so the verifier needs no YAML dependency.
The current code and packager require Python 3.11 or newer.

For existing base-relative model patches:

```bash
docker build -t sdlcbench/saleor-3.23-test:coverage-local jobs/coverage-task/tests
python3 -m coverage_eval.replay \
  --profile coverage_eval/profiles/saleor.yaml \
  --patches /path/to/model-patches \
  --output jobs/coverage-replay --candidate-kind reference
```

Replay reads repository names, patch filenames, image and Docker arguments from
the profile. `--image` can override the image. The test image must contain the
new evaluator; rebuild an older coverage image before replaying. Replay disables
networking. Saleor's local host entry and shared-memory setting live in its
profile rather than the generic replay code.

Candidate kinds are `agent` (default), `reference`, and `synthetic`. Harbor
packaged tasks also accept `COVERAGE_CANDIDATE_KIND` in the verifier environment.
Use the appropriate kind when evaluating reference patches or hand-written
smoke fixtures; the evaluator cannot infer who authored a patch.

## Configure another project

Start from `profiles/python-library.example.yaml`. Set the repository location,
base commit, source filters and test suites. A profile contains:

| Field | Meaning |
| --- | --- |
| `schema_version`, `project_id` | Profile version (1) and project identity |
| `repositories` | Arbitrary repository names, workspace paths and suites |
| `base_manifest` | Optional manifest supplying `repos.<name>.sha_base` and official Test Patch metadata |
| `prepare`, `services`, `grader` | Optional argv arrays for project environment/support preparation, service startup and scoring |
| `test_image`, `docker_args` | Optional direct Docker replay settings |
| `verifier_timeout_sec` | Optional Harbor verifier timeout override |

Each repository supports `name`, `path`, `base_commit`, `model_patch`,
`test_patch`, `test_patch_sha256`, `source_include` (required), `source_exclude`,
`test_include`, `test_support_include`, and `suites`.

Repository paths are relative to the workspace or absolute. They must not
intersect. `model_patch` defaults to `<name>.model.patch` under the artifacts
directory. Explicit relative `test_patch` paths resolve against the tests
directory. Test Patch paths supplied by the standard manifest resolve against
the parent of the tests directory, as in the existing task image.

Suite fields include:

| Field | Meaning |
| --- | --- |
| `name`, `runner`, `coverage_reader` | Globally unique suite name and registered adapters |
| `test_include`, `test_exclude` | Test files belonging to this suite |
| `source_include`, `source_exclude` | Optional additional filtering inside repository source scope |
| `command` | Runner executable argv override; defaults to pytest or local Jest |
| `args`, `discovery_args`, `baseline_args` | Runner arguments for execution, discovery and additional baseline discovery settings |
| `working_directory`, `env` | Repository-relative working directory and environment overrides |
| `coverage_sources` | Required pytest-cov source packages/directories, relative to the working directory |
| `baseline_unset_env` | Environment keys removed during baseline discovery |
| `result_directory` | Optional legacy command output directory moved to the suite output location |

Glob paths are repository-relative POSIX paths: `*` matches within one segment,
`**` matches zero or more segments. For example, `**/test_*.py` also matches a
test at the repository root. Repository test recognition uses `test_include`,
or the union of suite includes if omitted. List fixtures, conftest files and
other support files under `test_support_include`. Source exclusions should
cover generated code and any directories outside the intended measurement.

Commands and environment values support `{workspace}`, `{tests}`, `{artifacts}`,
`{verifier}`, `{repo}`, `{output}`, and `{suite}`. `{output}` is the suite output
for runner commands, and the verifier output for global hooks. Commands execute
as argv arrays without an implicit shell; escape literal braces as `{{` / `}}`.
Unknown fields, adapters, placeholders and escaping relative paths are rejected.

Without a `prepare` hook, the evaluator resets the disposable repositories to
the base, applies candidate patches, restores paths touched by the optional
official Test Patch, and applies that patch with Git. Tasks needing split-hunk
adaptation or other project logic supply their own `prepare` command. That hook
must deterministically prepare candidate code plus the official test/support
layer for both runs. `services` runs once before official tests; each suite must
provide its usual test isolation. The grader runs after official suites, before
Agent preparation.

The evaluator **resets and applies patches in the supplied workspace**. Use
Harbor's separate verifier container or disposable local clones. Local use:

```bash
python3 -m coverage_eval.runner --profile /path/to/profile.json \
  --workspace /path/to/disposable-repos --tests /path/to/test-assets \
  --artifacts /path/to/model-patches --output /path/to/fresh-results
```

## Reports and ownership

`coverage/coverage.json` uses report schema version 2. It records candidate kind,
profile/patch hashes, base commits, suite exit codes, grader results, exact Agent
selection and separate coverage per suite and per repository. Repository totals
union the lines from its suites, without double counting. Original raw reports,
logs and `coverage/agent/selection.json` remain available for inspection.

The official group contains base tests plus the optional official Test Patch.
The Agent group restores candidate test/support files saved before that layer
was applied. A case is selected if its ID is new against the base, or its source
body/decorators overlap candidate patch lines. Renames are considered separately.
Changes to shared helpers/fixtures are recorded as support changes; they do not
make all dependent cases Agent-authored. Duplicate Jest names or unresolved
source spans are uncertain and are not silently attributed. Jest inventory
collection executes tests, and the report records this; discovery executions
are excluded from coverage measurement.

`official_status` / `agent_status` distinguish `measured`, `no_tests`,
`unsupported`, and failures. A group without tests has null metrics. A measured
suite covering no executable source lines has a null percentage; a measured
suite with executable lines and no hits has 0%. Failed tests can still produce
coverage and make the run partial. Missing coverage makes the run an error.
Uncertain attribution, unsupported Agent test files, and production source
changes during tests are recorded explicitly. An empty configured official
suite makes the run partial. Successful legacy command suites can coexist with
complete unit coverage even though their own code coverage is unsupported.

The common metric is line coverage. Python uses exact Coverage.py executable
statements; Istanbul uses statement-start lines. Branch percentages are not
normalized across languages. The denominator consists of reported executable
lines inside the configured scope; files absent from instrumentation are listed
as `unreported_source_files` rather than assigned invented executable lines.
Fixture/module initialization can contribute coverage.

Groups are compared only for identical production source hashes. Comparable
files use the union of executable lines in both reports. Changed-line coverage
intersects those executable lines with candidate diff lines; deleted lines do
not enter the denominator. `agent_only_covered_lines` measures incremental
coverage over official tests.

Saleor official E2E suites still run for its original score through the command
adapter. E2E **code coverage** and Agent case selection remain unsupported.

## Add a framework or format

Implement `Runner` from `models.py` and register its class in `registry.RUNNERS`.
It supplies capabilities, `discover(Context, files, baseline=...)`, and
`run(Context, cases)`. An optional `validate(Suite)` method checks runner-specific
configuration before workspace preparation. `cases=None` runs the scoped official suite; an empty list
runs no Agent cases. Discovery emits repository-relative paths, stable case IDs,
selectors and inclusive source spans. A runner declares any inability to discover
or select cases, so the core reports unsupported Agent test files.

Implement `CoverageReader.read(report, Context)` and register it in
`registry.READERS`. Return `{relative_path: (executable_line_set, covered_line_set)}`
filtered by the configured source scope. Multiple runners may use one reader.
Use `Run.report` to identify the raw report artifact. All source comparison and
coverage calculations remain in the core.

## Verification

```bash
python3 -m unittest discover -s coverage_eval/tests -v
```

Real adapter tests additionally require pytest-cov and, for Jest,
`COVERAGE_JEST_NODE_MODULES=/path/to/node_modules` containing Jest and TypeScript.
They create unrelated Python/JavaScript repositories with nested layouts and
verify two groups, multiple suites, incremental coverage and absent Agent tests.
Set `COVERAGE_INTEGRATION_ARTIFACTS` to preserve their reports.

For sealed workflow snapshots, `snapshot_to_patch` still supports the existing
`--archive`, `--snapshot-manifest`, `--base-root`, and `--patch-manifest` interface.
Its manifest can list other repositories. Saleor reference `*.code.patch` files
are split code layers: export base-relative model patches through the task's
collection hook before replaying them.
