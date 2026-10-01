"""Read Istanbul statement-start lines and merge compatible raw reports."""

import json

from coverage_eval.readers.common import relative_source
from coverage_eval.utils import write_json


class IstanbulReader:
    def read(self, report, context):
        result = {}
        for filename, record in json.loads(report.read_text()).items():
            relative = relative_source(filename, context)
            if relative is None:
                continue
            executable, covered = set(), set()
            for key, location in record["statementMap"].items():
                line = location["start"]["line"]
                executable.add(line)
                if record["s"].get(key, 0) > 0:
                    covered.add(line)
            result[relative] = (executable, covered)
        return result


def merge_istanbul(paths, output):
    merged = {}
    for path in paths:
        for filename, record in json.loads(path.read_text()).items():
            if filename not in merged:
                merged[filename] = record
                continue
            target = merged[filename]
            for key in ("statementMap", "fnMap", "branchMap"):
                if target.get(key) != record.get(key):
                    raise ValueError(f"Istanbul source map mismatch: {filename}")
            for key in ("s", "f"):
                if target.get(key, {}).keys() != record.get(key, {}).keys():
                    raise ValueError(f"Istanbul counter mismatch: {filename}")
                for counter, value in record.get(key, {}).items():
                    target[key][counter] += value
            if target.get("b", {}).keys() != record.get("b", {}).keys():
                raise ValueError(f"Istanbul branch mismatch: {filename}")
            for counter, values in record.get("b", {}).items():
                if len(target["b"][counter]) != len(values):
                    raise ValueError(f"Istanbul branch count mismatch: {filename}")
                target["b"][counter] = [a + b for a, b in zip(target["b"][counter], values)]
    write_json(output, merged)
