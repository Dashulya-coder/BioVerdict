"""Turning the records of a finished run into the views the API returns."""

from __future__ import annotations

import sqlite3

from bioverdict.api.schemas import (
    Badge,
    BundleInfo,
    ChainLinkView,
    ChainStatus,
    ClaimView,
    DriverView,
    EventView,
    EvidenceView,
    ExecutiveVerdict,
    FinancialsResponse,
    LinkView,
    LLMCallView,
    MarketResponse,
    ModuleView,
    ReportResponse,
    RunSummary,
    SectionView,
    TornadoBar,
    TraceResponse,
    TraceTotals,
)
from bioverdict.market.tam import estimate_market
from bioverdict.pipeline.reason_score import run_financials
from bioverdict.scoring.config import ConfidenceConfig, VerdictConfig
from bioverdict.scoring.module_answers import ModuleResult, module_answers
from bioverdict.scoring.verdict import chain_confidences
from bioverdict.store.load_bundle import load_bundle
from bioverdict.store.models import (
    Basis,
    Bundle,
    ChainLink,
    Claim,
    ClaimEvidenceLink,
    Evidence,
    EvidenceType,
    ResolverOutput,
    Section,
    SectionStatus,
    VerdictResult,
)
from bioverdict.store.runs_repo import DONE, RunRecord, get_run, load_claims, load_events


class RunNotFoundError(LookupError):
    pass


class RunNotReadyError(RuntimeError):
    """The run has no report yet: it is still running or it failed."""


class ItemNotFoundError(LookupError):
    pass


_CLAIM_BADGE: dict[Basis, Badge] = {
    Basis.EXTRACTED: "source_fact",
    Basis.DERIVED: "source_fact",
    Basis.INFERRED: "ai_inference",
    Basis.HYPOTHESIS: "ai_inference",
    Basis.MODELED: "ai_inference",
    Basis.UNKNOWN: "unknown",
}


def _evidence_badge(evidence: Evidence) -> Badge:
    return "source_fact" if evidence.type is EvidenceType.SOURCE_FACT else "ai_inference"


def run_summary(record: RunRecord) -> RunSummary:
    return RunSummary(
        run_id=record.run_id,
        status=record.status,
        verdict=record.verdict,
        as_of=record.as_of,
        created_at=record.created_at,
        finished_at=record.finished_at,
        input=record.input,
    )


def require_run(conn: sqlite3.Connection, run_id: str) -> RunRecord:
    record = get_run(conn, run_id)
    if record is None:
        raise RunNotFoundError(run_id)
    return record


def require_finished(conn: sqlite3.Connection, run_id: str) -> RunRecord:
    record = require_run(conn, run_id)
    if record.status != DONE or record.result is None or record.resolver is None:
        raise RunNotReadyError(f"run {run_id} is {record.status}, there is no report yet")
    return record


def _link_view(link: ClaimEvidenceLink, evidence: Evidence) -> LinkView:
    return LinkView(
        evidence_id=evidence.id,
        direction=link.direction,
        quote=link.quote,
        source=evidence.source,
        url=evidence.url,
        source_kind=evidence.source_kind,
        level=evidence.level,
        published_at=evidence.published_at,
        badge=_evidence_badge(evidence),
    )


def _claim_view(
    claim: Claim, links: list[ClaimEvidenceLink], evidence: dict[str, Evidence]
) -> ClaimView:
    return ClaimView(
        id=claim.id,
        section=claim.section,
        text=claim.text,
        claim_type=claim.claim_type,
        basis=claim.basis,
        badge=_CLAIM_BADGE[claim.basis],
        status=claim.status,
        confidence=claim.confidence,
        confidence_parts=claim.confidence_parts,
        flags=claim.flags,
        chain_link=claim.chain_link,
        gate_signals=claim.gate_signals,
        critical=claim.critical,
        implication=claim.implication,
        diligence_type=claim.diligence_type.value if claim.diligence_type else None,
        depends_on=claim.depends_on,
        links=[
            _link_view(link, evidence[link.evidence_id])
            for link in links
            if link.claim_id == claim.id and link.evidence_id in evidence
        ],
    )


def evidence_view(evidence: Evidence, links: list[ClaimEvidenceLink]) -> EvidenceView:
    cited_by = sorted({link.claim_id for link in links if link.evidence_id == evidence.id})
    return EvidenceView(
        id=evidence.id,
        source=evidence.source,
        source_family=evidence.source_family,
        source_kind=evidence.source_kind,
        url=evidence.url,
        locator=evidence.locator,
        excerpt=evidence.excerpt,
        published_at=evidence.published_at,
        retrieved_at=evidence.retrieved_at,
        level=evidence.level,
        independence_group=evidence.independence_group,
        badge=_evidence_badge(evidence),
        claim_ids=cited_by,
    )


def chain_status(confidence: float | None) -> ChainStatus:
    """Missing below the scoring threshold (or with no claim), supported at the key-claim bar."""
    if confidence is None or confidence < ConfidenceConfig().missing_link_threshold:
        return "missing"
    return "supported" if confidence >= VerdictConfig().key_claim_min else "weak"


def translation_chain(claims: list[Claim]) -> list[ChainLinkView]:
    confidences = chain_confidences(claims)
    return [
        ChainLinkView(
            link=link,
            status=chain_status(confidence),
            confidence=confidence,
            claim_ids=[c.id for c in claims if c.chain_link is link],
        )
        for link, confidence in zip(ChainLink, confidences, strict=True)
    ]


def module_view(result: ModuleResult) -> ModuleView:
    return ModuleView(
        module=result.module,
        title=result.title,
        question=result.question,
        answer=result.answer,
        headline=result.headline,
        balance=result.balance,
        favourable=result.favourable,
        unfavourable=result.unfavourable,
        claim_ids=result.claim_ids,
        drivers=[
            DriverView(claim_id=d.claim_id, contribution=d.contribution) for d in result.drivers
        ],
        unknown_count=result.unknown_count,
        evidence_count=result.evidence_count,
        gates=result.gates,
    )


def module_views(
    claims: list[Claim], links: list[ClaimEvidenceLink], result: VerdictResult
) -> list[ModuleView]:
    return [module_view(m) for m in module_answers(claims, links, result)]


def _sections(claims: list[ClaimView], bundle: Bundle) -> list[SectionView]:
    views = []
    for section in Section:
        in_section = sorted(
            (c for c in claims if c.section is section), key=lambda c: (not c.critical, c.id)
        )
        known = bundle.section_statuses.get(section)
        if not in_section and known is None:
            continue
        status = known or SectionStatus.FOUND
        views.append(SectionView(section=section, status=status, claims=in_section))
    return views


def build_report(conn: sqlite3.Connection, run_id: str) -> ReportResponse:
    record = require_finished(conn, run_id)
    assert record.result is not None and record.resolver is not None
    bundle = load_bundle(conn, run_id)
    claims, links = load_claims(conn, run_id)
    evidence = bundle.evidence_by_id()

    claim_views = [_claim_view(c, links, evidence) for c in claims]
    cited = {link.evidence_id for link in links}
    sources = [evidence_view(e, links) for e in bundle.evidence if e.id in cited]
    result = record.result

    return ReportResponse(
        run=run_summary(record),
        executive=ExecutiveVerdict(
            verdict=result.verdict,
            confidence=result.confidence,
            top_risks=result.top_risks,
            top_risk_claims=result.top_risk_claims,
            what_would_change_our_mind=result.what_would_change_our_mind,
            capital=result.capital,
            months_to_milestone=result.months_to_milestone,
            pos=result.pos,
            rnpv=result.rnpv,
        ),
        assumptions=record.resolver.assumptions,
        modules=module_views(claims, links, result),
        sections=_sections(claim_views, bundle),
        translation_chain=translation_chain(claims),
        translation_chain_probability=result.translation_chain_probability,
        gates=result.gates,
        diligence_questions=result.diligence_questions,
        sources=sources,
        bundle=BundleInfo(
            bundle_id=bundle.bundle_id,
            version=bundle.version,
            content_hash=bundle.content_hash,
            as_of=bundle.as_of,
            evidence_count=len(bundle.evidence),
            section_statuses=bundle.section_statuses,
        ),
    )


def get_claim(conn: sqlite3.Connection, run_id: str, claim_id: str) -> ClaimView:
    require_run(conn, run_id)
    claims, links = load_claims(conn, run_id)
    claim = next((c for c in claims if c.id == claim_id), None)
    if claim is None:
        raise ItemNotFoundError(f"claim {claim_id} is not in run {run_id}")
    return _claim_view(claim, links, load_bundle(conn, run_id).evidence_by_id())


def get_evidence(conn: sqlite3.Connection, run_id: str, evidence_id: str) -> EvidenceView:
    require_run(conn, run_id)
    bundle = load_bundle(conn, run_id)
    item = bundle.evidence_by_id().get(evidence_id)
    if item is None:
        raise ItemNotFoundError(f"evidence {evidence_id} is not in run {run_id}")
    _, links = load_claims(conn, run_id)
    return evidence_view(item, links)


def get_resolver(conn: sqlite3.Connection, run_id: str) -> ResolverOutput:
    """What the run resolved its input to; not ready until the resolve step has finished."""
    record = require_run(conn, run_id)
    if record.resolver is None:
        raise RunNotReadyError(f"run {run_id} has not resolved its input yet")
    return record.resolver


def list_evidence(conn: sqlite3.Connection, run_id: str) -> list[EvidenceView]:
    """The whole frozen bundle, cited or not; not ready until the bundle is frozen."""
    require_run(conn, run_id)
    try:
        bundle = load_bundle(conn, run_id)
    except LookupError as exc:
        raise RunNotReadyError(f"run {run_id} has no frozen bundle yet") from exc
    _, links = load_claims(conn, run_id)
    return [evidence_view(item, links) for item in bundle.evidence]


def build_market(conn: sqlite3.Connection, run_id: str) -> MarketResponse:
    """The market size of the run's bundle; not ready until the bundle is frozen."""
    require_run(conn, run_id)
    try:
        bundle = load_bundle(conn, run_id)
    except LookupError as exc:
        raise RunNotReadyError(f"run {run_id} has no frozen bundle yet") from exc
    estimate = estimate_market(bundle)
    _, links = load_claims(conn, run_id)
    by_id = bundle.evidence_by_id()
    return MarketResponse(
        run_id=run_id,
        patients=estimate.patients,
        patients_basis=estimate.patients_basis,
        annual_price_usd=estimate.annual_price_usd,
        tam_usd=estimate.tam.tam_usd if estimate.tam else None,
        range_basis=estimate.range_basis,
        assumptions=estimate.assumptions,
        warnings=estimate.warnings,
        missing=estimate.missing,
        sources=[evidence_view(by_id[evidence_id], links) for evidence_id in estimate.evidence_ids],
    )


def build_financials(conn: sqlite3.Connection, run_id: str) -> FinancialsResponse:
    """PoS, rNPV, capital and the tornado of the run's bundle; same bundle, same numbers."""
    require_run(conn, run_id)
    try:
        bundle = load_bundle(conn, run_id)
    except LookupError as exc:
        raise RunNotReadyError(f"run {run_id} has no frozen bundle yet") from exc
    fin = run_financials(conn, run_id, bundle)
    _, links = load_claims(conn, run_id)
    by_id = bundle.evidence_by_id()
    rnpv = fin.rnpv
    return FinancialsResponse(
        run_id=run_id,
        stage=fin.stage,
        area=fin.area,
        pos=fin.pos.pos if fin.pos else None,
        rnpv=rnpv.rnpv if rnpv else None,
        capital_usd=rnpv.capital if rnpv else None,
        months_to_milestone=rnpv.months_to_milestone if rnpv else None,
        probability_positive=rnpv.probability_positive if rnpv else None,
        tornado=[TornadoBar(input=n, at_low=lo, at_high=hi) for n, lo, hi in rnpv.tornado]
        if rnpv
        else [],
        assumptions=fin.assumptions,
        missing=fin.missing,
        sources=[evidence_view(by_id[i], links) for i in fin.evidence_ids],
    )


def build_trace(conn: sqlite3.Connection, run_id: str) -> TraceResponse:
    require_run(conn, run_id)
    events = [
        EventView(seq=e.seq, step=e.step, status=e.status, detail=e.detail, created_at=e.created_at)
        for e in load_events(conn, run_id)
    ]
    calls = [
        LLMCallView(
            step=row["step"],
            provider=row["provider"],
            model=row["model"],
            input_tokens=row["input_tokens"] or 0,
            output_tokens=row["output_tokens"] or 0,
            cost_usd=row["cost_usd"] or 0.0,
            latency_ms=row["latency_ms"],
            attempts=row["attempts"],
            cache_hit=bool(row["cache_hit"]),
            failover_from=row["failover_from"],
            error=row["error"],
        )
        for row in conn.execute("SELECT * FROM llm_calls WHERE run_id = ? ORDER BY id", (run_id,))
    ]
    return TraceResponse(
        run_id=run_id,
        events=events,
        llm_calls=calls,
        totals=TraceTotals(
            input_tokens=sum(c.input_tokens for c in calls),
            output_tokens=sum(c.output_tokens for c in calls),
            cost_usd=sum(c.cost_usd for c in calls),
            calls=len(calls),
        ),
    )
