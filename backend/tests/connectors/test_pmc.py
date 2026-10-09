"""The PubMed Central full-text connector on a recorded open-access paper."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.pmc import (
    MAX_PAPERS,
    MAX_PIECES,
    PmcFullTextConnector,
    by_strength,
    parse_full_text,
    require_document,
    reusable,
)
from bioverdict.connectors.text import CHUNK_CHARS
from bioverdict.connectors.validate import BodyError
from bioverdict.contracts import Connector
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate
from bioverdict.store.models import (
    Evidence,
    EvidenceLevel,
    Indication,
    Locator,
    ResolverOutput,
    SourceKind,
    Target,
)

RAW = Path(__file__).parents[3] / "fixtures" / "raw" / "pmc"
OPEN = (RAW / "bioc_38052910.json").read_bytes()  # CC BY 4.0
ABSENT = (RAW / "bioc_not_found.txt").read_bytes()
AS_OF = date(2026, 10, 9)
QUERY = ResolverOutput(indication=Indication(name="CRC"), targets=[Target(symbol="KRAS")])


def paper(
    pmid: str = "38052910",
    level: EvidenceLevel = EvidenceLevel.HUMAN_INTERVENTIONAL,
    day: date = date(2023, 12, 5),
) -> Evidence:
    return Evidence(
        id=f"pmid:{pmid}",
        source="PubMed",
        source_family="literature",
        source_kind=SourceKind.PEER_REVIEWED,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        locator=Locator(type="pmid", value=pmid),
        excerpt="Title\nAbstract.",
        published_at=day,
        retrieved_at=datetime(2026, 10, 9, tzinfo=UTC),
        level=level,
        independence_group="trial:NCT04449874",
        version=1,
    )


def with_licence(text: str) -> bytes:
    answer = json.loads(OPEN)
    answer[0]["documents"][0]["passages"][0]["infons"]["license"] = text
    return json.dumps(answer).encode()


class Papers:
    """Stands for the PubMed connector: the papers it found for the query."""

    name = "pubmed"

    def __init__(self, *papers: Evidence) -> None:
        self.papers = list(papers)

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        return self.papers


class Service:
    def __init__(self, answers: dict[str, bytes | int]) -> None:
        self.answers = answers
        self.asked: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        pmid = request.url.path.split("/")[-2]
        self.asked.append(pmid)
        answer = self.answers.get(pmid, ABSENT)
        if isinstance(answer, int):
            return httpx.Response(answer)
        return httpx.Response(200, content=answer)


def connector(tmp_path: Path, service: Service, *papers: Evidence) -> PmcFullTextConnector:
    conn = connect(tmp_path / "pmc.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(service))
    http = CachedHttpClient(client, HttpCache(conn), wait=wait_none())
    return PmcFullTextConnector(http, Papers(*papers))  # type: ignore[arg-type]


def test_it_is_a_connector(tmp_path: Path) -> None:
    assert isinstance(connector(tmp_path, Service({})), Connector)


def test_results_and_tables_become_pieces_of_the_same_paper() -> None:
    pieces, _ = parse_full_text(OPEN, paper())

    assert pieces and len(pieces) <= MAX_PIECES
    assert all(len(p.excerpt) <= CHUNK_CHARS for p in pieces)
    assert "Patient disposition and baseline demographics" in pieces[0].excerpt  # Results first
    first = pieces[0]
    assert first.url == "https://pmc.ncbi.nlm.nih.gov/articles/PMC10803265/"
    assert first.locator == Locator(type="pmcid", value="PMC10803265#results:1")
    assert first.source == "PubMed Central (open-access full text)"
    # The same paper as its abstract: counted once, weighed and dated alike.
    assert {p.independence_group for p in pieces} == {"trial:NCT04449874"}
    assert {(p.level, p.source_kind, p.published_at) for p in pieces} == {
        (EvidenceLevel.HUMAN_INTERVENTIONAL, SourceKind.PEER_REVIEWED, date(2023, 12, 5))
    }
    assert len({p.id for p in pieces}) == len(pieces)


def test_every_piece_is_text_of_the_paper() -> None:
    passages = json.loads(OPEN)[0]["documents"][0]["passages"][1:]
    # The connector reads the Results before the tables; within each, the paper's own order.
    ordered = sorted(passages, key=lambda p: p["infons"]["section_type"] != "RESULTS")
    article = " ".join(" ".join(p["text"] for p in ordered).split())

    pieces, _ = parse_full_text(OPEN, paper())

    assert all(piece.excerpt in article for piece in pieces)


@pytest.mark.parametrize(
    "licence",
    [
        (
            "Creative Commons Attribution Non-Commercial No Derivatives 4.0 License: "
            "https://creativecommons.org/licenses/by-nc-nd/4.0/"
        ),
        "distributed under the (CC BY-NC-ND 4.0) license.",
        "https://creativecommons.org/licenses/by-nc/4.0/",
        "All rights reserved.",
        "",
    ],
)
def test_a_paper_whose_licence_restricts_reuse_is_left_with_its_abstract(licence: str) -> None:
    assert not reusable(licence)
    assert parse_full_text(with_licence(licence), paper()) == ([], False)


@pytest.mark.parametrize(
    "licence",
    [
        (
            "licensed under a Creative Commons Attribution 4.0 International License ... "
            "http://creativecommons.org/licenses/by/4.0/."
        ),
        "CC BY",
        "https://creativecommons.org/publicdomain/zero/1.0/",
    ],
)
def test_an_open_licence_is_read(licence: str) -> None:
    assert reusable(licence)


def test_a_paper_outside_the_open_subset_has_no_full_text() -> None:
    require_document(ABSENT)  # a valid answer, so it is cached and not asked again
    assert parse_full_text(ABSENT, paper()) == ([], False)


@pytest.mark.parametrize("body", [b"<html>maintenance</html>", b"[]", b'[{"documents": []}]'])
def test_anything_else_is_refused_before_it_is_cached(body: bytes) -> None:
    with pytest.raises(BodyError):
        require_document(body)


def test_human_findings_and_the_newest_papers_come_first() -> None:
    old = paper("1", day=date(2020, 1, 1))
    new = paper("2", day=date(2025, 1, 1))
    lab = paper("3", level=EvidenceLevel.IN_VITRO, day=date(2026, 1, 1))

    assert [p.id for p in by_strength([lab, old, new])] == ["pmid:2", "pmid:1", "pmid:3"]


def test_a_paper_that_names_the_asset_comes_before_a_newer_paper_on_its_class() -> None:
    about_asset = paper("1", day=date(2020, 1, 1)).model_copy(
        update={"excerpt": "Divarasib (GDC-6036) in solid tumours.\nAbstract."}
    )
    about_class = paper("2", day=date(2026, 1, 1))

    ordered = by_strength([about_class, about_asset], ["divarasib"])

    assert [p.id for p in ordered] == ["pmid:1", "pmid:2"]


async def test_fetch_reads_the_open_papers_and_skips_the_rest(tmp_path: Path) -> None:
    service = Service({"38052910": OPEN, "2": with_licence("CC BY-NC-ND 4.0")})
    source = connector(tmp_path, service, paper(), paper("2"), paper("3"))

    evidence = await source.fetch(QUERY, AS_OF)

    assert sorted(service.asked) == ["2", "3", "38052910"]
    assert {e.locator.value.split("#")[0] for e in evidence if e.locator} == {"PMC10803265"}
    assert [p for p in source.problems if "could not be read" in p] == []


async def test_a_second_run_is_answered_from_the_cache_also_for_absent_papers(
    tmp_path: Path,
) -> None:
    service = Service({"38052910": OPEN})
    source = connector(tmp_path, service, paper(), paper("3"))

    first = await source.fetch(QUERY, AS_OF)
    second = await source.fetch(QUERY, AS_OF)

    assert first and [e.excerpt for e in first] == [e.excerpt for e in second]
    assert sorted(service.asked) == ["3", "38052910"]


async def test_a_failed_download_is_named_and_the_other_papers_are_read(tmp_path: Path) -> None:
    service = Service({"38052910": OPEN, "2": 500})
    source = connector(tmp_path, service, paper("2", day=date(2026, 1, 1)), paper())

    evidence = await source.fetch(QUERY, AS_OF)

    assert evidence and "full text of PMID 2 could not be read" in source.problems


async def test_no_more_than_the_limit_of_full_texts_is_read(tmp_path: Path) -> None:
    many = [paper(str(n), day=date(2020, 1, n)) for n in range(1, 13)]
    service = Service({p.locator.value: OPEN for p in many if p.locator})

    evidence = await connector(tmp_path, service, *many).fetch(QUERY, AS_OF)

    assert len(service.asked) == MAX_PAPERS
    assert len(evidence) <= MAX_PAPERS * MAX_PIECES


async def test_nothing_is_asked_when_pubmed_found_nothing(tmp_path: Path) -> None:
    service = Service({})

    assert await connector(tmp_path, service).fetch(QUERY, AS_OF) == []
    assert service.asked == []
