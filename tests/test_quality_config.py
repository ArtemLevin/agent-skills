from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.config import write_default_config
from agentkit.quality.config import ensure_quality_config, load_quality_config


class QualityConfigTests(unittest.TestCase):
    def test_missing_section_uses_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_default_config(root)
            config = load_quality_config(root)
            self.assertTrue(config.enabled)
            self.assertFalse(config.required)
            self.assertEqual(config.mode, "report")

    def test_ensure_appends_section_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_default_config(root)
            ensure_quality_config(root)
            ensure_quality_config(root)
            self.assertEqual(path.read_text(encoding="utf-8").count("[quality]"), 1)

    def test_invalid_policy_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_default_config(root)
            path.write_text(
                path.read_text(encoding="utf-8") + '\n[quality]\ndetails_policy = "sometimes"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "never, on_warning, or always"):
                load_quality_config(root)


if __name__ == "__main__":
    unittest.main()
