from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from coverage_eval.attribution import select_cases, support_changes
from coverage_eval.config import load_profile, parse_profile, profile_dict
from coverage_eval.metrics import merge_lines
from coverage_eval.models import Discovery, TestCase
from coverage_eval.package import build
from coverage_eval.reporting import pair
from coverage_eval.registry import RUNNERS
from coverage_eval.runners.pytest import PytestRunner
from coverage_eval.utils import matches
from coverage_eval.workspace import changed_lines


def example_profile():
    return {"schema_version": 1, "project_id": "billing", "repositories": [{
        "name": "api", "path": "packages/calculator", "base_commit": "abc123",
        "source_include": ["lib/**/*.py"], "test_support_include": ["**/conftest.py"],
        "suites": [{"name": "unit", "runner": "pytest", "coverage_reader": "coverage_py",
                    "test_include": ["tests/**/test_*.py"], "coverage_sources": ["lib"]}]}]}


class ArchitectureTests(unittest.TestCase):
    def test_registered_adapter_needs_no_new_config_branch(self):
        data = example_profile()
        data["repositories"][0]["suites"][0]["runner"] = "alternate-runner"
        with patch.dict(RUNNERS, {"alternate-runner": PytestRunner}):
            self.assertEqual(parse_profile(data).repositories[0].suites[0].runner, "alternate-runner")
    def test_profile_roundtrip_and_other_project_paths(self):
        data = example_profile()
        data["repositories"][0]["suites"].append({**data["repositories"][0]["suites"][0], "name": "integration"})
        profile = parse_profile(data)
        self.assertEqual(parse_profile(json.loads(json.dumps(profile_dict(profile)))), profile)
        self.assertEqual(profile.repositories[0].path, "packages/calculator")

    def test_invalid_profiles_fail_before_execution(self):
        changes = [
            lambda d: d.update({"surprise": True}),
            lambda d: d["repositories"][0]["suites"][0].update({"runner": "missing"}),
            lambda d: d["repositories"][0]["suites"][0].update({"coverage_reader": "missing"}),
            lambda d: d["repositories"][0]["suites"][0].update({"working_directory": "../elsewhere"}),
            lambda d: d.update({"prepare": ["python3", "{unknown}/prepare.py"]}),
            lambda d: d["repositories"][0]["suites"].append(deepcopy(d["repositories"][0]["suites"][0])),
        ]
        for change in changes:
            with self.subTest(change=change):
                data = example_profile()
                change(data)
                with self.assertRaises(ValueError):
                    parse_profile(data)

    def test_globs_include_root_tests_but_star_does_not_cross_directories(self):
        self.assertTrue(matches("test_a.py", ("**/test_*.py",)))
        self.assertTrue(matches("tests/nested/test_a.py", ("tests/**/test_*.py",)))
        self.assertFalse(matches("tests/nested/test_a.py", ("tests/test_*.py",)))

    def test_absent_agent_tests_are_null_instead_of_zero(self):
        report = pair({"lib/a.py": ({1, 2}, {1})}, None, {}, {}, {"lib/a.py": "same"},
                      {"lib/a.py": "same"}, "measured", "no_tests")
        self.assertIsNone(report["agent"])
        self.assertIsNone(report["comparison"])
        self.assertEqual(report["agent_status"], "no_tests")

    def test_zero_is_retained_for_an_actual_measured_report(self):
        report = pair({"lib/a.py": ({1, 2}, {1})}, {"lib/a.py": ({1, 2}, set())}, {},
                      {"lib/a.py": "same"}, {"lib/a.py": "same"}, {"lib/a.py": "same"},
                      "measured", "measured")
        self.assertEqual(report["agent"]["line_percent"], 0)

    def test_fixture_changes_do_not_make_unchanged_test_agent_authored(self):
        case = TestCase("test_a", "tests/test_a.py", "test_a", 8, 9)
        changes = {case.path: {3}}
        selected, uncertain = select_cases([case], changes, {case.path}, Discovery([case]), set())
        self.assertFalse(selected)
        self.assertFalse(uncertain)
        self.assertEqual(support_changes(changes, [case], {case.path}), {case.path: [3]})

    def test_missing_and_duplicate_locations_are_uncertain(self):
        case = TestCase("test_a", "tests/test_a.py", "test_a", uncertainty="duplicate name")
        selected, uncertain = select_cases([case], {case.path: {1}}, set(), Discovery([]), set())
        self.assertFalse(selected)
        self.assertEqual(uncertain[0]["reason"], "duplicate name")

    def test_multiple_suite_reports_union_lines_without_double_counting(self):
        self.assertEqual(merge_lines([{"lib/a.py": ({1, 2}, {1})},
                                      {"lib/a.py": ({1, 2, 3}, {2})}]),
                         {"lib/a.py": ({1, 2, 3}, {1, 2})})

    def test_deletion_hunk_does_not_count_an_unchanged_following_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "a.py").write_text("one\ntwo\nthree\n")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c",
                            "user.email=test@example.com", "commit", "-qm", "base"], check=True)
            base = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            (root / "a.py").write_text("one\nthree\n")
            self.assertEqual(changed_lines(root, base)["a.py"], set())

    def test_custom_harbor_task_keeps_its_image_hooks_and_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = root / "custom-task"
            (task / "tests").mkdir(parents=True)
            (task / "tests/Dockerfile").write_text("FROM local/custom-test:latest\nCOPY . /tests\n")
            (task / "tests/test.sh").write_text("#!/bin/sh\npython3 /tests/grader.py\n")
            toml = '[task]\nname="custom/project"\n[environment]\ndocker_image="local/custom-base:latest"\n[[verifier.collect]]\ncommand="collect-custom-artifacts"\n'
            (task / "task.toml").write_text(toml)
            profile = root / "profile.json"
            profile.write_text(json.dumps(example_profile()))
            output = build(root / "packaged", task=task, profile=profile)
            parsed = tomllib.loads((output / "task.toml").read_text())
            self.assertEqual(parsed["task"]["name"], "custom/project-coverage")
            self.assertEqual(parsed["environment"]["docker_image"], "local/custom-base:latest")
            self.assertEqual(parsed["verifier"]["collect"][0]["command"], "collect-custom-artifacts")
            self.assertEqual((task / "task.toml").read_text(), toml)
            self.assertEqual(load_profile(output / "tests/coverage-profile.json").project_id, "billing")
            self.assertTrue((output / "tests/test.original.sh").is_file())
