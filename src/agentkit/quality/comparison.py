from __future__ import annotations

from .gate_models import QualityDiff, QualityMetricDelta
from .models import QualityHotspot, QualitySnapshot


def hotspot_identity(item: QualityHotspot) -> str:
    return "|".join((item.kind, item.file, item.class_name, item.name))


_PROJECT_METRICS = {
    "score": "score",
    "rp": "refactoring_pressure",
    "op": "overengineering_pressure",
    "density": "complexity_density",
}


def _metric(snapshot: QualitySnapshot, attr: str) -> float | None:
    if snapshot.project is None:
        return None
    value = getattr(snapshot.project, attr)
    return float(value) if value is not None else None


def compare_snapshots(
    baseline: QualitySnapshot,
    current: QualitySnapshot,
    *,
    baseline_strategy: str,
) -> QualityDiff:
    warnings: list[str] = []
    comparable = True

    if not baseline.usable:
        comparable = False
        warnings.append("Baseline quality snapshot is unavailable or unusable")
    if not current.usable:
        comparable = False
        warnings.append("Current quality snapshot is unavailable or unusable")
    if baseline.provider != current.provider:
        comparable = False
        warnings.append(f"Provider mismatch: {baseline.provider!r} vs {current.provider!r}")
    if baseline.provider_version != current.provider_version:
        comparable = False
        warnings.append(
            "Provider version mismatch: "
            f"{baseline.provider_version!r} vs {current.provider_version!r}"
        )
    baseline_language = baseline.project.language if baseline.project else ""
    current_language = current.project.language if current.project else ""
    if baseline_language and current_language and baseline_language != current_language:
        comparable = False
        warnings.append(f"Language mismatch: {baseline_language!r} vs {current_language!r}")

    metrics: dict[str, QualityMetricDelta] = {}
    for name, attr in _PROJECT_METRICS.items():
        before = _metric(baseline, attr)
        after = _metric(current, attr)
        metric_comparable = comparable and before is not None and after is not None
        metrics[name] = QualityMetricDelta(
            metric=name,
            baseline=before,
            current=after,
            delta=(after - before) if metric_comparable else None,
            comparable=metric_comparable,
        )
        if comparable and not metric_comparable:
            warnings.append(f"Metric {name} is missing from one or both snapshots")

    before_map = {hotspot_identity(item): item for item in baseline.hotspots}
    after_map = {hotspot_identity(item): item for item in current.hotspots}
    new_ids = sorted(after_map.keys() - before_map.keys())
    resolved_ids = sorted(before_map.keys() - after_map.keys())
    persisting_ids = sorted(before_map.keys() & after_map.keys())

    changed: list[QualityHotspot] = []
    for identity in persisting_ids:
        before = before_map[identity]
        after = after_map[identity]
        if (
            before.status != after.status
            or before.status_score != after.status_score
            or before.rank_score != after.rank_score
            or before.complexity != after.complexity
            or before.refactoring_pressure != after.refactoring_pressure
            or before.overengineering_pressure != after.overengineering_pressure
        ):
            changed.append(after)

    if baseline_strategy == "none":
        comparable = False
        warnings.append("Delta comparison is disabled by baseline_strategy=none")
        metrics = {
            name: QualityMetricDelta(
                metric=item.metric,
                baseline=None,
                current=item.current,
                delta=None,
                comparable=False,
            )
            for name, item in metrics.items()
        }

    return QualityDiff(
        provider=current.provider or baseline.provider,
        provider_version=current.provider_version or baseline.provider_version,
        baseline_fingerprint=baseline.source_fingerprint,
        current_fingerprint=current.source_fingerprint,
        comparable=comparable,
        metrics=metrics,
        new_hotspots=tuple(after_map[item] for item in new_ids),
        resolved_hotspots=tuple(before_map[item] for item in resolved_ids),
        persisting_hotspots=tuple(after_map[item] for item in persisting_ids),
        changed_hotspots=tuple(changed),
        warnings=tuple(dict.fromkeys(warnings)),
    )
