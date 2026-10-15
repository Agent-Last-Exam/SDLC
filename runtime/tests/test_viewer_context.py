"""Display copies preserve evidence and are readable by the installed Harbor Viewer."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from runtime.viewer_context import display_trajectory, prepare


class ViewerContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.jobs = self.root / "jobs"
        self.archive = self.jobs / "archived-rollout"
        self.bundle = self.archive / "prompt-snapshots"
        self.bundle.mkdir(parents=True)
        self.original = {
            "schema_version": "ATIF-v1.8", "session_id": "main",
            "agent": {"name": "claude-code", "version": "test", "model_name": "test"},
            "steps": [
                {"step_id": 1, "source": "user", "message": "Original request",
                 "timestamp": "2026-10-14T00:00:00Z"},
                {"step_id": 2, "source": "agent", "message": "Original response",
                 "tool_calls": [{"tool_call_id": "tool-1", "function_name": "bash",
                                 "arguments": {"command": "true"}}],
                 "metrics": {"prompt_tokens": 10, "completion_tokens": 5},
                 "extra": {"is_sidechain": True}},
            ],
            "final_metrics": {"total_steps": 2, "total_cost_usd": 1.25},
        }
        raw = gzip.compress(json.dumps(self.original).encode(), mtime=0)
        (self.archive / "trajectory.json.gz").write_bytes(raw)
        role = b"Saved role with ```nested fence```"
        role_path = self.bundle / "job-a/trial-a/stages/sprint1/prd/role.md"
        role_path.parent.mkdir(parents=True)
        role_path.write_bytes(role)
        self.manifest = {
            "schema_version": 1, "archive": "archived-rollout",
            "trajectory": {"path": "trajectory.json.gz",
                           "sha256": hashlib.sha256(raw).hexdigest()},
            "rollouts": [{
                "source_job": "job-a", "source_trial": "trial-a",
                "recovery_source": {"job": "job-before", "trial": "trial-before"},
                "stages": [{
                    "stage_id": "sprint1/prd", "role": "pm", "recorded_status": "accepted",
                    "session_id": "main", "identical_snapshot_in_recovery_source": True,
                    "session_present_in_published_trajectory_metadata": True,
                    "missing_snapshot_files": ["instruction.md", "native-evidence.json"],
                    "files": [{"path": role_path.relative_to(self.bundle).as_posix(),
                               "source_sha256": hashlib.sha256(role).hexdigest(),
                               "export_sha256": hashlib.sha256(role).hexdigest()}],
                }],
            }],
        }
        self.path = self.bundle / "manifest.json"
        self.write_manifest()

    def write_manifest(self):
        self.path.write_text(json.dumps(self.manifest))

    def test_display_separates_context_and_preserves_original_events_and_metrics(self):
        raw = (self.archive / "trajectory.json.gz").read_bytes()
        original = copy.deepcopy(self.original)
        view, _ = display_trajectory(self.path)
        offset = view["extra"]["archive_context_view"]["supplemental_steps"]
        self.assertEqual(3, offset)
        self.assertTrue(all(s["source"] == "system" for s in view["steps"][:offset]))
        self.assertIn("非原始对话事件", view["steps"][0]["message"])
        self.assertIn("job-a / trial-a", view["steps"][1]["message"])
        self.assertIn("不能计作本次重新执行", view["steps"][1]["message"])
        self.assertIn("native-evidence.json", view["steps"][1]["message"])
        self.assertIn("````", view["steps"][1]["message"])
        self.assertEqual(original["final_metrics"], view["final_metrics"])
        restored = copy.deepcopy(view["steps"][offset:])
        for step in restored:
            step["step_id"] = step["extra"].pop("archive_original_step_id")
            if not step["extra"]:
                del step["extra"]
        self.assertEqual(original["steps"], restored)
        self.assertEqual(raw, (self.archive / "trajectory.json.gz").read_bytes())

    def test_tampering_fails_before_any_output_is_written(self):
        self.manifest["trajectory"]["sha256"] = "bad"
        self.write_manifest()
        output = self.root / "viewer"
        with self.assertRaisesRegex(ValueError, "Trajectory hash mismatch"):
            prepare(self.jobs, output)
        self.assertFalse(output.exists())

    def test_snapshot_tampering_and_path_escape_are_rejected(self):
        self.manifest["rollouts"][0]["stages"][0]["files"][0]["export_sha256"] = "bad"
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "Snapshot hash mismatch"):
            display_trajectory(self.path)
        self.manifest["rollouts"][0]["stages"][0]["files"][0]["path"] = "../outside"
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "escapes"):
            display_trajectory(self.path)

    def test_preparation_is_deterministic_and_refuses_source_or_existing_output(self):
        for name in [self.jobs, self.jobs / "viewer", self.root]:
            with self.assertRaises(ValueError):
                prepare(self.jobs, name)
        first = prepare(self.jobs, self.root / "view-a")
        second = prepare(self.jobs, self.root / "view-b")
        self.assertEqual(first, second)
        relative = Path(first[0]["viewer_job"]) / "archive-view/agent/trajectory.json"
        self.assertEqual((self.root / "view-a" / relative).read_bytes(),
                         (self.root / "view-b" / relative).read_bytes())
        self.assertFalse(list((self.root / "view-a").rglob("result.json")))
        with self.assertRaisesRegex(ValueError, "already exists"):
            prepare(self.jobs, self.root / "view-a")

    def test_installed_harbor_schema_and_real_viewer_api_accept_the_display_copy(self):
        try:
            from fastapi.testclient import TestClient
            from harbor.models.trajectories import Trajectory
            from harbor.models.trial.config import TrialConfig
            from harbor.viewer.scanner import JobScanner
            from harbor.viewer.server import create_app
        except ImportError:
            self.skipTest("Run this integration test with the installed Harbor Python")
        output = self.root / "viewer"
        [entry] = prepare(self.jobs, output)
        job, trial = entry["viewer_job"], entry["viewer_trial"]
        self.assertEqual([trial], JobScanner(output).list_trials(job))
        TrialConfig.model_validate_json((output / job / trial / "config.json").read_text())
        client = TestClient(create_app(output))
        response = client.get(f"/api/jobs/{job}/trials/{trial}/trajectory")
        self.assertEqual(200, response.status_code)
        parsed = Trajectory.model_validate(response.json())
        self.assertEqual("system", parsed.steps[0].source)
        self.assertEqual(5, len(parsed.steps))
        self.assertEqual(1.25, parsed.final_metrics.total_cost_usd)


if __name__ == "__main__":
    unittest.main()
