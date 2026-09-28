#!/usr/bin/env python3
"""Run one OpenCode document-judge turn and extract its final JSON object."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


OPENCODE_PLUGIN_VERSION = "1.18.31"


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("judge final output must be a JSON object")
    return value


def opencode_config(model: str, base_url: str) -> dict:
    if "/" not in model:
        raise ValueError("OpenCode judge model must be provider/model")
    provider, model_id = model.split("/", 1)
    return {
        "provider": {
            provider: {
                "models": {model_id: {}},
                "options": {"baseURL": base_url},
            }
        },
        "model": model,
        "small_model": model,
        "agent": {
            "title": {"disable": True},
            "build": {"steps": 12},
        },
        "permission": "allow",
    }


def opencode_environment(config_home: Path, config_path: Path,
                         base: dict[str, str] | None = None) -> dict[str, str]:
    source = base if base is not None else os.environ
    allowed = (
        "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
        "OPENAI_API_KEY", "OPENAI_BASE_URL",
    )
    env = {name: source[name] for name in allowed if source.get(name)}
    env["PATH"] = "/opt/document-eval/bin:" + env.get(
        "PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )
    env["OPENCODE_CONFIG"] = str(config_path)
    env["OPENCODE_FAKE_VCS"] = "git"
    env["OPENCODE_PURE"] = "1"
    env["OPENCODE_DISABLE_MODELS_FETCH"] = "1"
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    env["OPENCODE_DISABLE_PRUNE"] = "1"
    env["OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER"] = "1"
    env["XDG_CONFIG_HOME"] = str(config_home / "xdg-config")
    env["XDG_CACHE_HOME"] = str(config_home / "xdg-cache")
    env["XDG_DATA_HOME"] = str(config_home / "xdg-data")
    env["XDG_STATE_HOME"] = str(config_home / "xdg-state")
    for name in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        Path(env[name]).mkdir(parents=True, exist_ok=True)
    return env


def prepare_opencode_dependencies(config_home: Path, env: dict[str, str]) -> None:
    config_dir = config_home / "xdg-config" / "opencode"
    config_dir.mkdir(parents=True, exist_ok=True)
    installed = config_dir / "node_modules" / "@opencode-ai" / "plugin" / "package.json"
    if installed.is_file():
        try:
            if json.loads(installed.read_text()).get("version") == OPENCODE_PLUGIN_VERSION:
                return
        except (OSError, json.JSONDecodeError):
            pass
    package = config_dir / "package.json"
    package.write_text(json.dumps({
        "private": True,
        "dependencies": {"@opencode-ai/plugin": OPENCODE_PLUGIN_VERSION},
    }))
    install_env = dict(env)
    install_env["npm_config_update_notifier"] = "false"
    subprocess.run([
        "npm", "install", "--ignore-scripts", "--no-audit", "--no-fund",
    ], cwd=config_dir, env=install_env, check=True,
       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)


def warmup_opencode(config_home: Path, model: str, cwd: str,
                    env: dict[str, str]) -> None:
    marker = config_home / ".judge-warmed"
    if marker.is_file():
        return
    stdout_path = config_home / "warmup.events.jsonl"
    stderr_path = config_home / "warmup.stderr.txt"
    command = [
        "opencode", "--model=" + model, "run", "--format=json", "--thinking",
        "--dangerously-skip-permissions", "--", "Reply exactly WARM.",
    ]
    with stdout_path.open("w") as stdout, stderr_path.open("w") as stderr:
        result = subprocess.run(command, cwd=cwd, env=env, text=True,
                                stdout=stdout, stderr=stderr)
    if result.returncode:
        message = stderr_path.read_text(errors="replace")[-2000:]
        raise RuntimeError(f"OpenCode judge warmup failed: {message}")
    marker.write_text("ok\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--stderr", required=True)
    args = parser.parse_args()
    config_home = Path(os.environ.get(
        "DOCUMENT_OPENCODE_HOME", "/tmp/document-judge-opencode"
    ))
    config_home.mkdir(parents=True, exist_ok=True)
    config = opencode_config(args.model, os.environ["OPENAI_BASE_URL"])
    config_path = config_home / "opencode.json"
    config_path.write_text(json.dumps(config))
    env = opencode_environment(config_home, config_path)
    prepare_opencode_dependencies(config_home, env)
    warmup_opencode(config_home, args.model, args.cwd, env)
    command = [
        "opencode", "--model=" + args.model, "run", "--format=json", "--thinking",
        "--dangerously-skip-permissions", "--", Path(args.prompt).read_text(),
    ]
    with Path(args.events).open("w") as stdout, Path(args.stderr).open("w") as stderr:
        result = subprocess.run(command, cwd=args.cwd, env=env, text=True,
                                stdout=stdout, stderr=stderr)
    if result.returncode:
        print(f"OpenCode document judge exited with {result.returncode}", file=sys.stderr)
        return result.returncode
    texts = []
    for line in Path(args.events).read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "text":
            text = (event.get("part") or {}).get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
    if not texts:
        print("OpenCode document judge produced no text output", file=sys.stderr)
        return 2
    try:
        value = parse_json(texts[-1])
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"OpenCode final output is not JSON: {exc}", file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(value, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
