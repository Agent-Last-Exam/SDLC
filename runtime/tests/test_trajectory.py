"""Claude Code native-to-ATIF export checks; no model calls."""
import json
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harbor.models.agent.context import AgentContext
from harbor.agents.installed.claude_code import ClaudeCode
from harbor.models.trajectories.trajectory import Trajectory
from runtime.trajectory import export_trajectory, stream_cost
from runtime.workflow_agent import WorkflowClaudeCode


def user_event(session_id, text, timestamp):
    return {
        "type": "user", "sessionId": session_id, "timestamp": timestamp,
        "version": "2.1.273",
        "message": {"role": "user", "content": text},
    }


def assistant_event(session_id, text, timestamp, prompt=10, completion=3,
                    cached=2, sidechain=False, agent_id=None):
    row = {
        "type": "assistant", "sessionId": session_id,
        "timestamp": timestamp, "version": "2.1.273",
        "isSidechain": sidechain,
        "message": {
            "id": f"msg-{timestamp}-{agent_id or 'main'}",
            "role": "assistant", "model": "claude-opus-4-6",
            "content": [{"type": "text", "text": text}],
            "usage": {
                "input_tokens": prompt, "output_tokens": completion,
                "cache_read_input_tokens": cached,
            },
        },
    }
    if agent_id:
        row["agentId"] = agent_id
        row["agent_id"] = agent_id
    return row


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    return path


class TrajectoryTests(unittest.TestCase):
    def setUp(self):
        cost_patch = patch.object(
            ClaudeCode, "_estimate_step_costs", return_value=None
        )
        cost_patch.start()
        self.addCleanup(cost_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.trial = Path(self.temp.name)
        self.logs = self.trial / "agent"
        workflow = self.trial / "workflow"
        workflow.mkdir()
        (workflow / "state.json").write_text(json.dumps({
            "principal_session": "main", "status": "failed"
        }))
        rows = [
            user_event("main", "SDLC_STAGE_ROLE: pm", "2026-01-01T00:00:00Z"),
            assistant_event("main", "pm result", "2026-01-01T00:00:01Z"),
            user_event("main", "SDLC_STAGE_ROLE: architect", "2026-01-01T00:00:02Z"),
            assistant_event("main", "architect result", "2026-01-01T00:00:03Z"),
        ]
        self.source = write_rows(
            self.logs / "sessions/projects/-workspace/main.jsonl", rows
        )
        write_rows(
            self.logs / "sessions/projects/-workspace/main/subagents/agent-child.jsonl",
            [assistant_event("main", "child result", "2026-01-01T00:00:01.5Z",
                             sidechain=True, agent_id="child")],
        )

    def test_export_selects_principal_preserves_roles_and_raw_bytes(self):
        original = self.source.read_bytes()
        exported = export_trajectory(self.logs, "claude-opus-4-6")
        parsed = Trajectory.model_validate_json((self.logs / "trajectory.json").read_text())
        self.assertEqual(parsed.session_id, "main")
        self.assertEqual(len(parsed.steps), len(exported.steps))
        self.assertTrue(any("architect" in str(step.message) for step in parsed.steps))
        self.assertTrue(any((step.extra or {}).get("is_sidechain") for step in parsed.steps))
        self.assertEqual(original, self.source.read_bytes())

    def test_failed_run_post_hook_exports_but_smoke_does_not(self):
        agent = object.__new__(WorkflowClaudeCode)
        agent.logs_dir, agent.model_name = self.logs, "claude-opus-4-6"
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

    def test_stage_stream_costs_are_summed_without_double_counting_rows(self):
        first = self.trial / "first.jsonl"
        second = self.trial / "second.jsonl"
        write_rows(first, [
            {"type": "result", "total_cost_usd": 0.1},
            {"type": "result", "total_cost_usd": 0.2},
        ])
        write_rows(second, [{"type": "result", "total_cost_usd": 0.3}])
        self.assertAlmostEqual(stream_cost([first, second]), 0.5)


class FlatTrajectoryTests(unittest.TestCase):
    def setUp(self):
        cost_patch = patch.object(
            ClaudeCode, "_estimate_step_costs", return_value=None
        )
        cost_patch.start()
        self.addCleanup(cost_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.trial = Path(self.temp.name)
        self.logs = self.trial / "agent"
        self.logs.mkdir()
        workflow = self.trial / "workflow"
        workflow.mkdir()
        self.descriptors = [
            {"stage_id": "sprint1/prd", "role": "pm", "session_id": "main-pm"},
            {"stage_id": "sprint1/tech-design", "role": "architect",
             "session_id": "main-architect"},
        ]
        (workflow / "state.json").write_text(json.dumps({
            "mode": "flat", "status": "failed",
            "principal_sessions": self.descriptors,
        }))
        self.sources = [
            self.write_session("sprint1/prd", "main-pm", "pm main", 10, 3, 2),
            self.write_session("sprint1/tech-design", "main-architect",
                               "architect main", 20, 7, 4),
        ]
        child = self.sources[0].with_suffix("") / "subagents/agent-child.jsonl"
        self.sources.append(write_rows(child, [
            assistant_event("main-pm", "pm child", "2026-01-01T00:00:00.5Z",
                            5, 2, 1, True, "child")
        ]))
        for index, descriptor in enumerate(self.descriptors, start=1):
            stream = (self.trial / "workflow/stages" / descriptor["stage_id"]
                      / "claude-code.jsonl")
            write_rows(stream, [{"type": "result", "total_cost_usd": index / 10}])

    def write_session(self, stage_id, session_id, message, prompt, completion, cached):
        path = (self.trial / "workflow/stages" / stage_id
                / "sessions/projects/-workspace" / f"{session_id}.jsonl")
        return write_rows(path, [
            assistant_event(session_id, message, "2026-01-01T00:00:01Z",
                            prompt, completion, cached)
        ])

    def test_flat_export_merges_principals_and_preserves_sidechains(self):
        originals = {path: path.read_bytes() for path in self.sources}
        exported = export_trajectory(self.logs, "claude-opus-4-6")
        parsed = Trajectory.model_validate_json((self.logs / "trajectory.json").read_text())
        self.assertEqual(parsed.session_id, "flat-workflow")
        self.assertEqual([step.step_id for step in parsed.steps], list(range(1, 4)))
        self.assertEqual([step.extra["stage_id"] for step in parsed.steps], [
            "sprint1/prd", "sprint1/prd", "sprint1/tech-design",
        ])
        self.assertTrue(parsed.steps[0].extra["is_sidechain"])
        self.assertIn("pm main", str(parsed.steps[1].message))
        self.assertIn("architect main", str(parsed.steps[2].message))
        self.assertIsNone(parsed.subagent_trajectories)
        self.assertEqual(parsed.final_metrics.total_prompt_tokens, 42)
        self.assertEqual(parsed.final_metrics.total_completion_tokens, 12)
        self.assertEqual(parsed.final_metrics.total_cached_tokens, 7)
        self.assertAlmostEqual(parsed.final_metrics.total_cost_usd, 0.3)
        self.assertEqual(parsed.final_metrics.total_steps, len(parsed.steps))
        self.assertEqual(parsed.final_metrics.extra["subagent_step_count"], 1)
        self.assertEqual(len(exported.steps), 3)
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_flat_export_requires_each_recorded_principal(self):
        self.sources[1].unlink()
        with self.assertRaisesRegex(ValueError, "Principal session log missing: main-architect"):
            export_trajectory(self.logs)
        self.assertFalse((self.logs / "trajectory.json").exists())


class HierarchicalTrajectoryTests(unittest.TestCase):
    def setUp(self):
        cost_patch = patch.object(
            ClaudeCode, "_estimate_step_costs", return_value=None
        )
        cost_patch.start()
        self.addCleanup(cost_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.trial = Path(self.temp.name)
        self.logs = self.trial / "agent"
        self.logs.mkdir()
        workflow = self.trial / "workflow"
        workflow.mkdir()
        state = {
            "mode": "hierarchical", "status": "blocked",
            "lead_session": "lead-1",
            "members": {
                "pm-1": {"id": "pm-1", "role": "pm", "session_id": "member-1",
                         "assignments": ["prd-v1"]},
            },
            "assignments": {
                "prd-v1": {"id": "prd-v1", "stage_id": "sprint1/prd",
                           "member_id": "pm-1", "status": "completed",
                           "revision_id": "rev-0001"},
            },
            "revisions": {
                "rev-0001": {"id": "rev-0001", "task_id": "prd-v1"},
            },
            "counters": {"peak_concurrency": 1},
        }
        (workflow / "state.json").write_text(json.dumps(state))
        lead = workflow / "lead/turn-002"
        write_rows(lead / "sessions/projects/-workspace/lead-1.jsonl", [
            assistant_event("lead-1", "lead plan", "2026-01-01T00:00:01Z")
        ])
        write_rows(lead / "claude-code.jsonl", [
            {"type": "result", "total_cost_usd": 0.2}
        ])
        member = workflow / "assignments/prd-v1"
        write_rows(member / "sessions/projects/-workspace/member-1.jsonl", [
            user_event("member-1", "SDLC_TEAM_TASK: prd-v1", "2026-01-01T00:00:02Z"),
            assistant_event("member-1", "prd result", "2026-01-01T00:00:03Z"),
        ])
        write_rows(member / "claude-code.jsonl", [
            {"type": "result", "total_cost_usd": 0.3}
        ])

    def test_hierarchical_export_embeds_members_and_revision_metadata(self):
        exported = export_trajectory(self.logs, "claude-opus-4-6")
        parsed = Trajectory.model_validate_json(
            (self.logs / "trajectory.json").read_text()
        )
        self.assertEqual(parsed.trajectory_id, "hierarchical-lead")
        self.assertEqual(parsed.extra["mode"], "hierarchical")
        self.assertEqual(len(parsed.subagent_trajectories), 1)
        member = parsed.subagent_trajectories[0]
        self.assertEqual(member.trajectory_id, "team-member-pm-1")
        self.assertEqual(member.extra["revisions"], ["rev-0001"])
        self.assertTrue(any(
            (step.extra or {}).get("task_id") == "prd-v1"
            and step.extra.get("revision_id") == "rev-0001"
            for step in member.steps
        ))
        self.assertAlmostEqual(parsed.final_metrics.total_cost_usd, 0.5)
        self.assertEqual(exported.session_id, "lead-1")


if __name__ == "__main__":
    unittest.main()
