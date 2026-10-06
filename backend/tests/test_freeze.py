import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from bioverdict.store.bundle import compute_content_hash
from bioverdict.store.db import connect
from bioverdict.store.evidence_repo import load_evidence
from bioverdict.store.freeze import freeze
from bioverdict.store.migrations import migrate
from bioverdict.store.models import (
    Evidence,
    EvidenceLevel,
    Locator,
    Section,
    SectionStatus,
    SourceKind,
)

RUN = "R-1"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "t.db")
    migrate(connection)
    return connection


def make_evidence(url: str, published_at: date | None = date(2024, 1, 1), **overrides) -> Evidence:
    fields = {
        "id": "tmp",
        "source": "ClinicalTrials.gov",
        "source_family": "registry",
        "source_kind": SourceKind.REGISTRY,
        "url": url,
        "locator": Locator(type="nct", value=url.rsplit("/", 1)[-1]),
        "excerpt": f"text of {url}",
        "published_at": published_at,
        "retrieved_at": datetime(2026, 10, 6, tzinfo=UTC),
        "level": EvidenceLevel.HUMAN_INTERVENTIONAL,
        "independence_group": "sponsor:test",
        "version": 1,
    }
    return Evidence(**{**fields, **overrides})


A = "https://example.org/NCT01"
B = "https://example.org/NCT02"
C = "https://example.org/NCT03"


def test_first_freeze_creates_version_1(conn: sqlite3.Connection) -> None:
    bundle = freeze(conn, RUN, [make_evidence(B), make_evidence(A)], date(2026, 10, 6))

    assert (bundle.version, bundle.bundle_id) == (1, "B-R-1-v1")
    assert [(e.id, e.url) for e in bundle.evidence] == [("E-0001", A), ("E-0002", B)]
    assert bundle.content_hash == compute_content_hash(bundle.evidence, bundle.section_statuses)


def test_catalog_lists_urls_and_locator_values(conn: sqlite3.Connection) -> None:
    bundle = freeze(conn, RUN, [make_evidence(A)], date(2026, 10, 6))
    assert bundle.catalog == sorted([A, "NCT01"])


def test_evidence_after_as_of_is_not_stored(conn: sqlite3.Connection) -> None:
    late = make_evidence(B, published_at=date(2026, 7, 2))
    bundle = freeze(conn, RUN, [make_evidence(A), late], date(2026, 6, 30))

    assert [e.url for e in bundle.evidence] == [A]
    assert [e.url for e in load_evidence(conn, RUN)] == [A]


def test_second_version_keeps_ids_and_adds_new_evidence(conn: sqlite3.Connection) -> None:
    v1 = freeze(conn, RUN, [make_evidence(B)], date(2026, 6, 30))
    v2 = freeze(conn, RUN, [make_evidence(A)], date(2026, 7, 2))

    assert v2.version == 2
    assert [(e.id, e.url) for e in v2.evidence] == [("E-0001", B), ("E-0002", A)]
    assert v2.content_hash != v1.content_hash


def test_freezing_the_same_evidence_again_adds_nothing(conn: sqlite3.Connection) -> None:
    v1 = freeze(conn, RUN, [make_evidence(A)], date(2026, 10, 6))
    v2 = freeze(conn, RUN, [make_evidence(A)], date(2026, 10, 6))

    assert len(load_evidence(conn, RUN)) == 1
    assert v2.version == 2 and v2.content_hash == v1.content_hash


def test_as_of_may_not_move_back(conn: sqlite3.Connection) -> None:
    freeze(conn, RUN, [make_evidence(A)], date(2026, 7, 2))

    with pytest.raises(ValueError, match="earlier"):
        freeze(conn, RUN, [make_evidence(B)], date(2026, 6, 30))

    assert len(load_evidence(conn, RUN)) == 1  # nothing was written
    assert conn.execute("SELECT count(*) FROM bundles").fetchone()[0] == 1


def test_section_statuses_carry_forward_and_can_be_overridden(conn: sqlite3.Connection) -> None:
    first = {Section.CLINICAL: SectionStatus.FOUND, Section.COMPETITION: SectionStatus.NOT_SEARCHED}
    freeze(conn, RUN, [make_evidence(A)], date(2026, 10, 6), first)
    v2 = freeze(conn, RUN, [], date(2026, 10, 6), {Section.COMPETITION: SectionStatus.FOUND})

    assert v2.section_statuses == {
        Section.CLINICAL: SectionStatus.FOUND,
        Section.COMPETITION: SectionStatus.FOUND,
    }


def test_newer_status_replaces_older_in_the_new_bundle_only(conn: sqlite3.Connection) -> None:
    key = "nct:NCT01:overall_status"
    old = make_evidence(A, date(2025, 1, 1), status_key=key, excerpt="RECRUITING")
    new = make_evidence(A, date(2026, 9, 16), status_key=key, excerpt="COMPLETED")

    v1 = freeze(conn, RUN, [old], date(2026, 6, 30))
    v2 = freeze(conn, RUN, [new], date(2026, 10, 6))

    assert [e.excerpt for e in v1.evidence] == ["RECRUITING"]
    assert [e.excerpt for e in v2.evidence] == ["COMPLETED"]
    assert len(load_evidence(conn, RUN)) == 2  # the older record is still stored


def test_runs_are_independent(conn: sqlite3.Connection) -> None:
    freeze(conn, "R-1", [make_evidence(A)], date(2026, 10, 6))
    other = freeze(conn, "R-2", [make_evidence(B)], date(2026, 10, 6))

    assert other.version == 1
    assert [e.id for e in other.evidence] == ["E-0001"]
