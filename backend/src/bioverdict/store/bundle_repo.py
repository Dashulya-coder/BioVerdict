"""Storing a bundle exactly as it is: fixtures and demo dumps, where ids and hash are given.

`freeze` builds a bundle from collected evidence and assigns ids. This does the opposite: the
bundle already exists, so nothing is renumbered, and the stored hash must match the content.
"""

from __future__ import annotations

import json
import sqlite3

from bioverdict.store.bundle import compute_content_hash
from bioverdict.store.evidence_repo import save_evidence
from bioverdict.store.freeze import SECTION_STATUSES
from bioverdict.store.models import Bundle


def save_bundle(conn: sqlite3.Connection, bundle: Bundle) -> None:
    actual = compute_content_hash(bundle.evidence, bundle.section_statuses)
    if actual != bundle.content_hash:
        raise ValueError(
            f"{bundle.bundle_id}: content_hash {bundle.content_hash} does not match the "
            f"evidence ({actual}); refusing to store a bundle that was altered"
        )
    with conn:
        save_evidence(conn, bundle.run_id, bundle.evidence)
        conn.execute(
            "INSERT INTO bundles (bundle_id, run_id, version, content_hash, as_of, catalog_json, "
            "section_statuses_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                bundle.bundle_id,
                bundle.run_id,
                bundle.version,
                bundle.content_hash,
                bundle.as_of.isoformat(),
                json.dumps(bundle.catalog),
                SECTION_STATUSES.dump_json(bundle.section_statuses).decode("utf-8"),
                bundle.created_at.isoformat(),
            ),
        )
