"""Narrow continuation after the documented compaction-evidence false positive.

Preserves original files, session ID and absolute one-hour deadline. Never
replays PRD/design or accepts a model/API error as a completed stage.
"""
import hashlib
import json
from pathlib import Path
import shutil
import time

from runtime.workflow_agent import WorkflowClaudeCode, HarborBackend, native_role_evidence, _jsonl_rows
from runtime.workflow_controller import Controller, digest


class DocumentContinuation(WorkflowClaudeCode):
    def __init__(self, *args, recovery_source, **kwargs):
        self.source = Path(recovery_source)
        events = _jsonl_rows(self.source / "workflow/events.jsonl")
        self.absolute_deadline = next(e["time"] for e in events if e["event"] == "stage_execution_started") + 3600
        if time.time() >= self.absolute_deadline:
            raise TimeoutError("Original document rollout deadline has expired")
        super().__init__(*args, **kwargs)
        if [s["role"] for s in self.compiled["stages"]] != ["pm", "architect", "qa-design"]:
            raise ValueError("Continuation is limited to three document stages")
        original = json.loads((self.source / "workflow/state.json").read_text())
        if original.get("error") != "Native transcript does not contain the current stage-role activation":
            raise ValueError("Only the compaction role-evidence false positive can be continued")
        if len(original["stages"]) != 2 or original["stages"][0]["status"] != "accepted":
            raise ValueError("Expected completed PRD and interrupted technical design")
        original_config = json.loads((self.source / "config.json").read_text())
        if original_config["agent"]["model_name"] != self.model_name:
            raise ValueError("Cannot change model during continuation")

    async def run(self, instruction, environment, context):
        control = self.logs_dir.parent / "workflow"
        backend = HarborBackend(self.delegate, environment, context, self.prepared / "workspace")
        controller = Controller(self.compiled, self.prepared / "workspace", control, backend,
                                stop_after_stage="sprint1/test-design")
        original = json.loads((self.source / "workflow/state.json").read_text())
        sid = original["principal_session"]
        prior_prepared = Path(json.loads((self.source / "config.json").read_text())["agent"]["kwargs"]["prepared_path"])
        for name in ("instruction.md", "base-revisions.json"):
            if digest(prior_prepared / "workspace" / name) != digest(self.prepared / "workspace" / name):
                raise ValueError("Continuation inputs differ from original rollout")
        for index, stage in enumerate(self.compiled["stages"][:2]):
            source_logs = self.source / "workflow/stages" / stage["stage_id"]
            result = [r for r in _jsonl_rows(source_logs / "claude-code.jsonl") if r.get("type") == "result"]
            if not result or result[-1].get("stop_reason") != "end_turn" or result[-1].get("is_error"):
                raise ValueError("Original stage did not end normally")
            evidence = native_role_evidence(source_logs / "sessions", sid, stage["role"], stage["stage_id"])
            role_sha = digest(source_logs / "role.md")
            started = [e for e in _jsonl_rows(self.source / "workflow/events.jsonl")
                       if e["event"] == "stage_started" and e["stage"] == stage["stage_id"]]
            if started[-1]["role_sha256"] != role_sha:
                raise ValueError("Original role prompt has changed")
            source = (self.source / "workflow/accepted" / stage["stage_id"] if index == 0 else
                      self.source / "artifacts/logs/artifacts" / stage["stage_id"])
            destination = control / "accepted" / stage["stage_id"]
            destination.mkdir(parents=True)
            for path in stage["outputs"].values():
                relative = Path(path).relative_to(stage["writable_directory"])
                artifact = source / relative
                if not artifact.is_file() or artifact.is_symlink():
                    raise ValueError("Original document is missing or redirected")
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(artifact, target)
                if index == 0 and original["stages"][0]["outputs"].get(str(relative)) != digest(target):
                    raise ValueError("Frozen PRD changed")
            hashes = {str(p.relative_to(destination)): digest(p) for p in destination.rglob("*") if p.is_file()}
            await backend.reuse(stage, destination)
            await backend.seal(stage, hashes)
            controller.freeze_baseline(stage, hashes)
            record = {**original["stages"][index], "status": "accepted", "session_id": sid,
                      "outputs": hashes, "recovered_from": str(self.source), "missing_outputs": []}
            controller.state["stages"].append(record)
            target_logs = control / "stages" / stage["stage_id"]
            target_logs.mkdir(parents=True)
            for name in ("role.md", "instruction.md", "claude-code.jsonl", "native-evidence.json"):
                if (source_logs / name).is_file():
                    shutil.copyfile(source_logs / name, target_logs / name)
            primary = source_logs / "sessions/projects/-workspace" / (sid + ".jsonl")
            target_primary = target_logs / "sessions/projects/-workspace" / primary.name
            target_primary.parent.mkdir(parents=True)
            shutil.copyfile(primary, target_primary)
            evidence.update(role_prompt_sha256=role_sha, recovery_reason="ignore SDK compaction summary as role activation")
            (target_logs / "recovery-evidence.json").write_text(json.dumps(evidence, indent=2))
        controller.accepted_prd = control / "accepted/sprint1/prd/prd.md"
        controller.state.update(cursor=2, principal_session=sid, recovery_source=str(self.source),
                                original_deadline_epoch=self.absolute_deadline)
        controller.event("document_checkpoint_restored", session_id=sid)
        sessions = control / "stages/sprint1/tech-design/sessions"
        await environment.upload_dir(sessions, "/logs/agent/sessions")
        remaining = self.absolute_deadline - time.time()
        if remaining <= 0:
            raise TimeoutError("Original document rollout deadline has expired")
        self.delegate.execution_deadline = time.monotonic() + remaining
        self.delegate.max_runtime_sec = remaining
        try:
            await controller.run()
        except TimeoutError:
            controller.state["status"] = "timed_out"
            controller.event("original_deadline_exhausted")
            raise
        finally:
            await environment.download_file("/logs/request-evidence.jsonl", control / "request-evidence.jsonl")
