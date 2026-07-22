from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentkit.models import CommandResult, TokenUsage
from agentkit.reporting import aggregate_report
from agentkit.telemetry import UsageLedger


class ReportingTests(unittest.TestCase):
    def test_aggregates_recent_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / ".agent" / "state" / "runs"
            for index, ready in ((1, True), (2, False)):
                run_dir = runs / f"run-{index}"
                run_dir.mkdir(parents=True)
                ledger = UsageLedger(run_id=run_dir.name, provider="codex")
                ledger.record(
                    phase="implementation",
                    kind="agent",
                    result=CommandResult(
                        ["codex"],
                        0,
                        "",
                        "",
                        float(index),
                        usage=TokenUsage(
                            input_tokens=100 * index,
                            output_tokens=10 * index,
                            total_tokens=110 * index,
                            measured=True,
                        ),
                    ),
                )
                ledger.save(run_dir / "usage.json")
                (run_dir / "completion.json").write_text(
                    json.dumps(
                        {
                            "status": "ready_for_review" if ready else "needs_attention",
                            "ready": ready,
                        }
                    ),
                    encoding="utf-8",
                )
            report = aggregate_report(root, limit=20)
            self.assertEqual(report["runs"], 2)
            self.assertEqual(report["ready_runs"], 1)
            self.assertEqual(report["totals"]["input_tokens"], 300)
            self.assertEqual(report["phases"]["implementation"]["agent_calls"], 2)


if __name__ == "__main__":
    unittest.main()
