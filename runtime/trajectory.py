"""Export Single, Flat or Hierarchical Claude sessions for Harbor Viewer."""
import argparse
import json
from pathlib import Path
import re
import shutil
import tempfile

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.models.trajectories import FinalMetrics, Trajectory
from harbor.utils.trajectory_utils import format_trajectory_json

from runtime.agent_cost import stream_cost


def session_metadata(path):
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                session_id = event.get("sessionId")
                if isinstance(session_id, str) and session_id:
                    return {"id": session_id}
    except OSError:
        pass
    return None


def convert_session(converter, source, label, total_cost_usd=None):
    # Isolate the selected principal and its own Claude subagent directory so
    # another Flat Stage cannot replace or mix into the conversion.
    with tempfile.TemporaryDirectory() as directory:
        isolated = Path(directory)
        shutil.copyfile(source, isolated / "session.jsonl")
        sidechains = source.with_suffix("") / "subagents"
        if sidechains.is_dir():
            shutil.copytree(sidechains, isolated / "session/subagents")
        if total_cost_usd is not None:
            (isolated / "claude-code.txt").write_text(
                json.dumps({"type": "result", "total_cost_usd": total_cost_usd}) + "\n"
            )
        trajectory = converter._convert_events_to_trajectory(
            isolated, logs_dir=isolated
        )
    if trajectory is None:
        raise ValueError(f"Harbor could not convert {label} session")
    return trajectory


def locate_session(directory, session_id):
    matches = [
        path for path in sorted(directory.rglob("*.jsonl"))
        if "subagents" not in path.parts
        if (session_metadata(path) or {}).get("id") == session_id
    ]
    if not matches:
        raise ValueError(f"Principal session log missing: {session_id}")
    if len(matches) != 1:
        raise ValueError(f"Principal session log is ambiguous: {session_id}")
    return matches[0]


def annotate(trajectory, stage_id, role):
    for step in trajectory.steps:
        step.extra = {
            **(step.extra or {}),
            "stage_id": stage_id,
            "role": role,
            "session_id": trajectory.session_id,
        }


def aggregate_metrics(trajectories, principal_steps, subagent_steps):
    available = [
        trajectory.final_metrics for trajectory in trajectories
        if trajectory.final_metrics is not None
    ]

    def sum_known(field):
        values = [getattr(metric, field) for metric in available]
        values = [value for value in values if value is not None]
        return sum(values) if values else None

    costs = [metric.total_cost_usd for metric in available]
    complete_cost = (
        len(available) == len(trajectories)
        and all(value is not None for value in costs)
    )
    return FinalMetrics(
        total_prompt_tokens=sum_known("total_prompt_tokens"),
        total_completion_tokens=sum_known("total_completion_tokens"),
        total_cached_tokens=sum_known("total_cached_tokens"),
        total_cost_usd=sum(costs) if complete_cost else None,
        total_steps=principal_steps,
        extra={
            "trajectory_count": len(trajectories),
            "trajectories_with_usage": len(available),
            "principal_step_count": principal_steps,
            "subagent_step_count": subagent_steps,
        },
    )


def export_flat_trajectory(logs_dir, state, model_name):
    workflow = logs_dir.parent / "workflow"
    descriptors = state.get("principal_sessions") or [
        {"stage_id": stage["id"], "role": stage["role"],
         "session_id": stage["session_id"]}
        for stage in state.get("stages", []) if stage.get("session_id")
    ]
    if not descriptors:
        return None
    converter = ClaudeCode(logs_dir=logs_dir, model_name=model_name)
    principals = []
    for descriptor in descriptors:
        stage_id = descriptor["stage_id"]
        role = descriptor["role"]
        session_id = descriptor["session_id"]
        sessions = workflow / "stages" / stage_id / "sessions"
        cost = stream_cost([workflow / "stages" / stage_id / "claude-code.jsonl"])
        principal = convert_session(
            converter, locate_session(sessions, session_id), f"principal {session_id}", cost
        )
        annotate(principal, stage_id, role)
        principals.append(principal)

    steps = []
    for principal in principals:
        for step in principal.steps:
            step.step_id = len(steps) + 1
            steps.append(step)
    subagent_steps = sum(
        1 for principal in principals for step in principal.steps
        if (step.extra or {}).get("is_sidechain")
    )
    return Trajectory(
        schema_version="ATIF-v1.8",
        session_id="flat-workflow",
        trajectory_id="flat-workflow",
        agent=principals[0].agent,
        steps=steps,
        notes=(
            "Flat principal steps are ordered by Stage. Token and cost totals include "
            "all Claude main-chain and sidechain steps. Sidechains retain their native "
            "extra.is_sidechain marker and Agent metadata. Missing usage is not invented."
        ),
        final_metrics=aggregate_metrics(
            principals, len(steps), subagent_steps
        ),
        extra={"mode": "flat", "principal_sessions": descriptors},
    )


def export_single_trajectory(logs_dir, state, model_name):
    session_id = state.get("principal_session")
    if not session_id and state.get("role_probe") and state.get("records"):
        session_id = state["records"][-1]["session_id"]
    candidates = []
    for path in sorted((logs_dir / "sessions").rglob("*.jsonl")):
        if "subagents" in path.parts:
            continue
        payload = session_metadata(path)
        if payload is None:
            continue
        if session_id:
            if payload.get("id") == session_id:
                candidates.append(path)
        elif "subagents" not in path.parts:
            candidates.append(path)
    if not candidates:
        if session_id:
            raise ValueError(f"Principal session log missing: {session_id}")
        return None
    if len(candidates) != 1:
        raise ValueError("Cannot identify a single principal session for trajectory export")
    converter = ClaudeCode(logs_dir=logs_dir, model_name=model_name)
    stage_streams = sorted(
        (logs_dir.parent / "workflow/stages").glob("**/claude-code.jsonl")
    )
    cost = stream_cost(stage_streams or [logs_dir / "claude-code.txt"])
    return convert_session(converter, candidates[0], "principal", cost)


def _latest_team_session(workflow, directories, session_id):
    for directory in reversed(directories):
        sessions = workflow / directory / "sessions"
        try:
            return locate_session(sessions, session_id)
        except ValueError as exc:
            if "missing" not in str(exc):
                raise
    raise ValueError(f"Principal session log missing: {session_id}")


def _annotate_member(trajectory, member, assignments, revisions):
    task_map = {task["id"]: task for task in assignments}
    revision_map = {
        revision["task_id"]: revision["id"] for revision in revisions
        if revision.get("task_id") in task_map
    }
    active = None
    marker = re.compile(r"SDLC_TEAM_TASK:\s*([a-z][a-z0-9_-]*)")
    for step in trajectory.steps:
        match = marker.search(str(step.message or ""))
        if match and match.group(1) in task_map:
            active = task_map[match.group(1)]
        extra = {
            "team_member_id": member["id"],
            "role": member["role"],
            "session_id": trajectory.session_id,
        }
        if active:
            extra.update(
                task_id=active["id"],
                stage_id=active["stage_id"],
                revision_id=revision_map.get(active["id"]),
            )
        step.extra = {**(step.extra or {}), **extra}
    trajectory.extra = {
        **(trajectory.extra or {}),
        "member_id": member["id"],
        "role": member["role"],
        "assignments": [task["id"] for task in assignments],
        "stages": sorted({task["stage_id"] for task in assignments}),
        "revisions": [revision_map[task["id"]] for task in assignments if task["id"] in revision_map],
    }


def export_hierarchical_trajectory(logs_dir, state, model_name):
    workflow = logs_dir.parent / "workflow"
    lead_session = state.get("lead_session")
    if not lead_session:
        return None
    lead_dirs = sorted(
        str(path.relative_to(workflow)) for path in (workflow / "lead").glob("turn-*")
        if path.is_dir()
    )
    lead_source = _latest_team_session(workflow, lead_dirs, lead_session)
    converter = ClaudeCode(logs_dir=logs_dir, model_name=model_name)
    lead_cost = stream_cost([
        workflow / directory / "claude-code.jsonl" for directory in lead_dirs
    ])
    lead = convert_session(converter, lead_source, "hierarchical Lead", lead_cost)
    for step in lead.steps:
        step.extra = {
            **(step.extra or {}),
            "team_role": "lead",
            "session_id": lead_session,
        }

    assignments = state.get("assignments", {})
    revisions = list(state.get("revisions", {}).values())
    children = []
    for member in state.get("members", {}).values():
        session_id = member.get("session_id")
        member_tasks = [assignments[task_id] for task_id in member.get("assignments", [])]
        executed = [task for task in member_tasks if task["status"] != "queued"]
        if not session_id or not executed:
            continue
        directories = ["assignments/" + task["id"] for task in executed]
        source = _latest_team_session(workflow, directories, session_id)
        cost = stream_cost([
            workflow / directory / "claude-code.jsonl" for directory in directories
        ])
        child = convert_session(
            converter, source, f"team member {member['id']}", cost
        )
        child.trajectory_id = "team-member-" + member["id"]
        _annotate_member(child, member, member_tasks, revisions)
        children.append(child)
    lead.trajectory_id = "hierarchical-lead"
    lead.subagent_trajectories = children or None
    all_trajectories = [lead, *children]
    lead.final_metrics = aggregate_metrics(
        all_trajectories,
        len(lead.steps),
        sum(len(child.steps) for child in children),
    )
    lead.notes = (
        "Hierarchical Lead is the root trajectory. Persistent member sessions are "
        "embedded as subagent_trajectories; task, Stage and immutable revision "
        "metadata is retained. Usage is aggregated without inventing missing values."
    )
    lead.extra = {
        **(lead.extra or {}),
        "mode": "hierarchical",
        "lead_session": lead_session,
        "member_count": len(state.get("members", {})),
        "assignment_count": len(assignments),
        "revision_count": len(revisions),
        "peak_concurrency": state.get("counters", {}).get("peak_concurrency"),
    }
    return lead


def export_trajectory(logs_dir, model_name=None):
    logs_dir = Path(logs_dir)
    state_path = logs_dir.parent / "workflow/state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state.get("mode") == "flat":
        trajectory = export_flat_trajectory(logs_dir, state, model_name)
    elif state.get("mode") == "hierarchical":
        trajectory = export_hierarchical_trajectory(logs_dir, state, model_name)
    else:
        trajectory = export_single_trajectory(logs_dir, state, model_name)
    if trajectory is None:
        return None  # No model turn started, or a synthetic run.
    target = logs_dir / "trajectory.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(format_trajectory_json(trajectory.to_json_dict()))
    temporary.replace(target)
    return trajectory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial", type=Path, help="Existing Harbor trial directory")
    args = parser.parse_args()
    trajectory = export_trajectory(args.trial / "agent")
    if trajectory is None:
        parser.error("No native session found; nothing to export")
    print(f"{args.trial / 'agent/trajectory.json'} ({len(trajectory.steps)} steps)")


if __name__ == "__main__":
    main()
