from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate

URL = "https://example.org/api"


class Server:
    """Counts requests and plays back queued outcomes, then answers 200.

    An outcome is a status code, or an exception to raise (a network failure).
    """

    def __init__(self, *outcomes: int | Exception) -> None:
        self.requests: list[httpx.Request] = []
        self._outcomes = list(outcomes)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        outcome = self._outcomes.pop(0) if self._outcomes else 200
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome, content=f"body-{len(self.requests)}".encode())


def make_client(tmp_path: Path, server: Server) -> CachedHttpClient:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    transport = httpx.MockTransport(server)
    http = httpx.AsyncClient(transport=transport)
    return CachedHttpClient(http, HttpCache(conn), wait=wait_none())


async def test_second_get_is_served_from_cache(tmp_path: Path) -> None:
    server = Server()
    client = make_client(tmp_path, server)

    first = await client.get(URL, {"q": "a"})
    second = await client.get(URL, {"q": "a"})

    assert first.body == second.body == b"body-1"
    assert len(server.requests) == 1


async def test_different_params_are_fetched_separately(tmp_path: Path) -> None:
    server = Server()
    client = make_client(tmp_path, server)

    await client.get(URL, {"q": "a"})
    await client.get(URL, {"q": "b"})

    assert len(server.requests) == 2


async def test_client_error_is_raised_once_and_not_cached(tmp_path: Path) -> None:
    server = Server(404)
    client = make_client(tmp_path, server)

    with pytest.raises(httpx.HTTPStatusError):
        await client.get(URL)
    assert (await client.get(URL)).body == b"body-2"  # the retry reaches the server
    assert (await client.get(URL)).body == b"body-2"  # and is now cached
    assert len(server.requests) == 2


async def test_post_json_is_cached_by_payload_not_key_order(tmp_path: Path) -> None:
    server = Server()
    client = make_client(tmp_path, server)

    await client.post_json(URL, {"query": "x", "variables": {"a": 1}})
    await client.post_json(URL, {"variables": {"a": 1}, "query": "x"})
    await client.post_json(URL, {"query": "y"})

    assert len(server.requests) == 2
    assert server.requests[0].headers["content-type"] == "application/json"


async def test_server_error_is_retried_until_it_succeeds(tmp_path: Path) -> None:
    server = Server(503, 502)
    client = make_client(tmp_path, server)

    assert (await client.get(URL)).body == b"body-3"
    assert len(server.requests) == 3
    assert (await client.get(URL)).body == b"body-3"  # cached after the success
    assert len(server.requests) == 3


async def test_rate_limit_is_retried(tmp_path: Path) -> None:
    server = Server(429)
    client = make_client(tmp_path, server)

    assert (await client.get(URL)).body == b"body-2"


async def test_network_failure_is_retried(tmp_path: Path) -> None:
    server = Server(httpx.ConnectError("boom"))
    client = make_client(tmp_path, server)

    assert (await client.get(URL)).body == b"body-2"


async def test_gives_up_after_max_attempts_and_caches_nothing(tmp_path: Path) -> None:
    server = Server(500, 500, 500)
    client = make_client(tmp_path, server)

    with pytest.raises(httpx.HTTPStatusError):
        await client.get(URL)
    assert len(server.requests) == 3  # MAX_ATTEMPTS

    assert (await client.get(URL)).body == b"body-4"  # nothing was cached by the failure


async def test_a_cached_answer_keeps_its_original_download_time(tmp_path: Path) -> None:
    server = Server()
    client = make_client(tmp_path, server)

    first = await client.get(URL)
    second = await client.get(URL)

    assert second.fetched_at == first.fetched_at  # not the time it was read back
    assert len(server.requests) == 1
