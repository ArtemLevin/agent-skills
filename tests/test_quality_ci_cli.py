from __future__ import annotations

import unittest

from agentkit.quality.ci_cli import build_parser


class QualityCIParserTests(unittest.TestCase):
    def test_parses_planned_commands(self) -> None:
        parser = build_parser()
        install = parser.parse_args(["quality", "install", "--force"])
        self.assertEqual(install.ci_command, "install")
        self.assertTrue(install.force)

        local = parser.parse_args(
            [
                "quality",
                "run-local",
                "--base-ref",
                "origin/main",
                "--run-id",
                "ci-1",
            ]
        )
        self.assertEqual(local.base_ref, "origin/main")
        self.assertEqual(local.run_id, "ci-1")

        summary = parser.parse_args(
            ["quality", "summary", "--run-id", "latest", "--annotations"]
        )
        self.assertEqual(summary.ci_command, "summary")
        self.assertTrue(summary.annotations)


if __name__ == "__main__":
    unittest.main()
