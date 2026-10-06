import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.opentargets import API_URL, OpenTargetsConnector, OpenTargetsError
from bioverdict.contracts import Connector
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate
from bioverdict.store.models import Asset, EvidenceLevel, Indication, ResolverOutput, Target

RAW = Path(__file__).parents[3] / "fixtures" / "raw"
TODAY = date(2026, 10, 7)


def answer(path: str) -> bytes:
    return (RAW / path).read_bytes()


class FakeOpenTargets:
    """Answers GraphQL requests from recorded responses and remembers what was asked."""

    def __init__(self, fail_first: bool = False) -> None:
        self.payloads: list[dict] = []
        self._fail_first = fail_first

    def __call__(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        self.payloads.append(payload)
        if self._fail_first and len(self.payloads) == 1:
            return httpx.Response(200, content=b'{"errors":[{"message":"boom"}]}')
        text, variables = payload["query"], payload["variables"]
        if "search(" in text:
            known = variables["name"].casefold() in ("divarasib", "divarasib adipate")
            return httpx.Response(
                200,
                content=answer(
                    "opentargets/search_divarasib.json" if known else "opentargets/search_none.json"
                ),
            )
        if "drug(" in text:
            return httpx.Response(200, content=answer("divarasib/opentargets_drug.json"))
        return httpx.Response(200, content=answer("divarasib/opentargets_assoc.json"))

    def asked(self, fragment: str) -> int:
        return sum(fragment in p["query"] for p in self.payloads)


def make_connector(tmp_path: Path, server: FakeOpenTargets) -> OpenTargetsConnector:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(server))
    return OpenTargetsConnector(CachedHttpClient(client, HttpCache(conn), wait=wait_none()))


def query(
    assets: list[str] | None = None,
    ensembl: str | None = "ENSG00000133703",
    mondo: str | None = "MONDO_0005233",
) -> ResolverOutput:
    return ResolverOutput(
        indication=Indication(name="NSCLC", mondo_id=mondo),
        targets=[Target(symbol="KRAS", ensembl=ensembl)],
        known_assets=assets or [],
    )


def test_satisfies_connector_protocol(tmp_path: Path) -> None:
    assert isinstance(make_connector(tmp_path, FakeOpenTargets()), Connector)


async def test_asset_and_target_give_a_drug_record_and_association_records(tmp_path: Path) -> None:
    evidence = await make_connector(tmp_path, FakeOpenTargets()).fetch(query(["divarasib"]), TODAY)

    levels = sorted(e.level.value for e in evidence)
    assert levels == sorted(
        ["registry_record", "registry_record", "human_observational", "animal_in_vivo", "in_vitro"]
    )
    assert {e.source for e in evidence} == {"Open Targets"}


async def test_the_drug_is_looked_up_by_the_id_of_the_exact_name(tmp_path: Path) -> None:
    server = FakeOpenTargets()
    await make_connector(tmp_path, server).fetch(query(["divarasib"]), TODAY)

    drug_calls = [p for p in server.payloads if "drug(" in p["query"]]
    assert [p["variables"]["id"] for p in drug_calls] == ["CHEMBL5095236"]


async def test_an_unknown_asset_is_skipped_without_a_drug_lookup(tmp_path: Path) -> None:
    server = FakeOpenTargets()
    evidence = await make_connector(tmp_path, server).fetch(
        query(["notadrug"], ensembl=None), TODAY
    )

    assert evidence == [] and server.asked("drug(") == 0


async def test_without_ids_from_the_resolver_the_association_is_not_fetched(tmp_path: Path) -> None:
    server = FakeOpenTargets()
    connector = make_connector(tmp_path, server)

    assert await connector.fetch(query(ensembl=None), TODAY) == []
    assert await connector.fetch(query(mondo=None), TODAY) == []
    assert server.asked("associatedTargets") == 0


async def test_a_snapshot_is_invisible_to_a_run_dated_before_it_was_downloaded(
    tmp_path: Path,
) -> None:
    connector = make_connector(tmp_path, FakeOpenTargets())
    assert await connector.fetch(query(["divarasib"]), date(2020, 1, 1)) == []


async def test_a_repeated_fetch_is_served_from_the_cache(tmp_path: Path) -> None:
    server = FakeOpenTargets()
    connector = make_connector(tmp_path, server)
    await connector.fetch(query(["divarasib"]), TODAY)
    asked = len(server.payloads)
    await connector.fetch(query(["divarasib"]), TODAY)
    assert len(server.payloads) == asked


async def test_graphql_errors_are_raised_and_not_cached(tmp_path: Path) -> None:
    server = FakeOpenTargets(fail_first=True)
    connector = make_connector(tmp_path, server)

    with pytest.raises(OpenTargetsError, match="boom"):
        await connector.fetch(query(["divarasib"]), TODAY)
    evidence = await connector.fetch(query(["divarasib"]), TODAY)

    assert any(e.level is EvidenceLevel.REGISTRY_RECORD for e in evidence)
    assert server.payloads[0]["query"] == server.payloads[1]["query"]  # the retry reached the API
    assert str(API_URL).startswith("https://api.platform.opentargets.org")


async def test_an_asset_with_a_confirmed_id_is_read_without_searching_by_name(
    tmp_path: Path,
) -> None:
    server = FakeOpenTargets()
    resolved = ResolverOutput(
        indication=Indication(name="NSCLC", mondo_id="MONDO_0005233"),
        targets=[Target(symbol="KRAS")],
        known_assets=["HRO761"],  # a name Open Targets does not list
        assets=[Asset(name="DIVARASIB", chembl_id="CHEMBL5095236")],
    )

    evidence = await make_connector(tmp_path, server).fetch(resolved, TODAY)

    assert server.asked("search(") == 0
    assert [p["variables"]["id"] for p in server.payloads if "drug(" in p["query"]] == [
        "CHEMBL5095236"
    ]
    assert any(e.level is EvidenceLevel.REGISTRY_RECORD for e in evidence)


async def test_an_unconfirmed_asset_is_not_looked_up_by_name_behind_the_resolvers_back(
    tmp_path: Path,
) -> None:
    server = FakeOpenTargets()
    resolved = ResolverOutput(
        indication=Indication(name="NSCLC"),
        targets=[Target(symbol="KRAS")],
        known_assets=["divarasib"],
        assets=[Asset(name="divarasib", chembl_id=None)],  # the Resolver could not confirm it
    )

    assert await make_connector(tmp_path, server).fetch(resolved, TODAY) == []
    assert server.asked("search(") == 0
