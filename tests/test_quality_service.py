from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from agentkit.config import ContextConfig, SecurityConfig
from agentkit.quality.config import QualityConfig
from agentkit.quality.models import Availability
from agentkit.quality.service import QualityService


_SCRIPT = r'''
import json
import sys
project = {
    "lang": "python",
    "loc": 30,
    "status": {"name": "warning", "score": 45, "reasons": []},
    "refactoring_pressure": {
        "score": 55,
        "stat(modules)": {"avg": 8, "min": 2, "max": 31, "p50": 6, "p90": 20},
    },
    "overengineering_pressure": {"score": 15},
    "complexity": {
        "score": 20,
        "density": 25.0,
        "stat(modules)": {"avg": 5, "min": 1, "max": 22, "p50": 4, "p90": 17},
    }
}
payload = {"project": project}
if "--details" in sys.argv:
    payload["functions"] = [{
        "name": "work", "file": "sample.py", "loc": 20,
        "status": {"name": "warning", "score": 55, "reasons": ["branching"]},
        "complexity": {"score": 18, "total": 24, "density": 90.0}
    }]
print(json.dumps(payload))
'''


class QualityServiceTests(unittest.TestCase):
    def _service(self, root: Path, events: list[str]) -> QualityService:
        script = root / "fake_strictacode.py"
        script.write_text(_SCRIPT, encoding="utf-8")
        quality = QualityConfig(
            command=[sys.executable, str(script)],
            details_policy="on_warning",
            cache_ttl_seconds=3600,
            max_packages=0,
            max_modules=0,
            max_classes=0,
            max_methods=0,
            max_functions=5,
        )
        context = ContextConfig(
            cache_path=".agent/cache/context.db",
            max_profile_files=100,
        )
        security = SecurityConfig(allowed_executables=[], denied_substrings=[])

        def observer(phase: str, result: object) -> None:
            events.append(phase)

        return QualityService(root, quality, context, security, observer=observer)

    def test_analysis_escalates_to_details_and_caches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.py").write_text("def work(x):\n    return x\n", encoding="utf-8")
            events: list[str] = []
            service = self._service(root, events)
            first_dir = root / ".agent/state/runs/first"
            first_dir.mkdir(parents=True)
            first = service.analyze(first_dir)
            self.assertEqual(first.snapshot.availability, Availability.AVAILABLE)
            self.assertTrue(first.snapshot.details)
            self.assertEqual(len(first.snapshot.hotspots), 1)
            self.assertEqual(events, ["quality_before", "quality_before"])
            self.assertTrue(first.artifacts.snapshot_path.is_file())

            events.clear()
            second_dir = root / ".agent/state/runs/second"
            second_dir.mkdir(parents=True)
            second = service.analyze(second_dir)
            self.assertTrue(second.snapshot.cache_hit)
            self.assertEqual(events, [])

            (root / "sample.py").write_text(
                "def work(x):\n    if x:\n        return x\n    return 0\n",
                encoding="utf-8",
            )
            events.clear()
            third_dir = root / ".agent/state/runs/third"
            third_dir.mkdir(parents=True)
            third = service.analyze(third_dir)
            self.assertFalse(third.snapshot.cache_hit)
            self.assertEqual(events, ["quality_before", "quality_before"])

    def test_unavailable_provider_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.py").write_text("x = 1\n", encoding="utf-8")
            service = QualityService(
                root,
                QualityConfig(command=["definitely-missing-strictacode"]),
                ContextConfig(cache_path=".agent/cache/context.db"),
                SecurityConfig(allowed_executables=[], denied_substrings=[]),
            )
            run_dir = root / ".agent/state/runs/unavailable"
            run_dir.mkdir(parents=True)
            result = service.analyze(run_dir)
            self.assertEqual(result.snapshot.availability, Availability.UNAVAILABLE)
            self.assertIsNone(result.snapshot.project)
            self.assertNotEqual(result.warning, "")


if __name__ == "__main__":
    unittest.main()
