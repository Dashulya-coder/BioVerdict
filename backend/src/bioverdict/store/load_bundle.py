"""Rebuilding a stored bundle version and checking it was not altered."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

from bioverdict.store.bundle import compute_content_hash, select_bundle_evidence
from bioverdict.store.evidence_repo import load_evidence
from bioverdict.store.freeze import SECTION_STATUSES
from bioverdict.store.models import Bundle


class BundleNotFoundError(LookupError):
    pass


class BundleIntegrityError(RuntimeError):
    """The stored evidence no longer hashes to the hash recorded at freeze time."""


def load_bundle(conn: sqlite3.Connection, run_id: str, version: int | None = None) -> Bundle:
    """Load one bundle version of a run (the latest by default).

    The evidence is rebuilt exactly as `freeze` selected it: everything up to that version,
    visible at the bundle's `as_of`, without superseded status facts.
    """
    query = "SELECT * FROM bundles WHERE run_id = ?"
    if version is None:
        row = conn.execute(query + " ORDER BY version DESC LIMIT 1", (run_id,)).fetchone()
    else:
        row = conn.execute(query + " AND version = ?", (run_id, version)).fetchone()
    if row is None:
        wanted = "any bundle" if version is None else f"bundle version {version}"
        raise BundleNotFoundError(f"run {run_id!r} has no {wanted}")

    as_of = date.fromisoformat(row["as_of"])
    stored = [e for e in load_evidence(conn, run_id) if e.version <= row["version"]]
    evidence = select_bundle_evidence(stored, as_of)
    statuses = SECTION_STATUSES.validate_json(row["section_statuses_json"])

    actual_hash = compute_content_hash(evidence, statuses)
    if actual_hash != row["content_hash"]:
        raise BundleIntegrityError(
            f"{row['bundle_id']}: recorded hash {row['content_hash']} but the stored "
            f"evidence hashes to {actual_hash}"
        )
    return Bundle(
        bundle_id=row["bundle_id"],
        run_id=run_id,
        version=row["version"],
        as_of=as_of,
        content_hash=row["content_hash"],
        catalog=json.loads(row["catalog_json"]),
        evidence=evidence,
        section_statuses=statuses,
        created_at=datetime.fromisoformat(row["created_at"]),
    )
