from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_EVAL_TOML = r'''

# BEGIN AGENTKIT EVALS
[eval]
default_repetitions = 1
max_repetitions = 10
command_timeout_seconds = 900
keep_workspaces = false
report_limit = 50

[eval.regression]
acceptance_rate_drop = 0.0
ready_rate_drop = 0.0
quality_gate_pass_rate_drop = 0.0
agent_calls_increase = 1.0
duration_increase_percent = 25.0
new_critical_hotspots_increase = 0.0
# END AGENTKIT EVALS
'''


@dataclass(frozen=True)
class RegressionThresholds:
    acceptance_rate_drop: float = 0.0
    ready_rate_drop: float = 0.0
    quality_gate_pass_rate_drop: float = 0.0
    agent_calls_increase: float = 1.0
    duration_increase_percent: float = 25.0
    new_critical_hotspots_increase: float = 0.0


@dataclass(frozen=True)
class EvaluationConfig:
    default_repetitions: int = 1
    max_repetitions: int = 10
    command_timeout_seconds: int = 900
    keep_workspaces: bool = False
    report_limit: int = 50
    regression: RegressionThresholds = field(default_factory=RegressionThresholds)


def _positive_int(value: Any, *, name: str, default: int) -> int:
    parsed = int(default if value is None else value)
    if parsed <= 0:
        raise ValueError(f"eval.{name} must be positive")
    return parsed


def _non_negative(value: Any, *, name: str, default: float) -> float:
    parsed = float(default if value is None else value)
    if parsed < 0:
        raise ValueError(f"eval.regression.{name} must be zero or positive")
    return parsed


def load_evaluation_config(project_root: Path) -> EvaluationConfig:
    path = project_root / ".agent" / "agentkit.toml"
    if not path.is_file():
        return EvaluationConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    raw = data.get("eval", {})
    if not isinstance(raw, dict):
        raise ValueError("Configuration section [eval] must be a table")
    regression = raw.get("regression", {})
    if not isinstance(regression, dict):
        raise ValueError("Configuration section [eval.regression] must be a table")
    default_repetitions = _positive_int(
        raw.get("default_repetitions"), name="default_repetitions", default=1
    )
    max_repetitions = _positive_int(
        raw.get("max_repetitions"), name="max_repetitions", default=10
    )
    if default_repetitions > max_repetitions:
        raise ValueError("eval.default_repetitions cannot exceed eval.max_repetitions")
    return EvaluationConfig(
        default_repetitions=default_repetitions,
        max_repetitions=max_repetitions,
        command_timeout_seconds=_positive_int(
            raw.get("command_timeout_seconds"),
            name="command_timeout_seconds",
            default=900,
        ),
        keep_workspaces=bool(raw.get("keep_workspaces", False)),
        report_limit=_positive_int(raw.get("report_limit"), name="report_limit", default=50),
        regression=RegressionThresholds(
            acceptance_rate_drop=_non_negative(
                regression.get("acceptance_rate_drop"),
                name="acceptance_rate_drop",
                default=0.0,
            ),
            ready_rate_drop=_non_negative(
                regression.get("ready_rate_drop"),
                name="ready_rate_drop",
                default=0.0,
            ),
            quality_gate_pass_rate_drop=_non_negative(
                regression.get("quality_gate_pass_rate_drop"),
                name="quality_gate_pass_rate_drop",
                default=0.0,
            ),
            agent_calls_increase=_non_negative(
                regression.get("agent_calls_increase"),
                name="agent_calls_increase",
                default=1.0,
            ),
            duration_increase_percent=_non_negative(
                regression.get("duration_increase_percent"),
                name="duration_increase_percent",
                default=25.0,
            ),
            new_critical_hotspots_increase=_non_negative(
                regression.get("new_critical_hotspots_increase"),
                name="new_critical_hotspots_increase",
                default=0.0,
            ),
        ),
    )


def ensure_evaluation_config(project_root: Path) -> Path:
    path = project_root / ".agent" / "agentkit.toml"
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist")
    text = path.read_text(encoding="utf-8")
    if "[eval]" not in text:
        path.write_text(text.rstrip() + DEFAULT_EVAL_TOML, encoding="utf-8")
        return path
    additions = ""
    if "[eval.regression]" not in text:
        additions += DEFAULT_EVAL_TOML.split("[eval.regression]", 1)[1]
        additions = "\n[eval.regression]" + additions
    if additions:
        path.write_text(text.rstrip() + additions, encoding="utf-8")
    return path
