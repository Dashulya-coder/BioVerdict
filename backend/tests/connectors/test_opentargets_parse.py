import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bioverdict.connectors.opentargets import (
    DATATYPE_LEVEL,
    parse_associations,
    parse_drug,
    pick_drug,
)
from bioverdict.store.models import EvidenceLevel

RAW = Path(__file__).parents[3] / "fixtures" / "raw"
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def load(path: str) -> dict:
    return json.loads((RAW / path).read_text(encoding="utf-8"))


SEARCH = load("opentargets/search_divarasib.json")
DRUG = load("divarasib/opentargets_drug.json")
KRAS_NSCLC = load("divarasib/opentargets_assoc.json")
PCSK9_CAD = load("opentargets/assoc_pcsk9_cad.json")


def by_datatype(evidence: list) -> dict:
    return {json.loads(e.excerpt)["datatype"]: e for e in evidence}


def test_the_exact_drug_name_wins_over_a_similar_one() -> None:
    assert pick_drug(SEARCH, "divarasib") == "CHEMBL5095236"
    assert pick_drug(SEARCH, "  DIVARASIB ") == "CHEMBL5095236"
    assert pick_drug(SEARCH, "divarasib adipate") == "CHEMBL5314604"


def test_a_partial_or_unknown_name_matches_nothing() -> None:
    assert pick_drug(SEARCH, "divara") is None
    assert pick_drug(load("opentargets/search_none.json"), "zzzznotadrug") is None


def test_drug_yields_one_clinical_stage_record() -> None:
    [item] = parse_drug(DRUG, NOW, disease_id="MONDO_0005233")

    fragment = json.loads(item.excerpt)
    assert fragment["maximumClinicalStage"] == "PHASE_3"
    assert fragment["indication"]["disease"]["id"] == "MONDO_0005233"
    assert fragment["indication"]["maxClinicalStage"] == "PHASE_3"
    assert item.level is EvidenceLevel.REGISTRY_RECORD
    assert item.status_key == "chembl:CHEMBL5095236:clinical_stage"
    assert item.published_at is None and item.retrieved_at == NOW


def test_the_indication_is_added_only_for_a_disease_the_drug_has() -> None:
    assert "indication" not in json.loads(parse_drug(DRUG, NOW)[0].excerpt)
    other = parse_drug(DRUG, NOW, disease_id="MONDO_0000001")
    assert "indication" not in json.loads(other[0].excerpt)


def test_an_unknown_drug_yields_nothing() -> None:
    assert parse_drug({"data": {"drug": None}}, NOW) == []


def test_each_data_type_becomes_its_own_evidence_with_a_level_for_what_it_is() -> None:
    found = by_datatype(parse_associations(KRAS_NSCLC, NOW))

    assert set(found) == {"clinical", "affected_pathway", "somatic_mutation", "animal_model"}
    assert found["somatic_mutation"].level is EvidenceLevel.HUMAN_OBSERVATIONAL
    assert found["animal_model"].level is EvidenceLevel.ANIMAL_IN_VIVO
    assert found["affected_pathway"].level is EvidenceLevel.IN_VITRO
    assert found["clinical"].level is EvidenceLevel.REGISTRY_RECORD


def test_germline_genetics_is_human_genetics() -> None:
    found = by_datatype(parse_associations(PCSK9_CAD, NOW))
    assert found["genetic_association"].level is EvidenceLevel.HUMAN_GENETICS


def test_text_mining_of_papers_is_left_to_the_literature_connector() -> None:
    assert "literature" not in by_datatype(parse_associations(KRAS_NSCLC, NOW))
    assert "literature" not in DATATYPE_LEVEL


def test_scores_are_copied_exactly() -> None:
    source = {
        d["id"]: d["score"]
        for d in KRAS_NSCLC["data"]["disease"]["associatedTargets"]["rows"][0]["datatypeScores"]
    }
    for datatype, item in by_datatype(parse_associations(KRAS_NSCLC, NOW)).items():
        assert json.loads(item.excerpt)["score"] == source[datatype]


def test_every_record_can_be_superseded_by_a_later_snapshot() -> None:
    items = parse_associations(KRAS_NSCLC, NOW) + parse_drug(DRUG, NOW)
    assert all(item.status_key for item in items)
    assert len({item.status_key for item in items}) == len(items)
    assert len({item.id for item in items}) == len(items)


def test_independent_data_types_do_not_share_an_independence_group() -> None:
    groups = {e.independence_group for e in parse_associations(KRAS_NSCLC, NOW)}
    assert len(groups) == len(parse_associations(KRAS_NSCLC, NOW))


@pytest.mark.parametrize(
    "response",
    [
        {"data": {"disease": None}},  # an unknown or retired disease id
        load("opentargets/assoc_no_row.json"),  # a target with no association to the disease
        {"data": None},
    ],
)
def test_missing_associations_yield_nothing(response: dict) -> None:
    assert parse_associations(response, NOW) == []
