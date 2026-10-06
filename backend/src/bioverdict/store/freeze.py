"""Freezing evidence into a versioned, content-hashed bundle (ADR-001, ADR-007).

Each call creates the next bundle version of a run. Evidence is append-only: a version adds
evidence and never edits or removes what an earlier version holds.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime

from pydantic import TypeAdapter

from bioverdict.store.as_of import filter_as_of
from bioverdict.store.bundle import compute_content_hash, select_bundle_evidence
from bioverdict.store.evidence_ids import assign_ids
from bioverdict.store.evidence_repo import load_evidence, save_evidence
from bioverdict.store.models import Bundle, Evidence, Section, SectionStatus

SECTION_STATUSES = TypeAdapter(dict[Section, SectionStatus])


def build_catalog(evidence: list[Evidence]) -> list[str]:
    """Every URL and identifier the bundle's evidence was actually fetched from."""
    entries: set[str] = set()
    for item in evidence:
        entries.add(item.url)
        if item.locator is not None:
            entries.add(item.locator.value)
    return sorted(entries)


def freeze(
    conn: sqlite3.Connection,
    run_id: str,
    incoming: list[Evidence],
    as_of: date,
    section_statuses: dict[Section, SectionStatus] | None = None,
) -> Bundle:
    """Store the new evidence and write the next bundle version of the run.

    `section_statuses` update the previous version's statuses; sections not mentioned keep
    theirs. `as_of` may not move backwards, since a version must contain everything the
    previous one did. The whole step is one transaction.
    """
    with conn:
        previous = conn.execute(
            "SELECT version, as_of, section_statuses_json FROM bundles "
            "WHERE run_id = ? ORDER BY version DESC LIMIT 1",
            (run_id,),
        ).fetchone()

        version = 1 if previous is None else previous["version"] + 1
        statuses: dict[Section, SectionStatus] = {}
        if previous is not None:
            if as_of < date.fromisoformat(previous["as_of"]):
                raise ValueError(
                    f"as_of {as_of} is earlier than version {previous['version']} "
                    f"({previous['as_of']}); a bundle version may not move back in time"
                )
            statuses = SECTION_STATUSES.validate_json(previous["section_statuses_json"])
        statuses.update(section_statuses or {})

        existing = load_evidence(conn, run_id)
        new = assign_ids(existing, filter_as_of(incoming, as_of), version)
        save_evidence(conn, run_id, new)

        visible = select_bundle_evidence(existing + new, as_of)
        bundle = Bundle(
            bundle_id=f"B-{run_id}-v{version}",
            run_id=run_id,
            version=version,
            as_of=as_of,
            content_hash=compute_content_hash(visible, statuses),
            catalog=build_catalog(visible),
            evidence=visible,
            section_statuses=statuses,
            created_at=datetime.now(UTC),
        )
        conn.execute(
            "INSERT INTO bundles (bundle_id, run_id, version, content_hash, as_of, catalog_json, "
            "section_statuses_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                bundle.bundle_id,
                run_id,
                version,
                bundle.content_hash,
                as_of.isoformat(),
                json.dumps(bundle.catalog),
                SECTION_STATUSES.dump_json(statuses).decode("utf-8"),
                bundle.created_at.isoformat(),
            ),
        )
    return bundle
