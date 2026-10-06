from pathlib import Path

import httpx
import pytest

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate

URL = "https://example.org/api"


class Server:
    """Counts requests and answers with the queued status codes (200 when the queue is empty)."""

    def __init__(self, *statuses: int) -> None:
        self.requests: list[httpx.Request] = []
        self._statuses = list(statuses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status = self._statuses.pop(0) if self._statuses else 200
        return httpx.Response(status, content=f"body-{len(self.requests)}".encode())


def make_client(tmp_path: Path, server: Server) -> CachedHttpClient:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    transport = httpx.MockTransport(server)
    return CachedHttpClient(httpx.AsyncClient(transport=transport), HttpCache(conn))


async def test_second_get_is_served_from_cache(tmp_path: Path) -> None:
    server = Server()
    client = make_client(tmp_path, server)

    first = await client.get(URL, {"q": "a"})
    second = await client.get(URL, {"q": "a"})

    assert first == second == b"body-1"
    assert len(server.requests) == 1


async def test_different_params_are_fetched_separately(tmp_path: Path) -> None:
    server = Server()
    client = make_client(tmp_path, server)

    await client.get(URL, {"q": "a"})
    await client.get(URL, {"q": "b"})

    assert len(server.requests) == 2


async def test_error_is_raised_and_not_cached(tmp_path: Path) -> None:
    server = Server(500)
    client = make_client(tmp_path, server)

    with pytest.raises(httpx.HTTPStatusError):
        await client.get(URL)
    assert await client.get(URL) == b"body-2"  # the retry reaches the server
    assert await client.get(URL) == b"body-2"  # and is now cached
    assert len(server.requests) == 2


async def test_post_json_is_cached_by_payload_not_key_order(tmp_path: Path) -> None:
    server = Server()
    client = make_client(tmp_path, server)

    await client.post_json(URL, {"query": "x", "variables": {"a": 1}})
    await client.post_json(URL, {"variables": {"a": 1}, "query": "x"})
    await client.post_json(URL, {"query": "y"})

    assert len(server.requests) == 2
    assert server.requests[0].headers["content-type"] == "application/json"
