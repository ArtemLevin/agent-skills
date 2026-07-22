from __future__ import annotations

import json
from typing import Any

from .errors import QualityProviderParseError
from .models import (
    Availability,
    QualityHotspot,
    QualityProject,
    QualitySnapshot,
    QualityStats,
)

PARSER_VERSION = "1"


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _stats(value: Any) -> QualityStats | None:
    data = _mapping(value)
    if not data:
        return None
    stats = QualityStats(
        avg=_number(data.get("avg")),
        min=_number(data.get("min")),
        max=_number(data.get("max")),
        p50=_number(data.get("p50")),
        p90=_number(data.get("p90")),
    )
    if all(item is None for item in stats.to_dict().values()):
        return None
    return stats


def _reasons(item: dict[str, Any]) -> tuple[str, ...]:
    status = _mapping(item.get("status"))
    values = _list(status.get("reasons"))
    return tuple(str(value) for value in values if isinstance(value, str))


def _hotspot(kind: str, item: dict[str, Any]) -> QualityHotspot:
    status = _mapping(item.get("status"))
    complexity = _mapping(item.get("complexity"))
    rp = _mapping(item.get("refactoring_pressure"))
    op = _mapping(item.get("overengineering_pressure"))
    complexity_score = _number(complexity.get("score"))
    if complexity_score is None:
        complexity_score = _number(complexity.get("value"))
    candidates = [
        _number(status.get("score")),
        complexity_score,
        _number(complexity.get("total")),
        _number(complexity.get("density")),
        _number(rp.get("score")),
        _number(op.get("score")),
    ]
    rank = max((value for value in candidates if value is not None), default=0.0)
    return QualityHotspot(
        kind=kind,
        name=str(item.get("name", "")),
        file=str(item.get("file", item.get("dir", ""))),
        class_name=str(item.get("class", "")),
        status=str(status.get("name", "")),
        status_score=_number(status.get("score")),
        loc=_integer(item.get("loc")),
        complexity=complexity_score,
        complexity_total=_number(complexity.get("total")),
        complexity_density=_number(complexity.get("density")),
        refactoring_pressure=_number(rp.get("score")),
        overengineering_pressure=_number(op.get("score")),
        reasons=_reasons(item),
        rank_score=rank,
    )


def _bounded_hotspots(
    payload: dict[str, Any],
    *,
    limits: dict[str, int],
) -> tuple[tuple[QualityHotspot, ...], bool]:
    category_map = {
        "packages": "package",
        "modules": "module",
        "classes": "class",
        "methods": "method",
        "functions": "function",
    }
    collected: list[QualityHotspot] = []
    truncated = False
    for key, kind in category_map.items():
        values = [item for item in _list(payload.get(key)) if isinstance(item, dict)]
        limit = max(0, int(limits.get(key, 0)))
        if limit and len(values) > limit:
            truncated = True
        if limit == 0:
            values = []
        else:
            values = values[:limit]
        collected.extend(_hotspot(kind, item) for item in values)
    collected.sort(key=lambda item: (item.rank_score, item.status_score or 0.0), reverse=True)
    return tuple(collected), truncated


def parse_strictacode_json(
    stdout: str,
    *,
    provider_version: str,
    details: bool,
    limits: dict[str, int],
) -> QualitySnapshot:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise QualityProviderParseError(
            f"StrictaCode returned invalid JSON: {exc}", stdout=stdout
        ) from exc
    if not isinstance(payload, dict):
        raise QualityProviderParseError(
            "StrictaCode JSON root must be an object", stdout=stdout
        )
    project_data = _mapping(payload.get("project"))
    if not project_data:
        raise QualityProviderParseError(
            "StrictaCode JSON does not contain project data", stdout=stdout
        )

    status = _mapping(project_data.get("status"))
    rp = _mapping(project_data.get("refactoring_pressure"))
    op = _mapping(project_data.get("overengineering_pressure"))
    complexity = _mapping(project_data.get("complexity"))
    warnings: list[str] = []

    required_metrics = {
        "project.score": _number(status.get("score")),
        "project.refactoring_pressure": _number(rp.get("score")),
        "project.overengineering_pressure": _number(op.get("score")),
        "project.complexity_density": _number(complexity.get("density")),
    }
    missing = [name for name, value in required_metrics.items() if value is None]
    if missing:
        warnings.append("Missing required provider fields: " + ", ".join(missing))

    project = QualityProject(
        score=required_metrics["project.score"],
        refactoring_pressure=required_metrics["project.refactoring_pressure"],
        overengineering_pressure=required_metrics["project.overengineering_pressure"],
        complexity_density=required_metrics["project.complexity_density"],
        status=str(status.get("name", "")),
        language=str(project_data.get("lang", "")),
        loc=_integer(project_data.get("loc")),
    )

    statistics: dict[str, QualityStats] = {}
    complexity_stats = _stats(complexity.get("stat(modules)"))
    if complexity_stats is not None:
        statistics["complexity"] = complexity_stats
    rp_stats = _stats(rp.get("stat(modules)"))
    if rp_stats is not None:
        statistics["refactoring_pressure"] = rp_stats
    op_stats = _stats(op.get("stat(modules)"))
    if op_stats is not None:
        statistics["overengineering_pressure"] = op_stats

    hotspots, truncated = _bounded_hotspots(payload, limits=limits)
    availability = Availability.PARTIAL if missing else Availability.AVAILABLE
    return QualitySnapshot(
        availability=availability,
        provider="strictacode",
        provider_version=provider_version,
        source_fingerprint="",
        project=project,
        statistics=statistics,
        hotspots=hotspots,
        warnings=tuple(warnings),
        truncated=truncated,
        details=details,
    )
