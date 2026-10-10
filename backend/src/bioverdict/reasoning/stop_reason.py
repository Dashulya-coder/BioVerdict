"""Why a study stopped, read by code from the registry's own words.

K1 (the same target failed for lack of efficacy) and K2 (serious on-target toxicity) must not rest
on a model's reading of a stop reason alone. A registry says "Futility" for one study and "business
decision, not based on any safety or efficacy concerns" for another; only the first is a failed
target. The classifier is deliberately cautious: wording it cannot place is `other`, and wording
that mixes an operational cause with a scientific one is `mixed`, which supports no gate.
"""

from __future__ import annotations

import json
import re
from enum import StrEnum

from bioverdict.reasoning.negation import has_unnegated


class StopReason(StrEnum):
    EFFICACY = "efficacy"  # futility, lack of efficacy, endpoint not met
    SAFETY = "safety"  # adverse events, toxicity, deaths, a clinical hold
    BUSINESS = "business"  # strategy, funding, enrolment, supply, the pandemic
    MIXED = "mixed"  # an operational cause stated together with a scientific one
    OTHER = "other"  # a reason is given but not placed
    UNKNOWN = "unknown"  # no reason is given


_EFFICACY = re.compile(
    r"futil|lack of (?:efficacy|benefit|effect)|insufficient (?:efficacy|benefit)|inefficac"
    r"|no (?:efficacy|clinical benefit)|(?:did not|failed to|not) (?:meet|achieve|reach|show)"
    r"|unlikely to (?:meet|demonstrate|show)|worse than (?:control|placebo|comparator)",
    re.IGNORECASE,
)
_SAFETY = re.compile(
    r"safety|adverse|toxic|death|mortalit|clinical hold|liver injury|hepatotox|cardiotox"
    r"|unacceptable|harm|serious",
    re.IGNORECASE,
)
_BUSINESS = re.compile(
    r"business|strateg|sponsor(?:'s)? decision|company decision|portfolio|prioriti|fund(?:ing|s)"
    r"|financ|commercial|cost|resourc|merger|acqui[rs]|enrol|recruit|accrual|slow|low (?:rate|"
    r"accrual)|covid|pandemic|logistic|drug supply|supply|manufactur|investigator (?:left|moved)"
    r"|site closure|administrative|regulatory feedback",
    re.IGNORECASE,
)


# How papers and registry records word a failed primary endpoint without "did not meet": an
# active-comparator trial that was "not superior" (evobrutinib and tolebrutinib against
# teriflunomide), an endpoint that "was not met". A noninferiority trial is meant not to be
# superior, so there "not superior" says nothing about failure.
_NOT_SUPERIOR = re.compile(r"\bnot superior to\b", re.IGNORECASE)
_NONINFERIORITY = re.compile(r"non-?inferior", re.IGNORECASE)
_ENDPOINT_NOT_MET = re.compile(
    r"end ?points? (?:was|were|had been|has been) not (?:met|achieved|reached)"
    r"|missed (?:its|the|their|both) (?:co-)?primary end ?points?",
    re.IGNORECASE,
)
# A hold that was lifted is not a safety action in force: "the FDA lifted the partial clinical
# hold" must not read as a hold.
_LIFTED_HOLD = re.compile(
    r"lift(?:ed|s|ing)? (?:the |a |its |their )?(?:partial |full )?clinical holds?"
    r"|(?:partial |full )?clinical holds? (?:was |were |has been |have been |had been )?"
    r"(?:lifted|removed|released|resolved)"
    r"|remov(?:ed|es|ing) (?:the |a |its )?(?:partial |full )?clinical holds?",
    re.IGNORECASE,
)


def without_lifted_holds(text: str) -> str:
    """`text` with every mention of a lifted clinical hold taken out."""
    return _LIFTED_HOLD.sub(" ", text)


def classify_stop_reason(text: str | None) -> StopReason:
    if not text or not text.strip():
        return StopReason.UNKNOWN
    text = without_lifted_holds(text)
    efficacy = (
        has_unnegated(_EFFICACY, text)  # "not based on any safety or efficacy concerns"
        or has_unnegated(_ENDPOINT_NOT_MET, text)
        or (has_unnegated(_NOT_SUPERIOR, text) and not _NONINFERIORITY.search(text))
    )
    safety = has_unnegated(_SAFETY, text)  # says neither
    business = bool(_BUSINESS.search(text))  # business wording stays even beside a negation
    scientific = efficacy or safety
    if business and scientific:
        return StopReason.MIXED
    if business:
        return StopReason.BUSINESS
    if efficacy and safety:
        return StopReason.MIXED
    if efficacy:
        return StopReason.EFFICACY
    if safety:
        return StopReason.SAFETY
    return StopReason.OTHER


def why_stopped(excerpt: str) -> str | None:
    """The `whyStopped` field of a ClinicalTrials.gov status record, or None for other text."""
    try:
        data = json.loads(excerpt)
    except json.JSONDecodeError, TypeError:
        return None
    if isinstance(data, dict) and isinstance(data.get("whyStopped"), str):
        return data["whyStopped"]
    return None


def overall_status(excerpt: str) -> str | None:
    try:
        data = json.loads(excerpt)
    except json.JSONDecodeError, TypeError:
        return None
    return data.get("overallStatus") if isinstance(data, dict) else None
