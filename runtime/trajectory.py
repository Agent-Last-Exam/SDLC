"""Export the principal Codex session for Harbor Viewer, without model calls."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from harbor.agents.installed.codex import Codex
from harbor.utils.trajectory_utils import format_trajectory_json


def export_trajectory(logs_dir, model_name=None):
    logs_dir = Path(logs_dir)
    state_path = logs_dir.parent / "workflow/state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    session_id = state.get("principal_session")
    if not session_id and state.get("role_probe") and state.get("records"):
        session_id = state["records"][-1]["session_id"]
    candidates = []
    for path in sorted((logs_dir / "sessions").rglob("*.jsonl")):
        with path.open() as stream:
            try:
                metadata = json.loads(stream.readline())
            except ValueError:
                continue
        if metadata.get("type") != "session_meta":
            continue
        payload = metadata.get("payload", {})
        if session_id:
            if payload.get("id") == session_id:
                candidates.append(path)
        elif not isinstance(payload.get("source"), dict) or "subagent" not in payload["source"]:
            candidates.append(path)
    if not candidates:
        if session_id:
            raise ValueError(f"Principal session log missing: {session_id}")
        return None  # No model turn started, or a synthetic run.
    if len(candidates) != 1:
        raise ValueError("Cannot identify a single principal session for trajectory export")

    # Harbor's converter picks the first JSONL in a directory. Isolate the
    # selected principal so child sessions cannot replace or mix into it.
    converter = Codex(logs_dir=logs_dir, model_name=model_name)
    with tempfile.TemporaryDirectory() as directory:
        shutil.copyfile(candidates[0], Path(directory) / "session.jsonl")
        trajectory = converter._convert_events_to_trajectory(Path(directory))
    if trajectory is None:
        raise ValueError("Harbor could not convert the principal session")
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
