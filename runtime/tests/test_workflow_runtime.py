import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from runtime.workflow_agent import (
    TeamClaudeCode, exact_resume_command, native_role_evidence, stream_session_ids,
)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_native_evidence_requires_latest_role_on_same_session(self):
        sessions = self.root / "sessions"
        sessions.mkdir()
        rows = [
            {"type": "user", "sessionId": "primary",
             "message": {"role": "user", "content": "SDLC_STAGE_ROLE: pm"}},
            {"type": "user", "sessionId": "primary",
             "message": {"role": "user", "content": "SDLC_STAGE_ROLE: architect"}},
        ]
        (sessions / "primary.jsonl").write_text("\n".join(json.dumps(x) for x in rows))
        evidence = native_role_evidence(sessions, "primary", "architect")
        self.assertEqual(evidence["role_activations_recorded"], 2)
        with self.assertRaisesRegex(RuntimeError, "current stage-role"):
            native_role_evidence(sessions, "primary", "pm")
        with self.assertRaisesRegex(RuntimeError, "missing"):
            native_role_evidence(sessions, "other", "architect")

    def test_stream_session_id_supports_claude_init_and_native_events(self):
        stream = self.root / "claude-code.jsonl"
        stream.write_text("\n".join(map(json.dumps, [
            {"type": "system", "subtype": "init", "session_id": "primary"},
            {"type": "assistant", "sessionId": "primary"},
        ])))
        self.assertEqual(stream_session_ids(stream), {"primary"})

    def test_single_resume_targets_the_recorded_session_exactly(self):
        command = "claude --verbose --continue --print"
        resumed = exact_resume_command(command, "session-123")
        self.assertEqual(resumed, "claude --verbose --resume session-123 --print")
        self.assertNotIn("--continue", resumed)
        with self.assertRaisesRegex(RuntimeError, "continuation flag"):
            exact_resume_command("claude --verbose --print", "session-123")

    def test_partial_child_log_does_not_hide_principal_evidence(self):
        d = self.root / "sessions"
        d.mkdir()
        child = d / "primary/subagents"
        child.mkdir(parents=True)
        (child / "agent-child.jsonl").write_text(
            json.dumps({"type": "assistant", "sessionId": "primary",
                        "isSidechain": True}) + '\n{"partial":'
        )
        rows = [{"type": "user", "sessionId": "primary",
                 "message": {"role": "user", "content": "SDLC_STAGE_ROLE: architect"}}]
        (d / "primary.jsonl").write_text("\n".join(json.dumps(x) for x in rows))
        self.assertTrue(native_role_evidence(d, "primary", "architect")["native_user_activation_verified"])


class TeamRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_team_agent_uses_fixed_identity_not_shared_default_user(self):
        agent = object.__new__(TeamClaudeCode)
        agent.execution_user = "team2201"
        agent.execution_tmpdir = "/workspace/team/assignments/task/scratch"
        agent.resume_session_id = None
        agent._exec = AsyncMock(return_value="ok")
        environment = type("Environment", (), {"default_user": "wrong-shared-user"})()
        result = await agent.exec_as_agent(environment, "true", env={"X": "1"})
        self.assertEqual(result, "ok")
        agent._exec.assert_awaited_once_with(
            environment, "true", user="team2201",
            env={"X": "1", "HOME": "/home/team2201",
                 "TMPDIR": "/workspace/team/assignments/task/scratch"},
        )


if __name__ == "__main__":
    unittest.main()
