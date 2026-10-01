"""Versioned reports with explicit scope, absence and comparability states."""

from coverage_eval.metrics import comparison, measured, merge_lines, normalize_pair
from coverage_eval.workspace import source_file


def pair(official, agent, changes, model_hashes, official_hashes, agent_hashes,
         official_status, agent_status):
    # None means unmeasured, while {} is a measured report with no source lines.
    old, new = official or {}, agent or {}
    old, new, _, _ = normalize_pair(old, new, official_hashes, agent_hashes)
    model_stable = {path for path, digest in model_hashes.items() if digest == agent_hashes.get(path)}
    shared_stable = {path for path in model_stable if official_hashes.get(path) == agent_hashes.get(path)}
    return {
        "official_status": official_status,
        "agent_status": agent_status,
        "official": measured(old, changes, changed_eligible=shared_stable) if official is not None else None,
        "agent": measured(new, changes, changed_eligible=model_stable) if agent is not None else None,
        "comparison": comparison(old, new, official_hashes, agent_hashes)
        if official is not None and agent is not None else None,
    }


def build_coverage(repositories, measurements, runs, inventories, changes):
    output = {"scope": "configured suites; line metrics use reported executable lines",
              "repositories": {}, "suites": {}}
    for repo in repositories:
        groups = {"official": [], "agent": []}
        for suite in repo.suites:
            old = measurements["official"].get(suite.name)
            new = measurements["agent"].get(suite.name)
            record = pair(old, new, changes[repo.name], inventories["model"][repo.name],
                          inventories["official"][repo.name], inventories["agent"][repo.name],
                          runs["official"][suite.name]["status"], runs["agent"][suite.name]["status"])
            record.update({"repository": repo.name, "runner": suite.runner,
                           "coverage_reader": suite.coverage_reader,
                           "scope": {"repository_include": repo.source_include,
                                     "repository_exclude": repo.source_exclude,
                                     "suite_include": suite.source_include,
                                     "suite_exclude": suite.source_exclude}})
            record["unreported_source_files"] = {
                group: sorted(path for path in inventories[group][repo.name]
                              if source_file(repo, path, suite) and path not in (lines or {}))
                for group, lines in (("official", old), ("agent", new))
                if lines is not None}
            output["suites"][suite.name] = record
            for group, lines in (("official", old), ("agent", new)):
                if lines is not None:
                    groups[group].append(lines)
        merged = {group: merge_lines(lines) if lines else None for group, lines in groups.items()}
        # A repository may have multiple frameworks; merge coverage by line union.
        states = {}
        for group in groups:
            supported = [runs[group][suite.name]["status"] for suite in repo.suites if suite.coverage_reader]
            if merged[group] is not None:
                states[group] = "partial" if any(state not in ("measured", "no_tests") for state in supported) else "measured"
            else:
                states[group] = "no_tests" if supported and all(state == "no_tests" for state in supported) else "unsupported" if not supported else "error"
        output["repositories"][repo.name] = pair(
            merged["official"], merged["agent"], changes[repo.name], inventories["model"][repo.name],
            inventories["official"][repo.name], inventories["agent"][repo.name], states["official"], states["agent"])
    return output
