"""pytest collection, source spans, exact selection and Coverage.py capture."""

import ast
import json
from pathlib import Path
import sys

from coverage_eval.models import Capabilities, Discovery, Run, TestCase
from coverage_eval.utils import command, environment, expand, suite_test_files, variables, write_json


def python_case_span(repo, path, line):
    try:
        tree = ast.parse((repo / path).read_text())
    except (OSError, SyntaxError, UnicodeError):
        return None, None
    functions = [node for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.lineno <= line <= node.end_lineno]
    if not functions:
        return None, None
    node = min(functions, key=lambda item: item.end_lineno - item.lineno)
    first = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
    return first, node.end_lineno


class PytestRunner:
    capabilities = Capabilities()

    def validate(self, suite):
        if not suite.coverage_sources:
            raise ValueError(f"{suite.name}: coverage_sources is required for pytest")

    def discover(self, context, files, *, baseline=False):
        context.output.mkdir(parents=True, exist_ok=True)
        if not files:
            write_json(context.output / "inventory.json", [])
            return Discovery([])
        report = context.output / "inventory.json"
        env = environment(context, baseline=baseline)
        env["COVERAGE_PYTEST_INVENTORY"] = str(report)
        values = variables(context.paths, repo=context.repo, output=context.output, suite=context.suite.name)
        argv = expand(context.suite.command or ("pytest",), values)
        argv += ["--collect-only", "-q", "--continue-on-collection-errors", "-p", "coverage_eval.pytest_plugin"]
        argv += expand(context.suite.discovery_args, values)
        if baseline:
            argv += expand(context.suite.baseline_args, values)
        argv += [str(context.repo / path) for path in sorted(files)]
        code = command(argv, cwd=context.cwd, env=env, log=context.output / "discovery.log")
        cases = []
        for item in json.loads(report.read_text()) if report.exists() else []:
            path = (context.cwd / item["path"]).resolve().relative_to(context.repo.resolve()).as_posix()
            start, end = python_case_span(context.repo, path, item["line"])
            cases.append(TestCase(item["id"], path, item["id"], start, end))
        return Discovery(cases, code if report.exists() else code or 1)

    def run(self, context, cases=None):
        if cases == []:
            return Run(None, "no_tests")
        files = suite_test_files(context) if cases is None else sorted({context.repo / case.path for case in cases})
        if not files:
            return Run(None, "no_tests")
        context.output.mkdir(parents=True, exist_ok=True)
        report = context.output / "coverage.json"
        env = environment(context)
        env["COVERAGE_FILE"] = str(context.output / ".coverage")
        values = variables(context.paths, repo=context.repo, output=context.output, suite=context.suite.name)
        argv = expand(context.suite.command or ("pytest",), values)
        argv += expand(context.suite.args, values)
        argv += ["--junitxml=" + str(context.output / "results.xml"), "-o", "junit_family=legacy",
                 "-p", "coverage_eval.pytest_plugin", "--cov-branch", "--cov-report=json:" + str(report)]
        argv += ["--cov=" + source for source in context.suite.coverage_sources]
        if cases is not None:
            selected = context.output / "selected.json"
            write_json(selected, [case.selector for case in cases])
            env["COVERAGE_SELECTED_NODEIDS"] = str(selected)
        argv += [str(path) for path in files]
        code = command(argv, cwd=context.cwd, env=env, log=context.output / "stdout.txt")
        if report.exists():
            helper = Path(__file__).resolve().parents[1] / "python_lines.py"
            precise = command([sys.executable, str(helper), "--raw-json", str(report),
                               "--repo", str(context.cwd), "--data-file", env["COVERAGE_FILE"],
                               "--output", str(context.output / "exact-lines.json")],
                              cwd=context.cwd, env=env, log=context.output / "exact-lines.log")
            if precise:
                raise RuntimeError(f"exact Python line export failed: {context.output}")
        status = "no_tests" if code == 5 and cases is None else "measured" if report.exists() else "error"
        return Run(code, status, report if report.exists() else None)
