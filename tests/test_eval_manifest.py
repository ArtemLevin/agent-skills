from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.evals.manifest import load_manifest, manifest_fingerprint


class EvaluationManifestTests(unittest.TestCase):
    def test_parses_committed_yaml_subset_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "task.yaml"
            path.write_text(
                """version: 1
id: local-bugfix-001
repository_fixture: evals/fixture
mode: standard
task: Fix duplicate scheduling
acceptance:
  commands:
    - [python, -m, unittest, discover, -s, tests]
  required_files:
    - tests/test_retry.py
quality:
  allow_new_critical_hotspots: 0
experiment:
  graphify: true
""",
                encoding="utf-8",
            )
            first = load_manifest(path)
            second = load_manifest(path)
            self.assertEqual(first, second)
            self.assertEqual(first.acceptance.commands[0][0], "python")
            self.assertEqual(manifest_fingerprint(first), manifest_fingerprint(second))

    def test_rejects_parent_fixture_path_and_secret_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "task.json"
            path.write_text(
                '{"id":"bad-task-001","repository_fixture":"../fixture",'
                '"mode":"standard","task":"x","experiment":{"api_key":"x"}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "safe relative path"):
                load_manifest(path)


if __name__ == "__main__":
    unittest.main()
