from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.quality.ci_config import QualityCIConfig, load_quality_ci_config
from agentkit.quality.ci_workflow import render_quality_workflow


class EvaluationCISmokeTests(unittest.TestCase):
    def test_smoke_suite_is_explicit_and_provider_cost_opt_in(self) -> None:
        default = render_quality_workflow(QualityCIConfig())
        enabled = render_quality_workflow(QualityCIConfig(eval_smoke_enabled=True))
        self.assertNotIn("agentkit eval suite", default)
        self.assertIn("agentkit eval suite", enabled)
        self.assertIn("--smoke", enabled)
        self.assertIn("AGENTKIT_EVAL_ID", enabled)

    def test_rejects_unsafe_eval_directory_and_repetition_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".agent/agentkit.toml"
            path.parent.mkdir(parents=True)
            path.write_text(
                "[quality]\n[quality.ci]\neval_manifest_directory = \"../outside\"\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "project-relative"):
                load_quality_ci_config(root)
            path.write_text(
                "[quality]\n[quality.ci]\neval_repetitions = 11\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "between 1 and 10"):
                load_quality_ci_config(root)


if __name__ == "__main__":
    unittest.main()
