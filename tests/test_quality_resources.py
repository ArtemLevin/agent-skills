from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.config import write_default_config
from agentkit.quality.resources import ensure_quality_project_files


class QualityResourceTests(unittest.TestCase):
    def test_install_adds_make_config_skill_and_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_default_config(root)
            makefile = root / ".agent/Makefile.agent"
            makefile.write_text("AGENTKIT ?= agentkit\n", encoding="utf-8")
            first = ensure_quality_project_files(root)
            second = ensure_quality_project_files(root)
            self.assertEqual(first, second)
            text = makefile.read_text(encoding="utf-8")
            self.assertEqual(text.count("# BEGIN AGENTKIT QUALITY"), 1)
            for target in (
                "ai-quality-doctor",
                "ai-quality:",
                "ai-quality-details",
                "ai-quality-hotspots",
                "ai-quality-show",
            ):
                self.assertIn(target, text)
            self.assertTrue((root / ".agent/skills/quality-diagnostics/SKILL.md").is_file())
            self.assertTrue((root / ".agent/schemas/quality-snapshot.schema.json").is_file())


if __name__ == "__main__":
    unittest.main()
