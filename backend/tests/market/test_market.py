"""Market sources and the market size computed from them, on recorded real answers."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from bioverdict.connectors.epidemiology import (
    CancerIncidenceConnector,
    CdcIndicatorsConnector,
    OrphanetConnector,
    PopulationConnector,
)
from bioverdict.connectors.pricing import AnalogPricingConnector, latest_year
from bioverdict.contracts import Connector
from bioverdict.market.tam import estimate_market
from bioverdict.store.bundle import compute_content_hash
from bioverdict.store.models import (
    Asset,
    Bundle,
    Evidence,
    EvidenceLevel,
    Indication,
    Range,
    ResolverOutput,
    Target,
)

from .sources import Sources, make_http

TODAY = datetime.now(UTC).date()  # undated records are visible from the day they are downloaded
KRAS = Target(symbol="KRAS", ensembl="ENSG00000133703")
NSCLC = Indication(name="non-small cell lung carcinoma", mondo_id="MONDO_0005233")
OBESITY = Indication(name="obesity disorder", mondo_id="MONDO_0011122")
HAE = Indication(name="hereditary angioedema", mondo_id="MONDO_0019623")
CONNECTORS = (
    AnalogPricingConnector,
    CancerIncidenceConnector,
    CdcIndicatorsConnector,
    OrphanetConnector,
    PopulationConnector,
)


def query(indication: Indication = NSCLC, **fields) -> ResolverOutput:
    return ResolverOutput(indication=indication, targets=[KRAS], **fields)


async def collect(
    tmp_path: Path, asked: ResolverOutput, server: Sources | None = None, as_of=TODAY
):
    http = make_http(tmp_path, server or Sources())
    evidence: list[Evidence] = []
    for connector in CONNECTORS:
        evidence += await connector(http).fetch(asked, as_of)
    return evidence


def bundle(evidence: list[Evidence]) -> Bundle:
    numbered = [e.model_copy(update={"id": f"E-{n:04d}"}) for n, e in enumerate(evidence, 1)]
    return Bundle(
        bundle_id="B-1",
        run_id="R-1",
        version=1,
        as_of=TODAY,
        content_hash=compute_content_hash(numbered, {}),
        catalog=[],
        evidence=numbered,
        section_statuses={},
        created_at=datetime.now(UTC),
    )


def families(evidence: list[Evidence]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in evidence:
        counts[item.source_family] = counts.get(item.source_family, 0) + 1
    return counts


# --- connectors -------------------------------------------------------------------------------


@pytest.mark.parametrize("connector", CONNECTORS)
def test_every_market_source_is_a_connector(tmp_path: Path, connector) -> None:
    assert isinstance(connector(make_http(tmp_path, Sources())), Connector)


async def test_analogs_are_the_drugs_approved_against_the_target_with_their_medicare_spending(
    tmp_path: Path,
) -> None:
    evidence = await AnalogPricingConnector(make_http(tmp_path, Sources())).fetch(query(), TODAY)

    assert families(evidence) == {"approved_analog": 2, "cms_spending": 2}
    analogs = [
        json.loads(e.excerpt)["drug"] for e in evidence if e.source_family == "approved_analog"
    ]
    assert {d["name"] for d in analogs} == {"SOTORASIB", "ADAGRASIB"}
    assert all(d["maximumClinicalStage"] == "APPROVAL" for d in analogs)
    spending = {
        json.loads(e.excerpt)["Brnd_Name"]: json.loads(e.excerpt)
        for e in evidence
        if e.source_family == "cms_spending"
    }
    assert set(spending) == {"Lumakras", "Krazati"}
    lumakras = spending["Lumakras"]
    assert lumakras["program"] == "Medicare Part D" and lumakras["year"] == 2024
    assert lumakras["Avg_Spnd_Per_Bene_2024"] == "98285.425905"  # CMS's own field and digits
    assert not any(key.endswith("_2023") for key in lumakras)


async def test_market_records_are_status_facts_that_no_model_reads(tmp_path: Path) -> None:
    evidence = await collect(tmp_path, query())

    assert evidence and all(e.status_key for e in evidence)
    # Counts and prices are records, not findings: they weigh nothing in a scientific claim.
    assert all(e.level is EvidenceLevel.REGISTRY_RECORD for e in evidence)
    assert {e.url.split("/")[2] for e in evidence} >= {
        "data.cms.gov",
        "statecancerprofiles.cancer.gov",
    }


async def test_the_asset_is_not_its_own_analog(tmp_path: Path) -> None:
    asked = query(known_assets=["Lumakras", "sotorasib"], assets=[Asset(name="SOTORASIB")])

    evidence = await AnalogPricingConnector(make_http(tmp_path, Sources())).fetch(asked, TODAY)

    names = {json.loads(e.excerpt).get("Gnrc_Name", "") for e in evidence}
    assert "Sotorasib" not in names and "Adagrasib" in names


async def test_without_a_target_id_no_analog_is_looked_up(tmp_path: Path) -> None:
    server = Sources()
    asked = ResolverOutput(indication=NSCLC, targets=[Target(symbol="KRAS")])

    assert await AnalogPricingConnector(make_http(tmp_path, server)).fetch(asked, TODAY) == []
    assert server.asked == []


async def test_a_payer_that_is_down_is_named_and_the_analogs_are_kept(tmp_path: Path) -> None:
    connector = AnalogPricingConnector(make_http(tmp_path, Sources("cms.gov")))

    evidence = await connector.fetch(query(), TODAY)

    assert families(evidence) == {"approved_analog": 2}
    assert len(connector.problems) == 4 and "SOTORASIB" in connector.problems[0]
    assert "503" not in "".join(connector.problems)


async def test_each_epidemiology_source_answers_only_for_the_diseases_it_covers(
    tmp_path: Path,
) -> None:
    lung = families(await collect(tmp_path / "a", query(NSCLC)))
    obesity = families(await collect(tmp_path / "b", query(OBESITY)))
    rare = families(await collect(tmp_path / "c", query(HAE)))

    assert lung["cancer_incidence"] == 1 and "cdc_indicator" not in lung
    assert obesity["cdc_indicator"] == 1 and "cancer_incidence" not in obesity
    assert rare["orphanet_prevalence"] == 4 and "cdc_indicator" not in rare


async def test_without_a_resolved_disease_no_epidemiology_is_read(tmp_path: Path) -> None:
    server = Sources()
    asked = query(Indication(name="pancreatic cancer"))
    http = make_http(tmp_path, server)

    for connector in CONNECTORS[1:]:
        assert await connector(http).fetch(asked, TODAY) == []
    assert server.asked == []


async def test_a_run_replayed_before_the_download_sees_no_market_snapshot(tmp_path: Path) -> None:
    evidence = await collect(tmp_path, query(HAE), as_of=date(2026, 1, 1))

    assert evidence == []  # undated snapshots and the 2026-06 Orphanet release are both later


async def test_orphanet_records_carry_the_release_date_and_orphanets_own_fields(
    tmp_path: Path,
) -> None:
    evidence = await OrphanetConnector(make_http(tmp_path, Sources())).fetch(query(HAE), TODAY)

    record = json.loads(evidence[0].excerpt)
    assert evidence[0].published_at == date(2026, 6, 23)
    assert record["OrphaCode"] == "91378" and record["PrevalenceClass"] == "1-9 / 100 000"
    assert evidence[0].url.endswith("/91378")


async def test_a_cancer_report_without_a_national_row_is_an_error_not_a_zero(
    tmp_path: Path,
) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>maintenance</html>")

    server = Sources()
    server.__call__ = broken  # type: ignore[method-assign]
    http = make_http(tmp_path, server)
    http._client = httpx.AsyncClient(transport=httpx.MockTransport(broken))

    with pytest.raises(ValueError, match="no national row"):
        await CancerIncidenceConnector(http).fetch(query(), TODAY)


def test_the_latest_reported_year_is_found_in_both_programs_spellings() -> None:
    assert latest_year({"Avg_Spnd_Per_Bene_2023": "1", "Avg_Spnd_Per_Bene_2024": ""}) == 2023
    assert latest_year({"Avg_Spndng_Per_Bene_2024": "5"}) == 2024
    assert latest_year({"Tot_Benes_2024": "5"}) is None


# --- market size ------------------------------------------------------------------------------


async def test_cancer_market_is_new_cases_times_the_analogs_spending(tmp_path: Path) -> None:
    estimate = estimate_market(bundle(await collect(tmp_path, query(NSCLC))))

    assert estimate.missing == [] and estimate.tam is not None
    assert estimate.patients is not None and estimate.patients.p50 == 225094
    assert estimate.patients_basis == "new cases a year in the United States"
    price = estimate.annual_price_usd
    assert price is not None and (round(price.p10), round(price.p90)) == (66903, 98285)
    tam = estimate.tam.tam_usd
    assert tam.p50 == pytest.approx(225094 * price.p50) and tam.p10 < tam.p50 < tam.p90
    assert 15e9 < tam.p50 < 22e9


async def test_every_number_points_at_the_records_it_was_read_from(tmp_path: Path) -> None:
    frozen = bundle(await collect(tmp_path, query(NSCLC)))

    estimate = estimate_market(frozen)

    used = {frozen.evidence_by_id()[i].source_family for i in estimate.evidence_ids}
    assert used == {"cancer_incidence", "cms_spending"}
    assert estimate.tam is not None and estimate.tam.evidence_ids == estimate.evidence_ids


async def test_the_simplifications_are_stated_with_the_numbers(tmp_path: Path) -> None:
    estimate = estimate_market(bundle(await collect(tmp_path, query(NSCLC))))

    text = " ".join(estimate.assumptions)
    for phrase in (
        "Lung & Bronchus",
        "wider than the indication",
        "before rebates",
        "not a sales forecast",
    ):
        assert phrase in text


async def test_a_common_condition_is_the_measured_share_of_the_adult_population(
    tmp_path: Path,
) -> None:
    estimate = estimate_market(bundle(await collect(tmp_path, query(OBESITY))))

    adults = 220498172 + 62844750
    assert estimate.patients == Range(
        p10=adults * 32.5 / 100, p50=adults * 32.8 / 100, p90=adults * 33.1 / 100
    )
    assert "aged 15 and over" in " ".join(estimate.assumptions)


async def test_a_rare_disease_is_the_bounds_of_its_prevalence_class(tmp_path: Path) -> None:
    estimate = estimate_market(bundle(await collect(tmp_path, query(HAE))))

    people = 341784857
    assert estimate.patients is not None
    assert estimate.patients.p10 == pytest.approx(people * 1 / 100_000)
    assert estimate.patients.p50 == pytest.approx(people * 5 / 100_000)  # Europe: mean 5.0
    assert estimate.patients.p90 == pytest.approx(people * 9 / 100_000)
    assert "Europe" in " ".join(estimate.assumptions)


async def test_one_country_s_prevalence_does_not_stand_for_the_united_states(
    tmp_path: Path,
) -> None:
    evidence = [
        e
        for e in await collect(tmp_path, query(HAE))
        if "Europe" not in e.excerpt  # leaves Denmark, Norway and other single countries
    ]

    estimate = estimate_market(bundle(evidence))

    assert estimate.patients is None and estimate.missing[0].startswith("patients:")


async def test_what_is_missing_is_named_and_nothing_is_filled_in(tmp_path: Path) -> None:
    evidence = await collect(tmp_path, query(NSCLC))
    no_price = [e for e in evidence if e.source_family != "cms_spending"]
    no_patients = [e for e in evidence if e.source_family != "cancer_incidence"]

    without_price = estimate_market(bundle(no_price))
    without_patients = estimate_market(bundle(no_patients))
    nothing = estimate_market(bundle([]))

    assert without_price.tam is None and without_price.patients is not None
    assert without_price.missing == [
        "price: no approved drug against the same target has Medicare spending data"
    ]
    assert without_patients.tam is None and without_patients.annual_price_usd is not None
    assert [m.split(":")[0] for m in nothing.missing] == ["patients", "price"]
    assert nothing.evidence_ids == [] and nothing.assumptions == []


async def test_a_prevalence_without_the_population_is_not_turned_into_patients(
    tmp_path: Path,
) -> None:
    evidence = [
        e for e in await collect(tmp_path, query(OBESITY)) if e.source_family != "population"
    ]

    assert estimate_market(bundle(evidence)).patients is None
