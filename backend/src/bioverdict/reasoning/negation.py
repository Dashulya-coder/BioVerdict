"""Is a phrase asserted or negated? Used wherever code reads a reason out of free text.

"there was no clinical hold", "not based on any safety concerns" and "was not discontinued" all
contain the words of the thing they deny. A phrase counts only if nothing earlier in its own
sentence negates it.
"""

from __future__ import annotations

import re

_NEGATION = re.compile(
    r"\b(?:no|not|never|without|neither|nor|none|cannot|unrelated|absence of|free of"
    r"|independent of|irrespective of|other than|rule[sd]? out)\b|n't\b",
    re.IGNORECASE,
)
_CLAUSE_BREAK = re.compile(r"[.;:!?]")
_REACH = 60  # characters before the phrase that may negate it


def has_unnegated(pattern: re.Pattern[str], text: str) -> bool:
    """True if `pattern` occurs somewhere with no negation earlier in its sentence."""
    for match in pattern.finditer(text):
        before = text[max(0, match.start() - _REACH) : match.start()]
        clause = _CLAUSE_BREAK.split(before)[-1]
        if not _NEGATION.search(clause):
            return True
    return False
