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

from runtime.document_rubric import (
    Manifest,
    aggregate,
    apply_delivery_gate,
    disagreements,
    rewardkit_details,
    validate_judgment,
)
from runtime.document_rubric_verifier import (
    DocumentEvaluationError,
    DocumentRubricVerifier,
    REMOTE_BASE_REVISIONS,
    REMOTE_JUDGE_CWD,
)
from runtime.document_opencode_judge_runner import (
    OPENCODE_PLUGIN_VERSION,
    opencode_config,
    opencode_environment,
    prepare_opencode_dependencies,
    warmup_opencode,
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

    def test_opencode_judge_pins_title_model_to_allowed_judge_model(self):
        value = opencode_config("openai/hy4-preview", "https://new-api.example/v1")
        self.assertEqual(value["model"], "openai/hy4-preview")
        self.assertEqual(value["small_model"], "openai/hy4-preview")
        self.assertEqual(value["agent"]["title"], {"disable": True})
        self.assertEqual(value["agent"]["build"], {"steps": 12})
        self.assertEqual(value["provider"]["openai"]["models"], {"hy4-preview": {}})

    def test_opencode_judge_isolates_global_config_and_plugin_cache(self):
        root = Path(self.temp.name) / "judge"
        config_path = root / "opencode.json"
        value = opencode_environment(root, config_path, {
            "HOME": "/root",
            "PATH": "/usr/bin",
            "CODEX_HOME": "/tmp/codex-home",
            "HTTP_PROXY": "http://proxy.invalid:7890",
            "https_proxy": "http://proxy.invalid:7890",
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "https://new-api.example/v1",
        })
        self.assertEqual(value["OPENCODE_CONFIG"], str(config_path))
        self.assertNotIn("HTTP_PROXY", value)
        self.assertNotIn("https_proxy", value)
        self.assertNotIn("CODEX_HOME", value)
        self.assertEqual(value["OPENAI_API_KEY"], "test-key")
        self.assertTrue(value["PATH"].startswith("/opt/document-eval/bin:"))
        for name in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
            self.assertTrue(Path(value[name]).is_dir())
            self.assertTrue(Path(value[name]).is_relative_to(root))
        for name in (
            "OPENCODE_PURE", "OPENCODE_DISABLE_MODELS_FETCH",
            "OPENCODE_DISABLE_AUTOUPDATE", "OPENCODE_DISABLE_PRUNE",
            "OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER",
        ):
            self.assertEqual(value[name], "1")

    def test_opencode_judge_preinstalls_matching_plugin_without_scripts(self):
        root = Path(self.temp.name) / "judge"
        with patch("runtime.document_opencode_judge_runner.subprocess.run") as run:
            prepare_opencode_dependencies(root, {"PATH": "/usr/bin"})
        package = json.loads((root / "xdg-config/opencode/package.json").read_text())
        self.assertEqual(
            package["dependencies"],
            {"@opencode-ai/plugin": OPENCODE_PLUGIN_VERSION},
        )
        command = run.call_args.args[0]
        self.assertEqual(command[0:2], ["npm", "install"])
        self.assertIn("--ignore-scripts", command)

    def test_opencode_judge_warmup_runs_once_per_sandbox(self):
        root = Path(self.temp.name) / "judge"
        root.mkdir()
        completed = SimpleNamespace(returncode=0)
        with patch("runtime.document_opencode_judge_runner.subprocess.run",
                   return_value=completed) as run:
            warmup_opencode(root, "openai/hy4-preview", "/tmp", {})
            warmup_opencode(root, "openai/hy4-preview", "/tmp", {})
        self.assertEqual(run.call_count, 1)
        self.assertEqual((root / ".judge-warmed").read_text(), "ok\n")

    def test_prepare_only_wires_private_manifest_without_copying_it_to_agent(self):
        from runtime import run_workflow

        root = Path(self.temp.name)
        task = root / "task"
        source = Path(run_workflow.__file__).resolve().parents[1] / "tasks/standard"
        for name in ("roles", "templates", "public", "workflows", "workflow-runtime"):
            shutil.copytree(source / name, task / name)
        repo = task / "environment/repos/fixture"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "README.md").write_text("fixture\n")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run([
            "git", "-C", str(repo), "-c", "user.name=Fixture",
            "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
            "commit", "-qm", "fixture",
        ], check=True)
        sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        (task / "environment/base-revisions.json").write_text(json.dumps({"fixture": {"commit": sha}}))

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
        verifier.opencode_plugin_archive_path = None
        verifier.opencode_plugin_archive_sha256 = None
        verifier.ripgrep_archive_path = None
        verifier.ripgrep_archive_sha256 = None
        verifier.judge_backend = "opencode"
        verifier.judge_model = "judge"
        verifier.judge_timeout_sec = 30
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

    async def test_separate_verifier_uploads_workspace_inputs_before_materializing_base(self):
        (self.workspace / "public").mkdir()
        (self.workspace / "public/query.md").write_text("query\n")
        (self.workspace / "templates").mkdir()
        (self.workspace / "templates/frontend-design.md").write_text("template\n")
        commit = "a" * 40
        (self.workspace / "base-revisions.json").write_text(json.dumps({
            "saleor": {"commit": commit},
        }))
        manifest = self.write_manifest([
            {"root": "candidate", "path": "sprint1/prd/prd.md", "purpose": "candidate"},
            {"root": "public", "path": "query.md", "purpose": "query"},
            {"root": "templates", "path": "frontend-design.md", "purpose": "template"},
            {"root": "base", "path": "saleor", "purpose": "base"},
        ])

        await self.verifier()._prepare_remote(manifest)

        base_upload = next(index for index, call in enumerate(self.calls)
                           if call[:1] == ("upload_file",)
                           and call[2] == REMOTE_BASE_REVISIONS.as_posix())
        materialize = next(index for index, call in enumerate(self.calls)
                           if call[0] == "exec" and "git -C" in call[1])
        self.assertLess(base_upload, materialize)
        self.assertIn(
            ("upload_dir", str((self.workspace / "public").resolve()), "/workspace/public"),
            self.calls,
        )
        self.assertIn(
            ("upload_dir", str((self.workspace / "templates").resolve()), "/workspace/templates"),
            self.calls,
        )
        self.assertIn("for name in saleor", self.calls[materialize][1])
        self.assertIn(REMOTE_BASE_REVISIONS.as_posix(), self.calls[materialize][1])

    async def test_candidate_only_rubric_does_not_require_base_workspace(self):
        manifest = self.write_manifest([
            {"root": "candidate", "path": "sprint1/prd/prd.md", "purpose": "candidate"},
        ])

        await self.verifier()._prepare_remote(manifest)

        self.assertFalse(any(call[0] == "upload_file"
                             and call[2] == REMOTE_BASE_REVISIONS.as_posix()
                             for call in self.calls))
        self.assertFalse(any(call[0] == "exec" and "git -C" in call[1]
                             for call in self.calls))

    async def test_base_rubric_rejects_missing_revision_manifest(self):
        manifest = self.write_manifest([
            {"root": "base", "path": "saleor", "purpose": "base"},
        ])

        with self.assertRaisesRegex(DocumentEvaluationError, "base-revisions.json"):
            await self.verifier()._prepare_remote(manifest)

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

        await verifier._prepare_remote(manifest)

        self.assertIn(
            ("upload_dir", str(source_candidate.resolve()), "/opt/document-eval/candidate"),
            self.calls,
        )
        self.assertEqual(
            (source_candidate / "sprint1/prd/prd.md").read_text(),
            "sealed\n",
        )

    async def test_pinned_opencode_plugin_archive_is_uploaded_and_verified(self):
        archive = self.root / "opencode-plugin.tgz"
        archive.write_bytes(b"frozen plugin archive")
        manifest = self.write_manifest([
            {"root": "candidate", "path": "sprint1/prd/prd.md", "purpose": "candidate"},
        ])
        verifier = self.verifier()
        verifier.opencode_plugin_archive_path = archive
        verifier.opencode_plugin_archive_sha256 = __import__("hashlib").sha256(
            archive.read_bytes()
        ).hexdigest()

        await verifier._prepare_remote(manifest)

        self.assertTrue(any(call[0] == "upload_file" and call[1] == str(archive)
                            and call[2].endswith("/opencode-plugin.tgz")
                            for call in self.calls))
        self.assertTrue(any(call[0] == "exec" and "sha256sum" in call[1]
                            and "tar xzf" in call[1] for call in self.calls))

    async def test_pinned_ripgrep_archive_is_installed_into_judge_path(self):
        archive = self.root / "ripgrep.tar.gz"
        archive.write_bytes(b"frozen ripgrep archive")
        manifest = self.write_manifest([
            {"root": "candidate", "path": "sprint1/prd/prd.md", "purpose": "candidate"},
        ])
        verifier = self.verifier()
        verifier.ripgrep_archive_path = archive
        verifier.ripgrep_archive_sha256 = __import__("hashlib").sha256(
            archive.read_bytes()
        ).hexdigest()

        await verifier._prepare_remote(manifest)

        self.assertTrue(any(call[0] == "upload_file" and call[1] == str(archive)
                            and call[2].endswith("/ripgrep.tar.gz")
                            for call in self.calls))
        self.assertTrue(any(call[0] == "exec" and "install -m 555" in call[1]
                            and "/bin/rg" in call[1] for call in self.calls))

    def test_judge_uses_empty_workdir_outside_candidate_tree(self):
        self.assertTrue(REMOTE_JUDGE_CWD.is_absolute())
        self.assertFalse(REMOTE_JUDGE_CWD.is_relative_to(Path("/opt/document-eval")))

    def test_only_structured_protocol_errors_are_retryable(self):
        self.assertTrue(DocumentRubricVerifier._retryable_protocol_error(
            DocumentEvaluationError("OpenCode final output is not JSON: bad")
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
