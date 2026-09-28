"""Validated contracts and aggregation for document-rubric evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


ROOTS = {"candidate", "public", "base", "templates", "private"}
AGGREGATIONS = {"min_group_pass_rate", "weighted_pass_rate", "all_pass"}


def _slug(value: Any, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", value):
        raise ValueError(f"{field} must be a lowercase slug: {value!r}")
    return value


def _relative(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or str(path) != value:
        raise ValueError(f"{field} must be a canonical relative path: {value!r}")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty text")
    return value.strip()


@dataclass(frozen=True)
class Evidence:
    root: str
    path: str
    purpose: str
    required: bool

    @classmethod
    def parse(cls, value: Any, field: str) -> "Evidence":
        if not isinstance(value, dict):
            raise ValueError(f"{field} must be an object")
        unknown = set(value) - {"root", "path", "purpose", "required"}
        if unknown:
            raise ValueError(f"{field} has unknown keys: {sorted(unknown)}")
        root = value.get("root")
        if root not in ROOTS:
            raise ValueError(f"{field}.root must be one of {sorted(ROOTS)}")
        required = value.get("required", True)
        if not isinstance(required, bool):
            raise ValueError(f"{field}.required must be boolean")
        return cls(
            root=root,
            path=_relative(value.get("path"), f"{field}.path"),
            purpose=_text(value.get("purpose", "evaluation evidence"), f"{field}.purpose"),
            required=required,
        )


@dataclass(frozen=True)
class Rubric:
    rubric_id: str
    title: str
    criteria: str
    refs: tuple[str, ...]
    weight: float
    critical: bool

    @classmethod
    def parse(cls, value: Any, field: str) -> "Rubric":
        if not isinstance(value, dict):
            raise ValueError(f"{field} must be an object")
        unknown = set(value) - {"rubric_id", "title", "criteria", "refs", "weight", "critical"}
        if unknown:
            raise ValueError(f"{field} has unknown keys: {sorted(unknown)}")
        rubric_id = value.get("rubric_id")
        if not isinstance(rubric_id, str) or not re.fullmatch(r"[A-Z][A-Z0-9_-]*", rubric_id):
            raise ValueError(f"{field}.rubric_id must be an uppercase stable ID")
        refs = value.get("refs", [])
        if not isinstance(refs, list) or not all(isinstance(ref, str) and ref.strip() for ref in refs):
            raise ValueError(f"{field}.refs must be a list of nonempty strings")
        weight = value.get("weight", 1)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
            raise ValueError(f"{field}.weight must be positive")
        critical = value.get("critical", False)
        if not isinstance(critical, bool):
            raise ValueError(f"{field}.critical must be boolean")
        return cls(
            rubric_id=rubric_id,
            title=_text(value.get("title"), f"{field}.title"),
            criteria=_text(value.get("criteria"), f"{field}.criteria"),
            refs=tuple(ref.strip() for ref in refs),
            weight=float(weight),
            critical=critical,
        )


@dataclass(frozen=True)
class Group:
    group_id: str
    title: str
    stage: str
    evidence: tuple[Evidence, ...]
    rubrics: tuple[Rubric, ...]

    @classmethod
    def parse(cls, value: Any, field: str) -> "Group":
        if not isinstance(value, dict):
            raise ValueError(f"{field} must be an object")
        unknown = set(value) - {"group_id", "title", "stage", "evidence", "rubrics"}
        if unknown:
            raise ValueError(f"{field} has unknown keys: {sorted(unknown)}")
        evidence = value.get("evidence")
        rubrics = value.get("rubrics")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"{field}.evidence must be a nonempty list")
        if not isinstance(rubrics, list) or not rubrics:
            raise ValueError(f"{field}.rubrics must be a nonempty list")
        parsed_rubrics = tuple(Rubric.parse(item, f"{field}.rubrics[{index}]")
                               for index, item in enumerate(rubrics))
        ids = [item.rubric_id for item in parsed_rubrics]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{field} contains duplicate rubric IDs")
        return cls(
            group_id=_slug(value.get("group_id"), f"{field}.group_id"),
            title=_text(value.get("title"), f"{field}.title"),
            stage=_text(value.get("stage"), f"{field}.stage"),
            evidence=tuple(Evidence.parse(item, f"{field}.evidence[{index}]")
                           for index, item in enumerate(evidence)),
            rubrics=parsed_rubrics,
        )


@dataclass(frozen=True)
class Manifest:
    rubric_set_id: str
    rubric_version: str
    source_revisions: dict[str, str]
    aggregation: str
    judge_replicas: int
    groups: tuple[Group, ...]
    path: Path

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        path = path.resolve()
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError("document evaluation manifest must be an object")
        unknown = set(value) - {
            "schema_version", "rubric_set_id", "rubric_version", "source_revisions",
            "aggregation", "judge_replicas", "groups",
        }
        if unknown:
            raise ValueError(f"manifest has unknown keys: {sorted(unknown)}")
        if value.get("schema_version") != 1:
            raise ValueError("document evaluation manifest schema_version must be 1")
        revisions = value.get("source_revisions")
        if not isinstance(revisions, dict) or not revisions or not all(
            isinstance(key, str) and key and isinstance(revision, str) and revision
            for key, revision in revisions.items()
        ):
            raise ValueError("source_revisions must be a nonempty string map")
        aggregation = value.get("aggregation", "min_group_pass_rate")
        if aggregation not in AGGREGATIONS:
            raise ValueError(f"aggregation must be one of {sorted(AGGREGATIONS)}")
        replicas = value.get("judge_replicas", 1)
        if isinstance(replicas, bool) or not isinstance(replicas, int) or not 1 <= replicas <= 3:
            raise ValueError("judge_replicas must be an integer from 1 to 3")
        groups = value.get("groups")
        if not isinstance(groups, list) or not groups:
            raise ValueError("groups must be a nonempty list")
        parsed_groups = tuple(Group.parse(item, f"groups[{index}]")
                              for index, item in enumerate(groups))
        group_ids = [group.group_id for group in parsed_groups]
        rubric_ids = [rubric.rubric_id for group in parsed_groups for rubric in group.rubrics]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("group IDs must be unique")
        if len(rubric_ids) != len(set(rubric_ids)):
            raise ValueError("rubric IDs must be unique across all groups")
        return cls(
            rubric_set_id=_slug(value.get("rubric_set_id"), "rubric_set_id"),
            rubric_version=_text(value.get("rubric_version"), "rubric_version"),
            source_revisions=dict(revisions),
            aggregation=aggregation,
            judge_replicas=replicas,
            groups=parsed_groups,
            path=path,
        )


def judgment_schema(group: Group) -> dict[str, Any]:
    rubric_ids = [rubric.rubric_id for rubric in group.rubrics]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["group_id", "results"],
        "properties": {
            "group_id": {"const": group.group_id},
            "results": {
                "type": "array",
                "minItems": len(rubric_ids),
                "maxItems": len(rubric_ids),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["rubric_id", "verdict", "evidence", "reason", "issue_id"],
                    "properties": {
                        "rubric_id": {"type": "string", "enum": rubric_ids},
                        "verdict": {"type": "string", "enum": ["P", "F"]},
                        "evidence": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["path", "location", "quote"],
                                "properties": {
                                    "path": {"type": "string", "minLength": 1},
                                    "location": {"type": "string", "minLength": 1},
                                    "quote": {"type": "string", "minLength": 1, "maxLength": 500},
                                },
                            },
                        },
                        "reason": {"type": "string", "minLength": 1, "maxLength": 1600},
                        "issue_id": {"type": ["string", "null"]},
                    },
                },
            },
        },
    }


def validate_judgment(group: Group, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("group_id") != group.group_id:
        raise ValueError(f"judge output has the wrong group_id for {group.group_id}")
    results = value.get("results")
    if not isinstance(results, list):
        raise ValueError(f"judge output results must be a list for {group.group_id}")
    by_id: dict[str, dict[str, Any]] = {}
    expected = {rubric.rubric_id for rubric in group.rubrics}
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("each judge result must be an object")
        rubric_id = result.get("rubric_id")
        if rubric_id not in expected or rubric_id in by_id:
            raise ValueError(f"unexpected or duplicate rubric result: {rubric_id!r}")
        if result.get("verdict") not in {"P", "F"}:
            raise ValueError(f"invalid verdict for {rubric_id}")
        evidence = result.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"missing evidence for {rubric_id}")
        for citation in evidence:
            if not isinstance(citation, dict) or set(citation) != {"path", "location", "quote"}:
                raise ValueError(f"invalid evidence object for {rubric_id}")
            if not all(isinstance(citation[key], str) and citation[key].strip()
                       for key in ("path", "location", "quote")):
                raise ValueError(f"empty evidence field for {rubric_id}")
        if not isinstance(result.get("reason"), str) or not result["reason"].strip():
            raise ValueError(f"missing reason for {rubric_id}")
        issue_id = result.get("issue_id")
        if result["verdict"] == "F" and (not isinstance(issue_id, str) or not issue_id.strip()):
            raise ValueError(f"failed rubric {rubric_id} needs an issue_id")
        if result["verdict"] == "P" and issue_id not in (None, ""):
            raise ValueError(f"passed rubric {rubric_id} cannot have an issue_id")
        by_id[rubric_id] = result
    if set(by_id) != expected:
        raise ValueError(f"judge output does not cover the frozen denominator for {group.group_id}")
    return {"group_id": group.group_id,
            "results": [by_id[rubric.rubric_id] for rubric in group.rubrics]}


def disagreements(group: Group, judgments: list[dict[str, Any]]) -> list[str]:
    if len(judgments) < 2:
        return []
    by_run = [{row["rubric_id"]: row["verdict"] for row in item["results"]}
              for item in judgments]
    return [rubric.rubric_id for rubric in group.rubrics
            if len({run[rubric.rubric_id] for run in by_run}) > 1]


def aggregate(manifest: Manifest, judgments: dict[str, dict[str, Any]]) -> tuple[dict[str, float | int], dict[str, Any]]:
    group_scores: dict[str, float] = {}
    details: list[dict[str, Any]] = []
    total_weight = passed_weight = 0.0
    critical_total = critical_passed = 0
    for group in manifest.groups:
        judgment = judgments[group.group_id]
        by_id = {row["rubric_id"]: row for row in judgment["results"]}
        group_total = group_passed = 0.0
        for rubric in group.rubrics:
            row = by_id[rubric.rubric_id]
            passed = row["verdict"] == "P"
            group_total += rubric.weight
            total_weight += rubric.weight
            if passed:
                group_passed += rubric.weight
                passed_weight += rubric.weight
            if rubric.critical:
                critical_total += 1
                critical_passed += int(passed)
            details.append({
                "group_id": group.group_id,
                "stage": group.stage,
                "rubric_id": rubric.rubric_id,
                "title": rubric.title,
                "weight": rubric.weight,
                "critical": rubric.critical,
                **row,
            })
        group_scores[group.group_id] = group_passed / group_total
    overall = passed_weight / total_weight
    if manifest.aggregation == "min_group_pass_rate":
        reward = min(group_scores.values())
    elif manifest.aggregation == "weighted_pass_rate":
        reward = overall
    else:
        reward = float(all(score == 1.0 for score in group_scores.values()))
    all_pass = int(all(row["verdict"] == "P" for row in details))
    rewards: dict[str, float | int] = {
        "reward": round(reward, 6),
        "rubric_pass_rate": round(overall, 6),
        "critical_pass_rate": round(critical_passed / critical_total, 6) if critical_total else 1.0,
        "document_acceptance": all_pass,
        "rubric_passed": sum(row["verdict"] == "P" for row in details),
        "rubric_total": len(details),
    }
    rewards.update({f"group_{group_id}": round(score, 6)
                    for group_id, score in group_scores.items()})
    report = {
        "schema_version": 1,
        "rubric_set_id": manifest.rubric_set_id,
        "rubric_version": manifest.rubric_version,
        "source_revisions": manifest.source_revisions,
        "aggregation": manifest.aggregation,
        "rewards": rewards,
        "groups": group_scores,
        "results": details,
    }
    return rewards, report


def apply_delivery_gate(
    rewards: dict[str, float | int],
    report: dict[str, Any],
    required_files: list[str],
    missing_files: list[str],
) -> tuple[dict[str, float | int], dict[str, Any]]:
    """Make required-file completeness a deterministic Harbor reward gate."""
    required = list(dict.fromkeys(required_files))
    missing = list(dict.fromkeys(missing_files))
    if not set(missing).issubset(required):
        raise ValueError("missing delivery files must be part of the required file set")
    complete = int(not missing)
    gated_rewards = dict(rewards)
    gated_rewards["delivery_completeness"] = complete
    if not complete:
        gated_rewards["reward"] = 0.0
        gated_rewards["document_acceptance"] = 0
    gated_report = dict(report)
    gated_report["rewards"] = gated_rewards
    gated_report["delivery"] = {
        "required_files": required,
        "missing_files": missing,
        "complete": bool(complete),
        "reward_gate": "all_required_files_present",
    }
    return gated_rewards, gated_report


def markdown_report(report: dict[str, Any]) -> str:
    rewards = report["rewards"]
    lines = [
        "# 文档 Rubric Judge 报告",
        "",
        f"Rubric：`{report['rubric_set_id']}` · `{report['rubric_version']}`",
        f"Harbor reward：**{rewards['reward']:.4f}**；全部评分项通过："
        + ("是" if rewards["document_acceptance"] else "否"),
        "",
        "## 分组得分",
        "",
        "| 分组 | 通过率 |",
        "| --- | ---: |",
    ]
    for group_id, score in report["groups"].items():
        lines.append(f"| {group_id} | {score:.2%} |")
    delivery = report.get("delivery")
    if delivery is not None:
        lines += ["", "## 交付完整性", ""]
        if delivery["complete"]:
            lines.append("全部要求文件均已交付。")
        else:
            lines += ["以下要求文件缺失，Harbor reward 按交付门禁记为 0：", ""]
            lines.extend(f"- `{path}`" for path in delivery["missing_files"])
    lines += ["", "## 逐项结果", "", "| Rubric | 结果 | 证据 | 判定 |", "| --- | --- | --- | --- |"]
    for row in report["results"]:
        citations = "；".join(f"{item['path']}:{item['location']}" for item in row["evidence"])
        reason = row["reason"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['rubric_id']} · {row['title']} | {row['verdict']} | {citations} | {reason} |")
    lines += [
        "",
        "## 口径",
        "",
        "- 每个冻结评分项只有 P/F，不给半分。",
        "- 缺少任一要求交付文件时，继续执行文档 Rubric Judge，但最终 Harbor reward 为 0。",
        "- `reward` 只负责 Harbor 数值传输；分组分数、关键项和逐项证据必须同时保留。",
        "- Judge 或基础设施失败会使评测报错，不会记为候选 0 分。",
    ]
    return "\n".join(lines) + "\n"


def rewardkit_details(report: dict[str, Any]) -> dict[str, Any]:
    """Return Harbor Viewer's RewardKit-compatible reward-details structure."""
    result: dict[str, Any] = {}
    for group_id, score in report["groups"].items():
        rows = [row for row in report["results"] if row["group_id"] == group_id]
        result[group_id] = {
            "kind": "document_rubric_judge",
            "score": score,
            "criteria": [
                {
                    "name": row["rubric_id"],
                    "description": row["title"],
                    "value": 1.0 if row["verdict"] == "P" else 0.0,
                    "raw": 1.0 if row["verdict"] == "P" else 0.0,
                    "weight": row["weight"],
                    "reasoning": row["reason"],
                    **({"error": row["issue_id"]} if row["issue_id"] else {}),
                }
                for row in rows
            ],
            "warnings": [],
            "judge_output": "Full structured evidence: verifier/document-evaluation.json",
        }
    delivery = report.get("delivery")
    if delivery is not None:
        missing = set(delivery["missing_files"])
        result["delivery_completeness"] = {
            "kind": "deterministic_delivery_gate",
            "score": 1.0 if delivery["complete"] else 0.0,
            "criteria": [
                {
                    "name": path,
                    "description": "Required document output exists as a regular file",
                    "value": 0.0 if path in missing else 1.0,
                    "raw": 0.0 if path in missing else 1.0,
                    "weight": 1.0,
                    "reasoning": "missing required file" if path in missing else "required file present",
                    **({"error": "MISSING_REQUIRED_FILE"} if path in missing else {}),
                }
                for path in delivery["required_files"]
            ],
            "warnings": [f"Missing required file: {path}" for path in delivery["missing_files"]],
            "judge_output": "Deterministic check recorded in verifier/document-evaluation.json",
        }
    return result
