"""Load explicit project profiles. JSON works without extra dependencies."""

from dataclasses import asdict, fields
import json
from pathlib import Path, PurePosixPath
from string import Formatter

from coverage_eval.models import Profile, Repository, Suite


DEFAULT_PROFILE = Path(__file__).with_name("profiles") / "saleor.yaml"


def _unknown(data, model, extra=()):
    if not isinstance(data, dict):
        raise ValueError(f"{model.__name__} must be an object")
    unknown = set(data) - {item.name for item in fields(model)} - set(extra)
    if unknown:
        raise ValueError(f"unknown {model.__name__} fields: {sorted(unknown)}")


def _strings(value, label):
    if not isinstance(value, (list, tuple)) or any(not isinstance(x, str) or not x for x in value):
        raise ValueError(f"{label} must be an array of nonempty strings")
    return tuple(value)


def _name(value, label):
    if not isinstance(value, str) or not value or value in (".", "..") or any(x not in
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for x in value):
        raise ValueError(f"invalid {label}: {value!r}")
    return value


def _path(value, label, *, absolute=False):
    if not isinstance(value, str) or not value or ".." in PurePosixPath(value).parts:
        raise ValueError(f"invalid {label}: {value!r}")
    if not absolute and PurePosixPath(value).is_absolute():
        raise ValueError(f"{label} must be relative")
    return value


def _patterns(value, label):
    patterns = _strings(value, label)
    for pattern in patterns:
        _path(pattern, label)
    return patterns


def _template(value):
    allowed = {"workspace", "tests", "artifacts", "verifier", "repo", "output", "suite"}
    try:
        for _, name, specification, conversion in Formatter().parse(value):
            if name is not None and (name not in allowed or specification or conversion):
                raise ValueError(f"unsupported command placeholder: {name!r}")
    except ValueError as exc:
        raise ValueError(f"invalid command template {value!r}: {exc}") from exc


def parse_profile(data):
    from coverage_eval.registry import READERS, RUNNERS

    _unknown(data, Profile, ("schema_version",))
    if data.get("schema_version") != 1:
        raise ValueError("profile schema_version must be 1")
    _name(data.get("project_id"), "project_id")
    repositories = []
    suite_names, repo_names, repo_paths = set(), set(), set()
    raw_repositories = data.get("repositories")
    if not isinstance(raw_repositories, list) or not raw_repositories:
        raise ValueError("repositories must be a nonempty array")
    for raw in raw_repositories:
        _unknown(raw, Repository)
        entry = dict(raw)
        name = _name(entry.get("name"), "repository name")
        path = _path(entry.get("path", name), "repository path", absolute=True)
        if name in repo_names or path in repo_paths:
            raise ValueError("repository names and paths must be unique")
        repo_names.add(name)
        repo_paths.add(path)
        entry["path"] = path
        entry["model_patch"] = _path(entry.get("model_patch") or f"{name}.model.patch", "model_patch")
        for key in ("test_patch", "base_commit", "test_patch_sha256"):
            if entry.get(key) is not None and (not isinstance(entry[key], str) or not entry[key]):
                raise ValueError(f"{key} must be a nonempty string")
        if entry.get("test_patch"):
            _path(entry["test_patch"], "test_patch", absolute=True)
        for key in ("source_include", "source_exclude", "test_include", "test_support_include"):
            if key in entry:
                entry[key] = _patterns(entry[key], key)
        if not entry.get("source_include"):
            raise ValueError(f"{name}: source_include is required")
        suites = []
        raw_suites = entry.get("suites")
        if not isinstance(raw_suites, list) or not raw_suites:
            raise ValueError(f"{name}: suites must be a nonempty array")
        for raw_suite in raw_suites:
            _unknown(raw_suite, Suite)
            suite = dict(raw_suite)
            suite_name = _name(suite.get("name"), "suite name")
            if suite_name in suite_names:
                raise ValueError("suite names must be unique across repositories")
            suite_names.add(suite_name)
            if suite.get("runner") not in RUNNERS:
                raise ValueError(f"unknown runner: {suite.get('runner')!r}")
            reader = suite.get("coverage_reader")
            if reader is not None and reader not in READERS:
                raise ValueError(f"unknown coverage reader: {reader!r}")
            suite["coverage_reader"] = reader
            adapter = RUNNERS[suite["runner"]]()
            if adapter.capabilities.coverage and reader is None:
                raise ValueError(f"{suite_name}: coverage_reader is required")
            if not adapter.capabilities.coverage and reader is not None:
                raise ValueError(f"{suite_name}: runner does not support code coverage")
            for key in ("test_include", "test_exclude", "source_include", "source_exclude"):
                if key in suite:
                    suite[key] = _patterns(suite[key], key)
            if not suite.get("test_include"):
                raise ValueError(f"{suite_name}: test_include is required")
            for key in ("command", "args", "discovery_args", "baseline_args", "coverage_sources", "baseline_unset_env"):
                if key in suite:
                    suite[key] = _strings(suite[key], key)
                    if key in ("command", "args", "discovery_args", "baseline_args"):
                        for value in suite[key]:
                            _template(value)
            suite["working_directory"] = _path(suite.get("working_directory", "."), "working_directory")
            env = suite.get("env", {})
            if not isinstance(env, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in env.items()):
                raise ValueError("env must map strings to strings")
            if suite.get("result_directory") is not None and not isinstance(suite["result_directory"], str):
                raise ValueError("result_directory must be a string")
            for value in env.values():
                _template(value)
            if suite.get("result_directory"):
                _template(suite["result_directory"])
            parsed_suite = Suite(**suite)
            validator = getattr(adapter, "validate", None)
            if validator:
                validator(parsed_suite)
            suites.append(parsed_suite)
        entry["suites"] = tuple(suites)
        repositories.append(Repository(**entry))
    entry = {key: value for key, value in data.items() if key != "schema_version"}
    entry["repositories"] = tuple(repositories)
    for key in ("prepare", "services", "grader", "docker_args"):
        if key in entry:
            entry[key] = _strings(entry[key], key)
            if key != "docker_args":
                for value in entry[key]:
                    _template(value)
    if entry.get("base_manifest") is not None:
        _path(entry["base_manifest"], "base_manifest", absolute=True)
    if not entry.get("base_manifest") and any(not repo.base_commit for repo in repositories):
        raise ValueError("each repository needs base_commit or a base_manifest")
    timeout = entry.get("verifier_timeout_sec")
    if timeout is not None and (type(timeout) is not int or timeout <= 0):
        raise ValueError("verifier_timeout_sec must be a positive integer")
    if entry.get("test_image") is not None and (not isinstance(entry["test_image"], str) or not entry["test_image"]):
        raise ValueError("test_image must be a nonempty string")
    return Profile(**entry)


def load_profile(path=DEFAULT_PROFILE):
    path = Path(path)
    if path.suffix == ".json":
        data = json.loads(path.read_text())
    else:
        try:
            import yaml
        except ImportError as exc:
            raise ValueError("YAML profiles require PyYAML; use JSON in minimal environments") from exc
        data = yaml.safe_load(path.read_text())
    return parse_profile(data)


def profile_dict(profile):
    return {"schema_version": 1, **asdict(profile)}
