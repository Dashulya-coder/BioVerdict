from pathlib import Path

import pytest

from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache, cache_key
from bioverdict.store.migrations import migrate

URL = "https://clinicaltrials.gov/api/v2/studies"


@pytest.fixture
def cache(tmp_path: Path) -> HttpCache:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    return HttpCache(conn)


def test_key_ignores_parameter_order() -> None:
    a = cache_key("GET", URL, {"query.intr": "divarasib", "pageSize": "50"})
    b = cache_key("GET", URL, {"pageSize": "50", "query.intr": "divarasib"})
    assert a == b


def test_key_treats_url_query_and_params_alike() -> None:
    inline = cache_key("GET", f"{URL}?pageSize=50")
    merged = cache_key("GET", URL, {"pageSize": "50"})
    assert inline == merged


def test_key_differs_by_method_params_and_body() -> None:
    base = cache_key("GET", URL, {"q": "a"})
    assert cache_key("POST", URL, {"q": "a"}) != base
    assert cache_key("GET", URL, {"q": "b"}) != base
    assert cache_key("POST", URL, body=b"1") != cache_key("POST", URL, body=b"2")


def test_miss_returns_none(cache: HttpCache) -> None:
    assert cache.get("missing") is None


def test_put_then_get_round_trips_bytes(cache: HttpCache) -> None:
    cache.put("k", URL, b'{"ok": true}')
    assert cache.get("k") == b'{"ok": true}'


def test_put_replaces_existing_entry(cache: HttpCache) -> None:
    cache.put("k", URL, b"old")
    cache.put("k", URL, b"new")
    assert cache.get("k") == b"new"
