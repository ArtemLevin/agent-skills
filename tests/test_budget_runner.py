from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from agentkit.adapters.base import AgentAdapter
from agentkit.config import load_config, write_default_config
from agentkit.models import CommandResult, RunMode, Stage, TokenUsage
from agentkit.runner import AgentKitRunner, RunRequest


class UsageAdapter(AgentAdapter):
    def execute(self, prompt: str, *, phase: str, cwd: Path) -> CommandResult:
        return CommandResult(
            ["fake-agent"],
            0,
            "planned",
            "",
            0.1,
            usage=TokenUsage(input_tokens=10, output_tokens=1, total_tokens=11, measured=True),
        )


class BudgetRunnerTests(unittest.TestCase):
    def test_hard_budget_stops_after_measured_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            (root / "README.md").write_text("test", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True)

            path = write_default_config(root)
            text = path.read_text(encoding="utf-8")
            text = text.replace("require_clean_tree = true", "require_clean_tree = false")
            text = text.replace("hard_input_tokens = 60000", "hard_input_tokens = 5")
            path.write_text(text, encoding="utf-8")

            outcome = AgentKitRunner(
                root,
                config=load_config(root),
                adapter=UsageAdapter(),
            ).run(
                RunRequest(
                    task="Prepare a plan",
                    mode=RunMode.STANDARD,
                    plan_only=True,
                    skip_graph=True,
                )
            )
            self.assertEqual(outcome.stage, Stage.BUDGET_EXCEEDED)
            self.assertEqual(outcome.exit_code, 5)
            usage = root / ".agent" / "state" / "runs" / outcome.run_id / "usage.json"
            self.assertTrue(usage.is_file())


if __name__ == "__main__":
    unittest.main()
