"""Real runner smoke tests. Run in an image containing pytest-cov and Jest."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from coverage_eval.config import load_profile
from coverage_eval.models import Context, Paths, TestCase
from coverage_eval.orchestrator import evaluate
from coverage_eval.runners.pytest import PytestRunner
from coverage_eval.runners.jest import JestRunner


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


PY_BASE = 'def classify(value):\n    if value < 0:\n        return "negative"\n    return "positive"\n'
PY_TARGET = 'def classify(value):\n    if value < 0:\n        return "negative"\n    if value == 0:\n        return "zero"\n    return "positive"\n'
PY_ORIGINAL = 'from lib.classifier import classify\n\ndef test_positive():\n    assert classify(1) == "positive"\n'
PY_AGENT = '\ndef test_negative():\n    assert classify(-1) == "negative"\n\ndef test_zero():\n    assert classify(0) == "zero"\n'
JS_BASE = 'exports.classify = value => {\n  if (value < 0) {\n    return "negative";\n  }\n  return "positive";\n};\n'
JS_TARGET = 'exports.classify = value => {\n  if (value < 0) {\n    return "negative";\n  }\n  if (value === 0) {\n    return "zero";\n  }\n  return "positive";\n};\n'
JS_ORIGINAL = 'const { classify } = require("../lib/classifier");\ntest("positive", () => { expect(classify(1)).toBe("positive"); });\n'
JS_AGENT = 'test("negative", () => { expect(classify(-1)).toBe("negative"); });\ntest("zero", () => { expect(classify(0)).toBe("zero"); });\n'


class AdapterIntegrationTests(unittest.TestCase):
    def setUp(self):
        artifacts = os.environ.get("COVERAGE_INTEGRATION_ARTIFACTS")
        if artifacts:
            Path(artifacts).mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="coverage-adapter-", dir=artifacts))
        if not artifacts:
            self.addCleanup(shutil.rmtree, self.root)
        self.workspace = self.root / "workspace"
        self.artifacts = self.root / "patches"
        self.artifacts.mkdir()

    def candidate(self, name, path, baseline, target, *, node_modules=None):
        repo = self.workspace / path
        repo.mkdir(parents=True)
        git(repo, "init", "-q")
        for file, content in baseline.items():
            destination = repo / file
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
        if node_modules:
            (repo / "node_modules").symlink_to(node_modules)
        git(repo, "add", ".")
        git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "base")
        base = git(repo, "rev-parse", "HEAD")
        for file, content in target.items():
            destination = repo / file
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
        git(repo, "add", "-N", ".")
        (self.artifacts / (name + ".model.patch")).write_text(git(repo, "diff", "--binary", "--full-index", base) + "\n")
        git(repo, "reset", "--hard", base)
        return base

    def run_profile(self, repositories):
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"schema_version": 1, "project_id": "independent-projects", "repositories": repositories}))
        return evaluate(load_profile(profile), Paths(self.workspace, self.root / "tests", self.artifacts, self.root / "result"),
                        candidate_kind="synthetic")

    def python_repo(self):
        base = self.candidate("billing-api", "packages/calculator", {
            "lib/classifier.py": PY_BASE, "tests/main/test_original.py": PY_ORIGINAL,
            "tests/extra/test_existing.py": PY_ORIGINAL,
        }, {"lib/classifier.py": PY_TARGET, "tests/main/test_original.py": PY_ORIGINAL + PY_AGENT})
        suites = [{"name": name, "runner": "pytest", "coverage_reader": "coverage_py",
                   "command": [sys.executable, "-m", "pytest"], "args": ["-p", "pytest_cov"],
                   "test_include": [pattern], "coverage_sources": ["lib"],
                   "env": {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}}
                  for name, pattern in [("python-main", "tests/main/test_*.py"), ("python-extra", "tests/extra/test_*.py")]]
        return {"name": "billing-api", "path": "packages/calculator", "base_commit": base,
                "source_include": ["lib/**/*.py"], "suites": suites}

    def direct_context(self, repo):
        profile = self.root / "direct-profile.json"
        profile.write_text(json.dumps({"schema_version": 1, "project_id": "selection-check", "repositories": [repo]}))
        repository = load_profile(profile).repositories[0]
        return Context(repository, repository.suites[0], self.workspace / repository.path,
                       self.root / "direct-result", Paths(self.workspace, self.root / "tests", self.artifacts, self.root / "result"))

    @unittest.skipUnless(importlib.util.find_spec("pytest_cov"), "requires pytest-cov")
    def test_pytest_missing_selected_case_is_an_error(self):
        context = self.direct_context(self.python_repo())
        run = PytestRunner().run(context, [TestCase("tests/main/test_original.py::test_missing",
                                                   "tests/main/test_original.py", "tests/main/test_original.py::test_missing")])
        self.assertNotEqual(run.exit_code, 0)

    @unittest.skipUnless(os.environ.get("COVERAGE_JEST_NODE_MODULES"), "requires COVERAGE_JEST_NODE_MODULES")
    def test_jest_missing_selected_case_is_an_error_even_if_jest_exits_zero(self):
        nodes = Path(os.environ["COVERAGE_JEST_NODE_MODULES"])
        base = self.candidate("ui", "ui", {"lib/classifier.js": JS_BASE,
                              "tests/classifier.test.js": JS_ORIGINAL,
                              "jest.config.json": '{"testEnvironment":"node","transform":{}}'}, {}, node_modules=nodes)
        context = self.direct_context({"name": "ui", "path": "ui", "base_commit": base,
                    "source_include": ["lib/**/*.js"], "suites": [{"name": "ui-unit", "runner": "jest",
                    "coverage_reader": "istanbul", "test_include": ["tests/**/*.test.js"],
                    "command": [str(nodes / ".bin/jest")], "args": ["--runInBand", "--config", "jest.config.json"]}]})
        run = JestRunner().run(context, [TestCase("tests/classifier.test.js::missing", "tests/classifier.test.js", "missing")])
        self.assertEqual(run.status, "error")

    @unittest.skipUnless(importlib.util.find_spec("pytest_cov"), "requires pytest-cov")
    def test_real_pytest_dual_groups_multiple_suites_and_no_agent_tests(self):
        result = self.run_profile([self.python_repo()])
        self.assertEqual(result["status"], "complete", result.get("issues"))
        report = result["coverage"]
        self.assertGreater(report["repositories"]["billing-api"]["comparison"]["agent_only_covered_lines"], 0)
        selected = result["selection"]["suites"]["python-main"]["selected_cases"]
        self.assertEqual(len(selected), 2)
        self.assertEqual(report["suites"]["python-extra"]["agent_status"], "no_tests")
        self.assertIsNone(report["suites"]["python-extra"]["agent"])
        self.assertEqual(result["candidate_kind"], "synthetic")

    @unittest.skipUnless(importlib.util.find_spec("pytest_cov") and os.environ.get("COVERAGE_JEST_NODE_MODULES"),
                         "requires pytest-cov and COVERAGE_JEST_NODE_MODULES")
    def test_real_multi_repo_pytest_and_jest_with_non_saleor_layout(self):
        nodes = Path(os.environ["COVERAGE_JEST_NODE_MODULES"])
        base = self.candidate("widget-ui", "ui/web", {
            "lib/classifier.js": JS_BASE, "tests/classifier.test.js": JS_ORIGINAL,
            "jest.config.json": json.dumps({"testEnvironment": "node", "transform": {},
                                            "collectCoverageFrom": ["lib/**/*.js"]}),
        }, {"lib/classifier.js": JS_TARGET, "tests/classifier.test.js": JS_ORIGINAL + JS_AGENT}, node_modules=nodes)
        js = {"name": "widget-ui", "path": "ui/web", "base_commit": base, "source_include": ["lib/**/*.js"],
              "suites": [{"name": "javascript-unit", "runner": "jest", "coverage_reader": "istanbul",
                          "test_include": ["tests/**/*.test.js"], "command": [str(nodes / ".bin/jest")],
                          "args": ["--runInBand", "--config", "jest.config.json"],
                          "discovery_args": ["--runInBand", "--config", "jest.config.json"]}]}
        result = self.run_profile([self.python_repo(), js])
        self.assertEqual(result["status"], "complete", result.get("issues"))
        self.assertEqual(set(result["coverage"]["repositories"]), {"billing-api", "widget-ui"})
        for name in ("billing-api", "widget-ui"):
            comparison = result["coverage"]["repositories"][name]["comparison"]
            self.assertGreater(comparison["agent_only_covered_lines"], 0)
            self.assertFalse(comparison["uncomparable_files"])
        self.assertEqual(len(result["selection"]["suites"]["javascript-unit"]["selected_cases"]), 2)


if __name__ == "__main__":
    unittest.main()
