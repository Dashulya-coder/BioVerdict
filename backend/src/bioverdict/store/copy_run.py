"""Starting a run from another run's evidence history (recompute on added evidence, A7).

The new run gets the same evidence rows, with the same ids and versions, and the same bundle
versions with the same hashes. Nothing of the original run is edited.
"""

from __future__ import annotations

import sqlite3

from bioverdict.store.evidence_repo import load_evidence, save_evidence


def copy_evidence_history(conn: sqlite3.Connection, source_run: str, target_run: str) -> None:
    """Copy every evidence row and every bundle version of `source_run`. One transaction."""
    with conn:
        save_evidence(conn, target_run, load_evidence(conn, source_run))
        conn.execute(
            "INSERT INTO bundles (bundle_id, run_id, version, content_hash, as_of, catalog_json, "
            "section_statuses_json, created_at) "
            "SELECT 'B-' || :target || '-v' || version, :target, version, content_hash, as_of, "
            "catalog_json, section_statuses_json, created_at FROM bundles WHERE run_id = :source",
            {"source": source_run, "target": target_run},
        )
