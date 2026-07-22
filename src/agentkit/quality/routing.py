from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agentkit.models import RunMode, TriageResult

from .hotspot_context import HotspotContext, RankedContextCandidate
from .routing_config import QualityRoutingConfig

_MODE_RANK = {
    RunMode.AUTO: 0,
    RunMode.FAST: 1,
    RunMode.STANDARD: 2,
    RunMode.DEEP: 3,
}


@dataclass(frozen=True)
class RoutingRule:
    rule: str
    action: str
    evidence: str
    file: str = ""
    symbol: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QualityRoute:
    version: int
    task: str
    original_mode: RunMode
    effective_mode: RunMode
    approval_required: bool
    scope_kind: str
    selected_skills: tuple[str, ...]
    risk_reasons: tuple[str, ...]
    requirements: tuple[str, ...]
    rules: tuple[RoutingRule, ...]
    warnings: tuple[str, ...]
    source_snapshot: str
    scoped_candidates: tuple[dict[str, Any], ...]

    @property
    def escalated(self) -> bool:
        return _MODE_RANK[self.effective_mode] > _MODE_RANK[self.original_mode]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "task": self.task,
            "original_mode": self.original_mode.value,
            "effective_mode": self.effective_mode.value,
            "escalated": self.escalated,
            "approval_required": self.approval_required,
            "scope_kind": self.scope_kind,
            "selected_skills": list(self.selected_skills),
            "risk_reasons": list(self.risk_reasons),
            "requirements": list(self.requirements),
            "rules": [item.to_dict() for item in self.rules],
            "warnings": list(self.warnings),
            "source_snapshot": self.source_snapshot,
            "scoped_candidates": list(self.scoped_candidates),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "original_mode": self.original_mode.value,
            "effective_mode": self.effective_mode.value,
            "escalated": self.escalated,
            "approval_required": self.approval_required,
            "scope_kind": self.scope_kind,
            "requirements": list(self.requirements),
            "rules": [item.to_dict() for item in self.rules],
            "warnings": list(self.warnings),
        }


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _candidate_identity(item: dict[str, Any]) -> tuple[str, str]:
    file = str(item.get("file") or item.get("dir") or "").replace("\\", "/")
    symbol = str(item.get("name") or "")
    return file, symbol


def _raw_hotspot(
    candidate: RankedContextCandidate,
    hotspots: list[dict[str, Any]],
) -> dict[str, Any]:
    exact: list[dict[str, Any]] = []
    file_matches: list[dict[str, Any]] = []
    for item in hotspots:
        file, symbol = _candidate_identity(item)
        if file != candidate.file:
            continue
        file_matches.append(item)
        if candidate.symbol and symbol == candidate.symbol:
            exact.append(item)
    return (exact or file_matches or [{}])[0]


def _graph_window(graph_output: str, candidate: RankedContextCandidate) -> str:
    lowered = graph_output.lower()
    anchors = [candidate.symbol.lower(), candidate.file.lower()]
    positions = [lowered.find(item) for item in anchors if item and lowered.find(item) >= 0]
    if not positions:
        return ""
    start = max(0, min(positions) - 350)
    end = min(len(lowered), max(positions) + 350)
    return lowered[start:end]


def _graph_signals(
    graph_output: str,
    candidate: RankedContextCandidate,
) -> tuple[bool, bool, bool]:
    window = _graph_window(graph_output, candidate)
    if not window:
        return False, False, False
    fan_in = any(
        token in window
        for token in ("fan-in", "fan_in", "many callers", "high fan in")
    )
    fan_out = any(
        token in window
        for token in ("fan-out", "fan_out", "many dependencies", "high fan out")
    )
    central = any(
        token in window
        for token in ("centrality", "central node", "highly connected", "critical path")
    )
    return fan_in, fan_out, central


def _max_mode(current: RunMode, proposed: RunMode) -> RunMode:
    return proposed if _MODE_RANK[proposed] > _MODE_RANK[current] else current


def route_quality(
    *,
    task: str,
    base_triage: TriageResult,
    context: HotspotContext | None,
    snapshot_payload: dict[str, Any] | None,
    graph_output: str,
    config: QualityRoutingConfig,
) -> QualityRoute:
    original_mode = base_triage.mode
    effective_mode = original_mode
    skills = list(base_triage.selected_skills)
    reasons = list(base_triage.risk_reasons)
    requirements: list[str] = []
    rules: list[RoutingRule] = []
    warnings: list[str] = []
    candidates: tuple[RankedContextCandidate, ...] = ()
    source_snapshot = ""

    if not config.enabled:
        warnings.append("Quality-aware routing is disabled")
    elif context is None or snapshot_payload is None:
        warnings.append(
            "Scoped quality evidence is unavailable; existing triage was preserved"
        )
    else:
        candidates = context.candidates
        source_snapshot = context.source_snapshot
        warnings.extend(context.warnings)
        raw_hotspots = [
            item
            for item in snapshot_payload.get("hotspots", [])
            if isinstance(item, dict)
        ]
        elevated = 0
        crisis = False
        for candidate in candidates:
            raw = _raw_hotspot(candidate, raw_hotspots)
            complexity = max(
                _number(raw.get("complexity")),
                _number(raw.get("complexity_total")),
            )
            rp = _number(raw.get("refactoring_pressure"))
            op = _number(raw.get("overengineering_pressure"))
            fan_in = _number(raw.get("fan_in"))
            fan_out = _number(raw.get("fan_out"))
            centrality = _number(raw.get("centrality"))
            graph_fan_in, graph_fan_out, graph_central = _graph_signals(
                graph_output, candidate
            )

            candidate_elevated = False
            location = candidate.file
            if candidate.symbol:
                location += f":{candidate.symbol}"

            if complexity > config.edge_case_complexity:
                candidate_elevated = True
                requirements.append("targeted_edge_case_tests")
                skills.append("risk-based-testing")
                rules.append(
                    RoutingRule(
                        "complexity_edge_cases",
                        "require targeted edge-case tests",
                        f"complexity {complexity:g} > {config.edge_case_complexity:g}",
                        candidate.file,
                        candidate.symbol,
                    )
                )
            if complexity > config.characterization_complexity:
                candidate_elevated = True
                requirements.append("characterization_test_before_structural_rewrite")
                skills.append("risk-based-testing")
                rules.append(
                    RoutingRule(
                        "complexity_characterization",
                        "require characterization test before structural rewrite",
                        f"complexity {complexity:g} > {config.characterization_complexity:g}",
                        candidate.file,
                        candidate.symbol,
                    )
                )
            if rp > config.high_refactoring_pressure:
                candidate_elevated = True
                requirements.append("regression_test")
                skills.append("risk-based-testing")
                rules.append(
                    RoutingRule(
                        "high_refactoring_pressure",
                        "add regression-test requirement",
                        f"RP {rp:g} > {config.high_refactoring_pressure:g}",
                        candidate.file,
                        candidate.symbol,
                    )
                )
            if op > config.high_overengineering_pressure:
                candidate_elevated = True
                skills.extend(("architecture-guard", "engineering-balance"))
                rules.append(
                    RoutingRule(
                        "high_overengineering_pressure",
                        "add architecture and engineering-balance review",
                        f"OP {op:g} > {config.high_overengineering_pressure:g}",
                        candidate.file,
                        candidate.symbol,
                    )
                )
            high_fan_in = (
                fan_in > config.high_fan_in
                or centrality > config.high_centrality
                or graph_fan_in
                or graph_central
            )
            if high_fan_in:
                candidate_elevated = True
                requirements.extend(("contract_tests", "component_tests"))
                rules.append(
                    RoutingRule(
                        "high_fan_in_or_centrality",
                        "expand contract and component tests",
                        (
                            f"fan_in={fan_in:g}, centrality={centrality:g}, "
                            f"graph_signal={graph_fan_in or graph_central}"
                        ),
                        candidate.file,
                        candidate.symbol,
                    )
                )
            if fan_out > config.high_fan_out or graph_fan_out:
                candidate_elevated = True
                requirements.append("integration_checks")
                rules.append(
                    RoutingRule(
                        "high_fan_out",
                        "add downstream integration checks",
                        f"fan_out={fan_out:g}, graph_signal={graph_fan_out}",
                        candidate.file,
                        candidate.symbol,
                    )
                )
            if (
                rp > config.high_refactoring_pressure
                and op > config.high_overengineering_pressure
            ):
                crisis = True
                if (
                    config.allow_mode_escalation
                    or config.require_approval_on_crisis
                ):
                    effective_mode = _max_mode(effective_mode, RunMode.DEEP)
                rules.append(
                    RoutingRule(
                        "combined_rp_op_crisis",
                        "escalate to deep mode and require approval",
                        f"scoped RP={rp:g}, OP={op:g} at {location}",
                        candidate.file,
                        candidate.symbol,
                    )
                )
            if candidate_elevated:
                elevated += 1

        if not candidates:
            warnings.append(
                "No task-scoped quality candidates were available; existing triage was preserved"
            )
        if elevated == 1:
            scope_kind = "local"
        elif elevated > 1:
            scope_kind = "systemic"
        elif candidates:
            scope_kind = "healthy"
        else:
            scope_kind = "unknown"

        if rules:
            reasons.extend(
                f"quality route: {item.rule} ({item.evidence})" for item in rules
            )
        reasons.extend(
            f"quality requirement: {item}" for item in dict.fromkeys(requirements)
        )
        approval_required = crisis and config.require_approval_on_crisis
        return QualityRoute(
            version=1,
            task=task.strip(),
            original_mode=original_mode,
            effective_mode=effective_mode,
            approval_required=approval_required,
            scope_kind=scope_kind,
            selected_skills=tuple(dict.fromkeys(skills)),
            risk_reasons=tuple(dict.fromkeys(reasons)),
            requirements=tuple(dict.fromkeys(requirements)),
            rules=tuple(rules),
            warnings=tuple(dict.fromkeys(warnings)),
            source_snapshot=source_snapshot,
            scoped_candidates=tuple(item.to_dict() for item in candidates),
        )

    return QualityRoute(
        version=1,
        task=task.strip(),
        original_mode=original_mode,
        effective_mode=effective_mode,
        approval_required=False,
        scope_kind="unknown",
        selected_skills=tuple(dict.fromkeys(skills)),
        risk_reasons=tuple(dict.fromkeys(reasons)),
        requirements=(),
        rules=(),
        warnings=tuple(dict.fromkeys(warnings)),
        source_snapshot=source_snapshot,
        scoped_candidates=tuple(item.to_dict() for item in candidates),
    )
