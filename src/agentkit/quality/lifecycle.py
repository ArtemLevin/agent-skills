from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentkit.config import ContextConfig, SecurityConfig

from .baseline import BaselineCapture, QualityBaselineManager
from .comparison import compare_snapshots
from .config import QualityConfig
from .gate import evaluate_quality_gate
from .gate_models import QualityDiff, QualityGateResult
from .models import QualitySnapshot
from .service import Observer, QualityAnalysisResult, QualityService


@dataclass(frozen=True)
class QualityCycleResult:
    baseline: BaselineCapture
    current: QualityAnalysisResult
    diff: QualityDiff
    gate: QualityGateResult
    diff_path: Path
    gate_path: Path


class QualityLifecycle:
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

    @staticmethod
    def _write(path: Path, payload: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def capture_baseline(self, run_directory: Path) -> BaselineCapture:
        return QualityBaselineManager(
            self.project_root,
            self.quality_config,
            self.context_config,
            self.security_config,
            observer=self.observer,
        ).capture(run_directory)

    def analyze_after(
        self,
        run_directory: Path,
        *,
        force_details: bool = False,
    ) -> QualityAnalysisResult:
        from .service import QualityArtifacts
        temporary = run_directory / ".quality-after-tmp"
        shutil.rmtree(temporary, ignore_errors=True)
        temporary.mkdir(parents=True, exist_ok=False)
        try:
            result = QualityService(
                self.project_root,
                self.quality_config,
                self.context_config,
                self.security_config,
                observer=self.observer,
                phase="quality_after",
            ).analyze(
                temporary,
                force_details=force_details,
            )
            mapping = {
                result.artifacts.snapshot_path: run_directory / "quality-after.json",
                result.artifacts.hotspots_path: run_directory / "quality-after-hotspots.json",
                result.artifacts.provider_path: run_directory / "quality-provider-after.json",
            }
            raw_stdout = None
            raw_stderr = None
            if result.artifacts.raw_stdout_path is not None:
                raw_stdout = run_directory / "quality-after-raw.stdout.txt"
                mapping[result.artifacts.raw_stdout_path] = raw_stdout
            if result.artifacts.raw_stderr_path is not None:
                raw_stderr = run_directory / "quality-after-raw.stderr.txt"
                mapping[result.artifacts.raw_stderr_path] = raw_stderr
            for source, target in mapping.items():
                target.write_bytes(source.read_bytes())
            return QualityAnalysisResult(
                snapshot=result.snapshot,
                provider_status=result.provider_status,
                artifacts=QualityArtifacts(
                    snapshot_path=run_directory / "quality-after.json",
                    hotspots_path=run_directory / "quality-after-hotspots.json",
                    provider_path=run_directory / "quality-provider-after.json",
                    raw_stdout_path=raw_stdout,
                    raw_stderr_path=raw_stderr,
                ),
            )
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    def compare(
        self,
        run_directory: Path,
        baseline: QualitySnapshot,
        current: QualitySnapshot,
    ) -> tuple[QualityDiff, Path]:
        diff = compare_snapshots(
            baseline,
            current,
            baseline_strategy=self.quality_config.baseline_strategy,
        )
        path = self._write(run_directory / "quality-diff.json", diff.to_dict())
        return diff, path

    def gate(
        self,
        run_directory: Path,
        current: QualitySnapshot,
        diff: QualityDiff,
    ) -> tuple[QualityGateResult, Path]:
        result = evaluate_quality_gate(self.quality_config, current, diff)
        path = self._write(run_directory / "quality-gate.json", result.to_dict())
        return result, path

    def finalize(
        self,
        run_directory: Path,
        baseline: BaselineCapture,
    ) -> QualityCycleResult:
        current = self.analyze_after(run_directory)
        diff, diff_path = self.compare(
            run_directory,
            baseline.result.snapshot,
            current.snapshot,
        )
        gate, gate_path = self.gate(run_directory, current.snapshot, diff)
        return QualityCycleResult(
            baseline=baseline,
            current=current,
            diff=diff,
            gate=gate,
            diff_path=diff_path,
            gate_path=gate_path,
        )
