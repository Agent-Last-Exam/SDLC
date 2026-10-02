import json
import unittest

from runtime.team_protocol import (
    ProtocolError, extract_structured_output, parse_lead_plan,
    parse_member_result, safe_scope,
)


class TeamProtocolTests(unittest.TestCase):
    def test_lead_plan_accepts_multiple_stage_members_and_strict_fields(self):
        plan = parse_lead_plan(json.dumps({
            "summary": "parallel design",
            "actions": [
                {"type": "spawn_member", "member_id": "architect-1", "role": "architect"},
                {"type": "spawn_member", "member_id": "architect-2", "role": "architect"},
            ],
        }), max_actions=2)
        self.assertEqual(len(plan["actions"]), 2)
        with self.assertRaisesRegex(ProtocolError, "unsupported fields"):
            parse_lead_plan(json.dumps({
                "summary": "bad", "actions": [{
                    "type": "spawn_member", "member_id": "pm-1", "role": "pm",
                    "shell": "ignored",
                }],
            }))

    def test_finish_must_be_the_only_action(self):
        with self.assertRaisesRegex(ProtocolError, "only action"):
            parse_lead_plan(json.dumps({
                "summary": "bad",
                "actions": [
                    {"type": "stop_member", "member_id": "pm-1"},
                    {"type": "finish_delivery", "outcome": "blocked", "reason": "x"},
                ],
            }))

    def test_removed_inspect_member_action_is_rejected(self):
        with self.assertRaisesRegex(ProtocolError, "unsupported action type"):
            parse_lead_plan(json.dumps({
                "summary": "obsolete action",
                "actions": [{"type": "inspect_member", "member_id": "pm-1"}],
            }))

    def test_scope_rejects_traversal_and_unscoped_roots(self):
        self.assertEqual(safe_scope("artifacts/sprint1/prd/prd.md"),
                         "artifacts/sprint1/prd/prd.md")
        for value in ("../repos/x", "/workspace/repos/x", "repos", "a/b", "repos//x"):
            with self.subTest(value=value), self.assertRaises(ProtocolError):
                safe_scope(value)

    def test_member_result_requires_exact_structured_output(self):
        result = parse_member_result(json.dumps({
            "status": "completed", "summary": "done",
            "outputs": ["artifacts/sprint1/prd/prd.md"], "blockers": [],
        }))
        self.assertEqual(result["status"], "completed")
        with self.assertRaises(ProtocolError):
            extract_structured_output("prose " + json.dumps(result))
        with self.assertRaisesRegex(ProtocolError, "explain"):
            parse_member_result(json.dumps({
                "status": "blocked", "summary": "no", "outputs": [], "blockers": [],
            }))

    def test_reviewer_is_read_only_and_has_verdict(self):
        result = parse_member_result(json.dumps({
            "status": "completed", "summary": "consistent", "outputs": [],
            "blockers": [], "verdict": "pass",
        }), reviewer=True)
        self.assertEqual(result["verdict"], "pass")
        with self.assertRaisesRegex(ProtocolError, "cannot produce"):
            parse_member_result(json.dumps({
                "status": "completed", "summary": "bad",
                "outputs": ["artifacts/x/y/z.md"], "blockers": [], "verdict": "pass",
            }), reviewer=True)


if __name__ == "__main__":
    unittest.main()
