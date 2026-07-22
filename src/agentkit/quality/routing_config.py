from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ROUTING_TOML = r'''

# BEGIN AGENTKIT QUALITY ROUTING
[quality.routing]
enabled = true
allow_mode_escalation = true
require_approval_on_crisis = true
characterization_complexity = 40
edge_case_complexity = 30
high_refactoring_pressure = 60
high_overengineering_pressure = 60
high_fan_in = 10
high_fan_out = 10
high_centrality = 0.75
# END AGENTKIT QUALITY ROUTING
'''


@dataclass(frozen=True)
class QualityRoutingConfig:
    enabled: bool = True
    allow_mode_escalation: bool = True
    require_approval_on_crisis: bool = True
    characterization_complexity: float = 40.0
    edge_case_complexity: float = 30.0
    high_refactoring_pressure: float = 60.0
    high_overengineering_pressure: float = 60.0
    high_fan_in: float = 10.0
    high_fan_out: float = 10.0
    high_centrality: float = 0.75


def _non_negative(value: Any, *, name: str, default: float) -> float:
    parsed = float(default if value is None else value)
    if parsed < 0:
        raise ValueError(f"quality.routing.{name} must be zero or positive")
    return parsed


def load_quality_routing_config(project_root: Path) -> QualityRoutingConfig:
    path = project_root / ".agent" / "agentkit.toml"
    if not path.is_file():
        return QualityRoutingConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    quality = data.get("quality", {})
    if not isinstance(quality, dict):
        raise ValueError("Configuration section [quality] must be a table")
    routing = quality.get("routing", {})
    if not isinstance(routing, dict):
        raise ValueError("Configuration section [quality.routing] must be a table")
    return QualityRoutingConfig(
        enabled=bool(routing.get("enabled", True)),
        allow_mode_escalation=bool(routing.get("allow_mode_escalation", True)),
        require_approval_on_crisis=bool(
            routing.get("require_approval_on_crisis", True)
        ),
        characterization_complexity=_non_negative(
            routing.get("characterization_complexity"),
            name="characterization_complexity",
            default=40,
        ),
        edge_case_complexity=_non_negative(
            routing.get("edge_case_complexity"),
            name="edge_case_complexity",
            default=30,
        ),
        high_refactoring_pressure=_non_negative(
            routing.get("high_refactoring_pressure"),
            name="high_refactoring_pressure",
            default=60,
        ),
        high_overengineering_pressure=_non_negative(
            routing.get("high_overengineering_pressure"),
            name="high_overengineering_pressure",
            default=60,
        ),
        high_fan_in=_non_negative(
            routing.get("high_fan_in"), name="high_fan_in", default=10
        ),
        high_fan_out=_non_negative(
            routing.get("high_fan_out"), name="high_fan_out", default=10
        ),
        high_centrality=_non_negative(
            routing.get("high_centrality"), name="high_centrality", default=0.75
        ),
    )


def ensure_quality_routing_config(project_root: Path) -> Path:
    path = project_root / ".agent" / "agentkit.toml"
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist")
    text = path.read_text(encoding="utf-8")
    if "[quality.routing]" not in text:
        path.write_text(text.rstrip() + DEFAULT_ROUTING_TOML, encoding="utf-8")
    return path
