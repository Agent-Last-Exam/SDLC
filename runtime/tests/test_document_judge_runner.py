"""Claude Code document Judge process contract; no model calls."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from runtime import document_judge_runner


class DocumentJudgeRunnerTests(unittest.TestCase):
    def test_uses_restricted_claude_structured_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "prompt.md"
            schema = root / "schema.json"
            output = root / "output.json"
            events = root / "events.json"
            stderr = root / "stderr.txt"
            prompt.write_text("Judge this")
            schema.write_text(json.dumps({
                "type": "object", "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
            }))
            captured = {}

            def run(command, **kwargs):
                captured["command"] = command
                captured["kwargs"] = kwargs
                kwargs["stdout"].write(json.dumps({"structured_output": {"ok": True}}))
                kwargs["stdout"].flush()
                return SimpleNamespace(returncode=0)

            argv = [
                "judge", "--model", "claude-opus-4-6", "--cwd", directory,
                "--prompt", str(prompt), "--schema", str(schema),
                "--output", str(output), "--events", str(events),
                "--stderr", str(stderr),
            ]
            with patch("sys.argv", argv), patch.object(
                document_judge_runner.subprocess, "run", side_effect=run
            ):
                self.assertEqual(document_judge_runner.main(), 0)

            command = captured["command"]
            self.assertEqual(command[0], "claude")
            self.assertIn("--restricted", command)
            self.assertIn("--json-schema", command)
            self.assertNotIn("codex", command)
            self.assertEqual(captured["kwargs"]["input"], "Judge this")
            self.assertEqual(json.loads(output.read_text()), {"ok": True})


if __name__ == "__main__":
    unittest.main()
