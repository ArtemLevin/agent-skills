from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.quality.ci_config import (
    ensure_quality_ci_config,
    load_quality_ci_config,
)


class QualityCIConfigTests(unittest.TestCase):
    def test_defaults_and_migration_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".agent/agentkit.toml"
            path.parent.mkdir(parents=True)
            path.write_text("[quality]\nenabled = true\n", encoding="utf-8")

            ensure_quality_ci_config(root)
            ensure_quality_ci_config(root)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("[quality.ci]"), 1)
            config = load_quality_ci_config(root)
            self.assertEqual(
                config.workflow_path,
                ".github/workflows/agentkit-quality.yml",
            )
            self.assertEqual(config.artifact_retention_days, 7)

    def test_rejects_unsafe_workflow_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".agent/agentkit.toml"
            path.parent.mkdir(parents=True)
            path.write_text(
                "[quality]\n[quality.ci]\nworkflow_path = \"../outside.yml\"\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "project-relative"):
                load_quality_ci_config(root)

    def test_rejects_unsafe_base_branch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".agent/agentkit.toml"
            path.parent.mkdir(parents=True)
            path.write_text(
                "[quality]\n[quality.ci]\nbase_branch = \"main; echo unsafe\"\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "safe branch"):
                load_quality_ci_config(root)

    def test_rejects_invalid_retention(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".agent/agentkit.toml"
            path.parent.mkdir(parents=True)
            path.write_text(
                "[quality]\n[quality.ci]\nartifact_retention_days = 91\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "between 1 and 90"):
                load_quality_ci_config(root)


if __name__ == "__main__":
    unittest.main()
