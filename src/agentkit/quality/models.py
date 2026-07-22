from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class Availability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass(frozen=True)
class QualityCapabilities:
    supported_languages: tuple[str, ...]
    project_details: bool = True
    package_details: bool = True
    module_details: bool = True
    class_details: bool = True
    function_details: bool = True
    line_numbers: bool = False
    absolute_thresholds: bool = True
    comparisons: bool = True
    provider_version: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["supported_languages"] = list(self.supported_languages)
        return data


@dataclass(frozen=True)
class QualityProviderStatus:
    availability: Availability
    provider: str
    provider_version: str
    executable: str
    detected_languages: tuple[str, ...] = ()
    supported_languages: tuple[str, ...] = ()
    message: str = ""
    capabilities: QualityCapabilities | None = None

    @property
    def usable(self) -> bool:
        return self.availability in {Availability.AVAILABLE, Availability.PARTIAL}

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "availability": self.availability.value,
            "provider": self.provider,
            "provider_version": self.provider_version,
            "executable": self.executable,
            "detected_languages": list(self.detected_languages),
            "supported_languages": list(self.supported_languages),
            "message": self.message,
            "capabilities": self.capabilities.to_dict() if self.capabilities else None,
        }


@dataclass(frozen=True)
class QualityStats:
    avg: float | None = None
    min: float | None = None
    max: float | None = None
    p50: float | None = None
    p90: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityStats":
        return cls(
            avg=_number_or_none(data.get("avg")),
            min=_number_or_none(data.get("min")),
            max=_number_or_none(data.get("max")),
            p50=_number_or_none(data.get("p50")),
            p90=_number_or_none(data.get("p90")),
        )


@dataclass(frozen=True)
class QualityProject:
    score: float | None
    refactoring_pressure: float | None
    overengineering_pressure: float | None
    complexity_density: float | None
    status: str
    language: str = ""
    loc: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityProject":
        return cls(
            score=_number_or_none(data.get("score")),
            refactoring_pressure=_number_or_none(data.get("refactoring_pressure")),
            overengineering_pressure=_number_or_none(data.get("overengineering_pressure")),
            complexity_density=_number_or_none(data.get("complexity_density")),
            status=str(data.get("status", "")),
            language=str(data.get("language", "")),
            loc=_int_or_none(data.get("loc")),
        )


@dataclass(frozen=True)
class QualityHotspot:
    kind: str
    name: str
    file: str = ""
    class_name: str = ""
    status: str = ""
    status_score: float | None = None
    loc: int | None = None
    complexity: float | None = None
    complexity_total: float | None = None
    complexity_density: float | None = None
    refactoring_pressure: float | None = None
    overengineering_pressure: float | None = None
    reasons: tuple[str, ...] = ()
    rank_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityHotspot":
        reasons = data.get("reasons", [])
        return cls(
            kind=str(data.get("kind", "")),
            name=str(data.get("name", "")),
            file=str(data.get("file", "")),
            class_name=str(data.get("class_name", "")),
            status=str(data.get("status", "")),
            status_score=_number_or_none(data.get("status_score")),
            loc=_int_or_none(data.get("loc")),
            complexity=_number_or_none(data.get("complexity")),
            complexity_total=_number_or_none(data.get("complexity_total")),
            complexity_density=_number_or_none(data.get("complexity_density")),
            refactoring_pressure=_number_or_none(data.get("refactoring_pressure")),
            overengineering_pressure=_number_or_none(data.get("overengineering_pressure")),
            reasons=tuple(str(item) for item in reasons if isinstance(item, str)),
            rank_score=float(data.get("rank_score", 0.0)),
        )


@dataclass(frozen=True)
class QualitySnapshot:
    availability: Availability
    provider: str
    provider_version: str
    source_fingerprint: str
    project: QualityProject | None
    statistics: dict[str, QualityStats] = field(default_factory=dict)
    hotspots: tuple[QualityHotspot, ...] = ()
    warnings: tuple[str, ...] = ()
    truncated: bool = False
    cache_hit: bool = False
    details: bool = False
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: int = 1

    @property
    def usable(self) -> bool:
        return self.availability in {Availability.AVAILABLE, Availability.PARTIAL}

    @property
    def elevated(self) -> bool:
        if self.project is None:
            return False
        return self.project.status.lower() in {"warning", "critical", "emergency"}

    def with_runtime(
        self,
        *,
        source_fingerprint: str | None = None,
        cache_hit: bool | None = None,
        warnings: tuple[str, ...] | None = None,
    ) -> "QualitySnapshot":
        return replace(
            self,
            source_fingerprint=(
                self.source_fingerprint if source_fingerprint is None else source_fingerprint
            ),
            cache_hit=self.cache_hit if cache_hit is None else cache_hit,
            warnings=self.warnings if warnings is None else warnings,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "availability": self.availability.value,
            "provider": self.provider,
            "provider_version": self.provider_version,
            "source_fingerprint": self.source_fingerprint,
            "project": self.project.to_dict() if self.project else None,
            "statistics": {name: stat.to_dict() for name, stat in self.statistics.items()},
            "hotspots": [hotspot.to_dict() for hotspot in self.hotspots],
            "warnings": list(self.warnings),
            "truncated": self.truncated,
            "cache_hit": self.cache_hit,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualitySnapshot":
        project = data.get("project")
        statistics = data.get("statistics", {})
        hotspots = data.get("hotspots", [])
        warnings = data.get("warnings", [])
        return cls(
            version=int(data.get("version", 1)),
            generated_at=str(data.get("generated_at", "")),
            availability=Availability(str(data.get("availability", Availability.FAILED.value))),
            provider=str(data.get("provider", "")),
            provider_version=str(data.get("provider_version", "unknown")),
            source_fingerprint=str(data.get("source_fingerprint", "")),
            project=QualityProject.from_dict(project) if isinstance(project, dict) else None,
            statistics={
                str(name): QualityStats.from_dict(value)
                for name, value in statistics.items()
                if isinstance(value, dict)
            }
            if isinstance(statistics, dict)
            else {},
            hotspots=tuple(
                QualityHotspot.from_dict(item)
                for item in hotspots
                if isinstance(item, dict)
            ),
            warnings=tuple(str(item) for item in warnings if isinstance(item, str)),
            truncated=bool(data.get("truncated", False)),
            cache_hit=bool(data.get("cache_hit", False)),
            details=bool(data.get("details", False)),
        )

    def task_packet_entry(self, snapshot_path: str, hotspots_path: str) -> dict[str, Any]:
        return {
            "availability": self.availability.value,
            "provider": self.provider,
            "provider_version": self.provider_version,
            "snapshot_path": snapshot_path,
            "hotspots_path": hotspots_path,
            "project": self.project.to_dict() if self.project else None,
            "hotspot_count": len(self.hotspots),
            "warnings": list(self.warnings[:5]),
            "truncated": self.truncated,
            "cache_hit": self.cache_hit,
        }


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _int_or_none(value: Any) -> int | None:
    number = _number_or_none(value)
    return int(number) if number is not None else None
