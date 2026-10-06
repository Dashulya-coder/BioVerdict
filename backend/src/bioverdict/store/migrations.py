"""Schema migrations. The applied level lives in `PRAGMA user_version`.

Keep MIGRATION_1 in sync with the SQL block in docs/data-model.md (a test compares them).
Never edit an applied migration: append a new one.
"""

from __future__ import annotations

import sqlite3

MIGRATION_1 = """
CREATE TABLE runs (
  run_id         TEXT PRIMARY KEY,
  input_json     TEXT,
  as_of          TEXT,
  status         TEXT,
  verdict        TEXT,
  created_at     TEXT,
  finished_at    TEXT,
  schema_version INTEGER
);
CREATE TABLE bundles (
  bundle_id             TEXT PRIMARY KEY,
  run_id                TEXT,
  version               INTEGER,
  content_hash          TEXT,
  as_of                 TEXT,
  catalog_json          TEXT,
  section_statuses_json TEXT,
  created_at            TEXT,
  UNIQUE (run_id, version)
);
CREATE TABLE evidence (
  run_id             TEXT,
  id                 TEXT,
  source             TEXT,
  source_family      TEXT,
  source_kind        TEXT,
  type               TEXT,
  url                TEXT,
  locator_json       TEXT,
  excerpt            TEXT,
  published_at       TEXT,
  retrieved_at       TEXT,
  level              TEXT,
  independence_group TEXT,
  version            INTEGER,
  PRIMARY KEY (run_id, id)
);
CREATE TABLE claims (
  run_id                TEXT,
  id                    TEXT,
  section               TEXT,
  claim_type            TEXT,
  text                  TEXT,
  basis                 TEXT,
  status                TEXT,
  confidence            REAL,
  confidence_parts_json TEXT,
  flags_json            TEXT,
  depends_on_json       TEXT,
  diligence_type        TEXT,
  chain_link            TEXT,
  gate_signals_json     TEXT,
  critical              INTEGER,
  version               INTEGER,
  PRIMARY KEY (run_id, id)
);
CREATE TABLE claim_evidence (
  run_id      TEXT,
  claim_id    TEXT,
  evidence_id TEXT,
  direction   TEXT,
  quote       TEXT,
  PRIMARY KEY (run_id, claim_id, evidence_id)
);
CREATE TABLE llm_calls (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id        TEXT,
  step          TEXT,
  provider      TEXT,
  model         TEXT,
  effort        TEXT,
  input_tokens  INTEGER,
  output_tokens INTEGER,
  cost_usd      REAL,
  latency_ms    INTEGER,
  attempts      INTEGER,
  cache_hit     INTEGER,
  failover_from TEXT,
  error         TEXT,
  created_at    TEXT
);
CREATE TABLE http_cache (
  key        TEXT PRIMARY KEY,
  url        TEXT,
  body       BLOB,
  fetched_at TEXT
);
CREATE TABLE verification_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id     TEXT,
  claim_id   TEXT,
  check_name TEXT,
  passed     INTEGER,
  detail     TEXT
);
"""

MIGRATIONS: list[str] = [MIGRATION_1]
SCHEMA_VERSION = len(MIGRATIONS)


def current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations, each in its own transaction. Returns the new version."""
    version = current_version(conn)
    if version > SCHEMA_VERSION:
        raise RuntimeError(f"database schema {version} is newer than code ({SCHEMA_VERSION})")
    for target, script in enumerate(MIGRATIONS[version:], start=version + 1):
        # executescript() commits first and runs the script as given, so wrap it explicitly
        conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {target};\nCOMMIT;")
    return current_version(conn)
