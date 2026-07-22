from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentkit.evals.runner import _copy_agent_artifacts
from agentkit.model_runtime.resources import ensure_model_runtime_files


class ModelRuntimeResourceTests(unittest.TestCase):
    def test_installs_skill_and_schemas_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = ensure_model_runtime_files(root)
            second = ensure_model_runtime_files(root)
            self.assertEqual(first, second)
            self.assertTrue((root / ".agent/skills/model-routing/SKILL.md").is_file())
            for name in (
                "agent-capabilities.schema.json",
                "model-route.schema.json",
                "model-attempts.schema.json",
                "prompt-prefix.schema.json",
            ):
                payload = json.loads((root / ".agent/schemas" / name).read_text(encoding="utf-8"))
                self.assertEqual(payload["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_evaluation_copy_preserves_model_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            for name in (
                "model-route.json",
                "model-attempts.json",
                "prompt-prefix-review.json",
            ):
                (source / name).write_text("{}", encoding="utf-8")
            copied = _copy_agent_artifacts(source, target)
            self.assertEqual(copied, target)
            self.assertTrue((target / "model-route.json").is_file())
            self.assertTrue((target / "model-attempts.json").is_file())
            self.assertTrue((target / "prompt-prefix-review.json").is_file())


if __name__ == "__main__":
    unittest.main()
