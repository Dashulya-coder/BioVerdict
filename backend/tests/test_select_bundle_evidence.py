from datetime import UTC, date, datetime

from bioverdict.store.bundle import select_bundle_evidence
from bioverdict.store.models import Evidence, EvidenceLevel, SourceKind

STATUS = "nct:NCT06497556:overall_status"


def make_evidence(eid: str, published_at: date, **overrides) -> Evidence:
    fields = {
        "id": eid,
        "source": "ClinicalTrials.gov",
        "source_family": "registry",
        "source_kind": SourceKind.REGISTRY,
        "url": "https://clinicaltrials.gov/study/NCT06497556",
        "excerpt": f"text {eid}",
        "published_at": published_at,
        "retrieved_at": datetime(2026, 10, 6, tzinfo=UTC),
        "level": EvidenceLevel.HUMAN_INTERVENTIONAL,
        "independence_group": "sponsor:Roche",
        "version": 1,
    }
    return Evidence(**{**fields, **overrides})


def ids(items: list[Evidence]) -> list[str]:
    return [e.id for e in items]


def test_status_known_at_the_analysis_date_survives_a_later_one() -> None:
    old = make_evidence("E-0001", date(2025, 1, 1), status_key=STATUS)
    new = make_evidence("E-0002", date(2026, 9, 16), status_key=STATUS)

    assert ids(select_bundle_evidence([old, new], date(2025, 6, 1))) == ["E-0001"]
    assert ids(select_bundle_evidence([old, new], date(2026, 10, 6))) == ["E-0002"]


def test_result_is_sorted_by_id() -> None:
    a = make_evidence("E-0002", date(2024, 1, 1))
    b = make_evidence("E-0001", date(2024, 1, 1))
    assert ids(select_bundle_evidence([a, b], date(2026, 10, 6))) == ["E-0001", "E-0002"]
