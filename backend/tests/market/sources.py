"""Replays the recorded answers of the market sources (scripts/record_market_fixtures.py)."""

import json
from pathlib import Path

import httpx
from tenacity import wait_none

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate

RAW = Path(__file__).parents[3] / "fixtures" / "raw" / "market"
HAE = "MONDO_0019623"  # the disease whose cross-references were recorded


def raw(name: str) -> bytes:
    return (RAW / name).read_bytes()


class Sources:
    """Answers each source from its recording; `down` names hosts that answer 503."""

    def __init__(self, *down: str) -> None:
        self.down = down
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        host, path, params = request.url.host, request.url.path, request.url.params
        if any(name in host for name in self.down):
            return httpx.Response(503)
        if "opentargets" in host:
            payload = json.loads(request.content)
            if "drugAndClinicalCandidates" in payload["query"]:
                return httpx.Response(200, content=raw("opentargets_analogs_kras.json"))
            if payload["variables"]["id"] == HAE:
                return httpx.Response(200, content=raw("opentargets_xrefs_hae.json"))
            # Any other disease: known to the database, with no Orphanet cross-reference.
            return httpx.Response(200, json={"data": {"disease": {"id": "x", "dbXRefs": []}}})
        if "cms.gov" in host:
            program = "d" if "7e0b4365" in path else "b"
            drug = params["keyword"].lower()
            return httpx.Response(200, content=raw(f"cms_{program}_{drug}.json"))
        if "cdc.gov" in host:
            return httpx.Response(200, content=raw("cdc_obesity.json"))
        if "worldbank" in host:
            return httpx.Response(200, content=raw(f"worldbank_{path.rsplit('/', 1)[1]}.json"))
        if "statecancerprofiles" in host:
            return httpx.Response(200, content=raw("cancer_lung.csv"))
        if "orphadata" in host:
            return httpx.Response(200, content=raw("orphanet_prevalence.xml"))
        raise AssertionError(f"unexpected request: {request.url}")

    def hosts(self) -> set[str]:
        return {request.url.host for request in self.asked}


def make_http(directory: Path, server: Sources) -> CachedHttpClient:
    directory.mkdir(parents=True, exist_ok=True)
    conn = connect(directory / "sources.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(server))
    return CachedHttpClient(client, HttpCache(conn), wait=wait_none())
