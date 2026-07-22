from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_QUALITY_TOML = r'''

# BEGIN AGENTKIT QUALITY
[quality]
enabled = true
provider = "strictacode"
required = false
mode = "report"
details_policy = "on_warning"
cache_enabled = true
cache_ttl_seconds = 86400
timeout_seconds = 900
command = ["strictacode"]
max_packages = 5
max_modules = 5
max_classes = 10
max_methods = 15
max_functions = 15
include = []
exclude = ["vendor", "generated", ".venv", "node_modules"]
# END AGENTKIT QUALITY
'''


@dataclass(frozen=True)
class QualityConfig:
    enabled: bool = True
    provider: str = "strictacode"
    required: bool = False
    mode: str = "report"
    details_policy: str = "on_warning"
    cache_enabled: bool = True
    cache_ttl_seconds: int = 86400
    timeout_seconds: int = 900
    command: list[str] = field(default_factory=lambda: ["strictacode"])
    max_packages: int = 5
    max_modules: int = 5
    max_classes: int = 10
    max_methods: int = 15
    max_functions: int = 15
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(
        default_factory=lambda: ["vendor", "generated", ".venv", "node_modules"]
    )


def _section(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("quality", {})
    if not isinstance(raw, dict):
        raise ValueError("Configuration section [quality] must be a table")
    return raw


def _strings(value: Any, *, name: str, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"quality.{name} must be an array of strings")
    return list(value)


def _positive(value: Any, *, name: str, default: int, allow_zero: bool = True) -> int:
    parsed = int(default if value is None else value)
    if parsed < 0 or (not allow_zero and parsed == 0):
        qualifier = "positive" if not allow_zero else "zero or positive"
        raise ValueError(f"quality.{name} must be {qualifier}")
    return parsed


def load_quality_config(project_root: Path) -> QualityConfig:
    path = project_root / ".agent" / "agentkit.toml"
    if not path.is_file():
        return QualityConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    quality = _section(data)
    details_policy = str(quality.get("details_policy", "on_warning")).lower()
    if details_policy not in {"never", "on_warning", "always"}:
        raise ValueError("quality.details_policy must be never, on_warning, or always")
    mode = str(quality.get("mode", "report")).lower()
    if mode != "report":
        raise ValueError("AgentKit 0.5 supports only quality.mode=report")
    provider = str(quality.get("provider", "strictacode")).lower()
    if provider != "strictacode":
        raise ValueError("AgentKit 0.5 supports only quality.provider=strictacode")
    command = _strings(
        quality.get("command", ["strictacode"]),
        name="command",
        default=["strictacode"],
    )
    if not command:
        raise ValueError("quality.command must be a non-empty argv array")
    return QualityConfig(
        enabled=bool(quality.get("enabled", True)),
        provider=provider,
        required=bool(quality.get("required", False)),
        mode=mode,
        details_policy=details_policy,
        cache_enabled=bool(quality.get("cache_enabled", True)),
        cache_ttl_seconds=_positive(
            quality.get("cache_ttl_seconds"), name="cache_ttl_seconds", default=86400
        ),
        timeout_seconds=_positive(
            quality.get("timeout_seconds"),
            name="timeout_seconds",
            default=900,
            allow_zero=False,
        ),
        command=command,
        max_packages=_positive(quality.get("max_packages"), name="max_packages", default=5),
        max_modules=_positive(quality.get("max_modules"), name="max_modules", default=5),
        max_classes=_positive(quality.get("max_classes"), name="max_classes", default=10),
        max_methods=_positive(quality.get("max_methods"), name="max_methods", default=15),
        max_functions=_positive(quality.get("max_functions"), name="max_functions", default=15),
        include=_strings(quality.get("include", []), name="include", default=[]),
        exclude=_strings(
            quality.get("exclude", ["vendor", "generated", ".venv", "node_modules"]),
            name="exclude",
            default=["vendor", "generated", ".venv", "node_modules"],
        ),
    )


def ensure_quality_config(project_root: Path) -> Path:
    path = project_root / ".agent" / "agentkit.toml"
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist")
    text = path.read_text(encoding="utf-8")
    if "[quality]" not in text:
        path.write_text(text.rstrip() + DEFAULT_QUALITY_TOML, encoding="utf-8")
    return path
