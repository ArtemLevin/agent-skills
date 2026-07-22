from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from agentkit.config import load_config
from agentkit.init_project import initialize_project
from agentkit.model_runtime import ModelRoutingRunner
from agentkit.models import RunMode
from agentkit.runner import RunRequest

from .collector import (
    collect_correctness,
    collect_efficiency,
    collect_quality,
    run_acceptance_commands,
)
from .config import EvaluationConfig
from .manifest import load_manifest, manifest_fingerprint
from .models import EvaluationManifest, EvaluationRunResult, EvaluationSummary
from .reports import aggregate_runs, render_summary_markdown, write_json


@dataclass(frozen=True)
class EvaluationExecution:
    source_run_id: str
    exit_code: int
    source_run_directory: Path | None
    error: str = ""


Executor = Callable[[Path, EvaluationManifest], EvaluationExecution]


def _safe_id(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in value.lower())
    cleaned = cleaned.strip(".-")
    return cleaned[:128] or "evaluation"


def new_evaluation_id(task_id: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{_safe_id(task_id)}-{stamp}-{uuid4().hex[:8]}"


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.is_dir():
        raise FileNotFoundError(f"Fixture directory does not exist: {root}")
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        parts = relative.parts
        if ".git" in parts or "__pycache__" in parts:
            continue
        if len(parts) >= 3 and parts[:3] == (".agent", "state", "runs"):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _run_git(workspace: Path, *args: str) -> None:
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "AgentKit Evaluation",
            "GIT_AUTHOR_EMAIL": "agentkit-eval@example.invalid",
            "GIT_COMMITTER_NAME": "AgentKit Evaluation",
            "GIT_COMMITTER_EMAIL": "agentkit-eval@example.invalid",
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
        }
    )
    result = subprocess.run(
        ["git", *args],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}"
        )


def prepare_workspace(source: Path, workspace: Path) -> None:
    if workspace.exists():
        raise RuntimeError(f"Evaluation workspace already exists: {workspace}")
    shutil.copytree(
        source,
        workspace,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".agent/state"),
    )
    config = workspace / ".agent" / "agentkit.toml"
    if not config.is_file():
        initialize_project(
            workspace,
            force=False,
            platform="agents",
            install_graphify_skill=False,
        )
    _run_git(workspace, "init", "-q")
    _run_git(workspace, "add", "--all")
    _run_git(workspace, "commit", "-q", "-m", "AgentKit evaluation fixture baseline")


def _copy_agent_artifacts(source: Path | None, target: Path) -> Path | None:
    if source is None or not source.is_dir():
        return None
    target.mkdir(parents=True, exist_ok=True)
    allowed = {
        "completion.json",
        "review.json",
        "verification.json",
        "usage.json",
        "budget.json",
        "task-packet.json",
        "quality-before.json",
        "quality-after.json",
        "quality-diff.json",
        "quality-gate.json",
        "quality-route.json",
        "verification-plan.json",
        "context.json",
        "model-route.json",
        "model-attempts.json",
    }
    for path in source.iterdir():
        if path.is_file() and (
            path.name in allowed
            or path.name.startswith("verification-after-fix-")
            or path.name.startswith("prompt-prefix-")
        ):
            shutil.copy2(path, target / path.name)
    return target


class EvaluationHarness:
    def __init__(
        self,
        project_root: Path,
        config: EvaluationConfig,
        *,
        executor: Executor | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.config = config
        self.executor = executor or self._default_executor

    def _fixture(self, manifest: EvaluationManifest) -> Path:
        path = (self.project_root / manifest.repository_fixture).resolve()
        try:
            path.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError("Evaluation fixture must remain inside the project root") from exc
        if not path.is_dir():
            raise FileNotFoundError(f"Evaluation fixture does not exist: {path}")
        return path

    @staticmethod
    def _default_executor(workspace: Path, manifest: EvaluationManifest) -> EvaluationExecution:
        config = load_config(workspace)
        route = manifest.experiment.get("model_route")
        request = RunRequest(
            task=manifest.task,
            mode=RunMode(manifest.mode),
            approve_deep=True,
            skip_graph=manifest.experiment.get("graphify") is False,
            route_override=str(route) if route else None,
        )
        outcome = ModelRoutingRunner(workspace, config=config).run(request)
        directory = workspace / ".agent" / "state" / "runs" / outcome.run_id
        return EvaluationExecution(
            source_run_id=outcome.run_id,
            exit_code=outcome.exit_code,
            source_run_directory=directory,
        )

    def _evaluation_directory(self, evaluation_id: str) -> Path:
        path = self.project_root / ".agent" / "evals" / _safe_id(evaluation_id)
        if path.exists():
            raise RuntimeError(f"Evaluation already exists: {path}")
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _run_once(
        self,
        manifest: EvaluationManifest,
        *,
        evaluation_id: str,
        evaluation_directory: Path,
        ordinal: int,
        keep_workspace: bool,
    ) -> tuple[EvaluationRunResult, str]:
        run_id = f"run-{ordinal:03d}"
        run_directory = evaluation_directory / "runs" / run_id
        workspace = run_directory / "workspace"
        run_directory.mkdir(parents=True, exist_ok=False)
        fixture = self._fixture(manifest)
        before_hash = tree_hash(fixture)
        warnings: list[str] = []
        execution = EvaluationExecution("", 2, None, "evaluation did not execute")
        commands = ()
        correctness = None
        efficiency = None
        quality = None
        changed: tuple[str, ...] = ()
        try:
            prepare_workspace(fixture, workspace)
            execution = self.executor(workspace, manifest)
            source_artifacts = _copy_agent_artifacts(
                execution.source_run_directory,
                run_directory / "agent-run",
            )
            workspace_config = load_config(workspace)
            commands = run_acceptance_commands(
                workspace,
                manifest,
                workspace_config,
                timeout_seconds=self.config.command_timeout_seconds,
            )
            correctness, changed, correctness_warnings = collect_correctness(
                workspace,
                source_artifacts,
                manifest,
                commands,
            )
            warnings.extend(correctness_warnings)
            efficiency = collect_efficiency(source_artifacts)
            quality = collect_quality(source_artifacts)
            if execution.error:
                warnings.append(execution.error)
        except Exception as exc:
            warnings.append(str(exc))
            from .models import CorrectnessMetrics, EfficiencyMetrics, QualityMetrics

            correctness = CorrectnessMetrics()
            efficiency = EfficiencyMetrics()
            quality = QualityMetrics()
            execution = EvaluationExecution(
                source_run_id=execution.source_run_id,
                exit_code=2,
                source_run_directory=None,
                error=str(exc),
            )

        after_hash = tree_hash(fixture)
        fixture_preserved = before_hash == after_hash
        if not fixture_preserved:
            warnings.append("Source fixture changed during evaluation")

        quality_expectation_passed = (
            quality.new_critical_hotspots
            <= manifest.quality.allow_new_critical_hotspots
        )
        if not quality_expectation_passed:
            warnings.append(
                "New critical hotspots exceeded manifest allowance: "
                f"{quality.new_critical_hotspots} > "
                f"{manifest.quality.allow_new_critical_hotspots}"
            )
        budget_passed = True
        if (
            manifest.budget.max_agent_calls is not None
            and efficiency.agent_calls > manifest.budget.max_agent_calls
        ):
            budget_passed = False
            warnings.append("Agent-call evaluation budget was exceeded")
        if (
            manifest.budget.max_duration_seconds is not None
            and efficiency.duration_seconds > manifest.budget.max_duration_seconds
        ):
            budget_passed = False
            warnings.append("Duration evaluation budget was exceeded")

        passed = bool(
            execution.exit_code == 0
            and correctness.acceptance_passed
            and correctness.ready_for_review
            and correctness.blocking_findings == 0
            and correctness.scope_violations == 0
            and fixture_preserved
            and quality_expectation_passed
            and budget_passed
            and quality.gate_allowed is not False
        )
        status = "passed" if passed else "error" if execution.error else "failed"
        result = EvaluationRunResult(
            evaluation_id=evaluation_id,
            task_id=manifest.id,
            run_id=run_id,
            status=status,
            source_run_id=execution.source_run_id,
            agent_exit_code=execution.exit_code,
            correctness=correctness,
            efficiency=efficiency,
            quality=quality,
            acceptance_commands=commands,
            changed_files=changed,
            warnings=tuple(dict.fromkeys(warnings)),
            fixture_hash=before_hash,
            fixture_preserved=fixture_preserved,
            experiment=manifest.experiment,
        )
        result_path = write_json(run_directory / "result.json", result.to_dict())
        if not keep_workspace:
            shutil.rmtree(workspace, ignore_errors=True)
        return result, str(result_path.relative_to(evaluation_directory))

    def run_manifest(
        self,
        manifest_path: Path,
        *,
        repetitions: int | None = None,
        evaluation_id: str | None = None,
        keep_workspaces: bool | None = None,
    ) -> tuple[EvaluationSummary, Path]:
        manifest = load_manifest(manifest_path)
        count = repetitions if repetitions is not None else manifest.repetitions
        if count <= 0 or count > self.config.max_repetitions:
            raise ValueError(
                f"Evaluation repetitions must be between 1 and {self.config.max_repetitions}"
            )
        selected_id = evaluation_id or new_evaluation_id(manifest.id)
        directory = self._evaluation_directory(selected_id)
        keep = self.config.keep_workspaces if keep_workspaces is None else keep_workspaces
        manifest_payload = manifest.to_dict() | {
            "manifest_path": str(manifest_path),
            "manifest_fingerprint": manifest_fingerprint(manifest),
        }
        write_json(directory / "manifest.json", manifest_payload)
        results: list[EvaluationRunResult] = []
        paths: list[str] = []
        for ordinal in range(1, count + 1):
            result, path = self._run_once(
                manifest,
                evaluation_id=selected_id,
                evaluation_directory=directory,
                ordinal=ordinal,
                keep_workspace=keep,
            )
            results.append(result)
            paths.append(path)
        summary = aggregate_runs(
            selected_id,
            results,
            kind="task",
            run_results=tuple(paths),
        )
        write_json(directory / "summary.json", summary.to_dict())
        (directory / "summary.md").write_text(
            render_summary_markdown(summary), encoding="utf-8"
        )
        return summary, directory

    def run_suite(
        self,
        manifest_directory: Path,
        *,
        repetitions: int | None = None,
        smoke_only: bool = False,
        evaluation_id: str | None = None,
        keep_workspaces: bool | None = None,
    ) -> tuple[EvaluationSummary, Path]:
        paths = sorted(
            path
            for path in manifest_directory.iterdir()
            if path.is_file() and path.suffix.lower() in {".yaml", ".yml", ".json"}
        )
        manifests = [(path, load_manifest(path)) for path in paths]
        if smoke_only:
            manifests = [item for item in manifests if item[1].smoke]
        if not manifests:
            raise FileNotFoundError("No matching evaluation manifests were found")
        selected_id = evaluation_id or new_evaluation_id("suite")
        directory = self._evaluation_directory(selected_id)
        write_json(
            directory / "manifest.json",
            {
                "version": 1,
                "kind": "suite",
                "evaluation_id": selected_id,
                "smoke_only": smoke_only,
                "manifests": [
                    {
                        "path": str(path),
                        "manifest": manifest.to_dict(),
                        "fingerprint": manifest_fingerprint(manifest),
                    }
                    for path, manifest in manifests
                ],
            },
        )
        all_results: list[EvaluationRunResult] = []
        result_paths: list[str] = []
        ordinal = 0
        keep = self.config.keep_workspaces if keep_workspaces is None else keep_workspaces
        for _path, manifest in manifests:
            count = repetitions if repetitions is not None else manifest.repetitions
            if count <= 0 or count > self.config.max_repetitions:
                raise ValueError(
                    f"Evaluation repetitions must be between 1 and {self.config.max_repetitions}"
                )
            for _ in range(count):
                ordinal += 1
                result, result_path = self._run_once(
                    manifest,
                    evaluation_id=selected_id,
                    evaluation_directory=directory,
                    ordinal=ordinal,
                    keep_workspace=keep,
                )
                all_results.append(result)
                result_paths.append(result_path)
        summary = aggregate_runs(
            selected_id,
            all_results,
            kind="suite",
            run_results=tuple(result_paths),
        )
        write_json(directory / "summary.json", summary.to_dict())
        (directory / "summary.md").write_text(
            render_summary_markdown(summary), encoding="utf-8"
        )
        return summary, directory
