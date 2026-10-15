#!/usr/bin/env python3
"""Prepare and run runtime-owned workflows against a task through Harbor."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from runtime.prepare_workflow import HERE, compile_workflow, prepare
from runtime.document_rubric import Manifest
from runtime.environment import load_env
from runtime.workflow_timeouts import DEFAULT_STAGE_TIMEOUT_SEC, harbor_timeout_sec
from runtime.reporting import write_report, write_index

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True, help="Task package directory")
    parser.add_argument("--mode", choices=["single", "flat", "hierarchical"], default="single")
    parser.add_argument("--model")
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high", "xhigh", "max"),
                        help="Claude Code effort; defaults to CLAUDE_REASONING_EFFORT or high")
    parser.add_argument("--smoke", action="store_true", help="Synthetic executor, no model; clearly marked outputs")
    parser.add_argument("--smoke-scenario", choices=["pass", "repair", "repair-reuse", "fail"], default="repair")
    parser.add_argument("--role-probe", action="store_true",
                        help="Two minimal real model turns verifying mode-specific role activation")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--stop-after-stage", help="Stop successfully after this accepted lifecycle stage")
    parser.add_argument("--document-only", action="store_true", help="Permit only PRD, design and test design; preserve subagent policy")
    parser.add_argument("--max-runtime-sec", type=float, help="Total model execution wall time, starting at first stage call")
    parser.add_argument("--stage-timeout-sec", type=float, default=DEFAULT_STAGE_TIMEOUT_SEC,
                        help="Single/Flat model execution limit per stage; defaults to 14400 (4 hours)")
    parser.add_argument("--resume-from", type=Path, help="Resume an accepted document checkpoint from a trial directory")
    parser.add_argument("--request-audit", action="store_true", help="Record request metadata without rewriting model requests")
    parser.add_argument("--request-profile", action="store_true", help="Enforce effort and prompt caching through a local audited relay")
    parser.add_argument("--client-version", default="2.1.273", help="Pinned Claude Code version")
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
    reasoning_effort = args.reasoning_effort or env.get("CLAUDE_REASONING_EFFORT") or "high"
    if reasoning_effort not in {"low", "medium", "high", "xhigh", "max"}:
        parser.error("CLAUDE_REASONING_EFFORT must be low, medium, high, xhigh or max")
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
        compiled = compile_workflow(args.mode, args.task)
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    if compiled["mode"] == "hierarchical" and (args.smoke or args.role_probe):
        parser.error("Hierarchical mode requires a real Lead-managed rollout; fixed-stage smoke and role probes do not apply")
    if compiled["mode"] == "hierarchical" and args.stop_after_stage:
        parser.error("Hierarchical mode stops through Lead finish_delivery, not --stop-after-stage")
    if compiled["mode"] == "hierarchical" and evaluation_manifest is not None:
        parser.error("Document boundary evaluation currently applies to Single or Flat mode")
    stage_ids = {stage["stage_id"] for stage in compiled["stages"]}
    if args.max_runtime_sec is not None and not 0 < args.max_runtime_sec < float("inf"):
        parser.error("--max-runtime-sec must be positive and finite")
    if not 0 < args.stage_timeout_sec < float("inf"):
        parser.error("--stage-timeout-sec must be positive and finite")
    if args.resume_from and (compiled["mode"] == "hierarchical" or args.smoke or args.role_probe):
        parser.error("--resume-from requires a real Single or Flat workflow")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.client_version):
        parser.error("--client-version must be an exact numeric release")
    if args.document_only:
        if compiled["mode"] not in {"single", "flat"}:
            parser.error("--document-only requires Single or Flat mode")
        if args.stop_after_stage not in (None, "sprint1/test-design"):
            parser.error("--document-only stops at sprint1/test-design")
        args.stop_after_stage = "sprint1/test-design"
        boundary = next(i for i, s in enumerate(compiled["stages"]) if s["stage_id"] == args.stop_after_stage)
        selected = compiled["stages"][:boundary + 1]
        if [s["role"] for s in selected] != ["pm", "architect", "qa-design"] or any(s.get("write_repos") for s in selected):
            parser.error("Unexpected document stage graph or repository write access")
        compiled["stages"] = selected
    if args.stop_after_stage and args.stop_after_stage not in stage_ids:
        parser.error(f"Unknown stop stage: {args.stop_after_stage}")
    model = args.model or env.get("CLAUDE_MODEL")
    if not args.smoke and not args.prepare_only:
        if not model:
            parser.error("Configure CLAUDE_MODEL or pass --model")
        direct_auth = any(env.get(name) for name in (
            "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
            "CLAUDE_CODE_OAUTH_TOKEN", "AWS_BEARER_TOKEN_BEDROCK",
            "AWS_ACCESS_KEY_ID", "AWS_PROFILE", "CLAUDE_CODE_USE_BEDROCK",
        ))
        if not direct_auth:
            parser.error(
                "Configure Anthropic API/OAuth credentials or AWS Bedrock credentials"
            )
    model = model or "synthetic-no-model"
    if not re.fullmatch(r"[A-Za-z0-9_./:-]+", model):
        parser.error("Claude model ID contains unsupported characters")
    name = args.job_name or f"workflow-{'smoke' if args.smoke else compiled['mode']}-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]+", name):
        parser.error("Invalid job name")
    prepared = HERE / ".prepared" / name
    if (HERE / "jobs" / name).exists():
        parser.error("Job already exists")
    prepare(compiled, prepared)
    checkpoint = None
    if args.resume_from:
        from runtime.workflow_checkpoint import validate_checkpoint
        try:
            checkpoint = validate_checkpoint(args.resume_from, prepared, compiled, model, reasoning_effort)
            if args.stop_after_stage:
                boundary = next(i for i, s in enumerate(compiled["stages"]) if s["stage_id"] == args.stop_after_stage)
                if boundary < checkpoint["cursor"]:
                    raise ValueError("Stop stage must follow the restored checkpoint")
        except (OSError, ValueError, KeyError) as exc:
            parser.error(str(exc))
    selected_stages = compiled["stages"]
    if args.role_probe:
        selected_stages = selected_stages[:2]
    elif args.stop_after_stage:
        boundary = next(i for i, s in enumerate(selected_stages) if s["stage_id"] == args.stop_after_stage)
        selected_stages = selected_stages[:boundary + 1]
    if checkpoint:
        selected_stages = selected_stages[checkpoint["cursor"]:]
    outer_timeout = (args.max_runtime_sec + 600 if args.max_runtime_sec else
                     harbor_timeout_sec(selected_stages, args.stage_timeout_sec))
    task = prepared / "task"
    environment = task / "environment"
    environment.mkdir(parents=True)
    shutil.copytree(prepared / "workspace", environment / "workspace", symlinks=True)
    shutil.copyfile(prepared / "runtime-inputs/Dockerfile", environment / "Dockerfile")
    (environment / ".dockerignore").write_text("*\n!Dockerfile\n!workspace/\n!workspace/**\n")
    (environment / "docker-compose.yaml").write_text("services:\n  main:\n    security_opt:\n      - no-new-privileges:true\n")
    shutil.copyfile(prepared / "workspace/instruction.md", task / "instruction.md")
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
        "agents": [{"import_path": "runtime.workflow_agent:WorkflowClaudeCode", "model_name": model,
                    "override_setup_timeout_sec": 600,
                    **({"override_timeout_sec": outer_timeout}
                       if compiled["mode"] != "hierarchical" or args.max_runtime_sec else {}),
                    "kwargs": {"prepared_path": str(prepared), "smoke": args.smoke,
                               "reasoning_effort": reasoning_effort,
                               "max_runtime_sec": args.max_runtime_sec,
                               "stage_timeout_sec": args.stage_timeout_sec,
                               "request_profile": args.request_profile,
                               "request_audit": args.request_audit,
                               "resume_from": str(args.resume_from.resolve()) if args.resume_from else None,
                               "client_version": args.client_version,
                               "smoke_scenario": args.smoke_scenario, "role_probe": args.role_probe,
                               "stop_after_stage": args.stop_after_stage,
                               "missing_output_policy": (
                                   "continue_for_evaluation" if evaluation_manifest is not None else "fail"
                               )}}],
        "tasks": [{"path": str(task)}],
        "extra_instruction_paths": [str(prepared / "workspace/business-conversations.md")],
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
