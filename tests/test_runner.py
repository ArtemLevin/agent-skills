from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from agentkit.config import load_config, write_default_config
from agentkit.models import RunMode, Stage
from agentkit.runner import AgentKitRunner, RunRequest


class RunnerTests(unittest.TestCase):
    def _git_project(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
        (root / "README.md").write_text("test", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True)

    def _dirty_allowed_config(self, root: Path) -> None:
        write_default_config(root)
        config_path = root / ".agent" / "agentkit.toml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                "require_clean_tree = true",
                "require_clean_tree = false",
            ),
            encoding="utf-8",
        )

    def test_dry_run_creates_packet_without_agent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git_project(root)
            self._dirty_allowed_config(root)
            runner = AgentKitRunner(root, config=load_config(root))
            outcome = runner.run(
                RunRequest(task="Fix a small bug", mode=RunMode.STANDARD, dry_run=True, skip_graph=True)
            )
            self.assertEqual(outcome.stage, Stage.TRIAGE)
            packet = root / ".agent" / "state" / "runs" / outcome.run_id / "task-packet.json"
            self.assertTrue(packet.is_file())

    def test_deep_mode_requires_explicit_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git_project(root)
            self._dirty_allowed_config(root)
            outcome = AgentKitRunner(root, config=load_config(root)).run(
                RunRequest(task="Run database migration", skip_graph=True)
            )
            self.assertEqual(outcome.stage, Stage.APPROVAL_REQUIRED)
            self.assertEqual(outcome.exit_code, 3)


if __name__ == "__main__":
    unittest.main()
