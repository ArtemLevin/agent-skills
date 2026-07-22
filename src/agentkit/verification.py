from __future__ import annotations

import shutil
from pathlib import Path

from .commands import CommandPolicy, run_command
from .config import VerificationConfig
from .models import CommandResult


def discover_commands(project_root: Path) -> list[list[str]]:
    commands: list[list[str]] = []
    pyproject = project_root / "pyproject.toml"
    tests = project_root / "tests"
    src = project_root / "src"
    text = pyproject.read_text(encoding="utf-8") if pyproject.is_file() else ""

    if tests.is_dir():
        if "[tool.pytest" in text or "pytest" in text:
            commands.append(["python", "-m", "pytest", "-q"])
        else:
            commands.append(["python", "-m", "unittest", "discover", "-s", "tests", "-v"])
    compile_targets = [path.name for path in (src, tests) if path.exists()]
    if compile_targets:
        commands.append(["python", "-m", "compileall", "-q", *compile_targets])
    if "[tool.ruff" in text and shutil.which("ruff"):
        commands.append(["ruff", "check", "."])
    return commands


def run_checks(
    project_root: Path,
    config: VerificationConfig,
    policy: CommandPolicy,
) -> list[CommandResult]:
    commands = config.commands or discover_commands(project_root)
    return [
        run_command(
            command,
            cwd=project_root,
            timeout_seconds=config.timeout_seconds,
            policy=policy,
        )
        for command in commands
    ]
