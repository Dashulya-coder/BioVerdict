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
