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


class FakeTime:
    """A clock the test moves by sleeping, so pacing is checked without waiting."""

    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def paced_client(tmp_path: Path, time_: FakeTime, interval: float = 1.0) -> CachedHttpClient:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    http = httpx.AsyncClient(transport=httpx.MockTransport(Server()))
    return CachedHttpClient(
        http,
        HttpCache(conn),
        min_interval_s=interval,
        clock=time_.clock,
        sleep=time_.sleep,
    )


async def test_network_calls_to_one_host_are_spaced(tmp_path: Path) -> None:
    time_ = FakeTime()
    client = paced_client(tmp_path, time_)

    await client.get("https://example.org/a")
    await client.get("https://example.org/b")
    await client.get("https://example.org/c")

    assert time_.sleeps == [pytest.approx(1.0), pytest.approx(1.0)]  # none before the first


async def test_calls_to_different_hosts_do_not_wait_for_each_other(tmp_path: Path) -> None:
    time_ = FakeTime()
    client = paced_client(tmp_path, time_)

    await client.get("https://one.example.org/a")
    await client.get("https://two.example.org/a")

    assert time_.sleeps == []


async def test_a_cache_hit_is_never_delayed(tmp_path: Path) -> None:
    time_ = FakeTime()
    client = paced_client(tmp_path, time_)
    await client.get("https://example.org/a")

    await client.get("https://example.org/a")  # served from the cache

    assert time_.sleeps == []


async def test_no_wait_when_enough_time_has_passed_anyway(tmp_path: Path) -> None:
    time_ = FakeTime()
    client = paced_client(tmp_path, time_)
    await client.get("https://example.org/a")
    time_.now += 5.0

    await client.get("https://example.org/b")

    assert time_.sleeps == []


async def test_pacing_is_off_by_default(tmp_path: Path) -> None:
    time_ = FakeTime()
    client = paced_client(tmp_path, time_, interval=0.0)

    await client.get("https://example.org/a")
    await client.get("https://example.org/b")

    assert time_.sleeps == []


class Rejected(Exception):
    pass


def reject_errors(body: bytes) -> None:
    if body.startswith(b"error"):
        raise Rejected(body.decode())


async def test_a_body_rejected_by_the_validator_is_not_cached(tmp_path: Path) -> None:
    class Flaky(Server):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            body = b"error: bad query" if len(self.requests) == 1 else b"fine"
            return httpx.Response(200, content=body)

    server = Flaky()
    client = make_client(tmp_path, server)

    with pytest.raises(Rejected):
        await client.post_json(URL, {"q": 1}, validate=reject_errors)
    second = await client.post_json(URL, {"q": 1}, validate=reject_errors)

    assert second.body == b"fine"  # the failed answer was not served from the cache
    assert len(server.requests) == 2


async def test_validator_is_not_applied_again_to_a_cached_body(tmp_path: Path) -> None:
    calls: list[bytes] = []

    def spy(body: bytes) -> None:
        calls.append(body)

    client = make_client(tmp_path, Server())
    await client.get(URL, validate=spy)
    await client.get(URL, validate=spy)
    assert len(calls) == 1


def aged_client(tmp_path: Path, server: Server, max_age_s: float | None) -> CachedHttpClient:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    http = httpx.AsyncClient(transport=httpx.MockTransport(server))
    return CachedHttpClient(http, HttpCache(conn), wait=wait_none(), max_age_s=max_age_s)


async def test_without_a_maximum_age_a_cached_answer_never_expires(tmp_path: Path) -> None:
    server = Server()
    await aged_client(tmp_path, server, None).get(URL)

    await aged_client(tmp_path, server, None).get(URL)

    assert len(server.requests) == 1


async def test_an_answer_older_than_the_maximum_age_is_fetched_again_and_replaced(
    tmp_path: Path,
) -> None:
    server = Server()
    first = await aged_client(tmp_path, server, None).get(URL)

    refreshed = await aged_client(tmp_path, server, 0).get(URL)  # 0: refresh everything
    kept = await aged_client(tmp_path, server, 3600).get(URL)  # young enough: reused

    assert len(server.requests) == 2
    assert refreshed.fetched_at > first.fetched_at and kept.fetched_at == refreshed.fetched_at


async def test_a_refresh_that_fails_does_not_fall_back_to_the_stale_answer(tmp_path: Path) -> None:
    server = Server()
    await aged_client(tmp_path, server, None).get(URL)
    failing = Server(404)

    with pytest.raises(httpx.HTTPStatusError):
        await aged_client(tmp_path, failing, 0).get(URL)
