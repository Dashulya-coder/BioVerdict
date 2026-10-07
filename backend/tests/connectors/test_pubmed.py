import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.pubmed import (
    PubMedConnector,
    build_terms,
    classify,
    parse_articles,
)
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

RAW = Path(__file__).parents[3] / "fixtures" / "raw" / "divarasib"
NOW = datetime(2026, 10, 7, tzinfo=UTC)

# Real PubMed records: the NEJM and Nature Medicine phase 1 papers, a crystal-structure paper,
# a review and a comment (pubmed.xml), the sotorasib and adagrasib phase 3 papers (analogs).
ARTICLES = {
    article.findtext(".//MedlineCitation/PMID"): article
    for name in ("pubmed.xml", "pubmed_analogs.xml")
    for article in ET.parse(RAW / name).getroot().findall(".//PubmedArticle")
}
NEJM, NATMED, STRUCTURE = "37611121", "38052910", "40391409"
REVIEW, COMMENT = "38739329", "37673947"
SOTORASIB_RCT, ADAGRASIB_RCT = "36764316", "40783289"


def xml_of(*pmids: str) -> bytes:
    root = ET.Element("PubmedArticleSet")
    root.extend(ARTICLES[pmid] for pmid in pmids)
    return ET.tostring(root, encoding="utf-8")


def parsed(*pmids: str) -> dict:
    return {e.locator.value: e for e in parse_articles(xml_of(*pmids), NOW)}


def test_a_phase_1_trial_is_interventional_peer_reviewed_evidence() -> None:
    item = parsed(NEJM)[NEJM]

    assert item.level is EvidenceLevel.HUMAN_INTERVENTIONAL
    assert item.source_kind is SourceKind.PEER_REVIEWED
    assert (item.source, item.source_family) == ("PubMed", "literature")
    assert item.url == f"https://pubmed.ncbi.nlm.nih.gov/{NEJM}/"
    assert item.published_at == date(2023, 8, 23)  # the day PubMed recorded it


def test_randomised_phase_3_papers_are_interventional() -> None:
    found = parsed(SOTORASIB_RCT, ADAGRASIB_RCT)
    assert {e.level for e in found.values()} == {EvidenceLevel.HUMAN_INTERVENTIONAL}


def test_the_excerpt_is_the_title_and_the_abstract_verbatim() -> None:
    item = parsed(NEJM)[NEJM]

    assert item.excerpt.startswith("Single-Agent Divarasib (GDC-6036)")
    assert "RESULTS: A total of 137 patients" in item.excerpt  # section labels are kept
    assert "a confirmed response was observed in 53.4% of patients" in item.excerpt


def test_special_characters_of_the_abstract_survive() -> None:
    item = parsed(STRUCTURE)[STRUCTURE]
    assert "Å" in item.excerpt and "Cα" in item.excerpt


def test_a_basic_science_paper_gets_the_weakest_level() -> None:
    assert parsed(STRUCTURE)[STRUCTURE].level is EvidenceLevel.IN_VITRO


def test_reviews_and_comments_are_left_out() -> None:
    found = parsed(NEJM, REVIEW, COMMENT)
    assert set(found) == {NEJM}


def test_papers_on_one_trial_share_an_independence_group() -> None:
    found = parsed(NEJM, NATMED, STRUCTURE)

    assert found[NEJM].independence_group == "trial:NCT04449874"
    assert found[NATMED].independence_group == "trial:NCT04449874"  # the same phase 1 study
    assert found[STRUCTURE].independence_group == f"paper:{STRUCTURE}"


def test_an_article_without_an_abstract_is_skipped() -> None:
    xml = (
        "<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article>"
        "<ArticleTitle>Only a title</ArticleTitle></Article></MedlineCitation>"
        "</PubmedArticle></PubmedArticleSet>"
    )
    assert parse_articles(xml, NOW) == []


@pytest.mark.parametrize(
    "types, mesh, expected",
    [
        (["Clinical Trial, Phase II"], [], EvidenceLevel.HUMAN_INTERVENTIONAL),
        (["Randomized Controlled Trial"], [], EvidenceLevel.HUMAN_INTERVENTIONAL),
        (["Journal Article"], ["Genome-Wide Association Study"], EvidenceLevel.HUMAN_GENETICS),
        (["Observational Study"], [], EvidenceLevel.HUMAN_OBSERVATIONAL),
        (["Meta-Analysis"], [], EvidenceLevel.HUMAN_OBSERVATIONAL),
        (["Journal Article"], ["Mice", "Humans"], EvidenceLevel.ANIMAL_IN_VIVO),
        (["Journal Article"], [], EvidenceLevel.IN_VITRO),
    ],
)
def test_levels_follow_the_labels_pubmed_gives(types, mesh, expected) -> None:
    classified = classify(types, mesh)
    assert classified is not None and classified[0] is expected


@pytest.mark.parametrize(
    "kind",
    ["Review", "Systematic Review", "Editorial", "Comment", "Letter", "News", "Published Erratum"],
)
def test_secondary_and_non_research_papers_are_skipped(kind: str) -> None:
    assert classify(["Journal Article", kind], []) is None


def test_a_preprint_is_marked_as_one() -> None:
    classified = classify(["Preprint"], [])
    assert classified is not None and classified[1] is SourceKind.PREPRINT


def test_a_trial_label_wins_over_animal_terms() -> None:
    classified = classify(["Clinical Trial, Phase I"], ["Mice"])
    assert classified is not None and classified[0] is EvidenceLevel.HUMAN_INTERVENTIONAL


# --- search terms ---------------------------------------------------------------------------


def query(assets: list[str], indication: str = "non-small cell lung carcinoma") -> ResolverOutput:
    return ResolverOutput(
        indication=Indication(name=indication),
        targets=[Target(symbol="KRAS")],
        known_assets=assets,
    )


def test_an_asset_is_searched_in_every_paper_and_in_trials_only() -> None:
    terms = build_terms(query(["divarasib", "GDC-6036"]))

    asset = '("divarasib"[Title/Abstract] OR "GDC-6036"[Title/Abstract])'
    assert terms[:2] == [
        asset,
        f"{asset} AND (clinical trial[pt] OR randomized controlled trial[pt])",
    ]


def test_the_class_of_the_target_is_searched_in_trials_for_analogs() -> None:
    terms = build_terms(query([]))

    assert terms == [
        (
            "(KRAS) AND non-small cell lung carcinoma AND "
            "(clinical trial[pt] OR randomized controlled trial[pt])"
        )
    ]


def test_without_a_stated_indication_there_is_no_class_search() -> None:
    assert build_terms(query([], indication="not specified")) == []


def test_characters_that_would_end_a_phrase_early_are_removed() -> None:
    [asset, _, _] = build_terms(query(['bad"name[x]']))
    assert asset == '("bad name x"[Title/Abstract])'


# --- the connector --------------------------------------------------------------------------


class FakeNCBI:
    """esearch answers by the kind of term; efetch returns the requested recorded articles."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        params = request.url.params
        if request.url.path.endswith("esearch.fcgi"):
            term = params["term"]
            if "[Title/Abstract]" in term and "clinical trial" in term:
                ids = [NEJM, NATMED]
            elif "[Title/Abstract]" in term:
                ids = [NEJM, REVIEW, COMMENT, STRUCTURE]
            else:
                ids = [SOTORASIB_RCT, ADAGRASIB_RCT]
            return httpx.Response(200, json={"esearchresult": {"idlist": ids}})
        wanted = params["id"].split(",")
        return httpx.Response(200, content=xml_of(*wanted))

    def calls(self, name: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.endswith(name)]


def make_connector(tmp_path: Path, server: FakeNCBI, **kwargs) -> PubMedConnector:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(server))
    return PubMedConnector(CachedHttpClient(client, HttpCache(conn), wait=wait_none()), **kwargs)


def test_satisfies_connector_protocol(tmp_path: Path) -> None:
    assert isinstance(make_connector(tmp_path, FakeNCBI()), Connector)


async def test_papers_of_all_searches_are_combined_without_repeats(tmp_path: Path) -> None:
    server = FakeNCBI()

    evidence = await make_connector(tmp_path, server).fetch(query(["divarasib"]), date(2026, 10, 7))

    pmids = [e.locator.value for e in evidence]
    assert sorted(pmids) == sorted({NEJM, NATMED, STRUCTURE, SOTORASIB_RCT, ADAGRASIB_RCT})
    assert len(pmids) == len(set(pmids))  # the review and the comment were skipped, none twice


async def test_only_the_papers_found_are_fetched_in_batches(tmp_path: Path) -> None:
    server = FakeNCBI()
    await make_connector(tmp_path, server).fetch(query(["divarasib"]), date(2026, 10, 7))

    assert len(server.calls("esearch.fcgi")) == 3  # asset, asset in trials, class of the target
    [fetch] = server.calls("efetch.fcgi")
    assert set(fetch.url.params["id"].split(",")) == {
        NEJM,
        REVIEW,
        COMMENT,
        STRUCTURE,
        NATMED,
        SOTORASIB_RCT,
        ADAGRASIB_RCT,
    }


async def test_every_request_names_the_tool(tmp_path: Path) -> None:
    server = FakeNCBI()
    await make_connector(tmp_path, server).fetch(query([]), date(2026, 10, 7))

    assert server.requests
    for request in server.requests:
        assert request.url.params["tool"] == "bioverdict-hackathon"
        assert "api_key" not in request.url.params and "email" not in request.url.params


async def test_a_contact_and_a_key_are_sent_when_given(tmp_path: Path) -> None:
    server = FakeNCBI()
    connector = make_connector(tmp_path, server, email="me@example.org", api_key="K")

    await connector.fetch(query([]), date(2026, 10, 7))

    for request in server.requests:
        assert request.url.params["email"] == "me@example.org"
        assert request.url.params["api_key"] == "K"


async def test_papers_recorded_after_the_cutoff_are_hidden(tmp_path: Path) -> None:
    evidence = await make_connector(tmp_path, FakeNCBI()).fetch(query([]), date(2024, 1, 1))
    assert {e.locator.value for e in evidence} == {SOTORASIB_RCT}  # KRYSTAL-12 is from 2025


async def test_a_repeated_fetch_is_served_from_the_cache(tmp_path: Path) -> None:
    server = FakeNCBI()
    connector = make_connector(tmp_path, server)
    await connector.fetch(query(["divarasib"]), date(2026, 10, 7))
    asked = len(server.requests)

    await connector.fetch(query(["divarasib"]), date(2026, 10, 7))

    assert len(server.requests) == asked


async def test_the_number_of_papers_per_search_is_limited(tmp_path: Path) -> None:
    server = FakeNCBI()
    await make_connector(tmp_path, server, retmax=7).fetch(query([]), date(2026, 10, 7))
    assert {r.url.params["retmax"] for r in server.calls("esearch.fcgi")} == {"7"}
