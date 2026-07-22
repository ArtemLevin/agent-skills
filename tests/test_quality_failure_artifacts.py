from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from agentkit.config import ContextConfig, SecurityConfig
from agentkit.quality.config import QualityConfig
from agentkit.quality.models import Availability
from agentkit.quality.service import QualityService


class QualityFailureArtifactTests(unittest.TestCase):
    def test_malformed_output_is_explicit_and_preserved_locally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.py").write_text("x = 1\n", encoding="utf-8")
            script = root / "broken_provider.py"
            script.write_text("print('not-json')\n", encoding="utf-8")
            service = QualityService(
                root,
                QualityConfig(
                    command=[sys.executable, str(script)],
                    details_policy="never",
                ),
                ContextConfig(cache_path=".agent/cache/context.db"),
                SecurityConfig(allowed_executables=[], denied_substrings=[]),
            )
            run_dir = root / ".agent/state/runs/failure"
            run_dir.mkdir(parents=True)
            result = service.analyze(run_dir)
            self.assertEqual(result.snapshot.availability, Availability.FAILED)
            self.assertTrue(result.artifacts.raw_stdout_path.is_file())
            self.assertEqual(
                result.artifacts.raw_stdout_path.read_text(encoding="utf-8").strip(),
                "not-json",
            )


if __name__ == "__main__":
    unittest.main()
