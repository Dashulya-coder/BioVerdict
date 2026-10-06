import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from bioverdict.connectors.clinicaltrials import (
    API_URL,
    FIELDS,
    ClinicalTrialsConnector,
    build_queries,
)
from bioverdict.connectors.http import CachedHttpClient
from bioverdict.contracts import Connector
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate
from bioverdict.store.models import Indication, ResolverOutput, Target

RAW = Path(__file__).parents[3] / "fixtures" / "raw" / "clinicaltrials"
DIVARASIB = (RAW / "search_divarasib.json").read_bytes()
TERMINATED = (RAW / "search_terminated.json").read_bytes()
TODAY = date(2026, 10, 7)


class FakeRegistry:
    """Answers search requests from the recorded responses and remembers what was asked."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        params = request.url.params
        body = TERMINATED if params.get("query.intr") == "sotorasib" else DIVARASIB
        return httpx.Response(200, content=body)


def make_connector(tmp_path: Path, registry: FakeRegistry) -> ClinicalTrialsConnector:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(registry))
    return ClinicalTrialsConnector(CachedHttpClient(client, HttpCache(conn), wait=wait_none()))


def asset_query(*assets: str) -> ResolverOutput:
    return ResolverOutput(
        indication=Indication(name="non-small cell lung cancer"),
        targets=[Target(symbol="KRAS")],
        known_assets=list(assets),
    )


def nct_ids(evidence: list) -> set[str]:
    return {e.locator.value for e in evidence if e.locator}


def test_satisfies_connector_protocol(tmp_path: Path) -> None:
    assert isinstance(make_connector(tmp_path, FakeRegistry()), Connector)


def test_asset_name_is_searched_as_intervention() -> None:
    [params] = build_queries(asset_query("divarasib"))
    assert params["query.intr"] == "divarasib"
    assert "query.cond" not in params
    assert params["fields"] == FIELDS and params["pageSize"] == "20"


def test_without_assets_the_indication_and_each_target_are_searched() -> None:
    query = ResolverOutput(
        indication=Indication(name="obesity"),
        targets=[Target(symbol="GLP1R"), Target(symbol="GIPR")],
    )
    queries = build_queries(query)
    assert [(q["query.cond"], q["query.term"]) for q in queries] == [
        ("obesity", "GLP1R"),
        ("obesity", "GIPR"),
    ]


async def test_fetch_returns_evidence_for_every_study_found(tmp_path: Path) -> None:
    registry = FakeRegistry()
    evidence = await make_connector(tmp_path, registry).fetch(asset_query("divarasib"), TODAY)

    expected = {
        s["protocolSection"]["identificationModule"]["nctId"]
        for s in json.loads(DIVARASIB)["studies"]
    }
    assert nct_ids(evidence) == expected
    assert registry.requests[0].url.params["query.intr"] == "divarasib"
    assert str(registry.requests[0].url).startswith(API_URL)


async def test_a_study_found_by_two_assets_is_read_once(tmp_path: Path) -> None:
    both = await make_connector(tmp_path, FakeRegistry()).fetch(
        asset_query("divarasib", "divarasib adipate"), TODAY
    )
    single = await make_connector(tmp_path, FakeRegistry()).fetch(asset_query("divarasib"), TODAY)
    assert len(both) == len(single)


async def test_results_of_several_assets_are_combined(tmp_path: Path) -> None:
    evidence = await make_connector(tmp_path, FakeRegistry()).fetch(
        asset_query("divarasib", "sotorasib"), TODAY
    )
    assert {"NCT04933695", "NCT04892017", "NCT04929223"} <= nct_ids(evidence)


async def test_as_of_hides_records_updated_after_the_cutoff(tmp_path: Path) -> None:
    connector = make_connector(tmp_path, FakeRegistry())
    now = await connector.fetch(asset_query("divarasib"), TODAY)
    earlier = await connector.fetch(asset_query("divarasib"), date(2021, 7, 1))

    assert all(e.published_at <= date(2021, 7, 1) for e in earlier if e.published_at)
    assert len(earlier) < len(now)
    assert not [e for e in earlier if e.id.endswith(":status")]  # updated years later


async def test_a_repeated_fetch_is_served_from_the_cache(tmp_path: Path) -> None:
    registry = FakeRegistry()
    connector = make_connector(tmp_path, registry)
    await connector.fetch(asset_query("divarasib"), TODAY)
    await connector.fetch(asset_query("divarasib"), TODAY)
    assert len(registry.requests) == 1


async def test_a_source_error_is_raised(tmp_path: Path) -> None:
    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    conn = connect(tmp_path / "t.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(failing))
    connector = ClinicalTrialsConnector(CachedHttpClient(client, HttpCache(conn), wait=wait_none()))
    with pytest.raises(httpx.HTTPStatusError):
        await connector.fetch(asset_query("divarasib"), TODAY)


async def test_retrieved_at_is_the_real_download_time(tmp_path: Path) -> None:
    connector = make_connector(tmp_path, FakeRegistry())
    first = await connector.fetch(asset_query("divarasib"), TODAY)
    second = await connector.fetch(asset_query("divarasib"), TODAY)

    assert {e.retrieved_at for e in first} == {e.retrieved_at for e in second}
    assert len({e.retrieved_at for e in first}) == 1
