"""Paths, glob matching and process execution, without project assumptions."""

from fnmatch import fnmatchcase
from functools import lru_cache
import json
import os
from pathlib import Path
import subprocess


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True)


@lru_cache(maxsize=4096)
def glob_matches(path, pattern):
    """POSIX globs: * stays in one segment, ** spans zero or more segments."""
    segments, patterns = path.split("/"), pattern.split("/")

    def match(i, j):
        if j == len(patterns):
            return i == len(segments)
        if patterns[j] == "**":
            return match(i, j + 1) or (i < len(segments) and match(i + 1, j))
        return i < len(segments) and fnmatchcase(segments[i], patterns[j]) and match(i + 1, j + 1)

    return match(0, 0)


def matches(path, include, exclude=()):
    return any(glob_matches(path, pattern) for pattern in include) and not any(
        glob_matches(path, pattern) for pattern in exclude)


def variables(paths, *, repo=None, output=None, suite=None):
    return {"workspace": str(paths.workspace), "tests": str(paths.tests),
            "artifacts": str(paths.artifacts), "verifier": str(paths.output),
            "repo": str(repo or paths.workspace), "output": str(output or paths.output),
            "suite": suite or ""}


def expand(argv, values):
    return [arg.format_map(values) for arg in argv]


def command(args, *, cwd, log, env=None):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as stream:
        return subprocess.run(args, cwd=cwd, env=env, stdout=stream,
                              stderr=subprocess.STDOUT, check=False).returncode


def environment(context, *, baseline=False):
    env = os.environ.copy()
    values = variables(context.paths, repo=context.repo, output=context.output, suite=context.suite.name)
    env.update({key: value.format_map(values) for key, value in context.suite.env.items()})
    if baseline:
        for key in context.suite.baseline_unset_env:
            env.pop(key, None)
    # The adapter package can be imported from a task image or local checkout.
    package_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = package_root + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("COVERAGE_SELECTED_NODEIDS", None)
    env.pop("COVERAGE_PYTEST_INVENTORY", None)
    return env


def suite_test_files(context):
    candidates = {path for pattern in context.suite.test_include for path in context.repo.glob(pattern)}
    return sorted(path for path in candidates if path.is_file() and not path.is_symlink()
                  and matches(path.relative_to(context.repo).as_posix(),
                              context.suite.test_include, context.suite.test_exclude))
