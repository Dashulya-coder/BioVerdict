"""HTTP client for connectors: every response goes through the cache.

Transient failures are retried (see retry.py). Errors that remain are raised and never cached,
because a failed fetch proves nothing about the source (section status `error`,
docs/data-model.md).

Network calls to one host are spaced by `min_interval_s`, so a burst of requests (a search, then
the results of ten studies) does not trip a source's rate limit and get answered with 429. Cache
hits are never delayed.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt
from tenacity.wait import wait_base

from bioverdict.connectors.retry import MAX_ATTEMPTS, is_transient, wait_for_retry
from bioverdict.store.http_cache import HttpCache, cache_key

# What a run should use (a few requests a second is well inside what public sources accept);
# the class default is 0 so that tests do not wait.
DEFAULT_MIN_INTERVAL_S = 0.4


@dataclass(frozen=True)
class HttpResponse:
    body: bytes
    fetched_at: datetime  # real download time, also for answers served from the cache


class CachedHttpClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        cache: HttpCache,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        wait: wait_base | Callable = wait_for_retry,
        min_interval_s: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._cache = cache
        self._max_attempts = max_attempts
        self._wait = wait
        self._min_interval_s = min_interval_s
        self._clock = clock
        self._sleep = sleep
        self._last_call: dict[str, float] = {}
        self._host_locks: dict[str, asyncio.Lock] = {}

    async def get(self, url: str, params: dict[str, str] | None = None) -> HttpResponse:
        key = cache_key("GET", url, params)
        cached = self._cache.get_entry(key)
        if cached is not None:
            return HttpResponse(cached.body, cached.fetched_at)

        response = await self._send(url, lambda: self._client.get(url, params=params))
        return self._store(key, url, response)

    async def post_json(self, url: str, payload: dict) -> HttpResponse:
        # Sorted keys make the body, and therefore the cache key, deterministic.
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        key = cache_key("POST", url, body=body)
        cached = self._cache.get_entry(key)
        if cached is not None:
            return HttpResponse(cached.body, cached.fetched_at)

        response = await self._send(
            url,
            lambda: self._client.post(
                url, content=body, headers={"Content-Type": "application/json"}
            ),
        )
        return self._store(key, url, response)

    async def _pace(self, url: str) -> None:
        """Wait until `min_interval_s` has passed since the last network call to this host."""
        if self._min_interval_s <= 0:
            return
        host = httpx.URL(url).host
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with lock:  # concurrent callers queue up instead of all firing at once
            due = self._last_call.get(host, float("-inf")) + self._min_interval_s
            if due > self._clock():
                await self._sleep(due - self._clock())
            self._last_call[host] = self._clock()

    async def _send(
        self, url: str, request: Callable[[], Awaitable[httpx.Response]]
    ) -> httpx.Response:
        """Send with retries on transient failures; raise the last error if they run out."""

        async def attempt() -> httpx.Response:
            await self._pace(url)
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

    def _store(self, key: str, url: str, response: httpx.Response) -> HttpResponse:
        fetched_at = self._cache.put(key, url, response.content)
        return HttpResponse(response.content, fetched_at)
