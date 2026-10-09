"""The second half of every run: reason over the frozen bundle, then score (fixture and live).

Nothing here touches the network. The bundle is the whole world and the model is whatever the
caller injects: canned answers for a fixture run, the real client for a live one.
"""

from __future__ import annotations

import sqlite3

from bioverdict.contracts import LLM
from bioverdict.reasoning import ModuleReasoner
from bioverdict.reasoning.grounding import Drop, fill_missing_chain_links
from bioverdict.reasoning.modules import ALL_MODULES
from bioverdict.scoring.verdict import score_verdict
from bioverdict.store.models import Basis, Bundle, VerdictResult, VerificationCheck
from bioverdict.store.runs_repo import DONE, add_event, finish_run, save_claims
from bioverdict.store.verification_repo import save_checks

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


def reason_and_score(
    conn: sqlite3.Connection, run_id: str, bundle: Bundle, llm: LLM
) -> VerdictResult:
    """Record the claims, the verdict and the progress events of the run, and finish it."""
    add_event(conn, run_id, "reason", "started", ", ".join(m.name for m in ALL_MODULES))
    reasoner = ModuleReasoner(llm, run_id)
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
    save_claims(conn, run_id, claims, links, bundle.version)
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

    add_event(conn, run_id, "score", "started")
    result = score_verdict(claims)
    add_event(conn, run_id, "score", "done", f"{result.verdict.value} ({result.confidence:.2f})")

    finish_run(conn, run_id, DONE, result)
    add_event(conn, run_id, "run", "done")
    return result
