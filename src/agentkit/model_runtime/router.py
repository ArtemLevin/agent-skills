from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agentkit.models import RunMode

from .base import MUTATING_PHASES
from .config import ModelRuntimeConfig, ModelTargetConfig


@dataclass(frozen=True)
class PhaseRoute:
    phase: str
    target: str
    provider: str
    model: str
    reasons: tuple[str, ...]
    fallbacks: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelRoutePlan:
    route: str
    phases: dict[str, PhaseRoute]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "route": self.route,
            "phases": {name: phase.to_dict() for name, phase in self.phases.items()},
            "warnings": list(self.warnings),
        }


def build_route_plan(
    config: ModelRuntimeConfig,
    *,
    mode: RunMode,
    route_override: str | None,
) -> ModelRoutePlan:
    inferred_route = mode.value if mode.value in config.routes else config.default_route
    route_name = route_override or inferred_route
    configured = config.routes.get(route_name, {})
    if route_override and route_name not in config.routes:
        raise ValueError(f"Unknown model route '{route_name}'")
    phases: dict[str, PhaseRoute] = {}
    warnings: list[str] = []
    for phase in ("plan", "implementation", "review", "targeted_fix"):
        target_name = configured.get(phase, "legacy-cli")
        target = config.targets.get(target_name)
        if target is None:
            raise ValueError(
                f"Route '{route_name}' phase '{phase}' references unknown "
                f"target '{target_name}'"
            )
        reasons = [f"route={route_name}", f"task_mode={mode.value}", f"phase={phase}"]
        if phase in MUTATING_PHASES and not target.capabilities.local_workspace_mutation:
            raise ValueError(
                f"Route '{route_name}' phase '{phase}' target '{target_name}' "
                "cannot mutate the local workspace"
            )
        if phase == "review" and target.provider == "openai" and not target.structured_outputs:
            raise ValueError(
                f"Route '{route_name}' review target '{target_name}' must enable "
                "structured outputs"
            )
        reasons.append(
            "local workspace mutation required"
            if phase in MUTATING_PHASES
            else "read-only phase"
        )
        configured_fallbacks = config.fallbacks.get(phase, ())[: config.max_fallbacks]
        if phase in MUTATING_PHASES and configured_fallbacks:
            warnings.append(
                f"Fallbacks for mutating phase '{phase}' are ignored to avoid "
                "compounding a partial diff"
            )
            fallbacks: tuple[str, ...] = ()
        else:
            fallbacks = configured_fallbacks
            for fallback_name in fallbacks:
                fallback = config.targets.get(fallback_name)
                if fallback is None:
                    raise ValueError(
                        f"Route '{route_name}' phase '{phase}' references unknown "
                        f"fallback '{fallback_name}'"
                    )
                if (
                    phase == "review"
                    and fallback.provider == "openai"
                    and not fallback.structured_outputs
                ):
                    raise ValueError(
                        f"Route '{route_name}' review fallback '{fallback_name}' must "
                        "enable structured outputs"
                    )
        phases[phase] = PhaseRoute(
            phase=phase,
            target=target.name,
            provider=target.provider,
            model=target.model,
            reasons=tuple(reasons),
            fallbacks=fallbacks,
        )
    return ModelRoutePlan(route=route_name, phases=phases, warnings=tuple(warnings))


def target_summary(target: ModelTargetConfig) -> dict[str, Any]:
    return {
        "name": target.name,
        "provider": target.provider,
        "model": target.model,
        "platform": target.platform,
        "capabilities": target.capabilities.to_dict(),
    }
