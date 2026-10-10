import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from bioverdict.connectors.clinicaltrials import parse_ct_date, parse_study
from bioverdict.store.models import EvidenceLevel

RAW = Path(__file__).parents[3] / "fixtures" / "raw" / "clinicaltrials"
NOW = datetime(2026, 10, 7, tzinfo=UTC)


def studies(name: str) -> list[dict]:
    return json.loads((RAW / name).read_text(encoding="utf-8"))["studies"]


DIVARASIB = studies("search_divarasib.json")
TERMINATED = studies("search_terminated.json")


def by_part(evidence: list, part: str) -> list:
    return [e for e in evidence if e.id.endswith(f":{part}")]


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2024-07-11", date(2024, 7, 11)),
        ("2024-07", date(2024, 7, 31)),
        ("2024-02", date(2024, 2, 29)),
        ("2024", date(2024, 12, 31)),
        (None, None),
        ("", None),
    ],
)
def test_ct_date_parsing_never_dates_a_record_earlier_than_it_may_be(value, expected) -> None:
    assert parse_ct_date(value) == expected


@pytest.mark.parametrize(
    "study", DIVARASIB, ids=lambda s: s["protocolSection"]["identificationModule"]["nctId"]
)
def test_each_study_yields_summary_outcomes_status_and_design(study: dict) -> None:
    evidence = parse_study(study, NOW)
    parts = {e.id.split(":", 1)[1] for e in evidence}
    assert {"summary", "primary-outcome-1", "status", "design"} <= parts


def test_only_status_and_design_carry_a_status_key() -> None:
    nct = DIVARASIB[0]["protocolSection"]["identificationModule"]["nctId"]
    for item in parse_study(DIVARASIB[0], NOW):
        part = item.id.split(":", 1)[1]
        if part in ("status", "design"):
            assert (
                item.status_key == f"nct:{nct}:{'overall_status' if part == 'status' else 'design'}"
            )
        else:
            assert item.status_key is None


@pytest.mark.parametrize(
    "study",
    DIVARASIB + TERMINATED,
    ids=lambda s: s["protocolSection"]["identificationModule"]["nctId"],
)
def test_every_status_evidence_has_a_status_key(study: dict) -> None:
    status = by_part(parse_study(study, NOW), "status")
    assert status and all(item.status_key for item in status)


@pytest.mark.parametrize(
    "study",
    DIVARASIB + TERMINATED,
    ids=lambda s: s["protocolSection"]["identificationModule"]["nctId"],
)
def test_excerpts_are_verbatim_from_the_record(study: dict) -> None:
    protocol = study["protocolSection"]
    for item in parse_study(study, NOW):
        part = item.id.split(":", 1)[1]
        if part == "summary":
            assert item.excerpt == protocol["descriptionModule"]["briefSummary"]
        elif part.startswith("primary-outcome"):
            number = int(part.rsplit("-", 1)[1]) - 1
            assert json.loads(item.excerpt) == protocol["outcomesModule"]["primaryOutcomes"][number]
        else:
            module = protocol["statusModule" if part == "status" else "designModule"]
            for key, value in json.loads(item.excerpt).items():
                assert module[key] == value


def test_dates_follow_the_record() -> None:
    evidence = parse_study(DIVARASIB[0], NOW)
    status_module = DIVARASIB[0]["protocolSection"]["statusModule"]
    posted = date.fromisoformat(status_module["studyFirstPostDateStruct"]["date"])
    updated = date.fromisoformat(status_module["lastUpdatePostDateStruct"]["date"])
    assert posted < updated
    assert by_part(evidence, "status")[0].published_at == updated
    # The registry gives the current wording only, so no part is dated before the last update:
    # a run replayed between the two dates must not read text that may have been written later.
    assert {item.published_at for item in evidence} == {updated}


def test_a_record_without_an_update_date_falls_back_to_its_first_posting() -> None:
    study = json.loads(json.dumps(DIVARASIB[0]))
    status_module = study["protocolSection"]["statusModule"]
    del status_module["lastUpdatePostDateStruct"]
    posted = date.fromisoformat(status_module["studyFirstPostDateStruct"]["date"])

    assert by_part(parse_study(study, NOW), "summary")[0].published_at == posted


def test_reason_for_stopping_is_part_of_the_status() -> None:
    futility = next(
        s for s in TERMINATED if s["protocolSection"]["statusModule"]["whyStopped"] == "Futility"
    )
    status = by_part(parse_study(futility, NOW), "status")[0]
    assert json.loads(status.excerpt)["whyStopped"] == "Futility"
    assert json.loads(status.excerpt)["overallStatus"] == "TERMINATED"


def test_level_source_and_sponsor() -> None:
    for item in parse_study(DIVARASIB[0], NOW):
        assert item.level is EvidenceLevel.REGISTRY_RECORD
        assert (item.source, item.source_family) == ("ClinicalTrials.gov", "registry")
        assert item.independence_group == "sponsor:Roche"
        assert item.url.startswith("https://clinicaltrials.gov/study/NCT")
        assert item.locator and item.locator.type == "nct"


def test_a_protocol_is_never_treated_as_a_finding() -> None:
    """Interventional or not, a registry record says a study exists, not what it found."""
    levels = {e.level for study in DIVARASIB + TERMINATED for e in parse_study(study, NOW)}
    assert levels == {EvidenceLevel.REGISTRY_RECORD}

    observational = json.loads(json.dumps(DIVARASIB[0]))
    observational["protocolSection"]["designModule"]["studyType"] = "OBSERVATIONAL"
    assert {e.level for e in parse_study(observational, NOW)} == {EvidenceLevel.REGISTRY_RECORD}


def test_missing_parts_are_skipped() -> None:
    study = json.loads(json.dumps(DIVARASIB[0]))
    del study["protocolSection"]["outcomesModule"]
    del study["protocolSection"]["descriptionModule"]
    parts = {e.id.split(":", 1)[1] for e in parse_study(study, NOW)}
    assert parts == {"status", "design"}


def test_placeholder_ids_are_unique_within_a_study() -> None:
    ids = [e.id for e in parse_study(DIVARASIB[0], NOW)]
    assert len(ids) == len(set(ids))


def test_sponsors_of_one_company_share_a_group() -> None:
    roche = {item.independence_group for study in DIVARASIB for item in parse_study(study, NOW)}
    assert roche == {"sponsor:Roche"}


def test_design_keeps_experimental_drug_and_comparator_roles_verbatim() -> None:
    study = json.loads(json.dumps(DIVARASIB[0]))
    arms = {
        "armGroups": [
            {"label": "A", "type": "EXPERIMENTAL"},
            {"label": "B", "type": "ACTIVE_COMPARATOR"},
        ],
        "interventions": [
            {"name": "Synthetic candidate", "type": "DRUG", "armGroupLabels": ["A"]},
            {"name": "Synthetic comparator", "type": "DRUG", "armGroupLabels": ["B"]},
        ],
    }
    study["protocolSection"]["armsInterventionsModule"] = arms
    [design] = by_part(parse_study(study, NOW), "design")
    parsed = json.loads(design.excerpt)
    assert parsed["armGroups"] == arms["armGroups"]
    assert parsed["interventions"] == arms["interventions"]
    assert design.level is EvidenceLevel.REGISTRY_RECORD
