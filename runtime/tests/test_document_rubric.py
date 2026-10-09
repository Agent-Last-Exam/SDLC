"""Document-rubric contracts and scoring; no model, Harbor, Docker, or network."""

import json
import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from io import BytesIO

from runtime.document_rubric import (
    Manifest,
    aggregate,
    apply_delivery_gate,
    disagreements,
    judgment_schema,
    rewardkit_details,
    validate_judgment,
)
from runtime.document_rubric_verifier import (
    DocumentEvaluationError,
    DocumentRubricVerifier,
    REMOTE_DIRECT_RUNNER,
)
from runtime.document_direct_judge_runner import (
    api_model,
    chat_completions_url,
    load_credentials,
    load_prompt,
    parse_judgment,
    read_response,
    request_payload,
)


def manifest_value():
    return {
        "schema_version": 1,
        "rubric_set_id": "saleor-docs",
        "rubric_version": "v1",
        "source_revisions": {"rubric": "161", "plan": "266"},
        "aggregation": "min_group_pass_rate",
        "judge_replicas": 1,
        "groups": [
            {
                "group_id": "prd",
                "title": "PRD",
                "stage": "sprint1/prd",
                "evidence": [{"root": "candidate", "path": "sprint1/prd/prd.md", "purpose": "candidate"}],
                "rubrics": [
                    {"rubric_id": "P1", "title": "Scope", "criteria": "Scope is explicit", "critical": True},
                    {"rubric_id": "P2", "title": "Acceptance", "criteria": "Acceptance is observable"},
                ],
            },
            {
                "group_id": "tech_design",
                "title": "Tech Design",
                "stage": "sprint1/tech-design",
                "evidence": [{"root": "candidate", "path": "sprint1/tech-design", "purpose": "candidate"}],
                "rubrics": [
                    {"rubric_id": "T1", "title": "Contract", "criteria": "Contract is consistent", "weight": 2},
                ],
            },
        ],
    }


def result(group_id, rows):
    return {"group_id": group_id, "results": [
        {"rubric_id": rubric_id, "verdict": verdict,
         "evidence": [{"path": "candidate.md", "location": "L1", "quote": "evidence"}],
         "reason": "supported" if verdict == "P" else "missing",
         "issue_id": None if verdict == "P" else "ISSUE-1"}
        for rubric_id, verdict in rows
    ]}


class DocumentRubricTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "manifest.json"
        self.path.write_text(json.dumps(manifest_value()))

    def test_manifest_freezes_unique_groups_and_rubrics(self):
        manifest = Manifest.load(self.path)
        self.assertEqual([group.group_id for group in manifest.groups], ["prd", "tech_design"])
        value = manifest_value()
        value["groups"][1]["rubrics"][0]["rubric_id"] = "P1"
        self.path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "unique"):
            Manifest.load(self.path)

    def test_private_path_escape_is_rejected(self):
        value = manifest_value()
        value["groups"][0]["evidence"][0] = {
            "root": "private", "path": "../golden.md", "purpose": "golden"
        }
        self.path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "canonical relative path"):
            Manifest.load(self.path)

    def test_judgment_requires_fixed_denominator_and_issue_for_failure(self):
        group = Manifest.load(self.path).groups[0]
        self.assertEqual(
            judgment_schema(group)["properties"]["group_id"],
            {"type": "string", "const": "prd"},
        )
        valid = validate_judgment(group, result("prd", [("P1", "P"), ("P2", "F")]))
        self.assertEqual(len(valid["results"]), 2)
        missing = result("prd", [("P1", "P")])
        with self.assertRaisesRegex(ValueError, "frozen denominator"):
            validate_judgment(group, missing)
        bad = result("prd", [("P1", "P"), ("P2", "F")])
        bad["results"][1]["issue_id"] = None
        with self.assertRaisesRegex(ValueError, "needs an issue_id"):
            validate_judgment(group, bad)

    def test_disagreement_requires_adjudication(self):
        group = Manifest.load(self.path).groups[0]
        first = validate_judgment(group, result("prd", [("P1", "P"), ("P2", "F")]))
        second = validate_judgment(group, result("prd", [("P1", "F"), ("P2", "F")]))
        self.assertEqual(disagreements(group, [first, second]), ["P1"])

    def test_min_group_score_prevents_cross_stage_compensation(self):
        manifest = Manifest.load(self.path)
        judgments = {
            "prd": validate_judgment(manifest.groups[0], result("prd", [("P1", "P"), ("P2", "F")])),
            "tech_design": validate_judgment(
                manifest.groups[1], result("tech_design", [("T1", "P")])
            ),
        }
        rewards, report = aggregate(manifest, judgments)
        self.assertEqual(rewards["group_prd"], 0.5)
        self.assertEqual(rewards["group_tech_design"], 1.0)
        self.assertEqual(rewards["reward"], 0.5)
        self.assertEqual(rewards["document_acceptance"], 0)
        self.assertEqual(report["aggregation"], "min_group_pass_rate")
        details = rewardkit_details(report)
        self.assertEqual(details["prd"]["kind"], "document_rubric_judge")
        self.assertEqual(details["prd"]["score"], 0.5)
        self.assertEqual([row["value"] for row in details["prd"]["criteria"]], [1.0, 0.0])

    def test_missing_required_document_forces_reward_zero_without_erasing_judgments(self):
        manifest = Manifest.load(self.path)
        judgments = {
            "prd": validate_judgment(manifest.groups[0], result("prd", [("P1", "P"), ("P2", "P")])),
            "tech_design": validate_judgment(
                manifest.groups[1], result("tech_design", [("T1", "P")])
            ),
        }
        rewards, report = aggregate(manifest, judgments)
        rewards, report = apply_delivery_gate(
            rewards,
            report,
            ["sprint1/prd/prd.md", "sprint1/tech-design/frontend-design.md"],
            ["sprint1/tech-design/frontend-design.md"],
        )
        self.assertEqual(rewards["reward"], 0.0)
        self.assertEqual(rewards["delivery_completeness"], 0)
        self.assertEqual(rewards["rubric_pass_rate"], 1.0)
        self.assertEqual(rewards["document_acceptance"], 0)
        self.assertEqual(
            report["delivery"]["missing_files"],
            ["sprint1/tech-design/frontend-design.md"],
        )
        details = rewardkit_details(report)["delivery_completeness"]
        self.assertEqual(details["score"], 0.0)
        self.assertEqual(details["criteria"][1]["error"], "MISSING_REQUIRED_FILE")

    def test_direct_judge_builds_schema_constrained_chat_request(self):
        schema = {"$schema": "draft", "type": "object", "properties": {}}
        value = request_payload("openai/gpt-5.6-sol", "judge", schema, 8000)
        self.assertEqual(api_model("openai/gpt-5.6-sol"), "gpt-5.6-sol")
        self.assertEqual(value["model"], "gpt-5.6-sol")
        self.assertEqual(value["messages"][1]["content"], "judge")
        self.assertEqual(value["response_format"]["type"], "json_schema")
        self.assertTrue(value["response_format"]["json_schema"]["strict"])
        self.assertNotIn(
            "$schema", value["response_format"]["json_schema"]["schema"]
        )
        self.assertEqual(value["max_completion_tokens"], 8000)
        self.assertTrue(value["stream"])
        self.assertEqual(value["stream_options"], {"include_usage": True})
        self.assertEqual(
            chat_completions_url("https://provider.example/v1"),
            "https://provider.example/v1/chat/completions",
        )

    def test_direct_judge_extracts_structured_assistant_content(self):
        response = {
            "choices": [{"message": {"content": '{"group_id":"prd"}'}}]
        }
        self.assertEqual(parse_judgment(response), {"group_id": "prd"})
        with self.assertRaisesRegex(ValueError, "no text content"):
            parse_judgment({"choices": [{"message": {"content": ""}}]})

    def test_direct_judge_reassembles_streamed_structured_output(self):
        class Stream(BytesIO):
            headers = {"Content-Type": "text/event-stream"}

        chunks = [
            {"id": "resp-1", "model": "judge", "choices": [{
                "delta": {"reasoning_content": "internal"}, "finish_reason": None,
            }]},
            {"id": "resp-1", "model": "judge", "choices": [{
                "delta": {"content": '{"group_id":'}, "finish_reason": None,
            }]},
            {"id": "resp-1", "model": "judge", "choices": [{
                "delta": {"content": '"prd"}'}, "finish_reason": "stop",
            }]},
            {"id": "resp-1", "model": "judge", "choices": [],
             "usage": {"prompt_tokens": 10, "completion_tokens": 2}},
        ]
        body = "".join(
            "data: " + json.dumps(chunk) + "\n\n" for chunk in chunks
        ) + "data: [DONE]\n\n"
        response = read_response(Stream(body.encode()))
        self.assertEqual(parse_judgment(response), {"group_id": "prd"})
        self.assertEqual(response["choices"][0]["finish_reason"], "stop")
        self.assertEqual(response["usage"]["prompt_tokens"], 10)

    def test_direct_judge_accepts_read_only_prompt_mount(self):
        prompt = Path(self.temp.name) / "prompt.md"
        prompt.write_text("fixed evidence")
        with patch("pathlib.Path.unlink", side_effect=OSError("read-only")):
            self.assertEqual(load_prompt(str(prompt)), "fixed evidence")

    def test_direct_judge_loads_and_deletes_credential_file(self):
        credential = Path(self.temp.name) / "credentials.json"
        credential.write_text(json.dumps({
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "https://provider.example/v1",
        }))
        self.assertEqual(
            load_credentials(str(credential)),
            ("test-key", "https://provider.example/v1"),
        )
        self.assertFalse(credential.exists())

    def test_v4_manifest_is_documents_only_and_keeps_atomic_group_counts(self):
        manifest_path = (
            Path(__file__).resolve().parents[2]
            / "examples/document-rubric-evaluation/rubrics/document-rubrics.v4.json"
        )
        manifest = Manifest.load(manifest_path)
        self.assertEqual(
            {group.group_id: len(group.rubrics) for group in manifest.groups},
            {"prd": 8, "tech_design": 8, "test_design": 6},
        )
        evidence = [item for group in manifest.groups for item in group.evidence]
        self.assertFalse(any(item.root in {"base", "templates"} for item in evidence))
        self.assertFalse(any("target-schema.graphql" in item.path for item in evidence))
        self.assertNotIn(
            "TDD-B8",
            {rubric.rubric_id for group in manifest.groups for rubric in group.rubrics},
        )
        tdd4 = next(
            rubric for group in manifest.groups for rubric in group.rubrics
            if rubric.rubric_id == "TDD4"
        )
        self.assertIn("不能作为本项失败依据", tdd4.criteria)

    def test_prepare_only_wires_private_manifest_without_copying_it_to_agent(self):
        from runtime import run_workflow

        root = Path(self.temp.name)
        task = root / "task"
        (task / "env").mkdir(parents=True)
        (task / "instruction.md").write_text("Evaluate this fixture.\n")
        (task / "task.toml").write_text('''schema_version = "1.3"

[task]
name = "bench/document-eval-fixture"

[metadata]
task_id = "document-eval-fixture"

[environment]
docker_image = "registry.invalid/document-eval-fixture:1"
cpus = 1
memory_mb = 1024
storage_mb = 4096
build_timeout_sec = 60.0
''')
        (task / "env/manifest.json").write_text(json.dumps({"repositories": {
            "fixture": {"agent_baseline_commit": "a" * 40},
        }}))

        runtime_home = root / "runtime-home"
        args = [
            "run_workflow", "--task", str(task), "--mode", "single", "--prepare-only",
            "--job-name", "document-eval-fixture", "--document-eval-manifest", str(self.path),
            "--judge-model", "judge-model",
        ]
        with patch.object(run_workflow, "HERE", runtime_home), patch("sys.argv", args), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_workflow.main(), 0)
        prepared = runtime_home / ".prepared/document-eval-fixture"
        recipe = json.loads((prepared / "job.json").read_text())
        self.assertEqual(
            recipe["verifier"]["import_path"],
            "runtime.document_rubric_verifier:DocumentRubricVerifier",
        )
        self.assertEqual(recipe["verifier"]["kwargs"]["manifest_path"], str(self.path.resolve()))
        self.assertEqual(recipe["verifier"]["kwargs"]["evaluation_boundary"], "sprint1/test-design")
        self.assertEqual(recipe["agents"][0]["kwargs"]["stop_after_stage"], "sprint1/test-design")
        self.assertEqual(
            recipe["agents"][0]["kwargs"]["missing_output_policy"],
            "continue_for_evaluation",
        )
        self.assertFalse(any(path.name == self.path.name for path in (prepared / "workspace").rglob("*")))


class RecordingEnvironment:
    def __init__(self, calls):
        self.calls = calls

    async def upload_file(self, source, target):
        self.calls.append(("upload_file", str(source), target))

    async def upload_dir(self, source, target):
        self.calls.append(("upload_dir", str(source), target))


class DocumentRubricVerifierPreparationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prepared = self.root / "prepared"
        self.workspace = self.prepared / "workspace"
        self.workspace.mkdir(parents=True)
        self.private = self.root / "private"
        self.private.mkdir()
        self.manifest_path = self.private / "manifest.json"
        self.trial = self.root / "trial"
        (self.trial / "workflow/accepted/sprint1/prd").mkdir(parents=True)
        (self.trial / "workflow/accepted/sprint1/prd/prd.md").write_text("candidate\n")
        self.calls = []

    def verifier(self):
        verifier = object.__new__(DocumentRubricVerifier)
        verifier.manifest_path = self.manifest_path
        verifier.prepared_path = self.prepared
        verifier.candidate_path = None
        verifier.judge_backend = "direct"
        verifier.judge_model = "judge"
        verifier.judge_timeout_sec = 30
        verifier.judge_max_completion_tokens = 8000
        verifier.max_evidence_bytes = 100_000
        verifier.evaluation_boundary = "sprint1/test-design"
        verifier.override_env = {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "https://example.invalid/v1",
        }
        verifier.verifier_env = {}
        verifier.environment = RecordingEnvironment(self.calls)
        verifier.trial_paths = SimpleNamespace(trial_dir=self.trial)

        async def record_exec(command, *, env=None):
            self.calls.append(("exec", command, env))
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        verifier._exec = record_exec
        return verifier

    def write_manifest(self, evidence):
        value = manifest_value()
        value["groups"] = [value["groups"][0]]
        value["groups"][0]["evidence"] = evidence
        self.manifest_path.write_text(json.dumps(value))
        return Manifest.load(self.manifest_path)

    async def test_direct_verifier_uploads_only_runner_and_returns_api_environment(self):
        manifest = self.write_manifest([
            {"root": "candidate", "path": "sprint1/prd/prd.md", "purpose": "candidate"},
        ])

        env = await self.verifier()._prepare_remote(manifest)

        self.assertEqual(env, {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "https://example.invalid/v1",
        })
        uploads = [call for call in self.calls if call[0] == "upload_file"]
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0][2], REMOTE_DIRECT_RUNNER.as_posix())
        self.assertFalse(any(call[0] == "upload_dir" for call in self.calls))
        self.assertFalse(any(call[0] == "exec" and "git -C" in call[1]
                             for call in self.calls))

    def test_fixed_evidence_packet_inlines_declared_files_with_hashes(self):
        (self.workspace / "public").mkdir()
        (self.workspace / "public/query.md").write_text("public requirement\n")
        manifest = self.write_manifest([
            {"root": "candidate", "path": "sprint1/prd/prd.md", "purpose": "candidate"},
            {"root": "public", "path": "query.md", "purpose": "query"},
        ])
        verifier = self.verifier()
        entries = verifier._evidence_entries(manifest.groups[0])

        self.assertEqual([entry["path"] for entry in entries], [
            "/candidate/sprint1/prd/prd.md", "/public/query.md",
        ])
        full = verifier._evidence_packet(entries, include_content=True)
        audit = verifier._evidence_packet(entries, include_content=False)
        self.assertIn("candidate\n", full)
        self.assertIn("public requirement\n", full)
        self.assertIn('"sha256":', full)
        self.assertNotIn("candidate\n", audit)
        self.assertNotIn("public requirement\n", audit)

    def test_missing_candidate_is_scored_but_missing_evaluator_input_is_infrastructure_error(self):
        manifest = self.write_manifest([
            {"root": "candidate", "path": "missing.md", "purpose": "candidate"},
        ])
        entries = self.verifier()._evidence_entries(manifest.groups[0])
        self.assertEqual(entries[0]["content"], "<missing required file>")

        manifest = self.write_manifest([
            {"root": "public", "path": "missing.md", "purpose": "query"},
        ])
        with self.assertRaisesRegex(DocumentEvaluationError, "required evaluator input"):
            self.verifier()._evidence_entries(manifest.groups[0])

    def test_inline_evidence_has_a_hard_size_limit(self):
        (self.workspace / "public").mkdir()
        (self.workspace / "public/query.md").write_text("123456")
        manifest = self.write_manifest([
            {"root": "public", "path": "query.md", "purpose": "query"},
        ])
        verifier = self.verifier()
        verifier.max_evidence_bytes = 5
        with self.assertRaisesRegex(DocumentEvaluationError, "exceeds 5 bytes"):
            verifier._evidence_entries(manifest.groups[0])

    async def test_exec_preserves_stdout_when_shell_warning_occupies_stderr(self):
        verifier = self.verifier()

        async def failed_exec(**kwargs):
            return SimpleNamespace(
                return_code=2,
                stderr="bash: no job control in this shell\n",
                stdout="actual runner failure\n",
            )

        verifier.environment.exec = failed_exec
        del verifier._exec
        with self.assertRaisesRegex(DocumentEvaluationError, "actual runner failure"):
            await verifier._exec("false")

    async def test_explicit_candidate_path_supports_regrade_without_mutating_source(self):
        source_candidate = self.root / "source-trial/workflow/accepted"
        (source_candidate / "sprint1/prd").mkdir(parents=True)
        (source_candidate / "sprint1/prd/prd.md").write_text("sealed\n")
        manifest = self.write_manifest([
            {"root": "candidate", "path": "sprint1/prd/prd.md", "purpose": "candidate"},
        ])
        verifier = self.verifier()
        verifier.candidate_path = source_candidate.resolve()

        entries = verifier._evidence_entries(manifest.groups[0])

        self.assertEqual(entries[0]["content"], "sealed\n")
        self.assertEqual(
            (source_candidate / "sprint1/prd/prd.md").read_text(),
            "sealed\n",
        )

    def test_only_structured_protocol_errors_are_retryable(self):
        self.assertTrue(DocumentRubricVerifier._retryable_protocol_error(
            DocumentEvaluationError("Direct document Judge output is not valid JSON: bad")
        ))
        self.assertTrue(DocumentRubricVerifier._retryable_protocol_error(
            DocumentEvaluationError("invalid structured judgment for prd")
        ))
        self.assertFalse(DocumentRubricVerifier._retryable_protocol_error(
            DocumentEvaluationError("HTTP 401 unauthorized")
        ))

    def test_required_candidate_paths_stop_at_document_boundary(self):
        resolved = {
            "contract": {"delivery": {"required": [
                "artifact:sprint1/prd/prd",
                "artifact:sprint1/tech-design/frontend_design",
                "artifact:sprint1/test-design/test_cases",
                "artifact:sprint1/development/handoff",
            ]}},
            "stages": [
                {"stage_id": "sprint1/prd", "outputs": {
                    "artifact:sprint1/prd/prd": "/workspace/artifacts/sprint1/prd/prd.md",
                }},
                {"stage_id": "sprint1/tech-design", "outputs": {
                    "artifact:sprint1/tech-design/frontend_design":
                        "/workspace/artifacts/sprint1/tech-design/frontend-design.md",
                }},
                {"stage_id": "sprint1/test-design", "outputs": {
                    "artifact:sprint1/test-design/test_cases":
                        "/workspace/artifacts/sprint1/test-design/test-cases.v1.csv",
                }},
                {"stage_id": "sprint1/development", "outputs": {
                    "artifact:sprint1/development/handoff":
                        "/workspace/artifacts/sprint1/development/test-handoff.md",
                }},
            ],
        }
        (self.prepared / "resolved-workflow.json").write_text(json.dumps(resolved))
        verifier = self.verifier()
        self.assertEqual(verifier._required_candidate_paths(), [
            "sprint1/prd/prd.md",
            "sprint1/tech-design/frontend-design.md",
            "sprint1/test-design/test-cases.v1.csv",
        ])
        required, missing = verifier._delivery_status()
        self.assertEqual(required, verifier._required_candidate_paths())
        self.assertEqual(missing, [
            "sprint1/tech-design/frontend-design.md",
            "sprint1/test-design/test-cases.v1.csv",
        ])


if __name__ == "__main__":
    unittest.main()
