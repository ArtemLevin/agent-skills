from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.config import BudgetConfig
from agentkit.models import CommandResult, TokenUsage
from agentkit.telemetry import BudgetController, UsageLedger, parse_token_usage


class TelemetryTests(unittest.TestCase):
    def test_parses_openai_compatible_json_usage(self) -> None:
        usage = parse_token_usage(
            '{"usage":{"input_tokens":120,"output_tokens":30,'
            '"input_tokens_details":{"cached_tokens":80},"total_tokens":150}}'
        )
        self.assertTrue(usage.measured)
        self.assertEqual(usage.input_tokens, 120)
        self.assertEqual(usage.output_tokens, 30)
        self.assertEqual(usage.cached_input_tokens, 80)
        self.assertEqual(usage.total_tokens, 150)

    def test_parses_text_usage_and_does_not_invent_missing_usage(self) -> None:
        usage = parse_token_usage("Input tokens: 1,200\nOutput tokens: 300")
        self.assertEqual(usage.total_tokens, 1500)
        missing = parse_token_usage("normal agent output")
        self.assertFalse(missing.measured)
        self.assertEqual(missing.total_tokens, 0)

    def test_ledger_separates_agent_and_tool_calls(self) -> None:
        ledger = UsageLedger(run_id="run-1", provider="codex")
        ledger.record(
            phase="implementation",
            kind="agent",
            result=CommandResult(
                ["codex"],
                0,
                "",
                "",
                2.5,
                usage=TokenUsage(
                    input_tokens=100,
                    output_tokens=20,
                    total_tokens=120,
                    measured=True,
                    source="test",
                ),
            ),
        )
        ledger.record(
            phase="verification",
            kind="tool",
            provider="local",
            result=CommandResult(["pytest"], 0, "", "", 1.0),
        )
        totals = ledger.totals()
        self.assertEqual(totals["agent_calls"], 1)
        self.assertEqual(totals["tool_calls"], 1)
        self.assertEqual(totals["input_tokens"], 100)
        self.assertEqual(totals["duration_seconds"], 3.5)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.json"
            ledger.save(path)
            loaded = UsageLedger.load(path)
            self.assertEqual(loaded.totals(), totals)

    def test_budget_blocks_next_call_and_detects_overspend(self) -> None:
        config = BudgetConfig(
            soft_input_tokens=5,
            hard_input_tokens=10,
            soft_output_tokens=0,
            hard_output_tokens=0,
            soft_agent_calls=1,
            hard_agent_calls=2,
            soft_duration_seconds=0,
            hard_duration_seconds=0,
            phase_agent_call_limits={"implementation": 1},
        )
        ledger = UsageLedger(run_id="run-1", provider="codex")
        ledger.record(
            phase="implementation",
            kind="agent",
            result=CommandResult(
                ["codex"],
                0,
                "",
                "",
                1.0,
                usage=TokenUsage(input_tokens=11, total_tokens=11, measured=True),
            ),
        )
        status = BudgetController(config).evaluate(ledger)
        self.assertFalse(status.allowed)
        self.assertTrue(status.soft_limits_reached)
        self.assertTrue(status.hard_limits_exceeded)
        allowed, reason = BudgetController(config).can_start_agent_call(
            ledger, "implementation"
        )
        self.assertFalse(allowed)
        self.assertIn("hard limit", reason)


if __name__ == "__main__":
    unittest.main()
