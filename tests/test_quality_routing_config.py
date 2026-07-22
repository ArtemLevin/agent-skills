from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.quality.routing_config import (
    ensure_quality_routing_config,
    load_quality_routing_config,
)


class QualityRoutingConfigTests(unittest.TestCase):
    def test_defaults_and_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".agent").mkdir()
            path = root / ".agent/agentkit.toml"
            path.write_text('version = 1\n\n[quality]\nenabled = true\n', encoding="utf-8")
            ensure_quality_routing_config(root)
            ensure_quality_routing_config(root)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("[quality.routing]"), 1)
            config = load_quality_routing_config(root)
            self.assertTrue(config.enabled)
            self.assertEqual(config.characterization_complexity, 40)

    def test_negative_threshold_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".agent").mkdir()
            (root / ".agent/agentkit.toml").write_text(
                '[quality.routing]\nedge_case_complexity = -1\n',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_quality_routing_config(root)


if __name__ == "__main__":
    unittest.main()
