from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import QualityConfig
from .gate_models import QualityDiff, QualityGateResult

_METRIC_LABELS = {
    "score": "Project score",
    "rp": "Refactoring pressure",
    "op": "Overengineering pressure",
    "density": "Complexity density",
}


def _number(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    if float(value).is_integer():
        return f"{value:+.0f}" if signed else f"{value:.0f}"
    return f"{value:+.2f}" if signed else f"{value:.2f}"


def _threshold(config: QualityConfig, metric: str) -> float | None:
    mapping = {
        "score": config.delta.score,
        "rp": config.delta.rp,
        "op": config.delta.op,
        "density": config.delta.density,
    }
    value = mapping.get(metric)
    return float(value) if value is not None and value > 0 else None


def _failed_metrics(gate: QualityGateResult) -> set[str]:
    return {
        item.metric
        for item in gate.violations
        if item.metric in _METRIC_LABELS
    }


def render_quality_summary(
    diff: QualityDiff,
    gate: QualityGateResult,
    config: QualityConfig,
    *,
    max_items: int = 10,
) -> str:
    failed = _failed_metrics(gate)
    lines = [
        "## AgentKit Quality Report",
        "",
        f"**Gate:** {'PASS' if gate.allowed else 'FAIL'} "
        f"(mode `{gate.mode}`, comparable `{str(diff.comparable).lower()}`)",
        "",
        "| Metric | Baseline | Current | Delta | Threshold | Result |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for metric in ("score", "rp", "op", "density"):
        item = diff.metrics.get(metric)
        threshold = _threshold(config, metric)
        if item is None:
            baseline = current = delta = "N/A"
            result = "UNKNOWN"
        else:
            baseline = _number(item.baseline)
            current = _number(item.current)
            delta = _number(item.delta, signed=True)
            result = "FAIL" if metric in failed else ("PASS" if item.comparable else "UNKNOWN")
        lines.append(
            "| "
            + " | ".join(
                (
                    _METRIC_LABELS[metric],
                    baseline,
                    current,
                    delta,
                    _number(threshold, signed=True),
                    result,
                )
            )
            + " |"
        )

    new_critical = sum(
        1
        for item in diff.new_hotspots
        if str(item.status).lower() in {"critical", "emergency"}
    )
    lines.extend(
        [
            "",
            f"- New hotspots: **{len(diff.new_hotspots)}**",
            f"- New critical hotspots: **{new_critical}**",
            f"- Resolved hotspots: **{len(diff.resolved_hotspots)}**",
            f"- Changed hotspots: **{len(diff.changed_hotspots)}**",
        ]
    )

    if gate.violations:
        lines.extend(["", "### Violations", ""])
        for violation in gate.violations[:max_items]:
            lines.append(f"- `{violation.metric}` — {violation.message}")
        if len(gate.violations) > max_items:
            lines.append(f"- … {len(gate.violations) - max_items} more violation(s) omitted")

    warnings = list(dict.fromkeys((*diff.warnings, *gate.warnings)))
    lines.extend(["", "### Measurement warnings", ""])
    if not warnings:
        lines.append("- None")
    else:
        for warning in warnings[:max_items]:
            lines.append(f"- {warning}")
        if len(warnings) > max_items:
            lines.append(f"- … {len(warnings) - max_items} more warning(s) omitted")

    return "\n".join(lines).rstrip() + "\n"


def github_annotations(
    diff: QualityDiff,
    gate: QualityGateResult,
    *,
    max_items: int = 10,
) -> tuple[str, ...]:
    messages: list[str] = []
    for violation in gate.violations[:max_items]:
        message = violation.message.replace("\n", " ").replace("\r", " ")
        messages.append(f"::warning title=AgentKit quality::{message}")
    for warning in list(dict.fromkeys((*diff.warnings, *gate.warnings)))[:max_items]:
        clean = warning.replace("\n", " ").replace("\r", " ")
        messages.append(f"::notice title=AgentKit quality measurement::{clean}")
    return tuple(messages)


def resolve_run_directory(project_root: Path, run_id: str) -> tuple[str, Path]:
    resolved = run_id
    if run_id == "latest":
        pointer = project_root / ".agent" / "state" / "quality-latest"
        if not pointer.is_file():
            pointer = project_root / ".agent" / "state" / "latest"
        if not pointer.is_file():
            raise FileNotFoundError("No AgentKit quality run exists")
        resolved = pointer.read_text(encoding="utf-8").strip()
    directory = project_root / ".agent" / "state" / "runs" / resolved
    if not directory.is_dir():
        raise FileNotFoundError(f"AgentKit run directory does not exist: {directory}")
    return resolved, directory


def load_quality_summary_inputs(
    project_root: Path,
    run_id: str,
) -> tuple[str, Path, QualityDiff, QualityGateResult]:
    resolved, directory = resolve_run_directory(project_root, run_id)
    diff_path = directory / "quality-diff.json"
    gate_path = directory / "quality-gate.json"
    diff_payload = json.loads(diff_path.read_text(encoding="utf-8"))
    gate_payload = json.loads(gate_path.read_text(encoding="utf-8"))
    if not isinstance(diff_payload, dict) or not isinstance(gate_payload, dict):
        raise ValueError("Quality diff and gate artifacts must be JSON objects")
    return (
        resolved,
        directory,
        QualityDiff.from_dict(diff_payload),
        QualityGateResult.from_dict(gate_payload),
    )
