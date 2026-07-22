from __future__ import annotations

import unittest

from agentkit.quality.comparison import compare_snapshots
from agentkit.quality.config import AbsoluteThresholds, DeltaThresholds, QualityConfig
from agentkit.quality.gate import evaluate_quality_gate
from agentkit.quality.models import Availability, QualityHotspot, QualityProject, QualitySnapshot


def snap(score: float, *, rp: float = 10, hotspot: QualityHotspot | None = None, availability: Availability = Availability.AVAILABLE) -> QualitySnapshot:
    return QualitySnapshot(
        availability=availability,
        provider="strictacode",
        provider_version="1",
        source_fingerprint=str(score),
        project=(
            QualityProject(
                score=score,
                refactoring_pressure=rp,
                overengineering_pressure=2,
                complexity_density=1,
                status="normal",
                language="python",
            )
            if availability is Availability.AVAILABLE
            else None
        ),
        hotspots=(hotspot,) if hotspot else (),
    )


class QualityGateTests(unittest.TestCase):
    def test_report_mode_records_but_allows_regression(self) -> None:
        before = snap(10)
        after = snap(20)
        diff = compare_snapshots(before, after, baseline_strategy="run_start")
        config = QualityConfig(mode="report", delta=DeltaThresholds(score=5, rp=0, op=0, density=0, new_critical_hotspots=None))
        gate = evaluate_quality_gate(config, after, diff)
        self.assertFalse(gate.passed)
        self.assertTrue(gate.allowed)
        self.assertEqual(len(gate.violations), 1)

    def test_enforce_mode_blocks_regression(self) -> None:
        before = snap(10)
        after = snap(20)
        diff = compare_snapshots(before, after, baseline_strategy="run_start")
        config = QualityConfig(mode="enforce", delta=DeltaThresholds(score=5, rp=0, op=0, density=0, new_critical_hotspots=None))
        gate = evaluate_quality_gate(config, after, diff)
        self.assertFalse(gate.allowed)

    def test_threshold_equality_passes(self) -> None:
        before = snap(10)
        after = snap(15)
        diff = compare_snapshots(before, after, baseline_strategy="run_start")
        config = QualityConfig(mode="enforce", delta=DeltaThresholds(score=5, rp=0, op=0, density=0, new_critical_hotspots=None))
        self.assertTrue(evaluate_quality_gate(config, after, diff).allowed)

    def test_absolute_and_hotspot_violations_are_all_reported(self) -> None:
        critical = QualityHotspot(kind="function", name="bad", file="bad.py", status="critical")
        before = snap(10)
        after = snap(30, rp=40, hotspot=critical)
        diff = compare_snapshots(before, after, baseline_strategy="run_start")
        config = QualityConfig(
            mode="enforce",
            absolute=AbsoluteThresholds(score=20, rp=30),
            delta=DeltaThresholds(score=5, rp=5, op=0, density=0, new_critical_hotspots=0),
        )
        gate = evaluate_quality_gate(config, after, diff)
        self.assertGreaterEqual(len(gate.violations), 5)

    def test_unavailable_policy_stop_blocks(self) -> None:
        before = snap(10)
        after = snap(0, availability=Availability.UNAVAILABLE)
        diff = compare_snapshots(before, after, baseline_strategy="run_start")
        config = QualityConfig(mode="report", unavailable_policy="stop")
        self.assertFalse(evaluate_quality_gate(config, after, diff).allowed)


if __name__ == "__main__":
    unittest.main()
