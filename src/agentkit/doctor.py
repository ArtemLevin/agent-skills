from __future__ import annotations

import subprocess
from pathlib import Path

from .config import load_config
from .executables import resolve_executable, resolve_graphify_executable
from .git import is_git_repository
from .graphify import find_graphify_project_skill


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

    graphify = resolve_graphify_executable()
    project_skill = find_graphify_project_skill(project_root)
    agent_binary = config.agent.command[0] if config and config.agent.command else ""
    agent = resolve_executable(agent_binary) if agent_binary else None
    graphify_command = [str(graphify.path), "--version"] if graphify.path else []
    agent_command = [str(agent.path), "--version"] if agent and agent.path else []

    return {
        "project_root": str(project_root),
        "git_repository": is_git_repository(project_root),
        "config_ok": config_ok,
        "config_error": config_error,
        "graphify": {
            "installed": graphify.found,
            "version": _version(graphify_command) if graphify_command else "unavailable",
            "package_installed": bool(graphify.package_version),
            "package_version": graphify.package_version,
            "executable_found": graphify.found,
            "executable_source": graphify.source,
            "executable": str(graphify.path) if graphify.path else "",
            "project_skill_installed": project_skill is not None,
            "project_skill_path": str(project_skill) if project_skill else "",
            "repair_command": "agentkit graph install --platform agents",
        },
        "agent": {
            "command": agent_binary,
            "installed": bool(agent and agent.found),
            "version": _version(agent_command) if agent_command else "unavailable",
            "executable_source": agent.source if agent else "unavailable",
            "executable": str(agent.path) if agent and agent.path else "",
        },
    }
