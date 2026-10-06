import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from bioverdict.connectors.clinicaltrials import (
    MAX_MEASURES,
    MAX_RESULT_STUDIES,
    ClinicalTrialsConnector,
    parse_results,
)
from bioverdict.connectors.http import CachedHttpClient
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate
from bioverdict.store.models import EvidenceLevel, Indication, ResolverOutput, Target

RAW = Path(__file__).parents[3] / "fixtures" / "raw" / "clinicaltrials"
NOW = datetime(2026, 10, 7, tzinfo=UTC)


def raw(name: str) -> dict:
    return json.loads((RAW / name).read_text(encoding="utf-8"))


def study(nct: str, sponsor: str = "Amgen") -> dict:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor}},
        }
    }


SOTORASIB = raw("results_NCT04303780.json")  # CodeBreaK 200: one primary measure
FUTILITY = raw("results_NCT04933695.json")  # terminated for futility: eight measures


def test_a_primary_result_keeps_the_values_the_registry_posted() -> None:
    [item] = parse_results(SOTORASIB, study("NCT04303780"), NOW)

    fragment = json.loads(item.excerpt)
    assert (fragment["type"], fragment["title"]) == ("PRIMARY", "Progression-free Survival (PFS)")
    assert fragment["groups"] == ["AMG 510", "Docetaxel"]
    values = [m["value"] for m in fragment["classes"][0]["categories"][0]["measurements"]]
    assert values == ["5.62", "4.47"]
    assert fragment["analyses"][0]["paramValue"] == "0.663"
    assert (fragment["analyses"][0]["ciLowerLimit"], fragment["analyses"][0]["ciUpperLimit"]) == (
        "0.509",
        "0.864",
    )


def test_a_result_is_human_evidence_dated_when_it_was_posted() -> None:
    [item] = parse_results(SOTORASIB, study("NCT04303780"), NOW)

    assert item.level is EvidenceLevel.HUMAN_INTERVENTIONAL
    assert item.published_at == date(2023, 5, 10)
    assert item.url == "https://clinicaltrials.gov/study/NCT04303780"
    assert item.independence_group == "sponsor:Amgen"


def test_a_result_can_be_replaced_by_an_amended_posting() -> None:
    [item] = parse_results(SOTORASIB, study("NCT04303780"), NOW)
    assert item.status_key == "nct:NCT04303780:result:primary:1"


def test_primary_measures_come_first_and_the_number_is_capped() -> None:
    items = parse_results(FUTILITY, study("NCT04933695"), NOW)

    assert len(items) == MAX_MEASURES
    assert json.loads(items[0].excerpt)["type"] == "PRIMARY"
    assert len({i.id for i in items}) == len(items) and len({i.status_key for i in items}) == len(
        items
    )


def test_every_posted_value_appears_verbatim_in_the_excerpt() -> None:
    source = SOTORASIB["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][0]
    [item] = parse_results(SOTORASIB, study("NCT04303780"), NOW)

    for measurement in source["classes"][0]["categories"][0]["measurements"]:
        assert f'"value": "{measurement["value"]}"' in item.excerpt
    assert source["timeFrame"] in item.excerpt


def test_a_study_without_posted_results_yields_nothing() -> None:
    empty = {"protocolSection": {"identificationModule": {"nctId": "NCT1"}}}
    assert parse_results(empty, study("NCT1"), NOW) == []


# --- the connector reads results only where they exist ---------------------------------------


def make_connector(tmp_path: Path, handler, **kwargs) -> ClinicalTrialsConnector:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ClinicalTrialsConnector(
        CachedHttpClient(client, HttpCache(conn), wait=wait_none()), **kwargs
    )


def search_record(nct: str, has_results: bool) -> dict:
    record = {
        "protocolSection": {
            "identificationModule": {"nctId": nct},
            "statusModule": {
                "overallStatus": "TERMINATED",
                "studyFirstPostDateStruct": {"date": "2021-01-01"},
                "lastUpdatePostDateStruct": {"date": "2022-01-01"},
            },
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Amgen"}},
        }
    }
    if has_results:
        record["hasResults"] = True
    return record


def query() -> ResolverOutput:
    return ResolverOutput(
        indication=Indication(name="NSCLC"),
        targets=[Target(symbol="KRAS")],
        known_assets=["sotorasib"],
    )


class Registry:
    """Pages of search records, and results for the studies that have them."""

    def __init__(self, pages: list[dict]) -> None:
        self.pages = pages
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.rstrip("/") != "/api/v2/studies":
            return httpx.Response(200, content=(RAW / "results_NCT04303780.json").read_bytes())
        token = request.url.params.get("pageToken")
        index = 0 if token is None else int(token)
        return httpx.Response(
            200, json=self.pages[index] if index < len(self.pages) else {"studies": []}
        )

    def results_asked(self) -> list[str]:
        return [r.url.path.rsplit("/", 1)[-1] for r in self.requests if "/studies/" in r.url.path]


async def test_results_are_read_only_for_studies_that_have_them(tmp_path: Path) -> None:
    registry = Registry(
        [{"studies": [search_record("NCT04303780", True), search_record("NCT2", False)]}]
    )

    evidence = await make_connector(tmp_path, registry).fetch(query(), date(2026, 10, 7))

    assert registry.results_asked() == ["NCT04303780"]
    assert any(e.level is EvidenceLevel.HUMAN_INTERVENTIONAL for e in evidence)


async def test_a_result_posted_after_the_cutoff_is_not_shown(tmp_path: Path) -> None:
    registry = Registry([{"studies": [search_record("NCT04303780", True)]}])

    evidence = await make_connector(tmp_path, registry).fetch(query(), date(2023, 1, 1))

    assert not [e for e in evidence if e.level is EvidenceLevel.HUMAN_INTERVENTIONAL]


async def test_no_more_results_are_read_than_the_limit(tmp_path: Path) -> None:
    many = [search_record(f"NCT{n:08d}", True) for n in range(MAX_RESULT_STUDIES + 5)]
    registry = Registry([{"studies": many}])

    await make_connector(tmp_path, registry).fetch(query(), date(2026, 10, 7))

    assert len(registry.results_asked()) == MAX_RESULT_STUDIES


async def test_the_next_page_of_a_query_is_read(tmp_path: Path) -> None:
    registry = Registry(
        [
            {"studies": [search_record("NCT00000001", False)], "nextPageToken": "1"},
            {"studies": [search_record("NCT00000002", False)]},
        ]
    )

    evidence = await make_connector(tmp_path, registry).fetch(query(), date(2026, 10, 7))

    assert {e.locator.value for e in evidence if e.locator} == {"NCT00000001", "NCT00000002"}


@pytest.mark.parametrize("pages", [1, 2])
async def test_the_page_limit_is_respected(tmp_path: Path, pages: int) -> None:
    many = [
        {"studies": [search_record(f"NCT0000000{n}", False)], "nextPageToken": str(n + 1)}
        for n in range(5)
    ]
    registry = Registry(many)

    await make_connector(tmp_path, registry, max_pages=pages).fetch(query(), date(2026, 10, 7))

    plain = [r for r in registry.requests if "filter.overallStatus" not in str(r.url)]
    assert len(plain) == pages


async def test_results_that_cannot_be_read_do_not_stop_the_rest(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.rstrip("/") != "/api/v2/studies":
            return httpx.Response(429)  # the registry refuses the results requests
        return httpx.Response(200, json={"studies": [search_record("NCT04303780", True)]})

    connector = make_connector(tmp_path, handler)

    evidence = await connector.fetch(query(), date(2026, 10, 7))

    assert any(e.id.endswith(":status") for e in evidence)  # the search evidence survives
    assert not [e for e in evidence if e.level is EvidenceLevel.HUMAN_INTERVENTIONAL]
    assert connector.problems == ["results of NCT04303780 could not be read (HTTPStatusError)"]


async def test_the_problems_of_one_fetch_are_not_carried_into_the_next(tmp_path: Path) -> None:
    registry = Registry([{"studies": [search_record("NCT04303780", False)]}])
    connector = make_connector(tmp_path, registry)
    connector.problems = ["left over"]

    await connector.fetch(query(), date(2026, 10, 7))

    assert connector.problems == []
