from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .models import CommandResult


class CommandPolicyError(ValueError):
    """Raised when AgentKit refuses to execute a configured command."""


class CommandPolicy:
    def __init__(self, allowed_executables: list[str], denied_substrings: list[str]) -> None:
        self.allowed = {item.lower() for item in allowed_executables}
        self.denied = [item.lower() for item in denied_substrings]

    def validate(self, command: list[str]) -> None:
        if not command:
            raise CommandPolicyError("Empty command is not allowed")
        executable = Path(command[0]).name.lower()
        if executable.endswith(".exe"):
            executable = executable[:-4]
        if self.allowed and executable not in self.allowed:
            raise CommandPolicyError(f"Executable '{executable}' is not in the allowlist")
        rendered = " ".join(command).lower()
        for fragment in self.denied:
            if fragment and fragment in rendered:
                raise CommandPolicyError(f"Command contains denied fragment: {fragment!r}")


def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    policy: CommandPolicy,
    env: dict[str, str] | None = None,
) -> CommandResult:
    policy.validate(command)
    started = time.monotonic()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=merged_env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        return CommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=time.monotonic() - started,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            duration_seconds=time.monotonic() - started,
            timed_out=True,
        )
