#!/usr/bin/env python3
"""Prepare and run the documentation workflow through local Harbor."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
import uuid

from runtime.prepare_workflow import HERE, compile_workflow, prepare, resolve_config
from runtime.environment import load_env
from runtime.reporting import write_report, write_index

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Explicit task-owned workflow YAML")
    parser.add_argument("--task", type=Path, help="Task directory; defaults to tasks/saleor-prd-tdd")
    parser.add_argument("--mode", choices=["single", "flat", "hierarchical"])
    parser.add_argument("--model")
    parser.add_argument("--use-local-codex-auth", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Synthetic executor, no model; clearly marked outputs")
    parser.add_argument("--role-probe", action="store_true", help="Two minimal real model turns verifying same-session role activation")
    parser.add_argument("--continue-from", type=Path, help="Continue a failed trial after its accepted PRD, keeping its native session")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--job-name")
    args = parser.parse_args()
    if args.smoke and args.role_probe:
        parser.error("--smoke and --role-probe are mutually exclusive")
    if args.continue_from and (args.smoke or args.role_probe):
        parser.error("Continuation cannot be combined with synthetic/probe mode")
    env = os.environ.copy()
    load_env(HERE / ".env", env)
    try:
        compiled = compile_workflow(resolve_config(args.config, args.task, args.mode))
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    if compiled["mode"] == "hierarchical":
        parser.error("Hierarchical is configured but its Lead backend is not implemented")
    if compiled["run"]["agent"]["adapter"] != "codex":
        parser.error("This execution backend currently supports Codex only")
    supported_stages = [("sprint1/prd", "pm"), ("sprint1/tech-design", "architect")]
    if [(s["stage_id"], s["role"]) for s in compiled["stages"]] != supported_stages:
        parser.error("This backend implements only the PRD -> technical-design documentation contract")
    model = args.model or env.get("CODEX_MODEL")
    if args.use_local_codex_auth:
        codex_home = Path.home() / ".codex"
        auth = codex_home / "auth.json"
        if not auth.is_file():
            parser.error("Local Codex auth.json is missing")
        env["CODEX_AUTH_JSON_PATH"] = str(auth)
        local = tomllib.loads((codex_home / "config.toml").read_text())
        model = model or local.get("model")
        if local.get("model_provider") not in (None, "openai"):
            parser.error("Custom local model provider needs explicit adapter configuration")
    if not args.smoke and not args.prepare_only:
        if not model:
            parser.error("Configure CODEX_MODEL or pass --model")
        if not (env.get("CODEX_AUTH_JSON_PATH") or env.get("OPENAI_API_KEY")):
            parser.error("Configure auth or explicitly select --use-local-codex-auth")
    model = model or "synthetic-no-model"
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", model):
        parser.error("Codex needs a plain model ID without provider prefixes")
    name = args.job_name or f"workflow-{'smoke' if args.smoke else compiled['mode']}-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]+", name):
        parser.error("Invalid job name")
    prepared = HERE / ".prepared" / name
    if (HERE / "jobs" / name).exists():
        parser.error("Job already exists")
    prepare(compiled, prepared)
    if args.continue_from:
        old_config = json.loads((args.continue_from / "config.json").read_text())
        old_prepared = Path(old_config["agent"]["kwargs"]["prepared_path"])
        if json.loads((prepared / "input-manifest.json").read_text()) != json.loads((old_prepared / "input-manifest.json").read_text()):
            parser.error("Public inputs changed; cannot continue the same workflow")
    task = prepared / "task"
    environment = task / "environment"
    environment.mkdir(parents=True)
    shutil.copytree(prepared / "workspace", environment / "workspace", symlinks=True)
    shutil.copyfile(prepared / "runtime-inputs/Dockerfile", environment / "Dockerfile")
    (environment / ".dockerignore").write_text("*\n!Dockerfile\n!workspace/\n!workspace/**\n")
    (environment / "docker-compose.yaml").write_text("services:\n  main:\n    security_opt:\n      - no-new-privileges:true\n")
    (task / "instruction.md").write_text("Execute the configured documentation workflow; stop after technical review.\n")
    shutil.copyfile(prepared / "runtime-inputs/task.toml", task / "task.toml")
    recipe = {
        "job_name": name, "jobs_dir": str(HERE / "jobs"), "n_attempts": 1, "n_concurrent_trials": 1,
        "retry": {"max_retries": 0}, "environment": {"type": "docker", "delete": True},
        "verifier": {"disable": True},
        "agents": [{"import_path": "runtime.workflow_agent:WorkflowCodex", "model_name": model,
                    "override_setup_timeout_sec": 600,
                    "kwargs": {"prepared_path": str(prepared), "smoke": args.smoke, "role_probe": args.role_probe,
                               "continue_from": str(args.continue_from.resolve()) if args.continue_from else None}}],
        "tasks": [{"path": str(task)}],
    }
    (prepared / "job.json").write_text(json.dumps(recipe, indent=2) + "\n")
    print(f"Recipe: {prepared / 'job.json'}", flush=True)
    if args.prepare_only:
        return 0
    env["PYTHONPATH"] = str(HERE) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    job = HERE / "jobs" / name
    try:
        result = subprocess.run(["harbor", "run", "--config", str(prepared / "job.json")], env=env, cwd=HERE)
    finally:
        job.mkdir(parents=True, exist_ok=True)
        print(f"Report: {write_report(job)}", flush=True)
        write_index(job.parent)
    if result.returncode:
        return result.returncode
    trial_results = list((HERE / "jobs" / name).glob("*/result.json"))
    if len(trial_results) != 1:
        raise RuntimeError("Expected one Harbor trial result")
    trial = trial_results[0].parent
    state_file = trial / "workflow/state.json"
    if json.loads(trial_results[0].read_text()).get("exception_info") or not state_file.exists():
        print(f"Workflow failed; inspect {trial}", file=sys.stderr)
        return 1
    state = json.loads(state_file.read_text())
    print(f"Workflow {state['status']}: {state_file}", flush=True)
    if not args.role_probe:
        print(f"Accepted artifacts: {trial / 'workflow/accepted'}", flush=True)
    return 0 if state["status"] == "complete" else 2 if state["status"] == "blocked" else 1


if __name__ == "__main__":
    sys.exit(main())
