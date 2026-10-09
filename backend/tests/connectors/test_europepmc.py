"""The Europe PMC preprint connector on a recorded real answer."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from bioverdict.connectors.europepmc import (
    EuropePmcConnector,
    EuropePmcError,
    build_queries,
    parse_preprints,
    plain,
    require_results,
)
from bioverdict.connectors.http import CachedHttpClient
from bioverdict.contracts import Connector
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate
from bioverdict.store.models import (
    EvidenceLevel,
    Indication,
    ResolverOutput,
    SourceKind,
    Target,
)

RECORDED = Path(__file__).parents[3] / "fixtures" / "raw" / "europepmc" / "preprints_divarasib.json"
NOW = datetime(2026, 10, 9, tzinfo=UTC)
AS_OF = date(2026, 10, 9)
EMPTY = {"hitCount": 0, "resultList": {"result": []}}


def recorded() -> dict:
    return json.loads(RECORDED.read_text(encoding="utf-8"))


def query(assets: list[str], indication: str = "NSCLC") -> ResolverOutput:
    return ResolverOutput(
        indication=Indication(name=indication), targets=[Target(symbol="KRAS")], known_assets=assets
    )


class Server:
    def __init__(self, *answers: dict | bytes) -> None:
        self.answers = list(answers)
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        answer = self.answers.pop(0) if self.answers else recorded()
        if isinstance(answer, bytes):
            return httpx.Response(200, content=answer)
        return httpx.Response(200, json=answer)


def connector(tmp_path: Path, server: Server) -> EuropePmcConnector:
    conn = connect(tmp_path / "epmc.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(server))
    return EuropePmcConnector(CachedHttpClient(client, HttpCache(conn), wait=wait_none()))


def test_it_is_a_connector(tmp_path: Path) -> None:
    assert isinstance(connector(tmp_path, Server()), Connector)


def test_a_preprint_is_the_weakest_level_and_marked_as_a_preprint() -> None:
    evidence = parse_preprints(recorded(), NOW)

    assert len(evidence) == 2
    first = evidence[0]
    assert first.source_kind is SourceKind.PREPRINT and first.level is EvidenceLevel.IN_VITRO
    assert first.source == "Europe PMC preprint (bioRxiv)" and first.source_family == "preprint"
    assert first.published_at == date(2026, 8, 20)
    assert first.url == "https://doi.org/10.64898/2026.08.16.745134"
    assert first.locator is not None and first.locator.type == "doi"
    assert len({item.independence_group for item in evidence}) == 2


def test_the_excerpt_is_the_title_and_abstract_without_markup() -> None:
    first = parse_preprints(recorded(), NOW)[0]

    title, abstract = first.excerpt.split("\n", 1)
    assert (
        title
        == "The KRAS G12C Inhibitor Divarasib Stabilizes RBM39 and Antagonizes Aryl-Sulfonamide Degraders"
    )
    assert "<" not in first.excerpt and abstract.startswith("Summary KRAS G12C inhibitors")


def test_markup_and_entities_become_plain_text() -> None:
    assert (
        plain("<p>IC<sub>50</sub> &lt; 5&nbsp;nM</p>\n<h4>Results</h4>") == "IC 50 < 5 nM Results"
    )


@pytest.mark.parametrize(
    "change",
    [{"abstractText": ""}, {"firstPublicationDate": None}, {"source": "MED"}, {"id": ""}],
)
def test_a_record_that_cannot_be_quoted_or_dated_or_is_no_preprint_is_skipped(change) -> None:
    answer = recorded()
    answer["resultList"]["result"] = [answer["resultList"]["result"][0] | change]

    assert parse_preprints(answer, NOW) == []


def test_a_preprint_without_a_doi_points_at_its_record() -> None:
    answer = recorded()
    del answer["resultList"]["result"][0]["doi"]

    first = parse_preprints(answer, NOW)[0]

    assert first.url.startswith("https://europepmc.org/article/PPR/PPR")
    assert first.locator is not None and first.locator.type == "ppr"


def test_an_asset_is_searched_by_every_name_among_preprints_only() -> None:
    names = 'TITLE:"divarasib" OR ABSTRACT:"divarasib" OR TITLE:"GDC-6036" OR ABSTRACT:"GDC-6036"'

    assert build_queries(query(["divarasib", "GDC-6036", "divarasib"])) == [
        f"({names}) AND SRC:PPR"
    ]


def test_without_an_asset_the_target_is_searched_in_the_indication() -> None:
    assert build_queries(query([], "lung cancer")) == [
        '(TITLE:"KRAS") AND (TITLE:"lung cancer" OR ABSTRACT:"lung cancer") AND SRC:PPR'
    ]
    assert build_queries(query([], "not specified")) == []


def test_characters_of_the_search_language_are_removed_from_a_name() -> None:
    assert build_queries(query(['x") OR SRC:MED OR ("y']))[0].startswith(
        '(TITLE:"x OR SRC MED OR y"'
    )


@pytest.mark.parametrize("body", [b"<html>busy</html>", b"{}", b'{"resultList": {"result": 3}}'])
def test_a_body_without_a_result_list_is_refused(body: bytes) -> None:
    with pytest.raises(EuropePmcError):
        require_results(body)


async def test_fetch_asks_once_for_the_newest_preprints_and_caches(tmp_path: Path) -> None:
    server = Server()
    source = connector(tmp_path, server)

    evidence = await source.fetch(query(["divarasib"]), AS_OF)
    again = await source.fetch(query(["divarasib"]), AS_OF)

    assert len(evidence) == 2 and [e.id for e in again] == [e.id for e in evidence]
    assert len(server.asked) == 1
    params = server.asked[0].url.params
    assert params["sort"] == "FIRST_PDATE_D desc" and params["resultType"] == "core"


async def test_a_replayed_run_does_not_see_a_later_preprint(tmp_path: Path) -> None:
    evidence = await connector(tmp_path, Server()).fetch(query(["divarasib"]), date(2025, 1, 1))

    assert [e.published_at for e in evidence] == [date(2024, 3, 21)]


async def test_nothing_is_asked_without_an_asset_or_an_indication(tmp_path: Path) -> None:
    server = Server()

    assert await connector(tmp_path, server).fetch(query([], "not specified"), AS_OF) == []
    assert server.asked == []


async def test_an_error_page_is_raised_and_not_cached(tmp_path: Path) -> None:
    server = Server(b"<html>maintenance</html>")
    source = connector(tmp_path, server)

    with pytest.raises(EuropePmcError):
        await source.fetch(query(["divarasib"]), AS_OF)

    assert len(await source.fetch(query(["divarasib"]), AS_OF)) == 2
    assert await connector(tmp_path, Server(EMPTY)).fetch(query(["other"]), AS_OF) == []
