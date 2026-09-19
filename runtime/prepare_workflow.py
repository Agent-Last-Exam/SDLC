#!/usr/bin/env python3
"""Validate/freeze public workflow inputs without calling an Agent or a model.

Use the Harbor Python environment (PyYAML is already installed there).
This is a preparation tool, not a workflow executor.
"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile

import yaml

HERE = Path(__file__).resolve().parents[1]
DEFAULT_TASK = HERE / "tasks/saleor-prd-tdd"


def resolve_config(config=None, task=None, mode=None):
    """Select a task-owned run profile; explicit YAML remains a supported entry."""
    if config is not None:
        if task is not None or mode is not None:
            raise ValueError("Use either --config or --task/--mode")
        return Path(config).resolve()
    root = Path(task).resolve() if task is not None else DEFAULT_TASK
    return root / "workflows" / f"{mode or 'single'}.yaml"


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def read_yaml(path):
    return yaml.load(path.read_text(), Loader=UniqueLoader)


def safe_relative(value):
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or "\\" in value or str(p) != value:
        raise ValueError(f"Unsafe or noncanonical workspace path: {value}")
    return value


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def compile_workflow(path, verify_repos=True):
    path = path.resolve()
    run = read_yaml(path)
    if run.get("schema_version") != 1 or run.get("kind") != "workflow_run":
        raise ValueError("Unsupported workflow schema")
    task_root = (path.parent / run["task_root"]).resolve()
    harbor_sources = {"task.toml": task_root / "task.toml",
                      "Dockerfile": task_root / "environment/Dockerfile"}
    for name, source in harbor_sources.items():
        if not source.is_file():
            raise ValueError(f"Missing task runtime input {name}: {source}")
    mode = run.get("mode")
    policies = {
        "single": ("fixed_forward", "continuous"),
        "flat": ("fixed_forward", "new_per_stage"),
        "hierarchical": ("lead_managed", "lead_with_members"),
    }
    if mode not in policies:
        raise ValueError(f"Unknown mode: {mode}")
    execution = run["execution"]
    if (execution["scheduling"], execution["principal_session"]) != policies[mode]:
        raise ValueError("Mode and session/scheduling policies disagree")
    contract_path = (path.parent / run["contract"]).resolve()
    contract = read_yaml(contract_path)
    if contract.get("schema_version") != 1 or contract.get("kind") != "delivery_contract":
        raise ValueError("Unsupported delivery contract")
    sources = {}
    for group in ("roles", "templates", "inputs"):
        sources[group] = {}
        for name, value in contract[group].items():
            source = (contract_path.parent / value).resolve()
            if not source.exists() or (name != "repos" and not source.is_file()):
                raise ValueError(f"Missing {group}:{name}: {source}")
            sources[group][name] = str(source)
    if not Path(sources["inputs"]["repos"]).is_dir():
        raise ValueError("Repository snapshot root is not a directory")
    workspace_paths = {
        "input:instruction": "instruction.md",
        "input:organization_delivery": "organization-delivery.md",
        "input:base_revisions": "base-revisions.json",
        "input:repos": "repos",
    }
    if set(contract["inputs"]) != {key.split(":")[1] for key in workspace_paths}:
        raise ValueError("Unknown or missing public inputs")
    for name, source in sources["templates"].items():
        workspace_paths[f"template:{name}"] = "templates/" + Path(source).name
    accepted_refs = set(workspace_paths)
    stages = []
    stage_ids = set()
    output_paths = set()
    for stage in contract["stages"]:
        sid = stage["id"]
        if not re.fullmatch(r"[a-z0-9_-]+/[a-z0-9_-]+", sid) or sid in stage_ids:
            raise ValueError(f"Invalid or duplicate stage: {sid}")
        stage_ids.add(sid)
        if stage["role"] not in sources["roles"]:
            raise ValueError(f"Unconfigured role: {stage['role']}")
        for ref in stage["inputs"]:
            if ref not in accepted_refs:
                raise ValueError(f"Unknown, self, or future input reference: {ref}")
        envelope = {
            "stage_id": sid,
            "role": stage["role"],
            "role_path": f"/workspace/roles/{stage['role']}.system.md",
            "inputs": {ref: "/workspace/" + workspace_paths[ref] for ref in stage["inputs"]},
            "outputs": {},
            "writable_directory": "/workspace/artifacts/" + sid,
            "scratch": "/workspace/scratch",
        }
        for name, value in stage["outputs"].items():
            value = safe_relative(value)
            if not value.startswith(f"artifacts/{sid}/") or value in output_paths:
                raise ValueError(f"Output outside its stage or duplicated: {value}")
            output_paths.add(value)
            ref = f"artifact:{sid}/{name}"
            workspace_paths[ref] = value
            accepted_refs.add(ref)
            envelope["outputs"][ref] = "/workspace/" + value
        stages.append(envelope)
    for ref in contract["delivery"]["required"]:
        if ref not in accepted_refs or not ref.startswith("artifact:"):
            raise ValueError(f"Missing final artifact: {ref}")
    if contract["delivery"]["stop_after"] != stages[-1]["stage_id"]:
        raise ValueError("Stop boundary must match final stage")
    revisions = json.loads(Path(sources["inputs"]["base_revisions"]).read_text())
    if verify_repos:
        for name, revision in revisions.items():
            repo = Path(sources["inputs"]["repos"]) / name
            expected = revision if isinstance(revision, str) else revision["commit"]
            if git(repo, "rev-parse", "HEAD") != expected:
                raise ValueError(f"Wrong Base SHA: {name}")
            if git(repo, "status", "--porcelain"):
                raise ValueError(f"Dirty Base snapshot: {name}")
    blockers = ["Preparation does not check model authentication or Docker availability; use run_workflow to execute"]
    if mode == "hierarchical":
        blockers.append("Lead blueprint, organization skill and team tools are not implemented")
    return {"schema_version": 1, "mode": mode, "run": run, "contract": contract,
            "task_root": str(task_root), "harbor_sources": {k: str(v) for k, v in harbor_sources.items()},
            "sources": sources, "stages": stages, "workspace_paths": workspace_paths,
            "execution_implemented": mode in {"single", "flat"},
            "execution_ready": False, "execution_blockers": blockers}


def prepare(compiled, destination):
    """Create a new public workspace plus host-only preparation manifest.

    Repository files come from git archive HEAD (no Target, remotes, host paths,
    dirty files, or credential-bearing .git config). No old artifacts are copied.
    """
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Destination already exists; choose a new preparation directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".workflow-", dir=destination.parent))
    try:
        workspace = staging / "workspace"
        workspace.mkdir()
        runtime_inputs = staging / "runtime-inputs"
        runtime_inputs.mkdir()
        for name, source in compiled["harbor_sources"].items():
            shutil.copyfile(source, runtime_inputs / name)
        for group in ("inputs", "templates", "roles"):
            for name, source in compiled["sources"][group].items():
                if group == "inputs" and name == "repos":
                    continue
                if group == "roles":
                    relative = f"roles/{name}.system.md"
                else:
                    ref = f"{'input' if group == 'inputs' else 'template'}:{name}"
                    relative = compiled["workspace_paths"][ref]
                target = workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        revisions = json.loads((workspace / "base-revisions.json").read_text())
        for name, revision in revisions.items():
            target = workspace / "repos" / name
            target.mkdir(parents=True)
            repo = Path(compiled["sources"]["inputs"]["repos"]) / name
            expected = revision if isinstance(revision, str) else revision["commit"]
            with tempfile.TemporaryFile() as archive:
                subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", expected], stdout=archive, check=True)
                archive.seek(0)
                with tarfile.open(fileobj=archive) as tar:
                    tar.extractall(target, filter="data")
        (workspace / "scratch").mkdir()
        for envelope in compiled["stages"]:
            (workspace / "artifacts" / envelope["stage_id"]).mkdir(parents=True)
        (staging / "resolved-workflow.json").write_text(json.dumps(compiled, ensure_ascii=False, indent=2) + "\n")
        checksums = {}
        for p in sorted(workspace.rglob("*")):
            if p.is_symlink():
                payload = str(p.readlink()).encode()
                kind = "symlink"
            elif p.is_file():
                payload = p.read_bytes()
                kind = "file"
            else:
                continue
            checksums[str(p.relative_to(workspace))] = {
                "kind": kind, "sha256": hashlib.sha256(payload).hexdigest(),
                "executable": bool(p.lstat().st_mode & 0o111),
            }
        (staging / "input-manifest.json").write_text(json.dumps(checksums, indent=2) + "\n")
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return {"directory": str(destination), "public_files": len(checksums), "model_called": False,
            "execution_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", type=Path)
    parser.add_argument("--task", type=Path, help="Task directory; defaults to tasks/saleor-prd-tdd")
    parser.add_argument("--mode", choices=["single", "flat", "hierarchical"])
    parser.add_argument("--output", type=Path, help="Create a new complete public workspace; never runs an Agent")
    args = parser.parse_args()
    try:
        compiled = compile_workflow(resolve_config(args.config, args.task, args.mode))
        result = prepare(compiled, args.output) if args.output else {
            "mode": compiled["mode"], "stages": compiled["stages"],
            "execution_ready": False, "execution_blockers": compiled["execution_blockers"],
        }
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
