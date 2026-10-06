from datetime import UTC, date, datetime

import pytest

from bioverdict.store.bundle import compute_content_hash
from bioverdict.store.models import (
    Evidence,
    EvidenceLevel,
    Section,
    SectionStatus,
    SourceKind,
)

STATUSES = {Section.CLINICAL: SectionStatus.FOUND}


def make_evidence(eid: str = "E-0001", **overrides) -> Evidence:
    fields = {
        "id": eid,
        "source": "ClinicalTrials.gov",
        "source_family": "registry",
        "source_kind": SourceKind.REGISTRY,
        "url": "https://clinicaltrials.gov/study/NCT06497556",
        "excerpt": "Phase 3, randomized",
        "published_at": date(2024, 7, 11),
        "retrieved_at": datetime(2026, 10, 6, 10, 0, tzinfo=UTC),
        "level": EvidenceLevel.HUMAN_INTERVENTIONAL,
        "independence_group": "sponsor:Roche",
        "version": 1,
    }
    return Evidence(**{**fields, **overrides})


def test_hash_has_sha256_prefix_and_is_deterministic() -> None:
    first = compute_content_hash([make_evidence()], STATUSES)
    assert first.startswith("sha256:") and len(first) == len("sha256:") + 64
    assert first == compute_content_hash([make_evidence()], STATUSES)


def test_fetch_time_and_store_version_do_not_change_the_hash() -> None:
    later = make_evidence(retrieved_at=datetime(2026, 10, 7, 9, 30, tzinfo=UTC), version=2)
    assert compute_content_hash([later], STATUSES) == compute_content_hash(
        [make_evidence()], STATUSES
    )


def test_input_order_does_not_change_the_hash() -> None:
    a, b = make_evidence("E-0001"), make_evidence("E-0002", excerpt="other")
    assert compute_content_hash([a, b], STATUSES) == compute_content_hash([b, a], STATUSES)


@pytest.mark.parametrize(
    "change",
    [
        {"excerpt": "Phase 2"},
        {"id": "E-0009"},
        {"url": "https://example.org"},
        {"published_at": date(2025, 1, 1)},
        {"level": EvidenceLevel.IN_VITRO},
        {"source_kind": SourceKind.COMPANY},
        {"independence_group": "sponsor:Other"},
    ],
    ids=lambda c: next(iter(c)),
)
def test_content_changes_change_the_hash(change: dict) -> None:
    base = compute_content_hash([make_evidence()], STATUSES)
    assert compute_content_hash([make_evidence(**change)], STATUSES) != base


def test_section_status_changes_the_hash() -> None:
    searched = compute_content_hash([make_evidence()], {Section.COMPETITION: SectionStatus.FOUND})
    skipped = compute_content_hash(
        [make_evidence()], {Section.COMPETITION: SectionStatus.NOT_SEARCHED}
    )
    assert searched != skipped


def test_adding_evidence_changes_the_hash() -> None:
    one = compute_content_hash([make_evidence("E-0001")], STATUSES)
    two = compute_content_hash([make_evidence("E-0001"), make_evidence("E-0002")], STATUSES)
    assert one != two


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValueError):
        compute_content_hash([make_evidence("E-0001"), make_evidence("E-0001")], STATUSES)
