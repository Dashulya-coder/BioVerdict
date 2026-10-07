import sqlite3
from pathlib import Path

import pytest

from bioverdict.store.bundle_repo import save_bundle
from bioverdict.store.db import connect
from bioverdict.store.load_bundle import load_bundle
from bioverdict.store.migrations import migrate
from bioverdict.store.models import Bundle

FIXTURE = Path(__file__).parents[2] / "fixtures" / "bundles" / "divarasib.json"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "t.db")
    migrate(connection)
    yield connection
    connection.close()


def fixture_bundle(run_id: str = "R-1") -> Bundle:
    bundle = Bundle.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    return bundle.model_copy(update={"run_id": run_id, "bundle_id": f"B-{run_id}-v1"})


def test_a_stored_bundle_loads_back_identical_with_its_ids(conn: sqlite3.Connection) -> None:
    bundle = fixture_bundle()

    save_bundle(conn, bundle)

    loaded = load_bundle(conn, "R-1")
    assert loaded == bundle
    assert [e.id for e in loaded.evidence] == [e.id for e in bundle.evidence]  # not renumbered


def test_the_same_fixture_can_serve_several_runs(conn: sqlite3.Connection) -> None:
    save_bundle(conn, fixture_bundle("R-1"))
    save_bundle(conn, fixture_bundle("R-2"))

    assert load_bundle(conn, "R-1").content_hash == load_bundle(conn, "R-2").content_hash


def test_a_bundle_whose_hash_does_not_match_its_evidence_is_refused(
    conn: sqlite3.Connection,
) -> None:
    bundle = fixture_bundle()
    tampered = bundle.evidence[0].model_copy(update={"excerpt": "something else"})
    altered = bundle.model_copy(update={"evidence": [tampered, *bundle.evidence[1:]]})

    with pytest.raises(ValueError, match="altered"):
        save_bundle(conn, altered)

    assert conn.execute("SELECT count(*) FROM evidence").fetchone()[0] == 0  # nothing written
