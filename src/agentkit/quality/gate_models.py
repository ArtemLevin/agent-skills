from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .models import QualityHotspot


@dataclass(frozen=True)
class QualityMetricDelta:
    metric: str
    baseline: float | None
    current: float | None
    delta: float | None
    comparable: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityMetricDelta":
        return cls(
            metric=str(data.get("metric", "")),
            baseline=_number_or_none(data.get("baseline")),
            current=_number_or_none(data.get("current")),
            delta=_number_or_none(data.get("delta")),
            comparable=bool(data.get("comparable", False)),
        )


@dataclass(frozen=True)
class QualityDiff:
    provider: str
    provider_version: str
    baseline_fingerprint: str
    current_fingerprint: str
    comparable: bool
    metrics: dict[str, QualityMetricDelta]
    new_hotspots: tuple[QualityHotspot, ...] = ()
    resolved_hotspots: tuple[QualityHotspot, ...] = ()
    persisting_hotspots: tuple[QualityHotspot, ...] = ()
    changed_hotspots: tuple[QualityHotspot, ...] = ()
    warnings: tuple[str, ...] = ()
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "provider": self.provider,
            "provider_version": self.provider_version,
            "baseline_fingerprint": self.baseline_fingerprint,
            "current_fingerprint": self.current_fingerprint,
            "comparable": self.comparable,
            "metrics": {name: item.to_dict() for name, item in self.metrics.items()},
            "new_hotspots": [item.to_dict() for item in self.new_hotspots],
            "resolved_hotspots": [item.to_dict() for item in self.resolved_hotspots],
            "persisting_hotspots": [item.to_dict() for item in self.persisting_hotspots],
            "changed_hotspots": [item.to_dict() for item in self.changed_hotspots],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityDiff":
        def hotspots(name: str) -> tuple[QualityHotspot, ...]:
            raw = data.get(name, [])
            return tuple(
                QualityHotspot.from_dict(item)
                for item in raw
                if isinstance(item, dict)
            )

        raw_metrics = data.get("metrics", {})
        return cls(
            version=int(data.get("version", 1)),
            generated_at=str(data.get("generated_at", "")),
            provider=str(data.get("provider", "")),
            provider_version=str(data.get("provider_version", "")),
            baseline_fingerprint=str(data.get("baseline_fingerprint", "")),
            current_fingerprint=str(data.get("current_fingerprint", "")),
            comparable=bool(data.get("comparable", False)),
            metrics={
                str(name): QualityMetricDelta.from_dict(item)
                for name, item in raw_metrics.items()
                if isinstance(item, dict)
            }
            if isinstance(raw_metrics, dict)
            else {},
            new_hotspots=hotspots("new_hotspots"),
            resolved_hotspots=hotspots("resolved_hotspots"),
            persisting_hotspots=hotspots("persisting_hotspots"),
            changed_hotspots=hotspots("changed_hotspots"),
            warnings=tuple(
                str(item) for item in data.get("warnings", []) if isinstance(item, str)
            ),
        )


@dataclass(frozen=True)
class QualityGateViolation:
    kind: str
    metric: str
    threshold: float
    baseline: float | None = None
    current: float | None = None
    delta: float | None = None
    scope: str = "project"
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityGateViolation":
        return cls(
            kind=str(data.get("kind", "")),
            metric=str(data.get("metric", "")),
            threshold=float(data.get("threshold", 0.0)),
            baseline=_number_or_none(data.get("baseline")),
            current=_number_or_none(data.get("current")),
            delta=_number_or_none(data.get("delta")),
            scope=str(data.get("scope", "project")),
            message=str(data.get("message", "")),
        )


@dataclass(frozen=True)
class QualityGateResult:
    mode: str
    unavailable_policy: str
    available: bool
    comparable: bool
    passed: bool
    allowed: bool
    violations: tuple[QualityGateViolation, ...] = ()
    warnings: tuple[str, ...] = ()
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: int = 1

    @property
    def regression_messages(self) -> list[str]:
        return [item.message for item in self.violations]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "mode": self.mode,
            "unavailable_policy": self.unavailable_policy,
            "available": self.available,
            "comparable": self.comparable,
            "passed": self.passed,
            "allowed": self.allowed,
            "violations": [item.to_dict() for item in self.violations],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityGateResult":
        return cls(
            version=int(data.get("version", 1)),
            generated_at=str(data.get("generated_at", "")),
            mode=str(data.get("mode", "report")),
            unavailable_policy=str(data.get("unavailable_policy", "warn")),
            available=bool(data.get("available", False)),
            comparable=bool(data.get("comparable", False)),
            passed=bool(data.get("passed", False)),
            allowed=bool(data.get("allowed", False)),
            violations=tuple(
                QualityGateViolation.from_dict(item)
                for item in data.get("violations", [])
                if isinstance(item, dict)
            ),
            warnings=tuple(
                str(item) for item in data.get("warnings", []) if isinstance(item, str)
            ),
        )


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
