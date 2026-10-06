"""HTTP response cache stored in the `http_cache` table.

Entries never expire: the same request always returns the same body, which keeps demo runs
reproducible and lets the cache be pre-warmed before the finals (docs/runbook.md).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
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


class HttpCache:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: str) -> bytes | None:
        row = self._conn.execute("SELECT body FROM http_cache WHERE key = ?", (key,)).fetchone()
        return None if row is None else row["body"]

    def put(self, key: str, url: str, body: bytes) -> None:
        fetched_at = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO http_cache (key, url, body, fetched_at) VALUES (?, ?, ?, ?)",
            (key, url, body, fetched_at),
        )
        self._conn.commit()
