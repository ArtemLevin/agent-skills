from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentkit.adapters import AgentAdapter, CommandAgentAdapter
from agentkit.models import CommandResult
from agentkit.quality.routing_integration import RoutingAwareRunner

from .base import MUTATING_PHASES, PromptEnvelope
from .config import (
    ModelRuntimeConfig,
    ModelTargetConfig,
    load_model_runtime_config,
    model_runtime_enabled,
)
from .openai import RETRYABLE_RETURN_CODE, OpenAIResponsesAdapter
from .router import ModelRoutePlan, build_route_plan

AdapterFactory = Callable[[ModelTargetConfig], AgentAdapter]


class ModelRoutingRunner(RoutingAwareRunner):
    """Select a bounded executor for each phase without widening mutation authority."""

    def __init__(
        self,
        *args: Any,
        adapter_factories: dict[str, AdapterFactory] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._model_config: ModelRuntimeConfig | None = None
        self._model_plan: ModelRoutePlan | None = None
        self._model_attempts: list[dict[str, Any]] = []
        self._adapter_factories = adapter_factories or {}

    def _ledger_provider(self, request: Any) -> str:
        if request.agent_override and request.route_override:
            raise ValueError("Use either agent_override or route_override, not both")
        if request.agent_override:
            return super()._ledger_provider(request)
        enabled = model_runtime_enabled(self.project_root)
        if request.route_override and not enabled:
            raise ValueError("--route requires models.enabled=true")
        if not enabled:
            return super()._ledger_provider(request)
        config = load_model_runtime_config(self.project_root, self.config.agent)
        self._model_config = config
        return "phase-routed"

    def _task_packet(
        self,
        request: Any,
        triage: Any,
        graph: Any,
        baseline_head: str,
    ) -> dict[str, object]:
        packet = super()._task_packet(request, triage, graph, baseline_head)
        if request.agent_override:
            return packet
        if self._model_config is None:
            return packet
        config = self._model_config
        plan = build_route_plan(
            config,
            mode=triage.mode,
            route_override=request.route_override,
        )
        self._model_plan = plan
        packet["model_route"] = plan.to_dict()
        if self._quality_runtime is not None:
            state = self._quality_runtime[0]
            self._state_write_json(state, "model-route.json", plan.to_dict())
        return packet

    def _adapter_for_target(self, target: ModelTargetConfig) -> AgentAdapter:
        factory = self._adapter_factories.get(target.provider)
        if factory is not None:
            return factory(target)
        if target.provider == "openai":
            return OpenAIResponsesAdapter(target)
        return CommandAgentAdapter(
            list(target.command),
            timeout_seconds=target.timeout_seconds,
            policy=self.policy,
            provider=target.platform or "cli",
        )

    def _execution_for_phase(
        self,
        phase: str,
        *,
        request: Any,
        triage: object,
    ) -> tuple[AgentAdapter, str]:
        if self._adapter_override is not None or request.agent_override or self._model_plan is None:
            return super()._execution_for_phase(
                phase,
                request=request,
                triage=triage,
            )
        decision = self._model_plan.phases[phase]
        assert self._model_config is not None
        target = self._model_config.targets[decision.target]
        return self._adapter_for_target(target), target.provider

    @staticmethod
    def _attempt(
        *,
        phase: str,
        target: ModelTargetConfig,
        result: CommandResult | None,
        attempt: int,
        kind: str,
    ) -> dict[str, Any]:
        return {
            "phase": phase,
            "target": target.name,
            "provider": target.provider,
            "model": target.model,
            "attempt": attempt,
            "kind": kind,
            "returncode": result.returncode if result is not None else None,
            "passed": result.passed if result is not None else False,
            "duration_seconds": result.duration_seconds if result is not None else 0.0,
            "usage": result.usage.to_dict() if result is not None and result.usage else None,
        }

    def _write_attempts(self, state: Any) -> None:
        self._state_write_json(
            state,
            "model-attempts.json",
            {"version": 1, "attempts": self._model_attempts},
        )

    def _execute_agent(self, **kwargs: Any):
        phase = str(kwargs["phase"])
        state = kwargs["state"]
        prompt = str(kwargs["prompt"])
        if self._model_plan is None or self._model_config is None:
            return super()._execute_agent(**kwargs)

        decision = self._model_plan.phases[phase]
        target = self._model_config.targets[decision.target]
        envelope = PromptEnvelope.from_prompt(prompt)
        self._state_write_json(
            state,
            f"prompt-prefix-{phase}.json",
            {
                **envelope.to_metadata(),
                "phase": phase,
                "target": target.name,
                "provider": target.provider,
                "model": target.model,
            },
        )

        attempt_number = 1
        result, budget_status, reason = super()._execute_agent(**kwargs)
        self._model_attempts.append(
            self._attempt(
                phase=phase,
                target=target,
                result=result,
                attempt=attempt_number,
                kind="primary",
            )
        )
        self._write_attempts(state)
        if result is None or result.passed or budget_status.hard_limits_exceeded:
            return result, budget_status, reason

        retries = 0
        while (
            phase not in MUTATING_PHASES
            and result.returncode == RETRYABLE_RETURN_CODE
            and retries < self._model_config.max_retries
        ):
            retries += 1
            attempt_number += 1
            result, budget_status, reason = super()._execute_agent(**kwargs)
            self._model_attempts.append(
                self._attempt(
                    phase=phase,
                    target=target,
                    result=result,
                    attempt=attempt_number,
                    kind="retry",
                )
            )
            self._write_attempts(state)
            if result is None or result.passed or budget_status.hard_limits_exceeded:
                return result, budget_status, reason

        # A provider switch after a mutating phase could compound an unknown partial diff.
        if phase in MUTATING_PHASES:
            return result, budget_status, reason

        for fallback_name in decision.fallbacks[: self._model_config.max_fallbacks]:
            fallback = self._model_config.targets[fallback_name]
            attempt_number += 1
            fallback_kwargs = dict(kwargs)
            fallback_kwargs["adapter"] = self._adapter_for_target(fallback)
            fallback_kwargs["provider"] = fallback.provider
            result, budget_status, reason = super()._execute_agent(**fallback_kwargs)
            self._model_attempts.append(
                self._attempt(
                    phase=phase,
                    target=fallback,
                    result=result,
                    attempt=attempt_number,
                    kind="fallback",
                )
            )
            self._write_attempts(state)
            if result is None or result.passed or budget_status.hard_limits_exceeded:
                return result, budget_status, reason
        return result, budget_status, reason

    def run(self, request: Any):
        self._model_config = None
        self._model_plan = None
        self._model_attempts = []
        return super().run(request)
