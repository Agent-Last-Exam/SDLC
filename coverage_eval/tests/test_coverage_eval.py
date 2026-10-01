from pathlib import Path
import json
import subprocess
import tarfile
import tempfile
import unittest

from coverage_eval.package import build
from coverage_eval.models import Context, Discovery, Paths, Repository, Suite, TestCase
from coverage_eval.runners.pytest import python_case_span
from coverage_eval.attribution import select_cases
from coverage_eval.workspace import renamed_test_files, changed_lines, test_file as is_test_file
from coverage_eval.metrics import comparison, normalize_pair
from coverage_eval.readers.coverage_py import CoveragePyReader
from coverage_eval.readers.istanbul import IstanbulReader
from coverage_eval.config import load_profile
from coverage_eval.snapshot_to_patch import convert
from runtime.workspace_snapshot import inventory


class CoverageEvalTests(unittest.TestCase):
    def test_generated_task_keeps_frozen_input_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            task = build(Path(temporary) / "coverage-task")
            self.assertIn("saleor-3.23-coverage", (task / "task.toml").read_text())
            self.assertIn("coverage_eval.runner", (task / "tests/test.sh").read_text())
            self.assertTrue((task / "tests/saleor.test.patch").is_file())
            self.assertTrue((task / "environment/base-revisions.json").is_file())
            self.assertTrue((task / "public/query.md").is_file())

    def test_changed_existing_pytest_body_is_agent_test(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "saleor/core/tests/test_example.py"
            path.parent.mkdir(parents=True)
            path.write_text("@pytest.mark.unit\ndef test_a():\n    assert 1 == 2\n\ndef test_b():\n    assert 1\n")
            relative = str(path.relative_to(root))
            span_a = python_case_span(root, relative, 2)
            span_b = python_case_span(root, relative, 5)
            cases = [TestCase("a", relative, "a", *span_a), TestCase("b", relative, "b", *span_b)]
            for changed in ({3}, {1}):
                selected, uncertain = select_cases(cases, {relative: changed}, {relative}, Discovery(cases), set())
                self.assertEqual([case.id for case in selected], ["a"])
                self.assertFalse(uncertain)

    def test_jest_selection_uses_new_name_and_changed_location(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            file = root / "src/foo.test.ts"
            file.parent.mkdir(parents=True)
            file.write_text("test('old', () => {\n  expect(2).toBe(2);\n});\ntest('new', () => {});\n")
            cases = [TestCase("src/foo.test.ts::old", "src/foo.test.ts", "old", 1, 3),
                     TestCase("src/foo.test.ts::new", "src/foo.test.ts", "new", 4, 4)]
            selected, unknown = select_cases(cases, {"src/foo.test.ts": {2}},
                                            {"src/foo.test.ts"}, Discovery(cases[:1]), set())
            self.assertEqual([case.selector for case in selected], ["old", "new"])
            self.assertFalse(unknown)

    def test_comparison_rejects_different_source_hash(self):
        old = {"src/a.ts": ({1, 2}, {1})}
        new = {"src/a.ts": ({1, 2}, {2})}
        result = comparison(old, new, {"src/a.ts": "before"}, {"src/a.ts": "after"})
        self.assertEqual(result["comparison_executable_lines"], 0)
        self.assertEqual(result["uncomparable_files"], ["src/a.ts"])

    def test_same_source_uses_union_denominator_when_jest_omits_lines(self):
        old = {"src/a.ts": ({1, 2, 3}, {1, 2})}
        new = {"src/a.ts": ({1}, {1})}
        first, second, comparable, divergent = normalize_pair(
            old, new, {"src/a.ts": "same"}, {"src/a.ts": "same"})
        self.assertEqual(first["src/a.ts"], ({1, 2, 3}, {1, 2}))
        self.assertEqual(second["src/a.ts"], ({1, 2, 3}, {1}))
        self.assertEqual(comparable, {"src/a.ts"})
        self.assertFalse(divergent)

    def test_changed_line_map_uses_candidate_line_numbers(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            source = repo / "src/a.ts"
            source.parent.mkdir()
            source.write_text("first\nsecond\nthird\n")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test",
                            "-c", "user.email=test@example.com", "commit", "-qm", "base"],
                           check=True)
            base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                           text=True).strip()
            source.write_text("first\nchanged\nthird\nadded\n")
            self.assertEqual(changed_lines(repo, base)["src/a.ts"], {2, 4})

    def test_git_detects_renamed_test_without_treating_it_as_new(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            old = repo / "test_old.py"
            old.write_text("def test_same():\n    assert True\n")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test",
                            "-c", "user.email=test@example.com", "commit", "-qm", "base"],
                           check=True)
            base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                           text=True).strip()
            subprocess.run(["git", "-C", str(repo), "mv", "test_old.py", "test_new.py"],
                           check=True)
            self.assertEqual(renamed_test_files(repo, base), {"test_new.py"})

    def test_raw_coverage_formats_normalize_to_executable_and_hit_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = Suite("unit", "pytest", "coverage_py", ("**/test_*.py",))
            repo = Repository("arbitrary", str(root), (suite,), source_include=("lib/**",),
                              test_support_include=("**/conftest.py",))
            ctx = Context(repo, suite, root, root, Paths())
            py = root / "python.json"
            py.write_text(json.dumps({"files": {"lib/a.py": {
                "executed_lines": [1, 3, 4], "missing_lines": [2], "excluded_lines": [4]},
                "lib/conftest.py": {"executed_lines": [1], "missing_lines": []}}}))
            self.assertEqual(CoveragePyReader().read(py, ctx)["lib/a.py"], ({1, 2, 3}, {1, 3}))
            self.assertNotIn("lib/conftest.py", CoveragePyReader().read(py, ctx))
            (root / "exact-lines.json").write_text(json.dumps({"files": {
                "lib/a.py": {"executable_lines": [1, 2], "covered_lines": [1]}}}))
            self.assertEqual(CoveragePyReader().read(py, ctx)["lib/a.py"], ({1, 2}, {1}))
            js = root / "istanbul.json"
            js.write_text(json.dumps({str(root / "lib/a.ts"): {
                "statementMap": {"0": {"start": {"line": 4}}, "1": {"start": {"line": 5}}},
                "s": {"0": 2, "1": 0}}}))
            self.assertEqual(IstanbulReader().read(js, ctx)["lib/a.ts"], ({4, 5}, {4}))

    def test_test_file_detection_covers_profile_test_patterns(self):
        repos = load_profile().repositories
        self.assertTrue(is_test_file(repos[0], "saleor/core/tests/test_core.py"))
        self.assertTrue(is_test_file(repos[1], "src/components/foo.test.tsx"))
        self.assertTrue(is_test_file(repos[1], "src/__tests__/foo.ts"))
        self.assertFalse(is_test_file(repos[1], "src/components/foo.tsx"))

    def test_workflow_snapshot_converts_to_base_relative_patch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bases = root / "bases"
            candidate = root / "candidate"
            candidate.mkdir()
            metadata = {"repos": {}}
            for name in ("saleor", "saleor-dashboard"):
                base = bases / name
                base.mkdir(parents=True)
                subprocess.run(["git", "init", "-q", str(base)], check=True)
                (base / "source.txt").write_text("before\n")
                subprocess.run(["git", "-C", str(base), "add", "."], check=True)
                subprocess.run(["git", "-C", str(base), "-c", "user.name=Test",
                                "-c", "user.email=test@example.com", "commit", "-qm", "base"],
                               check=True)
                sha = subprocess.check_output(["git", "-C", str(base), "rev-parse", "HEAD"],
                                              text=True).strip()
                metadata["repos"][name] = {"sha_base": sha}
                dest = candidate / name
                dest.mkdir()
                (dest / "source.txt").write_text("after\n")
            (candidate / "saleor" / "test_new.py").write_text("def test_new(): pass\n")
            sealed = inventory(candidate)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps(sealed))
            spec = root / "patch_manifest.json"
            spec.write_text(json.dumps(metadata))
            archive = root / "repos.tar"
            with tarfile.open(archive, "w") as handle:
                handle.add(candidate, arcname="repos")
            output = root / "patches"
            convert(archive, manifest, bases, spec, output)
            for name in metadata["repos"]:
                patch_file = output / f"{name}.model.patch"
                self.assertIn("source.txt", patch_file.read_text())
                subprocess.run(["git", "-C", str(bases / name), "apply", "--check",
                                str(patch_file)], check=True)


if __name__ == "__main__":
    unittest.main()
