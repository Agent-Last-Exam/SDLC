import json
from pathlib import Path
import tempfile
import unittest

from runtime.workflow_agent import native_role_evidence
from runtime.codex_app_turn import app_server_command


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_native_evidence_requires_latest_role_on_same_session(self):
        sessions = self.root / "sessions"
        sessions.mkdir()
        rows = [
            {"type": "session_meta", "payload": {"id": "primary"}},
            {"type": "response_item", "payload": {"role": "developer", "content": "SDLC_STAGE_ROLE: pm"}},
            {"type": "response_item", "payload": {"role": "developer", "content": "SDLC_STAGE_ROLE: architect"}},
        ]
        (sessions / "primary.jsonl").write_text("\n".join(json.dumps(x) for x in rows))
        evidence = native_role_evidence(sessions, "primary", "architect")
        self.assertEqual(evidence["role_activations_recorded"], 2)
        with self.assertRaisesRegex(RuntimeError, "current developer-role"):
            native_role_evidence(sessions, "primary", "pm")
        with self.assertRaisesRegex(RuntimeError, "missing"):
            native_role_evidence(sessions, "other", "architect")

    def test_native_subagent_flag_matches_execution_policy(self):
        self.assertIn("features.multi_agent=false", app_server_command(False))
        self.assertIn("features.multi_agent=true", app_server_command(True))

    def test_partial_child_log_does_not_hide_principal_evidence(self):
        d = self.root / "sessions"
        d.mkdir()
        (d / "child.jsonl").write_text(json.dumps({"type": "session_meta", "payload": {"id": "child"}}) + '\n{"partial":')
        rows = [{"type": "session_meta", "payload": {"id": "primary"}},
                {"type": "response_item", "payload": {"role": "developer", "content": "SDLC_STAGE_ROLE: architect"}}]
        (d / "primary.jsonl").write_text("\n".join(json.dumps(x) for x in rows))
        self.assertTrue(native_role_evidence(d, "primary", "architect")["native_developer_message_verified"])


if __name__ == "__main__":
    unittest.main()
