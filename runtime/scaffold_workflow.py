#!/usr/bin/env python3
"""Copy a task-owned workflow bundle into another task without replacing business inputs.

The target keeps its instruction, Harbor task definition, and environment.  If the
target uses a prebuilt ``docker_image`` (as frozen benchmark packages do), a
workflow-only runtime sidecar is created so the benchmark entrypoint remains
unchanged.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import tomllib
import re


HERE = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = HERE / "tasks/saleor-prd-tdd"


def _toml(path):
    return tomllib.loads(path.read_text())


def _repository_specs(target):
    revisions = target / "environment/base-revisions.json"
    if revisions.is_file():
        return json.loads(revisions.read_text()), False
    config = target / "tests/config.json"
    if not config.is_file():
        raise ValueError(
            "Target has no environment/base-revisions.json and no tests/config.json "
            "from which Base revisions can be derived"
        )
    repos = json.loads(config.read_text()).get("repos")
    if not isinstance(repos, dict) or not repos:
        raise ValueError("tests/config.json has no repository metadata")
    result = {}
    for name, value in repos.items():
        try:
            result[name] = {
                "url": f"https://github.com/{value['github']}.git",
                "version": value["git_base"],
                "commit": value["sha_base"],
            }
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Incomplete repository metadata for {name}") from exc
    return result, True


def _workflow_task_toml(target):
    task = _toml(target / "task.toml")
    task_meta = task.get("task", {})
    metadata = task.get("metadata", {})
    environment = task.get("environment", {})
    name = task_meta.get("name", target.name).replace('"', '')
    task_id = str(metadata.get("task_id", target.name)).replace('"', '')
    return f'''schema_version = "1.3"

[task]
name = "{name}-single-workflow"
description = "Single Agent SDLC workflow sidecar for {task_id}"

[metadata]
category = "software-development"
source_task = "{task_id}"
scope = "Workflow rollout; benchmark verifier remains owned by the source task"

[agent]
timeout_sec = 10800.0
network_mode = "public"
user = "root"

[environment]
build_timeout_sec = {float(environment.get('build_timeout_sec', 1800.0))}
cpus = {int(environment.get('cpus', 4))}
memory_mb = {int(environment.get('memory_mb', 8192))}
storage_mb = {int(environment.get('storage_mb', 20480))}
workdir = "/workspace"
'''


def _workflow_dockerfile(image):
    if not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9./:@_-]+", image):
        raise ValueError("Target docker_image is not a safe concrete image reference")
    return f'''FROM {image}

# Keep the benchmark's preinstalled application dependencies, and add only the
# tools required by the workflow Agent. Network is needed while building this
# thin overlay and for model API calls, not for fetching target application code.
RUN apt-get update \\
    && apt-get install -y --no-install-recommends ripgrep jq procps less \\
    && rm -rf /var/lib/apt/lists/* \\
    && npm install -g @openai/codex@0.154.0 \\
    && npm cache clean --force \\
    && codex --version

COPY workspace/ /workspace/
RUN chown -R root:root /workspace \\
    && chmod -R a-w /workspace \\
    && rm -rf /workspace/artifacts \\
    && mkdir -p /logs/artifacts /logs/agent \\
    && ln -s /logs/artifacts /workspace/artifacts

WORKDIR /workspace
ENTRYPOINT []
CMD ["sleep", "infinity"]
'''


def _render(source, relative, specs, sidecar, workflow_instruction):
    content = (source / relative).read_bytes()
    if relative == Path("roles/pm.system.md") and "saleor-platform" not in specs:
        text = content.decode()
        old = ("现有项目的代码仓库位于 `/workspace/repos/`：`saleor/` 是核心后端，"
               "`saleor-dashboard/` 是商家管理前端，`saleor-platform/` 提供项目运行与部署配置。")
        new = ("现有项目的代码仓库位于 `/workspace/repos/`：`saleor/` 是核心后端，"
               "`saleor-dashboard/` 是商家管理前端。")
        if old not in text:
            raise ValueError("Cannot adapt PM repository inventory: source text changed")
        content = text.replace(old, new).encode()
    if sidecar and relative.parent == Path("workflows") and relative.name in {
        "single.yaml", "flat.yaml", "hierarchical.yaml"
    }:
        text = content.decode()
        if "task_root: .." not in text:
            raise ValueError(f"Cannot adapt task_root in {relative}")
        content = text.replace("task_root: ..", "task_root: ../workflow-runtime", 1).encode()
    if workflow_instruction and relative == Path("workflows/lifecycle.yaml"):
        text = content.decode()
        if "instruction: ../instruction.md" not in text:
            raise ValueError("Cannot bind the target-specific workflow instruction")
        content = text.replace(
            "instruction: ../instruction.md",
            "instruction: ../workflow-instruction.md",
            1,
        ).encode()
    return content


def _manifest(target):
    path = target / "manifest.json"
    if not path.is_file():
        return False
    value = json.loads(path.read_text())
    files = {}
    for item in sorted(target.rglob("*")):
        if not item.is_file() or item == path or item.is_relative_to(target / "environment/repos"):
            continue
        files[str(item.relative_to(target))] = hashlib.sha256(item.read_bytes()).hexdigest()
    value["files"] = files
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    return True


def scaffold(source, target, *, force=False, update_manifest=False):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        raise ValueError("Source and target task must differ")
    for path in (source / "task.toml", source / "environment/Dockerfile",
                 target / "task.toml", target / "environment/Dockerfile",
                 target / "instruction.md"):
        if not path.is_file():
            raise ValueError(f"Missing task input: {path}")
    specs, derived = _repository_specs(target)
    target_toml = _toml(target / "task.toml")
    base_image = target_toml.get("environment", {}).get("docker_image")
    sidecar = bool(base_image)
    workflow_instruction = (target / "workflow-instruction.md").is_file()
    planned = {}
    for directory in ("roles", "templates", "workflows"):
        for item in sorted((source / directory).rglob("*")):
            if item.is_file():
                relative = item.relative_to(source)
                planned[relative] = _render(
                    source, relative, specs, sidecar, workflow_instruction
                )
    if derived:
        planned[Path("environment/base-revisions.json")] = (
            json.dumps(specs, ensure_ascii=False, indent=2) + "\n"
        ).encode()
    if sidecar:
        planned[Path("workflow-runtime/task.toml")] = _workflow_task_toml(target).encode()
        planned[Path("workflow-runtime/environment/Dockerfile")] = _workflow_dockerfile(base_image).encode()

    conflicts = []
    for relative, content in planned.items():
        destination = target / relative
        if destination.exists() and destination.read_bytes() != content:
            conflicts.append(str(relative))
    if conflicts and not force:
        raise ValueError("Refusing to replace adapted workflow files: " + ", ".join(conflicts))

    written, unchanged = [], []
    # Stage bytes first so an interrupted source read cannot leave a half-copy.
    with tempfile.TemporaryDirectory(prefix=".workflow-scaffold-", dir=target.parent) as tmp:
        staging = Path(tmp)
        for relative, content in planned.items():
            staged = staging / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(content)
        for relative, content in planned.items():
            destination = target / relative
            if destination.exists() and destination.read_bytes() == content:
                unchanged.append(str(relative))
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staging / relative, destination)
            written.append(str(relative))
    manifest_updated = _manifest(target) if update_manifest else False
    return {
        "source": str(source),
        "target": str(target),
        "repositories": sorted(specs),
        "base_revisions_derived": derived,
        "workflow_runtime_sidecar": sidecar,
        "written": written,
        "unchanged": unchanged,
        "manifest_updated": manifest_updated,
        "next_step": f"python3 -m runtime.prepare_sources --task {target}",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="Existing task receiving the workflow bundle")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help="Task providing roles, templates, workflow contract, and runtime sidecar")
    parser.add_argument("--force", action="store_true", help="Replace differing workflow-owned files")
    parser.add_argument("--update-manifest", action="store_true",
                        help="Refresh target manifest.json after copying")
    args = parser.parse_args()
    try:
        result = scaffold(args.source, args.target, force=args.force,
                          update_manifest=args.update_manifest)
    except (ValueError, OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
