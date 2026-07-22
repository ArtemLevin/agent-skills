from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentkit.config import ContextConfig
from agentkit.quality.hotspot_context import HotspotContextCompiler


class HotspotContextTests(unittest.TestCase):
    def _root(self, directory: str) -> Path:
        root = Path(directory)
        (root / ".agent/state/runs/run-1").mkdir(parents=True)
        (root / ".agent/state/quality-latest").write_text("run-1", encoding="utf-8")
        (root / "src").mkdir()
        (root / "src/recorder.py").write_text("def write_session():\n    return 1\n", encoding="utf-8")
        (root / "src/unrelated.py").write_text("def huge_parser():\n    return 2\n", encoding="utf-8")
        payload = {
            "availability": "available",
            "provider": "strictacode",
            "provider_version": "x",
            "source_fingerprint": "abc",
            "hotspots": [
                {"kind": "function", "name": "write_session", "file": "src/recorder.py", "status": "warning", "complexity": 10, "rank_score": 0.4, "reasons": []},
                {"kind": "function", "name": "huge_parser", "file": "src/unrelated.py", "status": "emergency", "complexity": 90, "rank_score": 1.0, "reasons": []},
            ],
            "warnings": [],
            "truncated": False,
        }
        (root / ".agent/state/runs/run-1/quality-before.json").write_text(json.dumps(payload), encoding="utf-8")
        return root

    def test_task_relevance_beats_unrelated_severity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            result = HotspotContextCompiler(root, ContextConfig(cache_enabled=False)).compile(task="fix recorder write session", limit=1)
            self.assertEqual(result.candidates[0].file, "src/recorder.py")
            self.assertEqual(result.candidates[0].line_start, 1)

    def test_graph_evidence_contributes_component(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            (root / "graphify-out").mkdir()
            (root / "graphify-out/graph.json").write_text('{"node":"src/recorder.py write_session"}', encoding="utf-8")
            result = HotspotContextCompiler(root, ContextConfig(cache_enabled=False)).compile(task="session persistence")
            candidate = next(item for item in result.candidates if item.file == "src/recorder.py")
            self.assertGreater(candidate.graph_score, 0)
            self.assertTrue(result.graph_available)

    def test_cache_invalidates_when_candidate_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            config = ContextConfig(cache_enabled=True, cache_path=".agent/cache/context.db")
            compiler = HotspotContextCompiler(root, config)
            first = compiler.compile(task="fix recorder")
            second = compiler.compile(task="fix recorder")
            self.assertFalse(first.cache_hit)
            self.assertTrue(second.cache_hit)
            (root / "src/recorder.py").write_text("def write_session():\n    return 3\n", encoding="utf-8")
            third = compiler.compile(task="fix recorder")
            self.assertFalse(third.cache_hit)


if __name__ == "__main__":
    unittest.main()
