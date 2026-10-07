"""Replay of real Open Targets answers recorded by scripts/record_resolver_fixtures.py."""

import hashlib
import json
from pathlib import Path

import httpx

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.opentargets import OpenTargetsApi
from bioverdict.resolver.lookup import OpenTargetsLookup
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate

RECORDING = (
    Path(__file__).parents[3] / "fixtures" / "raw" / "opentargets" / "resolver_recording.json"
)


def payload_key(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def replay(request: httpx.Request) -> httpx.Response:
    recorded = json.loads(RECORDING.read_text(encoding="utf-8"))
    payload = json.loads(request.content)
    entry = recorded.get(payload_key(payload))
    assert entry is not None, (
        f"request not recorded: {payload['variables']}. Re-run "
        "'uv run python ../scripts/record_resolver_fixtures.py' (add the case to its lists)."
    )
    return httpx.Response(200, json=entry["answer"])


def make_lookup(directory: Path) -> OpenTargetsLookup:
    conn = connect(directory / "t.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(replay))
    return OpenTargetsLookup(OpenTargetsApi(CachedHttpClient(client, HttpCache(conn))))
