#!/usr/bin/env python3
"""Validate and freeze workflow inputs without calling an Agent or a model.

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
import tomllib

import yaml

HERE = Path(__file__).resolve().parents[1]
DEFAULTS = Path(__file__).resolve().parent / "defaults"
CONTRACT = DEFAULTS / "workflows/lifecycle.yaml"

MODES = ("single", "flat", "hierarchical")
HIERARCHICAL_BUDGETS = (
    "max_members", "max_concurrency", "max_lead_turns", "max_assignments",
    "max_revisions_per_stage", "max_actions_per_turn",
)


def resolve_mode(mode):
    """Select the runtime's run profile for ``mode``."""
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}")
    return DEFAULTS / "workflows" / f"{mode}.yaml"


def validate_run(run, path):
    """Check the profile is well formed; the file is the source, not a copy to verify."""
    if run.get("schema_version") != 1 or run.get("kind") != "workflow_run":
        raise ValueError(f"Unsupported workflow schema: {path}")
    fields = {"schema_version", "kind", "mode", "contract", "agent", "execution"}
    if set(run) != fields:
        raise ValueError(f"{path.name}: run profile fields must be {sorted(fields)}")
    mode = run.get("mode")
    # The controllers branch on mode alone, so a mismatched file would silently
    # run a different mode than the one requested.
    if mode != path.stem:
        raise ValueError(f"Profile {path.name} declares mode {mode!r}")
    if run.get("agent") != {"adapter": "claude_code"}:
        raise ValueError(f"Unsupported agent adapter in {path.name}")
    execution = run["execution"]
    expected_execution = {"max_cost_usd"} | (
        set(HIERARCHICAL_BUDGETS) if mode == "hierarchical" else {"subagents"}
    )
    if set(execution) != expected_execution:
        raise ValueError(
            f"{path.name}: execution fields must be {sorted(expected_execution)}"
        )
    cost = execution.get("max_cost_usd")
    if type(cost) not in (int, float) or isinstance(cost, bool) or cost <= 0:
        raise ValueError(f"{path.name}: max_cost_usd must be a positive number")
    if mode == "hierarchical":
        for key in HIERARCHICAL_BUDGETS:
            if type(execution.get(key)) is not int or execution[key] <= 0:
                raise ValueError(f"{path.name}: {key} must be a positive integer")
        if execution["max_concurrency"] > execution["max_members"]:
            raise ValueError(f"{path.name}: max_concurrency cannot exceed max_members")
    else:
        subagents = execution.get("subagents")
        if not isinstance(subagents, dict) or set(subagents) != {"enabled"} \
                or not isinstance(subagents["enabled"], bool):
            raise ValueError(f"{path.name}: subagents must contain one boolean enabled field")
    return run


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


def resolve_source(value, *, base, task, group):
    """Resolve a contract source.

    ``defaults:`` reads the runtime default roles and templates, ``task:`` and
    ``derive:`` are relative to the task root, and a bare path is relative to the
    contract. ``derive:`` names the package file an input is computed from, so
    the resolved path is an input to generation rather than a copied file.
    """
    for scheme, root, allowed in (
        ("defaults:", DEFAULTS / group, {"roles", "templates"}),
        ("task:", task, {"inputs"}),
        ("derive:", task, {"inputs"}),
    ):
        if value.startswith(scheme):
            if group not in allowed:
                raise ValueError(f"{scheme} is not accepted for {group}")
            if root is None:
                raise ValueError(f"{scheme} requires a task directory; use --task")
            resolved = (root / safe_relative(value[len(scheme):])).resolve()
            if not resolved.is_relative_to(root.resolve()):
                raise ValueError(f"Unsafe {scheme} reference: {value}")
            return resolved
    return (base / value).resolve()


def derive_base_revisions(manifest):
    """Build Base revisions from the package's own environment manifest.

    Frozen packages record the immutable commit each repository's diff is taken
    against; that commit, not the upstream tag, is the Agent's Base.
    """
    repositories = json.loads(manifest.read_text())["repositories"]
    derived = {}
    for name, value in repositories.items():
        # Both values are interpolated into generated build commands.
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
            raise ValueError(f"Unsafe repository name: {name}")
        commit = value["agent_baseline_commit"]
        if not re.fullmatch(r"[0-9a-f]{40}", str(commit)):
            raise ValueError(f"Invalid agent baseline commit for {name}: {commit}")
        derived[name] = {"version": "agent-baseline", "commit": commit}
    return derived


def generated_task_toml(task_toml, mode):
    environment = task_toml["environment"]
    name, task_id = task_toml["task"]["name"], task_toml["metadata"]["task_id"]
    for value in (name, task_id):
        if '"' in value:
            raise ValueError(f"Task identity is not a safe TOML string: {value}")
    return f'''schema_version = "1.3"

[task]
name = "{name}-{mode}-workflow"
description = "{mode.title()} Agent SDLC workflow sidecar for {task_id}"

[metadata]
category = "software-development"
source_task = "{task_id}"
scope = "Workflow rollout; benchmark verifier remains owned by the source task"

[agent]
timeout_sec = 10800.0
network_mode = "public"
user = "root"

[environment]
build_timeout_sec = {float(environment["build_timeout_sec"])}
cpus = {int(environment["cpus"])}
memory_mb = {int(environment["memory_mb"])}
storage_mb = {int(environment["storage_mb"])}
workdir = "/workspace"

[verifier]
environment_mode = "separate"
network_mode = "public"
timeout_sec = 7200.0
'''


def generated_dockerfile(image, revisions):
    """Thin overlay on the task's published image; never rebuilds the application."""
    if not re.fullmatch(r"[A-Za-z0-9./:@_-]+", image):
        raise ValueError(f"Task docker_image is not a safe concrete image reference: {image}")
    # The image keeps each repository at /workspace/<name> with its installed
    # dependencies. Move rather than copy so node_modules survives intact, and
    # assert the Base commit the verifier diffs against.
    moves = " \\\n    && ".join(
        f'test "$(git -C /workspace/{name} rev-parse HEAD)" = "{spec["commit"]}" '
        f"&& mv /workspace/{name} /workspace/repos/{name}"
        for name, spec in sorted(revisions.items())
    )
    links = " \\\n    && ".join(
        f"ln -s /workspace/repos/{name} /workspace/{name}" for name in sorted(revisions)
    )
    relocate = f'''
# Relocate the image's repositories to the workspace layout the runtime owns, and
# keep the original paths as links so the image's own test runtime still resolves.
RUN mkdir -p /workspace/repos \\
    && {moves} \\
    && {links}
'''
    return f'''FROM {image}

# Keep the benchmark's preinstalled application dependencies, and add only the
# tools required by the workflow Agent. Network is needed while building this
# thin overlay and for model API calls, not for fetching target application code.
RUN apt-get update \\
    && apt-get install -y --no-install-recommends ripgrep jq procps less \\
    && rm -rf /var/lib/apt/lists/* \\
    && npm install -g @anthropic-ai/claude-code@2.1.273 \\
    && npm cache clean --force \\
    && claude --version
{relocate}
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


def compile_workflow(mode, task, verify_repos=True, contract_path=CONTRACT):
    """Compile a run of ``mode`` against a task package.

    The run profile, delivery contract and Harbor task definition are owned by the
    runtime under ``defaults/``; the package supplies only business inputs, its Base
    identity and the published image. Nothing is read from the package's workflows.
    """
    profile = resolve_mode(mode)
    run = validate_run(read_yaml(profile), profile)
    task = Path(task).resolve()
    if contract_path is CONTRACT:
        contract_path = (profile.parent / run["contract"]).resolve()
    task_toml = tomllib.loads((task / "task.toml").read_text())
    # A package shipping a published image owns no buildable environment, so the
    # Harbor definition is generated and the repositories come from that image.
    image = task_toml["environment"].get("docker_image")
    repos_source = "image" if image else "host"
    harbor_sources, generated_inputs = {}, {}
    harbor_generated = {"task.toml": generated_task_toml(task_toml, mode)} if image else {}
    if not image:
        harbor_sources = {"task.toml": task / "task.toml",
                          "Dockerfile": task / "environment/Dockerfile"}
        for name, source in harbor_sources.items():
            if not source.is_file():
                raise ValueError(f"Missing task runtime input {name}: {source}")
    contract_path = Path(contract_path).resolve()
    contract = read_yaml(contract_path)
    if contract.get("schema_version") != 1 or contract.get("kind") != "delivery_contract":
        raise ValueError("Unsupported delivery contract")
    if contract.get("scope") != "local_sdlc":
        raise ValueError("Only the local_sdlc lifecycle contract is supported")
    if mode == "hierarchical" and not {"lead", "member", "reviewer"}.issubset(contract.get("roles", {})):
        raise ValueError("Hierarchical contract requires lead, member and reviewer roles")
    sources = {}
    input_workspace_paths = {}
    for group in ("roles", "templates", "inputs"):
        sources[group] = {}
        for name, value in contract[group].items():
            if group == "inputs":
                if not isinstance(value, dict):
                    raise ValueError(f"Input {name} must explicitly declare source and workspace")
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
            source = resolve_source(
                source_value, base=contract_path.parent, task=task, group=group
            )
            if source_value.startswith("derive:"):
                if name != "base_revisions":
                    raise ValueError(f"derive: is only defined for base_revisions, not {name}")
                generated_inputs[name] = json.dumps(
                    derive_base_revisions(source), ensure_ascii=False, indent=2
                ) + "\n"
            elif name == "repos" and repos_source == "image":
                pass  # The image carries the repositories; no host tree exists.
            else:
                missing = (not source.is_dir() if name == "repos" else not source.is_file())
                if missing and (name != "repos" or verify_repos):
                    raise ValueError(f"Missing {group}:{name}: {source}")
            sources[group][name] = str(source)
            if group == "inputs":
                if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
                    raise ValueError(f"Invalid input name: {name}")
                input_workspace_paths[name] = workspace_value
    required_input_paths = {
        "instruction": "instruction.md",
        "base_revisions": "base-revisions.json",
        "repos": "repos",
    }
    if set(contract["inputs"]) != set(required_input_paths):
        raise ValueError("Local SDLC requires exactly instruction, base_revisions and repos inputs")
    if verify_repos and repos_source == "host" and not Path(sources["inputs"]["repos"]).is_dir():
        raise ValueError("Repository snapshot root is not a directory")
    if input_workspace_paths != required_input_paths:
        raise ValueError(f"Local SDLC inputs must use workspace paths {required_input_paths}")
    workspace_paths = {
        f"input:{name}": value for name, value in input_workspace_paths.items()
    }
    for name, source in sources["templates"].items():
        relative = "templates/" + Path(source).name
        if relative in workspace_paths.values():
            raise ValueError(f"Template path collides with a workflow input: {relative}")
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
        if "additional_outputs" in stage:
            additional = stage["additional_outputs"]
            if not isinstance(additional, dict) or set(additional) != {"directory", "purpose"}:
                raise ValueError(f"Invalid additional_outputs for {sid}")
            directory = safe_relative(additional["directory"])
            if not directory.startswith(f"artifacts/{sid}/"):
                raise ValueError(f"Additional output outside its stage: {directory}")
            if any(path == directory or path.startswith(directory + "/") for path in output_paths):
                raise ValueError(f"Additional output collides with a declared output: {directory}")
            envelope["additional_output_directory"] = "/workspace/" + directory
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
    if [(s["stage_id"], s["role"]) for s in stages] != expected:
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
    revisions = json.loads(
        generated_inputs["base_revisions"]
        if "base_revisions" in generated_inputs
        else Path(sources["inputs"]["base_revisions"]).read_text()
    )
    if image:
        harbor_generated["Dockerfile"] = generated_dockerfile(image, revisions)
    if verify_repos and repos_source == "host":
        for name, revision in revisions.items():
            repo = Path(sources["inputs"]["repos"]) / name
            expected = revision if isinstance(revision, str) else revision["commit"]
            if git(repo, "rev-parse", "HEAD") != expected:
                raise ValueError(f"Wrong Base SHA: {name}")
            if git(repo, "status", "--porcelain"):
                raise ValueError(f"Dirty Base snapshot: {name}")
    return {"schema_version": 1, "mode": mode, "run": run, "contract": contract,
            "task": str(task), "harbor_sources": {k: str(v) for k, v in harbor_sources.items()},
            "harbor_generated": harbor_generated, "generated_inputs": generated_inputs,
            "repos_source": repos_source,
            "sources": sources, "stages": stages, "workspace_paths": workspace_paths}


def prepare(compiled, destination):
    """Create a new Agent workspace plus host-only preparation manifest.

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
        for name, content in compiled["harbor_generated"].items():
            (runtime_inputs / name).write_text(content)
        generated_inputs = compiled["generated_inputs"]
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
                if group == "inputs" and name in generated_inputs:
                    target.write_text(generated_inputs[name])
                else:
                    shutil.copyfile(source, target)
        revisions = json.loads((workspace / compiled["workspace_paths"]["input:base_revisions"]).read_text())
        if compiled["repos_source"] == "image":
            # The image already carries each repository with its installed
            # dependencies; the generated Dockerfile moves them into place.
            revisions = {}
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
    return {"directory": str(destination), "workspace_files": len(checksums),
            "model_called": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True, help="Task package directory")
    parser.add_argument("--mode", choices=MODES, default="single")
    parser.add_argument("--output", type=Path, help="Create a complete Agent workspace; never runs an Agent")
    args = parser.parse_args()
    try:
        compiled = compile_workflow(args.mode, args.task)
        result = prepare(compiled, args.output) if args.output else {
            "mode": compiled["mode"], "stages": compiled["stages"],
        }
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
