from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .commands import CommandPolicy, run_command
from .config import GraphifyConfig
from .models import CommandResult


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


class GraphifyClient:
    def __init__(
        self,
        project_root: Path,
        config: GraphifyConfig,
        policy: CommandPolicy,
        *,
        timeout_seconds: int = 900,
    ) -> None:
        self.project_root = project_root
        self.config = config
        self.policy = policy
        self.timeout_seconds = timeout_seconds

    @property
    def installed(self) -> bool:
        return shutil.which("graphify") is not None

    def _execute(self, command: list[str]) -> CommandResult:
        return run_command(
            command,
            cwd=self.project_root,
            timeout_seconds=self.timeout_seconds,
            policy=self.policy,
        )

    def update(self) -> CommandResult | None:
        if not self.config.enabled or not self.installed:
            return None
        graph_exists = (self.project_root / "graphify-out" / "graph.json").is_file()
        command = ["graphify", "."]
        if graph_exists:
            command.append("--update")
        if self.config.directed:
            command.append("--directed")
        command.append("--no-viz")
        return self._execute(command)

    def query(self, task: str) -> CommandResult | None:
        if not self.config.enabled or not self.installed:
            return None
        question = (
            "Identify the smallest relevant code subgraph for this engineering task. "
            "Return entry points, direct dependencies, callers, related tests, and uncertain inferred links: "
            + task
        )
        command = [
            "graphify",
            "query",
            question,
            "--budget",
            str(self.config.query_budget),
        ]
        return self._execute(command)

    def build_context(self, task: str) -> GraphContext:
        if not self.config.enabled:
            return GraphContext(False, False, "", "", "Graphify is disabled")
        if not self.installed:
            warning = "Graphify executable is not installed or not on PATH"
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
