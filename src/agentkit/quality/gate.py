from __future__ import annotations

from .config import QualityConfig
from .comparison import hotspot_identity
from .gate_models import QualityDiff, QualityGateResult, QualityGateViolation
from .models import QualitySnapshot


_CURRENT_METRICS = {
    "score": "score",
    "rp": "refactoring_pressure",
    "op": "overengineering_pressure",
    "density": "complexity_density",
}


def _current(snapshot: QualitySnapshot, attr: str) -> float | None:
    if snapshot.project is None:
        return None
    value = getattr(snapshot.project, attr)
    return float(value) if value is not None else None


def evaluate_quality_gate(
    config: QualityConfig,
    current: QualitySnapshot,
    diff: QualityDiff,
) -> QualityGateResult:
    warnings = list(diff.warnings)
    violations: list[QualityGateViolation] = []

    available = current.usable
    comparison_required = config.baseline_strategy != "none"
    comparable = diff.comparable if comparison_required else True

    if not available:
        warnings.append("Current quality evidence is unavailable")
    if comparison_required and not comparable:
        warnings.append("Quality snapshots are not comparable")

    absolute_limits = {
        "score": config.absolute.score,
        "rp": config.absolute.rp,
        "op": config.absolute.op,
        "density": config.absolute.density,
    }
    for metric, attr in _CURRENT_METRICS.items():
        threshold = absolute_limits[metric]
        if threshold <= 0:
            continue
        value = _current(current, attr)
        if value is None:
            warnings.append(f"Absolute threshold for {metric} could not be evaluated")
            continue
        if value > threshold:
            violations.append(
                QualityGateViolation(
                    kind="absolute",
                    metric=metric,
                    threshold=threshold,
                    current=value,
                    message=f"{metric}={value:g} exceeds absolute threshold {threshold:g}",
                )
            )

    delta_limits = {
        "score": config.delta.score,
        "rp": config.delta.rp,
        "op": config.delta.op,
        "density": config.delta.density,
    }
    if comparison_required:
        for metric, threshold in delta_limits.items():
            if threshold <= 0:
                continue
            item = diff.metrics.get(metric)
            if item is None or not item.comparable or item.delta is None:
                warnings.append(f"Delta threshold for {metric} could not be evaluated")
                continue
            if item.delta > threshold:
                violations.append(
                    QualityGateViolation(
                        kind="delta",
                        metric=metric,
                        threshold=threshold,
                        baseline=item.baseline,
                        current=item.current,
                        delta=item.delta,
                        message=(
                            f"{metric} increased by {item.delta:g}; "
                            f"allowed increase is {threshold:g}"
                        ),
                    )
                )

        limit = config.delta.new_critical_hotspots
        if limit is not None:
            critical = [
                item
                for item in diff.new_hotspots
                if item.status.lower() in {"critical", "emergency"}
            ]
            if len(critical) > limit:
                violations.append(
                    QualityGateViolation(
                        kind="hotspot",
                        metric="new_critical_hotspots",
                        threshold=float(limit),
                        current=float(len(critical)),
                        scope=", ".join(hotspot_identity(item) for item in critical[:5])
                        or "project",
                        message=(
                            f"{len(critical)} new critical hotspots detected; allowed {limit}"
                        ),
                    )
                )

    unavailable_blocks = (
        config.unavailable_policy == "stop"
        and (not available or (comparison_required and not comparable))
    )
    measurement_complete = available and (comparable or not comparison_required)
    passed = measurement_complete and not violations
    allowed = not unavailable_blocks and (
        not violations or config.mode in {"report", "warn"}
    )

    return QualityGateResult(
        mode=config.mode,
        unavailable_policy=config.unavailable_policy,
        available=available,
        comparable=comparable,
        passed=passed,
        allowed=allowed,
        violations=tuple(violations),
        warnings=tuple(dict.fromkeys(warnings)),
    )
