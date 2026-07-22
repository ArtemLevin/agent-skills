from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agentkit.config import load_config, write_default_config
from agentkit.graphify import GraphContext
from agentkit.models import RunMode, TriageResult
from agentkit.quality.integration import QualityAwareRunner
from agentkit.quality.routing_config import ensure_quality_routing_config
from agentkit.quality.routing_integration import RoutingAwareRunner
from agentkit.runner import RunRequest


class QualityRoutingIntegrationTests(unittest.TestCase):
    def test_task_packet_refines_same_triage_and_writes_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_default_config(root)
            ensure_quality_routing_config(root)
            run_dir = root / ".agent/state/runs/run-1"
            run_dir.mkdir(parents=True)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "src/service.py").write_text(
                "def process():\n    return 1\n", encoding="utf-8"
            )
            snapshot = {
                "availability": "available",
                "source_fingerprint": "abc",
                "hotspots": [
                    {
                        "kind": "function",
                        "file": "src/service.py",
                        "name": "process",
                        "complexity": 45,
                        "refactoring_pressure": 80,
                        "overengineering_pressure": 80,
                        "rank_score": 0.9,
                        "reasons": [],
                    }
                ],
                "warnings": [],
                "truncated": False,
            }
            snapshot_path = run_dir / "quality-before.json"
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            (run_dir / "graph.json").write_text(
                json.dumps({"output": "src/service.py process centrality"}),
                encoding="utf-8",
            )
            runner = RoutingAwareRunner(root, config=load_config(root))
            runner._quality_runtime = (
                SimpleNamespace(run_id="run-1", directory=run_dir),
                lambda phase, result: None,
                None,
                None,
            )
            runner._quality_baseline = SimpleNamespace(
                result=SimpleNamespace(
                    artifacts=SimpleNamespace(snapshot_path=snapshot_path)
                )
            )
            triage = TriageResult(
                RunMode.STANDARD,
                ["base"],
                ["task-triage", "verification-router"],
            )
            base_packet = {
                "task": "fix service process",
                "mode": "standard",
                "risk_reasons": ["base"],
                "selected_skills": list(triage.selected_skills),
            }
            with patch.object(
                QualityAwareRunner,
                "_task_packet",
                return_value=base_packet,
            ):
                packet = runner._task_packet(
                    RunRequest(task="fix service process"),
                    triage,
                    GraphContext(True, True, "", "src/service.py process centrality"),
                    "head",
                )
            self.assertEqual(triage.mode, RunMode.DEEP)
            self.assertEqual(packet["mode"], "deep")
            self.assertTrue(packet["quality_route"]["approval_required"])
            self.assertTrue((run_dir / "quality-route.json").is_file())
            self.assertTrue((run_dir / "verification-plan.json").is_file())
            self.assertTrue(runner.config.verification.commands)


if __name__ == "__main__":
    unittest.main()
