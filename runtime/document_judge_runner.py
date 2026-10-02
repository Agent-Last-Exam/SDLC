#!/usr/bin/env python3
"""Run one schema-constrained Claude Code judge turn in the verifier sandbox."""

from __future__ import annotations

import argparse
import json
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

    schema = json.dumps(json.loads(Path(args.schema).read_text()), separators=(",", ":"))
    command = [
        "claude", "--print", "--output-format=json",
        "--model", args.model, "--effort", "high",
        "--json-schema", schema,
        "--safe-mode", "--restricted", "--permission-mode=dontAsk",
        "--add-dir", "/opt/document-eval", "/workspace/public",
        "/workspace/repos", "/workspace/templates",
        "--allowedTools", "Read", "Glob", "Grep",
        "--disallowedTools", "Bash", "Edit", "Write", "WebFetch",
        "WebSearch", "Task",
    ]
    prompt = Path(args.prompt).read_text()
    run_env = dict(os.environ)
    run_env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    with Path(args.events).open("w") as stdout, Path(args.stderr).open("w") as stderr:
        result = subprocess.run(
            command, input=prompt, text=True, stdout=stdout, stderr=stderr,
            cwd=args.cwd, env=run_env,
        )
    if result.returncode:
        print(f"document judge exited with {result.returncode}; see {args.stderr}", file=sys.stderr)
        return result.returncode
    try:
        envelope = json.loads(Path(args.events).read_text())
        value = envelope.get("structured_output")
        if not isinstance(value, dict):
            value = json.loads(envelope.get("result", ""))
        if not isinstance(value, dict):
            raise ValueError("structured output is not an object")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Claude Code final output is not structured JSON: {exc}", file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(value, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
