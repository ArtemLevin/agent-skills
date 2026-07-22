from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from agentkit.commands import CommandPolicy, run_command
from agentkit.config import ContextConfig, SecurityConfig
from agentkit.models import CommandResult

from .config import QualityConfig
from .models import (
    QualityCapabilities,
    QualityProviderStatus,
    QualitySnapshot,
)
from .service import Observer, QualityAnalysisResult, QualityService


@dataclass(frozen=True)
class BaselineCapture:
    strategy: str
    result: QualityAnalysisResult
    merge_base: str = ""
    worktree_path: str = ""
    warnings: tuple[str, ...] = ()


class QualityBaselineManager:
    def __init__(
        self,
        project_root: Path,
        quality_config: QualityConfig,
        context_config: ContextConfig,
        security_config: SecurityConfig,
        *,
        observer: Observer | None = None,
    ) -> None:
        self.project_root = project_root
        self.quality_config = quality_config
        self.context_config = context_config
        self.security_config = security_config
        self.observer = observer
        self.policy = CommandPolicy(
            security_config.allowed_executables,
            security_config.denied_substrings,
        )

    def _service(
        self,
        root: Path,
        *,
        phase: str,
    ) -> QualityService:
        return QualityService(
            root,
            self.quality_config,
            self.context_config,
            self.security_config,
            observer=self.observer,
            phase=phase,
        )

    def _execute(
        self,
        command: list[str],
        *,
        cwd: Path,
        phase: str,
    ) -> CommandResult:
        result = run_command(
            command,
            cwd=cwd,
            timeout_seconds=self.quality_config.timeout_seconds,
            policy=self.policy,
        )
        if self.observer is not None:
            self.observer(phase, result)
        return result

    def _from_file(self, run_directory: Path) -> BaselineCapture:
        path = Path(self.quality_config.baseline_file).expanduser()
        if not path.is_absolute():
            path = self.project_root / path
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Quality baseline must be a JSON object: {path}")
        snapshot = QualitySnapshot.from_dict(payload)
        status = QualityProviderStatus(
            availability=snapshot.availability,
            provider=snapshot.provider,
            provider_version=snapshot.provider_version,
            executable="snapshot-file",
            detected_languages=(
                (snapshot.project.language,)
                if snapshot.project and snapshot.project.language
                else ()
            ),
            supported_languages=(),
            message=f"Loaded quality baseline from {path}",
            capabilities=QualityCapabilities(
                supported_languages=(),
                provider_version=snapshot.provider_version,
            ),
        )
        run_directory.mkdir(parents=True, exist_ok=True)
        snapshot_path = run_directory / "quality-before.json"
        hotspots_path = run_directory / "quality-hotspots.json"
        provider_path = run_directory / "quality-provider.json"
        snapshot_path.write_text(
            json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        hotspots_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "availability": snapshot.availability.value,
                    "provider": snapshot.provider,
                    "provider_version": snapshot.provider_version,
                    "source_fingerprint": snapshot.source_fingerprint,
                    "hotspots": [item.to_dict() for item in snapshot.hotspots],
                    "warnings": list(snapshot.warnings),
                    "truncated": snapshot.truncated,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        provider_path.write_text(
            json.dumps(status.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        from .service import QualityArtifacts
        result = QualityAnalysisResult(
            snapshot=snapshot,
            provider_status=status,
            artifacts=QualityArtifacts(
                snapshot_path=snapshot_path,
                hotspots_path=hotspots_path,
                provider_path=provider_path,
            ),
        )
        return BaselineCapture(
            strategy="file",
            result=result,
            warnings=(f"Baseline loaded from {path}",),
        )

    def _merge_base(self, run_directory: Path) -> BaselineCapture:
        merge = self._execute(
            ["git", "merge-base", "HEAD", self.quality_config.base_branch],
            cwd=self.project_root,
            phase="quality_baseline",
        )
        if not merge.passed or not merge.stdout.strip():
            raise RuntimeError(
                "Could not resolve merge-base with "
                f"{self.quality_config.base_branch}: "
                f"{merge.stderr.strip() or merge.stdout.strip()}"
            )
        revision = merge.stdout.strip().splitlines()[-1]
        worktree = (
            self.project_root
            / ".agent"
            / "worktrees"
            / f"quality-baseline-{uuid4().hex[:8]}"
        )
        worktree.parent.mkdir(parents=True, exist_ok=True)
        add = self._execute(
            ["git", "worktree", "add", "--detach", str(worktree), revision],
            cwd=self.project_root,
            phase="quality_baseline",
        )
        if not add.passed:
            raise RuntimeError(
                "Could not materialize quality baseline worktree: "
                f"{add.stderr.strip() or add.stdout.strip()}"
            )

        warnings: list[str] = []
        try:
            result = self._service(worktree, phase="quality_baseline").analyze(
                run_directory
            )
        finally:
            remove = self._execute(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=self.project_root,
                phase="quality_baseline",
            )
            if not remove.passed:
                warnings.append(
                    "Temporary quality baseline worktree could not be removed "
                    f"automatically: {worktree}"
                )
                shutil.rmtree(worktree, ignore_errors=True)
        return BaselineCapture(
            strategy="merge_base",
            result=result,
            merge_base=revision,
            worktree_path=str(worktree),
            warnings=tuple(warnings),
        )

    def capture(self, run_directory: Path) -> BaselineCapture:
        strategy = self.quality_config.baseline_strategy
        if strategy == "file":
            return self._from_file(run_directory)
        if strategy == "merge_base":
            return self._merge_base(run_directory)
        result = self._service(self.project_root, phase="quality_before").analyze(
            run_directory
        )
        return BaselineCapture(
            strategy=strategy,
            result=result,
            warnings=(
                ("Delta comparison disabled by baseline_strategy=none",)
                if strategy == "none"
                else ()
            ),
        )
