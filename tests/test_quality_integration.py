from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agentkit.config import load_config, write_default_config
from agentkit.graphify import GraphContext
from agentkit.models import RunMode, TriageResult
from agentkit.quality.config import ensure_quality_config
from agentkit.quality.integration import QualityAwareRunner
from agentkit.runner import AgentKitError, RunRequest


class QualityIntegrationTests(unittest.TestCase):
    def _root(self, directory: str, *, required: bool) -> Path:
        root = Path(directory)
        config_path = write_default_config(root)
        ensure_quality_config(root)
        text = config_path.read_text(encoding="utf-8")
        text = text.replace("required = false", f"required = {'true' if required else 'false'}")
        text = text.replace('command = ["strictacode"]', 'command = ["missing-quality-provider"]')
        config_path.write_text(text, encoding="utf-8")
        (root / "sample.py").write_text("x = 1\n", encoding="utf-8")
        return root

    def test_optional_unavailable_provider_is_added_to_task_packet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory, required=False)
            runner = QualityAwareRunner(root, config=load_config(root))
            run_dir = root / ".agent/state/runs/test"
            run_dir.mkdir(parents=True)
            runner._quality_runtime = (
                SimpleNamespace(directory=run_dir),
                lambda phase, result: None,
            )
            packet = runner._task_packet(
                RunRequest(task="test"),
                TriageResult(RunMode.STANDARD, [], []),
                GraphContext(False, False, "", "", "skipped"),
                "head",
            )
            self.assertEqual(packet["quality"]["availability"], "unavailable")
            self.assertTrue((run_dir / "quality-before.json").is_file())

    def test_required_unavailable_provider_stops_before_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory, required=True)
            runner = QualityAwareRunner(root, config=load_config(root))
            run_dir = root / ".agent/state/runs/test"
            run_dir.mkdir(parents=True)
            runner._quality_runtime = (
                SimpleNamespace(directory=run_dir),
                lambda phase, result: None,
            )
            with self.assertRaisesRegex(AgentKitError, "Required quality provider"):
                runner._task_packet(
                    RunRequest(task="test"),
                    TriageResult(RunMode.STANDARD, [], []),
                    GraphContext(False, False, "", "", "skipped"),
                    "head",
                )


if __name__ == "__main__":
    unittest.main()
