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
baseline_strategy = "run_start"
base_branch = "main"
baseline_file = ""
unavailable_policy = "warn"

[quality.absolute]
score = 0
rp = 0
op = 0
density = 0.0

[quality.delta]
score = 5
rp = 5
op = 5
density = 3.0
new_critical_hotspots = 0
# END AGENTKIT QUALITY
'''


@dataclass(frozen=True)
class AbsoluteThresholds:
    score: float = 0.0
    rp: float = 0.0
    op: float = 0.0
    density: float = 0.0


@dataclass(frozen=True)
class DeltaThresholds:
    score: float = 5.0
    rp: float = 5.0
    op: float = 5.0
    density: float = 3.0
    new_critical_hotspots: int | None = 0


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
    baseline_strategy: str = "run_start"
    base_branch: str = "main"
    baseline_file: str = ""
    unavailable_policy: str = "warn"
    absolute: AbsoluteThresholds = field(default_factory=AbsoluteThresholds)
    delta: DeltaThresholds = field(default_factory=DeltaThresholds)


def _section(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("quality", {})
    if not isinstance(raw, dict):
        raise ValueError("Configuration section [quality] must be a table")
    return raw


def _table(value: Any, *, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"quality.{name} must be a table")
    return value


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


def _non_negative_float(value: Any, *, name: str, default: float) -> float:
    parsed = float(default if value is None else value)
    if parsed < 0:
        raise ValueError(f"quality.{name} must be zero or positive")
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
    if mode not in {"report", "warn", "enforce"}:
        raise ValueError("quality.mode must be report, warn, or enforce")

    provider = str(quality.get("provider", "strictacode")).lower()
    if provider != "strictacode":
        raise ValueError("AgentKit 0.6 supports only quality.provider=strictacode")

    baseline_strategy = str(quality.get("baseline_strategy", "run_start")).lower()
    if baseline_strategy not in {"run_start", "merge_base", "file", "none"}:
        raise ValueError(
            "quality.baseline_strategy must be run_start, merge_base, file, or none"
        )

    unavailable_policy = str(quality.get("unavailable_policy", "warn")).lower()
    if unavailable_policy not in {"allow", "warn", "stop"}:
        raise ValueError("quality.unavailable_policy must be allow, warn, or stop")

    command = _strings(
        quality.get("command", ["strictacode"]),
        name="command",
        default=["strictacode"],
    )
    if not command:
        raise ValueError("quality.command must be a non-empty argv array")

    absolute = _table(quality.get("absolute"), name="absolute")
    delta = _table(quality.get("delta"), name="delta")
    raw_new_critical = delta.get("new_critical_hotspots", 0)
    new_critical = (
        None
        if raw_new_critical is None
        else _positive(
            raw_new_critical,
            name="delta.new_critical_hotspots",
            default=0,
        )
    )

    baseline_file = str(quality.get("baseline_file", "")).strip()
    if baseline_strategy == "file" and not baseline_file:
        raise ValueError(
            "quality.baseline_file is required when baseline_strategy=file"
        )

    return QualityConfig(
        enabled=bool(quality.get("enabled", True)),
        provider=provider,
        required=bool(quality.get("required", False)),
        mode=mode,
        details_policy=details_policy,
        cache_enabled=bool(quality.get("cache_enabled", True)),
        cache_ttl_seconds=_positive(
            quality.get("cache_ttl_seconds"),
            name="cache_ttl_seconds",
            default=86400,
        ),
        timeout_seconds=_positive(
            quality.get("timeout_seconds"),
            name="timeout_seconds",
            default=900,
            allow_zero=False,
        ),
        command=command,
        max_packages=_positive(
            quality.get("max_packages"), name="max_packages", default=5
        ),
        max_modules=_positive(
            quality.get("max_modules"), name="max_modules", default=5
        ),
        max_classes=_positive(
            quality.get("max_classes"), name="max_classes", default=10
        ),
        max_methods=_positive(
            quality.get("max_methods"), name="max_methods", default=15
        ),
        max_functions=_positive(
            quality.get("max_functions"), name="max_functions", default=15
        ),
        include=_strings(quality.get("include", []), name="include", default=[]),
        exclude=_strings(
            quality.get(
                "exclude",
                ["vendor", "generated", ".venv", "node_modules"],
            ),
            name="exclude",
            default=["vendor", "generated", ".venv", "node_modules"],
        ),
        baseline_strategy=baseline_strategy,
        base_branch=str(quality.get("base_branch", "main")).strip() or "main",
        baseline_file=baseline_file,
        unavailable_policy=unavailable_policy,
        absolute=AbsoluteThresholds(
            score=_non_negative_float(
                absolute.get("score"), name="absolute.score", default=0
            ),
            rp=_non_negative_float(
                absolute.get("rp"), name="absolute.rp", default=0
            ),
            op=_non_negative_float(
                absolute.get("op"), name="absolute.op", default=0
            ),
            density=_non_negative_float(
                absolute.get("density"), name="absolute.density", default=0
            ),
        ),
        delta=DeltaThresholds(
            score=_non_negative_float(
                delta.get("score"), name="delta.score", default=5
            ),
            rp=_non_negative_float(
                delta.get("rp"), name="delta.rp", default=5
            ),
            op=_non_negative_float(
                delta.get("op"), name="delta.op", default=5
            ),
            density=_non_negative_float(
                delta.get("density"), name="delta.density", default=3
            ),
            new_critical_hotspots=new_critical,
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

    scalar_lines = [
        'baseline_strategy = "run_start"',
        'base_branch = "main"',
        'baseline_file = ""',
        'unavailable_policy = "warn"',
    ]
    lines = text.splitlines()
    quality_index = next(
        index
        for index, line in enumerate(lines)
        if line.strip() == "[quality]"
    )
    section_end = len(lines)
    for index in range(quality_index + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section_end = index
            break
    quality_section = "\n".join(lines[quality_index:section_end])
    missing_scalars = [
        line
        for line in scalar_lines
        if line.split(" = ", 1)[0] not in quality_section
    ]
    if missing_scalars:
        lines[section_end:section_end] = missing_scalars
    text = "\n".join(lines).rstrip() + "\n"

    tables = ""
    if "[quality.absolute]" not in text:
        tables += (
            "\n[quality.absolute]\n"
            "score = 0\nrp = 0\nop = 0\ndensity = 0.0\n"
        )
    if "[quality.delta]" not in text:
        tables += (
            "\n[quality.delta]\n"
            "score = 5\nrp = 5\nop = 5\ndensity = 3.0\n"
            "new_critical_hotspots = 0\n"
        )
    if tables:
        text = text.rstrip() + "\n" + tables
    path.write_text(text, encoding="utf-8")
    return path
