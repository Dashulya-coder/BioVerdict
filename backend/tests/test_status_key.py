from datetime import UTC, datetime

from bioverdict.store.models import Evidence, EvidenceLevel, SourceKind


def make_evidence(**overrides) -> Evidence:
    fields = {
        "id": "E-0001",
        "source": "ClinicalTrials.gov",
        "source_family": "registry",
        "source_kind": SourceKind.REGISTRY,
        "url": "https://clinicaltrials.gov/study/NCT06497556",
        "excerpt": "ACTIVE_NOT_RECRUITING",
        "retrieved_at": datetime(2026, 10, 6, tzinfo=UTC),
        "level": EvidenceLevel.HUMAN_INTERVENTIONAL,
        "independence_group": "sponsor:Roche",
        "version": 1,
    }
    return Evidence(**{**fields, **overrides})


def test_status_key_defaults_to_none() -> None:
    assert make_evidence().status_key is None


def test_status_key_round_trips_through_json() -> None:
    key = "nct:NCT06497556:overall_status"
    restored = Evidence.model_validate_json(make_evidence(status_key=key).model_dump_json())
    assert restored.status_key == key
