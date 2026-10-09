#!/usr/bin/env python3
"""Sandbox-side snapshot and controlled integration helpers for team candidates."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys


def snapshot(root, *, allow_internal_symlinks=False):
    root = Path(root)
    files = {}
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"candidate root is not a regular directory: {root}")
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        relative = str(path.relative_to(root))
        if stat.S_ISDIR(info.st_mode):
            continue
        if stat.S_ISLNK(info.st_mode):
            if not allow_internal_symlinks:
                raise ValueError(f"candidate contains a link or nonregular file: {relative}")
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"candidate symlink escapes repositories: {relative}")
            files[relative] = "symlink:" + os.readlink(path)
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(f"candidate contains a link or nonregular file: {relative}")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def changed(before, after):
    result = {}
    for path in sorted(set(before) | set(after)):
        if before.get(path) != after.get(path):
            result[path] = after.get(path, "deleted")
    return result


def integrate(shared, candidate, before, changes):
    """Apply scoped candidate files iff their shared Base bytes are unchanged."""
    shared, candidate = Path(shared), Path(candidate)
    current = snapshot(shared, allow_internal_symlinks=True)
    conflicts = [path for path in changes if current.get(path) != before.get(path)]
    if conflicts:
        raise ValueError("repository integration conflict: " + ", ".join(conflicts))
    for path, digest in changes.items():
        target = shared / path
        if not target.resolve(strict=False).is_relative_to(shared.resolve()):
            raise ValueError(f"integration path escapes repositories: {path}")
        if digest == "deleted":
            if target.exists() or target.is_symlink():
                if not target.is_file() or target.is_symlink():
                    if not target.is_symlink():
                        raise ValueError(f"cannot delete nonregular repository path: {path}")
                target.unlink()
            continue
        source = candidate / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if digest.startswith("symlink:"):
            expected = digest.removeprefix("symlink:")
            if not source.is_symlink() or os.readlink(source) != expected:
                raise ValueError(f"candidate symlink changed after sealing: {path}")
            if target.exists() or target.is_symlink():
                if target.is_dir() and not target.is_symlink():
                    raise ValueError(f"cannot replace repository directory: {path}")
                target.unlink()
            target.symlink_to(expected)
            continue
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"candidate file is missing: {path}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError(f"candidate file changed after sealing: {path}")
        temporary = target.with_name(target.name + ".sdlc-team-tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, target)


def main():
    command = sys.argv[1]
    if command in {"snapshot", "snapshot-repos"} and len(sys.argv) == 3:
        print(json.dumps(snapshot(
            sys.argv[2], allow_internal_symlinks=command == "snapshot-repos"
        ), sort_keys=True))
        return
    if command == "diff" and len(sys.argv) == 4:
        before = json.loads(Path(sys.argv[2]).read_text())
        print(json.dumps(changed(
            before, snapshot(sys.argv[3], allow_internal_symlinks=True)
        ), sort_keys=True))
        return
    if command == "integrate" and len(sys.argv) == 6:
        before = json.loads(Path(sys.argv[4]).read_text())
        changes = json.loads(Path(sys.argv[5]).read_text())
        integrate(sys.argv[2], sys.argv[3], before, changes)
        return
    raise SystemExit("usage: team_workspace.py snapshot ROOT | snapshot-repos ROOT | diff BEFORE ROOT | integrate SHARED CANDIDATE BEFORE CHANGES")


if __name__ == "__main__":
    main()
