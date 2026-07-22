from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentkit.config import write_default_config
from agentkit.evals.config import EvaluationConfig
from agentkit.evals.runner import EvaluationExecution, EvaluationHarness, tree_hash


class EvaluationRunnerTests(unittest.TestCase):
    def test_fixture_is_isolated_and_results_are_aggregated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "evals/fixture"
            fixture.mkdir(parents=True)
            (fixture / "retry.py").write_text("def retry():\n    return 1\n", encoding="utf-8")
            write_default_config(fixture)
            original = tree_hash(fixture)
            manifest = root / "task.json"
            manifest.write_text(
                json.dumps(
                    {
                        "id": "fixture-test-001",
                        "repository_fixture": "evals/fixture",
                        "mode": "standard",
                        "task": "add a regression test",
                        "acceptance": {
                            "commands": [["python", "-c", "from pathlib import Path; assert Path('tests/test_retry.py').is_file()"]],
                            "required_files": ["tests/test_retry.py"],
                            "forbidden_files": ["pyproject.toml"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            def fake(workspace: Path, _manifest: object) -> EvaluationExecution:
                (workspace / "tests").mkdir()
                (workspace / "tests/test_retry.py").write_text("pass\n", encoding="utf-8")
                run = workspace / ".agent/state/runs/fake"
                run.mkdir(parents=True)
                (run / "completion.json").write_text(
                    json.dumps({"status": "ready_for_review", "scope_passed": True, "blocking_findings": 0}),
                    encoding="utf-8",
                )
                (run / "usage.json").write_text(
                    json.dumps({"totals": {"agent_calls": 1, "measured_agent_calls": 1, "unknown_agent_calls": 0, "total_tokens": 50}}),
                    encoding="utf-8",
                )
                (run / "quality-diff.json").write_text(
                    json.dumps({"comparable": True, "metrics": {}, "new_hotspots": [], "resolved_hotspots": [], "persisting_hotspots": []}),
                    encoding="utf-8",
                )
                (run / "quality-gate.json").write_text(
                    json.dumps({"available": True, "allowed": True}), encoding="utf-8"
                )
                return EvaluationExecution("fake", 0, run)

            harness = EvaluationHarness(root, EvaluationConfig(), executor=fake)
            summary, output = harness.run_manifest(manifest, evaluation_id="fixture-eval")
            self.assertEqual(summary.passed_runs, 1)
            self.assertEqual(tree_hash(fixture), original)
            self.assertFalse((output / "runs/run-001/workspace").exists())
            self.assertTrue((output / "runs/run-001/agent-run/completion.json").is_file())


if __name__ == "__main__":
    unittest.main()
