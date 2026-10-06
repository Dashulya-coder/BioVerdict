"""HTTP client for connectors: every response goes through the cache.

Transient failures are retried (see retry.py). Errors that remain are raised and never cached,
because a failed fetch proves nothing about the source (section status `error`,
docs/data-model.md).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt
from tenacity.wait import wait_base

from bioverdict.connectors.retry import MAX_ATTEMPTS, is_transient, wait_for_retry
from bioverdict.store.http_cache import HttpCache, cache_key


class CachedHttpClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        cache: HttpCache,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        wait: wait_base | Callable = wait_for_retry,
    ) -> None:
        self._client = client
        self._cache = cache
        self._max_attempts = max_attempts
        self._wait = wait

    async def get(self, url: str, params: dict[str, str] | None = None) -> bytes:
        key = cache_key("GET", url, params)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        response = await self._send(lambda: self._client.get(url, params=params))
        return self._store(key, url, response)

    async def post_json(self, url: str, payload: dict) -> bytes:
        # Sorted keys make the body, and therefore the cache key, deterministic.
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        key = cache_key("POST", url, body=body)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        response = await self._send(
            lambda: self._client.post(
                url, content=body, headers={"Content-Type": "application/json"}
            )
        )
        return self._store(key, url, response)

    async def _send(self, request: Callable[[], Awaitable[httpx.Response]]) -> httpx.Response:
        """Send with retries on transient failures; raise the last error if they run out."""

        async def attempt() -> httpx.Response:
            response = await request()
            response.raise_for_status()
            return response

        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=self._wait,
            retry=retry_if_exception(is_transient),
            reraise=True,
        )
        return await retrying(attempt)

    def _store(self, key: str, url: str, response: httpx.Response) -> bytes:
        self._cache.put(key, url, response.content)
        return response.content
