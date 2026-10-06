from datetime import UTC, datetime

import pytest

from bioverdict.store.evidence_ids import assign_ids
from bioverdict.store.models import Evidence, EvidenceLevel, Locator, SourceKind


def make_evidence(url: str, excerpt: str = "text", eid: str = "tmp", **overrides) -> Evidence:
    fields = {
        "id": eid,
        "source": "ClinicalTrials.gov",
        "source_family": "registry",
        "source_kind": SourceKind.REGISTRY,
        "url": url,
        "excerpt": excerpt,
        "retrieved_at": datetime(2026, 10, 6, tzinfo=UTC),
        "level": EvidenceLevel.HUMAN_INTERVENTIONAL,
        "independence_group": "sponsor:test",
        "version": 1,
    }
    return Evidence(**{**fields, **overrides})


def test_ids_are_sequential_in_content_order() -> None:
    b, a = make_evidence("https://b.org"), make_evidence("https://a.org")
    result = assign_ids([], [b, a], version=1)
    assert [(e.id, e.url) for e in result] == [
        ("E-0001", "https://a.org"),
        ("E-0002", "https://b.org"),
    ]


def test_input_order_does_not_matter() -> None:
    items = [make_evidence(f"https://{name}.org") for name in "cab"]
    forward = assign_ids([], items, version=1)
    backward = assign_ids([], list(reversed(items)), version=1)
    assert [(e.id, e.url) for e in forward] == [(e.id, e.url) for e in backward]


def test_repeats_inside_incoming_are_collapsed() -> None:
    twice = [make_evidence("https://a.org"), make_evidence("https://a.org")]
    assert len(assign_ids([], twice, version=1)) == 1


def test_duplicate_resolution_is_deterministic() -> None:
    from_registry = make_evidence("https://a.org", source="ClinicalTrials.gov")
    from_search = make_evidence("https://a.org", source="Tavily")
    first = assign_ids([], [from_registry, from_search], version=1)
    second = assign_ids([], [from_search, from_registry], version=1)
    assert first[0].source == second[0].source


def test_locator_is_part_of_the_identity() -> None:
    one = make_evidence("https://a.org", locator=Locator(type="nct", value="NCT1"))
    two = make_evidence("https://a.org", locator=Locator(type="nct", value="NCT2"))
    assert len(assign_ids([], [one, two], version=1)) == 2


def test_existing_evidence_is_skipped_and_numbering_continues() -> None:
    old = make_evidence("https://a.org", eid="E-0007")
    result = assign_ids([old], [make_evidence("https://a.org"), make_evidence("https://z.org")], 2)
    assert [(e.id, e.url, e.version) for e in result] == [("E-0008", "https://z.org", 2)]


def test_changed_excerpt_is_new_evidence() -> None:
    old = make_evidence("https://a.org", "status: recruiting", eid="E-0001")
    result = assign_ids([old], [make_evidence("https://a.org", "status: completed")], version=2)
    assert [e.id for e in result] == ["E-0002"]


def test_version_is_set_on_new_evidence() -> None:
    assert assign_ids([], [make_evidence("https://a.org")], version=3)[0].version == 3


def test_non_canonical_existing_id_is_rejected() -> None:
    with pytest.raises(ValueError):
        assign_ids([make_evidence("https://a.org", eid="weird")], [], version=2)
