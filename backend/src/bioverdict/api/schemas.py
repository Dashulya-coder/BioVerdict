"""What the API returns. This is the contract the report and evidence screens are built on.

Every claim carries its links, every link carries the evidence it quotes, and every item says
whether it is a `source_fact` (copied from a source) or an `ai_inference` (a model's judgement),
so the UI can show `Recommendation -> Claims -> Evidence -> Sources` without further requests.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from bioverdict.scoring.module_answers import ModuleAnswer, ModuleId
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
    Implication,
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


class CheckView(_View):
    """A verification check the claim did not pass, in the words the check logged."""

    check: str = Field(description="entailment | source_authority | claim_downgraded")
    detail: str


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
    implication: Implication
    diligence_type: str | None
    depends_on: list[str]
    links: list[LinkView]
    checks: list[CheckView] = Field(
        default_factory=list,
        description="Checks the claim failed: why a quote was removed or the claim lost its weight",
    )


class SectionView(_View):
    section: Section
    status: SectionStatus
    claims: list[ClaimView]


class ChainLinkView(_View):
    link: ChainLink
    status: ChainStatus
    confidence: float | None = Field(description="Best claim confidence for this link, if any")
    claim_ids: list[str]


class DriverView(_View):
    claim_id: str
    contribution: float = Field(
        description="Pull on the module: above 0 speaks for investing, below 0 against"
    )


class ModuleView(_View):
    """One of the six underwriting modules: its answer and the claims the answer rests on.

    Computed by code from the claims (`scoring/module_answers.py`); open `claim_ids` in
    `sections` to follow answer -> claims -> quotes -> sources.
    """

    module: ModuleId
    title: str
    question: str
    answer: ModuleAnswer
    headline: str = Field(description="The rule that decided the answer, in words")
    balance: float | None = Field(
        description="-1 (all weight against) to +1 (all for); null without weighted claims"
    )
    favourable: float
    unfavourable: float
    claim_ids: list[str]
    drivers: list[DriverView] = Field(description="The claims that pull hardest, strongest first")
    unknown_count: int
    evidence_count: int = Field(description="Distinct evidence items the module's claims quote")
    gates: list[str] = Field(description="Fired gates that rest on this module's claims")


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
    modules: list[ModuleView] = Field(description="The six modules, each with its answer")
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


# --- market size (A9) ----------------------------------------------------------------------


class MarketResponse(_View):
    """Market size computed by code from the run's bundle. A model's judgement is nowhere in it,
    but its simplifications are: read `assumptions` with every number."""

    run_id: str
    label: Literal["modeled"] = "modeled"
    patients: Range | None
    patients_basis: str | None
    annual_price_usd: Range | None
    tam_usd: Range | None
    range_basis: str = Field(
        description="What p10, p50 and p90 are in the ranges above: bounds, not percentiles"
    )
    assumptions: list[str]
    warnings: list[str] = Field(
        default_factory=list, description="Why a number should not be read as a market"
    )
    missing: list[str] = Field(description="What could not be computed, and why")
    sources: list[EvidenceView] = Field(description="The records every number was read from")


# --- PoS, rNPV, capital (B7) ----------------------------------------------------------------


class TornadoBar(_View):
    input: str
    at_low: float = Field(description="rNPV (USD) with this input at its low end, others at base")
    at_high: float = Field(description="rNPV (USD) with this input at its high end")


class FinancialsResponse(_View):
    """PoS and rNPV computed by code from the run's bundle. Everything is `modeled`: read
    `assumptions` with every number. Inputs no source supports are placeholders."""

    run_id: str
    label: Literal["modeled"] = "modeled"
    stage: str | None
    area: str | None
    pos: Range | None
    rnpv: Range | None
    capital_usd: Range | None = Field(description="Cost of all remaining phases, not risk-weighted")
    months_to_milestone: Range | None
    probability_positive: float | None
    tornado: list[TornadoBar]
    assumptions: list[str]
    missing: list[str] = Field(description="What could not be computed, and why")
    sources: list[EvidenceView]


# --- adding evidence and comparing runs (A7) ---------------------------------------------------


MAX_ADDED_TEXT = 6000  # characters of one added excerpt


class AddedEvidence(_View):
    """One document an analyst adds to a finished run. Its labels are the submitter's own."""

    # The text goes into every reasoning prompt (four of them): a cap keeps ten pasted papers from
    # becoming a very large, very expensive run. About 1,500 tokens an item.
    text: str = Field(
        min_length=20, max_length=MAX_ADDED_TEXT, description="Verbatim excerpt of the document"
    )
    url: str = Field(
        pattern=r"^https?://\S+$", max_length=500, description="Where the excerpt was copied from"
    )
    source: str = Field(
        min_length=1, max_length=200, description="Name of the source, e.g. the journal"
    )
    source_kind: SourceKind
    level: EvidenceLevel
    published_at: date | None = None


class AddEvidenceRequest(_View):
    evidence: list[AddedEvidence] = Field(min_length=1, max_length=10)
    as_of: date | None = Field(
        default=None, description="Cutoff of the new run; not earlier than the original's"
    )


class RunSide(_View):
    """One of the two runs being compared."""

    run_id: str
    as_of: date
    bundle_version: int
    content_hash: str
    evidence_count: int
    verdict: Verdict
    confidence: float
    translation_chain_probability: float | None


class GateChange(_View):
    gate_id: GateId
    kind: Literal["hard", "soft"]
    fired_before: bool
    fired_after: bool


class ChainLinkChange(_View):
    link: ChainLink
    status_before: ChainStatus
    status_after: ChainStatus
    confidence_before: float | None
    confidence_after: float | None


class ClaimSnapshot(_View):
    id: str
    basis: Basis
    confidence: float
    gate_signals: list[GateId]
    critical: bool


class ClaimChange(_View):
    """A claim present in only one run, or stated in both with a different footing."""

    change: Literal["added", "removed", "changed"]
    section: Section
    text: str
    before: ClaimSnapshot | None
    after: ClaimSnapshot | None
    new_evidence_ids: list[str] = Field(
        description="Evidence absent from the base run that this claim quotes in the other run"
    )


class ModuleCause(_View):
    """A piece of evidence the earlier run did not have, and the claim it moved."""

    evidence_id: str = Field(description="Its id in the later run")
    source: str
    url: str
    published_at: date | None
    level: EvidenceLevel
    direction: Direction
    quote: str
    claim_id: str = Field(description="The claim's id in the later run")
    claim_text: str
    claim_change: Literal["added", "changed"]
    confidence_before: float | None
    confidence_after: float
    contribution_before: float | None
    contribution_after: float


class ModuleChange(_View):
    """One module in both runs. `causes` is empty when no new evidence touched it."""

    module: ModuleId
    title: str
    answer_before: ModuleAnswer
    answer_after: ModuleAnswer
    balance_before: float | None
    balance_after: float | None
    headline_before: str
    headline_after: str
    changed: bool = Field(description="The answer differs, or the balance moved")
    causes: list[ModuleCause]


class DiffResponse(_View):
    """What differs between two finished runs. Computed by code from the stored records."""

    base: RunSide
    head: RunSide
    verdict_changed: bool
    modules: list[ModuleChange] = Field(
        description="All six modules, before and after, with the new evidence that moved each"
    )
    gates: list[GateChange] = Field(description="Only the gates whose state differs")
    chain: list[ChainLinkChange] = Field(description="Only the links whose status differs")
    evidence_added: list[EvidenceView]
    evidence_removed: list[EvidenceView]
    claims: list[ClaimChange]
    unchanged_claims: int
    matching: str = Field(description="How claims and evidence of the two runs were paired")
