"""Bundle helpers: the content hash that identifies a frozen evidence snapshot."""

from __future__ import annotations

import hashlib
import json

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
