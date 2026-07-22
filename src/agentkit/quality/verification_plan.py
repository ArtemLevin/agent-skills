from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentkit.config import VerificationConfig
from agentkit.verification import discover_commands

from .routing import QualityRoute


@dataclass(frozen=True)
class PlannedCommand:
    command: tuple[str, ...]
    reason: str
    source_evidence: tuple[str, ...]
    scope: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["command"] = list(self.command)
        data["source_evidence"] = list(self.source_evidence)
        return data


@dataclass(frozen=True)
class VerificationPlan:
    version: int
    selected_commands: tuple[PlannedCommand, ...]
    requirements: tuple[str, ...]
    escalation_conditions: tuple[str, ...]
    omitted_checks: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "selected_commands": [item.to_dict() for item in self.selected_commands],
            "requirements": list(self.requirements),
            "escalation_conditions": list(self.escalation_conditions),
            "omitted_checks": list(self.omitted_checks),
            "warnings": list(self.warnings),
        }

    def as_config(self, timeout_seconds: int) -> VerificationConfig:
        return VerificationConfig(
            commands=[list(item.command) for item in self.selected_commands],
            timeout_seconds=timeout_seconds,
        )


def _is_test_command(command: list[str]) -> bool:
    text = " ".join(command).lower()
    return any(token in text for token in ("pytest", "unittest", "test"))


def _reason(command: list[str]) -> str:
    text = " ".join(command).lower()
    if "pytest" in text or "unittest" in text:
        return "execute the project regression test suite"
    if "compileall" in text:
        return "verify Python syntax and import-time bytecode compilation"
    if command and command[0].lower() == "ruff":
        return "run configured static lint checks"
    if command and command[0].lower() in {"mypy", "pyright"}:
        return "run configured static type checks"
    return "execute a configured project verification command"


def build_verification_plan(
    project_root: Path,
    base_config: VerificationConfig,
    route: QualityRoute,
) -> VerificationPlan:
    configured = [list(item) for item in base_config.commands]
    discovered = discover_commands(project_root)
    commands = configured or [list(item) for item in discovered]
    requirements = list(route.requirements)
    warnings: list[str] = []
    omitted: list[str] = []
    escalation: list[str] = []

    needs_full_suite = any(
        item
        in {
            "regression_test",
            "contract_tests",
            "component_tests",
            "integration_checks",
        }
        for item in requirements
    )
    if needs_full_suite:
        escalation.append(
            "Run the broadest discovered test command when scoped quality evidence indicates coupling or regression risk"
        )
        for command in discovered:
            if command not in commands:
                commands.append(list(command))

    rule_ids = tuple(item.rule for item in route.rules)
    planned = tuple(
        PlannedCommand(
            command=tuple(command),
            reason=_reason(command),
            source_evidence=rule_ids or ("base_verification_policy",),
            scope="full" if needs_full_suite and _is_test_command(command) else "configured",
        )
        for command in commands
    )

    has_tests = any(_is_test_command(list(item.command)) for item in planned)
    test_requirements = {
        "targeted_edge_case_tests",
        "characterization_test_before_structural_rewrite",
        "regression_test",
        "contract_tests",
        "component_tests",
        "integration_checks",
    }
    if test_requirements.intersection(requirements) and not has_tests:
        omitted.append(
            "Required test evidence was requested by the quality route, but no executable test command was configured or discovered"
        )
    if "characterization_test_before_structural_rewrite" in requirements:
        escalation.append(
            "Before structural rewrite, add or identify a characterization test that captures current observable behavior"
        )
    if "targeted_edge_case_tests" in requirements:
        escalation.append(
            "Add targeted edge-case assertions for the scoped high-complexity symbol"
        )
    if not planned:
        warnings.append("No verification commands were configured or discovered")

    return VerificationPlan(
        version=1,
        selected_commands=planned,
        requirements=tuple(dict.fromkeys(requirements)),
        escalation_conditions=tuple(dict.fromkeys(escalation)),
        omitted_checks=tuple(dict.fromkeys(omitted)),
        warnings=tuple(dict.fromkeys(warnings)),
    )
