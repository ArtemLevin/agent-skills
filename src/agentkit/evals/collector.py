from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentkit.commands import CommandPolicy, run_command
from agentkit.config import AgentKitConfig
from agentkit.git import changed_files

from .models import (
    AcceptanceCommandResult,
    CorrectnessMetrics,
    EfficiencyMetrics,
    EvaluationManifest,
    QualityMetrics,
)
from .redaction import bounded_tail

_CRITICAL = {"critical", "emergency"}


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def run_acceptance_commands(
    workspace: Path,
    manifest: EvaluationManifest,
    config: AgentKitConfig,
    *,
    timeout_seconds: int,
) -> tuple[AcceptanceCommandResult, ...]:
    policy = CommandPolicy(
        config.security.allowed_executables,
        config.security.denied_substrings,
    )
    results: list[AcceptanceCommandResult] = []
    for command in manifest.acceptance.commands:
        result = run_command(
            list(command),
            cwd=workspace,
            timeout_seconds=timeout_seconds,
            policy=policy,
        )
        results.append(
            AcceptanceCommandResult(
                command=command,
                passed=result.passed,
                returncode=result.returncode,
                duration_seconds=result.duration_seconds,
                stdout_tail=bounded_tail(result.stdout),
                stderr_tail=bounded_tail(result.stderr),
            )
        )
    return tuple(results)


def collect_correctness(
    workspace: Path,
    source_run_directory: Path | None,
    manifest: EvaluationManifest,
    commands: tuple[AcceptanceCommandResult, ...],
) -> tuple[CorrectnessMetrics, tuple[str, ...], tuple[str, ...]]:
    completion = _json(source_run_directory / "completion.json") if source_run_directory else {}
    review = _json(source_run_directory / "review.json") if source_run_directory else {}
    changed = tuple(sorted(changed_files(workspace)))
    changed_set = set(changed)
    required_ok = all((workspace / item).is_file() for item in manifest.acceptance.required_files)
    forbidden_ok = all(item not in changed_set for item in manifest.acceptance.forbidden_files)
    commands_ok = bool(commands) and all(item.passed for item in commands)
    if not manifest.acceptance.commands:
        commands_ok = True
    blocking = _int(completion.get("blocking_findings"))
    if not blocking:
        findings = review.get("findings", [])
        if isinstance(findings, list):
            blocking = sum(
                1
                for item in findings
                if isinstance(item, dict)
                and str(item.get("severity", "")).upper() in {"P0", "P1"}
            )
    scope_violations = 0 if bool(completion.get("scope_passed", True)) else 1
    ready = bool(completion.get("status") == "ready_for_review" or completion.get("ready"))
    warnings: list[str] = []
    if not required_ok:
        warnings.append("One or more required files are missing")
    if not forbidden_ok:
        warnings.append("One or more forbidden files changed")
    if not commands_ok:
        warnings.append("One or more acceptance commands failed")
    if not ready:
        warnings.append("AgentKit completion was not ready_for_review")
    return (
        CorrectnessMetrics(
            acceptance_commands_total=len(commands),
            acceptance_commands_passed=sum(1 for item in commands if item.passed),
            acceptance_passed=commands_ok and required_ok and forbidden_ok,
            required_files_passed=required_ok,
            forbidden_files_passed=forbidden_ok,
            ready_for_review=ready,
            blocking_findings=blocking,
            scope_violations=scope_violations,
            human_accepted=manifest.human_accepted,
        ),
        changed,
        tuple(warnings),
    )


def collect_efficiency(source_run_directory: Path | None) -> EfficiencyMetrics:
    if source_run_directory is None:
        return EfficiencyMetrics()
    usage = _json(source_run_directory / "usage.json")
    totals = usage.get("totals", {})
    if not isinstance(totals, dict):
        totals = {}
    task_packet = _json(source_run_directory / "task-packet.json")
    quality = task_packet.get("quality", {}) if isinstance(task_packet, dict) else {}
    context_cache_hit: bool | None = None
    if isinstance(quality, dict) and "cache_hit" in quality:
        context_cache_hit = bool(quality.get("cache_hit"))
    context_files: int | None = None
    context_symbols: int | None = None
    route = task_packet.get("quality_route", {}) if isinstance(task_packet, dict) else {}
    if isinstance(route, dict):
        candidates = route.get("scoped_candidates")
        if isinstance(candidates, list):
            context_files = len({str(item.get("file", "")) for item in candidates if isinstance(item, dict)})
            context_symbols = sum(1 for item in candidates if isinstance(item, dict) and item.get("symbol"))
    return EfficiencyMetrics(
        agent_calls=_int(totals.get("agent_calls")),
        tool_calls=_int(totals.get("tool_calls")),
        duration_seconds=round(_float(totals.get("duration_seconds")), 3),
        measured_agent_calls=_int(totals.get("measured_agent_calls")),
        unknown_agent_calls=_int(totals.get("unknown_agent_calls")),
        input_tokens=_int(totals.get("input_tokens")),
        output_tokens=_int(totals.get("output_tokens")),
        cached_input_tokens=_int(totals.get("cached_input_tokens")),
        reasoning_tokens=_int(totals.get("reasoning_tokens")),
        total_tokens=_int(totals.get("total_tokens")),
        context_files=context_files,
        context_symbols=context_symbols,
        context_cache_hit=context_cache_hit,
    )


def collect_quality(source_run_directory: Path | None) -> QualityMetrics:
    if source_run_directory is None:
        return QualityMetrics()
    diff = _json(source_run_directory / "quality-diff.json")
    gate = _json(source_run_directory / "quality-gate.json")
    metrics: dict[str, float | None] = {}
    raw_metrics = diff.get("metrics", {})
    if isinstance(raw_metrics, dict):
        for name, item in raw_metrics.items():
            if isinstance(item, dict):
                value = item.get("delta")
                metrics[str(name)] = float(value) if isinstance(value, (int, float)) else None
    new_hotspots = diff.get("new_hotspots", [])
    resolved = diff.get("resolved_hotspots", [])
    persisting = diff.get("persisting_hotspots", [])
    changed = diff.get("changed_hotspots", [])
    new_list = new_hotspots if isinstance(new_hotspots, list) else []
    recurrence = 0
    for item in changed if isinstance(changed, list) else []:
        if isinstance(item, dict) and str(item.get("status", "")).lower() in _CRITICAL:
            recurrence += 1
    return QualityMetrics(
        available=bool(gate.get("available", False)),
        comparable=bool(diff.get("comparable", False)),
        gate_allowed=bool(gate.get("allowed")) if gate else None,
        metric_deltas=metrics,
        new_hotspots=len(new_list),
        new_critical_hotspots=sum(
            1
            for item in new_list
            if isinstance(item, dict) and str(item.get("status", "")).lower() in _CRITICAL
        ),
        resolved_hotspots=len(resolved) if isinstance(resolved, list) else 0,
        persisting_hotspots=len(persisting) if isinstance(persisting, list) else 0,
        hotspot_recurrence=recurrence,
    )
