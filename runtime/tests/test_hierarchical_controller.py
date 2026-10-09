import copy
import json
from pathlib import Path
import tempfile
import unittest

from runtime.hierarchical_controller import HierarchicalController
from runtime.prepare_workflow import DEFAULTS, HERE, compile_workflow


class FakeTeamBackend:
    synthetic = False

    def __init__(self, plans, member_sessions=None, turn_cost=None):
        self.plans = iter(plans)
        self.member_sessions = member_sessions or {}
        self.turn_cost = turn_cost
        self.lead_resume = []
        self.member_resume = []
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def execute_lead(self, prompt, instruction, resume, turn_dir):
        self.lead_resume.append(resume)
        if self.turn_cost is not None:
            # Claude Code reports spend in the turn's own stream.
            (turn_dir / "claude-code.jsonl").write_text(
                json.dumps({"type": "result", "total_cost_usd": self.turn_cost}) + "\n"
            )
        return "lead-session", json.dumps(next(self.plans))

    async def prepare_assignment(self, member, task):
        pass

    async def execute_assignment(self, member, task, prompt, instruction, resume, task_dir):
        self.member_resume.append((member["id"], resume))
        session = self.member_sessions.setdefault(member["id"], "session-" + member["id"])
        outputs = task["write_scope"] if task["kind"] == "work" else []
        result = {
            "status": "completed", "summary": "synthetic controller test",
            "outputs": outputs, "blockers": [],
        }
        if task["kind"] == "review":
            result["verdict"] = "pass"
        return session, json.dumps(result)

    async def collect_assignment(self, task, result, task_dir):
        manifest = {path: (task["id"] * 64)[:64] for path in result["outputs"]}
        return manifest, {}

    async def seal_revision(self, task, revision, task_dir):
        pass

    async def accept_revision(self, revision, effect, directory):
        pass

    async def quiesce_member(self, member_id):
        pass

    async def stop_all(self):
        self.stopped = True

    def assignment_path(self, task_id, relative=None):
        return "/workspace/team/assignments/" + task_id + (("/" + relative) if relative else "")

    def revision_path(self, revision_id):
        return "/workspace/team/revisions/" + revision_id

    def revision_input_path(self, revision_id, ref):
        return self.revision_path(revision_id) + "/artifacts/input"


class HierarchicalControllerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.compiled = compile_workflow(
            "hierarchical", HERE / "tasks/saleor-3.23-pruned", verify_repos=False
        )

    async def test_persistent_lead_and_parallel_same_stage_members(self):
        plans = [
            {"summary": "make PRD", "actions": [
                {"type": "spawn_member", "member_id": "pm-1", "role": "pm"},
                {"type": "send_task", "task_id": "prd-v1", "member_id": "pm-1",
                 "stage_id": "sprint1/prd", "instructions": "write PRD",
                 "input_revisions": {}, "output_refs": ["artifact:sprint1/prd/prd"],
                 "write_scope": ["artifacts/sprint1/prd/prd.md"]},
            ]},
            {"summary": "parallel design", "actions": [
                {"type": "submit_artifact", "revision_id": "rev-0001",
                 "output_refs": ["artifact:sprint1/prd/prd"]},
                {"type": "spawn_member", "member_id": "architect-1", "role": "architect"},
                {"type": "spawn_member", "member_id": "architect-2", "role": "architect"},
                {"type": "send_task", "task_id": "frontend-v1", "member_id": "architect-1",
                 "stage_id": "sprint1/tech-design", "instructions": "frontend",
                 "input_revisions": {"artifact:sprint1/prd/prd": "rev-0001"},
                 "output_refs": ["artifact:sprint1/tech-design/frontend_design"],
                 "write_scope": ["artifacts/sprint1/tech-design/frontend-design.md"]},
                {"type": "send_task", "task_id": "backend-v1", "member_id": "architect-2",
                 "stage_id": "sprint1/tech-design", "instructions": "backend",
                 "input_revisions": {"artifact:sprint1/prd/prd": "rev-0001"},
                 "output_refs": ["artifact:sprint1/tech-design/backend_design"],
                 "write_scope": ["artifacts/sprint1/tech-design/backend-design.md"]},
            ]},
            {"summary": "stop bounded test", "actions": [
                {"type": "finish_delivery", "outcome": "blocked", "reason": "test boundary"},
            ]},
        ]
        backend = FakeTeamBackend(plans)
        controller = HierarchicalController(
            self.compiled, DEFAULTS, self.root / "workflow", backend
        )
        state = await controller.run()
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(backend.lead_resume, [None, "lead-session", "lead-session"])
        self.assertEqual({entry[0] for entry in backend.member_resume},
                         {"pm-1", "architect-1", "architect-2"})
        self.assertEqual(state["counters"]["peak_concurrency"], 2)
        self.assertTrue(backend.started)
        self.assertTrue(backend.stopped)

    async def test_lead_turn_budget_terminates_deterministically(self):
        compiled = copy.deepcopy(self.compiled)
        compiled["run"]["execution"]["max_lead_turns"] = 1
        backend = FakeTeamBackend([{
            "summary": "spawn", "actions": [
                {"type": "spawn_member", "member_id": "pm-1", "role": "pm"},
            ],
        }])
        state = await HierarchicalController(
            compiled, DEFAULTS, self.root / "budget", backend
        ).run()
        self.assertEqual(state["status"], "budget_exhausted")
        self.assertFalse(state["delivery_complete"])
        self.assertEqual(state["lead_turns"], 1)
        self.assertIn("max_lead_turns", state["error"])

    async def test_cost_budget_stops_the_lead_loop(self):
        compiled = copy.deepcopy(self.compiled)
        compiled["run"]["execution"]["max_cost_usd"] = 1.0
        spawn = {"summary": "spawn", "actions": [
            {"type": "spawn_member", "member_id": "pm-1", "role": "pm"},
        ]}
        # Each turn reports 0.6; the second crosses the 1.0 ceiling.
        backend = FakeTeamBackend([spawn, spawn, spawn], turn_cost=0.6)
        state = await HierarchicalController(
            compiled, DEFAULTS, self.root / "cost", backend
        ).run()
        self.assertEqual(state["status"], "budget_exhausted")
        self.assertFalse(state["delivery_complete"])
        self.assertIn("max_cost_usd", state["error"])
        self.assertEqual(state["cost_usd"], 1.2)
        # Stopped after the second turn rather than running the third.
        self.assertEqual(state["lead_turns"], 2)
        self.assertTrue(backend.stopped)

    async def test_rejected_plan_is_still_billed(self):
        compiled = copy.deepcopy(self.compiled)
        compiled["run"]["execution"]["max_cost_usd"] = 1.0
        # An invalid plan spends the model call that produced it.
        invalid = {"summary": "invalid", "actions": [{"type": "no_such_action"}]}
        backend = FakeTeamBackend([invalid, invalid, invalid], turn_cost=0.6)
        state = await HierarchicalController(
            compiled, DEFAULTS, self.root / "rejected", backend
        ).run()
        self.assertEqual(state["status"], "budget_exhausted")
        self.assertIn("max_cost_usd", state["error"])
        self.assertEqual(state["cost_usd"], 1.2)
        self.assertEqual(state["lead_turns"], 2)

    async def test_run_without_reported_cost_is_not_charged(self):
        compiled = copy.deepcopy(self.compiled)
        compiled["run"]["execution"]["max_cost_usd"] = 0.01
        backend = FakeTeamBackend([{
            "summary": "stop", "actions": [
                {"type": "finish_delivery", "outcome": "blocked", "reason": "test boundary"},
            ],
        }])
        state = await HierarchicalController(
            compiled, DEFAULTS, self.root / "nocost", backend
        ).run()
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(state["cost_usd"], 0.0)


if __name__ == "__main__":
    unittest.main()
