"""The biomarker fraction: read from a recorded real cohort, applied to the market size."""

import json
import math
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from bioverdict.connectors.biomarker import (
    FAMILY,
    BiomarkerFrequencyConnector,
    count_patients,
    named_variant,
)
from bioverdict.connectors.epidemiology import CancerIncidenceConnector
from bioverdict.connectors.http import CachedHttpClient
from bioverdict.contracts import Connector
from bioverdict.market.tam import estimate_market, wilson_interval
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

from .sources import Sources, make_http
from .test_market import bundle

RAW = Path(__file__).parents[3] / "fixtures" / "raw" / "biomarker"
SAMPLES = json.loads((RAW / "samples_nsclc.json").read_text())
MUTATIONS = json.loads((RAW / "mutations_kras_nsclc.json").read_text())
TODAY = datetime.now(UTC).date()
NSCLC = Indication(name="non-small cell lung carcinoma", mondo_id="MONDO_0005233")
KRAS = Target(symbol="KRAS", ensembl="ENSG00000133703")
QUERY = ResolverOutput(indication=NSCLC, targets=[KRAS], known_assets=["divarasib"])
CARRIERS, PATIENTS = 194, 1567  # KRAS G12C among the cohort's non-small cell lung patients


def registry_record(text: str, number: int = 1) -> Evidence:
    return Evidence(
        id=f"NCT{number}:summary",
        source="ClinicalTrials.gov",
        source_family="registry",
        source_kind=SourceKind.REGISTRY,
        url=f"https://clinicaltrials.gov/study/NCT{number}",
        excerpt=text,
        retrieved_at=datetime(2026, 10, 9, tzinfo=UTC),
        level=EvidenceLevel.REGISTRY_RECORD,
        independence_group="sponsor:Roche",
        version=1,
    )


G12C = [
    registry_record("divarasib in participants with KRAS G12C-positive advanced NSCLC", 1),
    registry_record("KRAS p.G12C mutation confirmed by a validated test", 2),
]


class Registry:
    name = "clinicaltrials"

    def __init__(self, records: list[Evidence]) -> None:
        self.records = records

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        return self.records


class Portal:
    """cBioPortal answering from the recordings."""

    def __init__(self, mutations: list[dict] | None = None) -> None:
        self.mutations = MUTATIONS if mutations is None else mutations
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        path = request.url.path
        if "/genes/" in path:
            return httpx.Response(200, content=(RAW / "gene_kras.json").read_bytes())
        if path.endswith("/clinical-data"):
            return httpx.Response(200, json=SAMPLES)
        if path.endswith("/mutations/fetch"):
            return httpx.Response(200, json=self.mutations)
        return httpx.Response(200, content=(RAW / "study.json").read_bytes())


def connector(tmp_path: Path, portal: Portal, records: list[Evidence]):
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = connect(tmp_path / "portal.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(portal))
    http = CachedHttpClient(client, HttpCache(conn), wait=wait_none())
    return BiomarkerFrequencyConnector(http, Registry(records))  # type: ignore[arg-type]


def test_it_is_a_connector(tmp_path: Path) -> None:
    assert isinstance(connector(tmp_path, Portal(), G12C), Connector)


def test_the_variant_is_the_one_the_registry_records_name() -> None:
    assert named_variant(G12C, ["KRAS"]) == ("KRAS", "G12C", 2)
    assert named_variant([registry_record("KRASG12C and KRAS-G12C in one record")], ["KRAS"]) == (
        "KRAS",
        "G12C",
        1,
    )


def test_no_variant_is_chosen_when_none_or_several_are_named_alike() -> None:
    pan = [registry_record("KRAS G12D, KRAS G12V or KRAS G12C mutations")]

    assert named_variant(pan, ["KRAS"]) is None
    assert named_variant([registry_record("KRAS-mutant tumours; PD-L1 TPS 50")], ["KRAS"]) is None
    assert named_variant(G12C, ["EGFR"]) is None  # another gene's variant is not this target's


def test_a_patient_with_several_samples_is_counted_once() -> None:
    samples = [
        {"sampleId": "S1", "patientId": "P1", "value": "Lung"},
        {"sampleId": "S2", "patientId": "P1", "value": "Lung"},
        {"sampleId": "S3", "patientId": "P2", "value": "Lung"},
        {"sampleId": "S4", "patientId": "P3", "value": "Other"},
    ]
    mutations = [
        {"sampleId": "S1", "proteinChange": "G12C"},
        {"sampleId": "S2", "proteinChange": "G12C"},
        {"sampleId": "S3", "proteinChange": "G12D"},
        {"sampleId": "S4", "proteinChange": "G12C"},  # another cancer type
    ]

    assert count_patients(samples, mutations, "Lung", "G12C") == (1, 2)


async def test_the_record_holds_counts_from_the_cohort_and_says_how_they_were_made(
    tmp_path: Path,
) -> None:
    (record,) = await connector(tmp_path, Portal(), G12C).fetch(QUERY, TODAY)

    fragment = json.loads(record.excerpt)
    assert (fragment["gene"], fragment["protein_change"]) == ("KRAS", "G12C")
    assert (fragment["patients_with_variant"], fragment["patients_sequenced"]) == (
        CARRIERS,
        PATIENTS,
    )
    assert fragment["pmid"] == "28481359" and "by code" in fragment["counted"]
    assert record.source_family == FAMILY and record.status_key is not None
    assert record.url == "https://www.cbioportal.org/study/summary?id=msk_impact_2017"


@pytest.mark.parametrize(
    "asked",
    [
        QUERY.model_copy(update={"known_assets": []}),  # a class of drugs has no one variant
        QUERY.model_copy(update={"indication": Indication(name="asthma", mondo_id="MONDO_1")}),
        QUERY.model_copy(update={"indication": Indication(name="NSCLC")}),  # no disease id
    ],
)
async def test_nothing_is_asked_without_an_asset_or_a_covered_cancer(
    tmp_path: Path, asked: ResolverOutput
) -> None:
    portal = Portal()

    assert await connector(tmp_path, portal, G12C).fetch(asked, TODAY) == []
    assert portal.asked == []


async def test_no_clear_variant_or_a_gene_the_cohort_does_not_show_gives_nothing(
    tmp_path: Path,
) -> None:
    unclear = [registry_record("KRAS-mutant tumours")]

    assert await connector(tmp_path, Portal(), unclear).fetch(QUERY, TODAY) == []
    assert await connector(tmp_path / "b", Portal(mutations=[]), G12C).fetch(QUERY, TODAY) == []


def test_the_interval_of_a_proportion_stays_inside_zero_and_one() -> None:
    low, high = wilson_interval(CARRIERS, PATIENTS)

    assert low < CARRIERS / PATIENTS < high and high - low < 0.04
    assert wilson_interval(0, 50)[0] == 0.0 and wilson_interval(0, 50)[1] > 0
    assert wilson_interval(50, 50)[1] == 1.0


async def market(tmp_path: Path, with_biomarker: bool):
    evidence = await CancerIncidenceConnector(make_http(tmp_path / "m", Sources())).fetch(
        QUERY, TODAY
    )
    if with_biomarker:
        evidence += await connector(tmp_path / "p", Portal(), G12C).fetch(QUERY, TODAY)
    return estimate_market(bundle(evidence))


async def test_new_cases_are_narrowed_to_the_patients_with_the_variant(tmp_path: Path) -> None:
    every_case = await market(tmp_path / "a", with_biomarker=False)
    with_variant = await market(tmp_path / "b", with_biomarker=True)

    assert every_case.patients is not None and with_variant.patients is not None
    share = CARRIERS / PATIENTS
    assert math.isclose(with_variant.patients.p50, every_case.patients.p50 * share)
    assert with_variant.patients.p10 < with_variant.patients.p50 < with_variant.patients.p90
    assert with_variant.patients.p90 < every_case.patients.p10  # about an eighth of the cases
    assert with_variant.patients_basis == "new cases a year in the United States with KRAS G12C"
    text = " ".join(with_variant.assumptions)
    assert "194 of 1567 patients (12.4%" in text and "MSK-IMPACT" in text
    assert "one cancer centre" in text and "no biomarker" not in text
    assert len(with_variant.evidence_ids) == len(every_case.evidence_ids) + 1


async def test_without_the_record_the_estimate_still_says_no_fraction_was_applied(
    tmp_path: Path,
) -> None:
    every_case = await market(tmp_path, with_biomarker=False)

    assert "no biomarker, stage or line-of-therapy fraction is applied" in every_case.assumptions[0]
