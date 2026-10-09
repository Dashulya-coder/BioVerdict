"""Starting heuristics from the Unobio plan. Calibrated on the eval set, never by hand-waving.

Every change to a number here needs a logged reason (docs/scoring.md, calibration protocol).
"""

from __future__ import annotations

import copy

from pydantic import BaseModel, ConfigDict, Field

from bioverdict.store.models import ClaimType, EvidenceLevel, SourceKind

_L = {
    ClaimType.TARGET_CAUSAL: {
        EvidenceLevel.HUMAN_GENETICS: 1.0,
        EvidenceLevel.HUMAN_INTERVENTIONAL: 0.8,
        EvidenceLevel.HUMAN_OBSERVATIONAL: 0.5,
        EvidenceLevel.ANIMAL_IN_VIVO: 0.3,
        EvidenceLevel.IN_VITRO: 0.15,
        EvidenceLevel.REGISTRY_RECORD: 0.0,  # a planned trial is no evidence the target is causal
    },
    ClaimType.DRUG_ACTS_IN_HUMANS: {
        EvidenceLevel.HUMAN_GENETICS: 0.4,
        EvidenceLevel.HUMAN_INTERVENTIONAL: 1.0,
        EvidenceLevel.HUMAN_OBSERVATIONAL: 0.4,
        EvidenceLevel.ANIMAL_IN_VIVO: 0.2,
        EvidenceLevel.IN_VITRO: 0.1,
        EvidenceLevel.REGISTRY_RECORD: 0.0,  # nor that the drug works: only results show that
    },
}
# Claims of another type use the weaker of the two columns per level.
_L[ClaimType.OTHER] = {
    lvl: min(_L[ClaimType.TARGET_CAUSAL][lvl], _L[ClaimType.DRUG_ACTS_IN_HUMANS][lvl])
    for lvl in EvidenceLevel
}
# Facts about studies and programs (a trial was stopped, a competitor is in Phase 3, a sponsor
# dropped the program) are what the gate claims are about, and a registry record is exactly what
# establishes them. They get their own claim type so that this weight cannot leak into `other`
# claims such as "the molecule modulates its target".
_L[ClaimType.STUDY_FACT] = {**_L[ClaimType.DRUG_ACTS_IN_HUMANS], EvidenceLevel.REGISTRY_RECORD: 1.0}

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

    level_weight: dict[ClaimType, dict[EvidenceLevel, float]] = Field(
        default_factory=lambda: copy.deepcopy(_L)
    )
    source_quality: dict[SourceKind, float] = Field(default_factory=lambda: copy.deepcopy(_Q))
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


class VerdictConfig(BaseModel):
    """Thresholds of the verdict rule. Set after the eval run, not before."""

    model_config = ConfigDict(extra="forbid")

    t_gate: float = 0.6  # a soft gate (caps at Conditional) fires on a claim this confident
    # A hard gate means Do Not Invest, so it asks for more: one registry record alone reaches
    # about 0.77 and a stop reason can be "business decision", so a second independent
    # confirmation is needed. Calibrated on the eval set like every threshold.
    t_hard_gate: float = 0.85
    # ...and rests on more than one independence group: two records of one study (one sponsor)
    # reach 0.86 by themselves, which is not a second source.
    hard_gate_min_groups: int = 2
    t_near: float = 0.4  # below the firing threshold but above this: "almost fired"
    chain_min: float = 0.5  # Invest needs chain probability >= this
    key_claim_min: float = 0.7  # Invest needs every critical claim >= this
    rnpv_p50_min: float = 0.0  # Invest needs rNPV P50 above this
    no_critical_confidence: float = 0.3  # verdict confidence when no claim is marked critical
