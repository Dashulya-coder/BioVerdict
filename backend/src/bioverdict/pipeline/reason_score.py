"""The second half of every run: reason over the frozen bundle, then score (fixture and live).

Nothing here touches the network. The bundle is the whole world and the model is whatever the
caller injects: canned answers for a fixture run, the real client for a live one.
"""

from __future__ import annotations

import logging
import sqlite3

from bioverdict.contracts import LLM
from bioverdict.llm.errors import LLMError
from bioverdict.reasoning import ModuleReasoner
from bioverdict.reasoning.critique import ask, challenge
from bioverdict.reasoning.grounding import Drop, fill_missing_chain_links
from bioverdict.reasoning.modules import ALL_MODULES
from bioverdict.reasoning.prompts import question_text
from bioverdict.scoring.confidence import apply_confidence
from bioverdict.scoring.financials import Financials, financial_model, with_financials
from bioverdict.scoring.verdict import score_verdict
from bioverdict.store.models import (
    Basis,
    Bundle,
    Claim,
    ClaimEvidenceLink,
    DiligenceQuestion,
    VerdictResult,
    VerificationCheck,
)
from bioverdict.store.runs_repo import DONE, add_event, finish_run, get_run, save_claims
from bioverdict.store.verification_repo import save_checks
from bioverdict.verification import rule_checks, verify_links

log = logging.getLogger(__name__)

QUOTE_CHECK = "quote_in_source"  # a citation that code could not ground in the bundle
DROPPED_CHECK = "claim_dropped"  # the claim was removed from the report for that reason


def drop_checks(drops: list[Drop], rejected: set[str]) -> list[VerificationCheck]:
    """What code removed or changed, for the verification log: nothing is dropped silently.

    A failed citation is a failed `quote_in_source` check. Other corrections (a gate or a claim
    type the module may not set, a repeated link) are logged under their own kind.
    """
    checks = [
        VerificationCheck(
            claim_id=drop.claim_id,
            check_name=QUOTE_CHECK if drop.is_citation_failure else drop.kind.value,
            passed=False,
            detail=f"{drop.what}: {drop.reason}",
        )
        for drop in drops
    ]
    checks += [
        VerificationCheck(
            claim_id=claim_id,
            check_name=DROPPED_CHECK,
            passed=False,
            detail="no grounded citation left, or one of its citations failed",
        )
        for claim_id in sorted(rejected)
    ]
    return checks


def run_financials(conn: sqlite3.Connection, run_id: str, bundle: Bundle) -> Financials:
    """PoS and rNPV of the run's bundle, for the question the run resolved.

    A question with no drug in it (an indication and a mechanism) is about the class: its stage
    is the most advanced program of the class in the bundle.
    """
    record = get_run(conn, run_id)
    resolver = record.resolver if record is not None else None
    if resolver is None:
        return financial_model(bundle, "")
    about_class = not resolver.assets and not resolver.known_assets
    return financial_model(bundle, resolver.indication.name, class_question=about_class)


def _question(conn: sqlite3.Connection, run_id: str) -> str:
    """The resolved question for the prompts ("" when the run has no resolved input)."""
    record = get_run(conn, run_id)
    resolver = record.resolver if record is not None else None
    return question_text(resolver) if resolver is not None else ""


def skeptic_pass(
    conn: sqlite3.Connection,
    run_id: str,
    bundle: Bundle,
    llm: LLM,
    claims: list[Claim],
    links: list[ClaimEvidenceLink],
) -> tuple[list[Claim], list[ClaimEvidenceLink], list[str]]:
    """Objections grounded in the bundle become `contradicts` links; confidence follows by formula.

    The Skeptic is advisory: when its model call fails the report is made without it, and the
    run says so in its events. Returns the claims, the links and the text of the kept objections.
    """
    add_event(conn, run_id, "skeptic", "started")
    try:
        found = challenge(llm, bundle, claims, links)
    except LLMError as exc:
        log.warning("skeptic skipped for %s: %s", run_id, exc)
        add_event(conn, run_id, "skeptic", "skipped", f"{type(exc).__name__}")
        return claims, links, []
    save_checks(conn, run_id, found.checks)
    dropped = sum(not c.passed for c in found.checks)
    add_event(
        conn,
        run_id,
        "skeptic",
        "done",
        f"{len(found.links)} objection(s) grounded in the evidence, {dropped} dropped by code",
    )
    if not found.links:
        return claims, links, found.objections
    links = [*links, *found.links]
    claims = apply_confidence(claims, links, bundle.evidence_by_id(), bundle.as_of)
    return claims, links, found.objections


def verify_pass(
    conn: sqlite3.Connection,
    run_id: str,
    bundle: Bundle,
    llm: LLM,
    claims: list[Claim],
    links: list[ClaimEvidenceLink],
    only: set[tuple[str, str]] | None = None,
    rules: bool = True,
) -> tuple[list[Claim], list[ClaimEvidenceLink]]:
    """Entailment judge, then the authority and temporal rules (docs/architecture.md, section 7).

    A link the judge does not confirm is removed, a claim left without support becomes a
    hypothesis, and the confidences follow by formula. If the judge cannot be reached the report
    is made with the links as they are and the run says `verify skipped`; the rules still run.
    """
    add_event(conn, run_id, "verify", "started")
    try:
        found = verify_links(llm, bundle, claims, links, only)
    except LLMError as exc:
        log.warning("verify skipped for %s: %s", run_id, exc)
        add_event(conn, run_id, "verify", "skipped", f"{type(exc).__name__}")
    else:
        save_checks(conn, run_id, found.checks)
        if found.removed:
            claims = apply_confidence(
                found.claims, found.links, bundle.evidence_by_id(), bundle.as_of
            )
            links = found.links
        add_event(
            conn,
            run_id,
            "verify",
            "done",
            f"{found.judged} link(s) judged by {', '.join(found.models) or 'nobody'}, "
            f"{found.removed} not confirmed and removed, "
            f"{len(found.downgraded)} claim(s) downgraded to hypothesis",
        )
    if rules:
        save_checks(conn, run_id, rule_checks(claims))
    return claims, links


def chair_pass(
    conn: sqlite3.Connection,
    run_id: str,
    bundle: Bundle,
    llm: LLM,
    claims: list[Claim],
    result: VerdictResult,
    objections: list[str],
) -> list[DiligenceQuestion]:
    """The Chair's questions, ranked by code. Advisory like the Skeptic: a failure gives none."""
    add_event(conn, run_id, "chair", "started")
    try:
        questions = ask(
            llm,
            bundle,
            claims,
            [g.near_miss for g in result.gates if g.near_miss],
            objections,
            rnpv=result.rnpv,
        )
    except LLMError as exc:
        log.warning("chair skipped for %s: %s", run_id, exc)
        add_event(conn, run_id, "chair", "skipped", f"{type(exc).__name__}")
        return []
    add_event(conn, run_id, "chair", "done", f"{len(questions)} diligence question(s), ranked")
    return questions


def reason_and_score(
    conn: sqlite3.Connection, run_id: str, bundle: Bundle, llm: LLM
) -> VerdictResult:
    """Record the claims, the verdict and the progress events of the run, and finish it."""
    add_event(conn, run_id, "reason", "started", ", ".join(m.name for m in ALL_MODULES))
    reasoner = ModuleReasoner(llm, run_id, question=_question(conn, run_id))
    claims, links = reasoner.reason(bundle)
    # A failed citation removes the whole claim, including a claim with other surviving
    # citations, rather than softening it to an inference.
    rejected = {d.claim_id for d in reasoner.trace.drops if d.is_citation_failure}
    cited = {link.claim_id for link in links}
    rejected |= {c.id for c in claims if c.basis is not Basis.UNKNOWN and c.id not in cited}
    next_number = max((int(c.id.removeprefix("C-")) for c in claims), default=0) + 1
    claims = [c for c in claims if c.id not in rejected]
    links = [link for link in links if link.claim_id not in rejected]
    claims += fill_missing_chain_links(claims, bundle, run_id, next_number)
    save_checks(conn, run_id, drop_checks(reasoner.trace.drops, rejected))
    corrections = sum(not d.is_citation_failure for d in reasoner.trace.drops)
    add_event(
        conn,
        run_id,
        "reason",
        "done",
        f"{len(claims)} claims, {len(rejected)} dropped by code; rejected claims: "
        f"{', '.join(sorted(rejected)) or 'none'}; {corrections} other corrections by code",
    )

    claims, links, objections = skeptic_pass(conn, run_id, bundle, llm, claims, links)
    claims, links = verify_pass(conn, run_id, bundle, llm, claims, links)
    save_claims(conn, run_id, claims, links, bundle.version)

    add_event(conn, run_id, "score", "started")
    fin = run_financials(conn, run_id, bundle)
    result = with_financials(score_verdict(claims, fin.rnpv.rnpv if fin.rnpv else None), fin)
    add_event(conn, run_id, "score", "done", f"{result.verdict.value} ({result.confidence:.2f})")

    questions = chair_pass(conn, run_id, bundle, llm, claims, result, objections)
    result = result.model_copy(update={"diligence_questions": questions})

    finish_run(conn, run_id, DONE, result)
    add_event(conn, run_id, "run", "done")
    return result
