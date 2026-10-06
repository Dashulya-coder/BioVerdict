"""Shared data model. Source of truth: the Unobio plan PDF, mirrored in docs/data-model.md.

"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Enums -------------------------------------------------------------------


class EvidenceLevel(StrEnum):
    """Strength hierarchy, strongest first."""

    HUMAN_GENETICS = "human_genetics"
    HUMAN_INTERVENTIONAL = "human_interventional"  # RCT, clinical trial data
    HUMAN_OBSERVATIONAL = "human_observational"
    ANIMAL_IN_VIVO = "animal_in_vivo"
    IN_VITRO = "in_vitro"


class EvidenceType(StrEnum):
    SOURCE_FACT = "source_fact"
    AI_INFERENCE = "ai_inference"


class SourceKind(StrEnum):
    """Drives the source-quality multiplier Q (peer-reviewed/regulator/registry 1.0, ...)."""

    PEER_REVIEWED = "peer_reviewed"
    REGULATOR = "regulator"
    REGISTRY = "registry"
    PREPRINT = "preprint"
    COMPANY = "company"  # press release or company presentation
    AI_INFERENCE = "ai_inference"


class Direction(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


class ClaimType(StrEnum):
    """Picks the column of the level-weight table L(level, claim type)."""

    TARGET_CAUSAL = "target_causal"  # "the target is causal for the disease"
    DRUG_ACTS_IN_HUMANS = "drug_acts_in_humans"
    OTHER = "other"


class Basis(StrEnum):
    EXTRACTED = "extracted"
    DERIVED = "derived"
    INFERRED = "inferred"
    MODELED = "modeled"
    HYPOTHESIS = "hypothesis"
    UNKNOWN = "unknown"


class SectionStatus(StrEnum):
    FOUND = "found"
    CONFLICTING = "conflicting"
    NOT_REPORTED = "not_reported"
    NONE_FOUND = "none_found"
    NOT_SEARCHED = "not_searched"
    ERROR = "error"
    INCOMPLETE = "incomplete"


class Section(StrEnum):
    UNMET_NEED = "unmet_need"
    MECHANISM = "mechanism"
    TRANSLATION = "translation"
    CLINICAL = "clinical"
    COMPETITION = "competition"
    COMMERCIAL = "commercial"
    IP_REGULATORY = "ip_regulatory"
    FLAGS = "flags"
    INVESTMENT = "investment"


class DiligenceType(StrEnum):
    PROPRIETARY_DATA = "proprietary_data"
    PATIENT_LEVEL_DATA = "patient_level_data"
    KOL_INTERVIEW = "kol_interview"
    EXPERIMENT = "experiment"
    CMC_DILIGENCE = "cmc_diligence"
    IP_DILIGENCE = "ip_diligence"


class Verdict(StrEnum):
    INVEST = "Invest"
    CONDITIONAL = "Conditional"
    DO_NOT_INVEST = "Do Not Invest"


class ServiceFlag(StrEnum):
    SPARSE = "sparse"  # sum |w| below threshold: "too little data"
    CONTESTED = "contested"  # strong support and strong contradiction at once
    MISSING_LINK = "missing_link"  # translation-chain link with confidence < 0.4


# --- Resolver ----------------------------------------------------------------


class Indication(_Model):
    name: str
    mondo_id: str | None = None
    efo_id: str | None = None


class Target(_Model):
    symbol: str
    uniprot: str | None = None
    ensembl: str | None = None


class ResolverOutput(_Model):
    """Normalized input. Several targets are allowed (retatrutide has three)."""

    indication: Indication
    targets: list[Target] = Field(min_length=1)
    action: str | None = None  # agonist | antagonist | inhibitor | degrader | knockdown | ...
    modality: str | None = None  # small molecule | antibody | siRNA | ASO | peptide | ...
    delivery: str | None = None  # oral | SC | IV | intrathecal | ...
    tissue: str | None = None
    known_assets: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(
        default_factory=list, description="Fields the system inferred itself"
    )


# --- Evidence, Claim, Bundle -------------------------------------------------


class Locator(_Model):
    type: str  # nct | pmid | doi | url | ...
    value: str


class Evidence(_Model):
    """One fact from one source. Stance lives on the claim link, not here."""

    id: str
    source: str
    source_family: str
    source_kind: SourceKind
    url: str
    locator: Locator | None = None
    excerpt: str = Field(min_length=1, description="Verbatim quote, used for span grounding")
    published_at: date | None = None
    retrieved_at: datetime
    type: EvidenceType = EvidenceType.SOURCE_FACT
    level: EvidenceLevel
    independence_group: str = Field(description="Lab or sponsor; repeats count once")
    version: int = Field(ge=1, description="Evidence-store version in which it appeared")


class ClaimEvidenceLink(_Model):
    claim_id: str
    evidence_id: str
    direction: Direction
    quote: str = Field(min_length=1, description="Must occur in the evidence excerpt")


class ConfidenceParts(_Model):
    support: float = Field(ge=0, le=1)
    contra: float = Field(ge=0, le=1)
    freshness: float = Field(ge=0, le=1)


class Claim(_Model):
    id: str
    run_id: str
    section: Section
    text: str
    claim_type: ClaimType = ClaimType.OTHER
    basis: Basis
    status: SectionStatus = SectionStatus.FOUND
    confidence: float = Field(ge=0, le=1)
    confidence_parts: ConfidenceParts | None = None
    flags: list[ServiceFlag] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    diligence_type: DiligenceType | None = None

    @model_validator(mode="after")
    def _unknown_needs_diligence_type(self) -> Claim:
        if self.basis is Basis.UNKNOWN and self.diligence_type is None:
            raise ValueError("an `unknown` claim must carry a diligence_type")
        return self


class Bundle(_Model):
    """Frozen, content-hashed evidence snapshot. The reasoning phase reads only this."""

    bundle_id: str
    run_id: str
    version: int = Field(ge=1)
    as_of: date
    content_hash: str
    catalog: list[str] = Field(description="URLs and IDs actually fetched in this run")
    evidence: list[Evidence] = Field(default_factory=list)
    section_statuses: dict[Section, SectionStatus] = Field(default_factory=dict)
    created_at: datetime

    def evidence_by_id(self) -> dict[str, Evidence]:
        return {e.id: e for e in self.evidence}


def quote_is_grounded(link: ClaimEvidenceLink, bundle: Bundle) -> bool:
    """A link is grounded only if its quote occurs verbatim in the evidence excerpt."""
    evidence = bundle.evidence_by_id().get(link.evidence_id)
    return evidence is not None and link.quote in evidence.excerpt


# --- Scoring, verification, LLM ----------------------------------------------


class Range(_Model):
    """P10 / P50 / P90 instead of a single number."""

    p10: float
    p50: float
    p90: float

    @model_validator(mode="after")
    def _ordered(self) -> Range:
        if not self.p10 <= self.p50 <= self.p90:
            raise ValueError("expected p10 <= p50 <= p90")
        return self


class GateResult(_Model):
    gate_id: str  # K1..K5 (hard), S1..S6 (soft)
    kind: Literal["hard", "soft"]
    fired: bool
    claim_ids: list[str] = Field(default_factory=list)
    near_miss: str | None = Field(
        default=None, description="Feeds 'What would change our mind' when almost fired"
    )


class DiligenceQuestion(_Model):
    text: str
    answered_by: DiligenceType
    value_of_information: float


class VerdictResult(_Model):
    verdict: Verdict
    confidence: float = Field(ge=0, le=1)
    gates: list[GateResult] = Field(default_factory=list)
    translation_chain_probability: float | None = Field(default=None, ge=0, le=1)
    pos: Range | None = None
    rnpv: Range | None = None
    capital: Range | None = None  # USD
    months_to_milestone: Range | None = None
    top_risks: list[str] = Field(default_factory=list, max_length=3)
    what_would_change_our_mind: list[str] = Field(default_factory=list)
    diligence_questions: list[DiligenceQuestion] = Field(default_factory=list)


class VerificationCheck(_Model):
    claim_id: str
    check_name: str  # quote_in_source | entailment | authority | temporal_validity
    passed: bool
    detail: str = ""


class VerificationReport(_Model):
    checks: list[VerificationCheck] = Field(default_factory=list)
    dropped_claim_ids: list[str] = Field(default_factory=list)


class LLMResult(_Model):
    step: str
    provider: str
    model: str
    parsed: dict | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    attempts: int = 1
    cache_hit: bool = False
    failover_from: str | None = None


class TamEstimate(_Model):
    """Market size derived by code from raw epidemiology and pricing data."""

    addressable_patients: Range
    annual_price_usd: Range
    tam_usd: Range
    evidence_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
