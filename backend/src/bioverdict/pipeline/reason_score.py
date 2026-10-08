"""The second half of every run: reason over the frozen bundle, then score (fixture and live).

Nothing here touches the network. The bundle is the whole world and the model is whatever the
caller injects: canned answers for a fixture run, the real client for a live one.
"""

from __future__ import annotations

import sqlite3

from bioverdict.contracts import LLM
from bioverdict.reasoning import ModuleReasoner
from bioverdict.reasoning.grounding import fill_missing_chain_links
from bioverdict.reasoning.modules import ALL_MODULES
from bioverdict.scoring.verdict import score_verdict
from bioverdict.store.models import Basis, Bundle, VerdictResult
from bioverdict.store.runs_repo import DONE, add_event, finish_run, save_claims


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
