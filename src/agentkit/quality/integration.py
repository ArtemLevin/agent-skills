from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from agentkit.runner import AgentKitError, AgentKitRunner, RunOutcome

from .config import load_quality_config
from .service import QualityAnalysisResult, QualityService


class QualityAwareRunner(AgentKitRunner):
    """AgentKit runner extension that adds report-only quality evidence."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._quality_runtime: tuple[Any, Any] | None = None
        self._quality_result: QualityAnalysisResult | None = None

    def _tool_observer(self, state: Any, ledger: Any, controller: Any):
        observer = super()._tool_observer(state, ledger, controller)
        self._quality_runtime = (state, observer)
        return observer

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
        state, observer = self._quality_runtime
        quality_config = load_quality_config(self.project_root)
        service = QualityService(
            self.project_root,
            quality_config,
            self.config.context,
            self.config.security,
            observer=observer,
            phase="quality_before",
        )
        result = service.analyze(state.directory)
        self._quality_result = result
        try:
            snapshot_path = result.artifacts.snapshot_path.relative_to(self.project_root).as_posix()
            hotspots_path = result.artifacts.hotspots_path.relative_to(self.project_root).as_posix()
        except ValueError:
            snapshot_path = str(result.artifacts.snapshot_path)
            hotspots_path = str(result.artifacts.hotspots_path)
        packet["quality"] = result.snapshot.task_packet_entry(snapshot_path, hotspots_path)
        if quality_config.required and not result.snapshot.usable:
            raise AgentKitError(
                "Required quality provider is not usable: "
                + (result.warning or result.snapshot.availability.value)
            )
        return packet

    def run(self, request: Any) -> RunOutcome:
        self._quality_runtime = None
        self._quality_result = None
        outcome = super().run(request)
        warning = self._quality_result.warning if self._quality_result is not None else ""
        if not warning or outcome.completion is None:
            return outcome
        if warning in outcome.completion.residual_risks:
            return outcome
        completion = replace(
            outcome.completion,
            residual_risks=outcome.completion.residual_risks + [warning],
        )
        completion_path = (
            self.project_root
            / ".agent"
            / "state"
            / "runs"
            / outcome.run_id
            / "completion.json"
        )
        completion_path.write_text(
            json.dumps(completion.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return replace(outcome, completion=completion)
