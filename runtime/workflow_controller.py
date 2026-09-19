"""Host-side, forward-only controller independent of the Agent backend."""
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import time

from runtime.workflow_gates import GateError, digest, validate_stage


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


class Controller:
    def __init__(self, compiled, workspace, directory, backend, attempts=2, recovery=None):
        if compiled["mode"] not in {"single", "flat"}:
            raise ValueError("Hierarchical execution is not implemented; cannot silently use a fixed workflow")
        self.compiled, self.workspace = compiled, Path(workspace)
        self.directory, self.backend = Path(directory), backend
        self.attempts = attempts
        self.directory.mkdir(parents=True, exist_ok=True)
        if (self.directory / "state.json").exists():
            raise ValueError("Controller state already exists; refuse to replay an accepted stage")
        self.state = {"mode": compiled["mode"], "status": "running", "cursor": 0, "stages": [],
                      "model_called": not backend.synthetic, "synthetic": backend.synthetic}
        self.accepted_prd = None
        self.initial_session = None
        if recovery is not None:
            source = Path(recovery)
            previous = json.loads((source / "state.json").read_text())
            if previous["status"] not in {"failed", "interrupted"} or previous["cursor"] != 1:
                raise ValueError("Only a failed/interrupted run with an accepted PRD can be continued")
            if previous["mode"] != compiled["mode"]:
                raise ValueError("Recovery mode differs from original run")
            accepted = previous["stages"][0]
            if accepted["status"] != "accepted" or accepted["id"] != compiled["stages"][0]["stage_id"]:
                raise ValueError("Recovery has no compatible accepted PRD stage")
            old = source / "accepted" / accepted["id"]
            for name, expected in accepted["outputs"].items():
                if digest(old / name) != expected:
                    raise ValueError("Recovery accepted artifact hash changed")
            new = self.directory / "accepted" / accepted["id"]
            new.parent.mkdir(parents=True)
            shutil.copytree(old, new)
            self.accepted_prd = new / "prd.md"
            self.initial_session = accepted["attempts"][-1]["session_id"]
            self.state.update(cursor=1, stages=[accepted], continued_from=str(source),
                              principal_session=self.initial_session)

    def event(self, event, **values):
        with (self.directory / "events.jsonl").open("a") as stream:
            stream.write(json.dumps({"time": time.time(), "event": event, **values}, ensure_ascii=False) + "\n")
        atomic_json(self.directory / "state.json", self.state)

    async def run(self):
        session = self.initial_session
        self.event("run_started")
        try:
            for index, stage in enumerate(self.compiled["stages"]):
                if index < self.state["cursor"]:
                    continue
                if self.state["cursor"] != index:
                    raise RuntimeError("Invalid stage cursor")
                self.backend.stage_index = index
                feedback = None
                if self.compiled["mode"] == "flat":
                    session = None
                stage_record = {"id": stage["stage_id"], "role": stage["role"], "status": "running", "attempts": []}
                self.state["stages"].append(stage_record)
                for attempt in range(1, self.attempts + 1):
                    attempt_dir = self.directory / "attempts" / stage["stage_id"] / str(attempt)
                    attempt_dir.mkdir(parents=True)
                    role = (self.workspace / "roles" / f"{stage['role']}.system.md").read_text()
                    active_prompt = (
                        f"SDLC_STAGE_ROLE: {stage['role']}\nSDLC_STAGE_ID: {stage['stage_id']}\n"
                        "当前活动角色取代历史阶段角色；历史角色不再授权写入或继续执行。"
                        "只完成当前阶段并写出规定文件，然后结束本轮响应；阶段推进由外部 Controller 负责。\n\n" + role
                    )
                    instruction = "读取当前阶段声明的输入并完成正式输出。\n" + json.dumps(stage, ensure_ascii=False, indent=2)
                    if feedback:
                        instruction += "\n上一提交未通过公开结构检查。仅修正当前阶段产物：\n" + feedback
                    (attempt_dir / "role.md").write_text(active_prompt)
                    (attempt_dir / "instruction.md").write_text(instruction)
                    prior_hash = digest(self.accepted_prd) if self.accepted_prd else None
                    self.event("stage_started", stage=stage["stage_id"], attempt=attempt, resume_session=session,
                               role_sha256=hashlib.sha256(active_prompt.encode()).hexdigest(), prd_input_sha256=prior_hash)
                    await self.backend.activate(stage, attempt, session)
                    try:
                        actual_session = await self.backend.execute(stage, active_prompt, instruction, session, attempt_dir)
                    finally:
                        await self.backend.quiesce()
                    if session and actual_session != session:
                        raise RuntimeError(f"Native session changed during resume: {session} -> {actual_session}")
                    session = actual_session
                    candidate = attempt_dir / "outputs"
                    await self.backend.collect(stage, candidate)
                    record = {"attempt": attempt, "session_id": session, "status": "submitted",
                              "prd_input_sha256": prior_hash}
                    stage_record["attempts"].append(record)
                    self.event("stage_submitted", stage=stage["stage_id"], attempt=attempt)
                    try:
                        details = validate_stage(stage, candidate, self.workspace, self.accepted_prd)
                    except GateError as exc:
                        feedback = str(exc)
                        record.update(status="rejected", error=feedback)
                        self.event("gate_rejected", stage=stage["stage_id"], attempt=attempt, error=feedback)
                        if attempt == self.attempts:
                            raise
                        continue
                    sealed = self.directory / "accepted" / stage["stage_id"]
                    sealed.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(candidate, sealed)
                    hashes = {str(p.relative_to(sealed)): digest(p) for p in sorted(sealed.rglob("*")) if p.is_file()}
                    await self.backend.seal(stage, hashes)
                    if self.accepted_prd and digest(self.accepted_prd) != prior_hash:
                        raise RuntimeError("Accepted PRD changed")
                    record.update(status="accepted", hashes=hashes, gate=details)
                    stage_record.update(status="accepted", outputs=hashes)
                    if stage["role"] == "pm":
                        self.accepted_prd = sealed / "prd.md"
                    self.state["cursor"] = index + 1
                    self.event("stage_accepted", stage=stage["stage_id"], hashes=hashes)
                    if details.get("review_outcome") == "blocked":
                        self.state["status"] = "blocked"
                        self.event("run_blocked", reason="technical_review")
                        return self.state
                    break
            self.state["status"] = "complete"
            self.event("run_completed")
            return self.state
        except BaseException as exc:
            self.state["status"] = "interrupted" if isinstance(exc, asyncio.CancelledError) else "failed"
            self.state["error"] = str(exc)
            if self.state["stages"] and self.state["stages"][-1]["status"] == "running":
                self.state["stages"][-1]["status"] = "failed"
            self.event("run_failed", error=str(exc))
            raise
