from __future__ import annotations

import unittest

from agentkit.adapters.command import CommandAgentAdapter
from agentkit.commands import CommandPolicy


class AdapterTests(unittest.TestCase):
    def test_renders_prompt_placeholder(self) -> None:
        adapter = CommandAgentAdapter(
            ["codex", "exec", "{prompt}", "--phase={phase}"],
            timeout_seconds=1,
            policy=CommandPolicy(["codex"], []),
        )
        self.assertEqual(
            adapter.render("do work", "review"),
            ["codex", "exec", "do work", "--phase=review"],
        )

    def test_appends_prompt_without_placeholder(self) -> None:
        adapter = CommandAgentAdapter(
            ["aider", "--message"],
            timeout_seconds=1,
            policy=CommandPolicy(["aider"], []),
        )
        self.assertEqual(adapter.render("task", "implementation"), ["aider", "--message", "task"])


if __name__ == "__main__":
    unittest.main()
