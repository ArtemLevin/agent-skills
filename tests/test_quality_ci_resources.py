from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentkit.quality.resources_ci import ensure_quality_ci_files


class QualityCIResourcesTests(unittest.TestCase):
    def test_installs_resources_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / ".agent/agentkit.toml"
            config.parent.mkdir(parents=True)
            config.write_text("[quality]\nenabled = true\n", encoding="utf-8")
            ensure_quality_ci_files(root)
            ensure_quality_ci_files(root)

            makefile = (root / ".agent/Makefile.agent").read_text(encoding="utf-8")
            self.assertEqual(
                makefile.count("# BEGIN AGENTKIT QUALITY CI"),
                1,
            )
            self.assertIn("ai-quality-ci-install", makefile)
            self.assertTrue(
                (root / ".agent/skills/quality-ci/SKILL.md").is_file()
            )
            schema = json.loads(
                (root / ".agent/schemas/quality-ci-result.schema.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(schema["title"], "AgentKit quality CI result")
            self.assertIn(
                "fetch-depth: 0",
                (root / ".agent/templates/agentkit-quality.yml")
                .read_text(encoding="utf-8"),
            )
            text = config.read_text(encoding="utf-8")
            self.assertEqual(text.count("[quality.ci]"), 1)


if __name__ == "__main__":
    unittest.main()
