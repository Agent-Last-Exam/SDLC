"""Build a separate coverage Harbor task from an existing task and profile."""

import argparse
import json
from pathlib import Path
import re
import shutil
import tomllib

from coverage_eval.config import DEFAULT_PROFILE, load_profile, profile_dict
from coverage_eval.utils import write_json


ROOT = Path(__file__).resolve().parents[1]
STANDARD = ROOT / "tasks/standard"


def _set_scalar(text, section, key, value):
    match = re.search(r"(?m)^\[" + re.escape(section) + r"\]\s*$", text)
    if not match:
        return text.rstrip() + f"\n\n[{section}]\n{key} = {value}\n"
    next_section = re.search(r"(?m)^\[", text[match.end():])
    end = match.end() + next_section.start() if next_section else len(text)
    block = text[match.end():end]
    assignment = re.compile(r"(?m)^" + re.escape(key) + r"\s*=.*$")
    block = assignment.sub(f"{key} = {value}", block) if assignment.search(block) else (
        block.rstrip() + f"\n{key} = {value}\n\n")
    return text[:match.end()] + block + text[end:]


def build(output: Path, *, task=STANDARD, profile=DEFAULT_PROFILE) -> Path:
    task, output = Path(task).resolve(), Path(output).resolve()
    profile = load_profile(profile)
    if output == task or output.is_relative_to(task):
        raise ValueError("coverage package must not overwrite or nest inside its source task")
    if output.exists():
        raise FileExistsError(output)
    if not (task / "tests").is_dir():
        raise ValueError("source task requires a tests directory and its test dependencies")
    if (task / "tests/coverage_eval").exists():
        raise ValueError("source task already contains coverage_eval")
    text = (task / "task.toml").read_text()
    parsed = tomllib.loads(text)
    name = parsed.get("task", {}).get("name", profile.project_id)
    text = _set_scalar(text, "task", "name", json.dumps(name + "-coverage"))
    text = _set_scalar(text, "metadata", "status", '"coverage-sidecar"')
    if profile.verifier_timeout_sec:
        text = _set_scalar(text, "verifier", "timeout_sec", str(profile.verifier_timeout_sec))
    # Local repository checkouts are not build assets and can be very large.
    def ignore(directory, entries):
        skipped = {name for name in entries if name in {".git", "__pycache__"}}
        if Path(directory) == task / "environment":
            skipped.update(name for name in entries if name == "repos")
        return skipped
    shutil.copytree(task, output, ignore=ignore)
    (output / "task.toml").write_text(text)
    shutil.copytree(ROOT / "coverage_eval", output / "tests/coverage_eval",
                    ignore=shutil.ignore_patterns("__pycache__", "tests"))
    # Runtime images only need the standard library to read the compiled profile.
    write_json(output / "tests/coverage-profile.json", profile_dict(profile))
    original = output / "tests/test.sh"
    if original.exists():
        shutil.copy2(original, output / "tests/test.original.sh")
    original.write_text(
        '#!/usr/bin/env bash\nset -euo pipefail\n'
        'PYTHONPATH="/tests${PYTHONPATH:+:$PYTHONPATH}" python3 -m coverage_eval.runner '
        '--profile /tests/coverage-profile.json '
        '--candidate-kind "${COVERAGE_CANDIDATE_KIND:-agent}"\n')
    original.chmod(0o755)
    shutil.copy2(ROOT / "coverage_eval/README.md", output / "COVERAGE.md")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, default=STANDARD)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.output, task=args.task, profile=args.profile))


if __name__ == "__main__":
    main()
