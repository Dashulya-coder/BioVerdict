from datetime import UTC, date, datetime

from bioverdict.store.as_of import filter_as_of, is_visible_as_of
from bioverdict.store.models import Evidence, EvidenceLevel, SourceKind


def make_evidence(
    eid: str,
    published_at: date | None,
    retrieved_at: datetime = datetime(2026, 10, 6, tzinfo=UTC),
) -> Evidence:
    return Evidence(
        id=eid,
        source="ClinicalTrials.gov",
        source_family="registry",
        source_kind=SourceKind.REGISTRY,
        url="https://clinicaltrials.gov/study/NCT00000000",
        excerpt="text",
        published_at=published_at,
        retrieved_at=retrieved_at,
        level=EvidenceLevel.HUMAN_INTERVENTIONAL,
        independence_group="sponsor:test",
        version=1,
    )


def test_later_evidence_is_hidden() -> None:
    assert not is_visible_as_of(make_evidence("E-1", date(2026, 7, 2)), date(2026, 6, 30))


def test_cutoff_date_is_inclusive() -> None:
    assert is_visible_as_of(make_evidence("E-1", date(2026, 7, 2)), date(2026, 7, 2))


def test_earlier_evidence_is_visible() -> None:
    assert is_visible_as_of(make_evidence("E-1", date(2024, 1, 1)), date(2026, 7, 2))


def test_undated_snapshot_is_visible_once_it_was_retrieved() -> None:
    snapshot = make_evidence("E-1", None, retrieved_at=datetime(2026, 10, 6, 23, 59, tzinfo=UTC))
    assert is_visible_as_of(snapshot, date(2026, 10, 6))
    assert is_visible_as_of(snapshot, date(2027, 1, 1))


def test_undated_snapshot_is_hidden_before_it_was_retrieved() -> None:
    snapshot = make_evidence("E-1", None, retrieved_at=datetime(2026, 10, 6, tzinfo=UTC))
    assert not is_visible_as_of(snapshot, date(2026, 10, 5))


def test_filter_keeps_order_and_drops_only_later_items() -> None:
    items = [
        make_evidence("E-1", date(2026, 7, 2)),
        make_evidence("E-2", date(2024, 1, 1)),
        make_evidence("E-3", None, retrieved_at=datetime(2024, 5, 1, tzinfo=UTC)),
        make_evidence("E-4", None, retrieved_at=datetime(2026, 5, 1, tzinfo=UTC)),
    ]
    kept = filter_as_of(items, date(2025, 1, 1))
    assert [e.id for e in kept] == ["E-2", "E-3"]
