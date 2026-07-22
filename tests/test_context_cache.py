from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentkit.context_cache import ContextCache


class ContextCacheTests(unittest.TestCase):
    def test_every_sqlite_connection_is_closed_after_use(self) -> None:
        real_connect = sqlite3.connect
        connections: list[sqlite3.Connection] = []

        def tracked_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
            connection = real_connect(*args, **kwargs)
            connections.append(connection)
            return connection

        with tempfile.TemporaryDirectory() as directory:
            with patch("agentkit.context_cache.sqlite3.connect", side_effect=tracked_connect):
                cache = ContextCache(Path(directory) / "context.db")
                cache.put("test", "key", fingerprint="fp", payload={"ok": True})
                cache.stats()

        self.assertTrue(connections)
        for connection in connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_roundtrip_requires_matching_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = ContextCache(Path(directory) / "cache.db")
            cache.put(
                "compiled_context",
                "task-key",
                fingerprint="a" * 64,
                payload={"value": 1},
                metadata={"phase": "implementation"},
                ttl_seconds=60,
            )
            hit = cache.get("compiled_context", "task-key", fingerprint="a" * 64)
            self.assertIsNotNone(hit)
            self.assertEqual(hit.payload, {"value": 1})
            self.assertIsNone(
                cache.get("compiled_context", "task-key", fingerprint="b" * 64)
            )
            self.assertEqual(cache.stats()["entries"], 1)

    def test_prune_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = ContextCache(Path(directory) / "cache.db")
            cache.put(
                "compiled_context",
                "old",
                fingerprint="a" * 64,
                payload={"value": 1},
            )
            pruned = cache.prune(max_age_days=0)
            self.assertEqual(pruned["deleted_entries"], 1)
            cache.put(
                "compiled_context",
                "new",
                fingerprint="a" * 64,
                payload={"value": 2},
            )
            self.assertEqual(cache.clear()["deleted_entries"], 1)

    def test_corrupt_database_is_quarantined_and_recreated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.db"
            path.write_bytes(b"not a sqlite database")
            cache = ContextCache(path)
            self.assertIn("quarantined", cache.recovery_warning)
            self.assertEqual(cache.stats()["entries"], 0)
            quarantined = list((path.parent / "quarantine").rglob("cache.db"))
            self.assertEqual(len(quarantined), 1)
            self.assertEqual(quarantined[0].read_bytes(), b"not a sqlite database")


if __name__ == "__main__":
    unittest.main()
