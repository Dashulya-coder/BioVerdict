from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from bioverdict.store.models import (
    Basis,
    Bundle,
    Claim,
    ClaimEvidenceLink,
    ClaimType,
    Direction,
    Evidence,
    EvidenceLevel,
    Range,
    ResolverOutput,
    Section,
    SourceKind,
    VerdictResult,
    quote_is_grounded,
)

NOW = datetime(2026, 10, 6, 10, 15, tzinfo=UTC)


def make_evidence(**kw) -> Evidence:
    base = {
        "id": "E-0042",
        "source": "ClinicalTrials.gov",
        "source_family": "registry",
        "source_kind": SourceKind.REGISTRY,
        "url": "https://clinicaltrials.gov/study/NCT00000000",
        "locator": {"type": "nct", "value": "NCT00000000"},
        "excerpt": "Objective response rate was 55% in 30 patients.",
        "published_at": date(2026, 7, 2),
        "retrieved_at": NOW,
        "level": EvidenceLevel.HUMAN_INTERVENTIONAL,
        "independence_group": "sponsor:acme",
        "version": 1,
    }
    return Evidence(**(base | kw))


def make_bundle(evidence: list[Evidence]) -> Bundle:
    return Bundle(
        bundle_id="B-1",
        run_id="R-1",
        version=1,
        as_of=date(2026, 10, 6),
        content_hash="sha256:abc",
        catalog=[e.url for e in evidence],
        evidence=evidence,
        created_at=NOW,
    )


def test_resolver_output_allows_several_targets() -> None:
    out = ResolverOutput(
        indication={"name": "obesity", "efo_id": "EFO_0001073"},
        targets=[{"symbol": "GLP1R"}, {"symbol": "GIPR"}, {"symbol": "GCGR"}],
        action="agonist",
        assumptions=["modality inferred as peptide"],
    )
    assert len(out.targets) == 3


def test_resolver_output_needs_a_target() -> None:
    with pytest.raises(ValidationError):
        ResolverOutput(indication={"name": "x"}, targets=[])


def test_evidence_roundtrip_and_no_extra_fields() -> None:
    e = make_evidence()
    assert Evidence.model_validate_json(e.model_dump_json()) == e
    with pytest.raises(ValidationError):
        make_evidence(direction="supports")  # stance belongs to the link


def test_unknown_claim_requires_diligence_type() -> None:
    kw = {
        "id": "C-1",
        "run_id": "R-1",
        "section": Section.TRANSLATION,
        "text": "t",
        "confidence": 0.0,
    }
    with pytest.raises(ValidationError):
        Claim(basis=Basis.UNKNOWN, **kw)
    Claim(basis=Basis.UNKNOWN, diligence_type="kol_interview", **kw)


def test_claim_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Claim(
            id="C-1",
            run_id="R-1",
            section=Section.MECHANISM,
            text="t",
            basis=Basis.EXTRACTED,
            claim_type=ClaimType.TARGET_CAUSAL,
            confidence=1.2,
        )


def test_quote_grounding() -> None:
    bundle = make_bundle([make_evidence()])
    ok = ClaimEvidenceLink(
        claim_id="C-1", evidence_id="E-0042", direction=Direction.SUPPORTS, quote="55% in 30"
    )
    bad = ok.model_copy(update={"quote": "response rate was 90%"})
    missing = ok.model_copy(update={"evidence_id": "E-9999"})
    assert quote_is_grounded(ok, bundle)
    assert not quote_is_grounded(bad, bundle)
    assert not quote_is_grounded(missing, bundle)


def test_range_must_be_ordered() -> None:
    Range(p10=1, p50=2, p90=3)
    with pytest.raises(ValidationError):
        Range(p10=3, p50=2, p90=1)


def test_verdict_values_and_top_risks_limit() -> None:
    VerdictResult(verdict="Conditional", confidence=0.5, top_risks=["a", "b", "c"])
    with pytest.raises(ValidationError):
        VerdictResult(verdict="Maybe", confidence=0.5)
    with pytest.raises(ValidationError):
        VerdictResult(verdict="Invest", confidence=0.5, top_risks=list("abcd"))
