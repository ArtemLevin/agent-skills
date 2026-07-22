from __future__ import annotations

import unittest

from agentkit.models import CompletionReport, RunMode


class CompletionQualityGateTests(unittest.TestCase):
    def test_quality_gate_participates_in_readiness(self) -> None:
        report = CompletionReport(
            status="ready_for_review",
            mode=RunMode.STANDARD,
            changed_files=[],
            checks_passed=True,
            review_passed=True,
            blocking_findings=0,
            scope_passed=True,
            budget_passed=True,
            quality_passed=False,
        )
        self.assertFalse(report.ready)
        self.assertIn("quality_passed", report.to_dict())

    def test_defaults_preserve_old_completion_semantics(self) -> None:
        report = CompletionReport(
            status="ready_for_review",
            mode=RunMode.STANDARD,
            changed_files=[],
            checks_passed=True,
            review_passed=True,
            blocking_findings=0,
            scope_passed=True,
        )
        self.assertTrue(report.ready)


if __name__ == "__main__":
    unittest.main()
