from bioverdict.store.models import Basis, Claim, ClaimType, ConfidenceParts, Section
from bioverdict.verification import rule_checks


def claim(cid: str, basis: Basis = Basis.EXTRACTED, parts: ConfidenceParts | None = None) -> Claim:
    return Claim(
        id=cid,
        run_id="R-1",
        section=Section.CLINICAL,
        text=cid,
        claim_type=ClaimType.TARGET_CAUSAL,
        basis=basis,
        confidence=0.5,
        confidence_parts=parts,
        diligence_type="experiment" if basis is Basis.UNKNOWN else None,
    )


def parts(support=0.6, contra=0.0, freshness=1.0) -> ConfidenceParts:
    return ConfidenceParts(
        support=support, contra=contra, freshness=freshness, independent_groups=1
    )


def test_evidence_that_carries_weight_passes_both_rules() -> None:
    checks = rule_checks([claim("C-1", parts=parts())])

    assert [(c.check_name, c.passed) for c in checks] == [
        ("source_authority", True),
        ("temporal_validity", True),
    ]


def test_evidence_with_no_weight_for_the_claim_type_fails_authority() -> None:
    (check,) = rule_checks([claim("C-1", parts=parts(support=0.0))])

    assert (check.check_name, check.passed) == ("source_authority", False)
    assert "target_causal" in check.detail


def test_old_evidence_fails_temporal_validity() -> None:
    checks = rule_checks([claim("C-1", parts=parts(freshness=0.1))])

    assert [(c.check_name, c.passed) for c in checks][-1] == ("temporal_validity", False)


def test_unknowns_hypotheses_and_claims_without_parts_are_not_checked() -> None:
    claims = [claim("C-1", Basis.UNKNOWN), claim("C-2", Basis.HYPOTHESIS), claim("C-3")]

    assert rule_checks(claims) == []
