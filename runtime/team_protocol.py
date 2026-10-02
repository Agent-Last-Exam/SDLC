"""Validated structured messages exchanged by the hierarchical team runtime."""

import json
from pathlib import PurePosixPath
import re


ACTION_TYPES = {
    "spawn_member", "send_task", "submit_artifact",
    "request_check", "stop_member", "finish_delivery",
}
ID_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}")
STAGE_PATTERN = re.compile(r"[a-z0-9_-]+/[a-z0-9_-]+")
ARTIFACT_PATTERN = re.compile(
    r"artifact:[a-z0-9_-]+/[a-z0-9_-]+/[a-z][a-z0-9_]*"
)


class ProtocolError(ValueError):
    """A model message is syntactically valid JSON but violates the team protocol."""


def _object(value, label):
    if not isinstance(value, dict):
        raise ProtocolError(f"{label} must be a JSON object")
    return value


def _exact_keys(value, required, optional, label):
    missing = required - set(value)
    extra = set(value) - required - optional
    if missing:
        raise ProtocolError(f"{label} is missing: {', '.join(sorted(missing))}")
    if extra:
        raise ProtocolError(f"{label} has unsupported fields: {', '.join(sorted(extra))}")


def _text(value, label, *, pattern=None, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ProtocolError(f"{label} must be a nonempty string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise ProtocolError(f"{label} has an invalid format: {value!r}")
    return value


def safe_scope(value):
    """Return a canonical assignment-relative path with no traversal or aliases."""
    _text(value, "write_scope entry")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or "\\" in value
        or str(path) != value
        or value in {"artifacts", "repos"}
        or not value.startswith(("artifacts/", "repos/"))
    ):
        raise ProtocolError(f"unsafe write scope: {value!r}")
    return value


def _string_list(value, label, *, pattern=None, scopes=False, allow_empty=False):
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ProtocolError(f"{label} must be a nonempty array")
    result = []
    for index, item in enumerate(value):
        if scopes:
            result.append(safe_scope(item))
        else:
            result.append(_text(item, f"{label}[{index}]", pattern=pattern))
    if len(set(result)) != len(result):
        raise ProtocolError(f"{label} contains duplicates")
    return result


def _revision_map(value, label="input_revisions"):
    if not isinstance(value, dict):
        raise ProtocolError(f"{label} must be an object")
    result = {}
    for ref, revision in value.items():
        _text(ref, f"{label} reference", pattern=ARTIFACT_PATTERN)
        result[ref] = _text(revision, f"{label}[{ref}]", pattern=ID_PATTERN)
    return result


def extract_structured_output(text):
    """Extract one JSON object, accepting a fenced final answer but no prose."""
    if not isinstance(text, str) or not text.strip():
        raise ProtocolError("model returned no structured output")
    candidate = text.strip()
    fence = chr(96) * 3
    if candidate.startswith(fence) and candidate.endswith(fence):
        lines = candidate.splitlines()
        if len(lines) < 3 or lines[-1].strip() != fence:
            raise ProtocolError("invalid JSON fence")
        if lines[0].strip() not in {fence, fence + "json", fence + "JSON"}:
            raise ProtocolError("only a JSON code fence is accepted")
        candidate = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON output: {exc.msg}") from exc
    return _object(value, "structured output")


def parse_lead_plan(text, *, max_actions=None):
    value = extract_structured_output(text)
    _exact_keys(value, {"summary", "actions"}, set(), "lead plan")
    summary = _text(value["summary"], "lead plan summary")
    actions = value["actions"]
    if not isinstance(actions, list) or not actions:
        raise ProtocolError("lead plan actions must be a nonempty array")
    if max_actions is not None and len(actions) > max_actions:
        raise ProtocolError(f"lead plan exceeds max_actions_per_turn ({max_actions})")
    parsed = [_parse_action(item, index) for index, item in enumerate(actions)]
    finishes = [action for action in parsed if action["type"] == "finish_delivery"]
    if finishes and len(parsed) != 1:
        raise ProtocolError("finish_delivery must be the only action in its turn")
    return {"summary": summary, "actions": parsed}


def _parse_action(raw, index):
    action = _object(raw, f"actions[{index}]")
    action_type = _text(action.get("type"), f"actions[{index}].type")
    if action_type not in ACTION_TYPES:
        raise ProtocolError(f"unsupported action type: {action_type}")
    label = f"{action_type} action"
    if action_type == "spawn_member":
        _exact_keys(action, {"type", "member_id", "role"}, set(), label)
        return {
            "type": action_type,
            "member_id": _text(action["member_id"], "member_id", pattern=ID_PATTERN),
            "role": _text(action["role"], "role", pattern=ID_PATTERN),
        }
    if action_type == "send_task":
        required = {
            "type", "task_id", "member_id", "stage_id", "instructions",
            "input_revisions", "output_refs", "write_scope",
        }
        _exact_keys(action, required, set(), label)
        return {
            "type": action_type,
            "task_id": _text(action["task_id"], "task_id", pattern=ID_PATTERN),
            "member_id": _text(action["member_id"], "member_id", pattern=ID_PATTERN),
            "stage_id": _text(action["stage_id"], "stage_id", pattern=STAGE_PATTERN),
            "instructions": _text(action["instructions"], "instructions"),
            "input_revisions": _revision_map(action["input_revisions"]),
            "output_refs": _string_list(
                action["output_refs"], "output_refs", pattern=ARTIFACT_PATTERN,
                allow_empty=True,
            ),
            "write_scope": _string_list(action["write_scope"], "write_scope", scopes=True),
        }
    if action_type == "request_check":
        required = {
            "type", "task_id", "member_id", "revision_id", "instructions",
            "input_revisions",
        }
        _exact_keys(action, required, set(), label)
        return {
            "type": action_type,
            "task_id": _text(action["task_id"], "task_id", pattern=ID_PATTERN),
            "member_id": _text(action["member_id"], "member_id", pattern=ID_PATTERN),
            "revision_id": _text(action["revision_id"], "revision_id", pattern=ID_PATTERN),
            "instructions": _text(action["instructions"], "instructions"),
            "input_revisions": _revision_map(action["input_revisions"]),
        }
    if action_type == "submit_artifact":
        _exact_keys(action, {"type", "revision_id", "output_refs"}, set(), label)
        return {
            "type": action_type,
            "revision_id": _text(action["revision_id"], "revision_id", pattern=ID_PATTERN),
            "output_refs": _string_list(
                action["output_refs"], "output_refs", pattern=ARTIFACT_PATTERN,
                allow_empty=True,
            ),
        }
    if action_type == "stop_member":
        _exact_keys(action, {"type", "member_id"}, {"reason"}, label)
        result = {
            "type": action_type,
            "member_id": _text(action["member_id"], "member_id", pattern=ID_PATTERN),
        }
        if "reason" in action:
            result["reason"] = _text(action["reason"], "reason")
        return result
    _exact_keys(action, {"type", "outcome", "reason"}, set(), label)
    if action["outcome"] not in {"complete", "blocked"}:
        raise ProtocolError("finish_delivery outcome must be complete or blocked")
    return {
        "type": action_type,
        "outcome": action["outcome"],
        "reason": _text(action["reason"], "reason"),
    }


def parse_member_result(text, *, reviewer=False):
    value = extract_structured_output(text)
    optional = {"verdict"} if reviewer else set()
    _exact_keys(value, {"status", "summary", "outputs", "blockers"}, optional, "member result")
    if value["status"] not in {"completed", "blocked"}:
        raise ProtocolError("member status must be completed or blocked")
    result = {
        "status": value["status"],
        "summary": _text(value["summary"], "member summary"),
        "outputs": _string_list(value["outputs"], "outputs", scopes=True, allow_empty=True),
        "blockers": _string_list(value["blockers"], "blockers", allow_empty=True),
    }
    if result["status"] == "completed" and result["blockers"]:
        raise ProtocolError("a completed member result cannot contain blockers")
    if result["status"] == "blocked" and not result["blockers"]:
        raise ProtocolError("a blocked member result must explain at least one blocker")
    if reviewer:
        if value.get("verdict") not in {"pass", "fail"}:
            raise ProtocolError("reviewer result must include verdict pass or fail")
        if result["outputs"]:
            raise ProtocolError("reviewers cannot produce outputs")
        result["verdict"] = value["verdict"]
    return result


def lead_plan_schema():
    """Compact protocol description embedded in the Lead prompt."""
    return {
        "root": {"summary": "string", "actions": "one or more actions"},
        "actions": {
            "spawn_member": ["member_id", "role"],
            "send_task": ["task_id", "member_id", "stage_id", "instructions", "input_revisions", "output_refs", "write_scope"],
            "submit_artifact": ["revision_id", "output_refs"],
            "request_check": ["task_id", "member_id", "revision_id", "instructions", "input_revisions"],
            "stop_member": ["member_id", "reason (optional)"],
            "finish_delivery": ["outcome: complete|blocked", "reason"],
        },
        "constraints": [
            "finish_delivery must be the only action in its turn",
            "submit_artifact actions must precede send_task/request_check actions",
        ],
    }


def member_result_schema(reviewer=False):
    schema = {
        "status": "completed|blocked",
        "summary": "string",
        "outputs": "array of assignment-relative regular-file paths",
        "blockers": "array of strings",
    }
    if reviewer:
        schema["verdict"] = "pass|fail"
    return schema
