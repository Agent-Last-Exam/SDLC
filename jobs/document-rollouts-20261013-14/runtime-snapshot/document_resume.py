"""Resume only the explicitly interrupted Opus PRD document run."""
import json
from pathlib import Path
from runtime.workflow_agent import WorkflowClaudeCode, HarborBackend, native_role_evidence, stream_session_ids, _jsonl_rows
from runtime.workflow_controller import Controller, digest

class ResumeBackend(HarborBackend):
    async def execute(self, stage, prompt, instruction, resume_session, stage_dir):
        if self.stage_index == 0:
            instruction += "\n此前客户端因用户调整运行时限被人工中断。沿用本会话已有分析继续完成当前 PRD；不要从头重复已完成的阅读和分析。"
        return await super().execute(stage, prompt, instruction, resume_session, stage_dir)

    async def activate(self, stage, resume_session):
        await super().activate(stage, resume_session)
        if self.stage_index == 0:
            partial = self.source / "workflow/stages/sprint1/prd/partial-artifacts"
            if partial.exists():
                await self.environment.upload_dir(partial, stage["writable_directory"])
                await self.root(f"chown -R {self.uid}:{self.uid} {stage['writable_directory']}")

class InterruptedDocumentResume(WorkflowClaudeCode):
    def __init__(self, *args, recovery_source, **kwargs):
        self.source = Path(recovery_source)
        marker = json.loads((self.source / "workflow/user-runtime-change.json").read_text())
        if marker.get("reason") != "User requested removal of 3600-second runtime limit":
            raise ValueError("Missing explicit user runtime-change checkpoint")
        super().__init__(*args, **kwargs)
        if self.delegate.max_runtime_sec is not None:
            raise ValueError("This continuation removes the model runtime limit")
        if self.stop_after_stage != "sprint1/test-design" or [s["role"] for s in self.compiled["stages"]] != ["pm", "architect", "qa-design"]:
            raise ValueError("Resume requires three document stages")
        if any(s.get("write_repos") for s in self.compiled["stages"]):
            raise ValueError("Document resume cannot write code")
        self.original = json.loads((self.source / "workflow/state.json").read_text())
        if len(self.original["stages"]) != 1 or self.original["cursor"] != 0 or self.original["status"] != "failed":
            raise ValueError("Expected deliberately interrupted first PRD stage")
        config = json.loads((self.source / "config.json").read_text())
        if config["agent"]["model_name"] != self.model_name:
            raise ValueError("Cannot change model during resume")
        previous = Path(config["agent"]["kwargs"]["prepared_path"])
        if json.loads((previous / "resolved-workflow.json").read_text()) != self.compiled:
            raise ValueError("Workflow changed during resume")
        for name in ("instruction.md", "base-revisions.json"):
            if digest(previous / "workspace" / name) != digest(self.prepared / "workspace" / name):
                raise ValueError("Original task or baseline changed")
        self.checkpoint = self.source / "workflow/stages/sprint1/prd"
        ids = stream_session_ids(self.checkpoint / "claude-code.jsonl")
        if len(ids) != 1:
            raise ValueError("Interrupted checkpoint needs one native session")
        self.sid = ids.pop()
        native_role_evidence(self.checkpoint / "sessions", self.sid, "pm", "sprint1/prd")
        started = [e for e in _jsonl_rows(self.source / "workflow/events.jsonl") if e["event"] == "stage_started"]
        if digest(self.checkpoint / "role.md") != started[0]["role_sha256"]:
            raise ValueError("Interrupted role prompt changed")

    async def run(self, instruction, environment, context):
        control = self.logs_dir.parent / "workflow"
        backend = ResumeBackend(self.delegate, environment, context, self.prepared / "workspace")
        backend.source = self.source
        controller = Controller(self.compiled, self.prepared / "workspace", control, backend,
                                stop_after_stage="sprint1/test-design")
        controller.state.update(principal_session=self.sid, recovery_source=str(self.source),
                                runtime_limit_removed=True, intervention="User runtime-limit change after manual interruption")
        await environment.upload_dir(self.checkpoint / "sessions", "/logs/agent/sessions")
        controller.event("interrupted_document_session_restored", session_id=self.sid)
        try:
            await controller.run()
        finally:
            await environment.download_file("/logs/request-evidence.jsonl", control / "request-evidence.jsonl")
