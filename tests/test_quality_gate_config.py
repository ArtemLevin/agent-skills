from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.quality.config import ensure_quality_config, load_quality_config


class QualityGateConfigTests(unittest.TestCase):
    def _root(self, content: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        (root / ".agent").mkdir()
        (root / ".agent" / "agentkit.toml").write_text(content, encoding="utf-8")
        return temporary, root

    def test_gate_configuration_loads(self) -> None:
        temporary, root = self._root(
            """
[quality]
mode = "enforce"
baseline_strategy = "merge_base"
base_branch = "develop"
unavailable_policy = "stop"
[quality.absolute]
score = 30
[quality.delta]
rp = 2
new_critical_hotspots = 1
"""
        )
        with temporary:
            config = load_quality_config(root)
            self.assertEqual(config.mode, "enforce")
            self.assertEqual(config.baseline_strategy, "merge_base")
            self.assertEqual(config.absolute.score, 30)
            self.assertEqual(config.delta.rp, 2)
            self.assertEqual(config.delta.new_critical_hotspots, 1)

    def test_file_strategy_requires_path(self) -> None:
        temporary, root = self._root("""
[quality]
baseline_strategy = "file"
""")
        with temporary:
            with self.assertRaisesRegex(ValueError, "baseline_file"):
                load_quality_config(root)

    def test_invalid_modes_are_rejected(self) -> None:
        temporary, root = self._root("""
[quality]
mode = "block-everything"
""")
        with temporary:
            with self.assertRaisesRegex(ValueError, "report, warn, or enforce"):
                load_quality_config(root)

    def test_migration_adds_missing_fields_idempotently(self) -> None:
        temporary, root = self._root("""
[quality]
mode = "report"
# END AGENTKIT QUALITY
""")
        with temporary:
            ensure_quality_config(root)
            first = (root / ".agent" / "agentkit.toml").read_text(encoding="utf-8")
            ensure_quality_config(root)
            second = (root / ".agent" / "agentkit.toml").read_text(encoding="utf-8")
            self.assertEqual(first, second)
            self.assertIn("baseline_strategy", first)
            self.assertIn("[quality.absolute]", first)
            self.assertIn("[quality.delta]", first)


if __name__ == "__main__":
    unittest.main()
