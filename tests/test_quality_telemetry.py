# ruff: noqa: E501
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from agentkit.config import ContextConfig, SecurityConfig
from agentkit.quality.config import QualityConfig
from agentkit.quality.service import QualityService
from agentkit.telemetry import UsageLedger


class QualityTelemetryTests(unittest.TestCase):
    def test_quality_tool_call_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.py").write_text("x = 1\n", encoding="utf-8")
            script = root / "provider.py"
            script.write_text(
                "import json\nprint(json.dumps({'project': {'lang':'python','loc':1,'status':{'name':'healthy','score':1},'refactoring_pressure':{'score':1},'overengineering_pressure':{'score':1},'complexity':{'score':1,'density':1.0}}}))\n",
                encoding="utf-8",
            )
            ledger = UsageLedger(run_id="run", provider="strictacode")

            def observer(phase: str, result: object) -> None:
                ledger.record(phase=phase, kind="tool", result=result, provider="strictacode")

            service = QualityService(
                root,
                QualityConfig(command=[sys.executable, str(script)], details_policy="never"),
                ContextConfig(cache_path=".agent/cache/context.db"),
                SecurityConfig(allowed_executables=[], denied_substrings=[]),
                observer=observer,
            )
            run_dir = root / ".agent/state/runs/run"
            run_dir.mkdir(parents=True)
            service.analyze(run_dir)
            self.assertEqual(len(ledger.events), 1)
            self.assertEqual(ledger.events[0].phase, "quality_before")
            self.assertEqual(ledger.events[0].kind, "tool")


if __name__ == "__main__":
    unittest.main()
