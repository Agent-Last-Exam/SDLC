import copy
import unittest

from runtime.prepare_workflow import HERE, compile_workflow
from runtime.team_broker import TeamBroker
from runtime.team_protocol import ProtocolError

PRUNED = HERE / "tasks/saleor-3.23-pruned"


def action(kind, **values):
    return {"type": kind, **values}


class TeamBrokerTests(unittest.TestCase):
    def setUp(self):
        self.compiled = compile_workflow("hierarchical", PRUNED, verify_repos=False)
        self.broker = TeamBroker(self.compiled)

    def apply(self, *actions):
        return self.broker.apply_plan({"summary": "test", "actions": list(actions)})

    def spawn(self, member_id, role):
        self.apply(action("spawn_member", member_id=member_id, role=role))

    def queue(self, task_id, member_id, stage_id, inputs, outputs, scopes):
        effects = self.apply(action(
            "send_task", task_id=task_id, member_id=member_id,
            stage_id=stage_id, instructions="work", input_revisions=inputs,
            output_refs=outputs, write_scope=scopes,
        ))
        return effects[0]["task"]

    def complete(self, task, files, routing=None):
        self.broker.mark_running(task["id"])
        result = {"status": "completed", "summary": "done",
                  "outputs": list(files), "blockers": []}
        return self.broker.record_assignment_result(
            task["id"], result, manifest=files, routing=routing
        )

    def accept(self, revision, refs=None):
        self.apply(action(
            "submit_artifact", revision_id=revision["id"],
            output_refs=refs or list(revision["outputs"]),
        ))

    def prd_revision(self, suffix):
        if "pm-1" not in self.broker.state["members"]:
            self.spawn("pm-1", "pm")
        task = self.queue(
            "prd-" + suffix, "pm-1", "sprint1/prd", {},
            ["artifact:sprint1/prd/prd"],
            ["artifacts/sprint1/prd/prd.md"],
        )
        return self.complete(task, {
            "artifacts/sprint1/prd/prd.md": suffix * 64,
        })

    def test_same_stage_allows_multiple_members_with_disjoint_outputs(self):
        prd = self.prd_revision("a")
        self.accept(prd)
        self.spawn("architect-1", "architect")
        self.spawn("architect-2", "architect")
        binding = {"artifact:sprint1/prd/prd": prd["id"]}
        first = self.queue(
            "frontend", "architect-1", "sprint1/tech-design", binding,
            ["artifact:sprint1/tech-design/frontend_design"],
            ["artifacts/sprint1/tech-design/frontend-design.md"],
        )
        second = self.queue(
            "backend", "architect-2", "sprint1/tech-design", binding,
            ["artifact:sprint1/tech-design/backend_design"],
            ["artifacts/sprint1/tech-design/backend-design.md"],
        )
        self.assertNotEqual(first["member_id"], second["member_id"])
        self.assertEqual(self.broker.state["counters"]["peak_concurrency"], 2)

    def test_parallel_overlapping_scope_is_rejected_atomically(self):
        prd = self.prd_revision("a")
        self.accept(prd)
        self.spawn("architect-1", "architect")
        self.spawn("architect-2", "architect")
        binding = {"artifact:sprint1/prd/prd": prd["id"]}
        self.queue(
            "frontend", "architect-1", "sprint1/tech-design", binding,
            ["artifact:sprint1/tech-design/frontend_design"],
            ["artifacts/sprint1/tech-design/frontend-design.md"],
        )
        before = copy.deepcopy(self.broker.state)
        with self.assertRaisesRegex(ProtocolError, "overlaps"):
            self.queue(
                "backend", "architect-2", "sprint1/tech-design", binding,
                ["artifact:sprint1/tech-design/frontend_design"],
                ["artifacts/sprint1/tech-design/frontend-design.md"],
            )
        self.assertEqual(self.broker.state, before)

    def test_member_output_outside_scope_is_rejected(self):
        self.spawn("pm-1", "pm")
        task = self.queue(
            "prd-v1", "pm-1", "sprint1/prd", {},
            ["artifact:sprint1/prd/prd"], ["artifacts/sprint1/prd/prd.md"],
        )
        self.broker.mark_running(task["id"])
        with self.assertRaisesRegex(ProtocolError, "outside write_scope"):
            self.broker.record_assignment_result(task["id"], {
                "status": "completed", "summary": "bad",
                "outputs": ["artifacts/sprint1/prd/prd.md", "repos/escape.py"],
                "blockers": [],
            }, manifest={
                "artifacts/sprint1/prd/prd.md": "a" * 64,
                "repos/escape.py": "b" * 64,
            })

    def test_upstream_replacement_marks_current_downstream_stale(self):
        first = self.prd_revision("a")
        self.accept(first)
        self.spawn("architect-1", "architect")
        task = self.queue(
            "design-v1", "architect-1", "sprint1/tech-design",
            {"artifact:sprint1/prd/prd": first["id"]},
            ["artifact:sprint1/tech-design/frontend_design"],
            ["artifacts/sprint1/tech-design/frontend-design.md"],
        )
        design = self.complete(task, {
            "artifacts/sprint1/tech-design/frontend-design.md": "c" * 64,
        })
        self.accept(design)
        second = self.prd_revision("b")
        self.accept(second)
        self.assertEqual(self.broker.state["revisions"][design["id"]]["status"], "stale")
        self.assertNotIn(
            "artifact:sprint1/tech-design/frontend_design",
            self.broker.state["current_artifacts"],
        )
        self.assertEqual(self.broker.state["revisions"][first["id"]]["status"], "accepted")

    def test_incomplete_closure_and_no_qa_pass_refuse_complete(self):
        prd = self.prd_revision("a")
        self.accept(prd)
        with self.assertRaisesRegex(ProtocolError, "QA verdict|required artifacts"):
            self.apply(action(
                "finish_delivery", outcome="complete", reason="premature",
            ))
        self.assertEqual(self.broker.state["status"], "running")

    def test_revision_acceptance_must_precede_new_assignments_in_a_plan(self):
        prd = self.prd_revision("a")
        self.spawn("pm-2", "pm")
        with self.assertRaisesRegex(ProtocolError, "must precede"):
            self.apply(
                action(
                    "send_task", task_id="other-prd", member_id="pm-2",
                    stage_id="sprint1/prd", instructions="alternative",
                    input_revisions={}, output_refs=["artifact:sprint1/prd/prd"],
                    write_scope=["artifacts/sprint1/prd/prd.md"],
                ),
                action(
                    "submit_artifact", revision_id=prd["id"],
                    output_refs=["artifact:sprint1/prd/prd"],
                ),
            )

    def test_member_session_is_stable_but_distinct_between_members(self):
        self.spawn("pm-1", "pm")
        self.spawn("pm-2", "pm")
        self.broker.set_member_session("pm-1", "session-a")
        self.broker.set_member_session("pm-2", "session-b")
        self.broker.set_member_session("pm-1", "session-a")
        with self.assertRaisesRegex(ProtocolError, "changed"):
            self.broker.set_member_session("pm-1", "session-b")

    def test_repository_only_parallel_revisions_are_supported(self):
        prd = self.prd_revision("a")
        self.accept(prd)
        self.spawn("developer-1", "developer")
        self.spawn("developer-2", "developer")
        # This unit test focuses on repository scheduling, so create minimal
        # accepted placeholders for all required design references.
        required = {}
        artifact_inputs = [
            ref for ref in self.broker.stages["sprint1/development"]["inputs"]
            if ref.startswith("artifact:")
        ]
        for index, ref in enumerate(artifact_inputs, start=100):
            if ref == "artifact:sprint1/prd/prd":
                required[ref] = prd["id"]
                continue
            revision_id = f"rev-{index:04d}"
            self.broker.state["revisions"][revision_id] = {
                "id": revision_id, "stage_id": "sprint1/tech-design",
                "task_id": "fixture", "member_id": "fixture", "status": "accepted",
                "input_revisions": {"artifact:sprint1/prd/prd": prd["id"]},
                "repository_revisions": [],
                "outputs": {ref: {"path": "artifacts/fixture", "sha256": "f" * 64}},
                "files": {}, "routing": {},
            }
            self.broker.state["current_artifacts"][ref] = revision_id
            required[ref] = revision_id
        first = self.queue(
            "core-code", "developer-1", "sprint1/development", required, [],
            ["repos/saleor"],
        )
        second = self.queue(
            "dashboard-code", "developer-2", "sprint1/development", required, [],
            ["repos/saleor-dashboard"],
        )
        first_revision = self.complete(first, {"repos/saleor/a.py": "a" * 64})
        second_revision = self.complete(
            second, {"repos/saleor-dashboard/a.ts": "b" * 64}
        )
        self.accept(first_revision, [])
        self.accept(second_revision, [])
        self.assertEqual(
            self.broker.state["current_repository_revisions"],
            [first_revision["id"], second_revision["id"]],
        )

    def test_reviewer_can_rebind_stale_revision_to_current_upstream(self):
        first = self.prd_revision("a")
        self.accept(first)
        self.spawn("architect-1", "architect")
        design_task = self.queue(
            "design-v1", "architect-1", "sprint1/tech-design",
            {"artifact:sprint1/prd/prd": first["id"]},
            ["artifact:sprint1/tech-design/frontend_design"],
            ["artifacts/sprint1/tech-design/frontend-design.md"],
        )
        design = self.complete(design_task, {
            "artifacts/sprint1/tech-design/frontend-design.md": "d" * 64,
        })
        self.accept(design)
        second = self.prd_revision("b")
        self.accept(second)
        self.spawn("reviewer-1", "reviewer")
        effects = self.apply(action(
            "request_check", task_id="review-design", member_id="reviewer-1",
            revision_id=design["id"], instructions="check against new PRD",
            input_revisions={"artifact:sprint1/prd/prd": second["id"]},
        ))
        task = effects[0]["task"]
        self.broker.mark_running(task["id"])
        rebound = self.broker.record_assignment_result(task["id"], {
            "status": "completed", "summary": "still valid", "outputs": [],
            "blockers": [], "verdict": "pass",
        })
        self.accept(rebound)
        self.assertEqual(
            self.broker.state["current_artifacts"][
                "artifact:sprint1/tech-design/frontend_design"
            ],
            rebound["id"],
        )
        self.assertEqual(rebound["source_revision"], design["id"])
        self.assertEqual(
            self.broker.state["revisions"][design["id"]]["status"], "stale"
        )

    def test_complete_accepts_a_consistent_sprint1_pass_closure(self):
        current = self.broker.state["current_artifacts"]
        for sequence, stage in enumerate(self.compiled["stages"][:6], start=1):
            revision_id = f"rev-{sequence:04d}"
            inputs = {
                ref: current[ref]
                for ref in stage["inputs"] if ref.startswith("artifact:")
            }
            outputs = {
                ref: {
                    "path": self.broker.output_paths[ref],
                    "sha256": str(sequence) * 64,
                }
                for ref in stage["outputs"]
            }
            revision = {
                "id": revision_id, "stage_id": stage["stage_id"],
                "task_id": f"fixture-{sequence}", "member_id": "fixture",
                "status": "accepted", "input_revisions": inputs,
                "repository_revisions": [], "outputs": outputs,
                "files": {},
                "routing": {"verdict": "pass"} if stage["role"] == "qa" else {},
            }
            self.broker.state["revisions"][revision_id] = revision
            for ref in outputs:
                current[ref] = revision_id
        self.broker.state["qa_verdict"] = "pass"
        self.apply(action(
            "finish_delivery", outcome="complete", reason="QA passed",
        ))
        self.assertEqual(self.broker.state["status"], "complete")
        self.assertTrue(self.broker.state["delivery_complete"])

    def test_cost_budget_accumulates_and_reports_exhaustion(self):
        limit = self.broker.state["max_cost_usd"]
        self.assertEqual(self.broker.state["cost_usd"], 0.0)
        self.assertFalse(self.broker.charge(limit / 4))
        self.assertFalse(self.broker.charge(limit / 4))
        self.assertEqual(self.broker.state["cost_usd"], limit / 2)
        # Unknown spend must not be counted as zero nor invented.
        self.assertFalse(self.broker.charge(None))
        self.assertEqual(self.broker.state["cost_usd"], limit / 2)
        self.assertTrue(self.broker.charge(limit / 2))

    def test_cost_exhaustion_terminates_as_budget_exhausted(self):
        self.broker.charge(self.broker.state["max_cost_usd"])
        self.broker.terminate_budget("max_cost_usd")
        self.assertEqual(self.broker.state["status"], "budget_exhausted")
        self.assertFalse(self.broker.state["delivery_complete"])
        self.assertIn("max_cost_usd", self.broker.state["error"])

    def test_lead_turn_budget_still_reports_its_own_name(self):
        self.broker.terminate_budget()
        self.assertIn("max_lead_turns", self.broker.state["error"])


if __name__ == "__main__":
    unittest.main()
