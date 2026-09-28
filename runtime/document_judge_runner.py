#!/usr/bin/env python3
"""Run one schema-constrained Codex document-judge turn in the verifier sandbox."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--stderr", required=True)
    args = parser.parse_args()

    command = [
        "codex", "exec",
        "--sandbox", "read-only",
        "--skip-git-repo-check",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--color", "never",
        "--model", args.model,
        "--output-schema", args.schema,
        "--output-last-message", args.output,
        "--json",
        "-c", "web_search=disabled",
        "-c", "model_reasoning_effort=high",
        "-c", "features.multi_agent=false",
        "-C", args.cwd,
    ]
    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        command.extend(["-c", "openai_base_url=" + base_url])
    prompt = Path(args.prompt).read_text()
    with Path(args.events).open("w") as stdout, Path(args.stderr).open("w") as stderr:
        result = subprocess.run(command, input=prompt, text=True, stdout=stdout, stderr=stderr)
    if result.returncode:
        print(f"document judge exited with {result.returncode}; see {args.stderr}", file=sys.stderr)
        return result.returncode
    if not Path(args.output).is_file() or not Path(args.output).read_text().strip():
        print("document judge produced no final structured output", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
