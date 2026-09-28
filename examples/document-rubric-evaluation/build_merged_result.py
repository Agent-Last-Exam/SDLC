#!/usr/bin/env python3
"""Rebuild the merged Tech Design example without calling a model."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from runtime.document_rubric import (  # noqa: E402
    Manifest,
    aggregate,
    apply_delivery_gate,
    markdown_report,
    rewardkit_details,
    validate_judgment,
)


SOURCE = HERE / "source-result-v4/document-evaluation.json"
MANIFEST = HERE / "rubrics/document-rubrics.v2.json"
CANDIDATE = HERE / "candidate"
OUTPUT = HERE / "merged-result-v5"
GROUP_ALIASES = {
    "tdd_schema": "tech_design",
    "tdd_quality": "tech_design",
}
REQUIRED_DOCUMENTS = [
    "sprint1/prd/prd.md",
    "sprint1/tech-design/frontend-design.md",
    "sprint1/tech-design/backend-design.md",
    "sprint1/tech-design/interface-contract.md",
    "sprint1/tech-design/target-schema.graphql",
    "sprint1/test-design/test-cases.v1.csv",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    source = json.loads(SOURCE.read_text())
    manifest = Manifest.load(MANIFEST)
    grouped: dict[str, list[dict]] = {group.group_id: [] for group in manifest.groups}
    for row in source["results"]:
        group_id = GROUP_ALIASES.get(row["group_id"], row["group_id"])
        grouped[group_id].append({
            key: row[key]
            for key in ("rubric_id", "verdict", "evidence", "reason", "issue_id")
        })

    judgments = {}
    for group in manifest.groups:
        judgments[group.group_id] = validate_judgment(group, {
            "group_id": group.group_id,
            "results": grouped[group.group_id],
        })

    rewards, report = aggregate(manifest, judgments)
    missing = [path for path in REQUIRED_DOCUMENTS if not (CANDIDATE / path).is_file()]
    rewards, report = apply_delivery_gate(
        rewards, report, REQUIRED_DOCUMENTS, missing
    )
    report["judge"] = {
        "model": source["judge"]["model"],
        "backend": source["judge"]["backend"],
        "replicas": source["judge"]["replicas"],
        "regrade_performed": False,
        "raw_results": "../source-result-v4/document-evaluation.json",
    }
    report["provenance"] = {
        "kind": "deterministic_grouping_example",
        "source_evaluation_sha256": sha256(SOURCE),
        "rubric_manifest_sha256": sha256(MANIFEST),
        "source_rubric_version": source["rubric_version"],
        "source_reward": source["rewards"]["reward"],
        "method": "Preserve final P/F verdicts and merge tdd_schema plus tdd_quality into tech_design.",
        "official_harbor_regrade": False,
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "document-evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    (OUTPUT / "document-evaluation.md").write_text(markdown_report(report))
    (OUTPUT / "reward-details.json").write_text(
        json.dumps(rewardkit_details(report), ensure_ascii=False, indent=2) + "\n"
    )
    (OUTPUT / "reward.json").write_text(
        json.dumps(rewards, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps({
        "reward": rewards["reward"],
        "groups": report["groups"],
        "missing_required_documents": missing,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
