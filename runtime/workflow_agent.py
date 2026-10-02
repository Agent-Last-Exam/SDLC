"""Harbor adapter: controller outside the sandbox, Claude Code inside it."""
import asyncio
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil

from harbor.agents.base import BaseAgent
from runtime.agents import PromptClaudeCode
from runtime.hierarchical_controller import HierarchicalController
from runtime.workflow_controller import Controller, digest
from runtime.local_deployment import validate_manifest
from runtime.trajectory import export_trajectory


def _jsonl_rows(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue  # A killed subagent can leave an incomplete trailing row.
    return rows


def _event_text(event):
    message = event.get("message", event)
    content = message.get("content") if isinstance(message, dict) else message
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return json.dumps(content, ensure_ascii=False)


def native_role_evidence(directory, session_id, role, stage_id=None):
    activations = []
    found = False
    for path in sorted(directory.rglob("*.jsonl")):
        if "subagents" in path.parts:
            continue
        rows = _jsonl_rows(path)
        if not any(row.get("sessionId") == session_id for row in rows):
            continue
        found = True
        activations.extend(
            row for row in rows
            if row.get("type") == "user" and "SDLC_STAGE_ROLE:" in _event_text(row)
        )
    if not found:
        raise RuntimeError("Principal native session transcript is missing")
    active_text = _event_text(activations[-1]) if activations else ""
    if not re.search(r"SDLC_STAGE_ROLE: " + re.escape(role) + r"(?:\s|$)", active_text):
        raise RuntimeError("Native transcript does not contain the current stage-role activation")
    if stage_id and not re.search(r"SDLC_STAGE_ID: " + re.escape(stage_id) + r"(?:\s|$)", active_text):
        raise RuntimeError("Native transcript contains a stale stage activation")
    return {
        "session_id": session_id,
        "active_role": role,
        "stage_id": stage_id,
        "native_user_activation_verified": True,
        "role_activations_recorded": len(activations),
        "transport": "claude-code-jsonl",
    }


def stream_session_ids(path):
    ids = []
    for event in _jsonl_rows(path):
        value = event.get("session_id") or event.get("sessionId")
        if isinstance(value, str) and value:
            ids.append(value)
    return set(ids)


def assistant_messages(path):
    messages = []
    for event in _jsonl_rows(path):
        if event.get("type") != "assistant":
            continue
        content = event.get("message", {}).get("content", [])
        if isinstance(content, str):
            messages.append(content)
            continue
        text = "".join(
            block.get("text", "") for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
        if text:
            messages.append(text)
    return messages


def exact_resume_command(command, session_id):
    if not session_id:
        return command
    marker = "--continue "
    if marker not in command:
        raise RuntimeError("Claude Code resume command is missing its continuation flag")
    return command.replace(marker, f"--resume {shlex.quote(session_id)} ", 1)


class StageClaudeCode(PromptClaudeCode):
    allow_subagents = True
    resume_session_id = None

    async def exec_as_agent(self, environment, command, **kwargs):
        user = environment.default_user
        if isinstance(user, str) and user.startswith("stage"):
            kwargs["env"] = {**kwargs.get("env", {}), "HOME": "/home/" + user}
        if self.resume_session_id and "claude --verbose --output-format=stream-json" in command:
            command = exact_resume_command(command, self.resume_session_id)
        return await super().exec_as_agent(environment, command, **kwargs)


class TeamClaudeCode(StageClaudeCode):
    """Claude adapter pinned to one Linux identity; safe under member concurrency."""

    execution_user = None
    execution_tmpdir = None

    async def exec_as_agent(self, environment, command, **kwargs):
        if not self.execution_user:
            raise RuntimeError("Team Claude execution identity is not configured")
        kwargs["env"] = {
            **kwargs.get("env", {}),
            "HOME": "/home/" + self.execution_user,
            **({"TMPDIR": self.execution_tmpdir} if self.execution_tmpdir else {}),
        }
        if self.resume_session_id and "claude --verbose --output-format=stream-json" in command:
            command = exact_resume_command(command, self.resume_session_id)
        return await self._exec(
            environment, command, user=self.execution_user, **kwargs
        )


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
            "rm -rf /workspace/scratch /tmp/claude-home /tmp/claude-secrets; "
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
        # Prove the actual execution identity cannot mutate workflow inputs or an
        # accepted stage. The subprocess runs as exactly the upcoming Agent UID.
        targets = ["/workspace/instruction.md", "/workspace/base-revisions.json",
                   "/workspace/roles", "/workspace/templates", "/workspace/repos"]
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
        activation = (
            f"SDLC_STAGE_ROLE: {stage['role']}\n"
            f"SDLC_STAGE_ID: {stage['stage_id']}\n\n"
            + instruction
        )
        self.agent.resume_session_id = resume_session
        self.agent._resume = bool(resume_session)
        try:
            await self.agent.run(activation, self.environment, self.context)
        finally:
            self.agent._resume = False
            self.agent.resume_session_id = None
            # Freeze the Stage before reading its logs. Controller.quiesce is an
            # exception-path fallback and becomes a no-op after this succeeds.
            await self.quiesce()
        stream = stage_dir / "claude-code.jsonl"
        await self.environment.download_file("/logs/agent/claude-code.txt", stream)
        await self.environment.download_dir("/logs/agent/sessions", stage_dir / "sessions")
        ids = stream_session_ids(stream)
        if len(ids) != 1:
            raise RuntimeError("Expected exactly one principal Claude Code session ID in the stage log")
        session_id = ids.pop()
        if resume_session is not None and session_id != resume_session:
            raise RuntimeError(
                f"Claude Code resumed the wrong session: {resume_session} -> {session_id}"
            )
        evidence = native_role_evidence(
            stage_dir / "sessions", session_id, stage["role"], stage["stage_id"]
        )
        evidence.update(
            role_prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            session_continuity_verified=resume_session in (None, session_id),
            system_prompt_transport="--append-system-prompt",
        )
        (stage_dir / "native-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        return session_id

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
            self.uid = None

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


class TeamHarborBackend:
    """Harbor transport for a persistent Lead and isolated persistent members."""

    synthetic = False

    def __init__(self, owner, environment, context, workspace, control_dir):
        self.owner = owner
        self.environment = environment
        self.context = context
        self.workspace = Path(workspace)
        self.control_dir = Path(control_dir)
        self.agents = {}
        self.users = {}
        self.uids = {}
        self._member_sequence = 0
        self._root_lock = asyncio.Lock()
        self._identity_lock = asyncio.Lock()
        self._service_lock = asyncio.Lock()
        self.revision_tasks = {}
        self.service_backend = HarborBackend(
            owner.delegate, environment, context, workspace
        )

    async def root(self, command):
        async with self._root_lock:
            result = await self.environment.exec(
                "set -e; " + command, user="root", cwd="/workspace"
            )
        if result.return_code:
            raise RuntimeError(
                f"Team sandbox operation failed: {result.stderr or result.stdout}"
            )
        return result

    def _agent(self, identity, remote_logs):
        if identity in self.agents:
            return self.agents[identity]
        host_logs = self.owner.logs_dir / "team" / identity
        host_logs.mkdir(parents=True, exist_ok=True)
        agent = TeamClaudeCode(
            logs_dir=host_logs,
            environment_logs_dir=PurePosixPath(remote_logs),
            model_name=self.owner.model_name,
            logger=self.owner.logger,
            system_prompt_path=self.workspace / "roles/workflow.system.md",
            version="2.1.273",
            reasoning_effort="high",
            disable_web_search=True,
            disallowed_tools=(
                "Agent,Task,Write,Edit,NotebookEdit" if identity == "lead"
                else "Agent,Task"
            ),
            extra_env=self.owner._extra_env,
        )
        agent.allow_subagents = False
        agent.execution_user = self.users[identity]
        self.agents[identity] = agent
        return agent

    async def _create_identity(self, identity, uid, remote_logs):
        async with self._identity_lock:
            if identity in self.users:
                return
            user = "team" + str(uid)
            self.users[identity] = user
            self.uids[identity] = uid
            await self.root(
                f"id {shlex.quote(user)} >/dev/null 2>&1 || "
                f"useradd -m -u {uid} -s /bin/bash {shlex.quote(user)}; "
                f"chmod 700 /home/{shlex.quote(user)}; "
                f"mkdir -p /home/{shlex.quote(user)}/tmp; "
                f"chown {uid}:{uid} /home/{shlex.quote(user)}/tmp; "
                f"chmod 700 /home/{shlex.quote(user)}/tmp; "
                f"mkdir -p {shlex.quote(remote_logs)}; "
                f"chown -R {uid}:{uid} {shlex.quote(remote_logs)}; "
                f"chmod 700 {shlex.quote(remote_logs)}"
            )
            self._agent(identity, remote_logs)

    async def start(self):
        await self.root(
            "rm -rf /workspace/team /logs/agent/team; "
            "mkdir -p /workspace/team/assignments /workspace/team/revisions "
            "/logs/agent/team/members; "
            "cp -a /workspace/repos /workspace/team/base-repos; "
            "chown -R root:root /workspace/team /workspace/repos; "
            "chmod -R a-w /workspace/team/base-repos /workspace/repos; chmod 755 /workspace/team "
            "/workspace/team/assignments /workspace/team/revisions"
        )
        inventory = await self.service_backend.repository_inventory()
        self.service_backend.repository_digest = inventory["sha256"]
        await self._create_identity("lead", 2101, "/logs/agent/team/lead")

    async def _execute(self, identity, prompt, instruction, resume_session, destination, role):
        agent = self.agents[identity]
        agent.prompt_text = prompt
        agent.resume_session_id = resume_session
        agent._resume = bool(resume_session)
        try:
            await agent.run(instruction, self.environment, self.context)
        finally:
            agent._resume = False
            agent.resume_session_id = None
        stream_remote = (agent.environment_logs_dir / "claude-code.txt").as_posix()
        sessions_remote = (agent.environment_logs_dir / "sessions").as_posix()
        stream = destination / "claude-code.jsonl"
        await self.environment.download_file(stream_remote, stream)
        await self.environment.download_dir(sessions_remote, destination / "sessions")
        ids = stream_session_ids(stream)
        if len(ids) != 1:
            raise RuntimeError(f"Expected exactly one Claude session for team {identity}")
        session_id = ids.pop()
        if resume_session is not None and session_id != resume_session:
            raise RuntimeError(
                f"Team session resumed incorrectly: {resume_session} -> {session_id}"
            )
        messages = assistant_messages(stream)
        if not messages:
            raise RuntimeError(f"Team {identity} returned no assistant message")
        evidence = {
            "identity": identity,
            "role": role,
            "session_id": session_id,
            "resume_session_id": resume_session,
            "session_continuity_verified": resume_session in (None, session_id),
            "role_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "transport": "claude-code-jsonl",
            "recursive_recruitment_disabled": True,
        }
        (destination / "native-evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )
        return session_id, messages[-1]

    async def execute_lead(self, prompt, instruction, resume_session, turn_dir):
        self.agents["lead"].execution_tmpdir = "/home/" + self.users["lead"] + "/tmp"
        try:
            return await self._execute(
                "lead", prompt, instruction, resume_session, turn_dir, "lead"
            )
        finally:
            await self._quiesce_identity("lead")

    async def prepare_assignment(self, member, task):
        identity = "member-" + member["id"]
        if identity not in self.users:
            # No await between allocation steps: distinct concurrently scheduled
            # members receive distinct UIDs before _create_identity serializes OS changes.
            self._member_sequence += 1
            uid = 2200 + self._member_sequence
            await self._create_identity(
                identity, uid, f"/logs/agent/team/members/{member['id']}"
            )
        uid = self.uids[identity]
        if member["role"] in {"developer", "deployer"}:
            async with self._service_lock:
                await self.service_backend.stop_services()
        if member["role"] == "qa" and self.service_backend.deployment_evidence is None:
            raise RuntimeError("QA requires a currently live, health-checked deployment")
        root = self.assignment_path(task["id"])
        await self.root(
            f"test ! -e {shlex.quote(root)}; "
            f"mkdir -p {shlex.quote(root + '/artifacts')} "
            f"{shlex.quote(root + '/metadata')} {shlex.quote(root + '/scratch')}; "
            f"chown -R root:root {shlex.quote(root)}; chmod -R a-w {shlex.quote(root)}"
        )
        await self.root(
            f"chown -R {uid}:{uid} {shlex.quote(root + '/scratch')}; "
            f"chmod -R u+rwX {shlex.quote(root + '/scratch')}"
        )
        if any(scope.startswith("repos/") for scope in task["write_scope"]):
            await self.root(
                f"mkdir -p {shlex.quote(root + '/repos')}; "
                f"cp -a /workspace/repos/. {shlex.quote(root + '/repos/')}; "
                f"python3 /opt/sdlc/team_workspace.py snapshot-repos {shlex.quote(root + '/repos')} "
                f"> {shlex.quote(root + '/metadata/repos-before.json')}; "
                f"chown -R root:root {shlex.quote(root + '/repos')}; "
                f"chmod -R a-w,a+rX {shlex.quote(root + '/repos')}"
            )
        outputs = {
            str(PurePosixPath(path).relative_to("/workspace"))
            for path in self._stage(task)["outputs"].values()
            if path
        }
        for scope in task["write_scope"]:
            target = root + "/" + scope
            if scope in outputs or scope.startswith("repos/") and await self._is_file(target):
                await self.root(
                    f"mkdir -p {shlex.quote(str(PurePosixPath(target).parent))}; "
                    f"test -e {shlex.quote(target)} || touch {shlex.quote(target)}; "
                    f"chown {uid}:{uid} {shlex.quote(target)}; chmod u+rw {shlex.quote(target)}"
                )
            else:
                await self.root(
                    f"mkdir -p {shlex.quote(target)}; chown -R {uid}:{uid} {shlex.quote(target)}; "
                    f"chmod -R u+rwX {shlex.quote(target)}"
                )
        await self.root(
            f"python3 /opt/sdlc/team_workspace.py snapshot {shlex.quote(root + '/artifacts')} "
            f"> {shlex.quote(root + '/metadata/artifacts-before.json')}; "
            f"chown -R root:root {shlex.quote(root + '/metadata')}; "
            f"chmod -R a-w {shlex.quote(root + '/metadata')}"
        )

    async def _is_file(self, remote):
        result = await self.environment.exec(
            "test -f " + shlex.quote(remote), user="root", cwd="/workspace"
        )
        return result.return_code == 0

    def _stage(self, task):
        return next(
            stage for stage in self.owner.compiled["stages"]
            if stage["stage_id"] == task["stage_id"]
        )

    async def execute_assignment(
        self, member, task, prompt, instruction, resume_session, task_dir
    ):
        identity = "member-" + member["id"]
        self.agents[identity].execution_tmpdir = self.assignment_path(
            task["id"], "scratch"
        )
        return await self._execute(
            identity, prompt, instruction, resume_session, task_dir, member["role"]
        )

    async def collect_assignment(self, task, result, task_dir):
        root = self.assignment_path(task["id"])
        metadata = root + "/metadata"
        artifacts_after = metadata + "/artifacts-after.json"
        await self.root(
            f"chown -R root:root {shlex.quote(root + '/artifacts')}; "
            f"chmod -R a-w {shlex.quote(root + '/artifacts')}; "
            + (f"chown -R root:root {shlex.quote(root + '/repos')}; "
               f"chmod -R a-w {shlex.quote(root + '/repos')}; "
               if any(scope.startswith("repos/") for scope in task["write_scope"])
               else "")
            +
            f"python3 /opt/sdlc/team_workspace.py snapshot {shlex.quote(root + '/artifacts')} "
            f"> {shlex.quote(artifacts_after)}"
        )
        before = json.loads((await self.environment.exec(
            "cat " + shlex.quote(metadata + "/artifacts-before.json"), user="root"
        )).stdout)
        after = json.loads((await self.environment.exec(
            "cat " + shlex.quote(artifacts_after), user="root"
        )).stdout)
        manifest = {
            "artifacts/" + path: value
            for path, value in after.items() if before.get(path) != value
        }
        removed = {
            "artifacts/" + path: "deleted"
            for path in before if path not in after
        }
        manifest.update(removed)
        repo_changes = {}
        if any(scope.startswith("repos/") for scope in task["write_scope"]):
            changes_file = metadata + "/repos-changes.json"
            await self.root(
                f"python3 /opt/sdlc/team_workspace.py diff "
                f"{shlex.quote(metadata + '/repos-before.json')} "
                f"{shlex.quote(root + '/repos')} > {shlex.quote(changes_file)}"
            )
            repo_changes = json.loads((await self.environment.exec(
                "cat " + shlex.quote(changes_file), user="root"
            )).stdout)
            manifest.update({"repos/" + path: value for path, value in repo_changes.items()})
        routing = {}
        if task["kind"] == "work" and self._stage(task)["role"] in {"qa", "triage"}:
            routing = await self._routing(task, root)
        if task["kind"] == "work" and self._stage(task)["role"] == "deployer":
            candidate_root = task_dir / "candidate-artifacts"
            await self.environment.download_dir(root + "/artifacts", candidate_root)
            stage = self._stage(task)
            candidate = candidate_root / PurePosixPath(
                stage["writable_directory"]
            ).relative_to("/workspace/artifacts")
            evidence_dir = task_dir / "deployment"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            async with self._service_lock:
                await self.service_backend.deploy(stage, candidate, evidence_dir)
        if task["kind"] == "work" and self._stage(task)["role"] == "qa":
            async with self._service_lock:
                await self.service_backend.collect_service_logs(task_dir)
        return manifest, routing

    async def _routing(self, task, root):
        stage = self._stage(task)
        name, key = (("test-verify.json", "verdict") if stage["role"] == "qa"
                     else ("repair-plan.json", "design_changed"))
        path = next(
            str(PurePosixPath(value).relative_to("/workspace"))
            for value in stage["outputs"].values() if PurePosixPath(value).name == name
        )
        result = await self.environment.exec(
            "cat " + shlex.quote(root + "/" + path), user="root"
        )
        if result.return_code:
            raise RuntimeError(f"Cannot read routing output {name}")
        data = json.loads(result.stdout)
        value = data[key]
        valid = (isinstance(value, str) and value in {"pass", "fail"}
                 if key == "verdict" else isinstance(value, bool))
        if not valid:
            raise RuntimeError(f"Invalid routing value in {name}")
        return {key: value}

    async def seal_revision(self, task, revision, task_dir):
        root = self.assignment_path(task["id"])
        remote_revision = self.revision_path(revision["id"])
        if task["kind"] == "review":
            source = self.revision_path(task["source_revision"])
            await self.root(
                f"mkdir -p {shlex.quote(remote_revision)}; "
                f"cp -a {shlex.quote(source + '/.')} {shlex.quote(remote_revision + '/')}; "
                f"chown -R root:root {shlex.quote(remote_revision)}; "
                f"chmod -R a+rX,a-w {shlex.quote(remote_revision)}"
            )
            host_revision = self.control_dir / "revisions" / revision["id"]
            host_revision.parent.mkdir(parents=True, exist_ok=True)
            await self.environment.download_dir(remote_revision, host_revision)
            (host_revision / "revision.json").write_text(
                json.dumps(revision, ensure_ascii=False, indent=2) + "\n"
            )
            self.revision_tasks[revision["id"]] = task["id"]
            return
        await self.root(
            f"mkdir -p {shlex.quote(remote_revision)}; "
            f"cp -a {shlex.quote(root + '/artifacts')} {shlex.quote(remote_revision + '/artifacts')}; "
            f"cp -a {shlex.quote(root + '/metadata')} {shlex.quote(remote_revision + '/metadata')}; "
            + (f"cp -a {shlex.quote(root + '/repos')} {shlex.quote(remote_revision + '/repos')}; "
               if any(path.startswith("repos/") for path in revision["files"]) else "")
            + f"chown -R root:root {shlex.quote(root)} {shlex.quote(remote_revision)}; "
              f"chmod -R a+rX,a-w {shlex.quote(root)} {shlex.quote(remote_revision)}"
        )
        host_revision = self.control_dir / "revisions" / revision["id"]
        host_revision.parent.mkdir(parents=True, exist_ok=True)
        await self.environment.download_dir(remote_revision, host_revision)
        (host_revision / "revision.json").write_text(
            json.dumps(revision, ensure_ascii=False, indent=2) + "\n"
        )
        for name in ("deployment", "service-logs"):
            evidence = task_dir / name
            if evidence.is_dir():
                shutil.copytree(evidence, host_revision / name)
        self.revision_tasks[revision["id"]] = task["id"]

    async def accept_revision(self, revision, effect, directory):
        remote_revision = self.revision_path(revision["id"])
        if effect.get("repository_set_changed"):
            async with self._service_lock:
                await self.service_backend.stop_services()
            await self._sync_repositories(effect["repository_revisions"])
            inventory = await self.service_backend.repository_inventory()
            self.service_backend.repository_digest = inventory["sha256"]
        host_revision = self.control_dir / "revisions" / revision["id"] / "artifacts"
        stage = self._stage(revision)
        copied_paths = set()
        for ref in effect["output_refs"]:
            relative = revision["outputs"][ref]["path"]
            source = host_revision / PurePosixPath(relative).relative_to("artifacts")
            output_relative = PurePosixPath(stage["outputs"][ref]).relative_to(
                PurePosixPath(stage["writable_directory"])
            )
            target = self.control_dir / "accepted" / stage["stage_id"] / output_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            copied_paths.add(relative)
            remote_target = "/logs/artifacts/" + str(
                PurePosixPath(stage["outputs"][ref]).relative_to("/workspace/artifacts")
            )
            await self.root(
                f"mkdir -p {shlex.quote(str(PurePosixPath(remote_target).parent))}; "
                f"cp {shlex.quote(remote_revision + '/' + relative)} {shlex.quote(remote_target)}; "
                f"chown root:root {shlex.quote(remote_target)}; chmod a-w {shlex.quote(remote_target)}"
            )
        for relative, expected in revision["files"].items():
            if (not relative.startswith("artifacts/") or relative in copied_paths
                    or expected == "deleted"):
                continue
            source = host_revision / PurePosixPath(relative).relative_to("artifacts")
            stage_relative = PurePosixPath(relative).relative_to(
                "artifacts", *PurePosixPath(stage["stage_id"]).parts
            )
            target = self.control_dir / "accepted" / stage["stage_id"] / stage_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            remote_target = "/logs/artifacts/" + str(
                PurePosixPath(stage["stage_id"]) / stage_relative
            )
            await self.root(
                f"mkdir -p {shlex.quote(str(PurePosixPath(remote_target).parent))}; "
                f"cp {shlex.quote(remote_revision + '/' + relative)} {shlex.quote(remote_target)}; "
                f"chown root:root {shlex.quote(remote_target)}; chmod a-w {shlex.quote(remote_target)}"
            )

    async def _sync_repositories(self, revision_ids):
        command = (
            "rm -rf /workspace/team/repos-next; "
            "cp -a /workspace/team/base-repos /workspace/team/repos-next; "
            "chmod -R u+w /workspace/team/repos-next; "
        )
        for revision_id in revision_ids:
            remote = self.revision_path(revision_id)
            command += (
                f"python3 /opt/sdlc/team_workspace.py integrate "
                f"/workspace/team/repos-next {shlex.quote(remote + '/repos')} "
                f"{shlex.quote(remote + '/metadata/repos-before.json')} "
                f"{shlex.quote(remote + '/metadata/repos-changes.json')}; "
            )
        command += (
            "rm -rf /workspace/team/repos-old; "
            "mv /workspace/repos /workspace/team/repos-old; "
            "mv /workspace/team/repos-next /workspace/repos; "
            "rm -rf /workspace/team/repos-old; "
            "chown -R root:root /workspace/repos; chmod -R a-w /workspace/repos"
        )
        await self.root(command)

    async def quiesce_member(self, member_id):
        await self._quiesce_identity("member-" + member_id)

    async def _quiesce_identity(self, identity):
        uid = self.uids.get(identity)
        if uid is not None:
            await self.root(f"pkill -KILL -u {uid} || test $? -eq 1")

    async def stop_all(self):
        for identity, uid in list(self.uids.items()):
            await self.root(f"pkill -KILL -u {uid} || test $? -eq 1")
        async with self._service_lock:
            await self.service_backend.stop_services()

    def assignment_path(self, task_id, relative=None):
        base = f"/workspace/team/assignments/{task_id}"
        return base + ("/" + relative if relative else "")

    def revision_path(self, revision_id):
        return f"/workspace/team/revisions/{revision_id}"

    def revision_input_path(self, revision_id, ref):
        revision = json.loads(
            (self.control_dir / "revisions" / revision_id / "revision.json").read_text()
        )
        return self.revision_path(revision_id) + "/" + revision["outputs"][ref]["path"]


class WorkflowClaudeCode(BaseAgent):
    SUPPORTS_ATIF = True

    def __init__(self, *args, prepared_path, smoke=False, smoke_scenario="repair", role_probe=False,
                 stop_after_stage=None, missing_output_policy="fail", **kwargs):
        super().__init__(*args, **kwargs)
        self.prepared = Path(prepared_path)
        self.compiled = json.loads((self.prepared / "resolved-workflow.json").read_text())
        self.smoke = smoke
        self.smoke_scenario = smoke_scenario
        self.role_probe = role_probe
        self.stop_after_stage = stop_after_stage
        self.missing_output_policy = missing_output_policy
        self.delegate = StageClaudeCode(
            logs_dir=self.logs_dir, model_name=self.model_name, logger=self.logger,
            system_prompt_path=self.prepared / "workspace/roles/workflow.system.md",
            version="2.1.273", reasoning_effort="high", disable_web_search=True,
            extra_env=self._extra_env,
        )
        self.delegate.allow_subagents = self.compiled["run"]["execution"].get("subagents", {}).get("enabled", False)

    @staticmethod
    def name():
        return "sdlc-workflow-claude-code"

    def version(self):
        return "2.1.273"

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
        for name in (
            "workspace_snapshot.py", "local_deployment.py", "workspace_cleanup.py",
            "team_workspace.py",
        ):
            await environment.upload_file(Path(__file__).parent / name, "/opt/sdlc/" + name)
        await self.delegate.exec_as_root(environment, "chmod 555 /opt/sdlc/*.py")
        # Prebuilt benchmark images keep the two frozen repositories directly
        # below /workspace. Native Kubernetes Jobs upload the public workflow
        # envelope after the image starts, so materialize clean, .git-free Base
        # trees at the workflow contract paths when they are not already there.
        materialize = r'''set -eu
mkdir -p /workspace/repos
for name in saleor saleor-dashboard; do
  if [ -d "/workspace/repos/$name" ]; then
    continue
  fi
  expected="$(python3 -c 'import json,sys; v=json.load(open("/workspace/base-revisions.json"))[sys.argv[1]]; print(v if isinstance(v,str) else v["commit"])' "$name")"
  test "$(git -C "/workspace/$name" rev-parse HEAD)" = "$expected"
  mkdir -p "/workspace/repos/$name"
  git -C "/workspace/$name" archive "$expected" | tar -xf - -C "/workspace/repos/$name"
done'''
        result = await environment.exec(materialize, user="root", cwd="/workspace")
        if result.return_code:
            raise RuntimeError("Could not materialize frozen workflow Base repositories")

    async def run(self, instruction, environment, context):
        # Sibling of /logs/agent, not inside any mounted Agent-writable log root.
        control_dir = self.logs_dir.parent / "workflow"
        backend = HarborBackend(self.delegate, environment, context, self.prepared / "workspace")
        if self.role_probe:
            control_dir.mkdir(parents=True)
            session = None
            flat = self.compiled["mode"] == "flat"
            seen_sessions = set()
            records = []
            for index, stage in enumerate(self.compiled["stages"][:2]):
                backend.stage_index = index
                stage_dir = control_dir / "stages" / stage["stage_id"]
                stage_dir.mkdir(parents=True)
                expected = stage["role"].upper() + "_READY"
                prompt = (f"SDLC_STAGE_ROLE: {stage['role']}\n"
                          f"本条阶段指令替代之前的活动角色。你现在的角色是 {stage['role']}。"
                          f"不得调用任何工具，不读写任何文件。最终只回复 {expected}。")
                resume_session = None if flat else session
                await backend.activate(stage, resume_session)
                try:
                    actual = await backend.execute(
                        stage, prompt, "按当前活动角色回复标识。", resume_session, stage_dir
                    )
                finally:
                    await backend.quiesce()
                if flat:
                    if actual in seen_sessions:
                        raise RuntimeError("Flat role probe reused a native session")
                    seen_sessions.add(actual)
                elif session and actual != session:
                    raise RuntimeError("Single role probe changed native session")
                session = actual
                messages = []
                messages = assistant_messages(stage_dir / "claude-code.jsonl")
                if not messages or messages[-1].strip() != expected:
                    raise RuntimeError(f"Role probe response mismatch: {messages}")
                records.append({"role": stage["role"], "session_id": session, "response": expected})
            state = {
                "status": "complete", "mode": self.compiled["mode"],
                "role_probe": True, "records": records,
            }
            if flat:
                state["principal_sessions"] = [
                    {"stage_id": stage["stage_id"], "role": stage["role"],
                     "session_id": record["session_id"]}
                    for stage, record in zip(self.compiled["stages"][:2], records)
                ]
            else:
                state["principal_session"] = session
            (control_dir / "state.json").write_text(json.dumps(state, indent=2))
            return
        if self.smoke:
            from runtime.workflow_smoke import SmokeBackend
            backend = SmokeBackend(backend, self.smoke_scenario)
        if self.compiled["mode"] == "hierarchical":
            if self.smoke or self.role_probe:
                raise ValueError("Hierarchical mode does not support fixed-stage smoke or role probes")
            team_backend = TeamHarborBackend(
                self, environment, context, self.prepared / "workspace", control_dir
            )
            controller = HierarchicalController(
                self.compiled, self.prepared / "workspace", control_dir, team_backend
            )
            await controller.run()
            return
        controller = Controller(self.compiled, self.prepared / "workspace", control_dir, backend,
                                stop_after_stage=self.stop_after_stage,
                                missing_output_policy=self.missing_output_policy)
        await controller.run()
