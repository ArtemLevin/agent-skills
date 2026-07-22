from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.quality.ci_config import QualityCIConfig
from agentkit.quality.ci_workflow import (
    install_quality_workflow,
    render_quality_workflow,
)


class QualityCIWorkflowTests(unittest.TestCase):
    def test_renderer_matches_golden_template(self) -> None:
        expected = (
            Path(__file__).resolve().parents[1]
            / "templates"
            / "agentkit-quality.yml"
        ).read_text(encoding="utf-8")
        self.assertEqual(render_quality_workflow(QualityCIConfig()), expected)

    def test_workflow_is_read_only_and_provider_neutral(self) -> None:
        content = render_quality_workflow(QualityCIConfig())
        self.assertIn("permissions:\n  contents: read", content)
        self.assertNotIn("pull-requests: write", content)
        self.assertIn("fetch-depth: 0", content)
        self.assertIn("agentkit ci quality run-local", content)
        self.assertNotIn("strictacode analyze", content)
        self.assertIn("if: always()", content)
        self.assertIn("actions/cache@v4", content)
        self.assertIn("actions/upload-artifact@v4", content)

    def test_shell_values_are_quoted(self) -> None:
        content = render_quality_workflow(
            QualityCIConfig(package_spec="package; echo unsafe")
        )
        self.assertIn(
            "python -m pip install 'package; echo unsafe'",
            content,
        )

    def test_does_not_overwrite_modified_workflow_without_force(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent kit ") as directory:
            root = Path(directory)
            config = QualityCIConfig()
            path, changed = install_quality_workflow(root, config)
            self.assertTrue(changed)
            path.write_text("name: custom\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "--force"):
                install_quality_workflow(root, config)
            _, changed = install_quality_workflow(root, config, force=True)
            self.assertTrue(changed)
            self.assertIn("name: AgentKit Quality", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
