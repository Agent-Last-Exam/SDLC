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
    if contract.get("scope") != "local_sdlc":
        raise ValueError("Only the local_sdlc lifecycle contract is supported")
    sources = {}
    input_workspace_paths = {}
    explicit_input_sources = {}
    for group in ("roles", "templates", "inputs"):
        sources[group] = {}
        for name, value in contract[group].items():
            if group == "inputs" and isinstance(value, dict):
                if set(value) != {"source", "workspace"}:
                    raise ValueError(
                        f"Input {name} must declare exactly source and workspace"
                    )
                source_value = value["source"]
                workspace_value = safe_relative(value["workspace"])
            else:
                source_value = value
                workspace_value = None
            if not isinstance(source_value, str):
                raise ValueError(f"Invalid {group}:{name} source")
            source = (contract_path.parent / source_value).resolve()
            missing = (not source.is_dir() if name == "repos" else not source.is_file())
            if missing and (name != "repos" or verify_repos):
                raise ValueError(f"Missing {group}:{name}: {source}")
            sources[group][name] = str(source)
            if group == "inputs":
                if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
                    raise ValueError(f"Invalid input name: {name}")
                input_workspace_paths[name] = workspace_value
                if isinstance(value, dict):
                    explicit_input_sources[name] = source
    legacy_input_paths = {
        "instruction": "instruction.md",
        "base_revisions": "base-revisions.json",
        "repos": "repos",
    }
    if not {"base_revisions", "repos"}.issubset(contract["inputs"]):
        raise ValueError("Missing required Base inputs")
    if verify_repos and not Path(sources["inputs"]["repos"]).is_dir():
        raise ValueError("Repository snapshot root is not a directory")
    for name, value in input_workspace_paths.items():
        if value is None:
            if name not in legacy_input_paths:
                raise ValueError(f"Input {name} needs an explicit workspace path")
            input_workspace_paths[name] = legacy_input_paths[name]
    if input_workspace_paths["base_revisions"] != "base-revisions.json":
        raise ValueError("base_revisions must be exposed as base-revisions.json")
    if input_workspace_paths["repos"] != "repos":
        raise ValueError("repos must be exposed as repos")
    for name, value in input_workspace_paths.items():
        if name not in {"instruction", "base_revisions", "repos"} and not value.startswith("public/"):
            raise ValueError(f"Public input {name} must stay below public/")
        contract_public_root = contract_path.parent.parent / "public"
        if (value.startswith("public/")
                and not explicit_input_sources[name].is_relative_to(contract_public_root)):
            raise ValueError(f"Public input {name} must come from the task public directory")
    if len(set(input_workspace_paths.values())) != len(input_workspace_paths):
        raise ValueError("Public inputs cannot share a workspace path")
    workspace_paths = {
        f"input:{name}": value for name, value in input_workspace_paths.items()
    }
    for name, source in sources["templates"].items():
        relative = "templates/" + Path(source).name
        if relative in workspace_paths.values():
            raise ValueError(f"Template path collides with a public input: {relative}")
        workspace_paths[f"template:{name}"] = relative
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
        for key in ("round", "write_repos", "capture_repos", "reuse_unless", "reuse_stage"):
            if key in stage:
                envelope[key] = stage[key]
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
    expected = [("sprint1/" + name, role) for name, role in (
        ("prd", "pm"), ("tech-design", "architect"), ("test-design", "qa-design"),
        ("development", "developer"), ("deploy", "deployer"), ("qa", "qa"))]
    expected += [("sprint2/" + name, role) for name, role in (
        ("triage", "triage"), ("tech-design", "architect"),
        ("development", "developer"), ("deploy", "deployer"), ("qa", "qa"))]
    if [(s["stage_id"], s["role"]) for s in stages] != expected or contract["delivery"].get("qa_rounds") != 2:
        raise ValueError("Local SDLC requires the bounded two-sprint plan")
    for stage in stages:
        if stage["role"] != "pm" and "artifact:sprint1/prd/prd" not in stage["inputs"]:
            raise ValueError("Every downstream stage must use the accepted first-round PRD")
        expected_round = int(stage["stage_id"][6])
        if stage["role"] not in {"pm", "architect"} or expected_round == 2:
            if type(stage.get("round")) is not int or stage["round"] != expected_round:
                raise ValueError("Stage round must match its sprint")
        if bool(stage.get("write_repos")) != (stage["role"] == "developer") or bool(stage.get("capture_repos")) != (stage["role"] == "developer"):
            raise ValueError("Only development stages must write and capture repositories")
        if stage["stage_id"].startswith("sprint2/") and stage["role"] == "architect":
            if stage.get("reuse_unless") != "design_changed" or stage.get("reuse_stage") != stage["stage_id"].replace("sprint2/", "sprint1/"):
                raise ValueError("Invalid repair-stage reuse policy")
        elif "reuse_unless" in stage or "reuse_stage" in stage:
            raise ValueError("Only repair design stages may reuse artifacts")
        if stage["role"] == "qa":
            case_refs = [ref for ref in stage["inputs"] if ref.endswith("/test_cases")]
            if case_refs != ["artifact:sprint1/test-design/test_cases"]:
                raise ValueError("Both QA rounds must use the accepted first-round test cases")
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
    if mode == "flat":
        blockers.append("Flat lifecycle isolation and handoff are not implemented")
    if mode == "hierarchical":
        blockers.append("Lead blueprint, organization skill and team tools are not implemented")
    return {"schema_version": 1, "mode": mode, "run": run, "contract": contract,
            "task_root": str(task_root), "harbor_sources": {k: str(v) for k, v in harbor_sources.items()},
            "sources": sources, "stages": stages, "workspace_paths": workspace_paths,
            "execution_implemented": mode == "single",
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
        revisions = json.loads((workspace / compiled["workspace_paths"]["input:base_revisions"]).read_text())
        for name, revision in revisions.items():
            target = workspace / compiled["workspace_paths"]["input:repos"] / name
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
