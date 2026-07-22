from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .config import RegressionThresholds
from .models import EvaluationComparison, EvaluationRunResult, EvaluationSummary
from .redaction import redact


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _average(values: Iterable[float | int | None]) -> float | None:
    measured = [float(item) for item in values if isinstance(item, (int, float)) and not isinstance(item, bool)]
    return round(mean(measured), 4) if measured else None


def aggregate_runs(
    evaluation_id: str,
    results: list[EvaluationRunResult],
    *,
    kind: str = "task",
    run_results: tuple[str, ...] = (),
) -> EvaluationSummary:
    run_count = len(results)
    passed = sum(1 for item in results if item.status == "passed")
    failed = sum(1 for item in results if item.status == "failed")
    errors = sum(1 for item in results if item.status == "error")
    completed = [item for item in results if item.status != "error"]
    correctness = {
        "acceptance_pass_rate": _rate(
            sum(1 for item in completed if item.correctness.acceptance_passed), len(completed)
        ),
        "ready_for_review_rate": _rate(
            sum(1 for item in completed if item.correctness.ready_for_review), len(completed)
        ),
        "blocking_findings_total": sum(item.correctness.blocking_findings for item in completed),
        "scope_violation_runs": sum(1 for item in completed if item.correctness.scope_violations),
        "fixture_preservation_rate": _rate(
            sum(1 for item in results if item.fixture_preserved), run_count
        ),
        "human_acceptance": {
            "accepted": sum(1 for item in completed if item.correctness.human_accepted is True),
            "rejected": sum(1 for item in completed if item.correctness.human_accepted is False),
            "unknown": sum(1 for item in completed if item.correctness.human_accepted is None),
        },
    }
    measured_token_runs = [
        item for item in results if item.efficiency.measured_agent_calls > 0
    ]
    efficiency = {
        "avg_agent_calls": _average(item.efficiency.agent_calls for item in results),
        "avg_tool_calls": _average(item.efficiency.tool_calls for item in results),
        "avg_duration_seconds": _average(item.efficiency.duration_seconds for item in results),
        "measured_token_runs": len(measured_token_runs),
        "unknown_usage_runs": sum(
            1 for item in results if item.efficiency.unknown_agent_calls > 0
        ),
        "unknown_agent_calls_total": sum(
            item.efficiency.unknown_agent_calls for item in results
        ),
        "avg_input_tokens_measured": _average(
            item.efficiency.input_tokens for item in measured_token_runs
        ),
        "avg_output_tokens_measured": _average(
            item.efficiency.output_tokens for item in measured_token_runs
        ),
        "avg_cached_input_tokens_measured": _average(
            item.efficiency.cached_input_tokens for item in measured_token_runs
        ),
        "avg_reasoning_tokens_measured": _average(
            item.efficiency.reasoning_tokens for item in measured_token_runs
        ),
        "avg_total_tokens_measured": _average(
            item.efficiency.total_tokens for item in measured_token_runs
        ),
        "avg_context_files": _average(item.efficiency.context_files for item in results),
        "avg_context_symbols": _average(item.efficiency.context_symbols for item in results),
        "context_cache_hit_rate": _rate(
            sum(1 for item in results if item.efficiency.context_cache_hit is True),
            sum(1 for item in results if item.efficiency.context_cache_hit is not None),
        ),
    }
    quality_available = [item for item in results if item.quality.available]
    quality_comparable = [item for item in results if item.quality.comparable]
    metric_names = sorted(
        {
            name
            for item in quality_comparable
            for name, value in item.quality.metric_deltas.items()
            if value is not None
        }
    )
    quality = {
        "measurement_availability_rate": _rate(len(quality_available), run_count),
        "comparison_rate": _rate(len(quality_comparable), run_count),
        "gate_pass_rate": _rate(
            sum(1 for item in quality_available if item.quality.gate_allowed is True),
            sum(1 for item in quality_available if item.quality.gate_allowed is not None),
        ),
        "avg_metric_deltas": {
            name: _average(item.quality.metric_deltas.get(name) for item in quality_comparable)
            for name in metric_names
        },
        "new_hotspots_total": sum(item.quality.new_hotspots for item in results),
        "new_critical_hotspots_total": sum(
            item.quality.new_critical_hotspots for item in results
        ),
        "avg_new_critical_hotspots": _average(
            item.quality.new_critical_hotspots for item in results
        ),
        "resolved_hotspots_total": sum(item.quality.resolved_hotspots for item in results),
        "hotspot_recurrence_total": sum(item.quality.hotspot_recurrence for item in results),
    }
    experiments = [item.experiment for item in results]
    experiment = experiments[0] if experiments and all(item == experiments[0] for item in experiments) else {}
    warnings: list[str] = []
    if efficiency["unknown_usage_runs"]:
        warnings.append("Some runs contain unknown agent token usage; token averages use measured runs only")
    if len(quality_available) < run_count:
        warnings.append("Quality measurements were unavailable for one or more runs")
    if errors:
        warnings.append("One or more evaluation runs ended with infrastructure errors")
    return EvaluationSummary(
        evaluation_id=evaluation_id,
        task_ids=tuple(sorted({item.task_id for item in results})),
        kind=kind,
        run_count=run_count,
        passed_runs=passed,
        failed_runs=failed,
        error_runs=errors,
        correctness=correctness,
        efficiency=efficiency,
        quality=quality,
        experiment=experiment,
        run_results=run_results,
        warnings=tuple(warnings),
    )


def render_summary_markdown(summary: EvaluationSummary) -> str:
    c = summary.correctness
    e = summary.efficiency
    q = summary.quality

    def value(item: Any) -> str:
        if item is None:
            return "unknown"
        if isinstance(item, float):
            return f"{item:.4g}"
        return str(item)

    lines = [
        "# AgentKit Evaluation Summary",
        "",
        f"- Evaluation: `{summary.evaluation_id}`",
        f"- Tasks: {', '.join(f'`{item}`' for item in summary.task_ids) or 'none'}",
        f"- Runs: {summary.run_count} ({summary.passed_runs} passed, {summary.failed_runs} failed, {summary.error_runs} errors)",
        "",
        "## Correctness",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Acceptance pass rate | {value(c.get('acceptance_pass_rate'))} |",
        f"| Ready-for-review rate | {value(c.get('ready_for_review_rate'))} |",
        f"| Blocking findings | {value(c.get('blocking_findings_total'))} |",
        f"| Scope-violation runs | {value(c.get('scope_violation_runs'))} |",
        "",
        "## Efficiency",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Average agent calls | {value(e.get('avg_agent_calls'))} |",
        f"| Average tool calls | {value(e.get('avg_tool_calls'))} |",
        f"| Average duration (s) | {value(e.get('avg_duration_seconds'))} |",
        f"| Average measured total tokens | {value(e.get('avg_total_tokens_measured'))} |",
        f"| Runs with unknown usage | {value(e.get('unknown_usage_runs'))} |",
        "",
        "## Quality",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Measurement availability | {value(q.get('measurement_availability_rate'))} |",
        f"| Quality gate pass rate | {value(q.get('gate_pass_rate'))} |",
        f"| New critical hotspots | {value(q.get('new_critical_hotspots_total'))} |",
        f"| Resolved hotspots | {value(q.get('resolved_hotspots_total'))} |",
        f"| Hotspot recurrence | {value(q.get('hotspot_recurrence_total'))} |",
    ]
    if summary.experiment:
        lines.extend(["", "## Experiment dimensions", ""])
        for key, item in sorted(summary.experiment.items()):
            lines.append(f"- `{key}`: `{item}`")
    if summary.warnings:
        lines.extend(["", "## Measurement warnings", ""])
        lines.extend(f"- {item}" for item in summary.warnings[:10])
    lines.extend(
        [
            "",
            "> Correctness, efficiency, and quality are intentionally reported separately. Lower cost alone is not evidence of a successful engineering change.",
            "",
        ]
    )
    return "\n".join(lines)


def _number(mapping: dict[str, Any], key: str) -> float | None:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _delta(baseline: float | None, current: float | None) -> float | None:
    return round(current - baseline, 4) if baseline is not None and current is not None else None


def _percent_increase(baseline: float | None, current: float | None) -> float | None:
    if baseline is None or current is None:
        return None
    if baseline == 0:
        return 0.0 if current == 0 else math.inf
    return round(((current - baseline) / baseline) * 100.0, 4)


def compare_summaries(
    baseline: dict[str, Any],
    current: dict[str, Any],
    thresholds: RegressionThresholds,
    *,
    baseline_name: str,
    current_name: str,
) -> EvaluationComparison:
    compatible = bool(
        baseline.get("version") == current.get("version") == 1
        and baseline.get("kind") == current.get("kind")
        and set(baseline.get("task_ids", [])) == set(current.get("task_ids", []))
    )
    warnings: list[str] = []
    if not compatible:
        warnings.append("Evaluation summaries are not schema/task compatible")

    bc = baseline.get("correctness", {}) if isinstance(baseline.get("correctness"), dict) else {}
    cc = current.get("correctness", {}) if isinstance(current.get("correctness"), dict) else {}
    be = baseline.get("efficiency", {}) if isinstance(baseline.get("efficiency"), dict) else {}
    ce = current.get("efficiency", {}) if isinstance(current.get("efficiency"), dict) else {}
    bq = baseline.get("quality", {}) if isinstance(baseline.get("quality"), dict) else {}
    cq = current.get("quality", {}) if isinstance(current.get("quality"), dict) else {}

    correctness = {
        key: {
            "baseline": _number(bc, key),
            "current": _number(cc, key),
            "delta": _delta(_number(bc, key), _number(cc, key)),
        }
        for key in ("acceptance_pass_rate", "ready_for_review_rate")
    }
    efficiency = {
        key: {
            "baseline": _number(be, key),
            "current": _number(ce, key),
            "delta": _delta(_number(be, key), _number(ce, key)),
        }
        for key in ("avg_agent_calls", "avg_tool_calls", "avg_duration_seconds", "avg_total_tokens_measured")
    }
    quality = {
        key: {
            "baseline": _number(bq, key),
            "current": _number(cq, key),
            "delta": _delta(_number(bq, key), _number(cq, key)),
        }
        for key in ("gate_pass_rate", "avg_new_critical_hotspots", "measurement_availability_rate")
    }

    regressions: list[str] = []
    improvements: list[str] = []

    def rate_rule(key: str, threshold: float, label: str) -> None:
        before = _number(bc, key)
        after = _number(cc, key)
        if before is None or after is None:
            return
        drop = before - after
        if drop > threshold:
            regressions.append(f"{label} dropped by {drop:.4g} (> {threshold:.4g})")
        elif after > before:
            improvements.append(f"{label} improved by {after - before:.4g}")

    rate_rule("acceptance_pass_rate", thresholds.acceptance_rate_drop, "Acceptance pass rate")
    rate_rule("ready_for_review_rate", thresholds.ready_rate_drop, "Ready-for-review rate")

    before_gate = _number(bq, "gate_pass_rate")
    after_gate = _number(cq, "gate_pass_rate")
    if before_gate is not None and after_gate is not None:
        drop = before_gate - after_gate
        if drop > thresholds.quality_gate_pass_rate_drop:
            regressions.append(
                f"Quality gate pass rate dropped by {drop:.4g} (> {thresholds.quality_gate_pass_rate_drop:.4g})"
            )
        elif after_gate > before_gate:
            improvements.append(f"Quality gate pass rate improved by {after_gate - before_gate:.4g}")

    before_calls = _number(be, "avg_agent_calls")
    after_calls = _number(ce, "avg_agent_calls")
    if before_calls is not None and after_calls is not None:
        increase = after_calls - before_calls
        if increase > thresholds.agent_calls_increase:
            regressions.append(
                f"Average agent calls increased by {increase:.4g} (> {thresholds.agent_calls_increase:.4g})"
            )
        elif after_calls < before_calls:
            improvements.append(f"Average agent calls decreased by {before_calls - after_calls:.4g}")

    duration_pct = _percent_increase(
        _number(be, "avg_duration_seconds"), _number(ce, "avg_duration_seconds")
    )
    efficiency["duration_increase_percent"] = duration_pct
    if duration_pct is not None and duration_pct > thresholds.duration_increase_percent:
        regressions.append(
            f"Average duration increased by {duration_pct:.4g}% (> {thresholds.duration_increase_percent:.4g}%)"
        )
    elif duration_pct is not None and duration_pct < 0:
        improvements.append(f"Average duration decreased by {-duration_pct:.4g}%")

    before_critical = _number(bq, "avg_new_critical_hotspots")
    after_critical = _number(cq, "avg_new_critical_hotspots")
    if before_critical is not None and after_critical is not None:
        increase = after_critical - before_critical
        if increase > thresholds.new_critical_hotspots_increase:
            regressions.append(
                f"Average new critical hotspots increased by {increase:.4g} (> {thresholds.new_critical_hotspots_increase:.4g})"
            )
        elif after_critical < before_critical:
            improvements.append(
                f"Average new critical hotspots decreased by {before_critical - after_critical:.4g}"
            )

    if regressions:
        verdict = "regression"
    elif improvements:
        verdict = "improved"
    else:
        verdict = "neutral"
    if not compatible:
        verdict = "incomparable"
    return EvaluationComparison(
        baseline=baseline_name,
        current=current_name,
        compatible=compatible,
        verdict=verdict,
        correctness=correctness,
        efficiency=efficiency,
        quality=quality,
        regressions=tuple(regressions),
        improvements=tuple(improvements),
        warnings=tuple(warnings),
    )


def load_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Evaluation summary must be a JSON object: {path}")
    return payload


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = redact(payload)
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def discover_summaries(project_root: Path, *, limit: int) -> list[tuple[Path, dict[str, Any]]]:
    root = project_root / ".agent" / "evals"
    items: list[tuple[Path, dict[str, Any]]] = []
    if not root.is_dir():
        return items
    for path in root.rglob("summary.json"):
        try:
            payload = load_summary(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if payload.get("version") != 1 or payload.get("kind") not in {"task", "suite"}:
            continue
        items.append((path, payload))
    items.sort(key=lambda item: str(item[1].get("generated_at", "")), reverse=True)
    return items[:limit]


def quality_trend(project_root: Path, *, limit: int) -> dict[str, Any]:
    entries = []
    for path, summary in discover_summaries(project_root, limit=limit):
        entries.append(
            {
                "path": str(path),
                "evaluation_id": summary.get("evaluation_id"),
                "generated_at": summary.get("generated_at"),
                "task_ids": summary.get("task_ids", []),
                "quality": summary.get("quality", {}),
                "correctness": {
                    "acceptance_pass_rate": summary.get("correctness", {}).get("acceptance_pass_rate"),
                    "ready_for_review_rate": summary.get("correctness", {}).get("ready_for_review_rate"),
                },
            }
        )
    return {"version": 1, "entries": redact(entries)}


def efficiency_report(project_root: Path, *, limit: int) -> dict[str, Any]:
    entries = []
    for path, summary in discover_summaries(project_root, limit=limit):
        entries.append(
            {
                "path": str(path),
                "evaluation_id": summary.get("evaluation_id"),
                "generated_at": summary.get("generated_at"),
                "task_ids": summary.get("task_ids", []),
                "efficiency": summary.get("efficiency", {}),
                "correctness": summary.get("correctness", {}),
            }
        )
    return {
        "version": 1,
        "entries": redact(entries),
        "warning": "Efficiency is contextual evidence and is not a substitute for correctness.",
    }


def quality_regressions(
    project_root: Path,
    *,
    limit: int,
    thresholds: RegressionThresholds,
) -> dict[str, Any]:
    by_tasks: dict[tuple[str, ...], list[tuple[Path, dict[str, Any]]]] = {}
    for item in discover_summaries(project_root, limit=max(limit * 3, limit)):
        task_ids = tuple(sorted(str(value) for value in item[1].get("task_ids", [])))
        by_tasks.setdefault(task_ids, []).append(item)
    comparisons: list[dict[str, Any]] = []
    for items in by_tasks.values():
        items.sort(key=lambda item: str(item[1].get("generated_at", "")))
        for previous, current in zip(items, items[1:]):
            comparison = compare_summaries(
                previous[1],
                current[1],
                thresholds,
                baseline_name=str(previous[0]),
                current_name=str(current[0]),
            )
            if comparison.verdict == "regression":
                comparisons.append(comparison.to_dict())
    comparisons.sort(key=lambda item: str(item.get("generated_at", "")), reverse=True)
    return {"version": 1, "regressions": redact(comparisons[:limit])}
