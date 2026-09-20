"""Native-to-ATIF export and Harbor post-run integration; no model calls."""
import json
import logging
from pathlib import Path
import tempfile
import unittest

from harbor.models.agent.context import AgentContext
from harbor.models.trajectories.trajectory import Trajectory
from runtime.trajectory import export_trajectory
from runtime.workflow_agent import WorkflowCodex


class TrajectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.trial = Path(self.temp.name)
        self.logs = self.trial / "agent"
        sessions = self.logs / "sessions/2026/09/20"
        sessions.mkdir(parents=True)
        workflow = self.trial / "workflow"
        workflow.mkdir()
        (workflow / "state.json").write_text(json.dumps({"principal_session": "main", "status": "failed"}))
        rows = [{"type": "session_meta", "payload": {"id": "main", "cli_version": "0.154.0"}}]
        for index, role in enumerate(("pm", "architect")):
            rows.extend([
                {"type": "response_item", "payload": {"type": "message", "role": "developer",
                 "content": [{"type": "input_text", "text": f"SDLC_STAGE_ROLE: {role}"}]}},
                {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec",
                 "call_id": f"call-{index}", "input": f"read {role}"}},
                {"type": "response_item", "payload": {"type": "custom_tool_call_output",
                 "call_id": f"call-{index}", "output": f"{role} result"}},
            ])
        self.source = sessions / "z-main.jsonl"
        self.source.write_text("\n".join(json.dumps(row) for row in rows))
        (sessions / "a-child.jsonl").write_text(json.dumps({
            "type": "session_meta", "payload": {"id": "child", "source": {"subagent": {}}}}) + '\n{"partial":')

    def test_export_selects_principal_and_preserves_roles_calls_and_raw_bytes(self):
        original = self.source.read_bytes()
        exported = export_trajectory(self.logs, "gpt-6-astra")
        parsed = Trajectory.model_validate_json((self.logs / "trajectory.json").read_text())
        self.assertEqual(parsed.session_id, "main")
        self.assertEqual(len(parsed.steps), len(exported.steps))
        self.assertEqual(sum(len(s.tool_calls or []) for s in parsed.steps), 2)
        self.assertTrue(any("architect" in str(s.message) for s in parsed.steps))
        self.assertTrue(any("architect result" in str(s.observation) for s in parsed.steps))
        self.assertEqual(original, self.source.read_bytes())

    def test_failed_run_post_hook_exports_but_smoke_does_not(self):
        agent = object.__new__(WorkflowCodex)
        agent.logs_dir, agent.model_name = self.logs, "gpt-6-astra"
        agent.logger = logging.getLogger(__name__)
        agent.smoke = True
        agent.populate_context_post_run(AgentContext())
        self.assertFalse((self.logs / "trajectory.json").exists())
        agent.smoke = False
        agent.populate_context_post_run(AgentContext())
        self.assertTrue((self.logs / "trajectory.json").is_file())
        self.assertTrue(agent.SUPPORTS_ATIF)

    def test_missing_principal_never_exports_child_as_main(self):
        self.source.unlink()
        with self.assertRaisesRegex(ValueError, "Principal session log missing"):
            export_trajectory(self.logs)
        self.assertFalse((self.logs / "trajectory.json").exists())


if __name__ == "__main__":
    unittest.main()
