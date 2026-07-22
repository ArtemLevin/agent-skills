from __future__ import annotations

import unittest

from agentkit.evals.cli import (
    build_efficiency_parser,
    build_eval_parser,
    build_quality_history_parser,
)


class EvaluationCLITests(unittest.TestCase):
    def test_eval_quality_and_efficiency_commands_parse(self) -> None:
        self.assertEqual(build_eval_parser().parse_args(["run", "task.yaml"]).eval_command, "run")
        self.assertEqual(
            build_quality_history_parser().parse_args(["regressions", "--limit", "5"]).history_command,
            "regressions",
        )
        self.assertEqual(
            build_efficiency_parser().parse_args(["report"]).efficiency_command,
            "report",
        )


if __name__ == "__main__":
    unittest.main()
