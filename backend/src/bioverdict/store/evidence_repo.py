"""Reading and writing evidence rows. The caller owns the transaction."""

from __future__ import annotations

import json
import sqlite3

from bioverdict.store.models import Evidence

_COLUMNS = (
    "run_id, id, source, source_family, source_kind, type, url, locator_json, excerpt, "
    "published_at, retrieved_at, level, independence_group, version, status_key"
)
_PLACEHOLDERS = ", ".join(f":{name.strip()}" for name in _COLUMNS.split(","))


def save_evidence(conn: sqlite3.Connection, run_id: str, items: list[Evidence]) -> None:
    rows = []
    for item in items:
        data = item.model_dump(mode="json")
        locator = data.pop("locator")
        rows.append({**data, "run_id": run_id, "locator_json": json.dumps(locator)})
    conn.executemany(f"INSERT INTO evidence ({_COLUMNS}) VALUES ({_PLACEHOLDERS})", rows)


def load_evidence(conn: sqlite3.Connection, run_id: str) -> list[Evidence]:
    """All evidence of a run, every version, ordered by id."""
    rows = conn.execute("SELECT * FROM evidence WHERE run_id = ? ORDER BY id", (run_id,))
    return [_to_evidence(row) for row in rows]


def _to_evidence(row: sqlite3.Row) -> Evidence:
    data = dict(row)
    del data["run_id"]
    data["locator"] = json.loads(data.pop("locator_json"))
    return Evidence.model_validate(data)
