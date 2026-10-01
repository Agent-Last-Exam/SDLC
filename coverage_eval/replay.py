"""Replay a configured project in its prepared Harbor verifier image."""

import argparse
from pathlib import Path
import subprocess

from coverage_eval.config import DEFAULT_PROFILE, load_profile, profile_dict
from coverage_eval.utils import write_json


def replay(profile, patches, output, *, image=None, candidate_kind="agent"):
    patches, output = Path(patches).resolve(), Path(output).resolve()
    image = image or profile.test_image
    if not image:
        raise ValueError("provide --image or test_image in the profile")
    if candidate_kind not in {"agent", "reference", "synthetic"}:
        raise ValueError("invalid candidate_kind")
    for repo in profile.repositories:
        if not (patches / repo.model_patch).is_file():
            raise ValueError(f"missing {repo.model_patch}")
    if (output / "coverage/coverage.json").exists():
        raise ValueError("choose a fresh output directory")
    output.mkdir(parents=True, exist_ok=True)
    compiled = output / "profile-input.json"
    write_json(compiled, profile_dict(profile))
    subprocess.run(["docker", "run", "--rm", "--network", "none", *profile.docker_args,
                    "--mount", f"type=bind,src={patches},dst=/logs/artifacts,readonly",
                    "--mount", f"type=bind,src={output},dst=/logs/verifier",
                    "--mount", f"type=bind,src={compiled},dst=/tests/coverage-profile.json,readonly",
                    "-e", "PYTHONPATH=/tests", image, "python3", "-m", "coverage_eval.runner",
                    "--profile", "/tests/coverage-profile.json", "--candidate-kind", candidate_kind], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--patches", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image")
    parser.add_argument("--candidate-kind", choices=("agent", "reference", "synthetic"), default="agent")
    args = parser.parse_args()
    replay(load_profile(args.profile), args.patches, args.output, image=args.image, candidate_kind=args.candidate_kind)


if __name__ == "__main__":
    main()
