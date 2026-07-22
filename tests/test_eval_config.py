from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.config import write_default_config
from agentkit.evals.config import ensure_evaluation_config, load_evaluation_config


class EvaluationConfigTests(unittest.TestCase):
    def test_config_migration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_default_config(root)
            ensure_evaluation_config(root)
            first = path.read_text(encoding="utf-8")
            ensure_evaluation_config(root)
            second = path.read_text(encoding="utf-8")
            self.assertEqual(first, second)
            self.assertEqual(load_evaluation_config(root).max_repetitions, 10)


if __name__ == "__main__":
    unittest.main()
