"""Status facts: of several records with the same `status_key`, only the latest counts."""

from __future__ import annotations

from datetime import date, datetime

from bioverdict.store.models import Evidence


def _recency(evidence: Evidence) -> tuple[date, datetime, str]:
    """Publication date (retrieval date if undated), then retrieval time, then id as tie-break."""
    published = evidence.published_at or evidence.retrieved_at.date()
    return (published, evidence.retrieved_at, evidence.id)


def drop_superseded(evidence: list[Evidence]) -> list[Evidence]:
    """Keep every item without a `status_key`, and the latest item per `status_key`.

    The input order is preserved. Superseded items are not deleted from the store; they only
    stay out of the bundle, so earlier bundle versions keep their content.

    Apply `filter_as_of` BEFORE this function, never after. Otherwise a newer status that is
    still in the future of the analysis date supersedes the older one and is then hidden by the
    date filter, leaving no status at all (breaks backtests and time travel).
    """
    latest: dict[str, Evidence] = {}
    for item in evidence:
        key = item.status_key
        if key is not None and (key not in latest or _recency(item) > _recency(latest[key])):
            latest[key] = item

    return [item for item in evidence if item.status_key is None or latest[item.status_key] is item]
