"""Deterministic state, authorization and revision rules for Hierarchical mode."""

import copy
from pathlib import PurePosixPath

from runtime.team_protocol import ProtocolError


def _scope_contains(scope, path):
    return path == scope or path.startswith(scope.rstrip("/") + "/")


def scopes_overlap(left, right):
    return _scope_contains(left, right) or _scope_contains(right, left)


class TeamBroker:
    """Own team lifecycle state; model output never mutates state directly."""

    def __init__(self, compiled):
        if compiled.get("mode") != "hierarchical":
            raise ValueError("TeamBroker requires a hierarchical workflow")
        self.compiled = compiled
        self.execution = compiled["run"]["execution"]
        self.stages = {stage["stage_id"]: stage for stage in compiled["stages"]}
        self.stage_order = {stage["stage_id"]: i for i, stage in enumerate(compiled["stages"])}
        self.output_paths = {
            ref: str(PurePosixPath(path).relative_to("/workspace"))
            for stage in compiled["stages"]
            for ref, path in stage["outputs"].items()
        }
        self.output_stages = {
            ref: stage["stage_id"]
            for stage in compiled["stages"]
            for ref in stage["outputs"]
        }
        self.sprint1_required = {
            ref for ref in compiled["contract"]["delivery"]["required"]
            if ref.startswith("artifact:sprint1/")
        }
        self.sprint2_required = {
            ref for stage in compiled["stages"]
            if stage["stage_id"].startswith("sprint2/")
            for ref in stage["outputs"]
        }
        self.allowed_roles = set(compiled["contract"]["roles"]) - {
            "workflow", "lead", "member",
        }
        required = list(compiled["contract"]["delivery"]["required"])
        self.state = {
            "mode": "hierarchical",
            "status": "running",
            "model_called": True,
            "lead_session": None,
            "lead_turns": 0,
            "max_cost_usd": self.execution["max_cost_usd"],
            "cost_usd": 0.0,
            "members": {},
            "assignments": {},
            "revisions": {},
            "current_artifacts": {},
            "current_repository_revisions": [],
            "required_artifacts": required,
            "qa_verdict": None,
            "live_deployment_revision": None,
            "delivery_complete": False,
            "counters": {
                "members": 0,
                "assignments": 0,
                "revisions": 0,
                "reworks": 0,
                "peak_concurrency": 0,
            },
        }
        self._revision_sequence = 0

    def _limit(self, name):
        return self.execution[name]

    def public_state(self):
        """JSON-safe state supplied to Lead, excluding no host secrets or paths."""
        return copy.deepcopy(self.state)

    def set_lead_session(self, session_id):
        current = self.state["lead_session"]
        if current is not None and current != session_id:
            raise ProtocolError(f"Lead native session changed: {current} -> {session_id}")
        self.state["lead_session"] = session_id

    def record_lead_turn(self):
        self.state["lead_turns"] += 1
        if self.state["lead_turns"] > self._limit("max_lead_turns"):
            raise ProtocolError("Lead turn budget exceeded")

    def terminate_budget(self, budget="max_lead_turns"):
        self.state.update(
            status="budget_exhausted",
            delivery_complete=False,
            error=f"{budget} ({self._limit(budget)}) exhausted",
        )

    def charge(self, spent):
        """Accumulate reported spend; returns True when the cost budget is spent."""
        if spent is not None:
            self.state["cost_usd"] = round(self.state["cost_usd"] + spent, 6)
        return self.state["cost_usd"] >= self._limit("max_cost_usd")

    def _new_revision_id(self):
        self._revision_sequence += 1
        return f"rev-{self._revision_sequence:04d}"

    def apply_plan(self, plan):
        """Validate and commit one Lead plan, returning runtime effects."""
        seen_assignment = False
        for action in plan["actions"]:
            if action["type"] in {"send_task", "request_check"}:
                seen_assignment = True
            elif action["type"] == "submit_artifact" and seen_assignment:
                raise ProtocolError(
                    "submit_artifact actions must precede assignments in a plan"
                )
        saved_state = copy.deepcopy(self.state)
        saved_sequence = self._revision_sequence
        effects = []
        try:
            for action in plan["actions"]:
                handler = getattr(self, "_action_" + action["type"])
                effect = handler(action)
                if effect is not None:
                    effects.append(effect)
        except BaseException:
            self.state = saved_state
            self._revision_sequence = saved_sequence
            raise
        return effects

    def _action_spawn_member(self, action):
        members = self.state["members"]
        member_id, role = action["member_id"], action["role"]
        if member_id in members:
            raise ProtocolError(f"member already exists: {member_id}")
        if role not in self.allowed_roles:
            raise ProtocolError(f"role is not available to a member: {role}")
        if len(members) >= self._limit("max_members"):
            raise ProtocolError("max_members exceeded")
        member = {
            "id": member_id,
            "role": role,
            "status": "idle",
            "session_id": None,
            "assignments": [],
        }
        members[member_id] = member
        self.state["counters"]["members"] = len(members)
        return {"type": "spawn_member", "member": copy.deepcopy(member)}

    def _validate_inputs(self, stage, supplied):
        required = {ref for ref in stage["inputs"] if ref.startswith("artifact:")}
        if set(supplied) != required:
            missing = sorted(required - set(supplied))
            extra = sorted(set(supplied) - required)
            raise ProtocolError(
                f"input revision binding mismatch; missing={missing}, extra={extra}"
            )
        current = self.state["current_artifacts"]
        for ref, revision_id in supplied.items():
            if current.get(ref) != revision_id:
                raise ProtocolError(
                    f"input revision is not current for {ref}: {revision_id}"
                )
            revision = self.state["revisions"].get(revision_id)
            if revision is None or revision["status"] == "stale":
                raise ProtocolError(f"input revision is unavailable: {revision_id}")
            if ref not in revision["outputs"]:
                raise ProtocolError(
                    f"input revision {revision_id} does not provide {ref}"
                )

    def _validate_scopes(self, stage, output_refs, scopes):
        expected_paths = [self.output_paths[ref] for ref in output_refs]
        declared_paths = [self.output_paths[ref] for ref in stage["outputs"]]
        additional = stage.get("additional_output_directory")
        additional = (
            str(PurePosixPath(additional).relative_to("/workspace"))
            if additional else None
        )
        for path in expected_paths:
            if not any(_scope_contains(scope, path) for scope in scopes):
                raise ProtocolError(f"write_scope does not cover output: {path}")
        for scope in scopes:
            if scope.startswith("artifacts/"):
                unauthorized = [
                    path for path in declared_paths
                    if _scope_contains(scope, path) and path not in expected_paths
                ]
                if unauthorized:
                    raise ProtocolError(
                        f"artifact write_scope includes unassigned outputs: {unauthorized}"
                    )
                covers_output = any(
                    _scope_contains(scope, path) for path in expected_paths
                )
                within_additional = additional and _scope_contains(additional, scope)
                if not covers_output and not within_additional:
                    raise ProtocolError(f"artifact write_scope exceeds assigned outputs: {scope}")
            elif not stage.get("write_repos") or not scope.startswith("repos/"):
                raise ProtocolError(f"repository write scope is not allowed: {scope}")
        active = [
            task for task in self.state["assignments"].values()
            if task["status"] in {"queued", "running"} and task.get("write_scope")
        ]
        for task in active:
            for left in scopes:
                for right in task["write_scope"]:
                    if scopes_overlap(left, right):
                        raise ProtocolError(
                            f"write_scope overlaps active task {task['id']}: {left} / {right}"
                        )

    def _validate_service_concurrency(self, stage):
        role = stage["role"]
        if role not in {"developer", "deployer", "qa"}:
            return
        active_roles = {
            self.stages[task["stage_id"]]["role"]
            for task in self.state["assignments"].values()
            if task["status"] in {"queued", "running"}
        }
        conflicts = (
            active_roles & {"deployer", "qa"} if role == "developer"
            else active_roles & {"developer", "deployer", "qa"}
            if role == "deployer"
            else active_roles & {"developer", "deployer"}
        )
        if conflicts:
            raise ProtocolError(
                f"{role} conflicts with active service roles: {sorted(conflicts)}"
            )

    def _reserve_assignment(self, action, kind):
        tasks = self.state["assignments"]
        if action["task_id"] in tasks:
            raise ProtocolError(f"task already exists: {action['task_id']}")
        if len(tasks) >= self._limit("max_assignments"):
            raise ProtocolError("max_assignments exceeded")
        member = self.state["members"].get(action["member_id"])
        if member is None or member["status"] == "stopped":
            raise ProtocolError(f"member is unavailable: {action['member_id']}")
        if member["status"] != "idle":
            raise ProtocolError(f"member is already busy: {action['member_id']}")
        in_flight = sum(
            task["status"] in {"queued", "running"} for task in tasks.values()
        )
        if in_flight >= self._limit("max_concurrency"):
            raise ProtocolError("max_concurrency exceeded")
        revision_id = self._new_revision_id()
        task = {
            "id": action["task_id"],
            "kind": kind,
            "member_id": action["member_id"],
            "status": "queued",
            "revision_id": revision_id,
            "instructions": action["instructions"],
            "input_revisions": copy.deepcopy(action["input_revisions"]),
            "result": None,
        }
        tasks[task["id"]] = task
        member["status"] = "busy"
        member["assignments"].append(task["id"])
        self.state["counters"]["assignments"] = len(tasks)
        concurrent = sum(t["status"] in {"queued", "running"} for t in tasks.values())
        self.state["counters"]["peak_concurrency"] = max(
            concurrent, self.state["counters"]["peak_concurrency"]
        )
        return task

    def _action_send_task(self, action):
        stage = self.stages.get(action["stage_id"])
        if stage is None:
            raise ProtocolError(f"unknown stage: {action['stage_id']}")
        member = self.state["members"].get(action["member_id"])
        if member is None or member["role"] != stage["role"]:
            raise ProtocolError(
                f"task role {stage['role']} requires a matching member"
            )
        output_refs = action["output_refs"]
        if any(ref not in stage["outputs"] for ref in output_refs):
            raise ProtocolError("task output_refs must belong to its stage")
        required_task_output = {
            "qa": "/verdict",
            "triage": "/repair_plan",
            "deployer": "/deployment",
        }.get(stage["role"])
        if (required_task_output is not None
                and not any(ref.endswith(required_task_output) for ref in output_refs)):
            raise ProtocolError(
                f"{stage['role']} task must include its {required_task_output[1:]} output"
            )
        if (not output_refs and (
                not stage.get("write_repos")
                or not action["write_scope"]
                or any(not scope.startswith("repos/") for scope in action["write_scope"]))):
            raise ProtocolError(
                "an output-free task must be a repository-only development task"
            )
        self._validate_inputs(stage, action["input_revisions"])
        self._validate_service_concurrency(stage)
        if stage["role"] == "qa":
            sprint = action["stage_id"].split("/", 1)[0]
            deployment_ref = f"artifact:{sprint}/deploy/deployment"
            deployment_id = self.state["current_artifacts"].get(deployment_ref)
            if deployment_id is None:
                raise ProtocolError("QA requires an accepted deployment revision")
            deployment = self.state["revisions"][deployment_id]
            if deployment.get("repository_revisions", []) != self.state["current_repository_revisions"]:
                raise ProtocolError("QA deployment does not bind the current repository revisions")
            if self.state["live_deployment_revision"] != deployment_id:
                raise ProtocolError("QA requires the accepted deployment revision to be live")
        if action["stage_id"] == "sprint2/triage":
            if not self.sprint1_required.issubset(self.state["current_artifacts"]):
                raise ProtocolError("repair triage requires all Sprint 1 artifacts")
            if self.state.get("qa_verdict") != "fail":
                raise ProtocolError("repair triage requires an accepted Sprint 1 QA failure")
        self._validate_scopes(stage, output_refs, action["write_scope"])
        completed_for_stage = sum(
            revision["stage_id"] == action["stage_id"]
            for revision in self.state["revisions"].values()
        )
        reserved_for_stage = sum(
            task.get("stage_id") == action["stage_id"]
            and task["status"] in {"queued", "running"}
            for task in self.state["assignments"].values()
        )
        if completed_for_stage + reserved_for_stage >= self._limit("max_revisions_per_stage"):
            raise ProtocolError("max_revisions_per_stage exceeded")
        task = self._reserve_assignment(action, "work")
        task.update(
            stage_id=action["stage_id"],
            output_refs=list(output_refs),
            write_scope=list(action["write_scope"]),
            repository_revisions=list(self.state["current_repository_revisions"]),
        )
        if any(
            revision["stage_id"] == action["stage_id"]
            for revision in self.state["revisions"].values()
        ):
            self.state["counters"]["reworks"] += 1
        if stage["role"] in {"developer", "deployer"}:
            self.state["live_deployment_revision"] = None
        return {"type": "execute_assignment", "task": copy.deepcopy(task)}

    def _action_request_check(self, action):
        member = self.state["members"].get(action["member_id"])
        if member is None or member["role"] != "reviewer":
            raise ProtocolError("request_check requires a reviewer member")
        revision = self.state["revisions"].get(action["revision_id"])
        if revision is None:
            raise ProtocolError(f"unknown revision: {action['revision_id']}")
        if any(path.startswith("repos/") for path in revision["files"]):
            raise ProtocolError(
                "repository revisions must be rebuilt, not rebound by a reviewer"
            )
        stage = self.stages[revision["stage_id"]]
        self._validate_inputs(stage, action["input_revisions"])
        task = self._reserve_assignment(action, "review")
        task.update(
            stage_id=revision["stage_id"],
            source_revision=revision["id"],
            output_refs=[],
            write_scope=[],
            repository_revisions=list(self.state["current_repository_revisions"]),
        )
        return {"type": "execute_assignment", "task": copy.deepcopy(task)}

    def _action_stop_member(self, action):
        member = self.state["members"].get(action["member_id"])
        if member is None:
            raise ProtocolError(f"unknown member: {action['member_id']}")
        if member["status"] == "busy":
            raise ProtocolError("cannot stop a member with an active assignment")
        member["status"] = "stopped"
        member["stop_reason"] = action.get("reason")
        return {"type": "stop_member", "member_id": action["member_id"]}

    def _action_submit_artifact(self, action):
        repository_before = list(self.state["current_repository_revisions"])
        revision = self.state["revisions"].get(action["revision_id"])
        if revision is None:
            raise ProtocolError(f"unknown revision: {action['revision_id']}")
        if revision["status"] == "stale":
            raise ProtocolError("cannot submit a stale revision")
        if not set(action["output_refs"]).issubset(revision["outputs"]):
            raise ProtocolError("revision does not contain all submitted output_refs")
        repo_files = any(path.startswith("repos/") for path in revision["files"])
        if not action["output_refs"] and not repo_files:
            raise ProtocolError("an empty artifact submission needs repository changes")
        accept_repository = repo_files and not revision.get("repository_accepted", False)
        if not action["output_refs"] and not accept_repository:
            raise ProtocolError("repository revision is already accepted")
        replaced = {}
        for ref in action["output_refs"]:
            old = self.state["current_artifacts"].get(ref)
            if old and old != revision["id"]:
                replaced[ref] = old
            self.state["current_artifacts"][ref] = revision["id"]
        revision["status"] = "accepted"
        revision["accepted_outputs"] = sorted(
            set(revision.get("accepted_outputs", [])) | set(action["output_refs"])
        )
        for ref, old_revision in replaced.items():
            self._stale_dependants(ref, old_revision)
        if accept_repository:
            revision["repository_accepted"] = True
            self.state["current_repository_revisions"].append(revision["id"])
            self._stale_repository_dependants(revision, removed=False)
            self.state["live_deployment_revision"] = None
        if any(ref.endswith("/deployment") for ref in action["output_refs"]):
            if self.state["live_deployment_revision"] != revision["id"]:
                raise ProtocolError(
                    "only the currently live, health-checked deployment can be accepted"
                )
        self._refresh_qa_verdict()
        return {
            "type": "accept_revision",
            "revision_id": revision["id"],
            "output_refs": list(action["output_refs"]),
            "replaced": replaced,
            "accept_repository": accept_repository,
            "repository_set_changed": (
                repository_before != self.state["current_repository_revisions"]
            ),
            "repository_revisions": list(self.state["current_repository_revisions"]),
        }

    def _action_finish_delivery(self, action):
        running = [
            task["id"] for task in self.state["assignments"].values()
            if task["status"] in {"queued", "running"}
        ]
        if running:
            raise ProtocolError(f"cannot finish with active assignments: {running}")
        if action["outcome"] == "complete":
            self.validate_delivery()
            self.state.update(status="complete", delivery_complete=True)
        else:
            self.state.update(status="blocked", delivery_complete=False)
        self.state["finish_reason"] = action["reason"]
        return {"type": "finish_delivery", "outcome": action["outcome"]}

    def mark_running(self, task_id):
        task = self.state["assignments"][task_id]
        if task["status"] != "queued":
            raise ProtocolError(f"task is not queued: {task_id}")
        task["status"] = "running"

    def _release_member(self, task):
        member = self.state["members"][task["member_id"]]
        if member["status"] != "stopped":
            member["status"] = "idle"

    def record_assignment_result(self, task_id, result, manifest=None, routing=None):
        task = self.state["assignments"][task_id]
        if task["status"] != "running":
            raise ProtocolError(f"task is not running: {task_id}")
        task["result"] = copy.deepcopy(result)
        if result["status"] == "blocked":
            task["status"] = "blocked"
            self._release_member(task)
            return None
        if task["kind"] == "review":
            return self._record_review(task, result)
        manifest = manifest or {}
        if set(result["outputs"]) != set(manifest):
            raise ProtocolError("member-reported outputs do not match collected files")
        for path in manifest:
            if not any(_scope_contains(scope, path) for scope in task["write_scope"]):
                raise ProtocolError(f"member wrote outside write_scope: {path}")
        output_paths = {self.output_paths[ref]: ref for ref in task["output_refs"]}
        missing = sorted(set(output_paths) - set(manifest))
        if missing:
            raise ProtocolError(f"assignment is missing declared outputs: {missing}")
        if any(manifest[path] == "deleted" for path in output_paths):
            raise ProtocolError("a declared output cannot be deleted")
        revision = {
            "id": task["revision_id"],
            "stage_id": task["stage_id"],
            "task_id": task["id"],
            "member_id": task["member_id"],
            "status": "candidate",
            "input_revisions": copy.deepcopy(task["input_revisions"]),
            "repository_revisions": list(task["repository_revisions"]),
            "outputs": {
                output_paths[path]: {"path": path, "sha256": manifest[path]}
                for path in output_paths
            },
            "files": copy.deepcopy(manifest),
            "routing": copy.deepcopy(routing or {}),
        }
        self.state["revisions"][revision["id"]] = revision
        self.state["counters"]["revisions"] = len(self.state["revisions"])
        task["status"] = "completed"
        if self.stages[task["stage_id"]]["role"] == "deployer":
            self.state["live_deployment_revision"] = revision["id"]
        self._release_member(task)
        return copy.deepcopy(revision)

    def _record_review(self, task, result):
        source = self.state["revisions"][task["source_revision"]]
        task["status"] = "completed"
        task["verdict"] = result["verdict"]
        self._release_member(task)
        if result["verdict"] == "fail":
            return None
        revision = {
            **copy.deepcopy(source),
            "id": task["revision_id"],
            "task_id": task["id"],
            "member_id": task["member_id"],
            "status": "candidate",
            "input_revisions": copy.deepcopy(task["input_revisions"]),
            "repository_revisions": list(task["repository_revisions"]),
            "source_revision": source["id"],
            "review": {"task_id": task["id"], "verdict": "pass"},
        }
        revision.pop("accepted_outputs", None)
        revision.pop("repository_accepted", None)
        revision.pop("stale_because", None)
        self.state["revisions"][revision["id"]] = revision
        self.state["counters"]["revisions"] = len(self.state["revisions"])
        return copy.deepcopy(revision)

    def fail_assignment(self, task_id, error):
        task = self.state["assignments"][task_id]
        discarded = [
            revision_id for revision_id, revision in self.state["revisions"].items()
            if revision.get("task_id") == task_id and revision["status"] == "candidate"
        ]
        for revision_id in discarded:
            del self.state["revisions"][revision_id]
            if self.state["live_deployment_revision"] == revision_id:
                self.state["live_deployment_revision"] = None
        self.state["counters"]["revisions"] = len(self.state["revisions"])
        task.update(status="failed", error=str(error))
        self._release_member(task)

    def set_member_session(self, member_id, session_id):
        member = self.state["members"][member_id]
        current = member["session_id"]
        if current is not None and current != session_id:
            raise ProtocolError(
                f"member {member_id} native session changed: {current} -> {session_id}"
            )
        member["session_id"] = session_id

    def _stale_dependants(self, changed_ref, old_revision):
        queue = [(changed_ref, old_revision)]
        visited = set()
        while queue:
            ref, revision_id = queue.pop(0)
            key = (ref, revision_id)
            if key in visited:
                continue
            visited.add(key)
            for revision in self.state["revisions"].values():
                if revision["status"] == "stale":
                    continue
                if revision["input_revisions"].get(ref) != revision_id:
                    continue
                revision["status"] = "stale"
                revision["stale_because"] = {"artifact": ref, "revision": revision_id}
                if self.state["live_deployment_revision"] == revision["id"]:
                    self.state["live_deployment_revision"] = None
                if revision["id"] in self.state["current_repository_revisions"]:
                    self.state["current_repository_revisions"].remove(revision["id"])
                    self._stale_repository_dependants(revision, removed=True)
                for output_ref in list(revision["outputs"]):
                    if self.state["current_artifacts"].get(output_ref) == revision["id"]:
                        del self.state["current_artifacts"][output_ref]
                        queue.append((output_ref, revision["id"]))

    def _refresh_qa_verdict(self):
        candidates = []
        for ref, revision_id in self.state["current_artifacts"].items():
            if not ref.endswith("/verdict"):
                continue
            revision = self.state["revisions"][revision_id]
            verdict = revision.get("routing", {}).get("verdict")
            if verdict in {"pass", "fail"}:
                candidates.append((self.stage_order[revision["stage_id"]], verdict))
        self.state["qa_verdict"] = max(candidates)[1] if candidates else None

    def _stale_repository_dependants(self, code_revision, *, removed):
        current_repos = self.state["current_repository_revisions"]
        for revision in self.state["revisions"].values():
            if revision["id"] == code_revision["id"] or revision["status"] == "stale":
                continue
            role = self.stages[revision["stage_id"]]["role"]
            downstream = (
                self.stage_order[revision["stage_id"]]
                > self.stage_order[code_revision["stage_id"]]
            )
            depends_on_code = code_revision["id"] in revision.get(
                "repository_revisions", []
            )
            mismatched_downstream = (
                downstream
                and role in {"developer", "deployer", "qa"}
                and revision.get("repository_revisions", []) != current_repos
            )
            if (removed and depends_on_code) or mismatched_downstream:
                revision["status"] = "stale"
                revision["stale_because"] = {
                    "repository_revision": code_revision["id"]
                }
                if revision["id"] in current_repos:
                    current_repos.remove(revision["id"])
                    self._stale_repository_dependants(revision, removed=True)
                    self.state["live_deployment_revision"] = None
                for output_ref in list(revision["outputs"]):
                    if self.state["current_artifacts"].get(output_ref) == revision["id"]:
                        del self.state["current_artifacts"][output_ref]
                        self._stale_dependants(output_ref, revision["id"])

    def validate_delivery(self):
        current = self.state["current_artifacts"]
        qa_revisions = [
            self.state["revisions"][revision_id]
            for ref, revision_id in current.items() if ref.endswith("/verdict")
        ]
        if not qa_revisions:
            raise ProtocolError("no accepted QA verdict revision exists")
        latest_qa = max(qa_revisions, key=lambda item: self.stage_order[item["stage_id"]])
        required = set(self.state["required_artifacts"])
        if latest_qa["stage_id"].startswith("sprint2/"):
            required.update(self.sprint2_required)
        missing = sorted(required - set(current))
        if missing:
            raise ProtocolError(f"required artifacts are missing: {missing}")
        if self.state.get("qa_verdict") != "pass":
            raise ProtocolError("the latest accepted QA verdict is not pass")
        if latest_qa.get("repository_revisions", []) != self.state["current_repository_revisions"]:
            raise ProtocolError("latest QA revision does not bind the accepted repository revisions")
        checked = set()

        def check_revision(revision_id):
            if revision_id in checked:
                return
            revision = self.state["revisions"].get(revision_id)
            if revision is None or revision["status"] == "stale":
                raise ProtocolError(f"delivery contains stale revision: {revision_id}")
            for ref, dependency in revision["input_revisions"].items():
                if current.get(ref) != dependency:
                    raise ProtocolError(
                        f"inconsistent revision closure for {ref}: {dependency}"
                    )
                check_revision(dependency)
            checked.add(revision_id)

        for revision_id in set(current.values()):
            check_revision(revision_id)
        return True
