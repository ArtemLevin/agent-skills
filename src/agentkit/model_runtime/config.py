from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentkit.config import AgentConfig

from .base import AgentCapabilities

_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_PHASES = frozenset({"plan", "implementation", "review", "targeted_fix"})
_REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh"})


@dataclass(frozen=True)
class ModelTargetConfig:
    name: str
    provider: str
    model: str = ""
    platform: str = ""
    command: tuple[str, ...] = ()
    api_key_env: str = "OPENAI_API_KEY"
    timeout_seconds: int = 300
    store: bool = False
    structured_outputs: bool = False
    prompt_caching: bool = True
    reasoning_effort: str = ""

    @property
    def capabilities(self) -> AgentCapabilities:
        if self.provider == "cli":
            return AgentCapabilities(
                local_workspace_mutation=True,
                read_only_mode=True,
            )
        return AgentCapabilities(
            structured_outputs=self.structured_outputs,
            exact_usage=True,
            prompt_caching=self.prompt_caching,
            read_only_mode=True,
            reasoning_control=True,
        )


@dataclass(frozen=True)
class ModelRuntimeConfig:
    enabled: bool = False
    default_route: str = "standard"
    max_retries: int = 1
    max_fallbacks: int = 1
    routes: dict[str, dict[str, str]] = field(default_factory=dict)
    targets: dict[str, ModelTargetConfig] = field(default_factory=dict)
    fallbacks: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _table(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a TOML table")
    return value


def _bounded_int(value: Any, *, name: str, default: int, maximum: int) -> int:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise ValueError(f"{name} must be an integer")
    parsed = default if value is None else value
    if parsed < 0 or parsed > maximum:
        raise ValueError(f"{name} must be between 0 and {maximum}")
    return parsed


def _positive_int(value: Any, *, name: str, default: int) -> int:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise ValueError(f"{name} must be a positive integer")
    parsed = default if value is None else value
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _boolean(value: Any, *, name: str, default: bool) -> bool:
    parsed = default if value is None else value
    if not isinstance(parsed, bool):
        raise ValueError(f"{name} must be a boolean")
    return parsed


def _strings(value: Any, *, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{name} must be an array of non-empty strings")
    return tuple(value)


def model_runtime_enabled(project_root: Path) -> bool:
    path = project_root / ".agent" / "agentkit.toml"
    if not path.is_file():
        return False
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    models = _table(data.get("models"), "models")
    return _boolean(models.get("enabled"), name="models.enabled", default=False)


def load_model_runtime_config(project_root: Path, agent: AgentConfig) -> ModelRuntimeConfig:
    path = project_root / ".agent" / "agentkit.toml"
    if not path.is_file():
        return ModelRuntimeConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    models = _table(data.get("models"), "models")
    enabled = _boolean(models.get("enabled"), name="models.enabled", default=False)

    targets: dict[str, ModelTargetConfig] = {
        "legacy-cli": ModelTargetConfig(
            name="legacy-cli",
            provider="cli",
            platform=agent.platform,
            command=tuple(agent.command),
            timeout_seconds=agent.timeout_seconds,
        )
    }
    for target_name, raw in _table(models.get("targets"), "models.targets").items():
        target = _table(raw, f"models.targets.{target_name}")
        provider = str(target.get("provider", "")).lower()
        if provider not in {"cli", "openai"}:
            raise ValueError(
                f"models.targets.{target_name}.provider must be cli or openai"
            )
        model_value = target.get("model", "")
        if not isinstance(model_value, str):
            raise ValueError(f"models.targets.{target_name}.model must be a string")
        model = model_value
        api_key_env_value = target.get("api_key_env", "OPENAI_API_KEY")
        if not isinstance(api_key_env_value, str):
            raise ValueError(f"models.targets.{target_name}.api_key_env must be a string")
        api_key_env = api_key_env_value
        if provider == "openai" and not model:
            raise ValueError(f"models.targets.{target_name}.model is required")
        if provider == "openai" and not _ENV_NAME.fullmatch(api_key_env):
            raise ValueError(
                f"models.targets.{target_name}.api_key_env must be an environment variable name"
            )
        command = _strings(target.get("command"), name=f"models.targets.{target_name}.command")
        if provider == "cli" and not command:
            command = tuple(agent.command)
        reasoning_effort = target.get("reasoning_effort", "")
        if not isinstance(reasoning_effort, str) or (
            reasoning_effort and reasoning_effort not in _REASONING_EFFORTS
        ):
            raise ValueError(
                f"models.targets.{target_name}.reasoning_effort must be one of "
                f"{sorted(_REASONING_EFFORTS)}"
            )
        targets[str(target_name)] = ModelTargetConfig(
            name=str(target_name),
            provider=provider,
            model=model,
            platform=str(target.get("platform", agent.platform if provider == "cli" else "")),
            command=command,
            api_key_env=api_key_env,
            timeout_seconds=_positive_int(
                target.get("timeout_seconds"),
                name=f"models.targets.{target_name}.timeout_seconds",
                default=300,
            ),
            store=_boolean(
                target.get("store"),
                name=f"models.targets.{target_name}.store",
                default=False,
            ),
            structured_outputs=_boolean(
                target.get("structured_outputs"),
                name=f"models.targets.{target_name}.structured_outputs",
                default=provider == "openai",
            ),
            prompt_caching=_boolean(
                target.get("prompt_caching"),
                name=f"models.targets.{target_name}.prompt_caching",
                default=provider == "openai",
            ),
            reasoning_effort=reasoning_effort,
        )

    routes: dict[str, dict[str, str]] = {}
    for route_name, raw in _table(models.get("routes"), "models.routes").items():
        route = _table(raw, f"models.routes.{route_name}")
        unknown = set(route) - _PHASES
        if unknown:
            raise ValueError(
                f"models.routes.{route_name} contains unknown phases: {sorted(unknown)}"
            )
        if not all(isinstance(value, str) and value for value in route.values()):
            raise ValueError(
                f"models.routes.{route_name} phase targets must be non-empty strings"
            )
        routes[str(route_name)] = {str(phase): target for phase, target in route.items()}

    fallbacks = {
        str(phase): _strings(value, name=f"models.fallback.{phase}")
        for phase, value in _table(models.get("fallback"), "models.fallback").items()
    }
    unknown_fallbacks = set(fallbacks) - _PHASES
    if unknown_fallbacks:
        raise ValueError(f"models.fallback contains unknown phases: {sorted(unknown_fallbacks)}")

    default_route = models.get("default_route", "standard")
    if not isinstance(default_route, str) or not default_route:
        raise ValueError("models.default_route must be a non-empty string")
    config = ModelRuntimeConfig(
        enabled=enabled,
        default_route=default_route,
        max_retries=_bounded_int(
            models.get("max_retries"), name="models.max_retries", default=1, maximum=3
        ),
        max_fallbacks=_bounded_int(
            models.get("max_fallbacks"), name="models.max_fallbacks", default=1, maximum=3
        ),
        routes=routes,
        targets=targets,
        fallbacks=fallbacks,
    )
    if enabled:
        if routes and config.default_route not in routes:
            raise ValueError(
                f"models.default_route references unknown route: {config.default_route}"
            )
        for route_name, route in routes.items():
            missing = sorted(set(route.values()) - set(targets))
            if missing:
                raise ValueError(
                    f"models.routes.{route_name} references unknown targets: {missing}"
                )
        missing_fallbacks = sorted(
            {item for values in fallbacks.values() for item in values} - set(targets)
        )
        if missing_fallbacks:
            raise ValueError(f"models.fallback references unknown targets: {missing_fallbacks}")
    return config
