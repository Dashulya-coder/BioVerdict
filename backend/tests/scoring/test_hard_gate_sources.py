"""A hard gate means Do Not Invest: more confidence is not the same as a second source."""

from datetime import UTC, date, datetime

from bioverdict.scoring.confidence import apply_confidence, claim_confidence
from bioverdict.scoring.verdict import score_verdict
from bioverdict.store.models import (
    Basis,
    Claim,
    ClaimEvidenceLink,
    ClaimType,
    Direction,
    Evidence,
    EvidenceLevel,
    GateId,
    Section,
    SourceKind,
    Verdict,
)

AS_OF = date(2026, 10, 7)


def record(eid: str, group: str, text: str) -> Evidence:
    return Evidence(
        id=eid,
        source="ClinicalTrials.gov",
        source_family="registry",
        source_kind=SourceKind.REGISTRY,
        url=f"https://clinicaltrials.gov/{eid}",
        excerpt=text,
        published_at=date(2026, 1, 1),
        retrieved_at=datetime(2026, 10, 7, tzinfo=UTC),
        level=EvidenceLevel.REGISTRY_RECORD,
        independence_group=group,
        version=1,
    )


STATUS = '{"overallStatus": "TERMINATED", "whyStopped": "Futility"}'
DESIGN = '{"studyType": "INTERVENTIONAL", "phases": ["PHASE3"], "whyStopped": "Futility"}'


def scored(*evidence: Evidence, directions=None) -> tuple[Claim, list[ClaimEvidenceLink]]:
    claim = Claim(
        id="C-1",
        run_id="R",
        section=Section.CLINICAL,
        text="the same target failed for futility",
        claim_type=ClaimType.STUDY_FACT,
        basis=Basis.EXTRACTED,
        confidence=0.0,
        gate_signals=[GateId.K1],
    )
    directions = directions or [Direction.SUPPORTS] * len(evidence)
    links = [
        ClaimEvidenceLink(claim_id="C-1", evidence_id=e.id, direction=d, quote="Futility")
        for e, d in zip(evidence, directions, strict=True)
    ]
    (out,) = apply_confidence([claim], links, {e.id: e for e in evidence}, AS_OF)
    return out, links


def k1(result):
    return next(g for g in result.gates if g.gate_id is GateId.K1)


def test_two_records_of_one_study_are_confident_but_not_a_second_source() -> None:
    """Reproduced by the review of #51: two records of one sponsor reached 0.858 and fired K1."""
    claim, _ = scored(
        record("E-1", "sponsor:Amgen", STATUS), record("E-2", "sponsor:Amgen", DESIGN)
    )
    assert claim.confidence > 0.85  # above the hard-gate bar by itself
    assert claim.confidence_parts.independent_groups == 1
    result = score_verdict([claim])
    assert not k1(result).fired and result.verdict is not Verdict.DO_NOT_INVEST
    assert "second independent source" in k1(result).near_miss
    assert any("not yet confirmed" in r for r in result.top_risks)


def test_a_second_independence_group_lets_the_gate_fire() -> None:
    claim, _ = scored(
        record("E-1", "sponsor:Amgen", STATUS), record("E-2", "trial:NCT04933695", DESIGN)
    )
    assert claim.confidence_parts.independent_groups == 2
    result = score_verdict([claim])
    assert k1(result).fired and result.verdict is Verdict.DO_NOT_INVEST


def test_only_supporting_evidence_counts_as_a_source() -> None:
    claim, _ = scored(
        record("E-1", "sponsor:Amgen", STATUS),
        record("E-2", "sponsor:Other", DESIGN),
        directions=[Direction.SUPPORTS, Direction.CONTRADICTS],
    )
    assert claim.confidence_parts.independent_groups == 1


def test_a_soft_gate_does_not_need_a_second_group() -> None:
    claim, _ = scored(record("E-1", "sponsor:A", "competitor in phase 3 Futility"))
    claim = claim.model_copy(update={"gate_signals": [GateId.S4], "confidence": 0.7})
    assert next(g for g in score_verdict([claim]).gates if g.gate_id is GateId.S4).fired


def test_a_claim_built_by_hand_without_a_breakdown_is_not_held_to_the_rule() -> None:
    hand = Claim(
        id="C-1",
        run_id="R",
        section=Section.CLINICAL,
        text="x",
        claim_type=ClaimType.STUDY_FACT,
        basis=Basis.EXTRACTED,
        confidence=0.95,
        gate_signals=[GateId.K1],
    )
    assert hand.confidence_parts is None and k1(score_verdict([hand])).fired


def test_the_breakdown_round_trips_and_old_records_still_load() -> None:
    claim, _ = scored(record("E-1", "sponsor:A", STATUS))
    assert Claim.model_validate_json(claim.model_dump_json()) == claim
    old = {"support": 0.5, "contra": 0.0, "freshness": 1.0}  # stored before this field existed
    from bioverdict.store.models import ConfidenceParts

    assert ConfidenceParts.model_validate(old).independent_groups == 0


def test_the_unsupported_result_has_no_sources() -> None:
    claim = Claim(
        id="C-1",
        run_id="R",
        section=Section.CLINICAL,
        text="x",
        claim_type=ClaimType.STUDY_FACT,
        basis=Basis.EXTRACTED,
        confidence=0.0,
    )
    assert claim_confidence(claim, [], {}, AS_OF).parts.independent_groups == 0
