from __future__ import annotations

import unittest

from agentkit.quality.comparison import compare_snapshots
from agentkit.quality.models import Availability, QualityHotspot, QualityProject, QualitySnapshot


def snapshot(*, score: float | None = 10, rp: float | None = 20, op: float | None = 5, density: float | None = 3, hotspots: tuple[QualityHotspot, ...] = (), provider_version: str = "1") -> QualitySnapshot:
    return QualitySnapshot(
        availability=Availability.AVAILABLE,
        provider="strictacode",
        provider_version=provider_version,
        source_fingerprint="f",
        project=QualityProject(
            score=score,
            refactoring_pressure=rp,
            overengineering_pressure=op,
            complexity_density=density,
            status="normal",
            language="python",
        ),
        hotspots=hotspots,
    )


class QualityComparisonTests(unittest.TestCase):
    def test_metrics_and_hotspot_sets(self) -> None:
        old = QualityHotspot(kind="function", name="old", file="a.py")
        kept = QualityHotspot(kind="function", name="kept", file="b.py", complexity=4)
        new = QualityHotspot(kind="function", name="new", file="c.py", status="critical")
        changed = QualityHotspot(kind="function", name="kept", file="b.py", complexity=9)
        diff = compare_snapshots(
            snapshot(hotspots=(old, kept)),
            snapshot(score=14, hotspots=(new, changed)),
            baseline_strategy="run_start",
        )
        self.assertTrue(diff.comparable)
        self.assertEqual(diff.metrics["score"].delta, 4)
        self.assertEqual([item.name for item in diff.new_hotspots], ["new"])
        self.assertEqual([item.name for item in diff.resolved_hotspots], ["old"])
        self.assertEqual([item.name for item in diff.persisting_hotspots], ["kept"])
        self.assertEqual([item.name for item in diff.changed_hotspots], ["kept"])

    def test_provider_version_mismatch_is_explicit(self) -> None:
        diff = compare_snapshots(snapshot(provider_version="1"), snapshot(provider_version="2"), baseline_strategy="run_start")
        self.assertFalse(diff.comparable)
        self.assertTrue(any("version mismatch" in item.lower() for item in diff.warnings))

    def test_missing_metric_is_not_improvement(self) -> None:
        diff = compare_snapshots(snapshot(score=None), snapshot(score=1), baseline_strategy="run_start")
        self.assertIsNone(diff.metrics["score"].delta)
        self.assertFalse(diff.metrics["score"].comparable)

    def test_none_strategy_disables_delta_comparison(self) -> None:
        diff = compare_snapshots(snapshot(score=10), snapshot(score=100), baseline_strategy="none")
        self.assertFalse(diff.comparable)
        self.assertIsNone(diff.metrics["score"].delta)


if __name__ == "__main__":
    unittest.main()
