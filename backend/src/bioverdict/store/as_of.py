"""The `as_of` rule shared by connectors and the evidence store (ADR-007).

A run replayed "as of" a date may only see evidence published on or before that date.
"""

from __future__ import annotations

from datetime import date

from bioverdict.store.models import Evidence


def is_visible_as_of(evidence: Evidence, as_of: date) -> bool:
    """Inclusive on the cutoff date. Undated evidence is kept: nothing proves it is later."""
    return evidence.published_at is None or evidence.published_at <= as_of


def filter_as_of(evidence: list[Evidence], as_of: date) -> list[Evidence]:
    return [item for item in evidence if is_visible_as_of(item, as_of)]
