"""The SEC EDGAR connector on recorded real answers (scripts/record_edgar_fixtures.py)."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from tenacity import wait_none

from bioverdict.connectors.edgar import (
    FAMILY,
    MAX_FILINGS,
    EdgarConnector,
    documents,
    event_filings,
    find_cik,
    naming,
    paragraphs,
)
from bioverdict.connectors.http import CachedHttpClient
from bioverdict.contracts import Connector
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate
from bioverdict.store.models import (
    Evidence,
    EvidenceLevel,
    Indication,
    ResolverOutput,
    SourceKind,
    Target,
)

RAW = Path(__file__).parents[3] / "fixtures" / "raw" / "edgar"
COMPANIES = json.loads((RAW / "company_tickers.json").read_text())
SUBMISSIONS = json.loads((RAW / "submissions.json").read_text())
INDEX = json.loads((RAW / "index.json").read_text())
EXHIBIT = (RAW / "rvmd-ex99_1.htm").read_bytes()
AS_OF = date(2026, 10, 9)
CONTACT = "Test Person test@example.org"
RECORDED = "0001193125-26-335039"  # the 8-K whose index and exhibit were recorded
QUERY = ResolverOutput(
    indication=Indication(name="pancreatic cancer"),
    targets=[Target(symbol="KRAS")],
    known_assets=["zoldonrasib", "RMC-9805"],
)


def study(sponsor: str, nct: str = "NCT1") -> Evidence:
    return Evidence(
        id=f"{nct}:status",
        source="ClinicalTrials.gov",
        source_family="registry",
        source_kind=SourceKind.REGISTRY,
        url=f"https://clinicaltrials.gov/study/{nct}",
        excerpt="{}",
        retrieved_at=datetime(2026, 10, 9, tzinfo=UTC),
        level=EvidenceLevel.REGISTRY_RECORD,
        independence_group=f"sponsor:{sponsor}",
        version=1,
    )


class Registry:
    """Stands for the ClinicalTrials.gov connector: the studies it found for the asset."""

    name = "clinicaltrials"

    def __init__(self, *records: Evidence) -> None:
        self.records = list(records)

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        return self.records


class Sec:
    """Answers from the recordings; every filing shares the recorded index and exhibit."""

    def __init__(self, failing: str = "") -> None:
        self.failing = failing
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        path = request.url.path
        if self.failing and self.failing in path:
            return httpx.Response(500)
        if path.endswith("company_tickers.json"):
            return httpx.Response(200, json=COMPANIES)
        if "/submissions/" in path:
            return httpx.Response(200, json=SUBMISSIONS)
        if path.endswith("index.json"):
            return httpx.Response(200, json=INDEX)
        if path.endswith("rvmd-ex99_1.htm"):
            return httpx.Response(200, content=EXHIBIT)
        return httpx.Response(200, content=b"<html><p>Cover page of the report.</p></html>")


def connector(
    tmp_path: Path, server: Sec, *records: Evidence, contact: str | None = CONTACT
) -> EdgarConnector:
    conn = connect(tmp_path / "sec.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(server))
    http = CachedHttpClient(client, HttpCache(conn), wait=wait_none())
    return EdgarConnector(http, Registry(*records), contact)  # type: ignore[arg-type]


def test_it_is_a_connector(tmp_path: Path) -> None:
    assert isinstance(connector(tmp_path, Sec()), Connector)


def test_a_sponsor_is_matched_by_its_whole_name_only() -> None:
    assert find_cik("Revolution Medicines", COMPANIES) == (1628171, "Revolution Medicines, Inc.")
    assert find_cik("REVOLUTION MEDICINES INC.", COMPANIES) is not None
    assert find_cik("Revolution", COMPANIES) is None  # part of a name is not the company
    assert find_cik("Roche", COMPANIES) is None  # does not file with the SEC
    assert find_cik("", COMPANIES) is None


def test_a_subsidiary_named_pharmaceuticals_is_its_listed_parent() -> None:
    assert find_cik("Novartis Pharmaceuticals", COMPANIES) == (1114448, "NOVARTIS AG")


def test_two_companies_under_one_name_give_no_answer() -> None:
    twins = COMPANIES | {"x": {"cik_str": 999, "ticker": "X", "title": "Amgen Corp"}}

    assert find_cik("Amgen", twins) is None


def test_only_filings_that_report_on_the_pipeline_are_read_newest_first() -> None:
    filings = event_filings(SUBMISSIONS, AS_OF)

    assert filings and len(filings) <= MAX_FILINGS
    assert {f["form"] for f in filings} == {"8-K"}
    assert [f["filed"] for f in filings] == sorted((f["filed"] for f in filings), reverse=True)
    assert RECORDED in {f["accessionNumber"] for f in filings}
    # The newest 8-K is a financing (items 1.01 and 2.03): not a pipeline report.
    assert "0001193125-26-377362" not in {f["accessionNumber"] for f in filings}


def test_a_replayed_run_sees_only_filings_made_by_then() -> None:
    filings = event_filings(SUBMISSIONS, date(2026, 5, 1))

    assert filings and all(f["filed"] <= date(2026, 5, 1) for f in filings)


def test_the_main_document_and_the_press_release_exhibit_are_read() -> None:
    assert documents(INDEX, "rvmd-20260805.htm") == ["rvmd-20260805.htm", "rvmd-ex99_1.htm"]
    assert documents(INDEX, "missing.htm") == ["rvmd-ex99_1.htm"]


def test_paragraphs_are_visible_text_without_markup_or_the_machine_header() -> None:
    page = (
        b"<html><ix:header><ix:hidden>0001628171 false</ix:hidden></ix:header>"
        b"<style>p{}</style><p>First&nbsp;line<br>second &amp; third</p><div>Next</div></html>"
    )

    assert paragraphs(page) == ["First line", "second & third", "Next"]


def test_only_what_names_the_asset_is_kept_and_a_heading_brings_its_paragraph() -> None:
    texts = ["About us.", "Zoldonrasib in PDAC", "The company presented data.", "Cash position."]

    assert naming(texts, ["zoldonrasib"]) == ["Zoldonrasib in PDAC", "The company presented data."]
    assert naming(texts, ["abc"]) == []  # too short a name would match unrelated words


async def test_fetch_follows_sponsor_company_filings_and_keeps_the_assets_paragraphs(
    tmp_path: Path,
) -> None:
    server = Sec()
    edgar = connector(tmp_path, server, study("Revolution Medicines"), study("Roche", "NCT2"))

    evidence = await edgar.fetch(QUERY, AS_OF)

    assert evidence and edgar.problems == []
    first = evidence[0]
    assert first.source == "SEC EDGAR 8-K of Revolution Medicines, Inc."
    assert first.source_family == FAMILY and first.source_kind is SourceKind.COMPANY
    # A company's statement: a fact about a program, no weight for "the drug works".
    assert {e.level for e in evidence} == {EvidenceLevel.REGISTRY_RECORD}
    # The company and its own registry records count once.
    assert {e.independence_group for e in evidence} == {"sponsor:Revolution Medicines"}
    assert all("zoldonrasib" in e.excerpt.casefold() for e in evidence)
    assert all(
        e.url.startswith("https://www.sec.gov/Archives/edgar/data/1628171/") for e in evidence
    )
    assert all(e.published_at is not None and e.published_at <= AS_OF for e in evidence)
    assert len({e.id for e in evidence}) == len(evidence)
    assert all(r.headers["user-agent"] == CONTACT for r in server.asked)


async def test_a_sponsor_outside_the_sec_gives_nothing_and_no_problem(tmp_path: Path) -> None:
    server = Sec()
    edgar = connector(tmp_path, server, study("Roche"))

    assert await edgar.fetch(QUERY, AS_OF) == [] and edgar.problems == []
    assert [r.url.path for r in server.asked] == ["/files/company_tickers.json"]


async def test_without_a_contact_the_sec_is_not_asked_and_the_section_says_so(
    tmp_path: Path,
) -> None:
    server = Sec()
    edgar = connector(tmp_path, server, study("Revolution Medicines"), contact=" ")

    assert await edgar.fetch(QUERY, AS_OF) == []
    assert edgar.problems == ["SEC_USER_AGENT is not set: the SEC was not asked"]
    assert server.asked == []


async def test_nothing_is_asked_without_an_asset_name_or_a_sponsor(tmp_path: Path) -> None:
    server = Sec()
    no_asset = QUERY.model_copy(update={"known_assets": []})

    assert (
        await connector(tmp_path, server, study("Revolution Medicines")).fetch(no_asset, AS_OF)
        == []
    )
    assert await connector(tmp_path, server).fetch(QUERY, AS_OF) == []
    assert server.asked == []


async def test_a_filing_that_cannot_be_read_is_named_and_the_others_are_kept(
    tmp_path: Path,
) -> None:
    folder = RECORDED.replace("-", "")
    edgar = connector(tmp_path, Sec(failing=folder), study("Revolution Medicines"))

    evidence = await edgar.fetch(QUERY, AS_OF)

    assert evidence and edgar.problems == [f"filing {RECORDED} could not be read"]


async def test_a_second_run_is_answered_from_the_cache(tmp_path: Path) -> None:
    server = Sec()
    edgar = connector(tmp_path, server, study("Revolution Medicines"))

    first = await edgar.fetch(QUERY, AS_OF)
    asked = len(server.asked)
    second = await edgar.fetch(QUERY, AS_OF)

    assert [e.excerpt for e in first] == [e.excerpt for e in second]
    assert len(server.asked) == asked
