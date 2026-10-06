"""HTTP response cache stored in the `http_cache` table.

Entries never expire: the same request always returns the same body, which keeps demo runs
reproducible and lets the cache be pre-warmed before the finals (docs/runbook.md).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx


def cache_key(
    method: str,
    url: str,
    params: dict[str, str] | None = None,
    body: bytes | None = None,
) -> str:
    """Stable key for a request: parameter order does not matter, method and body do."""
    full_url = httpx.URL(url).copy_merge_params(params or {})
    query = sorted(full_url.params.multi_items())
    base_url = str(full_url.copy_with(query=None))
    body_hash = hashlib.sha256(body).hexdigest() if body is not None else None

    payload = json.dumps([method.upper(), base_url, query, body_hash], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheEntry:
    body: bytes
    fetched_at: datetime  # when the body was really downloaded, not when it was read back


class HttpCache:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_entry(self, key: str) -> CacheEntry | None:
        row = self._conn.execute(
            "SELECT body, fetched_at FROM http_cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        return CacheEntry(row["body"], datetime.fromisoformat(row["fetched_at"]))

    def get(self, key: str) -> bytes | None:
        entry = self.get_entry(key)
        return None if entry is None else entry.body

    def put(self, key: str, url: str, body: bytes) -> datetime:
        """Store a response and return the time it was recorded as fetched."""
        fetched_at = datetime.now(UTC)
        self._conn.execute(
            "INSERT OR REPLACE INTO http_cache (key, url, body, fetched_at) VALUES (?, ?, ?, ?)",
            (key, url, body, fetched_at.isoformat()),
        )
        self._conn.commit()
        return fetched_at
