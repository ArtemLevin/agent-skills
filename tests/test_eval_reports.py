from __future__ import annotations

import unittest

from agentkit.evals.config import RegressionThresholds
from agentkit.evals.models import (
    CorrectnessMetrics,
    EfficiencyMetrics,
    EvaluationRunResult,
    QualityMetrics,
)
from agentkit.evals.reports import aggregate_runs, compare_summaries


def result(run_id: str, *, ready: bool, unknown: int, tokens: int) -> EvaluationRunResult:
    return EvaluationRunResult(
        evaluation_id="eval-1",
        task_id="task-1",
        run_id=run_id,
        status="passed" if ready else "failed",
        source_run_id=run_id,
        agent_exit_code=0,
        correctness=CorrectnessMetrics(
            acceptance_passed=ready,
            required_files_passed=True,
            forbidden_files_passed=True,
            ready_for_review=ready,
        ),
        efficiency=EfficiencyMetrics(
            agent_calls=1,
            measured_agent_calls=0 if unknown else 1,
            unknown_agent_calls=unknown,
            total_tokens=tokens,
        ),
        quality=QualityMetrics(available=True, comparable=True, gate_allowed=True),
    )


class EvaluationReportTests(unittest.TestCase):
    def test_unknown_usage_is_not_averaged_as_zero(self) -> None:
        summary = aggregate_runs(
            "eval-1",
            [result("a", ready=True, unknown=0, tokens=100), result("b", ready=True, unknown=1, tokens=0)],
        )
        self.assertEqual(summary.efficiency["avg_total_tokens_measured"], 100.0)
        self.assertEqual(summary.efficiency["unknown_usage_runs"], 1)

    def test_correctness_regression_dominates_efficiency_improvement(self) -> None:
        baseline = aggregate_runs("base", [result("a", ready=True, unknown=0, tokens=100)]).to_dict()
        current_run = result("b", ready=False, unknown=0, tokens=50)
        current = aggregate_runs("current", [current_run]).to_dict()
        comparison = compare_summaries(
            baseline,
            current,
            RegressionThresholds(),
            baseline_name="base.json",
            current_name="current.json",
        )
        self.assertEqual(comparison.verdict, "regression")
        self.assertTrue(any("Acceptance" in item for item in comparison.regressions))

    def test_threshold_equality_passes(self) -> None:
        baseline = aggregate_runs("base", [result("a", ready=True, unknown=0, tokens=100)]).to_dict()
        current = aggregate_runs("current", [result("b", ready=True, unknown=0, tokens=100)]).to_dict()
        comparison = compare_summaries(
            baseline,
            current,
            RegressionThresholds(agent_calls_increase=0.0),
            baseline_name="base.json",
            current_name="current.json",
        )
        self.assertEqual(comparison.verdict, "neutral")


if __name__ == "__main__":
    unittest.main()
