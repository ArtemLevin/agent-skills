from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from agentkit.commands import CommandPolicy
from agentkit.quality.config import QualityConfig
from agentkit.quality.models import Availability
from agentkit.quality.strictacode import StrictaCodeProvider


class QualityProviderTests(unittest.TestCase):
    def test_unsupported_language_is_distinct_from_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
            provider = StrictaCodeProvider(
                QualityConfig(command=[sys.executable, "-c", "print('{}')"]),
                CommandPolicy([Path(sys.executable).stem], []),
            )
            status = provider.doctor(root)
            self.assertEqual(status.availability, Availability.UNSUPPORTED)
            self.assertIn("rust", status.detected_languages)


if __name__ == "__main__":
    unittest.main()
