#!/usr/bin/env python3
"""Prepare and run task-owned workflows through local Harbor."""
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
from runtime.document_rubric import Manifest
from runtime.environment import load_env
from runtime.reporting import write_report, write_index

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Explicit task-owned workflow YAML")
    parser.add_argument("--task", type=Path, help="Task directory; defaults to tasks/standard")
    parser.add_argument("--mode", choices=["single", "flat", "hierarchical"])
    parser.add_argument("--model")
    parser.add_argument("--use-local-codex-auth", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Synthetic executor, no model; clearly marked outputs")
    parser.add_argument("--smoke-scenario", choices=["pass", "repair", "repair-reuse", "fail"], default="repair")
    parser.add_argument("--role-probe", action="store_true", help="Two minimal real model turns verifying same-session role activation")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--stop-after-stage", help="Stop successfully after this accepted lifecycle stage")
    parser.add_argument("--document-eval-manifest", type=Path,
                        help="Private frozen document-rubric manifest; enables the Harbor document verifier")
    parser.add_argument("--judge-model",
                        help="Independent document Judge model; or set DOCUMENT_JUDGE_MODEL")
    parser.add_argument("--judge-replicas", type=int, choices=(1, 2, 3),
                        help="Override the private manifest's independent Judge count")
    parser.add_argument("--job-name")
    args = parser.parse_args()
    if args.smoke and args.role_probe:
        parser.error("--smoke and --role-probe are mutually exclusive")
    env = os.environ.copy()
    load_env(HERE / ".env", env)
    evaluation_manifest = None
    judge_model = args.judge_model or env.get("DOCUMENT_JUDGE_MODEL")
    if args.document_eval_manifest:
        if args.smoke or args.role_probe:
            parser.error("document evaluation requires a real workflow rollout")
        evaluation_manifest = args.document_eval_manifest.resolve()
        try:
            Manifest.load(evaluation_manifest)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f"Invalid document evaluation manifest: {exc}")
        if not judge_model:
            parser.error("Pass --judge-model or set DOCUMENT_JUDGE_MODEL")
        if args.stop_after_stage is None:
            args.stop_after_stage = "sprint1/test-design"
        elif args.stop_after_stage != "sprint1/test-design":
            parser.error("document evaluation is scoped to --stop-after-stage sprint1/test-design")
    elif args.judge_model or args.judge_replicas:
        parser.error("Judge options require --document-eval-manifest")
    try:
        compiled = compile_workflow(resolve_config(args.config, args.task, args.mode))
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    if not compiled["execution_implemented"]:
        parser.error(f"{compiled['mode']} execution is not implemented for the lifecycle; use --mode single")
    if compiled["run"]["agent"]["adapter"] != "codex":
        parser.error("This execution backend currently supports Codex only")
    stage_ids = {stage["stage_id"] for stage in compiled["stages"]}
    if args.stop_after_stage and args.stop_after_stage not in stage_ids:
        parser.error(f"Unknown stop stage: {args.stop_after_stage}")
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
    task = prepared / "task"
    environment = task / "environment"
    environment.mkdir(parents=True)
    shutil.copytree(prepared / "workspace", environment / "workspace", symlinks=True)
    shutil.copyfile(prepared / "runtime-inputs/Dockerfile", environment / "Dockerfile")
    (environment / ".dockerignore").write_text("*\n!Dockerfile\n!workspace/\n!workspace/**\n")
    (environment / "docker-compose.yaml").write_text("services:\n  main:\n    security_opt:\n      - no-new-privileges:true\n")
    (task / "instruction.md").write_text("Execute the configured workflow with its stage boundaries and termination rules.\n")
    shutil.copyfile(prepared / "runtime-inputs/task.toml", task / "task.toml")
    verifier = {"disable": True}
    if evaluation_manifest is not None:
        verifier = {
            "import_path": "runtime.document_rubric_verifier:DocumentRubricVerifier",
            "kwargs": {
                "manifest_path": str(evaluation_manifest),
                "prepared_path": str(prepared),
                "judge_model": judge_model,
                "evaluation_boundary": args.stop_after_stage,
                **({"judge_replicas": args.judge_replicas} if args.judge_replicas else {}),
            },
        }
    recipe = {
        "job_name": name, "jobs_dir": str(HERE / "jobs"), "n_attempts": 1, "n_concurrent_trials": 1,
        "retry": {"max_retries": 0}, "environment": {"type": "docker", "delete": True},
        "verifier": verifier,
        "agents": [{"import_path": "runtime.workflow_agent:WorkflowCodex", "model_name": model,
                    "override_setup_timeout_sec": 600,
                    "kwargs": {"prepared_path": str(prepared), "smoke": args.smoke,
                               "smoke_scenario": args.smoke_scenario, "role_probe": args.role_probe,
                               "stop_after_stage": args.stop_after_stage,
                               "missing_output_policy": (
                                   "continue_for_evaluation" if evaluation_manifest is not None else "fail"
                               )}}],
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
    successful = state["status"] == "complete" or (
        state["status"] == "stopped_at_boundary"
        and state.get("stop_after_stage") == args.stop_after_stage
    )
    return 0 if successful else 1


if __name__ == "__main__":
    sys.exit(main())
