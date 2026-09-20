import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from runtime.reporting import LEGACY_MARKER, MARKER, write_report, write_index


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name) / "jobs/run"
        self.trial = self.job / "trial"
        (self.trial / "workflow").mkdir(parents=True)
        (self.job / "config.json").write_text(json.dumps({"agents": [{"model_name": "test", "kwargs": {}}]}))

    def test_blocked_report_preserves_outcome_and_checks_accepted_bytes(self):
        output = self.trial / "workflow/accepted/sprint1/prd/prd.md"
        output.parent.mkdir(parents=True)
        output.write_text("PRD")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        state = {"status": "blocked", "mode": "single", "stages": [
            {"id": "sprint1/prd", "role": "pm", "status": "accepted", "attempts": [{"session_id": "s"}], "outputs": {"prd.md": digest}},
            {"id": "sprint1/tech-design", "role": "architect", "status": "accepted", "attempts": [{"session_id": "s", "prd_input_sha256": digest}], "outputs": {}}]}
        (self.trial / "workflow/state.json").write_text(json.dumps(state))
        text = write_report(self.job).read_text()
        self.assertIn("**blocked**", text)
        self.assertIn("PRD 输出 / 技术阶段输入哈希：一致", text)
        self.assertIn("主会话数：1", text)
        output.write_text("changed")
        self.assertIn("缺失或不一致", write_report(self.job).read_text())
        write_index(self.job.parent)
        self.assertIn("blocked", (self.job.parent / "README.md").read_text())

    def test_exception_does_not_become_success_or_leak_raw_request(self):
        (self.trial / "result.json").write_text(json.dumps({"exception_info": {"exception_type": "RuntimeError", "exception_message": "SECRET_REQUEST_CONTENT"}}))
        text = write_report(self.job).read_text()
        self.assertIn("**failed**", text)
        self.assertNotIn("SECRET_REQUEST_CONTENT", text)

    def test_single_execution_report_links_stage_logs_and_only_sealed_outputs(self):
        workflow = self.trial / "workflow"
        prd = workflow / "accepted/sprint1/prd/prd.md"
        prd.parent.mkdir(parents=True)
        prd.write_text("PRD")
        digest = hashlib.sha256(prd.read_bytes()).hexdigest()
        partial = workflow / "accepted/sprint1/tech-design/partial.md"
        partial.parent.mkdir(parents=True)
        partial.write_text("unfinished")
        logs = workflow / "stages/sprint1/prd"
        logs.mkdir(parents=True)
        for name in ("native-evidence.json", "deployment-evidence.json"):
            (logs / name).write_text("{}")
        (workflow / "state.json").write_text(json.dumps({
            "status": "failed", "mode": "single", "stages": [
                {"id": "sprint1/prd", "role": "pm", "status": "accepted",
                 "execution_started": True, "session_id": "s", "outputs": {"prd.md": digest}},
                {"id": "sprint1/tech-design", "role": "architect", "status": "failed",
                 "execution_started": True, "session_id": "s", "prd_input_sha256": digest},
                {"id": "sprint2/tech-design", "role": "architect", "status": "accepted",
                 "reused_from": "sprint1/tech-design", "outputs": {}}]}))
        text = write_report(self.job).read_text()
        self.assertIn("| sprint1/prd | pm | accepted | 1 |", text)
        self.assertIn("| sprint1/tech-design | architect | failed | 1 |", text)
        self.assertIn("主会话数：1", text)
        self.assertIn("PRD 输出 / 技术阶段输入哈希：一致", text)
        self.assertIn("stages/sprint1/prd/native-evidence.json", text)
        self.assertIn("stages/sprint1/prd/deployment-evidence.json", text)
        self.assertIn("不代表内容验收通过", text)
        self.assertNotIn("partial.md", text)
        self.assertNotIn("attempts", text)

    def test_probe_is_distinguished_and_manual_report_is_protected(self):
        (self.job / "config.json").write_text(json.dumps({"agents": [{"kwargs": {"role_probe": True}}]}))
        (self.trial / "workflow/state.json").write_text(json.dumps({"status": "complete", "role_probe": True, "records": [{"role": "pm", "session_id": "s", "response": "PM_READY"}]}))
        text = write_report(self.job).read_text()
        self.assertIn("真实模型，非业务交付", text)
        self.assertIn("PM_READY", text)
        (self.job / "report.md").write_text("Human notes")
        with self.assertRaisesRegex(ValueError, "manually authored"):
            write_report(self.job)

    def test_legacy_generated_report_and_index_can_be_updated(self):
        (self.job / "report.md").write_text(LEGACY_MARKER + "\nOld report")
        (self.job.parent / "README.md").write_text(LEGACY_MARKER + "\nOld index")
        self.assertTrue(write_report(self.job).read_text().startswith(MARKER))
        write_index(self.job.parent)
        self.assertTrue((self.job.parent / "README.md").read_text().startswith(MARKER))

    def test_missing_trial_is_incomplete(self):
        (self.trial / "workflow").rmdir()
        (self.trial).rmdir()
        self.assertIn("未找到 trial 记录", write_report(self.job).read_text())

    def test_terminal_qa_failure_is_reported_without_claiming_success(self):
        (self.trial / "workflow/state.json").write_text(json.dumps({
            "status": "qa_failed", "qa_verdict": "fail", "mode": "single", "stages": []}))
        text = write_report(self.job).read_text()
        self.assertIn("**qa_failed**", text)
        self.assertIn("达到修复轮次上限", text)
        self.assertNotIn("本阶段未执行 Saleor", text)


if __name__ == "__main__":
    unittest.main()
