#!/usr/bin/env python3
"""Select C/D candidates, counting collection-blocked tests as failed."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def record(repo, suite, path, classname, name, status, **extra):
    classname = f"{repo}.{suite}.{classname}"
    return dict(id=f"{classname}.{name}", repo=repo, suite=suite, path=path,
                classname=classname, name=name, status=status, **extra)


def core(report, suite):
    tests, blocked = [], []
    for case in ET.parse(report).getroot().iter("testcase"):
        error, failure, skipped = (case.find(tag) for tag in ("error", "failure", "skipped"))
        if error is not None and not case.get("classname"):
            blocked.append(dict(repo="saleor", suite=suite, path=case.attrib["file"],
                                reason="\n\n".join(e.text or e.get("message", "")
                                                    for e in case.findall("error"))))
            continue
        status = ("error" if error is not None else "failed" if failure is not None
                  else "skipped" if skipped is not None else "passed")
        tests.append(record("saleor", suite, case.attrib["file"],
                            case.attrib["classname"], case.attrib["name"], status))
    return tests, blocked


def jest(report, multiplicity):
    tests, blocked, duplicates = [], [], []
    for file in read_json(report)["testResults"]:
        path = str(Path(file["name"]).relative_to("/workspace/saleor-dashboard"))
        counts = Counter(test["fullName"] for test in file["assertionResults"])
        seen = Counter()
        if not file["assertionResults"] and file["status"] == "failed":
            blocked.append(dict(repo="saleor-dashboard", suite="dash-unit", path=path,
                                reason=file["message"]))
        for test in file["assertionResults"]:
            title = test["fullName"]
            seen[title] += 1
            key = (path, title)
            multiplicity[key] = counts[title]
            name = title
            if counts[title] > 1:
                name += f" [occurrence={seen[title]}]"
                duplicates.append(dict(path=path, title=title, occurrence=seen[title],
                                       count=counts[title]))
            status = {"passed": "passed", "failed": "failed", "pending": "skipped",
                      "todo": "skipped", "skipped": "skipped"}[test["status"]]
            tests.append(record("saleor-dashboard", "dash-unit", path, path, name, status,
                                original_title=title))
    return tests, blocked, duplicates


def playwright(report):
    tests, setup = [], []

    def walk(suites, titles=()):
        for suite in suites:
            chain = titles + ((suite["title"],) if suite["title"] else ())
            for spec in suite["specs"]:
                # The root suite is the file name; nested describe titles identify the test.
                title = " / ".join((*chain[1:], spec["title"]))
                for test in spec["tests"]:
                    result_statuses = [r["status"] for r in test["results"]]
                    status = ("passed" if test["status"] == "expected"
                              and result_statuses[-1:] == ["passed"]
                              and test["expectedStatus"] == "passed"
                              else "failed" if test["status"] == "unexpected"
                              and any(s in {"failed", "timedOut"} for s in result_statuses)
                              else "unexecuted")
                    item = record("saleor-dashboard", "dash-e2e",
                                  "playwright/tests/" + spec["file"],
                                  test["projectName"] + "." + spec["file"], title, status,
                                  source_status=test["status"], result_statuses=result_statuses)
                    (setup if test["projectName"] == "setup" else tests).append(item)
            walk(suite.get("suites", []), chain)

    data = read_json(report)
    assert not data.get("errors"), data.get("errors")
    walk(data["suites"])
    assert all(test["status"] == "passed" for test in setup), "Playwright setup failed"
    return tests, setup


def load(directory):
    tests, blocked, duplicate_records, multiplicity = [], [], [], {}
    for suite in ("core-unit", "core-e2e"):
        cases, errors = core(directory / f"{suite}-report/results.xml", suite)
        tests.extend(cases)
        blocked.extend(errors)
    cases, errors, duplicates = jest(directory / "dash-unit-report/results.json", multiplicity)
    tests.extend(cases)
    blocked.extend(errors)
    duplicate_records.extend(duplicates)
    cases, setup = playwright(directory / "dash-e2e-report/results.json")
    tests.extend(cases)
    assert len({test["id"] for test in tests}) == len(tests), "normalized ID collision"
    return {test["id"]: test for test in tests}, blocked, setup, duplicate_records, multiplicity


