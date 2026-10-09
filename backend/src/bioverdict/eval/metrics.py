"""What one finished run looks like in numbers, read from its stored records (docs/eval.md).

Everything here is counted by code. Nothing asks a model, so these metrics say whether a report
is grounded and honest about gaps, not whether its claims are true (that is the entailment
judge, B8).
"""

from __future__ import annotations

import sqlite3

from pydantic import BaseModel, ConfigDict

from bioverdict.pipeline.reason_score import DROPPED_CHECK, QUOTE_CHECK
from bioverdict.reasoning.modules import ALL_MODULES
from bioverdict.store.load_bundle import load_bundle
from bioverdict.store.models import Basis, Section, SectionStatus
from bioverdict.store.runs_repo import DONE, get_run, load_claims, load_events
from bioverdict.store.verification_repo import load_checks

# The sections the reasoning modules write: a report must say something about each of them.
REQUIRED_SECTIONS = tuple(dict.fromkeys(module.section for module in ALL_MODULES))


class RunMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str
    failure: str | None = None  # the reason a failed run recorded
    verdict: str | None = None
    confidence: float | None = None
    top_risks: list[str] = []

    evidence: int = 0
    claims: int = 0
    unknown_claims: int = 0
    unknown_with_diligence_type: int = 0  # an honest unknown says what data would answer it
    links: int = 0
    quotes_present: int = 0  # links whose quote is verbatim in the evidence it names
    cited_evidence: int = 0
    cited_in_catalog: int = 0  # cited evidence whose address is in the bundle catalog
    sections_covered: int = 0  # required sections with at least one claim, unknowns included
    sections_required: int = len(REQUIRED_SECTIONS)
    section_statuses: dict[Section, SectionStatus] = {}
    citations_rejected: int = 0  # citations the model proposed and code could not ground
    claims_dropped: int = 0  # claims removed because of that
    other_corrections: int = 0

    seconds: float | None = None
    llm_calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


def run_metrics(conn: sqlite3.Connection, run_id: str) -> RunMetrics:
    run = get_run(conn, run_id)
    if run is None:
        raise LookupError(f"run {run_id} not found")
    metrics = RunMetrics(run_id=run_id, status=run.status, verdict=run.verdict)
    if run.finished_at is not None:
        metrics.seconds = (run.finished_at - run.created_at).total_seconds()
    calls = conn.execute(
        "SELECT COUNT(*) AS calls, COALESCE(SUM(cache_hit), 0) AS hits, "
        "COALESCE(SUM(input_tokens), 0) AS input, COALESCE(SUM(output_tokens), 0) AS output, "
        "COALESCE(SUM(cost_usd), 0) AS cost FROM llm_calls WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    metrics.llm_calls, metrics.cache_hits = calls["calls"], calls["hits"]
    metrics.input_tokens, metrics.output_tokens = calls["input"], calls["output"]
    metrics.cost_usd = calls["cost"]

    if run.status != DONE or run.result is None:
        failed = [e.detail for e in load_events(conn, run_id) if e.status == "failed"]
        metrics.failure = failed[-1] if failed else "the run did not finish"
        return metrics

    metrics.confidence, metrics.top_risks = run.result.confidence, run.result.top_risks
    bundle = load_bundle(conn, run_id)
    evidence, catalog = bundle.evidence_by_id(), set(bundle.catalog)
    claims, links = load_claims(conn, run_id)
    unknown = [c for c in claims if c.basis is Basis.UNKNOWN]
    cited = {link.evidence_id for link in links}
    checks = load_checks(conn, run_id)

    metrics.evidence, metrics.section_statuses = len(bundle.evidence), bundle.section_statuses
    metrics.claims, metrics.unknown_claims = len(claims), len(unknown)
    metrics.unknown_with_diligence_type = sum(c.diligence_type is not None for c in unknown)
    metrics.links = len(links)
    metrics.quotes_present = sum(
        link.evidence_id in evidence and link.quote in evidence[link.evidence_id].excerpt
        for link in links
    )
    metrics.cited_evidence = len(cited)
    metrics.cited_in_catalog = sum(
        evidence_id in evidence and evidence[evidence_id].url in catalog for evidence_id in cited
    )
    metrics.sections_covered = len({c.section for c in claims} & set(REQUIRED_SECTIONS))
    metrics.citations_rejected = sum(c.check_name == QUOTE_CHECK for c in checks)
    metrics.claims_dropped = sum(c.check_name == DROPPED_CHECK for c in checks)
    metrics.other_corrections = len(checks) - metrics.citations_rejected - metrics.claims_dropped
    return metrics
