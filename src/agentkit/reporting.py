from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import BudgetConfig
from .telemetry import BudgetController, UsageLedger


def resolve_run_id(project_root: Path, run_id: str | None = None) -> str:
    if run_id and run_id != "latest":
        return run_id
    latest = project_root / ".agent" / "state" / "latest"
    if not latest.is_file():
        raise FileNotFoundError("No AgentKit runs found")
    value = latest.read_text(encoding="utf-8").strip()
    if not value:
        raise FileNotFoundError("AgentKit latest-run marker is empty")
    return value


def usage_path(project_root: Path, run_id: str | None = None) -> Path:
    resolved = resolve_run_id(project_root, run_id)
    path = project_root / ".agent" / "state" / "runs" / resolved / "usage.json"
    if not path.is_file():
        raise FileNotFoundError(f"Usage telemetry is unavailable for run {resolved}")
    return path


def load_usage(project_root: Path, run_id: str | None = None) -> dict[str, Any]:
    return json.loads(usage_path(project_root, run_id).read_text(encoding="utf-8"))


def load_budget_status(
    project_root: Path,
    budget: BudgetConfig,
    run_id: str | None = None,
) -> dict[str, Any]:
    path = usage_path(project_root, run_id)
    ledger = UsageLedger.load(path)
    return {
        "run_id": ledger.run_id,
        "configuration": {
            "enabled": budget.enabled,
            "soft_input_tokens": budget.soft_input_tokens,
            "hard_input_tokens": budget.hard_input_tokens,
            "soft_output_tokens": budget.soft_output_tokens,
            "hard_output_tokens": budget.hard_output_tokens,
            "soft_agent_calls": budget.soft_agent_calls,
            "hard_agent_calls": budget.hard_agent_calls,
            "soft_duration_seconds": budget.soft_duration_seconds,
            "hard_duration_seconds": budget.hard_duration_seconds,
            "unknown_usage_policy": budget.unknown_usage_policy,
            "phase_agent_call_limits": budget.phase_agent_call_limits,
        },
        "status": BudgetController(budget).evaluate(ledger).to_dict(),
    }


def aggregate_report(project_root: Path, *, limit: int = 20) -> dict[str, Any]:
    runs_root = project_root / ".agent" / "state" / "runs"
    if not runs_root.is_dir():
        return {"runs": 0, "ready_runs": 0, "ready_rate": 0.0, "totals": {}, "phases": {}}

    run_directories = sorted(
        (path for path in runs_root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )[: max(limit, 0)]

    totals: dict[str, float] = {
        "agent_calls": 0,
        "tool_calls": 0,
        "duration_seconds": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        "measured_agent_calls": 0,
        "unknown_agent_calls": 0,
    }
    phases: dict[str, dict[str, float]] = {}
    ready_runs = 0
    included_runs: list[str] = []

    for run_dir in run_directories:
        path = run_dir / "usage.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        included_runs.append(run_dir.name)
        for key, value in data.get("totals", {}).items():
            if key in totals and isinstance(value, (int, float)):
                totals[key] += value
        for phase, values in data.get("phases", {}).items():
            if not isinstance(values, dict):
                continue
            target = phases.setdefault(phase, {key: 0 for key in totals})
            for key, value in values.items():
                if key in target and isinstance(value, (int, float)):
                    target[key] += value
        completion = run_dir / "completion.json"
        if completion.is_file():
            payload = json.loads(completion.read_text(encoding="utf-8"))
            if payload.get("ready") is True or payload.get("status") == "ready_for_review":
                ready_runs += 1

    run_count = len(included_runs)
    totals["duration_seconds"] = round(float(totals["duration_seconds"]), 3)
    for values in phases.values():
        values["duration_seconds"] = round(float(values["duration_seconds"]), 3)
    averages = {
        key: round(float(value) / run_count, 3) if run_count else 0
        for key, value in totals.items()
    }
    return {
        "runs": run_count,
        "ready_runs": ready_runs,
        "ready_rate": round(ready_runs / run_count, 3) if run_count else 0.0,
        "totals": totals,
        "averages_per_run": averages,
        "phases": phases,
        "run_ids": included_runs,
    }
