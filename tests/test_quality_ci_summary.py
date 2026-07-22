from __future__ import annotations

import unittest

from agentkit.quality.ci_summary import (
    github_annotations,
    render_quality_summary,
)
from agentkit.quality.config import QualityConfig
from agentkit.quality.gate_models import (
    QualityDiff,
    QualityGateResult,
    QualityGateViolation,
    QualityMetricDelta,
)


class QualityCISummaryTests(unittest.TestCase):
    def _diff(self) -> QualityDiff:
        return QualityDiff(
            provider="strictacode",
            provider_version="x",
            baseline_fingerprint="a",
            current_fingerprint="b",
            comparable=True,
            metrics={
                "score": QualityMetricDelta("score", 30, 32, 2, True),
                "rp": QualityMetricDelta("rp", 50, 57, 7, True),
                "op": QualityMetricDelta("op", 20, 19, -1, True),
                "density": QualityMetricDelta("density", 10.0, 10.5, 0.5, True),
            },
            warnings=("measurement warning",),
        )

    def _gate(self) -> QualityGateResult:
        return QualityGateResult(
            mode="enforce",
            unavailable_policy="warn",
            available=True,
            comparable=True,
            passed=False,
            allowed=False,
            violations=(
                QualityGateViolation(
                    kind="delta",
                    metric="rp",
                    threshold=5,
                    baseline=50,
                    current=57,
                    delta=7,
                    message="RP delta 7 exceeds 5",
                ),
            ),
        )

    def test_renders_bounded_metric_table_and_gate(self) -> None:
        content = render_quality_summary(
            self._diff(),
            self._gate(),
            QualityConfig(),
        )
        self.assertIn("## AgentKit Quality Report", content)
        self.assertIn("| Refactoring pressure | 50 | 57 | +7 | +5 | FAIL |", content)
        self.assertIn("RP delta 7 exceeds 5", content)
        self.assertIn("measurement warning", content)

    def test_annotations_are_bounded(self) -> None:
        annotations = github_annotations(
            self._diff(),
            self._gate(),
            max_items=1,
        )
        self.assertLessEqual(len(annotations), 2)
        self.assertTrue(annotations[0].startswith("::warning"))


if __name__ == "__main__":
    unittest.main()
