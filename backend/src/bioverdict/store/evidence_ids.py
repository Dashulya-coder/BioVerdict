"""Canonical evidence ids, assigned when evidence is frozen into a bundle.

Connectors return evidence with placeholder ids. The store renumbers it so the same
documents always get the same ids, whatever order the network answered in, because claims
and the content hash refer to these ids.
"""

from __future__ import annotations

import re

from bioverdict.store.models import Evidence

_ID_PATTERN = re.compile(r"E-(\d+)")


def dedup_key(evidence: Evidence) -> tuple[str, str, str]:
    """Two items with the same url, locator and excerpt are the same piece of evidence."""
    locator = evidence.locator
    locator_value = locator.value if locator is not None else ""
    return (evidence.url, locator_value, evidence.excerpt)


def _number(evidence_id: str) -> int:
    match = _ID_PATTERN.fullmatch(evidence_id)
    if match is None:
        raise ValueError(f"not a canonical evidence id: {evidence_id!r}")
    return int(match.group(1))


def assign_ids(existing: list[Evidence], incoming: list[Evidence], version: int) -> list[Evidence]:
    """Return the incoming evidence that is new, numbered after the existing ids.

    Evidence already present (same dedup key) is skipped, and so are repeats inside `incoming`.
    New items are sorted by their content before numbering, so the result does not depend on
    input order. Existing ids never change, which keeps earlier bundle versions valid.
    """
    seen = {dedup_key(item) for item in existing}
    next_number = max((_number(item.id) for item in existing), default=0) + 1

    unique: dict[tuple[str, str, str], Evidence] = {}
    # The full JSON is the last sort key, so duplicates resolve the same way every time.
    for item in sorted(incoming, key=lambda e: (dedup_key(e), e.model_dump_json())):
        key = dedup_key(item)
        if key not in seen and key not in unique:
            unique[key] = item

    return [
        item.model_copy(update={"id": f"E-{number:04d}", "version": version})
        for number, item in enumerate(unique.values(), start=next_number)
    ]
