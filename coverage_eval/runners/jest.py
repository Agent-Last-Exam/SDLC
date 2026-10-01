"""Jest inventories, TypeScript spans, exact per-file name selection."""

from collections import Counter, defaultdict
from dataclasses import replace
import json
from pathlib import Path
import re
import subprocess

from coverage_eval.models import Capabilities, Discovery, Run, TestCase
from coverage_eval.readers.istanbul import merge_istanbul
from coverage_eval.utils import command, environment, expand, suite_test_files, variables, write_json


def jest_ranges(path, cwd):
    helper = Path(__file__).resolve().parents[1] / "jest_ranges.cjs"
    result = subprocess.run(["node", str(helper), str(path)], cwd=cwd,
                            capture_output=True, text=True, check=False)
    if result.returncode:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


class JestRunner:
    capabilities = Capabilities()

    def discover(self, context, files, *, baseline=False):
        context.output.mkdir(parents=True, exist_ok=True)
        if not files:
            write_json(context.output / "inventory.json", [])
            return Discovery([])
        report = context.output / "results.json"
        values = variables(context.paths, repo=context.repo, output=context.output, suite=context.suite.name)
        argv = expand(context.suite.command or ("node_modules/.bin/jest",), values)
        argv += expand(context.suite.discovery_args, values)
        if baseline:
            argv += expand(context.suite.baseline_args, values)
        argv += ["--json", "--outputFile=" + str(report), "--testLocationInResults",
                 "--runTestsByPath", *[str(context.repo / path) for path in sorted(files)]]
        code = command(argv, cwd=context.cwd, env=environment(context, baseline=baseline),
                       log=context.output / "discovery.log")
        if not report.exists():
            return Discovery([], code or 1, True)
        cases = []
        for file in json.loads(report.read_text()).get("testResults", []):
            path = Path(file["name"]).resolve().relative_to(context.repo.resolve()).as_posix()
            rows = file.get("assertionResults", [])
            counts = Counter(case["fullName"] for case in rows)
            ranges = jest_ranges(context.repo / path, context.cwd)
            for row in rows:
                name, location = row["fullName"], row.get("location")
                reason = "duplicate name or missing location" if counts[name] != 1 or not location else None
                spans = [span for span in ranges or [] if location and span["start"] <= location["line"] <= span["end"]]
                span = max(spans, key=lambda item: item["end"] - item["start"]) if spans else {}
                cases.append(TestCase(path + "::" + name, path, name, span.get("start"), span.get("end"), reason))
        write_json(context.output / "inventory.json", [case.__dict__ for case in cases])
        return Discovery(cases, code, True)

    def _run(self, context, cases):
        context.output.mkdir(parents=True, exist_ok=True)
        values = variables(context.paths, repo=context.repo, output=context.output, suite=context.suite.name)
        argv = expand(context.suite.command or ("node_modules/.bin/jest",), values)
        argv += expand(context.suite.args, values)
        argv += ["--json", "--outputFile=" + str(context.output / "results.json"),
                 "--testLocationInResults", "--coverage", "--coverageReporters=json",
                 "--coverageDirectory=" + str(context.output / "coverage")]
        if cases is not None:
            pattern = "^(?:" + "|".join(re.escape(case.selector) for case in cases) + ")$"
            argv += ["--runTestsByPath", str(context.repo / cases[0].path), "--testNamePattern", pattern]
        else:
            argv += ["--runTestsByPath", *[str(path) for path in suite_test_files(context)]]
        code = command(argv, cwd=context.cwd, env=environment(context), log=context.output / "stdout.txt")
        report = context.output / "coverage/coverage-final.json"
        selection_complete = True
        if cases is not None:
            results = context.output / "results.json"
            observed = {row["fullName"] for file in json.loads(results.read_text()).get("testResults", [])
                        for row in file.get("assertionResults", [])} if results.is_file() else set()
            missing = {case.selector for case in cases} - observed
            if missing:
                selection_complete = False
                write_json(context.output / "missing-selection.json", sorted(missing))
        return Run(code, "measured" if report.exists() and selection_complete else "error",
                   report if report.exists() else None)

    def run(self, context, cases=None):
        if cases is None:
            if not suite_test_files(context):
                return Run(None, "no_tests")
            return self._run(context, None)
        if not cases:
            return Run(None, "no_tests")
        grouped = defaultdict(list)
        for case in cases:
            grouped[case.path].append(case)
        results = []
        for index, (_, selected) in enumerate(sorted(grouped.items())):
            results.append(self._run(replace(context, output=context.output / "runs" / str(index)), selected))
        report = context.output / "coverage/coverage-final.json"
        reports = [run.report for run in results if run.report is not None]
        if reports:
            merge_istanbul(reports, report)
        return Run(max(run.exit_code for run in results),
                   "measured" if len(reports) == len(results) and all(run.status == "measured" for run in results)
                   else "error", report if reports else None)
