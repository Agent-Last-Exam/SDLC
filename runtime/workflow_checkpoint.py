"""Restore accepted document boundaries into a fresh Single or Flat environment.

Only read-only document prefixes are supported. Accepted development snapshots
and interrupted, unaccepted work are never replayed by this entry point.
"""
import copy
import json
from pathlib import Path
import shutil

from runtime.workflow_controller import digest


def regular_tree(directory):
    directory = Path(directory)
    if not directory.is_dir() or any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError(f"Checkpoint directory is redirected or missing: {directory}")
    hashes = {}
    for path in directory.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError(f"Checkpoint contains a redirected or nonregular file: {path}")
        if path.is_file():
            if path.stat().st_nlink != 1:
                raise ValueError(f"Checkpoint contains a hard link: {path}")
            hashes[str(path.relative_to(directory))] = digest(path)
    return hashes


def validate_checkpoint(source, prepared, compiled, model, effort):
    # Import lazily: the runtime adapter calls this module during construction.
    from runtime.workflow_agent import _jsonl_rows, native_role_evidence

    source, prepared = Path(source), Path(prepared)
    original = json.loads((source / "workflow/state.json").read_text())
    config = json.loads((source / "config.json").read_text())["agent"]
    prior = Path(config["kwargs"]["prepared_path"])
    previous = json.loads((prior / "resolved-workflow.json").read_text())
    mode = compiled["mode"]
    if mode not in {"single", "flat"} or original.get("mode") != mode or previous["mode"] != mode:
        raise ValueError("Checkpoint and destination must use the same Single or Flat mode")
    if original.get("synthetic") or not original.get("model_called", True):
        raise ValueError("Synthetic checkpoints cannot resume a real workflow")
    cursor = original.get("cursor")
    if type(cursor) is not int or not 0 < cursor < len(compiled["stages"]):
        raise ValueError("Checkpoint must have accepted stages and remaining work")
    if original.get("status") not in {"interrupted", "timed_out", "failed", "stopped_at_boundary", "budget_exhausted"}:
        raise ValueError("Checkpoint must be stopped at an accepted boundary")
    stages = compiled["stages"][:cursor]
    if stages != previous["stages"][:cursor] or any(
        s["role"] not in {"pm", "architect", "qa-design"}
        or s.get("write_repos") or s.get("capture_repos") for s in stages
    ):
        raise ValueError("Only unchanged read-only document stage contracts can be restored")
    records = original["stages"]
    if len(records) not in {cursor, cursor + 1}:
        raise ValueError("Unexpected checkpoint stage history")
    for stage, record in zip(stages, records[:cursor]):
        if record["id"] != stage["stage_id"] or record["status"] != "accepted" or record.get("missing_outputs"):
            raise ValueError("Checkpoint requires complete accepted documents")
    if len(records) > cursor and (
        records[-1]["id"] != compiled["stages"][cursor]["stage_id"] or records[-1]["status"] != "failed"
    ):
        raise ValueError("Cannot replay accepted or running work")
    if model != config["model_name"] or effort != config["kwargs"].get("reasoning_effort", "high"):
        raise ValueError("Model and effort must match the checkpoint")
    for name in ("instruction.md", "business-conversations.md", "base-revisions.json"):
        if digest(prior / "workspace" / name) != digest(prepared / "workspace" / name):
            raise ValueError(f"Original business input or Base changed: {name}")
    events = _jsonl_rows(source / "workflow/events.jsonl")
    for stage, record in zip(stages, records):
        stage_id = stage["stage_id"]
        actual = regular_tree(source / "workflow/accepted" / stage_id)
        if not actual or actual != record["outputs"]:
            raise ValueError(f"Accepted artifact hashes changed: {stage_id}")
        required = {str(Path(path).relative_to(stage["writable_directory"])) for path in stage["outputs"].values()}
        if not required.issubset(actual):
            raise ValueError(f"Missing declared checkpoint output: {stage_id}")
        logs = source / "workflow/stages" / stage_id
        started = [e for e in events if e["event"] == "stage_started" and e["stage"] == stage_id]
        if not started or started[-1]["role_sha256"] != digest(logs / "role.md"):
            raise ValueError(f"Original role evidence changed: {stage_id}")
        if mode == "single":
            sid = original.get("principal_session")
            if not sid or record.get("session_id") != sid:
                raise ValueError("Original Single session changed")
            results = [r for r in _jsonl_rows(logs / "claude-code.jsonl") if r.get("type") == "result"]
            if not results or results[-1].get("is_error") or results[-1].get("stop_reason") != "end_turn":
                raise ValueError("Original Single stage did not end normally")
            regular_tree(logs / "sessions")
            native_role_evidence(logs / "sessions", sid, stage["role"], stage_id)
    return original


async def restore_checkpoint(source, original, controller, backend):
    source = Path(source)
    cursor = original["cursor"]
    for stage, record in zip(controller.compiled["stages"][:cursor], original["stages"][:cursor]):
        stage_id = stage["stage_id"]
        destination = controller.directory / "accepted" / stage_id
        shutil.copytree(source / "workflow/accepted" / stage_id, destination)
        await backend.reuse(stage, destination)
        await backend.seal(stage, record["outputs"])
        controller.freeze_baseline(stage, record["outputs"])
        controller.state["stages"].append({**copy.deepcopy(record), "recovered_from": str(source)})
        logs = controller.directory / "stages" / stage_id
        logs.mkdir(parents=True)
        for name in ("role.md", "instruction.md", "native-evidence.json"):
            shutil.copyfile(source / "workflow/stages" / stage_id / name, logs / name)
        if stage["role"] == "pm":
            controller.accepted_prd = destination / "prd.md"
    controller.state.update(cursor=cursor, recovery_source=str(source),
                            prior_cost_usd=original.get("cost_usd"), cost_scope="resumed stages only")
    single = controller.compiled["mode"] == "single"
    if single:
        controller.state["principal_session"] = original["principal_session"]
        last_stage = controller.compiled["stages"][cursor - 1]["stage_id"]
        await backend.environment.upload_dir(source / "workflow/stages" / last_stage / "sessions",
                                             "/logs/agent/sessions")
    else:
        # Record prior identities for lineage and to reject accidental reuse;
        # no previous chat files are copied into the new Flat environment.
        controller.state["principal_sessions"] = [
            {"stage_id": r["id"], "role": s["role"], "session_id": r["session_id"]}
            for s, r in zip(controller.compiled["stages"][:cursor], original["stages"])
            if r.get("session_id")
        ]
    await controller.check_baseline()
    controller.event("checkpoint_restored", restored_stages=cursor, replayed_stages=0,
                     restored_chat_sessions=int(single))
