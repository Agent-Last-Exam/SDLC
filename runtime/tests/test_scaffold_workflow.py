"""Task-owned workflow scaffolding checks; no Docker, model, or network calls."""

import json
from pathlib import Path
import tempfile
import unittest

from runtime.scaffold_workflow import DEFAULT_SOURCE, scaffold


class WorkflowScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "standard"
        (self.target / "environment").mkdir(parents=True)
        (self.target / "tests").mkdir()
        (self.target / "instruction.md").write_text("Target instruction\n")
        (self.target / "workflow-instruction.md").write_text("Workflow product brief\n")
        (self.target / "environment/Dockerfile").write_text("FROM scratch\n")
        (self.target / "task.toml").write_text('''schema_version = "1.3"
[task]
name = "fixture/standard"
[metadata]
task_id = "fixture"
[environment]
docker_image = "fixture:base"
cpus = 8
memory_mb = 16000
storage_mb = 40000
build_timeout_sec = 7200.0
''')
        (self.target / "tests/config.json").write_text(json.dumps({"repos": {
            "saleor": {"github": "saleor/saleor", "git_base": "3.22.0", "sha_base": "a" * 40},
            "saleor-dashboard": {"github": "saleor/saleor-dashboard", "git_base": "3.22.9", "sha_base": "b" * 40},
        }}))
        (self.target / "manifest.json").write_text(json.dumps({"schema": "fixture", "files": {}}))

    def test_scaffolds_frozen_package_with_sidecar_and_derived_revisions(self):
        result = scaffold(DEFAULT_SOURCE, self.target, update_manifest=True)
        self.assertTrue(result["base_revisions_derived"])
        self.assertTrue(result["workflow_runtime_sidecar"])
        self.assertEqual((self.target / "instruction.md").read_text(), "Target instruction\n")
        self.assertIn('docker_image = "fixture:base"', (self.target / "task.toml").read_text())
        self.assertIn("task_root: ../workflow-runtime",
                      (self.target / "workflows/single.yaml").read_text())
        self.assertIn("instruction: ../workflow-instruction.md",
                      (self.target / "workflows/lifecycle.yaml").read_text())
        self.assertNotIn("saleor-platform", (self.target / "roles/pm.system.md").read_text())
        revisions = json.loads((self.target / "environment/base-revisions.json").read_text())
        self.assertEqual(revisions["saleor-dashboard"]["commit"], "b" * 40)
        self.assertIn("memory_mb = 16000", (self.target / "workflow-runtime/task.toml").read_text())
        overlay = (self.target / "workflow-runtime/environment/Dockerfile").read_text()
        self.assertIn("FROM fixture:base", overlay)
        self.assertIn("COPY workspace/ /workspace/", overlay)
        manifest = json.loads((self.target / "manifest.json").read_text())
        self.assertIn("workflows/lifecycle.yaml", manifest["files"])
        self.assertIn("workflow-runtime/environment/Dockerfile", manifest["files"])

    def test_is_idempotent_and_refuses_unrequested_replacement(self):
        scaffold(DEFAULT_SOURCE, self.target)
        second = scaffold(DEFAULT_SOURCE, self.target)
        self.assertFalse(second["written"])
        (self.target / "templates/prd.md").write_text("local change\n")
        with self.assertRaisesRegex(ValueError, "Refusing"):
            scaffold(DEFAULT_SOURCE, self.target)
        result = scaffold(DEFAULT_SOURCE, self.target, force=True)
        self.assertIn("templates/prd.md", result["written"])


if __name__ == "__main__":
    unittest.main()
