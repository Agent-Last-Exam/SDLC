"""Harbor adapter: controller outside the sandbox, Codex inside it."""
import json
from pathlib import Path
import shlex

from harbor.agents.base import BaseAgent
from harbor_local.runtime.agents import PromptCodex
from harbor_local.runtime.workflow_controller import Controller


def native_role_evidence(directory, session_id, role):
    for path in directory.rglob("*.jsonl"):
        lines = path.read_text().splitlines()
        if not lines:
            continue
        try:
            first = json.loads(lines[0])
        except ValueError:
            continue
        if first.get("type") != "session_meta" or first.get("payload", {}).get("id") != session_id:
            continue  # A terminated child may have an incomplete trailing record.
        rows = [json.loads(line) for line in lines if line.strip()]
        active = [r for r in rows if r.get("type") == "response_item"
                  and r.get("payload", {}).get("role") == "developer"
                  and "SDLC_STAGE_ROLE:" in json.dumps(r, ensure_ascii=False)]
        if not active or f"SDLC_STAGE_ROLE: {role}" not in json.dumps(active[-1], ensure_ascii=False):
            raise RuntimeError("Native transcript does not contain the current developer-role Blueprint")
        return {"session_id": session_id, "active_role": role, "native_developer_message_verified": True,
                "role_activations_recorded": len(active)}
    raise RuntimeError("Principal native session transcript is missing")


class StageCodex(PromptCodex):
    allow_subagents = True

    async def exec_as_agent(self, environment, command, **kwargs):
        user = environment.default_user
        if isinstance(user, str) and user.startswith("stage"):
            kwargs["env"] = {**kwargs.get("env", {}), "HOME": "/home/" + user}
        if "codex exec " in command:
            command = "python3 /opt/sdlc/codex_app_turn.py /tmp/sdlc-app-request.json 2>&1 | tee /logs/agent/codex.txt"
        return await super().exec_as_agent(environment, command, **kwargs)


class HarborBackend:
    synthetic = False

    def __init__(self, agent, environment, context, workspace):
        self.agent, self.environment, self.context = agent, environment, context
        self.workspace = workspace
        self.stage_index = 0
        self.uid = None
        self.sealed_hashes = {}

    async def root(self, command):
        result = await self.environment.exec("set -e; " + command, user="root", cwd="/workspace")
        if result.return_code:
            raise RuntimeError(f"Controller sandbox operation failed: {result.stderr or result.stdout}")
        return result

    async def activate(self, stage, attempt, resume_session):
        self.uid = 1200 + self.stage_index * 10 + attempt
        self.user = f"stage{self.uid}"
        out = shlex.quote(stage["writable_directory"])
        cleanup_roots = ["/tmp", "/var/tmp", "/dev/shm"]
        if resume_session is None:
            cleanup_roots.append("/logs/agent")
        cleanup = (
            "import pathlib,shutil; roots=" + repr(cleanup_roots) + "; "
            "items=[p for r in roots for p in pathlib.Path(r).iterdir()]; "
            "[(shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()) for p in items]"
        )
        await self.root("python3 -c " + shlex.quote(cleanup))
        # Only this stage directory is agent-owned. Its parent and prior stages
        # stay root-owned. no-new-privileges blocks setuid privilege escalation.
        await self.root(
            f"id {self.user} >/dev/null 2>&1 || useradd -m -u {self.uid} -s /bin/bash {self.user}; "
            f"chmod 700 /home/{self.user}; "
            "rm -rf /workspace/scratch /tmp/codex-home /tmp/codex-secrets; "
            f"mkdir -p /workspace/scratch {out} /logs/agent; "
            f"chown -R {self.uid}:{self.uid} /workspace/scratch {out} /logs/agent; "
            f"chmod -R u+rwX {out}; "
            "chmod 755 /workspace/scratch; "
            + ("rm -rf /logs/agent/sessions; " if resume_session is None else "")
            + "true"
        )
        self.environment.default_user = self.user
        # Prove the actual execution identity cannot mutate public input or an
        # accepted stage. The subprocess runs as exactly the upcoming Agent UID.
        targets = ["/workspace/instruction.md", "/workspace/roles", "/workspace/templates", "/workspace/repos"]
        if self.stage_index:
            targets.append("/workspace/artifacts/sprint1/prd/prd.md")
        probe = "python3 -c " + shlex.quote(
            "import os,pathlib; assert os.getuid()!=0; "
            f"assert all(not os.access(p,os.W_OK) for p in {targets!r}); "
            f"assert os.access({stage['writable_directory']!r},os.W_OK); "
            "assert not os.path.exists('/var/run/docker.sock'); "
            "assert 'NoNewPrivs:\\t1' in pathlib.Path('/proc/self/status').read_text(); "
            f"marker=pathlib.Path({stage['writable_directory']!r})/'.permission-probe'; "
            "marker.write_text('stage write allowed'); marker.unlink()"
        )
        result = await self.environment.exec(probe, user=self.user)
        if result.return_code:
            raise RuntimeError("Stage filesystem isolation probe failed")

    async def execute(self, stage, prompt, instruction, resume_session, attempt_dir):
        self.agent.prompt_text = prompt
        request_path = attempt_dir / "app-request.json"
        request_path.write_text(json.dumps({"model": self.agent.model_name, "prompt": prompt,
                                           "instruction": instruction, "session_id": resume_session,
                                           "allow_subagents": self.agent.allow_subagents}, ensure_ascii=False))
        await self.environment.upload_file(request_path, "/tmp/sdlc-app-request.json")
        self.agent._resume = bool(resume_session)
        try:
            await self.agent.run(instruction, self.environment, self.context)
        finally:
            self.agent._resume = False
        await self.quiesce()
        await self.environment.download_file("/logs/agent/codex.txt", attempt_dir / "codex.jsonl")
        await self.environment.download_dir("/logs/agent/sessions", attempt_dir / "sessions")
        ids = []
        for line in (attempt_dir / "codex.jsonl").read_text().splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "thread.started":
                ids.append(event["thread_id"])
        if len(set(ids)) != 1:
            raise RuntimeError("Expected exactly one principal thread.started event")
        evidence = native_role_evidence(attempt_dir / "sessions", ids[0], stage["role"])
        (attempt_dir / "native-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        return ids[0]

    async def quiesce(self):
        if self.uid is not None:
            # Applies to CLI subprocesses and any background tools/subagents.
            await self.root(f"pkill -KILL -u {self.uid} || test $? -eq 1")
            await self.root("python3 -c " + shlex.quote(
                "import subprocess,time; "
                f"uid={self.uid}; "
                "live=lambda: [r for r in subprocess.check_output(['ps','-eo','uid=,stat='],text=True).splitlines() "
                "if r.split()[0]==str(uid) and not r.split()[1].startswith('Z')]; "
                "time.sleep(0.1); assert not live(), 'Old stage still has live processes'"
            ))

    async def collect(self, stage, destination):
        out = stage["writable_directory"]
        # Check before tar transfer; following a link could pull a credential or
        # unrelated file into the host artifact store.
        script = "import os,pathlib,stat; p=pathlib.Path(" + repr(out) + "); "
        script += "assert p.is_dir() and not p.is_symlink(); "
        script += "assert all(not x.is_symlink() and (x.is_dir() or stat.S_ISREG(x.stat().st_mode)) for x in p.rglob('*'))"
        await self.root("python3 -c " + shlex.quote(script))
        await self.environment.download_dir(out, destination)

    async def seal(self, stage, hashes):
        out = stage["writable_directory"]
        await self.root(f"chown -R root:root {shlex.quote(out)} && chmod -R a-w {shlex.quote(out)}")
        self.sealed_hashes.update({out + "/" + rel: value for rel, value in hashes.items()})
        script = "import hashlib,pathlib; expected=" + repr(self.sealed_hashes) + "; "
        script += "assert all(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h for p,h in expected.items())"
        await self.root("python3 -c " + shlex.quote(script))


class WorkflowCodex(BaseAgent):
    SUPPORTS_ATIF = False  # Native per-attempt JSONL is retained without merging child trajectories.

    def __init__(self, *args, prepared_path, smoke=False, role_probe=False, continue_from=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.prepared = Path(prepared_path)
        self.compiled = json.loads((self.prepared / "resolved-workflow.json").read_text())
        self.smoke = smoke
        self.role_probe = role_probe
        self.continue_from = Path(continue_from) if continue_from else None
        self.delegate = StageCodex(
            logs_dir=self.logs_dir, model_name=self.model_name, logger=self.logger,
            system_prompt_path=self.prepared / "workspace/roles/pm.system.md",
            version="0.154.0", reasoning_effort="high", web_search="disabled",
        )
        self.delegate.allow_subagents = self.compiled["run"]["execution"].get("subagents", {}).get("enabled", False)

    @staticmethod
    def name():
        return "sdlc-workflow-codex"

    def version(self):
        return "0.154.0"

    async def setup(self, environment):
        await self.delegate.setup(environment)
        await self.delegate.exec_as_root(environment, "mkdir -p /opt/sdlc")
        await environment.upload_file(Path(__file__).parent / "codex_app_turn.py", "/opt/sdlc/codex_app_turn.py")
        await self.delegate.exec_as_root(environment, "chmod 555 /opt/sdlc/codex_app_turn.py")

    async def run(self, instruction, environment, context):
        # Sibling of /logs/agent, not inside any mounted Agent-writable log root.
        control_dir = self.logs_dir.parent / "workflow"
        backend = HarborBackend(self.delegate, environment, context, self.prepared / "workspace")
        if self.role_probe:
            control_dir.mkdir(parents=True)
            session = None
            records = []
            for index, stage in enumerate(self.compiled["stages"]):
                backend.stage_index = index
                attempt_dir = control_dir / stage["role"]
                attempt_dir.mkdir()
                expected = stage["role"].upper() + "_READY"
                prompt = (f"SDLC_STAGE_ROLE: {stage['role']}\n"
                          f"本条 developer 指令替代之前的活动角色。你现在的角色是 {stage['role']}。"
                          f"不得调用任何工具，不读写任何文件。最终只回复 {expected}。")
                await backend.activate(stage, 1, session)
                try:
                    actual = await backend.execute(stage, prompt, "按当前活动角色回复标识。", session, attempt_dir)
                finally:
                    await backend.quiesce()
                if session and actual != session:
                    raise RuntimeError("Role probe changed native session")
                session = actual
                messages = []
                for line in (attempt_dir / "codex.jsonl").read_text().splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    item = event.get("params", {}).get("item", {})
                    if item.get("type") == "agentMessage":
                        messages.append(item.get("text", ""))
                if not messages or messages[-1].strip() != expected:
                    raise RuntimeError(f"Role probe response mismatch: {messages}")
                records.append({"role": stage["role"], "session_id": session, "response": expected})
            (control_dir / "state.json").write_text(json.dumps({"status": "complete", "role_probe": True, "records": records}, indent=2))
            return
        if self.smoke:
            from harbor_local.runtime.workflow_smoke import SmokeBackend
            backend = SmokeBackend(backend)
        recovery = self.continue_from / "workflow" if self.continue_from else None
        controller = Controller(self.compiled, self.prepared / "workspace", control_dir, backend, recovery=recovery)
        if self.continue_from:
            old_sessions = self.continue_from / "agent/sessions"
            if not list(old_sessions.rglob("*.jsonl")):
                raise RuntimeError("Cannot continue Single: native session transcript missing")
            await environment.upload_dir(old_sessions, "/logs/agent/sessions")
            await environment.upload_dir(controller.accepted_prd.parent, "/workspace/artifacts/sprint1/prd")
            await backend.seal(self.compiled["stages"][0], controller.state["stages"][0]["outputs"])
        await controller.run()
