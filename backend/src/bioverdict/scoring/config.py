"""Starting heuristics from the Unobio plan. Calibrated on the eval set, never by hand-waving.

Every change to a number here needs a logged reason (docs/scoring.md, calibration protocol).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from bioverdict.store.models import ClaimType, EvidenceLevel, SourceKind

_L = {
    ClaimType.TARGET_CAUSAL: {
        EvidenceLevel.HUMAN_GENETICS: 1.0,
        EvidenceLevel.HUMAN_INTERVENTIONAL: 0.8,
        EvidenceLevel.HUMAN_OBSERVATIONAL: 0.5,
        EvidenceLevel.ANIMAL_IN_VIVO: 0.3,
        EvidenceLevel.IN_VITRO: 0.15,
    },
    ClaimType.DRUG_ACTS_IN_HUMANS: {
        EvidenceLevel.HUMAN_GENETICS: 0.4,
        EvidenceLevel.HUMAN_INTERVENTIONAL: 1.0,
        EvidenceLevel.HUMAN_OBSERVATIONAL: 0.4,
        EvidenceLevel.ANIMAL_IN_VIVO: 0.2,
        EvidenceLevel.IN_VITRO: 0.1,
    },
}
# Claims of another type use the weaker of the two columns per level.
_L[ClaimType.OTHER] = {
    lvl: min(_L[ClaimType.TARGET_CAUSAL][lvl], _L[ClaimType.DRUG_ACTS_IN_HUMANS][lvl])
    for lvl in EvidenceLevel
}

_Q = {
    SourceKind.PEER_REVIEWED: 1.0,
    SourceKind.REGULATOR: 1.0,
    SourceKind.REGISTRY: 1.0,
    SourceKind.PREPRINT: 0.7,
    SourceKind.COMPANY: 0.5,
    SourceKind.AI_INFERENCE: 0.3,
}


class ConfidenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level_weight: dict[ClaimType, dict[EvidenceLevel, float]] = Field(default_factory=lambda: _L)
    source_quality: dict[SourceKind, float] = Field(default_factory=lambda: _Q)
    p0: float = 0.5  # prior probability of a claim
    kappa: float = 1.2  # log-odds scale
    contra_multiplier: float = 1.0  # plan: may be 1.2 to offset LLM optimism
    independence_decay: float = 0.5  # k-th item of one lab/sponsor gets decay^(k-1)
    half_life_years: float = 10.0  # biological data lose value slowly
    unknown_date_recency: float = 0.8
    no_evidence_confidence: float = 0.3  # claim without a verified quote is ai_inference
    sparse_threshold: float = 0.5  # sum |w| below it: "too little data"
    contested_threshold: float = 0.8  # both sums above it: contested
    missing_link_threshold: float = 0.4  # chain link below it is a missing link
