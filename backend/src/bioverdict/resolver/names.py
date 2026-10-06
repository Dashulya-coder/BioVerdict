"""Matching a user's drug name or code against the names a database knows (A1).

A name is accepted only when the query equals the drug's name or one of its synonyms after
ignoring case and punctuation. Similar-looking names are never accepted: a registry search for
"RMC-9805" also returns "RMC-5552", a different molecule, and "elisrasib" is not "elironrasib"
(docs/domain-pack-oncology.md). What does not match is reported, not guessed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum

# Salt and form words a database appends to a name: "divarasib adipate", "ION-582 free acid".
# They name the same active moiety, but a match that needs them ranks below an exact one.
_FORM_WORDS = (
    "freeacid", "freebase", "sodium", "potassium", "calcium", "hydrochloride", "hcl",
    "mesylate", "tosylate", "adipate", "succinate", "tartrate", "maleate", "fumarate",
    "phosphate", "acetate", "sulfate",
)  # fmt: skip


class MatchKind(IntEnum):
    """How a query matched a drug; a lower number is a stronger match."""

    NAME = 0  # the drug's own name
    SYNONYM = 1  # another name or code of the same drug
    FORM = 2  # a name or synonym once a salt or form word is removed


def normalize(text: str) -> str:
    """Lower case, letters and digits only: 'HRO-761' and 'hro761' become 'hro761'."""
    return re.sub(r"[^0-9a-z]", "", text.casefold())


def strip_form(normalized: str) -> str:
    """Remove trailing salt or form words, repeatedly: 'obudanersensodium' -> 'obudanersen'."""
    stripped = True
    while stripped:
        stripped = False
        for word in _FORM_WORDS:
            if normalized.endswith(word) and len(normalized) > len(word):
                normalized = normalized.removesuffix(word)
                stripped = True
    return normalized


def match_kind(query: str, name: str, synonyms: Iterable[str] = ()) -> MatchKind | None:
    """The strongest way `query` matches this drug, or None when it does not match at all."""
    wanted = normalize(query)
    if not wanted:
        return None
    if wanted == normalize(name):
        return MatchKind.NAME
    labels = [normalize(label) for label in synonyms]
    if wanted in labels:
        return MatchKind.SYNONYM
    wanted_core = strip_form(wanted)
    if wanted_core == strip_form(normalize(name)) or wanted_core in map(strip_form, labels):
        return MatchKind.FORM
    return None


@dataclass(frozen=True)
class Candidate:
    chembl_id: str
    name: str
    synonyms: tuple[str, ...] = ()
    parent_id: str | None = None  # the parent molecule when this record is a salt or form


@dataclass(frozen=True)
class Ranked:
    candidate: Candidate
    kind: MatchKind


def rank_candidates(query: str, candidates: Iterable[Candidate]) -> list[Ranked]:
    """Candidates that really match `query`, strongest match first, then by name."""
    ranked = []
    for candidate in candidates:
        kind = match_kind(query, candidate.name, candidate.synonyms)
        if kind is not None:
            ranked.append(Ranked(candidate, kind))
    return sorted(ranked, key=lambda r: (r.kind, r.candidate.name, r.candidate.chembl_id))


def choose(ranked: list[Ranked]) -> Candidate | None:
    """The one drug the query means, or None when it is unknown or ambiguous.

    The best-ranked candidates are compared. If they are one record, or a parent and its
    salts/forms, the parent is chosen. Two unrelated drugs at the same rank are ambiguous.
    """
    if not ranked:
        return None
    best = [r.candidate for r in ranked if r.kind == ranked[0].kind]
    parents = {c.parent_id or c.chembl_id for c in best}
    if len(parents) != 1:
        return None
    parent_id = parents.pop()
    return next((c for c in best if c.chembl_id == parent_id), best[0])
