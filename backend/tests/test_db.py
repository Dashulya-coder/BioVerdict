from pathlib import Path

from bioverdict.store.db import connect


def test_connect_enables_wal(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_rows_are_addressable_by_name(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    assert conn.execute("SELECT 1 AS one").fetchone()["one"] == 1


def test_reader_is_not_blocked_by_open_write(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    writer, reader = connect(path), connect(path)
    writer.execute("CREATE TABLE t (x INTEGER)")
    writer.commit()
    writer.execute("INSERT INTO t VALUES (1)")  # transaction left open
    assert reader.execute("SELECT count(*) FROM t").fetchone()[0] == 0
    writer.commit()
    assert reader.execute("SELECT count(*) FROM t").fetchone()[0] == 1
