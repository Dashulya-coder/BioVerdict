import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from bioverdict.store.db import connect
from bioverdict.store.freeze import freeze
from bioverdict.store.load_bundle import BundleIntegrityError, BundleNotFoundError, load_bundle
from bioverdict.store.migrations import migrate
from bioverdict.store.models import Evidence, EvidenceLevel, Locator, SourceKind

RUN = "R-1"
A, B = "https://example.org/NCT01", "https://example.org/NCT02"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "t.db")
    migrate(connection)
    return connection


def make_evidence(url: str, published_at: date = date(2024, 1, 1), **overrides) -> Evidence:
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


def test_loaded_bundle_equals_the_frozen_one(conn: sqlite3.Connection) -> None:
    frozen = freeze(conn, RUN, [make_evidence(A), make_evidence(B)], date(2026, 10, 6))
    assert load_bundle(conn, RUN) == frozen


def test_latest_version_is_the_default_and_old_ones_stay_loadable(conn: sqlite3.Connection) -> None:
    v1 = freeze(conn, RUN, [make_evidence(A)], date(2026, 6, 30))
    v2 = freeze(conn, RUN, [make_evidence(B)], date(2026, 7, 2))

    assert load_bundle(conn, RUN) == v2
    assert load_bundle(conn, RUN, version=1) == v1
    assert [e.url for e in load_bundle(conn, RUN, version=1).evidence] == [A]


def test_superseded_status_stays_hidden_after_reload(conn: sqlite3.Connection) -> None:
    key = "nct:NCT01:overall_status"
    old = make_evidence(A, date(2025, 1, 1), status_key=key, excerpt="RECRUITING")
    new = make_evidence(A, date(2026, 9, 16), status_key=key, excerpt="COMPLETED")
    freeze(conn, RUN, [old], date(2026, 6, 30))
    v2 = freeze(conn, RUN, [new], date(2026, 10, 6))

    assert load_bundle(conn, RUN, version=2) == v2


def test_missing_run_or_version_is_reported(conn: sqlite3.Connection) -> None:
    with pytest.raises(BundleNotFoundError):
        load_bundle(conn, "R-none")
    freeze(conn, RUN, [make_evidence(A)], date(2026, 10, 6))
    with pytest.raises(BundleNotFoundError, match="version 5"):
        load_bundle(conn, RUN, version=5)


def test_altered_evidence_is_detected(conn: sqlite3.Connection) -> None:
    freeze(conn, RUN, [make_evidence(A)], date(2026, 10, 6))
    conn.execute("UPDATE evidence SET excerpt = 'tampered' WHERE run_id = ?", (RUN,))
    conn.commit()

    with pytest.raises(BundleIntegrityError):
        load_bundle(conn, RUN)
