"""Export exact executable and covered lines from Coverage.py analysis data."""

import argparse
import json
from pathlib import Path

from coverage import Coverage


def export(raw_json, repo, output, data_file=None):
    raw = json.loads(raw_json.read_text())
    cov = Coverage(data_file=str(data_file or repo / ".coverage"), config_file=True)
    cov.load()
    files = {}
    for path in raw["files"]:
        absolute = Path(path) if Path(path).is_absolute() else repo / path
        if not absolute.is_file():
            raise FileNotFoundError(absolute)
        _, statements, _, missing, _ = cov.analysis2(str(absolute))
        executable = set(statements)
        files[path] = {
            "executable_lines": sorted(executable),
            "covered_lines": sorted(executable - set(missing)),
        }
    output.write_text(json.dumps({"files": files}, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-json", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--data-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.raw_json, args.repo, args.output, args.data_file)


if __name__ == "__main__":
    main()
