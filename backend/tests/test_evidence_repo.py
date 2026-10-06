import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from bioverdict.store.db import connect
from bioverdict.store.evidence_repo import load_evidence, save_evidence
from bioverdict.store.migrations import migrate
from bioverdict.store.models import Evidence, EvidenceLevel, Locator, SourceKind


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "t.db")
    migrate(connection)
    return connection


def make_evidence(eid: str = "E-0001", **overrides) -> Evidence:
    fields = {
        "id": eid,
        "source": "ClinicalTrials.gov",
        "source_family": "registry",
        "source_kind": SourceKind.REGISTRY,
        "url": "https://clinicaltrials.gov/study/NCT06497556",
        "locator": Locator(type="nct", value="NCT06497556"),
        "excerpt": "n = 24, Cα, Å",
        "published_at": date(2024, 7, 11),
        "retrieved_at": datetime(2026, 10, 6, 10, 15, tzinfo=UTC),
        "level": EvidenceLevel.HUMAN_INTERVENTIONAL,
        "independence_group": "sponsor:Roche",
        "status_key": "nct:NCT06497556:overall_status",
        "version": 2,
    }
    return Evidence(**{**fields, **overrides})


def test_round_trip_keeps_every_field(conn: sqlite3.Connection) -> None:
    original = make_evidence()
    save_evidence(conn, "R-1", [original])
    assert load_evidence(conn, "R-1") == [original]


def test_round_trip_with_missing_optional_fields(conn: sqlite3.Connection) -> None:
    bare = make_evidence(locator=None, published_at=None, status_key=None)
    save_evidence(conn, "R-1", [bare])
    assert load_evidence(conn, "R-1") == [bare]


def test_evidence_is_ordered_by_id_and_scoped_to_its_run(conn: sqlite3.Connection) -> None:
    save_evidence(conn, "R-1", [make_evidence("E-0002"), make_evidence("E-0001")])
    save_evidence(conn, "R-2", [make_evidence("E-0001")])
    assert [e.id for e in load_evidence(conn, "R-1")] == ["E-0001", "E-0002"]
    assert [e.id for e in load_evidence(conn, "R-2")] == ["E-0001"]


def test_same_id_twice_in_one_run_is_rejected(conn: sqlite3.Connection) -> None:
    save_evidence(conn, "R-1", [make_evidence()])
    with pytest.raises(sqlite3.IntegrityError):
        save_evidence(conn, "R-1", [make_evidence()])


def test_unknown_run_has_no_evidence(conn: sqlite3.Connection) -> None:
    assert load_evidence(conn, "R-missing") == []
