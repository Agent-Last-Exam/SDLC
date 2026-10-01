"""Convert a sealed workflow repos.tar into the standard two model patches.

Requires clean local base checkouts at the exact commits in patch_manifest.json.
"""

import argparse
import filecmp
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or path.parts[:1] != ("repos",):
        raise ValueError(f"unsafe archive member: {name}")
    return path


def extract(archive, destination):
    with tarfile.open(archive) as handle:
        for member in handle:
            relative = safe_name(member.name)
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with handle.extractfile(member) as source, target.open("wb") as sink:
                    shutil.copyfileobj(source, sink)
                target.chmod(member.mode & 0o777)
            elif member.issym():
                target.parent.mkdir(parents=True, exist_ok=True)
                resolved = (target.parent / member.linkname).resolve()
                if not resolved.is_relative_to(destination / "repos"):
                    raise ValueError(f"escaping symlink: {member.name}")
                target.symlink_to(member.linkname)
            else:
                raise ValueError(f"unsupported archive member: {member.name}")


def validate(snapshot, manifest):
    files = manifest["files"]
    actual = {str(path.relative_to(snapshot)) for path in snapshot.rglob("*")}
    if actual != set(files):
        raise ValueError("snapshot contents differ from sealed manifest")
    for relative, expected in files.items():
        path = snapshot / relative
        if "directory" in expected:
            if not path.is_dir():
                raise ValueError(f"missing directory: {relative}")
        elif "link" in expected:
            if not path.is_symlink() or os.readlink(path) != expected["link"]:
                raise ValueError(f"symlink mismatch: {relative}")
        elif (path.is_symlink() or not path.is_file()
              or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]
              or bool(path.stat().st_mode & 0o111) != expected["executable"]):
            raise ValueError(f"content mismatch: {relative}")
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    if digest != manifest["sha256"]:
        raise ValueError("snapshot manifest digest mismatch")


def materialize(base, candidate, repo, base_sha, output):
    if git(base, "rev-parse", "HEAD") != base_sha:
        raise ValueError(f"wrong base commit: {base}")
    if git(base, "status", "--porcelain"):
        raise ValueError(f"base checkout is dirty: {base}")
    repo.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(base, repo, symlinks=True)
    if git(repo, "rev-parse", "HEAD") != base_sha:
        raise ValueError(f"copied checkout has wrong base commit: {repo}")
    tracked = set(git(repo, "ls-files").splitlines())
    incoming = {str(path.relative_to(candidate)) for path in candidate.rglob("*")
                if path.is_file() or path.is_symlink()}
    if any(".git" in PurePosixPath(path).parts for path in incoming):
        raise ValueError("snapshot cannot contain Git metadata")
    for relative in tracked - incoming:
        (repo / relative).unlink(missing_ok=True)
    for relative in incoming:
        source = candidate / relative
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink() and target.is_symlink() and os.readlink(source) == os.readlink(target):
            continue
        if (source.is_file() and not source.is_symlink() and target.is_file()
            and not target.is_symlink() and filecmp.cmp(source, target, shallow=False)
            and (source.stat().st_mode & 0o111) == (target.stat().st_mode & 0o111)):
            continue
        if target.is_symlink() or target.is_file():
            target.unlink()
        if source.is_symlink():
            target.symlink_to(os.readlink(source))
        else:
            shutil.copy2(source, target)
    # Match the standard task's verifier.collect behavior. Ignored generated
    # files in a workflow snapshot are deliberately absent from model.patch.
    git(repo, "add", "-N", ".")
    with output.open("wb") as stream:
        subprocess.run(["git", "-C", str(repo), "diff", "--binary", "--full-index",
                        base_sha], stdout=stream, check=True)


def convert(archive, snapshot_manifest, base_root, patch_manifest, output):
    output.mkdir(parents=True, exist_ok=True)
    specification = json.loads(patch_manifest.read_text())
    sealed = json.loads(snapshot_manifest.read_text())
    with tempfile.TemporaryDirectory(prefix="coverage-snapshot-") as temporary:
        root = Path(temporary)
        extract(archive, root)
        validate(root / "repos", sealed)
        for name, metadata in specification["repos"].items():
            materialize(base_root / name, root / "repos" / name,
                        root / "checkouts" / name, metadata["sha_base"],
                        output / f"{name}.model.patch")
    provenance = {"archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                  "manifest_sha256": sealed["sha256"],
                  "patches": {name: hashlib.sha256((output / f"{name}.model.patch").read_bytes()).hexdigest()
                              for name in specification["repos"]}}
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--patch-manifest", type=Path,
                        default=Path(__file__).resolve().parents[1] /
                        "tasks/standard/tests/patch_manifest.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    convert(args.archive, args.snapshot_manifest, args.base_root,
            args.patch_manifest, args.output)


if __name__ == "__main__":
    main()
