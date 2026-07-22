from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from agentkit.models import Stage
from agentkit.runner import AgentKitError, AgentKitRunner, RunOutcome

from .baseline import BaselineCapture
from .config import QualityConfig, load_quality_config
from .lifecycle import QualityCycleResult, QualityLifecycle


class QualityAwareRunner(AgentKitRunner):
    """AgentKit runner extension with before/after quality evidence and gates."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._quality_runtime: tuple[Any, Any, Any, Any] | None = None
        self._quality_config: QualityConfig | None = None
        self._quality_lifecycle: QualityLifecycle | None = None
        self._quality_baseline: BaselineCapture | None = None
        self._quality_warning = ""

    def _tool_observer(
        self,
        state: Any,
        ledger: Any,
        controller: Any,
    ):
        observer = super()._tool_observer(state, ledger, controller)
        self._quality_runtime = (state, observer, ledger, controller)
        return observer

    @staticmethod
    def _relative(project_root: Path, path: Path) -> str:
        try:
            return path.relative_to(project_root).as_posix()
        except ValueError:
            return str(path)


    @staticmethod
    def _state_write_json(state: Any, name: str, payload: object) -> None:
        writer = getattr(state, "write_json", None)
        if callable(writer):
            writer(name, payload)
            return
        path = Path(state.directory) / name
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_baseline_metadata(
        self,
        state: Any,
        baseline: BaselineCapture,
    ) -> None:
        self._state_write_json(
            state,
            "quality-baseline.json",
            {
                "version": 1,
                "strategy": baseline.strategy,
                "merge_base": baseline.merge_base,
                "worktree_path": baseline.worktree_path,
                "warnings": list(baseline.warnings),
                "snapshot": self._relative(
                    self.project_root,
                    baseline.result.artifacts.snapshot_path,
                ),
            },
        )

    def _task_packet(
        self,
        request: Any,
        triage: Any,
        graph: Any,
        baseline_head: str,
    ) -> dict[str, object]:
        packet = super()._task_packet(
            request,
            triage,
            graph,
            baseline_head,
        )
        if self._quality_runtime is None:
            return packet

        quality_config = load_quality_config(self.project_root)
        self._quality_config = quality_config
        if not quality_config.enabled:
            packet["quality"] = {
                "availability": "unavailable",
                "provider": quality_config.provider,
                "warning": "Quality diagnostics are disabled",
            }
            return packet

        state = self._quality_runtime[0]
        observer = self._quality_runtime[1]
        lifecycle = QualityLifecycle(
            self.project_root,
            quality_config,
            self.config.context,
            self.config.security,
            observer=observer,
        )
        self._quality_lifecycle = lifecycle
        try:
            baseline = lifecycle.capture_baseline(state.directory)
        except Exception as exc:
            message = f"Quality baseline failed: {exc}"
            self._quality_warning = message
            packet["quality"] = {
                "availability": "failed",
                "provider": quality_config.provider,
                "warning": message,
                "baseline_strategy": quality_config.baseline_strategy,
            }
            self._state_write_json(
                state,
                "quality-baseline.json",
                {
                    "version": 1,
                    "strategy": quality_config.baseline_strategy,
                    "status": "failed",
                    "warning": message,
                },
            )
            if quality_config.required or quality_config.unavailable_policy == "stop":
                raise AgentKitError(message) from exc
            return packet

        self._quality_baseline = baseline
        self._write_baseline_metadata(state, baseline)
        result = baseline.result
        packet["quality"] = result.snapshot.task_packet_entry(
            self._relative(
                self.project_root,
                result.artifacts.snapshot_path,
            ),
            self._relative(
                self.project_root,
                result.artifacts.hotspots_path,
            ),
        )
        packet["quality"]["baseline_strategy"] = baseline.strategy
        packet["quality"]["merge_base"] = baseline.merge_base

        warning = result.warning
        if baseline.warnings:
            warning = "; ".join(
                item
                for item in (warning, *baseline.warnings)
                if item
            )
        self._quality_warning = warning
        if quality_config.required and not result.snapshot.usable:
            raise AgentKitError(
                "Required quality provider is not usable: "
                + (warning or result.snapshot.availability.value)
            )
        if (
            quality_config.unavailable_policy == "stop"
            and not result.snapshot.usable
        ):
            raise AgentKitError(
                "Quality unavailable_policy=stop: "
                + (warning or result.snapshot.availability.value)
            )
        return packet

    def _persist_completion(
        self,
        outcome: RunOutcome,
        completion: Any,
        *,
        cycle: QualityCycleResult | None = None,
    ) -> None:
        path = (
            self.project_root
            / ".agent"
            / "state"
            / "runs"
            / outcome.run_id
            / "completion.json"
        )
        payload = completion.to_dict()
        if cycle is not None:
            payload["quality_diff_path"] = self._relative(
                self.project_root,
                cycle.diff_path,
            )
            payload["quality_gate_path"] = self._relative(
                self.project_root,
                cycle.gate_path,
            )
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _with_warning(
        self,
        outcome: RunOutcome,
        warning: str,
    ) -> RunOutcome:
        if not warning or outcome.completion is None:
            return outcome
        if warning in outcome.completion.residual_risks:
            return outcome
        completion = replace(
            outcome.completion,
            residual_risks=[
                *outcome.completion.residual_risks,
                warning,
            ],
        )
        self._persist_completion(outcome, completion)
        return replace(outcome, completion=completion)

    def run(self, request: Any) -> RunOutcome:
        self._quality_runtime = None
        self._quality_config = None
        self._quality_lifecycle = None
        self._quality_baseline = None
        self._quality_warning = ""

        outcome = super().run(request)
        outcome = self._with_warning(outcome, self._quality_warning)

        if (
            outcome.completion is None
            or request.plan_only
            or request.dry_run
            or self._quality_lifecycle is None
            or self._quality_baseline is None
            or self._quality_config is None
        ):
            return outcome

        try:
            cycle = self._quality_lifecycle.finalize(
                (
                    self.project_root
                    / ".agent"
                    / "state"
                    / "runs"
                    / outcome.run_id
                ),
                self._quality_baseline,
            )
        except Exception as exc:
            message = f"Final quality analysis failed: {exc}"
            if (
                self._quality_config.required
                or self._quality_config.unavailable_policy == "stop"
            ):
                completion = replace(
                    outcome.completion,
                    status="needs_attention",
                    quality_passed=False,
                    quality_available=False,
                    quality_regressions=[message],
                    residual_risks=[
                        *outcome.completion.residual_risks,
                        message,
                    ],
                )
                self._persist_completion(outcome, completion)
                return replace(
                    outcome,
                    exit_code=6,
                    stage=Stage.QUALITY_GATE_FAILED,
                    completion=completion,
                    message=message,
                )
            return self._with_warning(outcome, message)

        state, _, ledger, controller = self._quality_runtime
        final_budget = self._persist_telemetry(
            state,
            ledger,
            controller,
        )
        gate = cycle.gate
        residual_risks = list(outcome.completion.residual_risks)

        if self._quality_config.unavailable_policy == "warn":
            residual_risks.extend(gate.warnings)
        if self._quality_config.mode == "warn":
            residual_risks.extend(gate.regression_messages)
        residual_risks = list(dict.fromkeys(residual_risks))

        status = outcome.completion.status
        if not final_budget.allowed:
            status = "budget_exceeded"
        elif not gate.allowed:
            status = "needs_attention"

        completion = replace(
            outcome.completion,
            status=status,
            budget_passed=(
                outcome.completion.budget_passed
                and final_budget.allowed
            ),
            quality_passed=gate.allowed,
            quality_available=gate.available,
            quality_regressions=gate.regression_messages,
            residual_risks=residual_risks,
        )
        self._persist_completion(outcome, completion, cycle=cycle)

        if not final_budget.allowed:
            return replace(
                outcome,
                exit_code=5,
                stage=Stage.BUDGET_EXCEEDED,
                completion=completion,
                message="Configured hard budget was exceeded",
            )
        if not gate.allowed:
            return replace(
                outcome,
                exit_code=6,
                stage=Stage.QUALITY_GATE_FAILED,
                completion=completion,
                message="Quality regression gate failed",
            )
        return replace(
            outcome,
            completion=completion,
            message=("Task is ready for human review" if completion.ready else outcome.message),
        )
