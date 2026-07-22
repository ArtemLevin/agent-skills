from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.config import VerificationConfig
from agentkit.models import RunMode
from agentkit.quality.routing import QualityRoute, RoutingRule
from agentkit.quality.verification_plan import build_verification_plan


class VerificationPlanTests(unittest.TestCase):
    def route(self, requirements: tuple[str, ...]) -> QualityRoute:
        return QualityRoute(
            version=1,
            task="fix service",
            original_mode=RunMode.STANDARD,
            effective_mode=RunMode.STANDARD,
            approval_required=False,
            scope_kind="local",
            selected_skills=("risk-based-testing",),
            risk_reasons=("quality route",),
            requirements=requirements,
            rules=(RoutingRule("high_refactoring_pressure", "test", "RP 61"),),
            warnings=(),
            source_snapshot="quality-before.json",
            scoped_candidates=(),
        )

    def test_every_selected_command_has_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            plan = build_verification_plan(
                root,
                VerificationConfig(
                    commands=[["python", "-m", "unittest", "discover", "-s", "tests"]]
                ),
                self.route(("regression_test",)),
            )
            self.assertTrue(plan.selected_commands)
            self.assertTrue(all(item.reason for item in plan.selected_commands))
            self.assertTrue(all(item.source_evidence for item in plan.selected_commands))

    def test_missing_test_command_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = build_verification_plan(
                root,
                VerificationConfig(commands=[["python", "-m", "compileall", "-q", "."]]),
                self.route(("characterization_test_before_structural_rewrite",)),
            )
            self.assertTrue(plan.omitted_checks)
            self.assertTrue(plan.escalation_conditions)


if __name__ == "__main__":
    unittest.main()
