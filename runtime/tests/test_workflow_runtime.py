import json
import asyncio
import shlex
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from runtime.workflow_agent import (
    TeamClaudeCode, StageClaudeCode, HarborBackend, exact_resume_command, native_role_evidence, stream_session_ids,
)
from runtime.request_relay import apply_profile, cache_count


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

    def test_compaction_summary_cannot_replace_real_role_activation(self):
        sessions = self.root / "sessions"
        sessions.mkdir()
        rows = [
            {"type": "user", "sessionId": "primary", "message": {"content": "SDLC_STAGE_ROLE: architect\nSDLC_STAGE_ID: sprint1/tech-design"}},
            {"type": "user", "sessionId": "primary", "isCompactSummary": True,
             "message": {"content": "Previously SDLC_STAGE_ROLE: pm, then SDLC_STAGE_ROLE: architect, SDLC_STAGE_ID: sprint1/tech-design)."}},
        ]
        (sessions / "primary.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
        evidence = native_role_evidence(sessions, "primary", "architect", "sprint1/tech-design")
        self.assertEqual(evidence["role_activations_recorded"], 1)

    def test_stream_session_id_supports_claude_init_and_native_events(self):
        stream = self.root / "claude-code.jsonl"
        stream.write_text("\n".join(map(json.dumps, [
            {"type": "system", "subtype": "init", "session_id": "primary"},
            {"type": "assistant", "sessionId": "primary"},
        ])))
        self.assertEqual(stream_session_ids(stream), {"primary"})

    def test_disabled_subagents_preserve_existing_tool_restrictions(self):
        prompt = self.root / "prompt.md"
        prompt.write_text("prompt")
        agent = StageClaudeCode(logs_dir=self.root / "logs", model_name="test",
                                system_prompt_path=prompt, disable_web_search=True)
        agent.allow_subagents = False
        flags = shlex.split(agent.build_cli_flags())
        self.assertEqual(flags.count("--disallowedTools"), 1)
        self.assertEqual(set(flags[flags.index("--disallowedTools") + 1].split(",")),
                         {"Agent", "Task", "WebSearch", "WebFetch"})

    def test_enabled_subagents_remain_available(self):
        prompt = self.root / "prompt.md"
        prompt.write_text("prompt")
        agent = StageClaudeCode(logs_dir=self.root / "logs", model_name="test",
                                system_prompt_path=prompt, disable_web_search=True)
        agent.allow_subagents = True
        flags = shlex.split(agent.build_cli_flags())
        denied = set(flags[flags.index("--disallowedTools") + 1].split(","))
        self.assertFalse({"Agent", "Task"} & denied)

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
    async def test_pinned_image_client_does_not_require_root_bootstrap(self):
        from runtime.workflow_agent import ensure_public_pinned_client
        env = SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(
            return_code=0, stdout="2.1.280 (Claude Code)\n")))
        await ensure_public_pinned_client(env, "2.1.280")
        env.exec.assert_awaited_once_with("/usr/local/bin/claude --version", user="root")

    async def test_pinned_client_falls_back_and_rejects_wrong_version(self):
        from runtime.workflow_agent import ensure_public_pinned_client
        wrong = SimpleNamespace(return_code=0, stdout="2.1.273 (Claude Code)\n")
        good = SimpleNamespace(return_code=0, stdout="2.1.280 (Claude Code)\n")
        env = SimpleNamespace(exec=AsyncMock(side_effect=[wrong, good]))
        await ensure_public_pinned_client(env, "2.1.280")
        self.assertEqual(env.exec.await_count, 2)
        env = SimpleNamespace(exec=AsyncMock(side_effect=[wrong, wrong]))
        with self.assertRaisesRegex(RuntimeError, "Pinned Claude Code"):
            await ensure_public_pinned_client(env, "2.1.280")

    async def test_stage_timeout_resets_and_preserves_failure_evidence(self):
        from runtime.workflow_timeouts import StageTimeoutError
        calls = []

        async def long_call(*args):
            calls.append(True)
            await asyncio.sleep(10)

        with tempfile.TemporaryDirectory() as temp:
            agent = SimpleNamespace(max_runtime_sec=None, stage_timeout_sec=.02,
                                    execution_deadline=None, run=long_call)
            environment = SimpleNamespace(download_dir=AsyncMock(), download_file=AsyncMock())
            backend = HarborBackend(agent, environment, None, Path(temp))
            backend.quiesce = AsyncMock()
            for stage_id in ("prd", "coding"):
                with self.assertRaisesRegex(StageTimeoutError, f"Stage {stage_id} execution timed out"):
                    await backend.execute(
                        {"role": "pm", "stage_id": stage_id, "writable_directory": "/out"},
                        "prompt", "instruction", None, Path(temp))
            self.assertEqual(len(calls), 2)
            self.assertIsNone(agent.execution_deadline)
            self.assertEqual(environment.download_file.await_count, 2)
            self.assertFalse(agent._resume)
            environment.download_dir.assert_any_await("/out", Path(temp) / "partial-artifacts")

    async def test_two_successful_stages_each_get_the_full_time_budget(self):
        async def short_call(*args):
            await asyncio.sleep(.03)

        with tempfile.TemporaryDirectory() as temp:
            agent = SimpleNamespace(max_runtime_sec=None, stage_timeout_sec=.05,
                                    execution_deadline=None, run=short_call)
            environment = SimpleNamespace(download_dir=AsyncMock(), download_file=AsyncMock())
            backend = HarborBackend(agent, environment, None, Path(temp))
            backend.quiesce = AsyncMock()
            with patch("runtime.workflow_agent.stream_session_ids", side_effect=lambda _: {"sid"}), \
                    patch("runtime.workflow_agent.native_role_evidence", return_value={}):
                for stage_id in ("prd", "coding"):
                    self.assertEqual(await backend.execute(
                        {"role": "pm", "stage_id": stage_id, "writable_directory": "/out"},
                        "prompt", "instruction", None, Path(temp)), "sid")

    async def test_total_deadline_kills_stage_and_preserves_partial_artifacts(self):
        async def long_call(*args):
            await asyncio.sleep(10)

        with tempfile.TemporaryDirectory() as temp:
            agent = SimpleNamespace(max_runtime_sec=.02, execution_deadline=None,
                                    run=long_call, _resume=False, resume_session_id=None)
            environment = SimpleNamespace(download_dir=AsyncMock(), download_file=AsyncMock())
            backend = HarborBackend(agent, environment, None, Path(temp))
            backend.quiesce = AsyncMock()
            with self.assertRaises(TimeoutError):
                await backend.execute({"role": "pm", "stage_id": "prd", "writable_directory": "/out"},
                                      "prompt", "instruction", None, Path(temp))
            self.assertTrue(backend.quiesce.await_count)
            environment.download_dir.assert_any_await("/out", Path(temp) / "partial-artifacts")
            deadline = agent.execution_deadline
            with self.assertRaises(TimeoutError):
                await backend.execute({"role": "pm", "stage_id": "prd", "writable_directory": "/out"},
                                      "prompt", "instruction", None, Path(temp))
            self.assertEqual(deadline, agent.execution_deadline)

    async def test_failed_evidence_download_preserves_original_model_error(self):
        async def failed_call(*args):
            raise RuntimeError("original model failure")

        with tempfile.TemporaryDirectory() as temp:
            agent = SimpleNamespace(max_runtime_sec=None, run=failed_call)
            environment = SimpleNamespace(download_dir=AsyncMock(side_effect=OSError("lost transfer")),
                                          download_file=AsyncMock(side_effect=OSError("lost transfer")))
            backend = HarborBackend(agent, environment, None, Path(temp))
            backend.quiesce = AsyncMock()
            with self.assertRaisesRegex(RuntimeError, "original model failure"):
                await backend.execute({"role": "pm", "stage_id": "prd", "writable_directory": "/out"},
                                      "prompt", "instruction", None, Path(temp))
            self.assertTrue((Path(temp) / "recovery-errors.json").is_file())

    def test_relay_preserves_history_and_sets_cache_effort(self):
        history = [{"role": "assistant", "content": [{"type": "thinking", "thinking": "history", "signature": "sig"}]}]
        body = {"model": "wrong", "system": "prefix", "messages": history}
        apply_profile(body, "selected", "max")
        self.assertIs(body["messages"], history)
        self.assertEqual(body["thinking"], {"type": "adaptive"})
        self.assertEqual(body["output_config"], {"effort": "max"})
        self.assertEqual(cache_count(body), 1)

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
