from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .commands import CommandPolicy, run_command
from .config import GraphifyConfig
from .executables import ExecutableResolution, resolve_graphify_executable
from .models import CommandResult


CommandObserver = Callable[[str, CommandResult], None]

_GRAPHIFYIGNORE_BEGIN = "# BEGIN AGENTKIT"
_GRAPHIFYIGNORE_END = "# END AGENTKIT"
_GRAPHIFYIGNORE_BLOCK = """# BEGIN AGENTKIT
.agent/
.agents/
graphify-out/
graph.json
# END AGENTKIT"""
_GRAPHIFY_REBUILD_MARKER = Path(".agent/state/graphify-rebuild-required")
_GRAPHIFY_OUTPUT_GRAPH = Path("graphify-out/graph.json")
_ROOT_GRAPH = Path("graph.json")


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


def graphify_rebuild_marker(project_root: Path) -> Path:
    return project_root / _GRAPHIFY_REBUILD_MARKER


def graphify_output_graph_path(project_root: Path) -> Path:
    return project_root / _GRAPHIFY_OUTPUT_GRAPH


def root_graph_path(project_root: Path) -> Path:
    return project_root / _ROOT_GRAPH


def mark_graphify_rebuild_required(project_root: Path) -> Path:
    marker = graphify_rebuild_marker(project_root)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("ignore-policy-changed\n", encoding="utf-8")
    return marker


def ensure_graphify_ignore(project_root: Path) -> bool:
    """Exclude AgentKit's generated control plane and published snapshot from extraction."""

    path = project_root / ".graphifyignore"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if _GRAPHIFYIGNORE_BEGIN in existing:
        if _GRAPHIFYIGNORE_END not in existing:
            raise ValueError(
                ".graphifyignore contains an incomplete AgentKit managed block"
            )
        start = existing.index(_GRAPHIFYIGNORE_BEGIN)
        end = existing.index(_GRAPHIFYIGNORE_END, start) + len(_GRAPHIFYIGNORE_END)
        updated = existing[:start] + _GRAPHIFYIGNORE_BLOCK + existing[end:]
    else:
        separator = "" if not existing or existing.endswith("\n") else "\n"
        updated = existing + separator + _GRAPHIFYIGNORE_BLOCK + "\n"
    if updated == existing:
        return False
    path.write_text(updated, encoding="utf-8", newline="\n")
    mark_graphify_rebuild_required(project_root)
    return True


def _replace_with_retries(source: Path, target: Path, *, attempts: int = 5) -> None:
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt + 1 >= attempts:
                raise
            time.sleep(0.05 * (attempt + 1))


def publish_root_graph(project_root: Path) -> Path:
    """Atomically mirror Graphify's canonical graph into the repository root."""

    source = graphify_output_graph_path(project_root)
    target = root_graph_path(project_root)
    if not source.is_file():
        raise FileNotFoundError(f"Graphify output is missing: {source}")
    if source.stat().st_size == 0:
        raise ValueError(f"Graphify output is empty: {source}")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=project_root,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as destination, source.open("rb") as origin:
            shutil.copyfileobj(origin, destination, length=1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        _replace_with_retries(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _publication_failure(result: CommandResult, error: Exception) -> CommandResult:
    message = f"AgentKit failed to publish root graph.json: {error}"
    stderr = "\n".join(part for part in (result.stderr.strip(), message) if part)
    return CommandResult(
        command=result.command,
        returncode=1,
        stdout=result.stdout,
        stderr=stderr,
        duration_seconds=result.duration_seconds,
        timed_out=result.timed_out,
        usage=result.usage,
    )


def _published_result(result: CommandResult, target: Path) -> CommandResult:
    notice = f"[agentkit] published {target.name}"
    stdout = "\n".join(part for part in (result.stdout.rstrip(), notice) if part)
    return CommandResult(
        command=result.command,
        returncode=result.returncode,
        stdout=stdout,
        stderr=result.stderr,
        duration_seconds=result.duration_seconds,
        timed_out=result.timed_out,
        usage=result.usage,
    )


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
        ensure_graphify_ignore(self.project_root)
        marker = graphify_rebuild_marker(self.project_root)
        rebuild_required = marker.is_file()
        graph_exists = graphify_output_graph_path(self.project_root).is_file()
        command = [self.executable, "."]
        if graph_exists and not rebuild_required:
            command.append("--update")
        if self.config.directed:
            command.append("--directed")
        command.extend(["--code-only", "--no-viz"])
        result = self._execute(command, phase="graph_update")
        if not result.passed:
            return result
        try:
            target = publish_root_graph(self.project_root)
        except (OSError, ValueError) as error:
            return _publication_failure(result, error)
        if rebuild_required:
            marker.unlink(missing_ok=True)
        return _published_result(result, target)

    def query(self, task: str) -> CommandResult | None:
        if not self.config.enabled or not self.installed:
            return None
        question = task.strip()
        if not question:
            raise ValueError("Graphify query requires a non-empty task")
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
