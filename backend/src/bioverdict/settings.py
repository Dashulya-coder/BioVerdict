"""Where the database and the fixtures are, read from the environment (see `.env.example`)."""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

from bioverdict.store.db import connect
from bioverdict.store.migrations import migrate

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = "data/bioverdict.sqlite"


def fixtures_dir() -> Path:
    return Path(os.environ.get("FIXTURES_DIR", REPO_ROOT / "fixtures"))


def db_path() -> Path:
    return Path(os.environ.get("DB_PATH", DEFAULT_DB_PATH))


def today() -> date:
    """Today's date where the server runs, which is the analyst's day (not the UTC day).

    A run dated by this day sees everything downloaded earlier today: evidence without a
    publication date is visible once it was retrieved on or before the run's date.
    """
    return datetime.now().astimezone().date()


def use_fixtures() -> bool:
    """Runs are answered from fixtures until the live pipeline is wired in."""
    return os.environ.get("USE_FIXTURES", "1") not in {"0", "false", "False", ""}


def open_database(path: Path | None = None) -> sqlite3.Connection:
    """A connection to the database, created and migrated on first use."""
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(target)
    migrate(conn)
    return conn
