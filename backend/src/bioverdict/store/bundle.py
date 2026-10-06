"""Bundle helpers: the content hash that identifies a frozen evidence snapshot."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from bioverdict.store.as_of import filter_as_of
from bioverdict.store.latest_wins import drop_superseded
from bioverdict.store.models import Evidence, Section, SectionStatus

# Not part of the document's content: when it was fetched, and which store version added it.
HASH_EXCLUDED_FIELDS = {"retrieved_at", "version"}


def compute_content_hash(
    evidence: list[Evidence],
    section_statuses: dict[Section, SectionStatus],
) -> str:
    """Hash what the reasoning phase can see, and nothing else.

    Identical evidence gives an identical hash regardless of fetch time or input order.
    Evidence ids are included on purpose: claims reference them, so two bundles whose ids
    differ must not share a hash (and with it a cached LLM answer).
    """
    ids = [e.id for e in evidence]
    if len(ids) != len(set(ids)):
        raise ValueError("evidence ids must be unique within a bundle")

    payload = {
        "evidence": [
            e.model_dump(mode="json", exclude=HASH_EXCLUDED_FIELDS)
            for e in sorted(evidence, key=lambda e: e.id)
        ],
        "section_statuses": {
            section.value: status.value for section, status in section_statuses.items()
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def select_bundle_evidence(evidence: list[Evidence], as_of: date) -> list[Evidence]:
    """The evidence a bundle holds, from everything stored up to its version.

    Order matters: first drop what is not yet known at `as_of`, then let the newest remaining
    status fact supersede the older ones. The other way round, a future status would erase the
    older one and then be hidden itself, leaving the run with no status at all.
    """
    visible = drop_superseded(filter_as_of(evidence, as_of))
    return sorted(visible, key=lambda item: item.id)
