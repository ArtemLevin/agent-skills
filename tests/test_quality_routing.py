from __future__ import annotations

import unittest

from agentkit.models import RunMode, TriageResult
from agentkit.quality.hotspot_context import HotspotContext, RankedContextCandidate
from agentkit.quality.routing import route_quality
from agentkit.quality.routing_config import QualityRoutingConfig


def context(*candidates: RankedContextCandidate) -> HotspotContext:
    return HotspotContext(
        version=1,
        task="fix service",
        source_snapshot=".agent/state/runs/run/quality-before.json",
        source_fingerprint="abc",
        graph_available=True,
        cache_key="key",
        fingerprint="fingerprint",
        cache_hit=False,
        candidates=tuple(candidates),
        warnings=(),
        content="",
    )


def candidate(file: str = "src/service.py", symbol: str = "process") -> RankedContextCandidate:
    return RankedContextCandidate(
        file=file,
        symbol=symbol,
        kind="function",
        line_start=10,
        line_end=30,
        task_score=1.0,
        quality_score=0.8,
        graph_score=0.5,
        total_score=0.85,
        reasons=("task tokens: service",),
    )


class QualityRoutingTests(unittest.TestCase):
    def base(self, mode: RunMode = RunMode.STANDARD) -> TriageResult:
        return TriageResult(mode, ["base risk"], ["task-triage", "verification-router"])

    def test_complexity_boundaries_are_strict(self) -> None:
        snapshot = {
            "hotspots": [
                {
                    "file": "src/service.py",
                    "name": "process",
                    "complexity": 30,
                }
            ]
        }
        route = route_quality(
            task="fix service process",
            base_triage=self.base(),
            context=context(candidate()),
            snapshot_payload=snapshot,
            graph_output="",
            config=QualityRoutingConfig(),
        )
        self.assertNotIn("targeted_edge_case_tests", route.requirements)
        snapshot["hotspots"][0]["complexity"] = 41
        route = route_quality(
            task="fix service process",
            base_triage=self.base(),
            context=context(candidate()),
            snapshot_payload=snapshot,
            graph_output="",
            config=QualityRoutingConfig(),
        )
        self.assertIn("targeted_edge_case_tests", route.requirements)
        self.assertIn(
            "characterization_test_before_structural_rewrite",
            route.requirements,
        )

    def test_combined_rp_op_escalates_and_requires_approval(self) -> None:
        snapshot = {
            "hotspots": [
                {
                    "file": "src/service.py",
                    "name": "process",
                    "refactoring_pressure": 61,
                    "overengineering_pressure": 80,
                }
            ]
        }
        route = route_quality(
            task="fix service process",
            base_triage=self.base(RunMode.FAST),
            context=context(candidate()),
            snapshot_payload=snapshot,
            graph_output="",
            config=QualityRoutingConfig(),
        )
        self.assertEqual(route.effective_mode, RunMode.DEEP)
        self.assertTrue(route.approval_required)
        self.assertIn("risk-based-testing", route.selected_skills)
        self.assertIn("architecture-guard", route.selected_skills)
        self.assertIn("engineering-balance", route.selected_skills)
        self.assertIn("regression_test", route.requirements)

    def test_unrelated_raw_hotspot_cannot_escalate(self) -> None:
        snapshot = {
            "hotspots": [
                {
                    "file": "src/unrelated.py",
                    "name": "huge_parser",
                    "refactoring_pressure": 100,
                    "overengineering_pressure": 100,
                    "complexity": 100,
                },
                {
                    "file": "src/service.py",
                    "name": "process",
                    "complexity": 5,
                },
            ]
        }
        route = route_quality(
            task="fix service process",
            base_triage=self.base(),
            context=context(candidate()),
            snapshot_payload=snapshot,
            graph_output="",
            config=QualityRoutingConfig(),
        )
        self.assertEqual(route.effective_mode, RunMode.STANDARD)
        self.assertFalse(route.approval_required)
        self.assertEqual(route.scope_kind, "healthy")

    def test_deep_base_mode_is_never_downgraded(self) -> None:
        route = route_quality(
            task="security migration",
            base_triage=self.base(RunMode.DEEP),
            context=None,
            snapshot_payload=None,
            graph_output="",
            config=QualityRoutingConfig(),
        )
        self.assertEqual(route.effective_mode, RunMode.DEEP)
        self.assertIn("existing triage was preserved", route.warnings[0])


if __name__ == "__main__":
    unittest.main()
