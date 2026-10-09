"""A gap or a guess cannot assert a gate, however confident the draft makes it look."""

from datetime import UTC, date, datetime

import pytest

from bioverdict.scoring.confidence import claim_confidence
from bioverdict.scoring.verdict import basis_can_assert, score_verdict
from bioverdict.store.models import (
    Basis,
    Claim,
    ClaimEvidenceLink,
    ClaimType,
    DiligenceType,
    Direction,
    Evidence,
    EvidenceLevel,
    GateId,
    Section,
    SourceKind,
    Verdict,
)

AS_OF = date(2026, 10, 7)


def registry(eid: str, group: str) -> Evidence:
    return Evidence(
        id=eid,
        source="ClinicalTrials.gov",
        source_family="registry",
        source_kind=SourceKind.REGISTRY,
        url=f"https://clinicaltrials.gov/{eid}",
        excerpt='{"overallStatus": "TERMINATED", "whyStopped": "Futility"}',
        published_at=date(2026, 1, 1),
        retrieved_at=datetime(2026, 10, 7, tzinfo=UTC),
        level=EvidenceLevel.REGISTRY_RECORD,
        independence_group=group,
        version=1,
    )


def gate_claim(basis: Basis, gate: GateId = GateId.K1, **kw) -> Claim:
    base = {
        "id": "C-1",
        "run_id": "R",
        "section": Section.CLINICAL,
        "text": "the same target failed",
        "claim_type": ClaimType.STUDY_FACT,
        "basis": basis,
        "confidence": 0.95,
        "gate_signals": [gate],
    }
    if basis is Basis.UNKNOWN:
        base["diligence_type"] = DiligenceType.PROPRIETARY_DATA
    return Claim(**(base | kw))


def links(*evidence: Evidence) -> list[ClaimEvidenceLink]:
    return [
        ClaimEvidenceLink(
            claim_id="C-1", evidence_id=e.id, direction=Direction.SUPPORTS, quote="TERMINATED"
        )
        for e in evidence
    ]


@pytest.mark.parametrize("basis", [Basis.UNKNOWN, Basis.HYPOTHESIS])
def test_an_unknown_or_hypothesised_claim_gains_nothing_from_the_evidence_it_cites(basis) -> None:
    """Reproduced by the review of #51: an unknown claim with two links scored 0.917 -> DNI."""
    a, b = registry("E-1", "sponsor:A"), registry("E-2", "sponsor:B")
    claim = gate_claim(basis, confidence=0.0)
    result = claim_confidence(claim, links(a, b), {"E-1": a, "E-2": b}, AS_OF)
    assert result.confidence == pytest.approx(0.3)


@pytest.mark.parametrize("basis", [Basis.UNKNOWN, Basis.HYPOTHESIS, Basis.INFERRED, Basis.MODELED])
def test_only_a_stated_fact_asserts_a_hard_gate(basis) -> None:
    claim = gate_claim(basis)
    result = score_verdict([claim])
    assert next(g for g in result.gates if g.gate_id is GateId.K1).fired is False
    assert result.verdict is not Verdict.DO_NOT_INVEST


@pytest.mark.parametrize("basis", [Basis.EXTRACTED, Basis.DERIVED])
def test_a_stated_fact_still_asserts_a_hard_gate(basis) -> None:
    result = score_verdict([gate_claim(basis)])
    assert result.verdict is Verdict.DO_NOT_INVEST


def test_a_conclusion_may_assert_a_soft_gate_but_a_gap_may_not() -> None:
    s4 = lambda basis: score_verdict([gate_claim(basis, GateId.S4)])
    fired = lambda r: next(g for g in r.gates if g.gate_id is GateId.S4).fired
    assert fired(s4(Basis.INFERRED)) and fired(s4(Basis.EXTRACTED))
    assert not fired(s4(Basis.UNKNOWN)) and not fired(s4(Basis.HYPOTHESIS))


def test_an_unconfirmed_signal_from_a_gap_does_not_cap_the_verdict_either() -> None:
    claim = gate_claim(Basis.UNKNOWN, confidence=0.7)  # between the soft and the hard bar
    assert "not yet confirmed" not in " ".join(score_verdict([claim]).top_risks)
    stated = gate_claim(Basis.EXTRACTED, confidence=0.7)
    assert "not yet confirmed" in " ".join(score_verdict([stated]).top_risks)


def test_the_rule_is_one_function() -> None:
    assert basis_can_assert(GateId.K2, Basis.EXTRACTED) and not basis_can_assert(
        GateId.K2, Basis.INFERRED
    )
    assert basis_can_assert(GateId.S4, Basis.INFERRED) and not basis_can_assert(
        GateId.S4, Basis.UNKNOWN
    )
