from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import load_config
from .git import is_git_repository


def _version(command: list[str]) -> str:
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    text = (result.stdout or result.stderr).strip().splitlines()
    return text[0] if text else f"exit {result.returncode}"


def doctor(project_root: Path) -> dict[str, object]:
    config_ok = True
    config_error = ""
    try:
        config = load_config(project_root)
    except Exception as exc:  # doctor must report all failures in one pass
        config_ok = False
        config_error = str(exc)
        config = None
    agent_binary = config.agent.command[0] if config and config.agent.command else ""
    return {
        "project_root": str(project_root),
        "git_repository": is_git_repository(project_root),
        "config_ok": config_ok,
        "config_error": config_error,
        "graphify": {
            "installed": shutil.which("graphify") is not None,
            "version": _version(["graphify", "--version"]) if shutil.which("graphify") else "unavailable",
        },
        "agent": {
            "command": agent_binary,
            "installed": bool(agent_binary and shutil.which(agent_binary)),
            "version": _version([agent_binary, "--version"]) if agent_binary and shutil.which(agent_binary) else "unavailable",
        },
    }
