#!/usr/bin/env python3
"""Score Saleor's C/D reports using the configured F2P and P2P sets."""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

TESTS_DIR = Path(os.environ.get("TESTS_DIR", "/tests"))
VERIFIER_DIR = Path(os.environ.get("VERIFIER_DIR", "/logs/verifier"))
RANK = {"passed": 0, "skipped": 1, "failed": 2}


def load_config():
    return json.loads((TESTS_DIR / "config.json").read_text())


def add(result, node_id, status, message=""):
    current = result.get(node_id)
    value = (status, message or "")
    if current is None or RANK[status] > RANK[current[0]]:
        result[node_id] = value
    elif RANK[status] == RANK[current[0]] and not current[1] and message:
        result[node_id] = value


def normalize_status(value):
    value = str(value or "").strip().lower()
    if value == "passed":
        return "passed"
    if value in {"skipped", "pending", "todo", "expected"}:
        return "skipped"
    return "failed"


def junit_status(testcase):
    for child in testcase:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag in {"failure", "error"}:
            message = "\n".join(
                value.strip()
                for value in (child.attrib.get("message", ""), child.text or "")
                if value.strip()
            )
            return "failed", message
        if tag == "skipped":
            return "skipped", (child.attrib.get("message", "") or "skipped").strip()
    return "passed", ""


def junit_report(path, suite):
    result = {}
    root = ET.parse(path).getroot()
    for testcase in root.iter("testcase"):
        classname = testcase.attrib.get("classname", "").strip()
        name = testcase.attrib.get("name", "").strip()
        if not name:
            continue
        if classname.startswith(("saleor.core-unit.", "saleor.core-e2e.", "saleor-dashboard.")):
            node_id = f"{classname}.{name}" if classname else name
        else:
            node_id = f"saleor.{suite}.{classname}.{name}" if classname else f"saleor.{suite}.{name}"
        status, message = junit_status(testcase)
        add(result, node_id, status, message)
    return result


def jest_report(path):
    result = {}
    document = json.loads(path.read_text())
    for file_result in document.get("testResults", []):
        test_file_path = file_result.get("testFilePath") or file_result.get("name")
        if not test_file_path:
            continue
        absolute = Path(test_file_path)
        relative = absolute.relative_to("/workspace/saleor-dashboard").as_posix()
        assertions = file_result.get("assertionResults", [])
        counts = Counter(
            str(assertion.get("fullName") or assertion.get("title") or "").strip()
            for assertion in assertions
        )
        seen = Counter()
        for assertion in assertions:
            name = str(assertion.get("fullName") or assertion.get("title") or "").strip()
            if not name:
                continue
            seen[name] += 1
            if counts[name] > 1:
                name = f"{name} [occurrence={seen[name]}]"
            node_id = f"saleor-dashboard.dash-unit.{relative}.{name}"
            message = "\n".join(assertion.get("failureMessages", [])).strip()
            add(result, node_id, normalize_status(assertion.get("status")), message)
    return result


def playwright_report(path):
    result = {}

    def visit(suites):
        for suite in suites:
            file_name = suite.get("file")
            for spec in suite.get("specs", []):
                spec_title = str(spec.get("title") or "").strip()
                for test in spec.get("tests", []):
                    project = str(test.get("projectName") or "").strip()
                    if project == "setup" or not file_name or not project:
                        continue
                    statuses = []
                    messages = []
                    for attempt in test.get("results", []):
                        statuses.append(normalize_status(attempt.get("status")))
                        messages.extend(error.get("message", "") for error in attempt.get("errors", []))
                    if "failed" in statuses:
                        status = "failed"
                    elif "passed" in statuses:
                        status = "passed"
                    else:
                        status = "skipped"
                    node_id = (
                        f"saleor-dashboard.dash-e2e.{project}.{Path(file_name).as_posix()}."
                        f"{spec_title}"
                    )
                    add(result, node_id, status, "\n".join(m for m in messages if m).strip())
            visit(suite.get("suites", []))

    document = json.loads(path.read_text())
    visit(document.get("suites", []))
    return result


def parse_report(path):
    if not path.exists():
        return {}
    if path.suffix == ".xml":
        suite = next((part for part in path.parts if part in {"core-unit", "core-e2e"}), None)
        if suite is None:
            root = ET.parse(path).getroot()
            classname = next(
                testcase.attrib.get("classname", "")
                for testcase in root.iter("testcase")
                if testcase.attrib.get("classname", "").startswith("saleor.")
            )
            suite = classname.split(".", 2)[1]
        return junit_report(path, suite)
    if any("dash-unit" in part for part in path.parts):
        return jest_report(path)
    if any("dash-e2e" in part for part in path.parts):
        return playwright_report(path)
    raise ValueError(f"cannot infer report type from {path}")


def default_reports(phase):
    return [
        Path(f"/logs/verifier/{phase}/core-unit/results.xml"),
        Path(f"/logs/verifier/{phase}/core-e2e/results.xml"),
        Path(f"/logs/verifier/{phase}/dash-unit/results.json"),
        Path(f"/logs/verifier/{phase}/dash-e2e/results.json"),
    ]


def reports_for(config, phase):
    configured = config.get("grade", {}).get(f"{phase}_reports")
    return [Path(value) for value in configured] if configured else default_reports(phase)


def load_ids(config, key):
    result = []
    seen = set()
    for value in config.get(key, []):
        node_id = str(value).strip()
        if node_id and node_id not in seen:
            seen.add(node_id)
            result.append(node_id)
    return result


def load_phase(config, phase):
    result = {}
    for path in reports_for(config, phase):
        for node_id, (status, message) in parse_report(path).items():
            add(result, node_id, status, message)
    return result


def bucket(node_ids, result):
    passed = 0
    rows = []
    for node_id in node_ids:
        entry = result.get(node_id)
        if entry is None:
            rows.append({"name": node_id, "status": "failed", "message": "missing from report (not executed or collection failed)"})
            continue
        status, message = entry
        row = {"name": node_id, "status": status}
        if message:
            row["message"] = message
        rows.append(row)
        passed += status == "passed"
    return passed, rows


def write_ctrf(config, p2p_rows, f2p_rows):
    tests = []
    for label, rows in (("p2p", p2p_rows), ("f2p", f2p_rows)):
        for row in rows:
            item = {"name": f"[{label}] {row['name']}", "status": row["status"]}
            if row.get("message"):
                item["message"] = row["message"]
            tests.append(item)
    passed = sum(row["status"] == "passed" for row in tests)
    document = {
        "reportFormat": "CTRF",
        "specVersion": "1.0.0",
        "results": {
            "tool": {"name": config.get("grade", {}).get("tool_label", "saleor-dual-repo")},
            "summary": {"tests": len(tests), "passed": passed, "failed": len(tests) - passed,
                        "skipped": 0, "pending": 0, "other": 0},
            "tests": tests,
        },
    }
    (VERIFIER_DIR / "ctrf.json").write_text(json.dumps(document, indent=2) + "\n")


def require_frozen(config):
    if config.get("status") != "frozen":
        raise SystemExit("Scoring blocked: config.status must be frozen; use diagnose for candidate statistics.")


def grade(diagnostic=False):
    config = load_config()
    if not diagnostic:
        require_frozen(config)
    p2p = load_ids(config, "p2p_node_ids")
    f2p = load_ids(config, "f2p_node_ids")
    pre = load_phase(config, "pre")
    post = load_phase(config, "post")
    p2p_passed, p2p_rows = bucket(p2p, post)
    f2p_passed, f2p_rows = bucket(f2p, post)
    pre_p2p_passed, _ = bucket(p2p, pre)
    pre_f2p_passed, _ = bucket(f2p, pre)
    p2p_total, f2p_total = len(p2p), len(f2p)
    total = p2p_total + f2p_total
    reward = int(
        bool(f2p_total)
        and f2p_passed == f2p_total
        and p2p_passed == p2p_total
        and pre_f2p_passed == 0
        and pre_p2p_passed == p2p_total
    )
    result = {
        "reward": reward,
        "f2p_total": f2p_total,
        "f2p_passed": f2p_passed,
        "p2p_total": p2p_total,
        "p2p_passed": p2p_passed,
        "f2p": f2p_passed / f2p_total if f2p_total else 0.0,
        "p2p": p2p_passed / p2p_total if p2p_total else 1.0,
        "partial": (f2p_passed + p2p_passed) / total if total else 0.0,
        "pre_f2p_passed": pre_f2p_passed,
        "pre_p2p_passed": pre_p2p_passed,
        "reports": {"pre": [str(path) for path in reports_for(config, "pre")], "post": [str(path) for path in reports_for(config, "post")]},
    }
    VERIFIER_DIR.mkdir(parents=True, exist_ok=True)
    if diagnostic:
        result.pop("reward")
        result["status"] = config["status"]
        result["scoreable"] = False
        (VERIFIER_DIR / "diagnostics.json").write_text(json.dumps(result, indent=2) + "\n")
        print(f"Diagnostic only: F2P {f2p_passed}/{f2p_total}; P2P {p2p_passed}/{p2p_total}; no reward written")
        return
    write_ctrf(config, p2p_rows, f2p_rows)
    (VERIFIER_DIR / "reward.json").write_text(json.dumps(result, indent=2) + "\n")
    (VERIFIER_DIR / "reward.txt").write_text(f"{reward}\n")
    print(f"P2P {p2p_passed}/{p2p_total} pass; F2P {f2p_passed}/{f2p_total} pass; PARTIAL {result['partial']:.6f}; REWARD {reward}")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"grade", "diagnose", "check"}:
        print("usage: grader.py grade|diagnose|check", file=sys.stderr)
        return 2
    if sys.argv[1] == "check":
        require_frozen(load_config())
    else:
        grade(diagnostic=sys.argv[1] == "diagnose")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
