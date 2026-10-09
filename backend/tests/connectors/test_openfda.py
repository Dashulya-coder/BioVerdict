"""The openFDA connector on recorded real answers (scripts/record_openfda_fixtures.py)."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.openfda import (
    ANALOG_FAMILY,
    OpenFdaConnector,
    OpenFdaError,
    parse_approvals,
    parse_label,
    pick_label,
    require_results,
)
from bioverdict.connectors.text import CHUNK_CHARS, chunks
from bioverdict.contracts import Connector
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate
from bioverdict.store.models import (
    Asset,
    Evidence,
    EvidenceLevel,
    Indication,
    ResolverOutput,
    SourceKind,
    Target,
)

RAW = Path(__file__).parents[3] / "fixtures" / "raw"
NOW = datetime(2026, 10, 9, tzinfo=UTC)
TODAY = datetime.now(UTC).date()
KRAS = Target(symbol="KRAS", ensembl="ENSG00000133703")
NOT_FOUND = {"error": {"code": "NOT_FOUND", "message": "No matches found!"}}


def recorded(name: str) -> dict:
    return json.loads((RAW / "openfda" / name).read_text(encoding="utf-8"))


class Fda:
    """Open Targets names the KRAS analogs; openFDA answers from its recordings."""

    def __init__(self, failing: str = "", status: int = 503, body: bytes | None = None) -> None:
        self.failing, self.status, self.body = failing, status, body
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        if "opentargets" in request.url.host:
            content = (RAW / "market" / "opentargets_analogs_kras.json").read_bytes()
            return httpx.Response(200, content=content)
        dataset = request.url.path.rsplit("/", 1)[1].removesuffix(".json")
        drug = request.url.params["search"].split('"')[1].lower()
        if self.failing and self.failing in (dataset, drug):
            if self.body is not None:
                return httpx.Response(200, content=self.body)
            return httpx.Response(self.status, json=NOT_FOUND)
        return httpx.Response(200, json=recorded(f"{dataset}_{drug}.json"))


def connector(tmp_path: Path, server: Fda, api_key: str | None = None) -> OpenFdaConnector:
    conn = connect(tmp_path / "fda.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(server))
    return OpenFdaConnector(CachedHttpClient(client, HttpCache(conn), wait=wait_none()), api_key)


def query(**fields) -> ResolverOutput:
    return ResolverOutput(indication=Indication(name="NSCLC"), targets=[KRAS], **fields)


def keys(evidence: list[Evidence]) -> set[str]:
    return {item.status_key for item in evidence if item.status_key}


def test_it_is_a_connector(tmp_path: Path) -> None:
    assert isinstance(connector(tmp_path, Fda()), Connector)


def test_an_original_approval_and_each_efficacy_supplement_are_dated_facts() -> None:
    approvals = parse_approvals(recorded("drugsfda_sotorasib.json"), "SOTORASIB", NOW)

    by_key = {item.status_key: item for item in approvals}
    assert set(by_key) == {"fda:NDA214665:ORIG1", "fda:NDA214665:SUPPL9"}
    original = by_key["fda:NDA214665:ORIG1"]
    assert original.published_at == date(2021, 5, 28)
    assert original.source_kind is SourceKind.REGULATOR
    assert original.level is EvidenceLevel.REGISTRY_RECORD  # an approval proves no efficacy here
    assert original.source_family == ANALOG_FAMILY and "approved analog" in original.source
    assert original.url.endswith("ApplNo=214665")
    fragment = json.loads(original.excerpt)
    assert fragment["review_priority"] == "PRIORITY" and fragment["sponsor_name"] == "AMGEN INC"


def test_a_labelling_supplement_is_not_an_approval_event() -> None:
    approvals = parse_approvals(recorded("drugsfda_sotorasib.json"), "SOTORASIB", NOW)

    kinds = {json.loads(a.excerpt)["submission_class_code_description"] for a in approvals}
    assert "Labeling" not in kinds


def test_a_biologic_is_matched_without_its_four_letter_suffix() -> None:
    approvals = parse_approvals(recorded("drugsfda_lecanemab.json"), "LECANEMAB", NOW)

    assert {a.locator.value for a in approvals if a.locator} == {"BLA761269", "BLA761375"}


def test_a_generic_copy_is_not_an_approval() -> None:
    answer = recorded("drugsfda_sotorasib.json")
    answer["results"][0]["application_number"] = "ANDA999999"

    assert parse_approvals(answer, "SOTORASIB", NOW) == []


def test_another_drug_in_the_answer_is_left_out() -> None:
    assert parse_approvals(recorded("drugsfda_sotorasib.json"), "ADAGRASIB", NOW) == []


def test_a_label_gives_whole_statements_and_quotable_study_text() -> None:
    answer = recorded("label_lecanemab.json")
    label = pick_label(answer, "LECANEMAB", {"BLA761269"})
    assert label is not None

    evidence = parse_label(label, "LECANEMAB", NOW)

    whole = {e.status_key.rsplit(":", 1)[1]: e for e in evidence if e.status_key}
    assert set(whole) == {"indications_and_usage", "boxed_warning"}
    assert whole["boxed_warning"].excerpt == label["boxed_warning"][0]
    assert whole["boxed_warning"].level is EvidenceLevel.HUMAN_OBSERVATIONAL
    studies = [e for e in evidence if e.status_key is None]
    assert studies and all(e.level is EvidenceLevel.HUMAN_INTERVENTIONAL for e in studies)
    assert all(len(e.excerpt) <= CHUNK_CHARS for e in studies)
    assert all(e.excerpt in label["clinical_studies"][0] for e in studies)  # verbatim pieces
    assert len({e.id for e in evidence}) == len(evidence)
    assert {e.published_at for e in evidence} == {date(2026, 7, 21)}
    assert all(e.url.endswith(label["set_id"]) for e in evidence)


def test_a_label_of_another_drug_is_not_picked() -> None:
    assert pick_label(recorded("label_sotorasib.json"), "ADAGRASIB", set()) is None


def test_the_label_of_an_approved_application_wins_over_a_newer_copy() -> None:
    own = {"set_id": "a", "effective_time": "20240101", "openfda": {"generic_name": ["X"]}}
    own["openfda"]["application_number"] = ["NDA1"]
    copy = {"set_id": "b", "effective_time": "20260101", "openfda": {"generic_name": ["X"]}}

    assert pick_label({"results": [copy, own]}, "X", {"NDA1"}) is own
    assert pick_label({"results": [copy, own]}, "X", set()) is copy


def test_chunks_lose_nothing_and_cut_between_sentences() -> None:
    text = " ".join(f"Sentence number {n} ends here." for n in range(400))

    pieces = chunks(text, 500)

    assert " ".join(pieces) == text
    assert all(len(piece) <= 500 and piece.endswith(".") for piece in pieces)
    assert chunks("x" * 1200, 500) == ["x" * 500, "x" * 500, "x" * 200]
    assert chunks("  ") == []
    assert chunks("One.\n\nTwo.   Three.", 8) == ["One.", "Two.", "Three."]


@pytest.mark.parametrize("body", [b"<html>busy</html>", b"[]", b'{"error": {"code": "X"}}'])
def test_a_body_without_results_is_refused(body: bytes) -> None:
    with pytest.raises(OpenFdaError):
        require_results(body)


async def test_fetch_reads_approvals_and_labels_of_the_targets_analogs(tmp_path: Path) -> None:
    server = Fda()

    evidence = await connector(tmp_path, server).fetch(query(), TODAY)

    assert {"fda:NDA214665:ORIG1", "fda:NDA216340:ORIG1"} <= keys(evidence)
    assert any("LUMAKRAS" in e.source for e in evidence)
    assert any("KRAZATI" in e.source for e in evidence)
    assert {e.source_family for e in evidence} == {ANALOG_FAMILY}
    assert len({e.id for e in evidence}) == len(evidence)


async def test_the_asset_itself_is_not_its_own_analog(tmp_path: Path) -> None:
    asked = query(known_assets=["sotorasib"], assets=[Asset(name="SOTORASIB")])

    evidence = await connector(tmp_path, Fda()).fetch(asked, TODAY)

    assert evidence and not any("LUMAKRAS" in e.source for e in evidence)


async def test_a_replayed_run_sees_only_what_was_approved_by_then(tmp_path: Path) -> None:
    evidence = await connector(tmp_path, Fda()).fetch(query(), date(2022, 6, 30))

    assert keys(evidence) == {"fda:NDA214665:ORIG1"}  # no adagrasib, no supplement, no label


async def test_nothing_is_read_without_a_target_id(tmp_path: Path) -> None:
    server = Fda()
    asked = ResolverOutput(indication=Indication(name="NSCLC"), targets=[Target(symbol="KRAS")])

    assert await connector(tmp_path, server).fetch(asked, TODAY) == []
    assert server.asked == []


async def test_no_match_is_an_empty_answer_not_a_problem(tmp_path: Path) -> None:
    fda = connector(tmp_path, Fda(failing="adagrasib", status=404))

    evidence = await fda.fetch(query(), TODAY)

    assert fda.problems == []
    assert evidence and not any("KRAZATI" in e.source for e in evidence)


async def test_a_failed_request_is_named_and_the_rest_is_kept(tmp_path: Path) -> None:
    fda = connector(tmp_path, Fda(failing="label", status=503))

    evidence = await fda.fetch(query(), TODAY)

    assert sorted(fda.problems) == [
        "openFDA label of ADAGRASIB could not be read",
        "openFDA label of SOTORASIB could not be read",
    ]
    assert evidence and all(e.status_key for e in evidence)  # approvals only


async def test_an_error_page_is_a_problem_and_is_not_cached(tmp_path: Path) -> None:
    server = Fda(failing="drugsfda", body=b"<html>maintenance</html>")
    fda = connector(tmp_path, server)

    await fda.fetch(query(), TODAY)
    asked_once = len(server.asked)
    await fda.fetch(query(), TODAY)

    assert "openFDA drugsfda of SOTORASIB could not be read" in fda.problems
    retried = [r for r in server.asked[asked_once:] if "drugsfda" in r.url.path]
    assert len(retried) == 2  # both analogs asked again: the bad body was never stored


async def test_the_key_travels_in_a_header_and_never_in_the_address(tmp_path: Path) -> None:
    server = Fda()

    await connector(tmp_path, server, api_key="secret-key").fetch(query(), TODAY)

    fda = [r for r in server.asked if "fda.gov" in r.url.host]
    assert fda and all(r.headers["authorization"].startswith("Basic ") for r in fda)
    assert not any("secret-key" in str(r.url) for r in fda)


async def test_an_answer_cached_with_a_key_is_found_without_one(tmp_path: Path) -> None:
    server = Fda()
    await connector(tmp_path, server, api_key="secret-key").fetch(query(), TODAY)
    asked = len(server.asked)

    await connector(tmp_path, server).fetch(query(), TODAY)

    assert len(server.asked) == asked
