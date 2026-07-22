from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentkit.quality.resources_routing import ensure_quality_routing_files


class QualityRoutingResourceTests(unittest.TestCase):
    def test_resources_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".agent").mkdir()
            (root / ".agent/agentkit.toml").write_text("version = 1\n", encoding="utf-8")
            ensure_quality_routing_files(root)
            ensure_quality_routing_files(root)
            makefile = (root / ".agent/Makefile.agent").read_text(encoding="utf-8")
            self.assertEqual(makefile.count("# BEGIN AGENTKIT QUALITY ROUTING"), 1)
            self.assertIn("ai-quality-triage", makefile)
            self.assertTrue((root / ".agent/skills/quality-aware-routing/SKILL.md").is_file())
            for name in ("quality-route.schema.json", "verification-plan.schema.json"):
                payload = json.loads((root / ".agent/schemas" / name).read_text(encoding="utf-8"))
                self.assertEqual(payload["type"], "object")


if __name__ == "__main__":
    unittest.main()
