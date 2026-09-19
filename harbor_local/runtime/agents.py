"""Prompt-only adapters; execution, auth and trajectories stay in Harbor 0.20.0."""

import json
import shlex
from pathlib import Path

from harbor.agents.installed.codex import Codex
from harbor.agents.installed.claude_code import ClaudeCode


class PromptMixin:
    REMOTE_PROMPT = "/tmp/sdlc-system-prompt.md"

    def __init__(self, *args, system_prompt_path, prompt_mode="append", **kwargs):
        if prompt_mode not in {"append", "replace"}:
            raise ValueError("prompt_mode must be append or replace")
        self.prompt_mode = prompt_mode
        self.prompt_text = Path(system_prompt_path).read_text(encoding="utf-8")
        if not self.prompt_text.strip():
            raise ValueError("System prompt is empty")
        super().__init__(*args, **kwargs)

    async def setup(self, environment):
        await super().setup(environment)
        # Use the captured bytes, even if the original file changes mid-run.
        snapshot = self.logs_dir / "system-prompt.md"
        snapshot.write_text(self.prompt_text, encoding="utf-8")
        await environment.upload_file(snapshot, self.REMOTE_PROMPT)
        await self.exec_as_root(
            environment, command=f"chmod 644 {shlex.quote(self.REMOTE_PROMPT)}"
        )
        (self.logs_dir / "prompt-config.json").write_text(
            json.dumps({"mode": self.prompt_mode, "adapter": type(self).__name__}, indent=2)
            + "\n"
        )


class PromptCodex(PromptMixin, Codex):
    def build_cli_flags(self):
        flags = super().build_cli_flags()
        if self.prompt_mode == "replace":
            value = "model_instructions_file=" + json.dumps(self.REMOTE_PROMPT)
        else:
            value = "developer_instructions=" + json.dumps(self.prompt_text, ensure_ascii=False)
        return flags + " -c " + shlex.quote(value)


class PromptClaudeCode(PromptMixin, ClaudeCode):
    def build_cli_flags(self):
        flags = super().build_cli_flags()
        option = "--system-prompt" if self.prompt_mode == "replace" else "--append-system-prompt"
        return flags + " " + option + " " + shlex.quote(self.prompt_text)
