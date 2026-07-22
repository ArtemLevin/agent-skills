from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.project_profile import build_project_profile, load_or_create_profile


class ProjectProfileTests(unittest.TestCase):
    def test_detects_python_project_and_reuses_current_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "src" / "service.py").write_text("def run():\n    return 1\n", encoding="utf-8")
            (root / "tests" / "test_service.py").write_text("import pytest\n", encoding="utf-8")
            (root / "pyproject.toml").write_text(
                '[project]\nname="demo"\ndependencies=["pytest", "fastapi"]\n[tool.pytest.ini_options]\n',
                encoding="utf-8",
            )
            profile = build_project_profile(root)
            self.assertIn("python", profile.languages)
            self.assertIn("pip", profile.package_managers)
            self.assertIn("fastapi", profile.frameworks)
            self.assertEqual(profile.source_roots, ["src"])
            self.assertEqual(profile.test_roots, ["tests"])
            path = root / ".agent" / "project-profile.json"
            first, refreshed = load_or_create_profile(root, path)
            second, refreshed_again = load_or_create_profile(root, path)
            self.assertTrue(refreshed)
            self.assertFalse(refreshed_again)
            self.assertEqual(first.fingerprint, second.fingerprint)


if __name__ == "__main__":
    unittest.main()
