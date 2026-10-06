from datetime import UTC, date, datetime

import pytest

from bioverdict.scoring.confidence import claim_confidence
from bioverdict.scoring.config import ConfidenceConfig
from bioverdict.store.models import (
    Basis,
    Claim,
    ClaimEvidenceLink,
    ClaimType,
    Direction,
    Evidence,
    EvidenceLevel,
    Section,
    SourceKind,
)

AS_OF = date(2026, 10, 7)
QUOTE = "TERMINATED"


def registry_evidence() -> Evidence:
    return Evidence(
        id="E-0001",
        source="ClinicalTrials.gov",
        source_family="registry",
        source_kind=SourceKind.REGISTRY,
        url="https://clinicaltrials.gov/study/NCT04933695",
        excerpt='{"overallStatus": "TERMINATED", "whyStopped": "Futility"}',
        published_at=date(2026, 7, 13),
        retrieved_at=datetime(2026, 10, 7, tzinfo=UTC),
        level=EvidenceLevel.REGISTRY_RECORD,
        independence_group="sponsor:Amgen",
        version=1,
    )


def confidence_of(claim_type: ClaimType) -> tuple[float, list]:
    claim = Claim(
        id="C-1",
        run_id="R-1",
        section=Section.CLINICAL,
        text="the trial was stopped",
        claim_type=claim_type,
        basis=Basis.EXTRACTED,
        confidence=0.5,
    )
    link = ClaimEvidenceLink(
        claim_id="C-1", evidence_id="E-0001", direction=Direction.SUPPORTS, quote=QUOTE
    )
    evidence = registry_evidence()
    result = claim_confidence(claim, [link], {evidence.id: evidence}, AS_OF)
    return result.confidence, result.flags


def test_every_level_has_a_weight_for_every_claim_type() -> None:
    table = ConfidenceConfig().level_weight
    for claim_type in ClaimType:
        assert set(table[claim_type]) == set(EvidenceLevel), claim_type


@pytest.mark.parametrize("claim_type", [ClaimType.TARGET_CAUSAL, ClaimType.DRUG_ACTS_IN_HUMANS])
def test_a_registry_record_proves_no_efficacy(claim_type: ClaimType) -> None:
    confidence, _ = confidence_of(claim_type)
    assert confidence == pytest.approx(0.5)  # unchanged from the prior


def test_a_registry_record_does_support_a_fact_about_a_study() -> None:
    confidence, _ = confidence_of(ClaimType.OTHER)
    assert confidence > 0.7  # enough to let a gate such as "the trial was stopped" fire
