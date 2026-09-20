import json
from pathlib import Path
import shutil
import tempfile
import unittest

from runtime.prepare_workflow import HERE, compile_workflow
from runtime.workflow_controller import Controller
from runtime.workflow_gates import GateError, validate_prd, validate_design, validate_stage, blocks, field
from runtime.workflow_smoke import write_fixture
from runtime.workflow_agent import native_role_evidence
from runtime.codex_app_turn import app_server_command


class FakeBackend:
    synthetic = True

    def __init__(self, workspace, reject_once=False, switch_session=False, pending_design=False):
        self.workspace = workspace
        self.pending_design = pending_design
        self.reject_once, self.switch_session = reject_once, switch_session
        self.calls = []
        self.stage_index = 0

    async def activate(self, stage, attempt, session):
        self.attempt = attempt

    async def execute(self, stage, prompt, instruction, session, attempt_dir):
        self.calls.append((stage["role"], session, prompt))
        self.candidate = attempt_dir / "fixture"
        write_fixture(self.candidate, stage["role"], self.workspace)
        if self.pending_design and stage["role"] == "architect":
            p = self.candidate / "backend-design.md"
            p.write_text(p.read_text().replace("无业务有效性声明。", "待确认：退款权益尚需产品决定；身份 token 清单未提供。"))
        if self.reject_once and stage["role"] == "pm" and self.attempt == 1:
            p = self.candidate / "prd.md"
            p.write_text(p.read_text().replace("优先级：P0", "优先级：关键"))
        return "changed" if session and self.switch_session else session or f"thread-{self.stage_index}"

    async def quiesce(self):
        pass

    async def collect(self, stage, destination):
        shutil.copytree(self.candidate, destination)

    async def seal(self, stage, hashes):
        pass


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def test_graphql_comments_inside_fences_are_not_markdown_boundaries(self):
        for fence in ("```", "~~~~"):
            text = f"### I01 · 接口\n- 目标定义：\n{fence}graphql\n# comment\n## nested comment\n### I99 · fake\ntype Query {{ shop: String }}\n{fence}\n- 字段说明：保留旧字段。\n## 3. 其他\n"
            parsed = blocks(text, "I")
            self.assertEqual(list(parsed), ["I01"])
            self.assertEqual(field(parsed["I01"], "字段说明"), "保留旧字段。")
            self.assertIn("# comment", parsed["I01"])
            self.assertNotIn("## 3. 其他", parsed["I01"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        shutil.copytree(HERE / "tasks/saleor-prd-tdd/templates", self.workspace / "templates")
        (self.workspace / "roles").mkdir()
        for role in ("pm", "architect"):
            shutil.copyfile(HERE / f"tasks/saleor-prd-tdd/roles/{role}.system.md", self.workspace / f"roles/{role}.system.md")
        schema = self.workspace / "repos/saleor/saleor/graphql/schema.graphql"
        schema.parent.mkdir(parents=True)
        schema.write_text("type Query { shop: Shop! }\ntype Shop { name: String! }\n")
        self.config = compile_workflow(HERE / "tasks/saleor-prd-tdd/workflows/single.yaml", verify_repos=False)

    async def run_controller(self, backend):
        controller = Controller(self.config, self.workspace, self.root / "control", backend)
        return await controller.run()

    async def test_single_keeps_session_and_changes_role(self):
        backend = FakeBackend(self.workspace)
        state = await self.run_controller(backend)
        self.assertEqual(state["status"], "complete")
        self.assertEqual([c[0] for c in backend.calls], ["pm", "architect"])
        self.assertIsNone(backend.calls[0][1])
        self.assertEqual(backend.calls[1][1], "thread-0")
        self.assertIn("SDLC_STAGE_ROLE: architect", backend.calls[1][2])
        for call, stage in zip(backend.calls, self.config["stages"]):
            for path in (*stage["inputs"].values(), *stage["outputs"].values()):
                self.assertIn(f"`{path}`", call[2])
            for internal_detail in ("base-revisions.json", "Controller", "封存", '"stage_id"'):
                self.assertNotIn(internal_detail, call[2])
        self.assertNotIn("Architect", backend.calls[0][2])
        self.assertNotIn("架构师", backend.calls[0][2])
        first, second = state["stages"]
        self.assertEqual(first["outputs"]["prd.md"], second["attempts"][0]["prd_input_sha256"])

    async def test_flat_does_not_resume(self):
        self.config["mode"] = "flat"
        backend = FakeBackend(self.workspace)
        await self.run_controller(backend)
        self.assertEqual([c[1] for c in backend.calls], [None, None])

    async def test_rejected_submission_only_retries_current_stage(self):
        backend = FakeBackend(self.workspace, reject_once=True)
        state = await self.run_controller(backend)
        self.assertEqual([c[0] for c in backend.calls], ["pm", "pm", "architect"])
        self.assertEqual(state["stages"][0]["attempts"][0]["status"], "rejected")
        self.assertEqual(state["status"], "complete")

    async def test_design_delivery_completes_with_pending_items_without_self_review(self):
        backend = FakeBackend(self.workspace, pending_design=True)
        state = await self.run_controller(backend)
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["cursor"], 2)
        self.assertEqual(len(backend.calls), 2)
        accepted = self.root / "control/accepted/sprint1/tech-design"
        self.assertEqual({p.name for p in accepted.iterdir()}, {
            "frontend-design.md", "backend-design.md", "interface-contract.md", "target-schema.graphql"})
        self.assertIn("待确认：退款权益", (accepted / "backend-design.md").read_text())
        self.assertNotIn("review_outcome", state["stages"][1]["attempts"][0]["gate"])

    async def test_session_change_fails_instead_of_silent_flat(self):
        backend = FakeBackend(self.workspace, switch_session=True)
        with self.assertRaisesRegex(RuntimeError, "session changed"):
            await self.run_controller(backend)
        state = json.loads((self.root / "control/state.json").read_text())
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["cursor"], 1)

    async def test_existing_state_cannot_be_replayed(self):
        await self.run_controller(FakeBackend(self.workspace))
        with self.assertRaisesRegex(ValueError, "replay"):
            Controller(self.config, self.workspace, self.root / "control", FakeBackend(self.workspace))

    async def test_recovery_continues_after_accepted_prd_on_same_session(self):
        with self.assertRaises(RuntimeError):
            await self.run_controller(FakeBackend(self.workspace, switch_session=True))
        backend = FakeBackend(self.workspace)
        recovered = Controller(self.config, self.workspace, self.root / "continued", backend,
                               recovery=self.root / "control")
        state = await recovered.run()
        self.assertEqual(state["status"], "complete")
        self.assertEqual([c[0] for c in backend.calls], ["architect"])
        self.assertEqual(backend.calls[0][1], "thread-0")
        self.assertEqual(state["stages"][0]["outputs"]["prd.md"],
                         state["stages"][1]["attempts"][0]["prd_input_sha256"])

    async def test_recovery_rejects_modified_accepted_prd(self):
        with self.assertRaises(RuntimeError):
            await self.run_controller(FakeBackend(self.workspace, switch_session=True))
        p = self.root / "control/accepted/sprint1/prd/prd.md"
        p.write_text(p.read_text() + "\nchanged\n")
        with self.assertRaisesRegex(ValueError, "hash changed"):
            Controller(self.config, self.workspace, self.root / "continued", FakeBackend(self.workspace),
                       recovery=self.root / "control")

    async def test_hierarchical_is_not_silently_replaced(self):
        self.config["mode"] = "hierarchical"
        with self.assertRaisesRegex(ValueError, "Hierarchical"):
            Controller(self.config, self.workspace, self.root / "control", FakeBackend(self.workspace))

    def test_invalid_acceptance_requirement_link(self):
        d = self.root / "prd"
        write_fixture(d, "pm", self.workspace)
        p = d / "prd.md"
        p.write_text(p.read_text().replace("AC-01-1", "AC-02-1"))
        with self.assertRaisesRegex(GateError, "wrong requirement"):
            validate_prd(d, self.workspace / "templates")

    def test_narrative_description_can_span_multiple_lines(self):
        d = self.root / "prd"
        write_fixture(d, "pm", self.workspace)
        p = d / "prd.md"
        p.write_text(p.read_text().replace("需求描述：验证阶段交接。", "需求描述：\n  验证阶段交接。\n  保留长文本段落。"))
        self.assertEqual(validate_prd(d, self.workspace / "templates")["requirements"], ["R01"])

    def test_undeclared_notes_cannot_become_flat_handoff(self):
        d = self.root / "prd"
        write_fixture(d, "pm", self.workspace)
        (d / "private-notes.md").write_text("not a declared artifact")
        with self.assertRaisesRegex(GateError, "Undeclared output"):
            validate_stage(self.config["stages"][0], d, self.workspace)

    def design(self):
        prd, design = self.root / "prd", self.root / "design"
        write_fixture(prd, "pm", self.workspace)
        write_fixture(design, "architect", self.workspace)
        return prd, design

    def validate(self, prd, design):
        return validate_design(design, self.workspace / "templates", prd / "prd.md",
                               self.workspace / "repos/saleor/saleor/graphql/schema.graphql")

    def test_dangling_interface_is_rejected(self):
        prd, design = self.design()
        p = design / "frontend-design.md"
        p.write_text(p.read_text().replace("I01", "I99"))
        with self.assertRaisesRegex(GateError, "Dangling I"):
            self.validate(prd, design)

    def test_dependency_cycle_is_rejected(self):
        prd, design = self.design()
        p = design / "backend-design.md"
        p.write_text(p.read_text().replace("依赖：无", "依赖：BT01"))
        with self.assertRaisesRegex(GateError, "cycle"):
            self.validate(prd, design)

    def test_schema_fragment_is_rejected(self):
        prd, design = self.design()
        (design / "target-schema.graphql").write_text("type Query { status: String }\n")
        with self.assertRaisesRegex(GateError, "fragment"):
            self.validate(prd, design)

    def test_native_evidence_requires_latest_role_on_same_session(self):
        sessions = self.root / "sessions"
        sessions.mkdir()
        rows = [
            {"type": "session_meta", "payload": {"id": "primary"}},
            {"type": "response_item", "payload": {"role": "developer", "content": "SDLC_STAGE_ROLE: pm"}},
            {"type": "response_item", "payload": {"role": "developer", "content": "SDLC_STAGE_ROLE: architect"}},
        ]
        (sessions / "primary.jsonl").write_text("\n".join(json.dumps(x) for x in rows))
        evidence = native_role_evidence(sessions, "primary", "architect")
        self.assertEqual(evidence["role_activations_recorded"], 2)
        with self.assertRaisesRegex(RuntimeError, "current developer-role"):
            native_role_evidence(sessions, "primary", "pm")
        with self.assertRaisesRegex(RuntimeError, "missing"):
            native_role_evidence(sessions, "other", "architect")

    def test_native_subagent_flag_matches_execution_policy(self):
        self.assertIn("features.multi_agent=false", app_server_command(False))
        self.assertIn("features.multi_agent=true", app_server_command(True))

    def test_partial_child_log_does_not_hide_principal_evidence(self):
        d = self.root / "sessions"
        d.mkdir()
        (d / "child.jsonl").write_text(json.dumps({"type": "session_meta", "payload": {"id": "child"}}) + '\n{"partial":')
        rows = [{"type": "session_meta", "payload": {"id": "primary"}},
                {"type": "response_item", "payload": {"role": "developer", "content": "SDLC_STAGE_ROLE: architect"}}]
        (d / "primary.jsonl").write_text("\n".join(json.dumps(x) for x in rows))
        self.assertTrue(native_role_evidence(d, "primary", "architect")["native_developer_message_verified"])


if __name__ == "__main__":
    unittest.main()
