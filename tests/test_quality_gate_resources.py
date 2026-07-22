from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentkit.quality.resources_gate import QUALITY_DIFF_SCHEMA, QUALITY_GATE_SCHEMA, ensure_quality_gate_project_files


class QualityGateResourceTests(unittest.TestCase):
    def test_schemas_are_json(self) -> None:
        json.loads(QUALITY_DIFF_SCHEMA)
        json.loads(QUALITY_GATE_SCHEMA)

    def test_make_and_resources_are_installed_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".agent").mkdir()
            (root / ".agent" / "Makefile.agent").write_text("AGENTKIT ?= agentkit\n", encoding="utf-8")
            ensure_quality_gate_project_files(root)
            ensure_quality_gate_project_files(root)
            makefile = (root / ".agent" / "Makefile.agent").read_text(encoding="utf-8")
            for target in (
                "ai-quality-baseline",
                "ai-quality-after",
                "ai-quality-compare",
                "ai-quality-gate",
                "ai-quality-cycle",
            ):
                self.assertIn(target, makefile)
            self.assertEqual(makefile.count("# BEGIN AGENTKIT QUALITY GATE"), 1)
            self.assertTrue((root / ".agent" / "skills" / "quality-regression-gate" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
