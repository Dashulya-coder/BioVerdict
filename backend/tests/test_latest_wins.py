from datetime import UTC, date, datetime

from bioverdict.store.as_of import filter_as_of
from bioverdict.store.latest_wins import drop_superseded
from bioverdict.store.models import Evidence, EvidenceLevel, SourceKind

STATUS = "nct:NCT06497556:overall_status"


def make_evidence(eid: str, published_at: date | None, **overrides) -> Evidence:
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


def test_items_without_status_key_are_never_dropped() -> None:
    summary = make_evidence("E-0001", date(2024, 7, 11))
    endpoint = make_evidence("E-0002", date(2024, 7, 11))
    assert ids(drop_superseded([summary, endpoint])) == ["E-0001", "E-0002"]


def test_newest_status_replaces_older_ones() -> None:
    old = make_evidence("E-0001", date(2025, 1, 1), status_key=STATUS)
    new = make_evidence("E-0002", date(2026, 9, 16), status_key=STATUS)
    assert ids(drop_superseded([old, new])) == ["E-0002"]
    assert ids(drop_superseded([new, old])) == ["E-0002"]


def test_other_facts_on_the_same_record_are_kept() -> None:
    summary = make_evidence("E-0001", date(2024, 7, 11))
    old = make_evidence("E-0002", date(2025, 1, 1), status_key=STATUS)
    new = make_evidence("E-0003", date(2026, 9, 16), status_key=STATUS)
    assert ids(drop_superseded([summary, old, new])) == ["E-0001", "E-0003"]


def test_different_keys_do_not_interact() -> None:
    a = make_evidence("E-0001", date(2025, 1, 1), status_key="nct:A:overall_status")
    b = make_evidence("E-0002", date(2024, 1, 1), status_key="nct:B:overall_status")
    assert ids(drop_superseded([a, b])) == ["E-0001", "E-0002"]


def test_undated_status_is_ranked_by_retrieval_date() -> None:
    dated = make_evidence("E-0001", date(2026, 1, 1), status_key=STATUS)
    snapshot = make_evidence("E-0002", None, status_key=STATUS)  # retrieved 2026-10-06
    assert ids(drop_superseded([dated, snapshot])) == ["E-0002"]


def test_same_date_resolves_by_retrieval_time_then_id() -> None:
    first = make_evidence("E-0001", date(2026, 1, 1), status_key=STATUS)
    later = make_evidence(
        "E-0002",
        date(2026, 1, 1),
        status_key=STATUS,
        retrieved_at=datetime(2026, 10, 7, tzinfo=UTC),
    )
    assert ids(drop_superseded([first, later])) == ["E-0002"]
    tie_a = make_evidence("E-0003", date(2026, 1, 1), status_key=STATUS)
    tie_b = make_evidence("E-0004", date(2026, 1, 1), status_key=STATUS)
    assert ids(drop_superseded([tie_b, tie_a])) == ["E-0004"]


def test_input_is_not_modified() -> None:
    items = [
        make_evidence("E-0001", date(2025, 1, 1), status_key=STATUS),
        make_evidence("E-0002", date(2026, 1, 1), status_key=STATUS),
    ]
    drop_superseded(items)
    assert ids(items) == ["E-0001", "E-0002"]


def test_as_of_must_be_applied_before_superseding() -> None:
    old = make_evidence("E-0001", date(2025, 1, 1), status_key=STATUS)
    new = make_evidence("E-0002", date(2026, 9, 16), status_key=STATUS)
    as_of = date(2025, 6, 1)

    right = drop_superseded(filter_as_of([old, new], as_of))
    wrong = filter_as_of(drop_superseded([old, new]), as_of)

    assert ids(right) == ["E-0001"]  # the status known on the analysis date
    assert ids(wrong) == []  # the future status erased it: why the order matters
