"""Construct C or D from the immutable base + E agent baseline."""

import argparse
import json
from pathlib import Path
import subprocess

from apply_patches import apply_layer


def run(*args: str) -> None:
    subprocess.run(args, check=True)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("phase", choices=["pre", "post"])
args = parser.parse_args()

package = Path("/")
manifest = json.loads(Path("/tests/patch_manifest.json").read_text())
for name, meta in manifest["repos"].items():
    repo = Path("/workspace") / name
    baseline = meta["agent_baseline_commit"]
    actual_commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", baseline], text=True
    ).strip()
    actual_tree = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", f"{baseline}^{{tree}}"], text=True
    ).strip()
    if actual_commit != baseline or actual_tree != meta["agent_baseline_tree"]:
        raise RuntimeError(f"{name}: image agent baseline does not match patch manifest")
    run("git", "-C", str(repo), "reset", "--hard", baseline)
    run("git", "-C", str(repo), "clean", "-fd")
    if args.phase == "post":
        run(
            "git", "-C", str(repo), "apply", "--index",
            "--whitespace=nowarn", "--allow-empty",
            f"/logs/artifacts/{name}.model.patch",
        )
    apply_layer(repo, package, meta, "test")
