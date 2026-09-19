#!/usr/bin/env python3
"""Fetch exactly one Base commit per repo; never copy modified working trees."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parents[1]
ENV = HERE / "tasks/saleor-prd-tdd/environment"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, help="Optional local Git repos, each under its repo name")
    args = parser.parse_args()
    specs = json.loads((ENV / "base-revisions.json").read_text())
    destination = ENV / "repos"
    destination.mkdir(exist_ok=True)
    for name, spec in specs.items():
        target = destination / name
        if target.exists():
            assert git(target, "rev-parse", "HEAD") == spec["commit"], f"Wrong SHA: {target}"
            assert git(target, "rev-list", "--count", "HEAD") == "1", f"Unexpected history: {target}"
            assert not git(target, "status", "--porcelain"), f"Dirty repo: {target}"
            assert not git(target, "remote"), f"Unexpected remote: {target}"
            print(f"Verified {name}: {spec['commit']}", flush=True)
            continue
        source = str((args.source_root / name).resolve()) if args.source_root else spec["url"]
        with tempfile.TemporaryDirectory(prefix=f".{name}-", dir=destination) as tmp:
            repo = Path(tmp) / name
            repo.mkdir()
            git(repo, "init", "--quiet")
            git(repo, "fetch", "--quiet", "--depth=1", "--no-tags", source, spec["commit"])
            git(repo, "checkout", "--quiet", "--detach", "FETCH_HEAD")
            assert git(repo, "rev-parse", "HEAD") == spec["commit"]
            assert git(repo, "rev-list", "--count", "HEAD") == "1"
            # FETCH_HEAD can contain a local host path; it is not needed at runtime.
            (repo / ".git/FETCH_HEAD").unlink(missing_ok=True)
            shutil.move(str(repo), target)
        print(f"Prepared {name}: {spec['commit']}", flush=True)


if __name__ == "__main__":
    main()
