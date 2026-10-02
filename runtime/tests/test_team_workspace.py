from pathlib import Path
import tempfile
import unittest

from runtime.team_workspace import changed, integrate, snapshot


class TeamWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.shared = self.root / "shared"
        self.candidate = self.root / "candidate"
        self.shared.mkdir()
        self.candidate.mkdir()
        (self.shared / "a.txt").write_text("base")
        (self.candidate / "a.txt").write_text("base")

    def test_disjoint_candidate_integrates_and_deletion_is_explicit(self):
        before = snapshot(self.shared)
        (self.candidate / "a.txt").write_text("candidate")
        (self.candidate / "new.txt").write_text("new")
        changes = changed(before, snapshot(self.candidate))
        integrate(self.shared, self.candidate, before, changes)
        self.assertEqual((self.shared / "a.txt").read_text(), "candidate")
        self.assertEqual((self.shared / "new.txt").read_text(), "new")

        second_before = snapshot(self.shared)
        (self.candidate / "a.txt").unlink()
        second_changes = changed(second_before, snapshot(self.candidate))
        integrate(self.shared, self.candidate, second_before, second_changes)
        self.assertFalse((self.shared / "a.txt").exists())

    def test_changed_shared_path_rejects_candidate_without_overwrite(self):
        before = snapshot(self.shared)
        (self.candidate / "a.txt").write_text("candidate")
        changes = changed(before, snapshot(self.candidate))
        (self.shared / "a.txt").write_text("other accepted revision")
        with self.assertRaisesRegex(ValueError, "integration conflict"):
            integrate(self.shared, self.candidate, before, changes)
        self.assertEqual((self.shared / "a.txt").read_text(), "other accepted revision")

    def test_snapshot_accepts_unchanged_internal_symlink_but_rejects_escape(self):
        (self.shared / "link").symlink_to("a.txt")
        with self.assertRaisesRegex(ValueError, "link or nonregular"):
            snapshot(self.shared)
        self.assertEqual(
            snapshot(self.shared, allow_internal_symlinks=True)["link"],
            "symlink:a.txt",
        )
        (self.shared / "escape").symlink_to("../outside")
        with self.assertRaisesRegex(ValueError, "symlink escapes"):
            snapshot(self.shared, allow_internal_symlinks=True)


if __name__ == "__main__":
    unittest.main()
