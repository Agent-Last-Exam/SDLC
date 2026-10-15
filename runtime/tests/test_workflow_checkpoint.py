import copy
import os
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from runtime.workflow_checkpoint import validate_checkpoint, restore_checkpoint
from runtime.workflow_controller import digest


class CheckpointTests(unittest.IsolatedAsyncioTestCase):
    def test_image_hardlinks_materialized_without_changing_content(self):
        from runtime.workspace_link_normalization import materialize_hardlinks
        from runtime.workspace_snapshot import inventory
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "file").write_text("same source bytes")
            os.link(root / "file", root / "alias")
            with self.assertRaisesRegex(ValueError, "hard link"):
                inventory(root)
            self.assertGreater(materialize_hardlinks(root), 0)
            self.assertEqual((root / "file").read_text(), (root / "alias").read_text())
            self.assertNotEqual((root / "file").stat().st_ino, (root / "alias").stat().st_ino)
            inventory(root)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source, self.prepared, self.prior = root / "source", root / "new", root / "old"
        self.compiled = {"mode": "flat", "stages": [
            {"stage_id": "sprint1/" + name, "role": role, "inputs": {},
             "outputs": {"artifact:" + name: "/workspace/artifacts/sprint1/" + name + "/" + file},
             "writable_directory": "/workspace/artifacts/sprint1/" + name}
            for name, role, file in [("prd", "pm", "prd.md"),
                                     ("tech-design", "architect", "design.md"),
                                     ("test-design", "qa-design", "test-cases.v1.csv"),
                                     ("development", "developer", "test-handoff.md")]
        ]}
        self.compiled["stages"][3].update(write_repos=True, capture_repos=True)
        self.compiled["stages"][3]["inputs"] = {"artifact:sprint1/test-design/test_cases": "cases"}
        for folder in (self.prepared, self.prior):
            (folder / "workspace").mkdir(parents=True)
            for name in ("instruction.md", "business-conversations.md", "base-revisions.json"):
                (folder / "workspace" / name).write_text(name)
        (self.prior / "resolved-workflow.json").write_text(json.dumps(self.compiled))
        self.source.mkdir()
        (self.source / "config.json").write_text(json.dumps({"agent": {
            "model_name": "deepseek", "kwargs": {"prepared_path": str(self.prior),
                                                     "reasoning_effort": "high"}}}))
        self.original = {"mode": "flat", "cursor": 3, "status": "interrupted", "stages": []}
        events = []
        for stage in self.compiled["stages"][:3]:
            sid = stage["stage_id"]
            folder = self.source / "workflow/accepted" / sid
            folder.mkdir(parents=True)
            file = Path(next(iter(stage["outputs"].values()))).name
            (folder / file).write_text("sealed " + sid)
            logs = self.source / "workflow/stages" / sid
            logs.mkdir(parents=True)
            for name in ("role.md", "instruction.md", "native-evidence.json"):
                (logs / name).write_text("evidence")
            events.append({"event": "stage_started", "stage": sid,
                           "role_sha256": digest(logs / "role.md")})
            self.original["stages"].append({"id": sid, "status": "accepted",
                                            "outputs": {file: digest(folder / file)}, "session_id": "old-" + stage["role"]})
        self.original["stages"].append({"id": "sprint1/development", "status": "failed"})
        (self.source / "workflow/events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events))
        self.save_state()

    def save_state(self):
        (self.source / "workflow/state.json").write_text(json.dumps(self.original))

    def validate(self, compiled=None):
        return validate_checkpoint(self.source, self.prepared, compiled or self.compiled,
                                   "deepseek", "high")

    def test_interrupted_flat_documents_can_be_reused(self):
        self.assertEqual(self.validate(), self.original)

    def test_tampered_artifact_rejected(self):
        (self.source / "workflow/accepted/sprint1/prd/prd.md").write_text("changed")
        with self.assertRaisesRegex(ValueError, "hashes changed"):
            self.validate()

    def test_changed_business_input_rejected(self):
        (self.prepared / "workspace/instruction.md").write_text("different task")
        with self.assertRaisesRegex(ValueError, "input or Base changed"):
            self.validate()

    def test_accepted_coding_cannot_be_replayed(self):
        self.original["stages"][3]["status"] = "accepted"
        self.save_state()
        with self.assertRaisesRegex(ValueError, "replay accepted or running work"):
            self.validate()

    def test_single_and_changed_contract_rejected(self):
        compiled = copy.deepcopy(self.compiled)
        compiled["mode"] = "single"
        with self.assertRaisesRegex(ValueError, "same Single or Flat mode"):
            self.validate(compiled)
        compiled = copy.deepcopy(self.compiled)
        compiled["stages"][0]["inputs"]["new"] = "input"
        with self.assertRaisesRegex(ValueError, "document stage contracts"):
            self.validate(compiled)

    async def test_restore_only_documents_and_skip_all_old_chat(self):
        backend = SimpleNamespace(reuse=AsyncMock(), seal=AsyncMock())
        controller = SimpleNamespace(compiled=self.compiled, directory=self.prepared / "control",
                                     state={"stages": []}, freeze_baseline=Mock(),
                                     check_baseline=AsyncMock(), event=Mock())
        await restore_checkpoint(self.source, self.original, controller, backend)
        self.assertEqual(controller.state["cursor"], 3)
        self.assertEqual(len(controller.state["stages"]), 3)
        self.assertNotIn("principal_session", controller.state)
        self.assertEqual(len(controller.state["principal_sessions"]), 3)
        self.assertEqual(backend.reuse.await_count, 3)
        self.assertFalse((controller.directory / "accepted/sprint1/development").exists())
        controller.event.assert_called_once_with("checkpoint_restored", restored_stages=3,
                                                 replayed_stages=0, restored_chat_sessions=0)

    def test_model_effort_and_base_must_match(self):
        with self.assertRaisesRegex(ValueError, "Model and effort"):
            validate_checkpoint(self.source, self.prepared, self.compiled, "other", "high")
        (self.prepared / "workspace/base-revisions.json").write_text("different")
        with self.assertRaisesRegex(ValueError, "Base changed"):
            self.validate()

    def test_symlinked_accepted_directory_is_rejected(self):
        folder = self.source / "workflow/accepted/sprint1/prd"
        original = folder.with_name("original")
        folder.rename(original)
        folder.symlink_to(original, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "redirected"):
            self.validate()

    def test_accepted_development_and_synthetic_checkpoints_are_rejected(self):
        self.original.update(synthetic=True)
        self.save_state()
        with self.assertRaisesRegex(ValueError, "Synthetic"):
            self.validate()
        self.original.pop("synthetic")
        self.original.update(cursor=4)
        self.save_state()
        with self.assertRaisesRegex(ValueError, "remaining work"):
            self.validate()

    def test_missing_declared_output_cannot_hide_behind_an_inventory(self):
        folder = self.source / "workflow/accepted/sprint1/prd"
        (folder / "prd.md").rename(folder / "other.md")
        self.original["stages"][0]["outputs"] = {"other.md": digest(folder / "other.md")}
        self.save_state()
        with self.assertRaisesRegex(ValueError, "declared checkpoint output"):
            self.validate()

    async def test_single_preserves_exact_native_session(self):
        self.compiled["mode"] = "single"
        (self.prior / "resolved-workflow.json").write_text(json.dumps(self.compiled))
        self.original.update(mode="single", principal_session="principal")
        for stage, record in zip(self.compiled["stages"][:3], self.original["stages"]):
            record["session_id"] = "principal"
            logs = self.source / "workflow/stages" / stage["stage_id"]
            (logs / "claude-code.jsonl").write_text(json.dumps({"type": "result", "stop_reason": "end_turn"}) + "\n")
            (logs / "sessions").mkdir()
            (logs / "sessions/principal.jsonl").write_text(json.dumps({
                "type": "user", "sessionId": "principal", "message": {"content":
                    f"SDLC_STAGE_ROLE: {stage['role']}\nSDLC_STAGE_ID: {stage['stage_id']}"}}) + "\n")
        self.save_state()
        self.validate()
        backend = SimpleNamespace(reuse=AsyncMock(), seal=AsyncMock(),
                                  environment=SimpleNamespace(upload_dir=AsyncMock()))
        controller = SimpleNamespace(compiled=self.compiled, directory=self.prepared / "control",
                                     state={"stages": []}, freeze_baseline=Mock(),
                                     check_baseline=AsyncMock(), event=Mock())
        await restore_checkpoint(self.source, self.original, controller, backend)
        self.assertEqual(controller.state["principal_session"], "principal")
        backend.environment.upload_dir.assert_awaited_once_with(
            self.source / "workflow/stages/sprint1/test-design/sessions", "/logs/agent/sessions")
        self.original["stages"][0]["session_id"] = "changed"
        self.save_state()
        with self.assertRaisesRegex(ValueError, "Single session changed"):
            self.validate()
