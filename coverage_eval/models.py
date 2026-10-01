"""Small data contracts shared by the evaluator and its adapters."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


LineMap = dict[str, tuple[set[int], set[int]]]


@dataclass(frozen=True)
class Suite:
    name: str
    runner: str
    coverage_reader: str | None
    test_include: tuple[str, ...]
    test_exclude: tuple[str, ...] = ()
    source_include: tuple[str, ...] = ("**/*",)
    source_exclude: tuple[str, ...] = ()
    command: tuple[str, ...] = ()
    args: tuple[str, ...] = ()
    discovery_args: tuple[str, ...] = ()
    baseline_args: tuple[str, ...] = ()
    coverage_sources: tuple[str, ...] = ()
    working_directory: str = "."
    env: dict[str, str] = field(default_factory=dict)
    baseline_unset_env: tuple[str, ...] = ()
    result_directory: str | None = None


@dataclass(frozen=True)
class Repository:
    name: str
    path: str
    suites: tuple[Suite, ...]
    base_commit: str | None = None
    model_patch: str = ""
    test_patch: str | None = None
    test_patch_sha256: str | None = None
    source_include: tuple[str, ...] = ("**/*",)
    source_exclude: tuple[str, ...] = ()
    test_include: tuple[str, ...] = ()
    test_support_include: tuple[str, ...] = ()


@dataclass(frozen=True)
class Profile:
    project_id: str
    repositories: tuple[Repository, ...]
    base_manifest: str | None = None
    prepare: tuple[str, ...] = ()
    services: tuple[str, ...] = ()
    grader: tuple[str, ...] = ()
    test_image: str | None = None
    docker_args: tuple[str, ...] = ()
    verifier_timeout_sec: int | None = None


@dataclass(frozen=True)
class Paths:
    workspace: Path = Path("/workspace")
    tests: Path = Path("/tests")
    artifacts: Path = Path("/logs/artifacts")
    output: Path = Path("/logs/verifier")


@dataclass(frozen=True)
class Capabilities:
    discover: bool = True
    select_cases: bool = True
    source_locations: bool = True
    coverage: bool = True


@dataclass(frozen=True)
class TestCase:
    id: str
    path: str
    selector: str
    start: int | None = None
    end: int | None = None
    uncertainty: str | None = None


@dataclass
class Discovery:
    cases: list[TestCase]
    exit_code: int = 0
    executed_tests: bool = False


@dataclass
class Run:
    exit_code: int | None
    status: str = "measured"
    report: Path | None = None


@dataclass(frozen=True)
class Context:
    repository: Repository
    suite: Suite
    repo: Path
    output: Path
    paths: Paths

    @property
    def cwd(self):
        return self.repo / self.suite.working_directory


class Runner(Protocol):
    capabilities: Capabilities

    def discover(self, context: Context, files: list[str], *, baseline: bool) -> Discovery: ...

    # None means the full suite; [] means no selected cases.
    def run(self, context: Context, cases: list[TestCase] | None) -> Run: ...


class CoverageReader(Protocol):
    def read(self, report: Path, context: Context) -> LineMap: ...
