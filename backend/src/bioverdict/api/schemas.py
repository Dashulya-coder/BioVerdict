"""What the API returns. This is the contract the report and evidence screens are built on.

Every claim carries its links, every link carries the evidence it quotes, and every item says
whether it is a `source_fact` (copied from a source) or an `ai_inference` (a model's judgement),
so the UI can show `Recommendation -> Claims -> Evidence -> Sources` without further requests.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from bioverdict.store.models import (
    Basis,
    ChainLink,
    ClaimType,
    ConfidenceParts,
    DiligenceQuestion,
    Direction,
    EvidenceLevel,
    GateId,
    GateResult,
    Locator,
    Range,
    Section,
    SectionStatus,
    ServiceFlag,
    SourceKind,
    Verdict,
)

Badge = Literal["source_fact", "ai_inference", "unknown"]
ChainStatus = Literal["supported", "weak", "missing"]


class _View(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunRequest(_View):
    """Start a run. Give an asset (name or code), or an indication with a mechanism."""

    asset: str | None = Field(default=None, description="Drug name or company code")
    indication: str | None = None
    mechanism: str | None = None
    as_of: date | None = Field(default=None, description="Analyse as of this date (default today)")


class RunCreated(_View):
    run_id: str
    status: str


class RunSummary(_View):
    run_id: str
    status: str
    verdict: str | None
    as_of: date
    created_at: datetime
    finished_at: datetime | None
    input: dict


class EvidenceView(_View):
    id: str
    source: str
    source_family: str
    source_kind: SourceKind
    url: str
    locator: Locator | None
    excerpt: str
    published_at: date | None
    retrieved_at: datetime
    level: EvidenceLevel
    independence_group: str
    badge: Badge
    claim_ids: list[str] = Field(description="The claims that quote this evidence")


class LinkView(_View):
    evidence_id: str
    direction: Direction
    quote: str
    source: str
    url: str
    source_kind: SourceKind
    level: EvidenceLevel
    published_at: date | None
    badge: Badge


class ClaimView(_View):
    id: str
    section: Section
    text: str
    claim_type: ClaimType
    basis: Basis
    badge: Badge
    status: SectionStatus
    confidence: float
    confidence_parts: ConfidenceParts | None
    flags: list[ServiceFlag]
    chain_link: ChainLink | None
    gate_signals: list[GateId]
    critical: bool
    diligence_type: str | None
    depends_on: list[str]
    links: list[LinkView]


class SectionView(_View):
    section: Section
    status: SectionStatus
    claims: list[ClaimView]


class ChainLinkView(_View):
    link: ChainLink
    status: ChainStatus
    confidence: float | None = Field(description="Best claim confidence for this link, if any")
    claim_ids: list[str]


class ExecutiveVerdict(_View):
    verdict: Verdict
    confidence: float
    top_risks: list[str]
    what_would_change_our_mind: list[str]
    capital: Range | None = Field(description="USD, from the investment model once it exists")
    months_to_milestone: Range | None
    pos: Range | None
    rnpv: Range | None


class BundleInfo(_View):
    bundle_id: str
    version: int
    content_hash: str
    as_of: date
    evidence_count: int
    section_statuses: dict[Section, SectionStatus]


class ReportResponse(_View):
    run: RunSummary
    executive: ExecutiveVerdict
    assumptions: list[str] = Field(description="What the system inferred or could not confirm")
    sections: list[SectionView]
    translation_chain: list[ChainLinkView]
    translation_chain_probability: float | None
    gates: list[GateResult]
    diligence_questions: list[DiligenceQuestion]
    sources: list[EvidenceView]
    bundle: BundleInfo


class EventView(_View):
    seq: int
    step: str
    status: str
    detail: str
    created_at: datetime


class LLMCallView(_View):
    step: str
    provider: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int | None
    attempts: int | None
    cache_hit: bool
    failover_from: str | None
    error: str | None


class TraceTotals(_View):
    input_tokens: int
    output_tokens: int
    cost_usd: float
    calls: int


class TraceResponse(_View):
    run_id: str
    events: list[EventView]
    llm_calls: list[LLMCallView]
    totals: TraceTotals
