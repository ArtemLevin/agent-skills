from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SCHEMA = """
CREATE TABLE IF NOT EXISTS context_entries (
    namespace TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_accessed_at REAL NOT NULL,
    expires_at REAL,
    PRIMARY KEY (namespace, cache_key)
);
CREATE INDEX IF NOT EXISTS idx_context_entries_updated_at
ON context_entries(updated_at);
CREATE INDEX IF NOT EXISTS idx_context_entries_expires_at
ON context_entries(expires_at);
"""


@dataclass(frozen=True)
class CacheEntry:
    namespace: str
    cache_key: str
    fingerprint: str
    payload: dict[str, Any]
    metadata: dict[str, Any]
    created_at: float
    updated_at: float
    last_accessed_at: float
    expires_at: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "cache_key": self.cache_key,
            "fingerprint": self.fingerprint,
            "payload": self.payload,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed_at": self.last_accessed_at,
            "expires_at": self.expires_at,
        }


class ContextCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    @staticmethod
    def _decode(row: sqlite3.Row) -> CacheEntry:
        return CacheEntry(
            namespace=str(row["namespace"]),
            cache_key=str(row["cache_key"]),
            fingerprint=str(row["fingerprint"]),
            payload=json.loads(str(row["payload_json"])),
            metadata=json.loads(str(row["metadata_json"])),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            last_accessed_at=float(row["last_accessed_at"]),
            expires_at=float(row["expires_at"]) if row["expires_at"] is not None else None,
        )

    def get(self, namespace: str, cache_key: str, *, fingerprint: str) -> CacheEntry | None:
        now = time.time()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM context_entries WHERE namespace = ? AND cache_key = ?",
                (namespace, cache_key),
            ).fetchone()
            if row is None:
                return None
            if str(row["fingerprint"]) != fingerprint:
                return None
            expires_at = row["expires_at"]
            if expires_at is not None and float(expires_at) <= now:
                return None
            connection.execute(
                "UPDATE context_entries SET last_accessed_at = ? WHERE namespace = ? AND cache_key = ?",
                (now, namespace, cache_key),
            )
            connection.commit()
            updated = dict(row)
            updated["last_accessed_at"] = now
            return CacheEntry(
                namespace=str(updated["namespace"]),
                cache_key=str(updated["cache_key"]),
                fingerprint=str(updated["fingerprint"]),
                payload=json.loads(str(updated["payload_json"])),
                metadata=json.loads(str(updated["metadata_json"])),
                created_at=float(updated["created_at"]),
                updated_at=float(updated["updated_at"]),
                last_accessed_at=float(updated["last_accessed_at"]),
                expires_at=float(updated["expires_at"])
                if updated["expires_at"] is not None
                else None,
            )

    def put(
        self,
        namespace: str,
        cache_key: str,
        *,
        fingerprint: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        ttl_seconds: int = 0,
    ) -> CacheEntry:
        now = time.time()
        expires_at = now + ttl_seconds if ttl_seconds > 0 else None
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO context_entries (
                    namespace, cache_key, fingerprint, payload_json, metadata_json,
                    created_at, updated_at, last_accessed_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, cache_key) DO UPDATE SET
                    fingerprint = excluded.fingerprint,
                    payload_json = excluded.payload_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at,
                    last_accessed_at = excluded.last_accessed_at,
                    expires_at = excluded.expires_at
                """,
                (
                    namespace,
                    cache_key,
                    fingerprint,
                    payload_json,
                    metadata_json,
                    now,
                    now,
                    now,
                    expires_at,
                ),
            )
            connection.commit()
        entry = self.get(namespace, cache_key, fingerprint=fingerprint)
        if entry is None:
            raise RuntimeError("Cache write could not be read back")
        return entry

    def stats(self) -> dict[str, Any]:
        now = time.time()
        with self._connect() as connection:
            total = int(connection.execute("SELECT COUNT(*) FROM context_entries").fetchone()[0])
            expired = int(
                connection.execute(
                    "SELECT COUNT(*) FROM context_entries "
                    "WHERE expires_at IS NOT NULL AND expires_at <= ?",
                    (now,),
                ).fetchone()[0]
            )
            rows = connection.execute(
                "SELECT namespace, COUNT(*) AS count FROM context_entries "
                "GROUP BY namespace ORDER BY namespace"
            ).fetchall()
        return {
            "path": str(self.path),
            "entries": total,
            "expired_entries": expired,
            "active_entries": total - expired,
            "namespaces": {str(row["namespace"]): int(row["count"]) for row in rows},
            "size_bytes": self.path.stat().st_size if self.path.exists() else 0,
        }

    def list_entries(
        self,
        *,
        namespace: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM context_entries"
        params: tuple[Any, ...] = ()
        if namespace:
            query += " WHERE namespace = ?"
            params = (namespace,)
        query += " ORDER BY last_accessed_at DESC LIMIT ?"
        params += (max(1, limit),)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._decode(row).to_dict() for row in rows]

    def prune(self, *, max_age_days: int = 30) -> dict[str, int]:
        now = time.time()
        cutoff = now - max(0, max_age_days) * 86400
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM context_entries
                WHERE (expires_at IS NOT NULL AND expires_at <= ?)
                   OR updated_at < ?
                """,
                (now, cutoff),
            )
            connection.commit()
            deleted = int(cursor.rowcount if cursor.rowcount is not None else 0)
        return {"deleted_entries": deleted, "max_age_days": max_age_days}

    def clear(self) -> dict[str, int]:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM context_entries")
            connection.commit()
            deleted = int(cursor.rowcount if cursor.rowcount is not None else 0)
        return {"deleted_entries": deleted}
