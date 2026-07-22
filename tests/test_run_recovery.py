from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.state import RunState


class RunRecoveryTests(unittest.TestCase):
    def test_incomplete_run_is_detected_and_read_only_run_can_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = RunState(root)
            state.checkpoint("plan", {"ready": True})
            self.assertEqual(len(RunState.incomplete_runs(root)), 1)
            resumed = RunState(root, run_id=state.run_id, resume=True)
            self.assertEqual(resumed.run_id, state.run_id)

    def test_incomplete_mutation_cannot_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = RunState(root)
            state.mark_mutation_started("implementation")
            self.assertEqual(
                RunState.incomplete_runs(root)[0]["status"],
                "manual_recovery_required",
            )
            with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                RunState(root, run_id=state.run_id, resume=True)

    def test_finish_updates_lifecycle_without_deleting_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = RunState(root)
            artifact = state.write_text("partial.diff", "user changes")
            RunState.finish_existing(
                root,
                state.run_id,
                status="failed",
                phase="implementation",
                message="needs inspection",
            )
            self.assertEqual(state.metadata()["status"], "failed")
            self.assertEqual(artifact.read_text(encoding="utf-8"), "user changes")


if __name__ == "__main__":
    unittest.main()
