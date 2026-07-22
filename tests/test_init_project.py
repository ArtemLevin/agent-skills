from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentkit.init_project import initialize_project


class InitProjectTests(unittest.TestCase):
    def test_initializes_embedded_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {"AGENTKIT_SOURCE": str(root / "missing")}, clear=False):
                result = initialize_project(root)
            self.assertTrue((root / ".agent" / "agentkit.toml").is_file())
            self.assertTrue((root / ".agent" / "AGENT.md").is_file())
            self.assertTrue((root / ".agent" / "skills" / "task-triage" / "SKILL.md").is_file())
            self.assertIn("-include .agent/Makefile.agent", (root / "Makefile").read_text(encoding="utf-8"))
            self.assertIn("graphify-out/", (root / ".gitignore").read_text(encoding="utf-8"))
            generated = (root / ".agent" / "Makefile.agent").read_text(encoding="utf-8")
            self.assertIn("ai-usage:", generated)
            self.assertIn("ai-budget:", generated)
            self.assertIn("ai-report:", generated)
            self.assertIn(result["resource_mode"], {"embedded-core-kit", "full-source-kit"})

    def test_init_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_project(root)
            initialize_project(root)
            makefile = (root / "Makefile").read_text(encoding="utf-8")
            self.assertEqual(makefile.count("# BEGIN AGENTKIT"), 1)


if __name__ == "__main__":
    unittest.main()
