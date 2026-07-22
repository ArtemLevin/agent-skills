from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from agentkit.commands import CommandPolicy, run_command
from agentkit.config import AgentKitConfig
from agentkit.models import CommandResult
from agentkit.telemetry import UsageLedger

from .ci_config import QualityCIConfig
from .ci_summary import render_quality_summary
from .config import QualityConfig
from .lifecycle import QualityCycleResult, QualityLifecycle


@dataclass(frozen=True)
class RepositoryComparison:
    base_ref: str
    head: str
    base_commit: str
    merge_base: str
    dirty: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class QualityCIResult:
    run_id: str
    status: str
    base_ref: str
    merge_base: str
    gate_allowed: bool
    exit_code: int
    run_directory: str
    artifact_directory: str
    summary_path: str
    warnings: tuple[str, ...] = ()
    version: int = 1

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["warnings"] = list(self.warnings)
        return data


def new_ci_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"ci-quality-{stamp}-{uuid4().hex[:8]}"


class QualityCIRunner:
    def __init__(
        self,
        project_root: Path,
        core_config: AgentKitConfig,
        quality_config: QualityConfig,
        ci_config: QualityCIConfig,
    ) -> None:
        self.project_root = project_root
        self.core_config = core_config
        self.quality_config = quality_config
        self.ci_config = ci_config
        self.policy = CommandPolicy(
            core_config.security.allowed_executables,
            core_config.security.denied_substrings,
        )

    def _execute(self, command: list[str], *, phase: str) -> CommandResult:
        return run_command(
            command,
            cwd=self.project_root,
            timeout_seconds=self.quality_config.timeout_seconds,
            policy=self.policy,
        )

    def _git_text(self, *args: str, description: str) -> str:
        result = self._execute(["git", *args], phase="quality_ci_git")
        if not result.passed:
            details = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"{description}: {details or 'git command failed'}")
        return result.stdout.strip()

    def inspect_repository(self, base_ref: str) -> RepositoryComparison:
        inside = self._git_text(
            "rev-parse",
            "--is-inside-work-tree",
            description="Could not inspect Git worktree",
        )
        if inside.lower() != "true":
            raise RuntimeError("AgentKit quality CI requires a Git worktree")

        shallow = self._git_text(
            "rev-parse",
            "--is-shallow-repository",
            description="Could not determine whether the clone is shallow",
        )
        if shallow.lower() == "true":
            raise RuntimeError(
                "AgentKit quality CI requires full Git history. "
                "Use actions/checkout with fetch-depth: 0 or fetch the base branch history."
            )

        base_commit = self._git_text(
            "rev-parse",
            "--verify",
            f"{base_ref}^{{commit}}",
            description=(
                f"Could not resolve base ref '{base_ref}'. "
                "Fetch the base branch before running quality CI"
            ),
        )
        head = self._git_text("rev-parse", "HEAD", description="Could not resolve HEAD")
        merge_base = self._git_text(
            "merge-base",
            "HEAD",
            base_ref,
            description=f"Could not resolve merge-base with '{base_ref}'",
        )
        dirty = bool(
            self._git_text(
                "status",
                "--porcelain",
                description="Could not inspect working-tree changes",
            )
        )
        if merge_base == head and not dirty:
            raise RuntimeError(
                "The resolved merge-base is the current clean HEAD. "
                "Run quality CI on a feature branch or provide an earlier base ref."
            )
        return RepositoryComparison(
            base_ref=base_ref,
            head=head,
            base_commit=base_commit,
            merge_base=merge_base,
            dirty=dirty,
        )

    def _run_directory(self, run_id: str) -> Path:
        directory = self.project_root / ".agent" / "state" / "runs" / run_id
        if directory.exists():
            raise RuntimeError(f"AgentKit run already exists: {directory}")
        directory.mkdir(parents=True, exist_ok=False)
        pointer = self.project_root / ".agent" / "state" / "quality-latest"
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(run_id, encoding="utf-8")
        return directory

    @staticmethod
    def _write_json(path: Path, payload: object) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def _relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.project_root).as_posix()
        except ValueError:
            return str(path)

    @staticmethod
    def _copy(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    def _package_artifacts(
        self,
        run_directory: Path,
        cycle: QualityCycleResult,
        summary: str,
    ) -> Path:
        artifacts = run_directory / "ci-artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        mapping = {
            cycle.baseline.result.artifacts.snapshot_path: artifacts
            / "quality-baseline.json",
            cycle.current.artifacts.snapshot_path: artifacts / "quality-current.json",
            cycle.diff_path: artifacts / "quality-diff.json",
            cycle.gate_path: artifacts / "quality-gate.json",
        }
        for source, target in mapping.items():
            self._copy(source, target)
        for name in (
            "quality-provider.json",
            "quality-provider-after.json",
            "quality-hotspots.json",
            "quality-after-hotspots.json",
            "usage.json",
        ):
            source = run_directory / name
            if source.is_file():
                self._copy(source, artifacts / name)
        (artifacts / "quality-summary.md").write_text(summary, encoding="utf-8")
        return artifacts

    def _write_failure(
        self,
        run_id: str,
        run_directory: Path,
        *,
        base_ref: str,
        message: str,
    ) -> None:
        artifacts = run_directory / "ci-artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "run_id": run_id,
            "status": "error",
            "base_ref": base_ref,
            "merge_base": "",
            "gate_allowed": False,
            "exit_code": 2,
            "run_directory": self._relative(run_directory),
            "artifact_directory": self._relative(artifacts),
            "summary_path": self._relative(artifacts / "quality-summary.md"),
            "warnings": [message],
        }
        self._write_json(run_directory / "ci-result.json", payload)
        self._write_json(artifacts / "ci-result.json", payload)
        (run_directory / "ci-exit-code").write_text("2\n", encoding="utf-8")
        (artifacts / "quality-summary.md").write_text(
            "## AgentKit Quality Report\n\n"
            "**Gate:** ERROR\n\n"
            f"- {message}\n",
            encoding="utf-8",
        )

    def run(self, *, base_ref: str, run_id: str | None = None) -> QualityCIResult:
        selected_run_id = run_id or new_ci_run_id()
        run_directory = self._run_directory(selected_run_id)
        try:
            if not self.ci_config.enabled:
                raise RuntimeError("quality.ci.enabled=false")
            if not self.quality_config.enabled:
                raise RuntimeError("quality.enabled=false; quality CI has no provider evidence")
            repository = self.inspect_repository(base_ref)
            effective = replace(
                self.quality_config,
                baseline_strategy="merge_base",
                base_branch=base_ref,
            )
            ledger = UsageLedger(
                run_id=selected_run_id,
                provider=effective.provider,
            )
            ledger.save(run_directory / "usage.json")

            def observe(phase: str, result: CommandResult) -> None:
                ledger.record(
                    phase=phase,
                    kind="tool",
                    result=result,
                    provider=effective.provider,
                )
                ledger.save(run_directory / "usage.json")

            lifecycle = QualityLifecycle(
                self.project_root,
                effective,
                self.core_config.context,
                self.core_config.security,
                observer=observe,
            )
            baseline = lifecycle.capture_baseline(run_directory)
            self._write_json(
                run_directory / "quality-baseline.json",
                {
                    "version": 1,
                    "strategy": baseline.strategy,
                    "requested_base_ref": base_ref,
                    "resolved_base_commit": repository.base_commit,
                    "merge_base": repository.merge_base,
                    "worktree_path": baseline.worktree_path,
                    "warnings": list(baseline.warnings),
                    "snapshot": "quality-before.json",
                },
            )
            cycle = lifecycle.finalize(run_directory, baseline)
            summary = render_quality_summary(
                cycle.diff,
                cycle.gate,
                effective,
            )
            summary_path = run_directory / "quality-summary.md"
            summary_path.write_text(summary, encoding="utf-8")
            artifact_directory = self._package_artifacts(
                run_directory,
                cycle,
                summary,
            )
            exit_code = 0 if cycle.gate.allowed else 6
            warnings = tuple(
                dict.fromkeys(
                    (
                        *baseline.warnings,
                        *cycle.diff.warnings,
                        *cycle.gate.warnings,
                    )
                )
            )
            result = QualityCIResult(
                run_id=selected_run_id,
                status="passed" if exit_code == 0 else "failed",
                base_ref=base_ref,
                merge_base=repository.merge_base,
                gate_allowed=cycle.gate.allowed,
                exit_code=exit_code,
                run_directory=self._relative(run_directory),
                artifact_directory=self._relative(artifact_directory),
                summary_path=self._relative(summary_path),
                warnings=warnings,
            )
            self._write_json(run_directory / "ci-result.json", result.to_dict())
            self._write_json(
                artifact_directory / "ci-result.json",
                result.to_dict(),
            )
            (run_directory / "ci-exit-code").write_text(
                f"{exit_code}\n",
                encoding="utf-8",
            )
            return result
        except Exception as exc:
            self._write_failure(
                selected_run_id,
                run_directory,
                base_ref=base_ref,
                message=str(exc),
            )
            raise
