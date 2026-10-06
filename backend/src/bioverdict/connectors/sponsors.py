"""Sponsor names to `independence_group` labels.

Scoring counts evidence from one lab or sponsor once, so one company must always get one
label. The registry names Roche's studies both "Hoffmann-La Roche" and "Genentech, Inc.";
without this they would look like two independent sources.
"""

from __future__ import annotations

import re

# Legal-form words dropped from the end of a name.
_LEGAL_SUFFIXES = {
    "inc", "incorporated", "ltd", "limited", "llc", "corp", "corporation", "co", "company",
    "ag", "gmbh", "plc", "sa", "nv", "bv", "kk", "lp",
}  # fmt: skip

# Subsidiaries and alternate spellings of one sponsor, keyed by the cleaned lowercase name.
# Extend when a new duplicate shows up; keep to ownership that is stable over time.
_ALIASES = {
    "hoffmann la roche": "Roche",
    "f hoffmann la roche": "Roche",
    "roche": "Roche",
    "genentech": "Roche",
    "chugai pharmaceutical": "Roche",
    "eli lilly": "Eli Lilly",
    "lilly": "Eli Lilly",
    "novo nordisk a s": "Novo Nordisk",
    "novo nordisk": "Novo Nordisk",
}


def _clean(name: str) -> list[str]:
    words = re.sub(r"[^\w\s]", " ", name).split()
    # "Eli Lilly and Company": dropping the legal form leaves a dangling "and".
    while words and words[-1].lower() in _LEGAL_SUFFIXES | {"and"}:
        words.pop()
    return words


def sponsor_group(name: str | None) -> str:
    """`sponsor:<canonical name>`, or `sponsor:unknown` when the record names none."""
    words = _clean(name or "")
    if not words:
        return "sponsor:unknown"
    cleaned = " ".join(words)
    return f"sponsor:{_ALIASES.get(cleaned.lower(), cleaned)}"
