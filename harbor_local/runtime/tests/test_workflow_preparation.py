"""Contract/preparation checks; no Agent, Docker, model, or network calls."""

import copy
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

from harbor_local.runtime.prepare_workflow import HERE, DEFAULT_TASK, compile_workflow, read_yaml, safe_relative, resolve_config


class WorkflowPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        self.contract = read_yaml(HERE / "tasks/saleor-prd-tdd/workflows/design-delivery.yaml")
        # Preserve real inputs while mutating isolated copies of YAML.
        for group in ("roles", "templates", "inputs"):
            self.contract[group] = {k: str((HERE / "tasks/saleor-prd-tdd/workflows" / v).resolve())
                                    for k, v in self.contract[group].items()}
        self.run = read_yaml(HERE / "tasks/saleor-prd-tdd/workflows/single.yaml")
        self.run["contract"] = "contract.yaml"

    def compile(self):
        self.run["task_root"] = str(DEFAULT_TASK)
        (self.root / "contract.yaml").write_text(yaml.safe_dump(self.contract))
        config = self.root / "run.yaml"
        config.write_text(yaml.safe_dump(self.run))
        return compile_workflow(config, verify_repos=False)

    def test_prd_handoff_and_final_scope(self):
        result = self.compile()
        prd, tech = result["stages"]
        ref = "artifact:sprint1/prd/prd"
        self.assertEqual(prd["outputs"][ref], tech["inputs"][ref])
        self.assertEqual(len(tech["outputs"]), 5)
        self.assertEqual(result["contract"]["delivery"]["stop_after"], "sprint1/tech-design")
        self.assertFalse(result["execution_ready"])

    def test_future_or_missing_artifact_is_rejected(self):
        self.contract["stages"][0]["inputs"].append("artifact:sprint1/tech-design/review")
        with self.assertRaisesRegex(ValueError, "future input"):
            self.compile()

    def test_missing_template_rejected(self):
        self.contract["templates"]["prd"] = str(self.root / "missing.md")
        with self.assertRaisesRegex(ValueError, "Missing templates"):
            self.compile()

    def test_output_cannot_write_into_previous_stage(self):
        self.contract["stages"][1]["outputs"]["review"] = "artifacts/sprint1/prd/review.md"
        with self.assertRaisesRegex(ValueError, "outside its stage"):
            self.compile()

    def test_path_escape_rejected(self):
        for path in ("../bad", "/tmp/bad", "artifacts/../bad", "a\\b", "a//b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_relative(path)

    def test_mode_policy_mismatch_rejected(self):
        self.run["execution"]["principal_session"] = "new_per_stage"
        with self.assertRaisesRegex(ValueError, "policies disagree"):
            self.compile()

    def test_all_modes_share_same_contract(self):
        single = self.compile()
        for mode in ("flat", "hierarchical"):
            self.run = read_yaml(HERE / f"tasks/saleor-prd-tdd/workflows/{mode}.yaml")
            self.run["contract"] = "contract.yaml"
            result = self.compile()
            self.assertEqual(result["stages"], single["stages"])
            self.assertFalse(result["execution_ready"])
        self.assertEqual(result["run"]["execution"]["scheduling"], "lead_managed")

    def test_duplicate_keys_rejected(self):
        path = self.root / "duplicate.yaml"
        path.write_text("mode: single\nmode: flat\n")
        with self.assertRaisesRegex(ValueError, "Duplicate YAML key"):
            read_yaml(path)

    def test_task_and_mode_selection(self):
        self.assertEqual(resolve_config(), DEFAULT_TASK / "workflows/single.yaml")
        self.assertEqual(resolve_config(task=self.root, mode="flat"), self.root / "workflows/flat.yaml")
        with self.assertRaisesRegex(ValueError, "either"):
            resolve_config(self.root / "run.yaml", task=self.root)
        with self.assertRaisesRegex(ValueError, "either"):
            resolve_config(self.root / "run.yaml", mode="single")

    def test_relocated_task_prepares_its_own_runtime_and_public_inputs(self):
        from harbor_local.runtime import run_workflow

        task = self.root / "custom-task"
        shutil.copytree(DEFAULT_TASK, task, ignore=shutil.ignore_patterns("repos"))
        repo = task / "environment/repos/fixture"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "README.md").write_text("Task-local fixture\n")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture"], check=True)
        sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        (task / "environment/base-revisions.json").write_text(json.dumps({"fixture": {"commit": sha}}))
        toml = task / "task.toml"
        toml.write_text(toml.read_text().replace("10800.0", "321.0"))
        dockerfile = task / "environment/Dockerfile"
        dockerfile.write_text(dockerfile.read_text() + "\n# Task-owned build\n")
        (task / "instruction.md").write_text("Custom task instruction\n")
        args = ["run_workflow", "--task", str(task), "--mode", "flat", "--prepare-only", "--job-name", "fixture-run"]
        home = self.root / "runtime-home"
        with patch.object(run_workflow, "HERE", home), patch("sys.argv", args), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_workflow.main(), 0)
        prepared = home / ".prepared/fixture-run"
        self.assertEqual((prepared / "task/task.toml").read_bytes(), toml.read_bytes())
        self.assertEqual((prepared / "task/environment/Dockerfile").read_bytes(), dockerfile.read_bytes())
        self.assertEqual((prepared / "workspace/instruction.md").read_text(), "Custom task instruction\n")
        self.assertEqual((prepared / "workspace/repos/fixture/README.md").read_text(), "Task-local fixture\n")
        compiled = json.loads((prepared / "resolved-workflow.json").read_text())
        self.assertEqual(compiled["mode"], "flat")
        for group in compiled["sources"].values():
            self.assertTrue(all(Path(p).is_relative_to(task) for p in group.values()))
        for role in ("pm", "architect"):
            source = task / f"roles/{role}.system.md"
            self.assertEqual((prepared / f"workspace/roles/{role}.system.md").read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
