from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.config import load_config, write_default_config


class ConfigTests(unittest.TestCase):
    def test_default_config_loads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_default_config(root)
            config = load_config(root)
            self.assertEqual(config.agent.platform, "codex")
            self.assertEqual(config.agent.command[:2], ["codex", "exec"])
            self.assertTrue(config.graphify.enabled)
            self.assertTrue(config.workflow.require_clean_tree)
            self.assertTrue(config.budget.enabled)
            self.assertEqual(config.budget.phase_agent_call_limits["implementation"], 1)

    def test_invalid_verification_command_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_default_config(root)
            text = path.read_text(encoding="utf-8").replace("commands = []", 'commands = ["pytest"]')
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "argv array"):
                load_config(root)

    def test_invalid_unknown_usage_policy_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_default_config(root)
            text = path.read_text(encoding="utf-8").replace(
                'unknown_usage_policy = "warn"', 'unknown_usage_policy = "guess"'
            )
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "allow, warn, or stop"):
                load_config(root)


if __name__ == "__main__":
    unittest.main()
