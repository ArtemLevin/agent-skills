from __future__ import annotations

import json
import unittest

from agentkit.quality.models import Availability
from agentkit.quality.parser import parse_strictacode_json


class QualityParserTests(unittest.TestCase):
    def _payload(self) -> dict[str, object]:
        return {
            "project": {
                "lang": "python",
                "loc": 120,
                "status": {"name": "warning", "score": 48, "reasons": []},
                "refactoring_pressure": {
                    "score": 62,
                    "stat(modules)": {"avg": 10, "min": 2, "max": 41, "p50": 8, "p90": 24},
                },
                "overengineering_pressure": {"score": 17},
                "complexity": {
                    "score": 55,
                    "density": 31.2,
                    "stat(modules)": {"avg": 7, "min": 1, "max": 42, "p50": 5, "p90": 19},
                },
            },
            "modules": [
                {
                    "name": "service.py",
                    "file": "src/service.py",
                    "loc": 80,
                    "status": {"name": "critical", "score": 72, "reasons": ["complex"]},
                    "refactoring_pressure": {"score": 68},
                    "overengineering_pressure": {"score": 12},
                    "complexity": {"score": 44, "density": 55.0},
                },
                {
                    "name": "other.py",
                    "file": "src/other.py",
                    "loc": 40,
                    "status": {"name": "normal", "score": 22, "reasons": []},
                    "refactoring_pressure": {"score": 20},
                    "overengineering_pressure": {"score": 10},
                    "complexity": {"score": 11, "density": 12.0},
                },
            ],
        }

    def test_parses_project_and_bounded_hotspots(self) -> None:
        snapshot = parse_strictacode_json(
            json.dumps(self._payload()),
            provider_version="0.0.5",
            details=True,
            limits={"packages": 0, "modules": 1, "classes": 0, "methods": 0, "functions": 0},
        )
        self.assertEqual(snapshot.availability, Availability.AVAILABLE)
        self.assertEqual(snapshot.project.refactoring_pressure, 62)
        self.assertEqual(len(snapshot.hotspots), 1)
        self.assertEqual(snapshot.hotspots[0].file, "src/service.py")
        self.assertTrue(snapshot.truncated)

    def test_missing_metric_is_partial_not_zero(self) -> None:
        payload = self._payload()
        payload["project"]["overengineering_pressure"] = {}
        snapshot = parse_strictacode_json(
            json.dumps(payload),
            provider_version="0.0.5",
            details=False,
            limits={"packages": 0, "modules": 0, "classes": 0, "methods": 0, "functions": 0},
        )
        self.assertEqual(snapshot.availability, Availability.PARTIAL)
        self.assertIsNone(snapshot.project.overengineering_pressure)
        self.assertTrue(any("overengineering" in item for item in snapshot.warnings))

    def test_invalid_json_raises(self) -> None:
        with self.assertRaisesRegex(Exception, "invalid JSON"):
            parse_strictacode_json(
                "not-json",
                provider_version="unknown",
                details=False,
                limits={},
            )


if __name__ == "__main__":
    unittest.main()
