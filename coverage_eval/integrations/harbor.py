"""CLI entry point for a Harbor verifier or a disposable local workspace."""

import argparse
from pathlib import Path

from coverage_eval.config import DEFAULT_PROFILE, load_profile
from coverage_eval.models import Paths
from coverage_eval.orchestrator import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    baked = Path("/tests/coverage-profile.json")
    parser.add_argument("--profile", type=Path, default=baked if baked.is_file() else DEFAULT_PROFILE)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--tests", type=Path, default=Path("/tests"))
    parser.add_argument("--artifacts", type=Path, default=Path("/logs/artifacts"))
    parser.add_argument("--output", type=Path, default=Path("/logs/verifier"))
    parser.add_argument("--candidate-kind", choices=("agent", "reference", "synthetic"), default="agent")
    args = parser.parse_args()
    paths = Paths(*(path.resolve() for path in (args.workspace, args.tests, args.artifacts, args.output)))
    result = evaluate(load_profile(args.profile), paths, candidate_kind=args.candidate_kind)
    print(f"Coverage evaluation {result['status']}: {paths.output / 'coverage/coverage.json'}")
    if result["status"] == "error":
        raise SystemExit(1)
