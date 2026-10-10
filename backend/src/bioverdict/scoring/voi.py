"""Value of information of a diligence question, computed by code (docs/scoring.md).

A question is about one claim. Its answer is either "yes, the claim holds" or "no, it does not".
For each answer the verdict is recomputed with the claim settled that way; the value of the
question is how far the verdict would move, weighted by how likely each answer is. The model
proposes questions and names the claim; it never says how much an answer is worth.

rNPV does not depend on the claims in this model (it follows from the stage and the market), so
the value is measured on the verdict, its confidence and the translation-chain probability.
"""

from __future__ import annotations

from dataclasses import dataclass

from bioverdict.scoring.config import ConfidenceConfig, VerdictConfig
from bioverdict.scoring.verdict import score_verdict
from bioverdict.store.models import Basis, Claim, Range, Verdict, VerdictResult

_STEPS = {Verdict.INVEST: 0, Verdict.CONDITIONAL: 1, Verdict.DO_NOT_INVEST: 2}


@dataclass(frozen=True)
class VoIConfig:
    """How a settled claim is represented, and how fine movements count against whole steps."""

    settled_yes: float = 0.95  # confidence of a claim an answer has established
    settled_no: float = 0.05  # ...and of one it has refuted
    unknown_prior: float = 0.5  # chance of "yes" when the evidence says nothing either way
    fine_weight: float = 0.5  # a move of 1.0 in confidence or chain probability counts this much


def _settle(claim: Claim, answer: bool, cfg: VoIConfig) -> Claim:
    parts = claim.confidence_parts
    return claim.model_copy(
        update={
            "basis": Basis.EXTRACTED,  # an answered question is a stated fact, not a guess
            "confidence": cfg.settled_yes if answer else cfg.settled_no,
            # A confirmed claim stands on enough independent sources and is no longer sparse.
            "confidence_parts": parts.model_copy(update={"independent_groups": 2})
            if parts
            else None,
            "flags": [],
        }
    )


def _shift(before: VerdictResult, after: VerdictResult, cfg: VoIConfig) -> float:
    steps = abs(_STEPS[before.verdict] - _STEPS[after.verdict])
    chain = abs(
        (before.translation_chain_probability or 0) - (after.translation_chain_probability or 0)
    )
    return steps + cfg.fine_weight * (abs(before.confidence - after.confidence) + chain)


def value_of_information(
    claims: list[Claim],
    claim_id: str,
    rnpv: Range | None = None,
    vcfg: VerdictConfig | None = None,
    ccfg: ConfidenceConfig | None = None,
    cfg: VoIConfig | None = None,
) -> float:
    """Expected movement of the verdict if `claim_id` were settled; 0 for a claim not in `claims`."""
    cfg = cfg or VoIConfig()
    target = next((c for c in claims if c.id == claim_id), None)
    if target is None:
        return 0.0
    now = score_verdict(claims, rnpv, vcfg, ccfg)
    p_yes = (
        cfg.unknown_prior
        if target.basis in (Basis.UNKNOWN, Basis.HYPOTHESIS)
        else target.confidence
    )
    value = 0.0
    for answer, weight in ((True, p_yes), (False, 1 - p_yes)):
        settled = [_settle(c, answer, cfg) if c.id == claim_id else c for c in claims]
        value += weight * _shift(now, score_verdict(settled, rnpv, vcfg, ccfg), cfg)
    return value
