"""Lead-managed Hierarchical workflow controller, independent of Agent transport."""

import asyncio
import hashlib
import json
from pathlib import Path
import time

from runtime.agent_cost import stream_cost
from runtime.team_broker import TeamBroker
from runtime.team_protocol import (
    ProtocolError,
    lead_plan_schema,
    member_result_schema,
    parse_lead_plan,
    parse_member_result,
)
from runtime.workflow_controller import atomic_json


class HierarchicalController:
    def __init__(self, compiled, workspace, directory, backend):
        if compiled.get("mode") != "hierarchical":
            raise ValueError("HierarchicalController requires hierarchical mode")
        self.compiled = compiled
        self.workspace = Path(workspace)
        self.directory = Path(directory)
        self.backend = backend
        self.directory.mkdir(parents=True, exist_ok=True)
        if (self.directory / "state.json").exists():
            raise ValueError("Controller state already exists; refuse to replay team actions")
        self.broker = TeamBroker(compiled)
        self.broker.state["model_called"] = not backend.synthetic
        self.broker.state["synthetic"] = backend.synthetic

    def event(self, event, **values):
        with (self.directory / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(
                {"time": time.time(), "event": event, **values}, ensure_ascii=False
            ) + "\n")
        atomic_json(self.directory / "state.json", self.broker.state)

    def _lead_instruction(self):
        stages = [{
            "stage_id": stage["stage_id"],
            "role": stage["role"],
            "inputs": list(stage["inputs"]),
            "outputs": {
                ref: str(Path(path).relative_to("/workspace"))
                for ref, path in stage["outputs"].items()
            },
            "additional_output_directory": (
                str(Path(stage["additional_output_directory"]).relative_to("/workspace"))
                if stage.get("additional_output_directory") else None
            ),
            "write_repos": bool(stage.get("write_repos")),
        } for stage in self.compiled["stages"]]
        payload = {
            "team_state": self.broker.public_state(),
            "stages": stages,
            "available_member_roles": sorted(self.broker.allowed_roles),
            "protocol": lead_plan_schema(),
            "remaining": {
                "lead_turns": self.broker._limit("max_lead_turns")
                - self.broker.state["lead_turns"],
                "members": self.broker._limit("max_members")
                - len(self.broker.state["members"]),
                "assignments": self.broker._limit("max_assignments")
                - len(self.broker.state["assignments"]),
            },
        }
        return (
            "根据以下 Runtime 状态决定下一批动作。只返回一个 JSON object，不要 Markdown 或解释。\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

    def _assignment_prompt(self, member, task):
        reviewer = task["kind"] == "review"
        general = (self.workspace / "roles" / (
            "reviewer.system.md" if reviewer else "member.system.md"
        )).read_text()
        professional = "" if reviewer else (
            self.workspace / "roles" / f"{member['role']}.system.md"
        ).read_text()
        marker = (
            f"<!-- SDLC_TEAM_MEMBER: {member['id']} -->\n"
            f"<!-- SDLC_TEAM_ROLE: {member['role']} -->\n"
            f"<!-- SDLC_TEAM_TASK: {task['id']} -->\n"
        )
        return general + "\n\n" + professional + "\n\n" + marker

    def _assignment_instruction(self, member, task):
        input_paths = {
            ref: self.backend.revision_input_path(revision_id, ref)
            for ref, revision_id in task["input_revisions"].items()
        }
        raw_inputs = {
            ref: path for ref, path in self.broker.stages[task["stage_id"]]["inputs"].items()
            if not ref.startswith("artifact:")
        }
        if any(scope.startswith("repos/") for scope in task["write_scope"]):
            raw_inputs["input:repos"] = self.backend.assignment_path(
                task["id"], "repos"
            )
        reviewer = task["kind"] == "review"
        payload = {
            "task_id": task["id"],
            "kind": task["kind"],
            "stage_id": task["stage_id"],
            "role": member["role"],
            "instructions": task["instructions"],
            "input_revisions": task["input_revisions"],
            "input_paths": input_paths,
            "raw_inputs": raw_inputs,
            "source_revision": task.get("source_revision"),
            "source_revision_path": (
                self.backend.revision_path(task["source_revision"])
                if task.get("source_revision") else None
            ),
            "output_refs": task["output_refs"],
            "write_scope": task["write_scope"],
            "assignment_root": self.backend.assignment_path(task["id"]),
            "scratch": self.backend.assignment_path(task["id"], "scratch"),
            "actual_write_paths": [
                self.backend.assignment_path(task["id"], scope)
                for scope in task["write_scope"]
            ],
            "result_schema": member_result_schema(reviewer),
        }
        return (
            f"SDLC_TEAM_TASK: {task['id']}\n"
            "执行这个 Runtime 授权的任务包。所有 write_scope 都相对于 assignment_root；"
            "最终只返回一个 JSON object。outputs 必须列出你实际新增、修改或删除的全部"
            " assignment-relative 文件路径。\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

    async def _run_assignment(self, task):
        member = self.broker.state["members"][task["member_id"]]
        task_dir = self.directory / "assignments" / task["id"]
        task_dir.mkdir(parents=True)
        self.broker.mark_running(task["id"])
        self.event("assignment_started", task=task["id"], member=member["id"])
        quiesced = False
        try:
            await self.backend.prepare_assignment(member, task)
            prompt = self._assignment_prompt(member, task)
            instruction = self._assignment_instruction(member, task)
            (task_dir / "role.md").write_text(prompt)
            (task_dir / "instruction.md").write_text(instruction)
            session_id, response = await self.backend.execute_assignment(
                member, task, prompt, instruction, member["session_id"], task_dir
            )
            self.broker.set_member_session(member["id"], session_id)
            # Freeze the member identity before hashing or copying its bytes.
            await self.backend.quiesce_member(member["id"])
            quiesced = True
            reviewer = task["kind"] == "review"
            result = parse_member_result(response, reviewer=reviewer)
            manifest, routing = await self.backend.collect_assignment(task, result, task_dir)
            revision = self.broker.record_assignment_result(
                task["id"], result, manifest=manifest, routing=routing
            )
            if revision is not None:
                await self.backend.seal_revision(task, revision, task_dir)
            self.event(
                "assignment_finished", task=task["id"], member=member["id"],
                status=result["status"], revision=revision["id"] if revision else None,
            )
            return revision
        except Exception as exc:
            self.broker.fail_assignment(task["id"], exc)
            self.event("assignment_failed", task=task["id"], error=str(exc))
            return None
        finally:
            if not quiesced:
                await self.backend.quiesce_member(member["id"])

    async def run(self):
        lead_prompt = (self.workspace / "roles/lead.system.md").read_text()
        self.event("run_started")
        try:
            await self.backend.start()
            while self.broker.state["status"] == "running":
                if self.broker.state["lead_turns"] >= self.broker._limit("max_lead_turns"):
                    self.broker.terminate_budget()
                    self.event("budget_exhausted", budget="max_lead_turns")
                    break
                turn = self.broker.state["lead_turns"] + 1
                turn_dir = self.directory / "lead" / f"turn-{turn:03d}"
                turn_dir.mkdir(parents=True)
                instruction = self._lead_instruction()
                (turn_dir / "instruction.md").write_text(instruction)
                self.event("lead_turn_started", turn=turn)
                session_id, response = await self.backend.execute_lead(
                    lead_prompt, instruction, self.broker.state["lead_session"], turn_dir
                )
                self.broker.set_lead_session(session_id)
                self.broker.record_lead_turn()
                # The turn is billed before its plan is judged: a rejected plan
                # still spent the model call that produced it.
                exhausted = self.broker.charge(
                    stream_cost([turn_dir / "claude-code.jsonl"])
                )
                try:
                    plan = parse_lead_plan(
                        response, max_actions=self.broker._limit("max_actions_per_turn")
                    )
                    effects = self.broker.apply_plan(plan)
                except ProtocolError as exc:
                    self.broker.state["last_plan_error"] = str(exc)
                    (turn_dir / "plan-rejection.txt").write_text(str(exc) + "\n")
                    self.event("lead_plan_rejected", turn=turn, error=str(exc))
                    if exhausted:
                        self.broker.terminate_budget("max_cost_usd")
                        self.event("budget_exhausted", budget="max_cost_usd",
                                   cost_usd=self.broker.state["cost_usd"])
                        break
                    continue
                self.broker.state.pop("last_plan_error", None)
                (turn_dir / "plan.json").write_text(
                    json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
                )
                self.event("lead_plan_accepted", turn=turn, summary=plan["summary"])
                # Accepted code revisions must be integrated before a downstream
                # assignment reads the shared repository in this same plan.
                for effect in effects:
                    if effect["type"] == "accept_revision":
                        await self.backend.accept_revision(
                            self.broker.state["revisions"][effect["revision_id"]], effect,
                            self.directory,
                        )
                assignments = [
                    effect["task"] for effect in effects
                    if effect["type"] == "execute_assignment"
                ]
                if assignments:
                    await asyncio.gather(*(
                        (self._run_assignment(task) for task in assignments)
                    ))
                # Add what the assignments spent on top of the already-billed turn.
                if assignments:
                    exhausted = self.broker.charge(stream_cost([
                        self.directory / "assignments" / task["id"] / "claude-code.jsonl"
                        for task in assignments
                    ])) or exhausted
                self.event("lead_turn_finished", turn=turn,
                           cost_usd=self.broker.state["cost_usd"])
                if exhausted and self.broker.state["status"] == "running":
                    self.broker.terminate_budget("max_cost_usd")
                    self.event("budget_exhausted", budget="max_cost_usd",
                               cost_usd=self.broker.state["cost_usd"])
                    break
            return self.broker.state
        except BaseException as exc:
            if self.broker.state["status"] == "running":
                self.broker.state.update(status="failed", delivery_complete=False, error=str(exc))
            self.event("run_failed", error=str(exc))
            raise
        finally:
            await self.backend.stop_all()
