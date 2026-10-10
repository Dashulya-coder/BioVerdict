"""How far one claim pulls the investment case: the weight shared by module answers and risks."""

from __future__ import annotations

from bioverdict.store.models import Basis, Claim, Implication


def contribution(claim: Claim) -> float:
    """How far a claim pulls its module, from its implication and its computed confidence.

    `2 * confidence - 1` is positive when the evidence makes the claim likely and negative when
    contradicting evidence outweighs the support, so a favourable claim that new evidence refutes
    ends up counting against. A claim with no weighted evidence (a gap, a hypothesis, a quote
    whose level carries no weight) pulls nowhere: its low confidence is ignorance, not refutation.
    """
    if claim.implication is Implication.NEUTRAL:
        return 0.0
    if claim.basis in (Basis.UNKNOWN, Basis.HYPOTHESIS):
        return 0.0
    parts = claim.confidence_parts
    if parts is not None and parts.support == 0 and parts.contra == 0:
        return 0.0
    sign = 1.0 if claim.implication is Implication.FAVOURABLE else -1.0
    return sign * (2 * claim.confidence - 1)
