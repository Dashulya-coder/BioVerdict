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
DEFAULT_CACHE_DIR = "data/cache"


def fixtures_dir() -> Path:
    return Path(os.environ.get("FIXTURES_DIR", REPO_ROOT / "fixtures"))


def db_path() -> Path:
    return Path(os.environ.get("DB_PATH", DEFAULT_DB_PATH))


def cache_dir() -> Path:
    return Path(os.environ.get("CACHE_DIR", DEFAULT_CACHE_DIR))


def http_cache_max_age_s() -> float | None:
    """How old a cached source answer may be, from `HTTP_CACHE_MAX_AGE_H` (hours).

    Unset, answers never expire: every run replays the same downloads, which a demo and a
    comparison of two runs need. Set it for live work, where a registry record changes.
    """
    hours = os.environ.get("HTTP_CACHE_MAX_AGE_H", "").strip()
    return float(hours) * 3600 if hours else None


def today() -> date:
    """Today's date where the server runs, which is the analyst's day (not the UTC day).

    A run dated by this day sees everything downloaded earlier today: evidence without a
    publication date is visible once it was retrieved on or before the run's date.
    """
    return datetime.now().astimezone().date()


def use_fixtures() -> bool:
    """Fixture runs are the default: offline and free. `USE_FIXTURES=0` makes runs live."""
    return os.environ.get("USE_FIXTURES", "1") not in {"0", "false", "False", ""}


def open_database(path: Path | None = None) -> sqlite3.Connection:
    """A connection to the database, created and migrated on first use."""
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(target)
    migrate(conn)
    return conn


def recompute_mode() -> str:
    """`classify` (the model places the new evidence, code recomputes) or `full` (every reasoning
    module runs again on the bigger bundle). The first is the default: it changes only what the
    evidence touches."""
    mode = os.environ.get("RECOMPUTE_MODE", "classify").strip().lower()
    return mode if mode in {"classify", "full"} else "classify"
