from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.quality.resources_hotspot import ensure_hotspot_context_files


class HotspotResourceTests(unittest.TestCase):
    def test_make_skill_and_schema_are_installed_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".agent").mkdir()
            ensure_hotspot_context_files(root)
            ensure_hotspot_context_files(root)
            make = (root / ".agent/Makefile.agent").read_text(encoding="utf-8")
            self.assertEqual(make.count("# BEGIN AGENTKIT HOTSPOT CONTEXT"), 1)
            self.assertIn("ai-context-hotspots", make)
            self.assertTrue((root / ".agent/skills/hotspot-aware-context/SKILL.md").is_file())
            self.assertTrue((root / ".agent/schemas/hotspot-context.schema.json").is_file())


if __name__ == "__main__":
    unittest.main()
