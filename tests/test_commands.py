from __future__ import annotations

import unittest

from agentkit.commands import CommandPolicy, CommandPolicyError


class CommandPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = CommandPolicy(["python", "git"], ["git reset --hard", "rm -rf /"])

    def test_allows_listed_executable(self) -> None:
        self.policy.validate(["python", "-m", "unittest"])

    def test_rejects_unknown_executable(self) -> None:
        with self.assertRaisesRegex(CommandPolicyError, "allowlist"):
            self.policy.validate(["curl", "https://example.com"])

    def test_rejects_denied_fragment(self) -> None:
        with self.assertRaisesRegex(CommandPolicyError, "denied fragment"):
            self.policy.validate(["git", "reset", "--hard"])


if __name__ == "__main__":
    unittest.main()
