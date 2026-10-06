import re
import sqlite3
from pathlib import Path

import pytest

from bioverdict.store.db import connect
from bioverdict.store.migrations import SCHEMA_VERSION, current_version, migrate

DATA_MODEL = Path(__file__).parents[2] / "docs" / "data-model.md"


def _columns(conn: sqlite3.Connection) -> dict[str, list[tuple[str, int]]]:
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    return {
        t: [(c["name"], c["pk"]) for c in conn.execute(f"PRAGMA table_info({t})")] for t in tables
    }


def test_migrate_creates_schema_and_sets_version(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    assert current_version(conn) == 0
    assert migrate(conn) == SCHEMA_VERSION
    assert current_version(conn) == SCHEMA_VERSION
    assert "evidence" in _columns(conn)


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    assert migrate(conn) == SCHEMA_VERSION


def test_newer_database_is_rejected(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(RuntimeError):
        migrate(conn)


def test_evidence_ids_may_repeat_across_runs(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    for run in ("R-1", "R-2"):
        conn.execute("INSERT INTO evidence (run_id, id) VALUES (?, 'E-0001')", (run,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO evidence (run_id, id) VALUES ('R-1', 'E-0001')")


def test_migration_matches_data_model_doc(tmp_path: Path) -> None:
    doc_sql = re.search(r"```sql\n(.*?)```", DATA_MODEL.read_text(encoding="utf-8"), re.DOTALL)
    assert doc_sql
    from_doc = sqlite3.connect(":memory:")
    from_doc.row_factory = sqlite3.Row
    from_doc.executescript(doc_sql.group(1))
    from_code = connect(tmp_path / "t.db")
    migrate(from_code)
    assert _columns(from_code) == _columns(from_doc)
