"""Candidate materialization and ownership cleanup regressions; no model calls."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from runtime.local_deployment import materialize, validate_manifest
from runtime.workspace_cleanup import cleanup_owned
from runtime.workspace_snapshot import inventory


class DeploymentBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'version.txt').write_text('1')
        self.release = self.root / 'deployment'

    def test_materialization_replaces_stale_source_and_build_outputs(self):
        first = inventory(self.source)['sha256']
        materialize(self.source, self.release, first)
        (self.release / 'old-build').write_text('old executable')
        (self.source / 'version.txt').write_text('2')
        second = inventory(self.source)['sha256']
        binding = materialize(self.source, self.release, second)
        self.assertNotEqual(first, second)
        self.assertEqual(binding['candidate_sha256'], second)
        self.assertEqual(inventory(self.release / 'repos')['sha256'], second)
        self.assertEqual((self.release / 'repos/version.txt').read_text(), '2')
        self.assertFalse((self.release / 'old-build').exists())
        # Agent preparation can change the copy; materialization must replace it.
        (self.release / 'repos/version.txt').write_text('broken preparation')
        materialize(self.source, self.release, second)
        self.assertEqual((self.release / 'repos/version.txt').read_text(), '2')

    def test_unaccepted_source_cannot_receive_current_candidate_identity(self):
        accepted = inventory(self.source)['sha256']
        (self.source / 'version.txt').write_text('unaccepted')
        with self.assertRaisesRegex(ValueError, 'accepted candidate'):
            materialize(self.source, self.release, accepted)
        self.assertFalse(self.release.exists())

    def test_old_release_symlink_cannot_redirect_materialization(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'keep').write_text('keep')
        self.release.symlink_to(outside, target_is_directory=True)
        materialize(self.source, self.release, inventory(self.source)['sha256'])
        self.assertFalse(self.release.is_symlink())
        self.assertEqual((outside / 'keep').read_text(), 'keep')

    def test_cleanup_preserves_service_resources_even_under_stage_parent(self):
        scratch = self.root / 'tmp'
        scratch.mkdir()
        mixed = scratch / 'mixed'
        mixed.mkdir()
        retired = mixed / 'stage-file'
        retired.touch()
        service = mixed / 'service-shared-memory'
        service.write_text('live')
        root_owned = scratch / 'root-file'
        root_owned.touch()
        link = scratch / 'stage-link'
        link.symlink_to(self.source, target_is_directory=True)
        original = Path.lstat
        owners = {mixed: 1201, retired: 1201, service: 1800, root_owned: 0, link: 1201}

        def stat_with_owner(path):
            info = original(path)
            return SimpleNamespace(st_mode=info.st_mode, st_uid=owners[path])

        with patch.object(Path, 'lstat', stat_with_owner):
            cleanup_owned([scratch], [1201])
        self.assertEqual(service.read_text(), 'live')
        self.assertTrue(root_owned.exists())
        self.assertFalse(retired.exists())
        self.assertFalse(link.is_symlink())
        self.assertTrue((self.source / 'version.txt').exists())

    def test_preparation_cannot_use_stage_scratch_or_malformed_commands(self):
        manifest = {'prepare': [], 'services': [{'name': 'app', 'argv': ['python3', 'app.py'],
                    'cwd': '/workspace/deployment/repos'}], 'healthchecks': ['http://127.0.0.1:8000/']}
        for command in ({'argv': ['true'], 'cwd': '/workspace/scratch'},
                        {'argv': [], 'cwd': '/workspace/deployment'}, {'shell': 'true'}):
            with self.subTest(command=command), self.assertRaises(ValueError):
                validate_manifest({**manifest, 'prepare': [command]})


if __name__ == '__main__':
    unittest.main()
