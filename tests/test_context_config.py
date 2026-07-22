from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.config import load_config, write_default_config


class ContextConfigTests(unittest.TestCase):
    def test_default_context_config_loads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_default_config(root)
            config = load_config(root)
            self.assertTrue(config.context.enabled)
            self.assertTrue(config.context.cache_enabled)
            self.assertEqual(config.context.max_candidate_files, 12)
            self.assertEqual(config.context.cache_path, ".agent/cache/context.db")

    def test_negative_context_limit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_default_config(root)
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "max_candidate_files = 12", "max_candidate_files = -1"
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "zero or positive"):
                load_config(root)


if __name__ == "__main__":
    unittest.main()
