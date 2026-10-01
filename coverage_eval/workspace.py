"""Candidate/test-layer preparation in the disposable verifier workspace."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import subprocess

from coverage_eval.utils import command, expand, git, matches, variables


def resolve_repositories(profile, paths):
    manifest = {}
    if profile.base_manifest:
        path = Path(profile.base_manifest)
        if not path.is_absolute():
            path = paths.tests / path
        manifest = json.loads(path.read_text())["repos"]
    repositories = []
    for repo in profile.repositories:
        metadata = manifest.get(repo.name, {})
        base = repo.base_commit or metadata.get("sha_base")
        if not base:
            raise ValueError(f"{repo.name}: missing base commit")
        test = metadata.get("test_patch", {})
        test_path = repo.test_patch
        if test_path:
            test_path = str(Path(test_path) if Path(test_path).is_absolute() else paths.tests / test_path)
        elif test.get("path"):
            # Standard manifest paths are relative to the task image root.
            test_path = str(paths.tests.parent / test["path"])
        repositories.append(replace(repo, base_commit=base, test_patch=test_path,
                                    test_patch_sha256=repo.test_patch_sha256 or
                                    (test.get("sha256") if not repo.test_patch else None)))
    roots = [repo_path(repo, paths).resolve() for repo in repositories]
    for index, root in enumerate(roots):
        if any(root == other or root.is_relative_to(other) or other.is_relative_to(root)
               for other in roots[index + 1:]):
            raise ValueError("repository workspace paths must not overlap")
    return tuple(repositories)


def repo_path(repo, paths):
    path = Path(repo.path)
    return path if path.is_absolute() else paths.workspace / path


def patch_paths(patch):
    output = subprocess.check_output(["git", "apply", "--numstat", "-z", str(patch)], text=True)
    return {row.split("\t", 2)[2] for row in output.split("\0") if row}


def test_file(repo, path):
    patterns = repo.test_include or tuple(pattern for suite in repo.suites for pattern in suite.test_include)
    return matches(path, patterns)


def test_support(repo, path):
    return test_file(repo, path) or matches(path, repo.test_support_include)


def source_file(repo, path, suite=None):
    if not matches(path, repo.source_include, repo.source_exclude) or test_support(repo, path):
        return False
    return suite is None or matches(path, suite.source_include, suite.source_exclude)


def source_inventory(repositories, paths):
    result = {}
    for repo in repositories:
        root = repo_path(repo, paths)
        files = {}
        candidates = {path for pattern in repo.source_include for path in root.glob(pattern)}
        for path in candidates:
            relative = path.relative_to(root).as_posix()
            if ".git" in path.relative_to(root).parts or path.is_symlink() or not path.is_file():
                continue
            if source_file(repo, relative):
                files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        result[repo.name] = files
    return result


def changed_lines(repo, base):
    diff = git(repo, "-c", "core.quotePath=false", "diff", "--no-ext-diff", "--unified=0", base)
    result, current = {}, None
    for row in diff.splitlines():
        if row.startswith("+++ b/"):
            current = row[6:]
            result.setdefault(current, set())
        elif row.startswith("+++ /dev/null"):
            current = None
        elif current and row.startswith("@@ "):
            match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", row)
            if match:
                start = int(match[1])
                count = int(match[2]) if match[2] is not None else 1
                result[current].update(range(start, start + count))
    return result


def renamed_test_files(repo, base):
    names = git(repo, "-c", "core.quotePath=false", "diff", "--name-status", "--find-renames", base)
    return {parts[2] for row in names.splitlines() if (parts := row.split("\t"))
            and parts[0].startswith("R") and len(parts) == 3}


def verify_inputs(repositories, paths):
    for repo in repositories:
        if git(repo_path(repo, paths), "rev-parse", "HEAD").strip() != repo.base_commit:
            raise ValueError(f"{repo.name}: wrong base commit")
        if not (paths.artifacts / repo.model_patch).is_file():
            raise ValueError(f"{repo.name}: missing model patch {repo.model_patch}")
        if repo.test_patch:
            digest = hashlib.sha256(Path(repo.test_patch).read_bytes()).hexdigest()
            if repo.test_patch_sha256 and digest != repo.test_patch_sha256:
                raise ValueError(f"{repo.name}: official test patch hash mismatch")


def reset(repositories, paths):
    for repo in repositories:
        git(repo_path(repo, paths), "reset", "--hard", repo.base_commit)


def candidate_workspace(repositories, paths):
    reset(repositories, paths)
    for repo in repositories:
        git(repo_path(repo, paths), "apply", "--index", "--whitespace=nowarn", "--allow-empty",
            str(paths.artifacts / repo.model_patch))


def hook(argv, paths, label):
    if not argv:
        return None
    code = command(expand(argv, variables(paths)), cwd=paths.workspace,
                   log=paths.output / "coverage" / "hooks" / f"{label}.log")
    if code:
        raise RuntimeError(f"{label} hook failed with exit code {code}")
    return code


def prepare(profile, repositories, paths, label):
    if profile.prepare:
        hook(profile.prepare, paths, label)
    else:
        candidate_workspace(repositories, paths)
        for repo in repositories:
            if not repo.test_patch:
                continue
            root = repo_path(repo, paths)
            base = set(git(root, "ls-tree", "-r", "--name-only", repo.base_commit).splitlines())
            for path in patch_paths(repo.test_patch):
                if path in base:
                    git(root, "restore", "--source=" + repo.base_commit, "--staged", "--worktree", "--", path)
                else:
                    git(root, "rm", "--force", "--ignore-unmatch", "--", path)
            git(root, "apply", "--index", "--whitespace=nowarn", "--allow-empty", repo.test_patch)
    # Remove candidate-only test/support modifications from the official group.
    for repo in repositories:
        root = repo_path(repo, paths)
        official = patch_paths(repo.test_patch) if repo.test_patch else set()
        base = set(git(root, "ls-tree", "-r", "--name-only", repo.base_commit).splitlines())
        for path in patch_paths(paths.artifacts / repo.model_patch) - official:
            if test_support(repo, path):
                if path in base:
                    git(root, "restore", "--source=" + repo.base_commit, "--staged", "--worktree", "--", path)
                else:
                    git(root, "rm", "--force", "--ignore-unmatch", "--", path)


def snapshot_tests(repositories, paths):
    snapshots = {}
    for repo in repositories:
        root = repo_path(repo, paths)
        files = {}
        # --no-renames includes both old and new paths, so a renamed/deleted
        # candidate test is restored exactly rather than keeping its base copy.
        for relative in git(root, "-c", "core.quotePath=false", "diff", "--name-only",
                            "--no-renames", repo.base_commit).splitlines():
            if not test_support(repo, relative):
                continue
            path = root / relative
            if path.is_symlink():
                raise ValueError(f"test symlink needs attribution: {repo.name}/{relative}")
            files[relative] = (path.read_bytes(), path.stat().st_mode & 0o777) if path.is_file() else None
        snapshots[repo.name] = files
    return snapshots


def restore_tests(snapshots, repositories, paths):
    for repo in repositories:
        root = repo_path(repo, paths)
        for relative, content in snapshots[repo.name].items():
            path = root / relative
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content[0])
                path.chmod(content[1])
