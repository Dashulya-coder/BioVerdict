from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from tenacity import wait_none

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.pubmed_guidelines import (
    PubMedGuidelinesConnector,
    build_term,
    parse_guidelines,
)
from bioverdict.contracts import Connector
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate
from bioverdict.store.models import EvidenceLevel, Indication, ResolverOutput, SourceKind, Target

RAW = Path(__file__).parents[3] / "fixtures" / "raw" / "divarasib"
NOW = datetime(2026, 10, 7, tzinfo=UTC)

# Real PubMed records (retrieved 2026-10-10): five practice guidelines for non-small cell lung
# cancer, the newest first. One has no abstract.
XML = (RAW / "pubmed_guidelines.xml").read_bytes()
NO_ABSTRACT, ASCO = "42851192", "42372216"


def query(indication: str = "non-small cell lung carcinoma") -> ResolverOutput:
    return ResolverOutput(
        indication=Indication(name=indication), targets=[Target(symbol="KRAS")], known_assets=[]
    )


def test_a_guideline_with_an_abstract_is_peer_reviewed_evidence_of_its_own() -> None:
    evidence = parse_guidelines(XML, NOW)

    assert len(evidence) == 4 and NO_ABSTRACT not in [e.locator.value for e in evidence]
    asco = next(e for e in evidence if e.locator.value == ASCO)
    assert "ASCO Living Guideline" in asco.excerpt.splitlines()[0]
    assert asco.level is EvidenceLevel.HUMAN_OBSERVATIONAL
    assert asco.source_kind is SourceKind.PEER_REVIEWED
    assert asco.source_family == "literature" and asco.url.endswith(f"/{ASCO}/")
    assert len({e.independence_group for e in evidence}) == 4  # two guidelines count twice


def test_a_paper_that_is_not_labelled_a_guideline_is_not_read() -> None:
    plain = XML.replace(b"Practice Guideline", b"Journal Article")

    assert parse_guidelines(plain, NOW) == []


def test_the_search_is_for_guidelines_of_the_indication() -> None:
    assert build_term('bad"name[x]') == "bad name x AND (Practice Guideline[pt] OR Guideline[pt])"


class FakeNCBI:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": [ASCO, NO_ABSTRACT]}})
        return httpx.Response(200, content=XML)


def connector(tmp_path: Path, server: FakeNCBI) -> PubMedGuidelinesConnector:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(server))
    return PubMedGuidelinesConnector(CachedHttpClient(client, HttpCache(conn), wait=wait_none()))


def test_satisfies_connector_protocol(tmp_path: Path) -> None:
    assert isinstance(connector(tmp_path, FakeNCBI()), Connector)


async def test_the_newest_guidelines_are_searched_and_read(tmp_path: Path) -> None:
    server = FakeNCBI()

    evidence = await connector(tmp_path, server).fetch(query(), date(2026, 10, 7))

    assert {e.locator.value for e in evidence} <= {ASCO, "42790620", "42764215", "42763208"}
    search = server.requests[0].url.params
    assert search["sort"] == "pub_date" and "Practice Guideline[pt]" in search["term"]
    assert "non-small cell lung carcinoma" in search["term"]


async def test_without_an_indication_nothing_is_asked(tmp_path: Path) -> None:
    server = FakeNCBI()

    assert await connector(tmp_path, server).fetch(query("not specified"), date(2026, 10, 7)) == []
    assert server.requests == []


async def test_a_guideline_recorded_after_the_cutoff_is_not_seen(tmp_path: Path) -> None:
    evidence = await connector(tmp_path, FakeNCBI()).fetch(query(), date(2020, 1, 1))

    assert evidence == []
