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
                    inputs = "\n".join(f"- `{path}`" for path in stage["inputs"].values())
                    outputs = "\n".join(f"- `{path}`" for path in stage["outputs"].values())
                    active_prompt = (
                        "你现在的角色和工作如下。\n\n" + role
                        + f"\n\n本次使用的材料路径：\n{inputs}\n\n本次交付文件的路径：\n{outputs}\n"
                        + f"\n<!-- SDLC_STAGE_ROLE: {stage['role']} -->\n"
                    )
                    instruction = "请根据这些材料完成你的工作，将交付文件保存到指定位置。"
                    if feedback:
                        instruction += "\n提交的文档有以下格式问题，请修正后重新保存：\n" + feedback
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
