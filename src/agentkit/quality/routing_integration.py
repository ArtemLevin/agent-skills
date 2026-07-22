from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from agentkit.runner import RunOutcome

from .hotspot_context import HotspotContextCompiler
from .integration import QualityAwareRunner
from .routing import QualityRoute, route_quality
from .routing_config import load_quality_routing_config
from .verification_plan import VerificationPlan, build_verification_plan


class RoutingAwareRunner(QualityAwareRunner):
    """Quality-aware runner that refines triage and verification before implementation."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._quality_route: QualityRoute | None = None
        self._verification_plan: VerificationPlan | None = None
        self._original_verification: Any = None
        self._original_workflow: Any = None

    def _task_packet(
        self,
        request: Any,
        triage: Any,
        graph: Any,
        baseline_head: str,
    ) -> dict[str, object]:
        packet = super()._task_packet(request, triage, graph, baseline_head)
        if self._quality_runtime is None:
            return packet

        state = self._quality_runtime[0]
        routing_config = load_quality_routing_config(self.project_root)
        context = None
        snapshot_payload: dict[str, Any] | None = None

        if routing_config.enabled and self._quality_baseline is not None:
            snapshot_path = self._quality_baseline.result.artifacts.snapshot_path
            try:
                raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
                snapshot_payload = raw if isinstance(raw, dict) else None
                context = HotspotContextCompiler(
                    self.project_root,
                    self.config.context,
                ).compile(
                    task=request.task,
                    run_id=state.run_id,
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._quality_warning = "; ".join(
                    item
                    for item in (
                        self._quality_warning,
                        f"Quality routing evidence failed: {exc}",
                    )
                    if item
                )

        route = route_quality(
            task=request.task,
            base_triage=triage,
            context=context,
            snapshot_payload=snapshot_payload,
            graph_output=str(getattr(graph, "output", "")),
            config=routing_config,
        )
        self._quality_route = route

        # The base runner creates triage before quality baseline capture. Mutating the
        # existing frozen result preserves one state machine while refining the exact
        # object subsequently used by approval, prompts, review, and completion.
        object.__setattr__(triage, "mode", route.effective_mode)
        object.__setattr__(triage, "risk_reasons", list(route.risk_reasons))
        object.__setattr__(triage, "selected_skills", list(route.selected_skills))
        self._state_write_json(state, "triage.json", triage.to_dict())
        self._state_write_json(state, "quality-route.json", route.to_dict())

        plan = build_verification_plan(
            self.project_root,
            self.config.verification,
            route,
        )
        self._verification_plan = plan
        self._state_write_json(state, "verification-plan.json", plan.to_dict())

        if self._original_verification is None:
            self._original_verification = self.config.verification
        object.__setattr__(
            self.config,
            "verification",
            plan.as_config(self.config.verification.timeout_seconds),
        )
        if route.approval_required:
            if self._original_workflow is None:
                self._original_workflow = self.config.workflow
            object.__setattr__(
                self.config,
                "workflow",
                replace(self.config.workflow, deep_requires_approval=True),
            )

        packet["mode"] = route.effective_mode.value
        packet["risk_reasons"] = list(route.risk_reasons)
        packet["selected_skills"] = list(route.selected_skills)
        packet["quality_route"] = route.summary()
        packet["verification_plan"] = {
            "path": f".agent/state/runs/{state.run_id}/verification-plan.json",
            "requirements": list(plan.requirements),
            "selected_commands": [
                item.to_dict() for item in plan.selected_commands
            ],
            "omitted_checks": list(plan.omitted_checks),
        }
        return packet

    def run(self, request: Any) -> RunOutcome:
        self._quality_route = None
        self._verification_plan = None
        self._original_verification = None
        self._original_workflow = None
        try:
            outcome = super().run(request)
            if outcome.completion is None or self._quality_route is None:
                return outcome
            residual = list(outcome.completion.residual_risks)
            residual.extend(self._quality_route.warnings)
            if self._verification_plan is not None:
                residual.extend(self._verification_plan.warnings)
                residual.extend(self._verification_plan.omitted_checks)
            completion = replace(
                outcome.completion,
                residual_risks=list(dict.fromkeys(residual)),
                quality_route=self._quality_route.summary(),
            )
            updated = replace(outcome, completion=completion)
            completion_path = (
                self.project_root
                / ".agent"
                / "state"
                / "runs"
                / outcome.run_id
                / "completion.json"
            )
            existing: dict[str, Any] = {}
            if completion_path.is_file():
                try:
                    raw = json.loads(completion_path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        existing = raw
                except (OSError, ValueError, json.JSONDecodeError):
                    existing = {}
            existing.update(completion.to_dict())
            completion_path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return updated
        finally:
            if self._original_verification is not None:
                object.__setattr__(
                    self.config,
                    "verification",
                    self._original_verification,
                )
            if self._original_workflow is not None:
                object.__setattr__(
                    self.config,
                    "workflow",
                    self._original_workflow,
                )
