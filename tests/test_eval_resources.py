from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.config import write_default_config
from agentkit.evals.resources import ensure_evaluation_files


class EvaluationResourcesTests(unittest.TestCase):
    def test_installs_make_skill_schemas_and_template_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_default_config(root)
            ensure_evaluation_files(root)
            makefile = root / ".agent/Makefile.agent"
            first = makefile.read_text(encoding="utf-8")
            ensure_evaluation_files(root)
            self.assertEqual(first, makefile.read_text(encoding="utf-8"))
            self.assertTrue((root / ".agent/skills/evaluation-harness/SKILL.md").is_file())
            self.assertTrue((root / ".agent/schemas/eval-summary.schema.json").is_file())
            self.assertTrue((root / ".agent/templates/eval-task.yaml").is_file())


if __name__ == "__main__":
    unittest.main()
