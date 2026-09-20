"""Lifecycle branch, version, and contract regression tests; no model calls."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from runtime.prepare_workflow import HERE, compile_workflow
from runtime.workflow_controller import Controller, stage_routing
from runtime.workflow_smoke import write_stage_fixture
from runtime.local_deployment import validate_manifest
from runtime.workspace_snapshot import inventory
from runtime.prepare_workflow import read_yaml
import yaml


class LifecycleBackend:
    synthetic = True

    def __init__(self, workspace, scenario='repair', bad_routing=False, bad_deploy=False, switch_session=False, freeform_prd=False):
        self.workspace, self.scenario = workspace, scenario
        self.bad_routing, self.bad_deploy = bad_routing, bad_deploy
        self.calls, self.reused, self.stops = [], [], 0
        self.stage_index = 0
        self.switch_session, self.freeform_prd = switch_session, freeform_prd

    async def activate(self, stage, session):
        pass

    async def execute(self, stage, prompt, instruction, session, stage_dir):
        self.calls.append((stage['stage_id'], session, prompt, instruction))
        self.candidate = stage_dir / 'fixture'
        write_stage_fixture(self.candidate, stage, self.workspace, self.scenario)
        if self.bad_routing and stage['role'] == 'qa':
            (self.candidate / 'test-verify.json').write_text('{broken json')
        if self.freeform_prd and stage['role'] == 'pm':
            p = self.candidate / 'prd.md'
            p.write_text(p.read_text().replace('优先级：P0', '优先级：关键'))
        return 'changed' if session and self.switch_session else session or 'single-native-session'

    async def quiesce(self):
        pass

    async def collect(self, stage, destination):
        shutil.copytree(self.candidate, destination)

    async def seal(self, stage, hashes):
        pass

    async def verify_baseline(self, artifacts):
        pass

    async def collect_service_logs(self, destination):
        pass

    async def capture_repositories(self, destination):
        return {'sha256': 'synthetic-candidate'}

    async def deploy(self, stage, candidate, stage_dir):
        if self.bad_deploy:
            raise RuntimeError('Synthetic environment failed readiness')
        return {'synthetic': True}

    async def reuse(self, stage, source):
        self.reused.append(stage['stage_id'])

    async def stop_services(self):
        self.stops += 1


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'
        for name in ('templates', 'roles'):
            shutil.copytree(HERE / 'tasks/saleor-prd-tdd' / name, self.workspace / name)
        schema = self.workspace / 'repos/saleor/saleor/graphql/schema.graphql'
        schema.parent.mkdir(parents=True)
        schema.write_text('type Query { shop: Shop! }\ntype Shop { name: String! }\n')
        self.config = compile_workflow(HERE / 'tasks/saleor-prd-tdd/workflows/single.yaml', verify_repos=False)

    async def run_case(self, **kwargs):
        backend = LifecycleBackend(self.workspace, **kwargs)
        controller = Controller(self.config, self.workspace, self.root / 'control', backend)
        return await controller.run(), backend

    async def test_first_pass_stops_before_repair(self):
        state, backend = await self.run_case(scenario='pass')
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(state['cursor'], 6)
        self.assertEqual(len(backend.calls), 6)
        self.assertEqual(state['principal_session'], 'single-native-session')
        self.assertTrue(all(c[1] == 'single-native-session' for c in backend.calls[1:]))
        self.assertEqual(backend.stops, 1)
        self.assertIn('上一阶段 sprint1/development 已结束', backend.calls[4][2])
        self.assertIn('SDLC_STAGE_ID: sprint1/deploy', backend.calls[4][2])

    async def test_failure_revises_design_but_keeps_original_cases(self):
        state, backend = await self.run_case()
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(len(backend.calls), 11)
        self.assertEqual([c[0] for c in backend.calls[6:]], [
            'sprint2/triage', 'sprint2/tech-design',
            'sprint2/development', 'sprint2/deploy', 'sprint2/qa'])
        accepted = self.root / 'control/accepted'
        self.assertEqual(json.loads((accepted / 'sprint1/qa/test-verify.json').read_text())['verdict'], 'fail')
        self.assertEqual(json.loads((accepted / 'sprint2/qa/test-verify.json').read_text())['verdict'], 'pass')
        self.assertIn('/workspace/artifacts/sprint2/tech-design/backend-design.md', backend.calls[8][2])
        self.assertIn('/workspace/artifacts/sprint1/qa/test-report.1.md', backend.calls[8][2])
        self.assertEqual(sum('/test-design' in call[0] for call in backend.calls), 1)
        self.assertFalse((accepted / 'sprint2/test-design').exists())
        case_ref = 'artifact:sprint1/test-design/test_cases'
        first_hash = state['stages'][5]['input_sha256'][case_ref]
        self.assertEqual(first_hash, state['stages'][-1]['input_sha256'][case_ref])
        self.assertIn('/workspace/artifacts/sprint1/test-design/test-cases.v1.csv', backend.calls[-1][2])

    async def test_unchanged_design_reused_without_agent_turn(self):
        state, backend = await self.run_case(scenario='repair-reuse')
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(len(backend.calls), 10)
        self.assertEqual(backend.reused, ['sprint2/tech-design'])
        accepted = self.root / 'control/accepted'
        self.assertFalse((accepted / 'sprint2/test-design').exists())
        self.assertEqual(state['stages'][7]['reused_from'], 'sprint1/tech-design')

    async def test_baseline_binds_original_artifacts_through_repair(self):
        from runtime.workflow_controller import digest
        state, backend = await self.run_case()
        control = self.root / 'control'
        baseline = json.loads((control / 'baseline.json').read_text())
        self.assertEqual(baseline['version'], 1)
        self.assertEqual(set(baseline['artifacts']), {
            'artifact:sprint1/prd/prd', 'artifact:sprint1/test-design/test_cases'})
        self.assertEqual(state['baseline_sha256'], digest(control / 'baseline.json'))
        for ref, entry in baseline['artifacts'].items():
            source = control / 'accepted' / Path(entry['path']).relative_to('/workspace/artifacts')
            self.assertEqual(entry['sha256'], digest(source))
            for stage in state['stages']:
                if ref in stage.get('input_sha256', {}):
                    self.assertEqual(stage['input_sha256'][ref], entry['sha256'])

    async def test_baseline_tampering_is_terminal_even_on_tool_error(self):
        scenarios = [('prd', 'sprint1/tech-design', False),
                     ('cases', 'sprint1/qa', False),
                     ('cases', 'sprint1/development', True),
                     ('manifest', 'sprint2/development', False)]
        for target, stage_id, tool_error in scenarios:
            with self.subTest(target=target, stage=stage_id):
                control = self.root / (target + stage_id.replace('/', '-') + str(tool_error))
                backend = LifecycleBackend(self.workspace)
                original = backend.execute

                async def execute(stage, prompt, instruction, session, stage_dir):
                    result = await original(stage, prompt, instruction, session, stage_dir)
                    if stage['stage_id'] == stage_id:
                        paths = {'prd': 'accepted/sprint1/prd/prd.md',
                                 'cases': 'accepted/sprint1/test-design/test-cases.v1.csv',
                                 'manifest': 'baseline.json'}
                        path = control / paths[target]
                        if tool_error:
                            path.unlink()
                            raise RuntimeError('Tool failed after removing baseline')
                        path.write_text(path.read_text() + '\nchanged\n')
                    return result

                with patch.object(backend, 'execute', execute):
                    with self.assertRaisesRegex(RuntimeError, 'Baseline integrity check failed'):
                        await Controller(self.config, self.workspace, control, backend).run()
                state = json.loads((control / 'state.json').read_text())
                self.assertEqual(state['status'], 'failed')
                self.assertEqual(backend.calls[-1][0], stage_id)
                self.assertEqual(sum(call[0] == stage_id for call in backend.calls), 1)

    async def test_container_baseline_rejects_changed_missing_or_linked_files(self):
        import subprocess
        from runtime.workflow_agent import HarborBackend
        from runtime.workflow_controller import digest
        backend = object.__new__(HarborBackend)

        async def root(command):
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr)

        backend.root = root
        source = self.root.resolve() / 'baseline-prd.md'
        source.write_text('frozen')
        entries = {'prd': {'path': str(source), 'sha256': digest(source)}}
        await backend.verify_baseline(entries)
        source.write_text('changed')
        with self.assertRaises(RuntimeError):
            await backend.verify_baseline(entries)
        source.unlink()
        with self.assertRaises(RuntimeError):
            await backend.verify_baseline(entries)
        replacement = self.root / 'replacement.md'
        replacement.write_text('frozen')
        source.symlink_to(replacement)
        with self.assertRaises(RuntimeError):
            await backend.verify_baseline(entries)

    async def test_second_failure_is_terminal_with_accepted_report(self):
        state, backend = await self.run_case(scenario='fail')
        self.assertEqual(state['status'], 'qa_failed')
        self.assertEqual(state['stages'][-1]['status'], 'accepted')
        self.assertEqual(state['cursor'], 11)
        self.assertEqual(len(backend.calls), 11)
        self.assertEqual(backend.stops, 1)

    async def test_unreadable_routing_stops_without_retry(self):
        backend = LifecycleBackend(self.workspace, scenario='pass', bad_routing=True)
        with self.assertRaisesRegex(RuntimeError, 'Cannot route stage'):
            await Controller(self.config, self.workspace, self.root / 'control', backend).run()
        self.assertEqual(sum(c[0] == 'sprint1/qa' for c in backend.calls), 1)
        state = json.loads((self.root / 'control/state.json').read_text())
        self.assertEqual(state['stages'][-1]['status'], 'failed')
        self.assertNotIn('outputs', state['stages'][-1])
        self.assertFalse(any(c[0].startswith('sprint2/') for c in backend.calls))

    async def test_unready_deployment_never_advances_to_qa(self):
        backend = LifecycleBackend(self.workspace, bad_deploy=True)
        with self.assertRaises(RuntimeError):
            await Controller(self.config, self.workspace, self.root / 'control', backend).run()
        self.assertFalse(any(c[0].endswith('/qa') for c in backend.calls))
        self.assertEqual(sum(c[0] == 'sprint1/deploy' for c in backend.calls), 1)
        self.assertEqual(backend.stops, 1)
        self.assertEqual(json.loads((self.root / 'control/state.json').read_text())['status'], 'failed')

    async def test_session_change_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'session changed'):
            await self.run_case(switch_session=True)
        state = json.loads((self.root / 'control/state.json').read_text())
        self.assertEqual(state['status'], 'failed')
        self.assertEqual(state['cursor'], 1)

    async def test_document_format_does_not_trigger_retry_or_output_copy(self):
        state, backend = await self.run_case(scenario='pass', freeform_prd=True)
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(len(backend.calls), 6)
        self.assertEqual(state['stages'][0]['outputs']['prd.md'], state['stages'][1]['prd_input_sha256'])
        self.assertFalse((self.root / 'control/attempts').exists())
        for stage in state['stages']:
            self.assertNotIn('attempts', stage)
            logs = self.root / 'control/stages' / stage['id']
            self.assertTrue((logs / 'instruction.md').is_file())
            self.assertFalse((logs / 'outputs').exists())
        self.assertNotIn('gate_rejected', (self.root / 'control/events.jsonl').read_text())

    async def test_missing_output_stops_without_retry(self):
        backend = LifecycleBackend(self.workspace)
        original = backend.execute
        async def execute(*args):
            result = await original(*args)
            (backend.candidate / 'prd.md').unlink()
            return result
        with patch.object(backend, 'execute', execute):
            with self.assertRaisesRegex(RuntimeError, 'Missing regular output'):
                await Controller(self.config, self.workspace, self.root / 'control', backend).run()
        self.assertEqual(len(backend.calls), 1)
        state = json.loads((self.root / 'control/state.json').read_text())
        self.assertEqual(state['status'], 'failed')
        self.assertNotIn('outputs', state['stages'][0])

    async def test_existing_state_cannot_be_replayed(self):
        await self.run_case(scenario='pass')
        with self.assertRaisesRegex(ValueError, 'replay'):
            Controller(self.config, self.workspace, self.root / 'control', LifecycleBackend(self.workspace))

    def test_unsupported_modes_rejected(self):
        for mode in ('flat', 'hierarchical'):
            config = {**self.config, 'mode': mode}
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                Controller(config, self.workspace, self.root / 'control', LifecycleBackend(self.workspace))

    def test_unsafe_round_and_reuse_policies_fail_at_compile_time(self):
        task = HERE / 'tasks/saleor-prd-tdd'
        base = task / 'workflows'
        run = read_yaml(base / 'single.yaml')
        run.update(task_root=str(task), contract='contract.yaml')
        config_path = self.root / 'single.yaml'
        config_path.write_text(yaml.safe_dump(run))
        original = read_yaml(base / 'lifecycle.yaml')
        for group in ('roles', 'templates', 'inputs'):
            original[group] = {k: str((base / v).resolve()) for k, v in original[group].items()}
        for index, key, value in ((5, 'round', True), (5, 'round', 2),
                                  (5, 'write_repos', True), (8, 'capture_repos', False),
                                  (6, 'reuse_unless', 'design_changed'), (7, 'reuse_stage', 'sprint1/prd')):
            contract = copy.deepcopy(original)
            contract['stages'][index][key] = value
            (self.root / 'contract.yaml').write_text(yaml.safe_dump(contract))
            with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                compile_workflow(config_path, verify_repos=False)

    async def test_routing_uses_only_verdict_and_design_changed(self):
        backend = LifecycleBackend(self.workspace, scenario='fail')
        original = backend.execute
        async def execute(stage, *args):
            result = await original(stage, *args)
            if stage['role'] == 'triage':
                (backend.candidate / 'repair-plan.json').write_text('{"design_changed": false}')
            if stage['role'] == 'qa' and stage['round'] == 2:
                # The report/CSV still say fail. Runtime follows the routing field.
                (backend.candidate / 'test-verify.json').write_text('{"verdict": "pass", "round": 99}')
            return result
        with patch.object(backend, 'execute', execute):
            state = await Controller(self.config, self.workspace, self.root / 'control', backend).run()
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(backend.reused, ['sprint2/tech-design'])
        self.assertEqual(len(backend.calls), 10)

    def test_manifest_rejects_external_healthcheck_and_escaping_cwd(self):
        manifest = {'prepare': [], 'services': [{'name': 'app', 'argv': ['python3', 'app.py'], 'cwd': '/workspace/deployment'}],
                    'healthchecks': ['http://127.0.0.1:8765/']}
        validate_manifest(manifest)
        for url in ('https://example.com', 'http://localhost:80/', 'http://user@127.0.0.1:80/', 'file:///etc/passwd'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_manifest({**manifest, 'healthchecks': [url]})
        bad = copy.deepcopy(manifest)
        bad['services'][0]['cwd'] += '/../repos'
        with self.assertRaises(ValueError):
            validate_manifest(bad)

    def test_missing_or_invalid_routing_fields_fail_clearly(self):
        for role, name, values in (
            ('qa', 'test-verify.json', [{}, [], None, {'verdict': []}, {'verdict': 'unknown'}]),
            ('triage', 'repair-plan.json', [{}, {'design_changed': 'false'}, {'design_changed': 0}]),
        ):
            for value in values:
                with self.subTest(role=role, value=value):
                    (self.root / name).write_text(json.dumps(value))
                    with self.assertRaisesRegex(RuntimeError, 'Cannot route stage'):
                        stage_routing({'role': role, 'stage_id': role}, self.root)

    def test_snapshot_tracks_modes_content_and_rejects_escape(self):
        repos = self.workspace / 'repos'
        p = repos / 'app.py'
        p.write_text('one')
        first = inventory(repos)['sha256']
        p.chmod(0o755)
        self.assertNotEqual(first, inventory(repos)['sha256'])
        first = inventory(repos)['sha256']
        p.write_text('two')
        self.assertNotEqual(first, inventory(repos)['sha256'])
        (repos / 'escape').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'escapes'):
            inventory(repos)


if __name__ == '__main__':
    unittest.main()
