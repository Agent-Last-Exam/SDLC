"""Validate native instruction injection without making model requests."""

from pathlib import Path
import shlex
import tempfile
import unittest

from runtime.agents import PromptClaudeCode
from runtime.environment import load_env


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.text = '中文 "quotes" \'single\'\n$(touch /tmp/never) `echo never` \\ path\n'
        self.prompt = self.root / "prompt.md"
        self.prompt.write_text(self.text)

    def adapter(self, cls, mode):
        return cls(logs_dir=self.root / "logs", model_name="test-model",
                   system_prompt_path=self.prompt, prompt_mode=mode)

    def test_claude_prompt_modes_preserve_literal_content(self):
        for mode, option in [("append", "--append-system-prompt"), ("replace", "--system-prompt")]:
            with self.subTest(mode=mode):
                tokens = shlex.split(self.adapter(PromptClaudeCode, mode).build_cli_flags())
                self.assertEqual(tokens[tokens.index(option) + 1], self.text)
                self.assertEqual(
                    tokens[tokens.index("--system-prompt-snapshot") + 1], "off"
                )

    def test_env_file_is_literal_and_blank_entries_preserve_exports(self):
        path = self.root / ".env"
        path.write_text('ANTHROPIC_API_KEY=\nCLAUDE_MODEL="test-model"\nLITERAL=\'$(echo nope) `echo nope`\'\n')
        env = {"ANTHROPIC_API_KEY": "already-exported"}
        load_env(path, env)
        self.assertEqual(env["ANTHROPIC_API_KEY"], "already-exported")
        self.assertEqual(env["LITERAL"], "$(echo nope) `echo nope`")
        self.assertEqual(env["CLAUDE_MODEL"], "test-model")


if __name__ == "__main__":
    unittest.main()
