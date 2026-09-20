"""Harbor adapter: controller outside the sandbox, Codex inside it."""
import json
from pathlib import Path
import re
import shlex

from harbor.agents.base import BaseAgent
from runtime.agents import PromptCodex
from runtime.workflow_controller import Controller, digest
from runtime.local_deployment import validate_manifest
from runtime.trajectory import export_trajectory


def native_role_evidence(directory, session_id, role, stage_id=None):
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
        content = active[-1]["payload"].get("content", []) if active else []
        active_text = content if isinstance(content, str) else "\n".join(item.get("text", "") for item in content)
        if not re.search(r"SDLC_STAGE_ROLE: " + re.escape(role) + r"(?:\s|-->|$)", active_text):
            raise RuntimeError("Native transcript does not contain the current developer-role Blueprint")
        if stage_id and not re.search(r"SDLC_STAGE_ID: " + re.escape(stage_id) + r"(?:\s|-->|$)", active_text):
            raise RuntimeError("Native transcript contains a stale stage activation")
        return {"session_id": session_id, "active_role": role, "native_developer_message_verified": True,
                "stage_id": stage_id,
                "role_activations_recorded": len(active)}
    raise RuntimeError("Principal native session transcript is missing")


class StageCodex(PromptCodex):
    allow_subagents = True

    async def exec_as_agent(self, environment, command, **kwargs):
        user = environment.default_user
        if isinstance(user, str) and user.startswith("stage"):
            kwargs["env"] = {**kwargs.get("env", {}), "HOME": "/home/" + user}
        if "codex exec " in command:
            command = "bash -o pipefail -c " + shlex.quote(
                "python3 /opt/sdlc/codex_app_turn.py /tmp/sdlc-app-request.json 2>&1 | tee /logs/agent/codex.txt")
        return await super().exec_as_agent(environment, command, **kwargs)


class HarborBackend:
    synthetic = False

    def __init__(self, agent, environment, context, workspace):
        self.agent, self.environment, self.context = agent, environment, context
        self.workspace = workspace
        self.stage_index = 0
        self.uid = None
        self.stage_uids = set()
        self.sealed_hashes = {}
        self.repository_digest = None
        self.deployment_evidence = None

    async def root(self, command):
        result = await self.environment.exec("set -e; " + command, user="root", cwd="/workspace")
        if result.return_code:
            raise RuntimeError(f"Controller sandbox operation failed: {result.stderr or result.stdout}")
        return result

    async def activate(self, stage, resume_session):
        if self.repository_digest is None:
            self.repository_digest = (await self.repository_inventory())["sha256"]
        if stage["role"] in {"developer", "deployer"}:
            await self.stop_services()
        # Previous stage processes have been quiesced. Shared /tmp and /dev/shm
        # also contain live service resources, so clean only retired stage UIDs.
        await self.root("python3 /opt/sdlc/workspace_cleanup.py " + " ".join(map(str, sorted(self.stage_uids))))
        self.uid = 1200 + self.stage_index * 10 + 1
        self.stage_uids.add(self.uid)
        self.user = f"stage{self.uid}"
        out = shlex.quote(stage["writable_directory"])
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
        if stage.get("write_repos"):
            await self.root(f"chown -R {self.uid}:{self.uid} /workspace/repos; chmod -R u+rwX /workspace/repos")
        else:
            await self.root("chown -R root:root /workspace/repos; chmod -R a-w /workspace/repos")
        # Prove the actual execution identity cannot mutate public input or an
        # accepted stage. The subprocess runs as exactly the upcoming Agent UID.
        targets = ["/workspace/instruction.md", "/workspace/roles", "/workspace/templates", "/workspace/repos"]
        if stage.get("write_repos"):
            targets.remove("/workspace/repos")
        if self.stage_index:
            targets.extend(self.sealed_hashes)
            targets.extend(str(Path(p).parent) for p in self.sealed_hashes)
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

    async def repository_inventory(self):
        result = await self.root("python3 /opt/sdlc/workspace_snapshot.py")
        return json.loads(result.stdout)

    async def capture_repositories(self, destination):
        result = await self.root("python3 /opt/sdlc/workspace_snapshot.py /tmp/sdlc-candidate.tar")
        inventory = json.loads(result.stdout)
        await self.environment.download_file("/tmp/sdlc-candidate.tar", destination / "repos.tar")
        (destination / "manifest.json").write_text(json.dumps(inventory, indent=2) + "\n")
        self.repository_digest = inventory["sha256"]
        return {"sha256": inventory["sha256"], "archive_sha256": digest(destination / "repos.tar")}

    async def reuse(self, stage, source):
        await self.environment.upload_dir(source, stage["writable_directory"])

    async def stop_services(self):
        await self.root("if id sdlcservice >/dev/null 2>&1; then "
                        "pkill -TERM -u sdlcservice || test $? -eq 1; "
                        "python3 -c " + shlex.quote(
                            "import subprocess,time; "
                            "live=lambda: [r for r in subprocess.check_output(['ps','-eo','uid=,stat='],text=True).splitlines() "
                            "if r.split()[0]=='1800' and not r.split()[1].startswith('Z')]; "
                            "deadline=time.monotonic()+5\n"
                            "while live() and time.monotonic()<deadline: time.sleep(.1)\n")
                        + "; pkill -KILL -u sdlcservice || test $? -eq 1; fi")
        self.deployment_evidence = None

    async def deploy(self, stage, candidate, stage_dir):
        validate_manifest(json.loads((candidate / "deployment.json").read_text()))
        await self.stop_services()
        # Materialize after the Agent has stopped: its leftover deployment
        # directory cannot become the release.
        script = ("import sys,json; sys.path.insert(0,'/opt/sdlc'); "
                  "from local_deployment import materialize; "
                  "print(json.dumps(materialize('/workspace/repos','/workspace/deployment',"
                  + repr(self.repository_digest) + ")))" )
        try:
            binding = json.loads((await self.root("python3 -c " + shlex.quote(script))).stdout)
        except RuntimeError as exc:
            raise RuntimeError("Could not materialize the accepted deployment candidate") from exc
        binding.update(stage_id=stage["stage_id"],
                       manifest_sha256=digest(candidate / "deployment.json"))
        await self.root("id sdlcservice >/dev/null 2>&1 || useradd -m -u 1800 -s /bin/bash sdlcservice; "
                        "chown -R sdlcservice:sdlcservice /workspace/deployment; "
                        "chmod -R u+rwX /workspace/deployment; "
                        "chown -R root:root /workspace/repos; chmod -R a-w /workspace/repos")
        # Launch exactly the bytes validated on the host, readable by the
        # service UID even if the Agent created its draft with mode 0600.
        manifest = "/opt/sdlc/deployment.json"
        await self.environment.upload_file(candidate / "deployment.json", manifest)
        await self.root("chmod 444 " + shlex.quote(manifest))
        evidence_file = "/workspace/deployment/.readiness.json"
        result = await self.environment.exec(
            "python3 /opt/sdlc/local_deployment.py " + shlex.quote(manifest) + " " + shlex.quote(evidence_file),
            user="sdlcservice", cwd="/workspace/deployment", timeout_sec=7800)
        if result.return_code:
            await self.stop_services()
            (stage_dir / "deployment-error.txt").write_text((result.stderr or "") + (result.stdout or ""))
            await self.collect_service_logs(stage_dir)
            raise RuntimeError("Local deployment failed readiness; inspect service logs in /workspace/deployment/.runtime-logs")
        await self.environment.download_file(evidence_file, stage_dir / "deployment-evidence.json")
        evidence = json.loads((stage_dir / "deployment-evidence.json").read_text())
        evidence.update(binding)
        (stage_dir / "deployment-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        self.deployment_evidence = evidence
        await self.collect_service_logs(stage_dir)
        return evidence

    async def collect_service_logs(self, destination):
        script = ("import pathlib,stat; p=pathlib.Path('/workspace/deployment/.runtime-logs'); "
                  "assert not p.is_symlink(); "
                  "assert not p.exists() or (p.is_dir() and all(not x.is_symlink() and stat.S_ISREG(x.stat().st_mode) for x in p.iterdir())); "
                  "print('present' if p.exists() else 'absent')")
        result = await self.root("python3 -c " + shlex.quote(script))
        if result.stdout.strip() == "present":
            await self.environment.download_dir("/workspace/deployment/.runtime-logs", destination / "service-logs")

    async def execute(self, stage, prompt, instruction, resume_session, stage_dir):
        self.agent.prompt_text = prompt
        request_path = stage_dir / "app-request.json"
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
        await self.environment.download_file("/logs/agent/codex.txt", stage_dir / "codex.jsonl")
        await self.environment.download_dir("/logs/agent/sessions", stage_dir / "sessions")
        ids = []
        for line in (stage_dir / "codex.jsonl").read_text().splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "thread.started":
                ids.append(event["thread_id"])
        if len(set(ids)) != 1:
            raise RuntimeError("Expected exactly one principal thread.started event")
        evidence = native_role_evidence(stage_dir / "sessions", ids[0], stage["role"],
                                        stage["stage_id"] if "SDLC_STAGE_ID:" in prompt else None)
        (stage_dir / "native-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
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
        if not stage.get("write_repos"):
            actual = (await self.repository_inventory())["sha256"]
            if actual != self.repository_digest:
                raise RuntimeError("Read-only candidate repositories changed outside development")
        out = stage["writable_directory"]
        # Check before tar transfer; following a link could pull a credential or
        # unrelated file into the host artifact store.
        script = "import os,pathlib,stat; p=pathlib.Path(" + repr(out) + "); "
        script += "assert p.is_dir() and not p.is_symlink(); "
        script += "assert all(not x.is_symlink() and (x.is_dir() or stat.S_ISREG(x.stat().st_mode)) for x in p.rglob('*'))"
        await self.root("python3 -c " + shlex.quote(script))
        await self.environment.download_dir(out, destination)

    async def verify_baseline(self, artifacts):
        if not artifacts:
            return
        script = "import hashlib,pathlib; entries=" + repr(list(artifacts.values())) + "\n"
        script += ("for entry in entries:\n"
                   " p=pathlib.Path(entry['path'])\n"
                   " if p.is_relative_to('/workspace/artifacts'):\n"
                   "  assert pathlib.Path('/workspace/artifacts').resolve()==pathlib.Path('/logs/artifacts'), 'Artifact root redirected'\n"
                   "  p=pathlib.Path('/logs/artifacts')/p.relative_to('/workspace/artifacts')\n"
                   " assert not any(x.is_symlink() for x in [p,*p.parents]), 'Baseline path replaced'\n"
                   " assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==entry['sha256'], 'Baseline content changed'\n")
        await self.root("python3 -c " + shlex.quote(script))

    async def seal(self, stage, hashes):
        out = stage["writable_directory"]
        await self.root(f"chown -R root:root {shlex.quote(out)} && chmod -R a-w {shlex.quote(out)}")
        self.sealed_hashes.update({out + "/" + rel: value for rel, value in hashes.items()})
        script = "import hashlib,pathlib; expected=" + repr(self.sealed_hashes) + "; "
        script += "assert all(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h for p,h in expected.items())"
        await self.root("python3 -c " + shlex.quote(script))
        if stage.get("write_repos"):
            await self.root("chown -R root:root /workspace/repos; chmod -R a-w /workspace/repos")


class WorkflowCodex(BaseAgent):
    SUPPORTS_ATIF = True

    def __init__(self, *args, prepared_path, smoke=False, smoke_scenario="repair", role_probe=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.prepared = Path(prepared_path)
        self.compiled = json.loads((self.prepared / "resolved-workflow.json").read_text())
        self.smoke = smoke
        self.smoke_scenario = smoke_scenario
        self.role_probe = role_probe
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

    def populate_context_post_run(self, context):
        # Harbor invokes this after syncing logs, including on failed runs.
        if self.smoke:
            return
        try:
            trajectory = export_trajectory(self.logs_dir, self.model_name)
        except Exception:
            self.logger.exception("Failed to export workflow trajectory for Harbor Viewer")
            return
        if trajectory and trajectory.final_metrics:
            metrics = trajectory.final_metrics
            context.cost_usd = metrics.total_cost_usd
            context.n_input_tokens = metrics.total_prompt_tokens or 0
            context.n_cache_tokens = metrics.total_cached_tokens or 0
            context.n_output_tokens = metrics.total_completion_tokens or 0

    async def setup(self, environment):
        await self.delegate.setup(environment)
        await self.delegate.exec_as_root(environment, "mkdir -p /opt/sdlc")
        for name in ("codex_app_turn.py", "workspace_snapshot.py", "local_deployment.py", "workspace_cleanup.py"):
            await environment.upload_file(Path(__file__).parent / name, "/opt/sdlc/" + name)
        await self.delegate.exec_as_root(environment, "chmod 555 /opt/sdlc/*.py")

    async def run(self, instruction, environment, context):
        # Sibling of /logs/agent, not inside any mounted Agent-writable log root.
        control_dir = self.logs_dir.parent / "workflow"
        backend = HarborBackend(self.delegate, environment, context, self.prepared / "workspace")
        if self.role_probe:
            control_dir.mkdir(parents=True)
            session = None
            records = []
            for index, stage in enumerate(self.compiled["stages"][:2]):
                backend.stage_index = index
                stage_dir = control_dir / stage["role"]
                stage_dir.mkdir()
                expected = stage["role"].upper() + "_READY"
                prompt = (f"SDLC_STAGE_ROLE: {stage['role']}\n"
                          f"本条 developer 指令替代之前的活动角色。你现在的角色是 {stage['role']}。"
                          f"不得调用任何工具，不读写任何文件。最终只回复 {expected}。")
                await backend.activate(stage, session)
                try:
                    actual = await backend.execute(stage, prompt, "按当前活动角色回复标识。", session, stage_dir)
                finally:
                    await backend.quiesce()
                if session and actual != session:
                    raise RuntimeError("Role probe changed native session")
                session = actual
                messages = []
                for line in (stage_dir / "codex.jsonl").read_text().splitlines():
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
            from runtime.workflow_smoke import SmokeBackend
            backend = SmokeBackend(backend, self.smoke_scenario)
        controller = Controller(self.compiled, self.prepared / "workspace", control_dir, backend)
        await controller.run()
