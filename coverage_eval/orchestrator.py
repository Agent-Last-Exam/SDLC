"""Coordinate candidate, official and Agent evaluation through adapter contracts."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from coverage_eval.attribution import select_cases, support_changes
from coverage_eval.config import profile_dict
from coverage_eval.models import Context, Discovery, Run
from coverage_eval.registry import READERS, RUNNERS
from coverage_eval.reporting import build_coverage
from coverage_eval.utils import command, expand, git, matches, variables, write_json
from coverage_eval.workspace import (candidate_workspace, changed_lines, hook, patch_paths,
                                     prepare, renamed_test_files, repo_path, reset,
                                     resolve_repositories, restore_tests, snapshot_tests,
                                     source_inventory, test_file, test_support, verify_inputs)


def _files(repo, suite, paths):
    root = repo_path(repo, paths)
    return sorted(path for path in patch_paths(paths.artifacts / repo.model_patch)
                  if matches(path, suite.test_include, suite.test_exclude) and (root / path).is_file())


def _context(repo, suite, paths, group, *, discovery=False):
    directory = paths.output / "coverage" / group / "discovery" / suite.name if discovery else (
        paths.output / "post" / suite.name if group == "official" else paths.output / "coverage" / group / suite.name)
    return Context(repo, suite, repo_path(repo, paths), directory, paths)


def evaluate(profile, paths, *, candidate_kind="agent"):
    if candidate_kind not in {"agent", "reference", "synthetic"}:
        raise ValueError("candidate_kind must be agent, reference or synthetic")
    paths.output.mkdir(parents=True, exist_ok=True)
    report_path = paths.output / "coverage" / "coverage.json"
    if report_path.exists():
        raise ValueError("output already contains a coverage run; choose a fresh output directory")
    result = {"schema_version": 2, "status": "running", "project_id": profile.project_id,
              "candidate_kind": candidate_kind}
    data = profile_dict(profile)
    result["profile_sha256"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    write_json(paths.output / "coverage" / "profile.json", data)
    measurements = {"official": {}, "agent": {}}
    runs = {"official": {}, "agent": {}}
    inventories, changes, baseline = {}, {}, {}
    issues = []
    try:
        repositories = resolve_repositories(profile, paths)
        verify_inputs(repositories, paths)
        result["base_commits"] = {repo.name: repo.base_commit for repo in repositories}
        result["model_patch_sha256"] = {repo.name: hashlib.sha256(
            (paths.artifacts / repo.model_patch).read_bytes()).hexdigest() for repo in repositories}
        result["official_test_patch_sha256"] = {repo.name: hashlib.sha256(
            Path(repo.test_patch).read_bytes()).hexdigest() if repo.test_patch else None for repo in repositories}
        provenance = paths.artifacts / "provenance.json"
        if provenance.is_file():
            result["input_provenance"] = json.loads(provenance.read_text())

        reset(repositories, paths)
        for repo in repositories:
            for suite in repo.suites:
                runner = RUNNERS[suite.runner]()
                if runner.capabilities.discover:
                    context = _context(repo, suite, paths, "base", discovery=True)
                    baseline[suite.name] = runner.discover(context, _files(repo, suite, paths), baseline=True)
                else:
                    baseline[suite.name] = Discovery([])

        candidate_workspace(repositories, paths)
        inventories["model"] = source_inventory(repositories, paths)
        base_files, renamed = {}, {}
        for repo in repositories:
            root = repo_path(repo, paths)
            changes[repo.name] = changed_lines(root, repo.base_commit)
            base_files[repo.name] = set(git(root, "ls-tree", "-r", "--name-only", repo.base_commit).splitlines())
            renamed[repo.name] = renamed_test_files(root, repo.base_commit)
        snapshots = snapshot_tests(repositories, paths)
        write_json(paths.output / "coverage/agent/model-changed-lines.json",
                   {name: {path: sorted(lines) for path, lines in files.items()} for name, files in changes.items()})
        write_json(paths.output / "coverage/agent/model-source-inventory.json", inventories["model"])

        prepare(profile, repositories, paths, "official-prepare")
        hook(profile.services, paths, "services")
        inventories["official"] = source_inventory(repositories, paths)
        for repo in repositories:
            for suite in repo.suites:
                context = _context(repo, suite, paths, "official")
                run = RUNNERS[suite.runner]().run(context, None)
                _record_run(run, context, "official", measurements, runs, issues)
        _check_source(repositories, paths, inventories["official"], issues, "official")
        write_json(paths.output / "coverage/official/source-inventory.json", inventories["official"])
        if profile.grader:
            code = command(expand(profile.grader, variables(paths)), cwd=paths.workspace,
                           log=paths.output / "coverage/hooks/grader.log")
            result["grader_exit_code"] = code
            if code:
                issues.append({"group": "official", "reason": "grader failed", "exit_code": code})
                (paths.output / "reward.txt").write_text("-1\n")
            reward = paths.output / "reward.json"
            result["standard_score"] = json.loads(reward.read_text()) if reward.is_file() else None

        prepare(profile, repositories, paths, "agent-prepare")
        restore_tests(snapshots, repositories, paths)
        inventories["agent"] = source_inventory(repositories, paths)
        selection = {"suites": {}, "unsupported_test_files": {}, "deleted_test_files": {},
                     "agent_test_file_sha256": {name: {
                         path: hashlib.sha256(content[0]).hexdigest() if content else None
                         for path, content in files.items()} for name, files in snapshots.items()}}
        for repo in repositories:
            test_changes = {path: lines for path, lines in changes[repo.name].items() if test_file(repo, path)}
            supported = [suite for suite in repo.suites if RUNNERS[suite.runner]().capabilities.select_cases
                         and RUNNERS[suite.runner]().capabilities.discover]
            unsupported = sorted(path for path in test_changes
                                 if not any(matches(path, suite.test_include, suite.test_exclude) for suite in supported))
            selection["unsupported_test_files"][repo.name] = unsupported
            selection["deleted_test_files"][repo.name] = sorted(path for path in snapshots[repo.name]
                                                               if snapshots[repo.name][path] is None)
            if unsupported:
                issues.append({"repository": repo.name, "reason": "unsupported Agent test files", "files": unsupported})
            for suite in repo.suites:
                runner = RUNNERS[suite.runner]()
                context = _context(repo, suite, paths, "agent")
                if not runner.capabilities.discover or not runner.capabilities.select_cases:
                    run = Run(None, "unsupported")
                else:
                    discovery = runner.discover(_context(repo, suite, paths, "agent", discovery=True),
                                                _files(repo, suite, paths), baseline=False)
                    suite_changes = {path: lines for path, lines in test_changes.items()
                                     if matches(path, suite.test_include, suite.test_exclude)}
                    cases, uncertain = select_cases(discovery.cases, suite_changes, base_files[repo.name],
                                                    baseline[suite.name], renamed[repo.name])
                    support = {path: lines for path, lines in changes[repo.name].items() if test_support(repo, path)}
                    selection["suites"][suite.name] = {
                        "repository": repo.name, "runner": suite.runner,
                        "selected_cases": [asdict(case) for case in cases], "uncertain": uncertain,
                        "changed_test_files": sorted(suite_changes), "renamed_files": sorted(renamed[repo.name]),
                        "support_changes": support_changes(support, discovery.cases, set(support)),
                        "base_discovery_exit_code": baseline[suite.name].exit_code,
                        "agent_discovery_exit_code": discovery.exit_code,
                        "discovery_executes_tests": discovery.executed_tests}
                    if uncertain or baseline[suite.name].exit_code or discovery.exit_code:
                        issues.append({"suite": suite.name, "reason": "incomplete test attribution or discovery"})
                    run = runner.run(context, cases)
                _record_run(run, context, "agent", measurements, runs, issues)
        _check_source(repositories, paths, inventories["agent"], issues, "agent")
        write_json(paths.output / "coverage/agent/source-inventory.json", inventories["agent"])
        write_json(paths.output / "coverage/agent/selection.json", selection)
        result["selection"] = selection
        result["coverage"] = build_coverage(repositories, measurements, runs, inventories, changes)
        coverage_errors = any(run["status"] == "error" for group in runs.values() for run in group.values())
        result["status"] = "error" if coverage_errors else "partial" if issues else "complete"
    except Exception as exc:
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
        if profile.grader and not (paths.output / "reward.txt").exists():
            (paths.output / "reward.txt").write_text("-1\n")
        raise
    finally:
        result["runs"] = runs
        result["issues"] = issues
        write_json(report_path, result)
    return result


def _record_run(run, context, group, measurements, runs, issues):
    context.output.mkdir(parents=True, exist_ok=True)
    if run.exit_code is not None:
        (context.output / "exit-code.txt").write_text(str(run.exit_code) + "\n")
    runs[group][context.suite.name] = {"status": run.status, "exit_code": run.exit_code,
                                     "raw_report": str(run.report) if run.report else None,
                                     "capabilities": asdict(RUNNERS[context.suite.runner]().capabilities)}
    lines = None
    if context.suite.coverage_reader and run.report is not None and run.status != "no_tests":
        if not run.report.is_file():
            raise RuntimeError(f"missing coverage report: {run.report}")
        lines = READERS[context.suite.coverage_reader]().read(run.report, context)
    measurements[group][context.suite.name] = lines
    if group == "official" and run.status == "no_tests":
        issues.append({"suite": context.suite.name, "group": group, "reason": "official suite collected no tests"})
    if run.exit_code not in (None, 0) or run.status == "error":
        issues.append({"suite": context.suite.name, "group": group, "reason": "suite failed or coverage missing",
                       "exit_code": run.exit_code})
    write_json(context.output / "run.json", runs[group][context.suite.name])


def _check_source(repositories, paths, before, issues, group):
    after = source_inventory(repositories, paths)
    for repo in repositories:
        changed = [path for path in set(before[repo.name]) | set(after[repo.name])
                   if before[repo.name].get(path) != after[repo.name].get(path)]
        if changed:
            issues.append({"repository": repo.name, "group": group,
                           "reason": "production source changed during tests", "files": sorted(changed)})
            # Do not compare a report whose corresponding source was mutated.
            for path in changed:
                before[repo.name].pop(path, None)
