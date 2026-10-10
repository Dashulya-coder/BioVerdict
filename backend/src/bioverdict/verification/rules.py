"""Gates 4 and 5: source authority and temporal validity, by rule (docs/architecture.md, section 7).

Both read what the confidence formula already computed, so they add no new judgement: they say, in
the verification log, why a claim is weak.
"""

from __future__ import annotations

from bioverdict.store.models import Basis, Claim, VerificationCheck

AUTHORITY = "source_authority"
TEMPORAL = "temporal_validity"
STALE_FRESHNESS = 0.3  # below this the evidence is more than ~2.5 half-lives old


def rule_checks(claims: list[Claim]) -> list[VerificationCheck]:
    """One authority and one temporal check for every claim that cites evidence."""
    checks: list[VerificationCheck] = []
    for claim in claims:
        parts = claim.confidence_parts
        if claim.basis in (Basis.UNKNOWN, Basis.HYPOTHESIS) or parts is None:
            continue
        if parts.support == 0 and parts.contra == 0:
            checks.append(
                VerificationCheck(
                    claim_id=claim.id,
                    check_name=AUTHORITY,
                    passed=False,
                    detail=(
                        "the cited evidence carries no weight for a "
                        f"{claim.claim_type.value} claim (wrong kind of source)"
                    ),
                )
            )
            continue
        checks.append(VerificationCheck(claim_id=claim.id, check_name=AUTHORITY, passed=True))
        stale = parts.freshness < STALE_FRESHNESS
        checks.append(
            VerificationCheck(
                claim_id=claim.id,
                check_name=TEMPORAL,
                passed=not stale,
                detail=f"evidence freshness {parts.freshness:.2f}" if stale else "",
            )
        )
    return checks
