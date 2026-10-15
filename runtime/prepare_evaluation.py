"""Build a separate Saleor evaluation task without changing its frozen source."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tomllib

HERE = Path(__file__).resolve().parents[1]
SUITES = {
    "core-unit": ("saleor.core-unit.", "results.xml"),
    "core-e2e": ("saleor.core-e2e.", "results.xml"),
    "dash-unit": ("saleor-dashboard.dash-unit.", "results.json"),
    "dash-e2e": ("saleor-dashboard.dash-e2e.", "results.json"),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def build(profile_path, output):
    profile_path, output = Path(profile_path).resolve(), Path(output).resolve()
    profile = json.loads(profile_path.read_text())
    if profile.get("schema_version") != 1:
        raise ValueError("Unsupported evaluation profile")
    # This adapter deliberately supports the three-suite Saleor variant only.
    if profile.get("suites") != ["core-unit", "core-e2e", "dash-unit"]:
        raise ValueError("Expected core-unit, core-e2e and dash-unit suites")
    identity = profile["profile_id"]
    if identity != "saleor-3.23-pruned-no-browser":
        raise ValueError("Unsupported profile identity")
    source = (HERE / profile["source_task"]).resolve()
    if output.exists():
        raise ValueError("Output must be a fresh directory")
    if output == source or source in output.parents or output in source.parents:
        raise ValueError("Output must be separate from the source task")
    source_config = json.loads((source / "tests/config.json").read_text())
    if source_config.get("status") != "frozen":
        raise ValueError("Source scoring selection must be frozen")
    prefixes = tuple(SUITES[s][0] for s in profile["suites"])
    config = dict(source_config)
    for key in ("f2p_node_ids", "p2p_node_ids"):
        ids = source_config[key]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate source IDs in {key}")
        if any(not i.startswith(tuple(v[0] for v in SUITES.values())) for i in ids):
            raise ValueError(f"Unknown test suite in {key}")
        config[key] = [i for i in ids if i.startswith(prefixes)]
    counts = {"f2p": len(config["f2p_node_ids"]), "p2p": len(config["p2p_node_ids"])}
    if counts != profile["expected_counts"]:
        raise ValueError(f"Source selection changed: {counts}")
    config["task_id"] = identity
    config["selection"] = {
        "artifact": "evaluation-profile.json",
        "counts": counts,
        "source_config_sha256": sha(source / "tests/config.json"),
        "source_selection": source_config.get("selection", {}),
        "excluded_suite": "dash-e2e",
        "same_code_and_test_patches": True,
    }
    config["grade"] = dict(source_config.get("grade", {}))
    config["grade"]["tool_label"] = identity
    for phase in ("pre", "post"):
        config["grade"][f"{phase}_reports"] = [
            f"/logs/verifier/{phase}/{suite}/{SUITES[suite][1]}"
            for suite in profile["suites"]
        ]
    runner = (source / "tests/test.sh").read_text()
    old = "run_phase {phase} core-unit core-e2e dash-unit dash-e2e"
    for phase in ("pre", "post"):
        expected = old.format(phase=phase)
        if runner.count(expected) != 1:
            raise ValueError("Source test entry point changed; review the adapter")
        runner = runner.replace(expected, f"run_phase {phase} core-unit core-e2e dash-unit")
    grader = (source / "tests/grader.py").read_text()
    old_reward = '    (VERIFIER_DIR / "reward.json").write_text(json.dumps(result, indent=2) + "\\n")'
    if grader.count(old_reward) != 1:
        raise ValueError("Source reward writer changed; review the adapter")
    grader = grader.replace(old_reward, '\n'.join([
        '    (VERIFIER_DIR / "reward-details.json").write_text(json.dumps(result, indent=2) + "\\n")',
        '    (VERIFIER_DIR / "reward.json").write_text(json.dumps({"reward": reward}, indent=2) + "\\n")',
    ]))
    task_text = (source / "task.toml").read_text()
    task = tomllib.loads(task_text)
    replacements = {
        f'name = "{task["task"]["name"]}"': f'name = "sdlcbench/{identity}"',
        f'task_id = "{task["metadata"]["task_id"]}"': f'task_id = "{identity}"',
        f'release_id = "{task["metadata"]["release_id"]}"': f'release_id = "{identity}-local-profile-v1"',
        f'status = "{task["metadata"]["status"]}"': 'status = "derived-local-profile"',
    }
    for old_value, new_value in replacements.items():
        if task_text.count(old_value) != 1:
            raise ValueError("Source task metadata changed; review the adapter")
        task_text = task_text.replace(old_value, new_value)
    # Validate the generated TOML before creating anything.
    tomllib.loads(task_text)
    shutil.copytree(source, output, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    write_json(output / "tests/config.json", config)
    write_json(output / "evaluation-profile.json", profile)
    (output / "tests/test.sh").write_text(runner)
    (output / "tests/grader.py").write_text(grader)
    (output / "task.toml").write_text(task_text)
    solve = output / "solution/solve.sh"
    solve.write_text('''#!/usr/bin/env bash
set -euo pipefail
for repo in saleor saleor-dashboard; do
  git -C "/workspace/$repo" update-index --refresh
  git -C "/workspace/$repo" apply --index --whitespace=nowarn "/solution/$repo.code.patch"
done
''')
    solve.chmod(0o755)
    (output / "README.md").write_text(
        f"# {identity}\n\nDerived evaluation profile; excludes browser E2E from execution and scoring.\n"
        f"Frozen subset: F2P {counts['f2p']}, P2P {counts['p2p']}. Not the original full release.\n"
        "Code/test patches and environment are unchanged. reward.json contains only the numeric reward; "
        "reward-details.json preserves metrics and report paths. Full-profile Golden documentation "
        "copied from the source is reference material, not evidence of this profile's calibration.\n"
    )
    files = {
        str(p.relative_to(output)): sha(p)
        for p in sorted(output.rglob("*"))
        if p.is_file() and p != output / "manifest.json"
        and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    write_json(output / "manifest.json", {
        "schema": "sdlc-evaluation-profile-v1", "task_id": identity,
        "release_status": "derived-local-profile", "source_task": profile["source_task"],
        "source_manifest_sha256": sha(source / "manifest.json"),
        "profile_sha256": sha(profile_path), "counts": counts, "files": files,
    })
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=HERE / "tasks/evaluation-profiles/saleor-3.23-no-browser.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    counts = build(args.profile, args.output)
    print(f"Prepared {args.output}: F2P {counts['f2p']}, P2P {counts['p2p']}")


if __name__ == "__main__":
    main()
