"""What the model is asked to return. The LLM drafts and classifies; code decides what stays.

The model may not produce `derived` or `modeled` claims (numbers are computed by code) and never
writes a confidence: that comes from the scoring formula.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from bioverdict.store.models import (
    ChainLink,
    ClaimType,
    DiligenceType,
    Direction,
    GateId,
)


class _Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DraftLink(_Draft):
    evidence_id: str = Field(description="An id from the evidence list, for example E-0007")
    direction: Direction
    quote: str = Field(description="Copied character for character from that evidence's text")


class DraftClaim(_Draft):
    text: str = Field(description="One checkable statement in plain language")
    claim_type: ClaimType
    basis: Literal["extracted", "inferred", "hypothesis", "unknown"]
    chain_link: ChainLink | None = Field(
        default=None, description="Translation module only: the chain link the claim speaks to"
    )
    diligence_type: DiligenceType | None = Field(
        default=None, description="Required for `unknown`: what kind of data would answer it"
    )
    gate_signals: list[GateId] = Field(
        default_factory=list, description="Kill criteria whose condition this claim asserts"
    )
    critical: bool = Field(default=False, description="True for a claim the verdict hinges on")
    links: list[DraftLink] = Field(default_factory=list)


class ModuleDraft(_Draft):
    claims: list[DraftClaim]


def merge_drafts(drafts: list[ModuleDraft], drop_unknown: bool = False) -> ModuleDraft:
    """One draft from the drafts of several batches of one module.

    A claim written in more than one batch (the same words) becomes one claim that carries the
    links of all of them: its gate tags and `critical` are united, the first batch's wording and
    labels stand. With several batches `unknown` claims are dropped: a batch cannot tell what is
    unknown when it has not read the others.
    """
    merged: dict[str, DraftClaim] = {}
    for draft in drafts:
        for claim in draft.claims:
            if drop_unknown and claim.basis == "unknown":
                continue
            key = " ".join(claim.text.casefold().split())
            if key not in merged:
                merged[key] = claim.model_copy(deep=True)
                continue
            kept = merged[key]
            have = {link.evidence_id for link in kept.links}
            kept.links += [link for link in claim.links if link.evidence_id not in have]
            kept.gate_signals += [g for g in claim.gate_signals if g not in kept.gate_signals]
            kept.critical = kept.critical or claim.critical
    return ModuleDraft(claims=list(merged.values()))
