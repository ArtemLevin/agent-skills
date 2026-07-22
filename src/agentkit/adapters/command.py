from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from agentkit.commands import CommandPolicy, run_command
from agentkit.models import CommandResult
from agentkit.telemetry import parse_token_usage

from .base import AgentAdapter


class CommandAgentAdapter(AgentAdapter):
    """Invoke any coding-agent CLI through a configurable argv template."""

    def __init__(
        self,
        command_template: list[str],
        *,
        timeout_seconds: int,
        policy: CommandPolicy,
        provider: str = "custom",
    ) -> None:
        if not command_template:
            raise ValueError("Agent command template cannot be empty")
        self.command_template = command_template
        self.timeout_seconds = timeout_seconds
        self.policy = policy
        self.provider = provider

    def render(self, prompt: str, phase: str) -> list[str]:
        rendered: list[str] = []
        prompt_inserted = False
        for part in self.command_template:
            if "{prompt}" in part:
                rendered.append(part.replace("{prompt}", prompt))
                prompt_inserted = True
            else:
                rendered.append(part.replace("{phase}", phase))
        if not prompt_inserted:
            rendered.append(prompt)
        return rendered

    def execute(self, prompt: str, *, phase: str, cwd: Path) -> CommandResult:
        result = run_command(
            self.render(prompt, phase),
            cwd=cwd,
            timeout_seconds=self.timeout_seconds,
            policy=self.policy,
        )
        usage = parse_token_usage(result.stdout, result.stderr)
        return replace(result, usage=usage)
