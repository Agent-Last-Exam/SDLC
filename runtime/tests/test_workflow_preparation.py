"""Contract/preparation checks; no Agent, Docker, model, or network calls."""

import json
from pathlib import Path
import tempfile
import unittest

import yaml

from runtime.prepare_workflow import (
    CONTRACT, DEFAULTS, HIERARCHICAL_BUDGETS, MODES, compile_workflow,
    derive_base_revisions, prepare, read_yaml, resolve_mode, resolve_source, safe_relative,
    validate_run,
)

PRUNED = Path(__file__).resolve().parents[2] / "tasks/saleor-3.23-pruned"

TASK_TOML = '''schema_version = "1.3"

[task]
name = "bench/frozen"

[metadata]
task_id = "frozen"

[environment]
docker_image = "registry.invalid/frozen:1"
cpus = 8
memory_mb = 16384
storage_mb = 40960
build_timeout_sec = 7200.0
'''


class TaskFixture(unittest.TestCase):
    """A frozen package carrying only business inputs, Base identity and an image."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        self.task = self.root / "frozen"
        (self.task / "env").mkdir(parents=True)
        (self.task / "instruction.md").write_text("Business need\n")
        (self.task / "task.toml").write_text(TASK_TOML)
        (self.task / "env/manifest.json").write_text(json.dumps({"repositories": {
            "saleor": {"agent_baseline_commit": "c" * 40},
            "saleor-dashboard": {"agent_baseline_commit": "a" * 40},
        }}))

    def contract_with(self, **changes):
        """Write an isolated copy of the default contract, resolved against the task."""
        contract = read_yaml(CONTRACT)
        contract.update(changes)
        path = self.task / "contract.yaml"
        path.write_text(yaml.safe_dump(contract))
        return path

    def compile(self, mode="single", **changes):
        return compile_workflow(
            mode, self.task, verify_repos=False, contract_path=self.contract_with(**changes),
        )

class ModeProfileTests(TaskFixture):
    def test_each_mode_loads_its_own_runtime_profile(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                self.assertEqual(resolve_mode(mode), DEFAULTS / f"workflows/{mode}.yaml")
                result = self.compile(mode)
                self.assertEqual(result["mode"], mode)
                self.assertEqual(result["run"]["agent"]["adapter"], "claude_code")
                self.assertNotIn("execution_implemented", result)
                self.assertNotIn("execution_ready", result)
                self.assertNotIn("execution_blockers", result)

    def test_all_modes_share_one_stage_graph(self):
        single = self.compile("single")
        for mode in ("flat", "hierarchical"):
            with self.subTest(mode=mode):
                self.assertEqual(self.compile(mode)["stages"], single["stages"])

    def test_profiles_declare_only_fields_the_runtime_reads(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                profile = read_yaml(resolve_mode(mode))
                self.assertEqual(
                    set(profile),
                    {"schema_version", "kind", "mode", "contract", "agent", "execution"},
                )
                expected = {"max_cost_usd"} | (
                    set(HIERARCHICAL_BUDGETS)
                    if mode == "hierarchical" else {"subagents"}
                )
                self.assertEqual(set(profile["execution"]), expected)

    def test_qa_rounds_come_from_the_stage_graph_alone(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                result = self.compile(mode)
                self.assertNotIn("max_qa_rounds", result["run"]["execution"])
                self.assertNotIn("qa_rounds", result)
                self.assertNotIn("qa_rounds", result["contract"]["delivery"])
                rounds = [s["round"] for s in result["stages"] if s["role"] == "qa"]
                self.assertEqual(rounds, [1, 2])

    def test_fixed_stage_modes_enable_subagents(self):
        for mode in ("single", "flat"):
            with self.subTest(mode=mode):
                self.assertTrue(self.compile(mode)["run"]["execution"]["subagents"]["enabled"])

    def test_every_mode_declares_a_cost_budget(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                self.assertGreater(self.compile(mode)["run"]["execution"]["max_cost_usd"], 0)

    def test_hierarchical_budgets_are_positive_and_consistent(self):
        execution = self.compile("hierarchical")["run"]["execution"]
        for key in HIERARCHICAL_BUDGETS:
            with self.subTest(key=key):
                self.assertIsInstance(execution[key], int)
                self.assertGreater(execution[key], 0)
        self.assertLessEqual(execution["max_concurrency"], execution["max_members"])

    def test_unknown_mode_rejected(self):
        for mode in ("", "parallel", None):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "Unknown mode"):
                resolve_mode(mode)
        self.assertEqual(sorted(MODES), ["flat", "hierarchical", "single"])


class ProfileValidationTests(unittest.TestCase):
    """The profile is the source of truth, so invalid values must fail loudly."""

    def profile(self, _mode, **changes):
        run = read_yaml(resolve_mode(_mode))
        for key, value in changes.items():
            if key == "execution":
                run["execution"] = {**run["execution"], **value}
            else:
                run[key] = value
        return run

    def test_declared_mode_must_match_the_file(self):
        # A mismatch would route the run to a different controller than requested.
        run = self.profile("flat", mode="hierarchical")
        with self.assertRaisesRegex(ValueError, "declares mode"):
            validate_run(run, resolve_mode("flat"))

    def test_unsupported_schema_or_adapter_rejected(self):
        for change, message in (
            ({"schema_version": 2}, "Unsupported workflow schema"),
            ({"kind": "something_else"}, "Unsupported workflow schema"),
            ({"agent": {"adapter": "codex"}}, "Unsupported agent adapter"),
        ):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                validate_run(self.profile("flat", **change), resolve_mode("flat"))

    def test_cost_budget_must_be_a_positive_number(self):
        for mode in MODES:
            for value in (0, -1.0, "fifty", None, True):
                with self.subTest(mode=mode, value=value), \
                        self.assertRaisesRegex(ValueError, "max_cost_usd"):
                    validate_run(
                        self.profile(mode, execution={"max_cost_usd": value}),
                        resolve_mode(mode),
                    )

    def test_cost_budget_accepts_int_and_float(self):
        for value in (25, 12.5):
            with self.subTest(value=value):
                run = validate_run(
                    self.profile("flat", execution={"max_cost_usd": value}),
                    resolve_mode("flat"),
                )
                self.assertEqual(run["execution"]["max_cost_usd"], value)

    def test_hierarchical_budgets_must_be_positive_and_consistent(self):
        for change, message in (
            ({"max_lead_turns": 0}, "max_lead_turns"),
            ({"max_members": "ten"}, "max_members"),
            ({"max_concurrency": 99}, "cannot exceed max_members"),
        ):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                validate_run(
                    self.profile("hierarchical", execution=change), resolve_mode("hierarchical")
                )

    def test_unused_profile_fields_are_rejected(self):
        path = resolve_mode("hierarchical")
        with self.assertRaisesRegex(ValueError, "run profile fields"):
            validate_run(self.profile("hierarchical", lead={"blueprint": "lead"}), path)
        with self.assertRaisesRegex(ValueError, "execution fields"):
            validate_run(
                self.profile("hierarchical", execution={"scheduling": "lead_managed"}),
                path,
            )

    def test_subagents_must_declare_enabled_for_fixed_stage_modes(self):
        with self.assertRaisesRegex(ValueError, "one boolean enabled field"):
            validate_run(
                self.profile("flat", execution={"subagents": {"scope": "current_stage"}}),
                resolve_mode("flat"),
            )

    def test_shipped_profiles_are_valid(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                path = resolve_mode(mode)
                self.assertEqual(validate_run(read_yaml(path), path)["mode"], mode)

class ContractTests(TaskFixture):
    def test_prd_handoff_and_final_scope(self):
        result = self.compile()
        prd, tech = result["stages"][:2]
        ref = "artifact:sprint1/prd/prd"
        self.assertEqual(prd["outputs"][ref], tech["inputs"][ref])
        self.assertEqual(len(tech["outputs"]), 4)
        self.assertEqual(
            tech["additional_output_directory"],
            "/workspace/artifacts/sprint1/tech-design/interfaces",
        )
        self.assertEqual(result["contract"]["delivery"]["stop_after"], "sprint2/qa")
        self.assertEqual(len(result["stages"]), 11)

    def test_instruction_is_the_business_input(self):
        result = self.compile()
        self.assertEqual(result["workspace_paths"]["input:instruction"], "instruction.md")
        self.assertEqual(result["workspace_paths"]["input:base_revisions"], "base-revisions.json")
        self.assertEqual(result["workspace_paths"]["input:repos"], "repos")
        prd = result["stages"][0]
        self.assertEqual(set(prd["inputs"]), {"input:instruction", "input:repos", "template:prd"})
        self.assertNotIn("private", json.dumps(result, ensure_ascii=False).lower())

    def test_inputs_must_be_explicit_and_use_the_runtime_layout(self):
        contract = read_yaml(CONTRACT)
        contract["inputs"]["instruction"] = "task:instruction.md"
        with self.assertRaisesRegex(ValueError, "explicitly declare"):
            self.compile(inputs=contract["inputs"])
        contract = read_yaml(CONTRACT)
        contract["inputs"]["instruction"]["workspace"] = "public/query.md"
        with self.assertRaisesRegex(ValueError, "must use workspace paths"):
            self.compile(inputs=contract["inputs"])
        contract = read_yaml(CONTRACT)
        contract["inputs"]["extra"] = {
            "source": "task:instruction.md", "workspace": "extra.md",
        }
        with self.assertRaisesRegex(ValueError, "requires exactly"):
            self.compile(inputs=contract["inputs"])

    def test_future_or_missing_artifact_is_rejected(self):
        contract = read_yaml(CONTRACT)
        contract["stages"][0]["inputs"].append("artifact:sprint1/tech-design/backend_design")
        with self.assertRaisesRegex(ValueError, "future input"):
            self.compile(stages=contract["stages"])

    def test_missing_template_rejected(self):
        contract = read_yaml(CONTRACT)
        contract["templates"]["prd"] = "defaults:absent.md"
        with self.assertRaisesRegex(ValueError, "Missing templates"):
            self.compile(templates=contract["templates"])

    def test_output_cannot_write_into_previous_stage(self):
        contract = read_yaml(CONTRACT)
        contract["stages"][1]["outputs"]["backend_design"] = "artifacts/sprint1/prd/backend-design.md"
        with self.assertRaisesRegex(ValueError, "outside its stage"):
            self.compile(stages=contract["stages"])

    def test_unsupported_contract_rejected(self):
        for change, message in (
            ({"kind": "something_else"}, "Unsupported delivery contract"),
            ({"scope": "global"}, "local_sdlc"),
        ):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                self.compile(**change)

    def test_path_escape_rejected(self):
        for path in ("../bad", "/tmp/bad", "artifacts/../bad", "a\\b", "a//b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_relative(path)

    def test_duplicate_keys_rejected(self):
        path = self.root / "duplicate.yaml"
        path.write_text("mode: single\nmode: flat\n")
        with self.assertRaisesRegex(ValueError, "Duplicate YAML key"):
            read_yaml(path)

class SourceSchemeTests(TaskFixture):
    def test_defaults_scheme_resolves_into_the_runtime_bundle(self):
        self.assertEqual(
            resolve_source("defaults:lead.system.md", base=self.root, task=None, group="roles"),
            DEFAULTS / "roles/lead.system.md",
        )
        result = self.compile()
        for group in ("roles", "templates"):
            with self.subTest(group=group):
                self.assertTrue(all(
                    Path(p).is_relative_to(DEFAULTS) for p in result["sources"][group].values()
                ))

    def test_task_scheme_resolves_against_the_package(self):
        self.assertEqual(
            resolve_source("task:instruction.md", base=self.root, task=self.task, group="inputs"),
            self.task / "instruction.md",
        )

    def test_schemes_cannot_escape_or_cross_groups(self):
        for value, group in (
            ("defaults:../../.env", "roles"),
            ("defaults:/etc/passwd", "roles"),
            ("task:../outside.md", "inputs"),
            ("derive:../outside.json", "inputs"),
            ("defaults:query.md", "inputs"),
            ("task:instruction.md", "roles"),
            ("derive:env/manifest.json", "templates"),
        ):
            with self.subTest(value=value, group=group), self.assertRaises(ValueError):
                resolve_source(value, base=self.root, task=self.task, group=group)

    def test_task_scheme_requires_a_task(self):
        with self.assertRaisesRegex(ValueError, "requires a task directory"):
            resolve_source("task:instruction.md", base=self.root, task=None, group="inputs")


class BaseRevisionTests(TaskFixture):
    def test_agent_baseline_is_the_derived_base(self):
        derived = json.loads(self.compile()["generated_inputs"]["base_revisions"])
        self.assertEqual(derived, {
            "saleor": {"version": "agent-baseline", "commit": "c" * 40},
            "saleor-dashboard": {"version": "agent-baseline", "commit": "a" * 40},
        })

    def test_derive_is_only_defined_for_base_revisions(self):
        contract = read_yaml(CONTRACT)
        contract["inputs"]["instruction"]["source"] = "derive:env/manifest.json"
        with self.assertRaisesRegex(ValueError, "only defined for base_revisions"):
            self.compile(inputs=contract["inputs"])

    def test_unsafe_manifest_values_rejected(self):
        manifest = self.task / "env/manifest.json"
        for repositories, message in (
            ({"saleor": {"agent_baseline_commit": "not-a-sha"}}, "Invalid agent baseline"),
            ({"../escape": {"agent_baseline_commit": "c" * 40}}, "Unsafe repository name"),
        ):
            with self.subTest(repositories=repositories):
                manifest.write_text(json.dumps({"repositories": repositories}))
                with self.assertRaisesRegex(ValueError, message):
                    derive_base_revisions(manifest)

    def test_real_pruned_package_derives_its_recorded_baselines(self):
        derived = derive_base_revisions(PRUNED / "env/manifest.json")
        self.assertEqual(
            derived["saleor"]["commit"], "c864e66b8e537d30732ddba62d3a4c47e49e4a3e"
        )
        self.assertEqual(
            derived["saleor-dashboard"]["commit"], "aebb2401b5079fbbb8c60150289d1896c108feca"
        )

class GeneratedHarborDefinitionTests(TaskFixture):
    def test_published_image_generates_the_definition_and_sources_repos_from_it(self):
        result = self.compile("flat")
        self.assertEqual(result["repos_source"], "image")
        self.assertEqual(result["harbor_sources"], {})
        self.assertEqual(sorted(result["harbor_generated"]), ["Dockerfile", "task.toml"])

        task_toml = result["harbor_generated"]["task.toml"]
        self.assertIn('name = "bench/frozen-flat-workflow"', task_toml)
        self.assertIn("cpus = 8", task_toml)
        self.assertIn("memory_mb = 16384", task_toml)
        self.assertIn('network_mode = "public"', task_toml)

        dockerfile = result["harbor_generated"]["Dockerfile"]
        self.assertIn("FROM registry.invalid/frozen:1", dockerfile)
        self.assertIn("@anthropic-ai/claude-code@2.1.273", dockerfile)
        # Repositories are moved, asserted against Base, and linked back.
        self.assertIn("mv /workspace/saleor /workspace/repos/saleor", dockerfile)
        self.assertIn(f'= "{"c" * 40}"', dockerfile)
        self.assertIn("ln -s /workspace/repos/saleor /workspace/saleor", dockerfile)

    def test_buildable_package_keeps_its_own_definition(self):
        (self.task / "task.toml").write_text(TASK_TOML.replace(
            'docker_image = "registry.invalid/frozen:1"\n', ""
        ))
        (self.task / "environment").mkdir()
        (self.task / "environment/Dockerfile").write_text("FROM scratch\n")
        result = self.compile()
        self.assertEqual(result["repos_source"], "host")
        self.assertEqual(result["harbor_generated"], {})
        self.assertEqual(sorted(result["harbor_sources"]), ["Dockerfile", "task.toml"])

    def test_buildable_package_without_dockerfile_rejected(self):
        (self.task / "task.toml").write_text(TASK_TOML.replace(
            'docker_image = "registry.invalid/frozen:1"\n', ""
        ))
        with self.assertRaisesRegex(ValueError, "Missing task runtime input"):
            self.compile()

    def test_unsafe_image_reference_rejected(self):
        (self.task / "task.toml").write_text(TASK_TOML.replace(
            "registry.invalid/frozen:1", "frozen:1; rm -rf /"
        ))
        with self.assertRaisesRegex(ValueError, "not a safe concrete image reference"):
            self.compile()

    def test_unsafe_task_identity_rejected(self):
        (self.task / "task.toml").write_text(TASK_TOML.replace(
            'name = "bench/frozen"', r'name = "bench\"frozen"'
        ))
        with self.assertRaisesRegex(ValueError, "not a safe TOML string"):
            self.compile()


class PreparedWorkspaceTests(TaskFixture):
    def test_prepared_workspace_carries_defaults_and_task_inputs(self):
        prepared = self.root / "prepared"
        result = prepare(self.compile("flat"), prepared)

        workspace = prepared / "workspace"
        self.assertEqual((workspace / "instruction.md").read_text(), "Business need\n")
        self.assertTrue((workspace / "roles/lead.system.md").is_file())
        self.assertTrue((workspace / "templates/prd.md").is_file())
        self.assertTrue((workspace / "scratch").is_dir())
        self.assertEqual(
            json.loads((workspace / "base-revisions.json").read_text())["saleor"]["commit"],
            "c" * 40,
        )
        # Image-sourced repositories are never staged on the host.
        self.assertFalse((workspace / "repos").exists())
        for name in ("Dockerfile", "task.toml"):
            self.assertTrue((prepared / "runtime-inputs" / name).is_file())
        compiled = json.loads((prepared / "resolved-workflow.json").read_text())
        self.assertEqual(compiled["mode"], "flat")
        manifest = json.loads((prepared / "input-manifest.json").read_text())
        self.assertEqual(result["workspace_files"], len(manifest))
        self.assertIn("instruction.md", manifest)
        self.assertIn("roles/lead.system.md", manifest)

    def test_existing_destination_refused(self):
        prepared = self.root / "prepared"
        prepared.mkdir()
        with self.assertRaisesRegex(ValueError, "already exists"):
            prepare(self.compile(), prepared)

    def test_every_stage_gets_an_artifact_directory(self):
        prepared = self.root / "prepared"
        compiled = self.compile("flat")
        prepare(compiled, prepared)
        for stage in compiled["stages"]:
            with self.subTest(stage=stage["stage_id"]):
                self.assertTrue(
                    (prepared / "workspace/artifacts" / stage["stage_id"]).is_dir()
                )


class RealPackageTests(unittest.TestCase):
    """The pruned package must compile with no workflow files of its own."""

    def test_pruned_package_owns_no_workflow_assets(self):
        for absent in ("workflows", "roles", "templates", "public", "workflow-runtime",
                       "environment/base-revisions.json", "environment/repos"):
            with self.subTest(absent=absent):
                self.assertFalse((PRUNED / absent).exists())

    def test_every_mode_compiles_against_the_pruned_package(self):
        for mode in ("single", "flat", "hierarchical"):
            with self.subTest(mode=mode):
                result = compile_workflow(mode, PRUNED, verify_repos=False)
                self.assertEqual(len(result["stages"]), 11)
                self.assertEqual(result["repos_source"], "image")
                self.assertIn(
                    "sdlcbench/saleor-3.23-env:build-0a5d5bc656cb",
                    result["harbor_generated"]["Dockerfile"],
                )
                self.assertIn(
                    "c864e66b8e537d30732ddba62d3a4c47e49e4a3e",
                    result["harbor_generated"]["Dockerfile"],
                )


if __name__ == "__main__":
    unittest.main()
