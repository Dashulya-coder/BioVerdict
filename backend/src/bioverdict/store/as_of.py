"""The `as_of` rule shared by connectors and the evidence store (ADR-007).

A run replayed "as of" a date may only see evidence published on or before that date.
"""

from __future__ import annotations

from datetime import date

from bioverdict.store.models import Evidence


def is_visible_as_of(evidence: Evidence, as_of: date) -> bool:
    """Whether a run replayed at `as_of` may see this evidence. The cutoff date is inclusive.

    Dated evidence is judged by its publication date. Undated evidence is a snapshot of a
    source's current state (for example an Open Targets record), so it is only trustworthy
    if it was retrieved by the cutoff; otherwise it may show the future.
    """
    if evidence.published_at is not None:
        return evidence.published_at <= as_of
    return evidence.retrieved_at.date() <= as_of


def filter_as_of(evidence: list[Evidence], as_of: date) -> list[Evidence]:
    return [item for item in evidence if is_visible_as_of(item, as_of)]
