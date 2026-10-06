"""HTTP client for connectors: every response goes through the cache.

Errors are raised and never cached, because a failed fetch proves nothing about the source
(section status `error`, docs/data-model.md).
"""

from __future__ import annotations

import json

import httpx

from bioverdict.store.http_cache import HttpCache, cache_key


class CachedHttpClient:
    def __init__(self, client: httpx.AsyncClient, cache: HttpCache) -> None:
        self._client = client
        self._cache = cache

    async def get(self, url: str, params: dict[str, str] | None = None) -> bytes:
        key = cache_key("GET", url, params)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        response = await self._client.get(url, params=params)
        return self._store(key, url, response)

    async def post_json(self, url: str, payload: dict) -> bytes:
        # Sorted keys make the body, and therefore the cache key, deterministic.
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        key = cache_key("POST", url, body=body)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        response = await self._client.post(
            url, content=body, headers={"Content-Type": "application/json"}
        )
        return self._store(key, url, response)

    def _store(self, key: str, url: str, response: httpx.Response) -> bytes:
        response.raise_for_status()
        self._cache.put(key, url, response.content)
        return response.content
