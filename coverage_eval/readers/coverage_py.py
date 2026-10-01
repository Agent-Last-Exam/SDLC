"""Read Coverage.py JSON, preferring its exact analysis line export."""

import json

from coverage_eval.readers.common import relative_source


class CoveragePyReader:
    def read(self, report, context):
        exact = report.with_name("exact-lines.json")
        precise = exact.is_file()
        data = json.loads((exact if precise else report).read_text())
        result = {}
        for filename, record in data["files"].items():
            relative = relative_source(filename, context)
            if relative is None:
                continue
            if precise:
                executable = set(record["executable_lines"])
                covered = set(record["covered_lines"]) & executable
            else:
                excluded = set(record.get("excluded_lines", []))
                covered = set(record.get("executed_lines", [])) - excluded
                executable = covered | (set(record.get("missing_lines", [])) - excluded)
            result[relative] = (executable, covered)
        return result
