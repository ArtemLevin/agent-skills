from __future__ import annotations

import unittest

from agentkit.quality.routing_cli import ROUTING_COMMANDS, build_parser


class QualityRoutingCliTests(unittest.TestCase):
    def test_expected_commands_are_registered(self) -> None:
        self.assertEqual(ROUTING_COMMANDS, {"triage", "plan-checks", "explain-route"})
        args = build_parser().parse_args(["triage", "--task", "fix service"])
        self.assertEqual(args.quality_command, "triage")


if __name__ == "__main__":
    unittest.main()
