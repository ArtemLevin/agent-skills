from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .commands import CommandPolicy, run_command
from .config import GraphifyConfig
from .executables import ExecutableResolution, resolve_graphify_executable
from .models import CommandResult


CommandObserver = Callable[[str, CommandResult], None]


@dataclass(frozen=True)
class GraphContext:
    available: bool
    updated: bool
    query: str
    output: str
    warning: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "updated": self.updated,
            "query": self.query,
            "output": self.output,
            "warning": self.warning,
        }


def graphify_project_skill_path(project_root: Path, platform: str = "agents") -> Path:
    normalized = platform.strip().lower().lstrip(".") or "agents"
    return project_root / f".{normalized}" / "skills" / "graphify"


def find_graphify_project_skill(project_root: Path) -> Path | None:
    preferred = graphify_project_skill_path(project_root, "agents")
    if preferred.is_dir():
        return preferred
    for parent in sorted(project_root.glob(".*")):
        candidate = parent / "skills" / "graphify"
        if candidate.is_dir():
            return candidate
    return None


def _graphify_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.setdefault("PYTHONUTF8", "1")
    environment.setdefault("PYTHONIOENCODING", "utf-8")
    return environment


def install_graphify_project_skill(
    project_root: Path,
    *,
    platform: str = "agents",
    required: bool = False,
    resolution: ExecutableResolution | None = None,
) -> dict[str, object]:
    resolved = resolution or resolve_graphify_executable()
    expected = graphify_project_skill_path(project_root, platform)
    if not resolved.found or resolved.path is None:
        payload: dict[str, object] = {
            "attempted": False,
            "installed": expected.is_dir(),
            "platform": platform,
            "project_skill_path": str(expected),
            "executable": resolved.to_dict(),
            "reason": "graphify executable not found",
            "repair_command": f"agentkit graph install --platform {platform}",
        }
        if required:
            raise RuntimeError(
                "Graphify is installed as an AgentKit dependency but its executable could not "
                "be resolved. Reinstall AgentKit or run the repair command after fixing the "
                "installation."
            )
        return payload

    result = subprocess.run(
        [
            str(resolved.path),
            "install",
            "--project",
            "--platform",
            platform,
        ],
        cwd=project_root,
        env=_graphify_environment(),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    payload = {
        "attempted": True,
        "installed": result.returncode == 0,
        "platform": platform,
        "project_skill_path": str(expected),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "executable": resolved.to_dict(),
        "repair_command": f"agentkit graph install --platform {platform}",
    }
    if result.returncode != 0 and required:
        details = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"Graphify project skill installation failed: {details}")
    return payload


class GraphifyClient:
    def __init__(
        self,
        project_root: Path,
        config: GraphifyConfig,
        policy: CommandPolicy,
        *,
        timeout_seconds: int = 900,
        observer: CommandObserver | None = None,
        resolution: ExecutableResolution | None = None,
    ) -> None:
        self.project_root = project_root
        self.config = config
        self.policy = policy
        self.timeout_seconds = timeout_seconds
        self.observer = observer
        self.resolution = resolution or resolve_graphify_executable()

    @property
    def installed(self) -> bool:
        return self.resolution.found

    @property
    def executable(self) -> str:
        if self.resolution.path is None:
            raise RuntimeError("Graphify executable is unavailable")
        return str(self.resolution.path)

    def _execute(self, command: list[str], *, phase: str) -> CommandResult:
        result = run_command(
            command,
            cwd=self.project_root,
            timeout_seconds=self.timeout_seconds,
            policy=self.policy,
            env={
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
            },
            encoding="utf-8",
            errors="replace",
        )
        if self.observer is not None:
            self.observer(phase, result)
        return result

    def update(self) -> CommandResult | None:
        if not self.config.enabled or not self.installed:
            return None
        graph_exists = (self.project_root / "graphify-out" / "graph.json").is_file()
        command = [self.executable, "."]
        if graph_exists:
            command.append("--update")
        if self.config.directed:
            command.append("--directed")
        command.extend(["--code-only", "--no-viz"])
        return self._execute(command, phase="graph_update")

    def query(self, task: str) -> CommandResult | None:
        if not self.config.enabled or not self.installed:
            return None
        question = (
            "Identify the smallest relevant code subgraph for this engineering task. "
            "Return entry points, direct dependencies, callers, related tests, and uncertain inferred links: "
            + task
        )
        command = [
            self.executable,
            "query",
            question,
            "--budget",
            str(self.config.query_budget),
        ]
        return self._execute(command, phase="graph_query")

    def build_context(self, task: str) -> GraphContext:
        if not self.config.enabled:
            return GraphContext(False, False, "", "", "Graphify is disabled")
        if not self.installed:
            warning = (
                "Graphify executable is unavailable; run "
                "`agentkit graph install --platform agents` after repairing the installation"
            )
            if self.config.required:
                raise RuntimeError(warning)
            return GraphContext(False, False, "", "", warning)
        update_result = self.update()
        if update_result is None or not update_result.passed:
            details = update_result.stderr.strip() if update_result else "update was not executed"
            if self.config.required:
                raise RuntimeError(f"Graphify update failed: {details}")
            return GraphContext(True, False, "", "", f"Graphify update failed: {details}")
        query_result = self.query(task)
        if query_result is None or not query_result.passed:
            details = query_result.stderr.strip() if query_result else "query was not executed"
            if self.config.required:
                raise RuntimeError(f"Graphify query failed: {details}")
            return GraphContext(True, True, "", "", f"Graphify query failed: {details}")
        return GraphContext(True, True, "task-scoped query", query_result.stdout.strip())
