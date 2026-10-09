"""Host-side, forward-only controller independent of the Agent backend."""
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import time

from runtime.agent_cost import stream_cost


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stage_routing(stage, directory):
    """Read only the fields needed to select the next stage, without grading outputs."""
    if stage["role"] not in {"qa", "triage"}:
        return {}
    name, key = (("test-verify.json", "verdict") if stage["role"] == "qa"
                 else ("repair-plan.json", "design_changed"))
    try:
        data = json.loads((directory / name).read_text())
        value = data[key]
        valid = (isinstance(value, str) and value in {"pass", "fail"}
                 if key == "verdict" else isinstance(value, bool))
        if not valid:
            raise ValueError(f"Invalid {key}: {value!r}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"Cannot route stage {stage['stage_id']} using {name}: {exc}") from exc
    return {key: value}


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


class Controller:
    def __init__(self, compiled, workspace, directory, backend, stop_after_stage=None,
                 missing_output_policy="fail"):
        if compiled["mode"] not in {"single", "flat"}:
            raise ValueError("Only Single and Flat lifecycle execution are implemented")
        self.compiled, self.workspace = compiled, Path(workspace)
        self.directory, self.backend = Path(directory), backend
        self.max_cost_usd = compiled["run"]["execution"]["max_cost_usd"]
        # The stage graph is the only source of QA rounds; a sprint added there
        # raises the count with no configuration to keep in step.
        self.qa_rounds = max(
            stage["round"] for stage in compiled["stages"] if stage["role"] == "qa"
        )
        if compiled["contract"].get("scope") != "local_sdlc":
            raise ValueError("Only the local_sdlc lifecycle contract is supported")
        stage_ids = {stage["stage_id"] for stage in compiled["stages"]}
        if stop_after_stage is not None and stop_after_stage not in stage_ids:
            raise ValueError(f"Unknown stop stage: {stop_after_stage}")
        if missing_output_policy not in {"fail", "continue_for_evaluation"}:
            raise ValueError(f"Unknown missing output policy: {missing_output_policy}")
        if missing_output_policy == "continue_for_evaluation":
            if stop_after_stage is None:
                raise ValueError("Evaluation output policy requires an explicit stop stage")
            boundary = next(index for index, stage in enumerate(compiled["stages"])
                            if stage["stage_id"] == stop_after_stage)
            if any(stage["role"] not in {"pm", "architect", "qa-design"}
                   for stage in compiled["stages"][:boundary + 1]):
                raise ValueError("Evaluation output policy is limited to document stages")
        self.stop_after_stage = stop_after_stage
        self.missing_output_policy = missing_output_policy
        self.directory.mkdir(parents=True, exist_ok=True)
        if (self.directory / "state.json").exists():
            raise ValueError("Controller state already exists; refuse to replay an accepted stage")
        self.state = {"mode": compiled["mode"], "status": "running", "cursor": 0, "stages": [],
                      "model_called": not backend.synthetic, "synthetic": backend.synthetic,
                      "missing_output_policy": missing_output_policy, "delivery_complete": True,
                      "max_cost_usd": self.max_cost_usd, "cost_usd": 0.0}
        if compiled["mode"] == "flat":
            self.state["principal_sessions"] = []
        self.accepted_prd = None
        self.baseline = {}

    def charge_stage(self, stage, stage_dir):
        """Accumulate the Stage's reported spend; returns True when the budget is spent.

        Cost comes from the Agent's own result events. A Stage that reports nothing
        adds nothing, so a missing stream never fabricates spend or hides it.
        """
        spent = stream_cost([stage_dir / "claude-code.jsonl"])
        if spent is not None:
            self.state["cost_usd"] = round(self.state["cost_usd"] + spent, 6)
        return self.state["cost_usd"] >= self.max_cost_usd

    def freeze_baseline(self, stage, hashes):
        names = {"sprint1/prd": "prd.md", "sprint1/test-design": "test-cases.v1.csv"}
        sid = stage["stage_id"]
        if sid not in names:
            return
        name = names[sid]
        ref = next(ref for ref, path in stage["outputs"].items() if Path(path).name == name)
        relative = str(Path(stage["outputs"][ref]).relative_to(stage["writable_directory"]))
        if relative not in hashes:
            return
        if ref in self.baseline:
            raise RuntimeError("Baseline cannot be replaced within a run")
        self.baseline[ref] = {"path": stage["outputs"][ref], "sha256": hashes[relative], "source_stage": sid}
        if len(self.baseline) == 2:
            path = self.directory / "baseline.json"
            if path.exists():
                raise RuntimeError("Baseline already exists")
            atomic_json(path, {"version": 1, "artifacts": self.baseline})
            self.state["baseline_sha256"] = digest(path)

    async def check_baseline(self, stage=None):
        try:
            for ref, entry in self.baseline.items():
                relative = Path(entry["path"]).relative_to("/workspace/artifacts")
                path = self.directory / "accepted" / relative
                if path.is_symlink() or digest(path) != entry["sha256"]:
                    raise ValueError(f"Content changed: {ref}")
                if stage and ref in stage["inputs"] and stage["inputs"][ref] != entry["path"]:
                    raise ValueError(f"Input redirected: {ref}")
            if "baseline_sha256" in self.state:
                if digest(self.directory / "baseline.json") != self.state["baseline_sha256"]:
                    raise ValueError("Manifest changed")
            await self.backend.verify_baseline(self.baseline)
        except (OSError, ValueError, RuntimeError) as exc:
            raise RuntimeError(f"Baseline integrity check failed: {exc}") from exc

    def event(self, event, **values):
        with (self.directory / "events.jsonl").open("a") as stream:
            stream.write(json.dumps({"time": time.time(), "event": event, **values}, ensure_ascii=False) + "\n")
        atomic_json(self.directory / "state.json", self.state)

    async def run(self):
        session = None
        flat_sessions = set()
        continuous_session = self.compiled["mode"] == "single"
        repair_plan = None
        self.event("run_started")
        try:
            for index, stage in enumerate(self.compiled["stages"]):
                if self.state["cursor"] != index:
                    raise RuntimeError("Invalid stage cursor")
                self.backend.stage_index = index
                stage_record = {"id": stage["stage_id"], "role": stage["role"], "status": "running"}
                self.state["stages"].append(stage_record)
                if stage.get("reuse_unless") and not repair_plan[stage["reuse_unless"]]:
                    await self.check_baseline(stage)
                    source = self.directory / "accepted" / stage["reuse_stage"]
                    sealed = self.directory / "accepted" / stage["stage_id"]
                    shutil.copytree(source, sealed)
                    hashes = {str(p.relative_to(sealed)): digest(p) for p in sorted(sealed.rglob("*")) if p.is_file()}
                    await self.backend.reuse(stage, sealed)
                    await self.backend.seal(stage, hashes)
                    await self.check_baseline(stage)
                    stage_record.update(status="accepted", outputs=hashes, reused_from=stage["reuse_stage"])
                    self.state["cursor"] = index + 1
                    self.event("stage_reused", stage=stage["stage_id"], source=stage["reuse_stage"])
                    continue
                await self.check_baseline(stage)
                stage_dir = self.directory / "stages" / stage["stage_id"]
                stage_dir.mkdir(parents=True)
                role = (self.workspace / "roles" / f"{stage['role']}.system.md").read_text()
                artifact_inputs = {
                    ref: self.directory / "accepted" / Path(path).relative_to("/workspace/artifacts")
                    for ref, path in stage["inputs"].items() if ref.startswith("artifact:")
                }
                missing_inputs = [
                    {"ref": ref, "path": stage["inputs"][ref]}
                    for ref, path in artifact_inputs.items()
                    if not path.is_file() or path.is_symlink()
                ]
                inputs = "\n".join(f"- `{path}`" for path in stage["inputs"].values())
                outputs = "\n".join(f"- `{path}`" for path in stage["outputs"].values())
                previous = self.state["stages"][-2]["id"] if len(self.state["stages"]) > 1 else None
                transition = (f"上一阶段 {previous} 已结束。" if previous else "工作流开始。")
                transition += f"当前进入 {stage['stage_id']}，第 {stage.get('round', 1)} 轮。"
                if continuous_session:
                    transition += ("历史消息保留用于参考；此前阶段的职责和交付要求不再是当前任务。"
                                   "本条阶段 system prompt 和 user 消息定义本阶段职责、可写范围和完成条件。\n")
                else:
                    transition += ("这是一个全新的 Flat Stage 主会话，不继承上一 Stage 的聊天历史。"
                                   "跨阶段信息只来自 Workspace 中下列声明输入和已接受产物。"
                                   "本条阶段 system prompt 和 user 消息定义本阶段职责、可写范围和完成条件。\n")
                writable = [stage["writable_directory"], stage["scratch"]]
                if stage.get("write_repos"):
                    writable.append("/workspace/repos")
                active_prompt = (
                    transition + "\n你现在的角色和工作如下。\n\n" + role
                    + f"\n\n本次使用的材料路径：\n{inputs}\n\n本次交付文件的路径：\n{outputs}\n"
                    + f"\n可写范围：{', '.join(writable)}。材料只读；具体读写权限以当前环境为准。"
                    + "\n完成条件：按模板保存全部本阶段文件后结束本阶段。"
                    + "\n已封存的 PRD 和测试用例为冻结基线，本次运行禁止修改或替换；发现问题只在当前报告中说明。"
                    + f"\n<!-- SDLC_STAGE_ROLE: {stage['role']} -->\n"
                    + f"<!-- SDLC_STAGE_ID: {stage['stage_id']} -->\n"
                )
                subagents = self.compiled["run"]["execution"].get("subagents", {})
                if subagents.get("enabled"):
                    active_prompt += (
                        "\n当前 Stage 允许使用 Claude Code multi-agent，把互相独立的工作拆给多个 subagent。"
                        "所有 subagent 只服务当前 Stage，并共享当前 Sandbox/Workspace。"
                        "并发写任务必须划分互不重叠的文件或写入范围，禁止多个 Agent 同时修改同一文件。"
                        "你作为当前 Stage 主 Agent，负责检查并整合正式交付。"
                        "结束本阶段前必须等待所有 subagent 完成，不得把子会话延续到下一 Stage。\n"
                    )
                if missing_inputs:
                    missing_paths = "\n".join(f"- `{item['path']}`" for item in missing_inputs)
                    active_prompt += (
                        "\n以下上游材料未交付。按缺失事实继续当前阶段，不得代写或回填上游文件；"
                        "只基于现有材料完成本阶段并明确受影响内容：\n" + missing_paths + "\n"
                    )
                instruction = "请根据这些材料完成你的工作，将交付文件保存到指定位置。"
                (stage_dir / "role.md").write_text(active_prompt)
                (stage_dir / "instruction.md").write_text(instruction)
                prior_hash = digest(self.accepted_prd) if self.accepted_prd else None
                input_hashes = {ref: digest(path) for ref, path in artifact_inputs.items()
                                if path.is_file() and not path.is_symlink()}
                resume_session = session if continuous_session else None
                self.event("stage_started", stage=stage["stage_id"], resume_session=resume_session,
                           role_sha256=hashlib.sha256(active_prompt.encode()).hexdigest(),
                           prd_input_sha256=prior_hash, missing_inputs=missing_inputs)
                await self.backend.activate(stage, resume_session)
                await self.check_baseline(stage)
                stage_record["execution_started"] = True
                self.event("stage_execution_started", stage=stage["stage_id"])
                try:
                    actual_session = await self.backend.execute(
                        stage, active_prompt, instruction, resume_session, stage_dir
                    )
                finally:
                    try:
                        await self.backend.quiesce()
                    finally:
                        await self.check_baseline(stage)
                if not isinstance(actual_session, str) or not actual_session:
                    raise RuntimeError("Backend did not return a principal native session ID")
                if continuous_session:
                    if session and actual_session != session:
                        raise RuntimeError(f"Native session changed during resume: {session} -> {actual_session}")
                    session = actual_session
                    self.state["principal_session"] = session
                else:
                    if actual_session in flat_sessions:
                        raise RuntimeError(f"Flat Stage reused a principal native session: {actual_session}")
                    flat_sessions.add(actual_session)
                    self.state["principal_sessions"].append({
                        "stage_id": stage["stage_id"],
                        "role": stage["role"],
                        "session_id": actual_session,
                    })
                sealed = self.directory / "accepted" / stage["stage_id"]
                sealed.parent.mkdir(parents=True, exist_ok=True)
                stage_record.update(session_id=actual_session, prd_input_sha256=prior_hash,
                                    input_sha256=input_hashes, missing_inputs=missing_inputs)
                try:
                    await self.backend.collect(stage, sealed)
                    if stage["role"] == "qa":
                        await self.backend.collect_service_logs(stage_dir)
                    missing_outputs = []
                    for ref, path in stage["outputs"].items():
                        output = sealed / Path(path).relative_to(stage["writable_directory"])
                        if not output.is_file() or output.is_symlink():
                            missing_outputs.append({"ref": ref, "path": path})
                    if missing_outputs and self.missing_output_policy == "fail":
                        raise RuntimeError(f"Missing regular output: {missing_outputs[0]['path']}")
                    details = stage_routing(stage, sealed)
                    if stage["role"] == "deployer":
                        await self.backend.deploy(stage, sealed, stage_dir)
                finally:
                    await self.check_baseline(stage)
                hashes = {str(p.relative_to(sealed)): digest(p) for p in sorted(sealed.rglob("*")) if p.is_file()}
                if stage.get("capture_repos"):
                    snapshot = self.directory / "candidates" / stage["stage_id"]
                    snapshot.mkdir(parents=True)
                    stage_record["candidate"] = await self.backend.capture_repositories(snapshot)
                await self.backend.seal(stage, hashes)
                self.freeze_baseline(stage, hashes)
                await self.check_baseline(stage)
                stage_record.update(status="accepted", outputs=hashes,
                                    missing_outputs=missing_outputs,
                                    delivery_complete=not missing_outputs)
                if missing_outputs:
                    self.state["delivery_complete"] = False
                if details:
                    stage_record["routing"] = details
                if stage["role"] == "pm":
                    prd = sealed / "prd.md"
                    self.accepted_prd = prd if prd.is_file() and not prd.is_symlink() else None
                self.state["cursor"] = index + 1
                exhausted = self.charge_stage(stage, stage_dir)
                stage_record["cost_usd"] = self.state["cost_usd"]
                self.event("stage_accepted", stage=stage["stage_id"], hashes=hashes,
                           missing_outputs=missing_outputs, cost_usd=self.state["cost_usd"])
                if stage["role"] == "triage":
                    repair_plan = details
                if stage["stage_id"] == self.stop_after_stage:
                    self.state["status"] = "stopped_at_boundary"
                    self.state["stop_after_stage"] = self.stop_after_stage
                    self.event("run_stopped_at_boundary", stage=self.stop_after_stage)
                    return self.state
                if stage["role"] == "qa":
                    self.state["qa_verdict"] = details["verdict"]
                    if details["verdict"] == "pass" or stage["round"] >= self.qa_rounds:
                        self.state["status"] = "complete" if details["verdict"] == "pass" else "qa_failed"
                        self.event("run_completed" if details["verdict"] == "pass" else "qa_rounds_exhausted",
                                   round=stage["round"], verdict=details["verdict"])
                        return self.state
                # Checked last so a run that already reached its own end is not
                # relabelled; the accepted Stage keeps its outputs either way.
                if exhausted:
                    self.state.update(status="budget_exhausted", delivery_complete=False)
                    self.event("budget_exhausted", budget="max_cost_usd",
                               cost_usd=self.state["cost_usd"], limit=self.max_cost_usd,
                               stage=stage["stage_id"])
                    return self.state
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
        finally:
            await self.backend.stop_services()
