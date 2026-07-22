from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class AcceptanceSpec:
    commands: tuple[tuple[str, ...], ...] = ()
    required_files: tuple[str, ...] = ()
    forbidden_files: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "commands": [list(item) for item in self.commands],
            "required_files": list(self.required_files),
            "forbidden_files": list(self.forbidden_files),
        }


@dataclass(frozen=True)
class QualityExpectation:
    allow_new_critical_hotspots: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BudgetExpectation:
    max_agent_calls: int | None = None
    max_duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationManifest:
    id: str
    repository_fixture: str
    mode: str
    task: str
    repetitions: int = 1
    smoke: bool = False
    integration: bool = False
    human_accepted: bool | None = None
    acceptance: AcceptanceSpec = field(default_factory=AcceptanceSpec)
    quality: QualityExpectation = field(default_factory=QualityExpectation)
    budget: BudgetExpectation = field(default_factory=BudgetExpectation)
    experiment: dict[str, str | int | float | bool] = field(default_factory=dict)
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "repository_fixture": self.repository_fixture,
            "mode": self.mode,
            "task": self.task,
            "repetitions": self.repetitions,
            "smoke": self.smoke,
            "integration": self.integration,
            "human_accepted": self.human_accepted,
            "acceptance": self.acceptance.to_dict(),
            "quality": self.quality.to_dict(),
            "budget": self.budget.to_dict(),
            "experiment": dict(sorted(self.experiment.items())),
        }


@dataclass(frozen=True)
class AcceptanceCommandResult:
    command: tuple[str, ...]
    passed: bool
    returncode: int
    duration_seconds: float
    stdout_tail: str = ""
    stderr_tail: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["command"] = list(self.command)
        return data


@dataclass(frozen=True)
class CorrectnessMetrics:
    acceptance_commands_total: int = 0
    acceptance_commands_passed: int = 0
    acceptance_passed: bool = False
    required_files_passed: bool = False
    forbidden_files_passed: bool = False
    ready_for_review: bool = False
    blocking_findings: int = 0
    scope_violations: int = 0
    human_accepted: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EfficiencyMetrics:
    agent_calls: int = 0
    tool_calls: int = 0
    duration_seconds: float = 0.0
    measured_agent_calls: int = 0
    unknown_agent_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    context_files: int | None = None
    context_symbols: int | None = None
    context_cache_hit: bool | None = None
    model_route: str = ""
    providers: tuple[str, ...] = ()
    models: tuple[str, ...] = ()

    @property
    def token_usage_complete(self) -> bool:
        return self.unknown_agent_calls == 0 and self.agent_calls == self.measured_agent_calls

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["token_usage_complete"] = self.token_usage_complete
        return data


@dataclass(frozen=True)
class QualityMetrics:
    available: bool = False
    comparable: bool = False
    gate_allowed: bool | None = None
    metric_deltas: dict[str, float | None] = field(default_factory=dict)
    new_hotspots: int = 0
    new_critical_hotspots: int = 0
    resolved_hotspots: int = 0
    persisting_hotspots: int = 0
    hotspot_recurrence: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "comparable": self.comparable,
            "gate_allowed": self.gate_allowed,
            "metric_deltas": dict(sorted(self.metric_deltas.items())),
            "new_hotspots": self.new_hotspots,
            "new_critical_hotspots": self.new_critical_hotspots,
            "resolved_hotspots": self.resolved_hotspots,
            "persisting_hotspots": self.persisting_hotspots,
            "hotspot_recurrence": self.hotspot_recurrence,
        }


@dataclass(frozen=True)
class EvaluationRunResult:
    evaluation_id: str
    task_id: str
    run_id: str
    status: str
    source_run_id: str
    agent_exit_code: int | None
    correctness: CorrectnessMetrics
    efficiency: EfficiencyMetrics
    quality: QualityMetrics
    acceptance_commands: tuple[AcceptanceCommandResult, ...] = ()
    changed_files: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    fixture_hash: str = ""
    fixture_preserved: bool = True
    experiment: dict[str, str | int | float | bool] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: int = 1

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "evaluation_id": self.evaluation_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "status": self.status,
            "source_run_id": self.source_run_id,
            "agent_exit_code": self.agent_exit_code,
            "correctness": self.correctness.to_dict(),
            "efficiency": self.efficiency.to_dict(),
            "quality": self.quality.to_dict(),
            "acceptance_commands": [item.to_dict() for item in self.acceptance_commands],
            "changed_files": list(self.changed_files),
            "warnings": list(self.warnings),
            "fixture_hash": self.fixture_hash,
            "fixture_preserved": self.fixture_preserved,
            "experiment": dict(sorted(self.experiment.items())),
        }


@dataclass(frozen=True)
class EvaluationSummary:
    evaluation_id: str
    task_ids: tuple[str, ...]
    kind: str
    run_count: int
    passed_runs: int
    failed_runs: int
    error_runs: int
    correctness: dict[str, Any]
    efficiency: dict[str, Any]
    quality: dict[str, Any]
    experiment: dict[str, str | int | float | bool]
    run_results: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "evaluation_id": self.evaluation_id,
            "task_ids": list(self.task_ids),
            "kind": self.kind,
            "run_count": self.run_count,
            "passed_runs": self.passed_runs,
            "failed_runs": self.failed_runs,
            "error_runs": self.error_runs,
            "correctness": self.correctness,
            "efficiency": self.efficiency,
            "quality": self.quality,
            "experiment": dict(sorted(self.experiment.items())),
            "run_results": list(self.run_results),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class EvaluationComparison:
    baseline: str
    current: str
    compatible: bool
    verdict: str
    correctness: dict[str, Any]
    efficiency: dict[str, Any]
    quality: dict[str, Any]
    regressions: tuple[str, ...]
    improvements: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "baseline": self.baseline,
            "current": self.current,
            "compatible": self.compatible,
            "verdict": self.verdict,
            "correctness": self.correctness,
            "efficiency": self.efficiency,
            "quality": self.quality,
            "regressions": list(self.regressions),
            "improvements": list(self.improvements),
            "warnings": list(self.warnings),
        }
