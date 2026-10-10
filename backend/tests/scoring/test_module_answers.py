"""The answer of each underwriting module is a balance of its claims, computed by code."""

import pytest

from bioverdict.scoring.module_answers import (
    ModuleAnswer,
    ModuleId,
    contribution,
    module_answers,
)
from bioverdict.scoring.verdict import score_verdict
from bioverdict.store.models import (
    Basis,
    Claim,
    ClaimEvidenceLink,
    ClaimType,
    ConfidenceParts,
    Direction,
    GateId,
    Implication,
    Range,
    Section,
    Verdict,
)

FOR, AGAINST = Implication.FAVOURABLE, Implication.UNFAVOURABLE
POSITIVE = Range(p10=10, p50=200, p90=900)


def claim(cid: str, confidence: float, implication: Implication = FOR, **kw) -> Claim:
    base = {
        "id": cid,
        "run_id": "R-1",
        "section": Section.CLINICAL,
        "text": f"claim {cid}",
        "claim_type": ClaimType.OTHER,
        "basis": Basis.EXTRACTED,
        "confidence": confidence,
        "implication": implication,
    }
    return Claim(**(base | kw))


def answer_of(claims: list[Claim], module: ModuleId = ModuleId.CLINICAL, links=None, rnpv=None):
    result = score_verdict(claims, rnpv)
    return next(m for m in module_answers(claims, links or [], result) if m.module is module)


def test_six_modules_are_reported_in_the_order_of_the_report() -> None:
    modules = module_answers([], [], score_verdict([]))

    assert [m.module for m in modules] == list(ModuleId)
    assert all(m.answer is ModuleAnswer.INSUFFICIENT for m in modules[:5])


def test_a_likely_claim_pulls_its_way_and_a_refuted_one_pulls_the_other() -> None:
    assert contribution(claim("A", 0.9)) == pytest.approx(0.8)
    assert contribution(claim("B", 0.9, AGAINST)) == pytest.approx(-0.8)
    assert contribution(claim("C", 0.2)) == pytest.approx(-0.6)  # favourable, but refuted


def test_gaps_guesses_and_context_pull_nowhere() -> None:
    unweighted = ConfidenceParts(support=0, contra=0, freshness=1)
    assert contribution(claim("A", 0.9, Implication.NEUTRAL)) == 0
    assert contribution(claim("B", 0.3, basis=Basis.HYPOTHESIS)) == 0
    assert contribution(claim("C", 0.3, confidence_parts=unweighted)) == 0
    gap = claim("D", 0.3, Implication.NEUTRAL, basis=Basis.UNKNOWN, diligence_type="experiment")
    assert contribution(gap) == 0


def test_favourable_weight_supports_and_unfavourable_weight_is_against() -> None:
    supports = answer_of([claim("A", 0.9), claim("B", 0.8), claim("C", 0.6, AGAINST)])
    against = answer_of([claim("A", 0.6), claim("B", 0.9, AGAINST)])

    assert supports.answer is ModuleAnswer.SUPPORTS and supports.balance > 0.25
    assert [d.claim_id for d in supports.drivers] == ["A", "B", "C"]  # strongest pull first
    assert against.answer is ModuleAnswer.AGAINST and "weighs against" in against.headline


def test_weight_on_both_sides_is_mixed_and_too_little_weight_is_no_answer() -> None:
    mixed = answer_of([claim("A", 0.9), claim("B", 0.85, AGAINST)])
    thin = answer_of([claim("A", 0.55)])

    assert mixed.answer is ModuleAnswer.MIXED
    assert thin.answer is ModuleAnswer.INSUFFICIENT and thin.balance is None


def test_only_the_claims_of_a_module_count_for_it() -> None:
    claims = [claim("A", 0.9), claim("B", 0.9, AGAINST, section=Section.COMPETITION)]

    assert answer_of(claims).answer is ModuleAnswer.SUPPORTS
    competitive = answer_of(claims, ModuleId.COMPETITIVE_COMMERCIAL)
    assert competitive.answer is ModuleAnswer.AGAINST and competitive.claim_ids == ["B"]


def test_contradicting_evidence_moves_the_module_through_the_claim_it_refutes() -> None:
    before = answer_of([claim("A", 0.9), claim("B", 0.7, AGAINST)])
    after = answer_of([claim("A", 0.25), claim("B", 0.7, AGAINST)])

    assert before.answer is ModuleAnswer.SUPPORTS and after.answer is ModuleAnswer.AGAINST


def test_a_fired_kill_gate_decides_its_module_whatever_the_balance() -> None:
    two_sources = ConfidenceParts(support=0.9, contra=0, freshness=1, independent_groups=2)
    stopped = claim(
        "K",
        0.9,
        AGAINST,
        claim_type=ClaimType.STUDY_FACT,
        gate_signals=[GateId.K4],
        confidence_parts=two_sources,
    )
    module = answer_of([claim("A", 0.95), claim("B", 0.95), claim("C", 0.95), stopped])

    assert module.answer is ModuleAnswer.AGAINST and module.gates == ["K4"]
    assert module.headline.startswith("K4 fired on K")


def test_a_fired_soft_gate_caps_a_favourable_module_at_mixed() -> None:
    crowded = claim("S", 0.9, AGAINST, section=Section.COMPETITION, gate_signals=[GateId.S4])
    ahead = [claim(f"A{n}", 0.95, section=Section.COMPETITION) for n in range(4)]

    module = answer_of([*ahead, crowded], ModuleId.COMPETITIVE_COMMERCIAL)

    assert module.balance >= 0.25 and module.answer is ModuleAnswer.MIXED and module.gates == ["S4"]


def test_the_investment_module_reports_the_verdict_and_the_claims_it_was_decided_on() -> None:
    key = claim("KEY", 0.9, critical=True, section=Section.TRANSLATION)
    link = ClaimEvidenceLink(
        claim_id="KEY", evidence_id="E-1", direction=Direction.SUPPORTS, quote="q"
    )
    claims = [key, claim("OTHER", 0.9)]
    result = score_verdict(claims, POSITIVE)

    module = module_answers(claims, [link], result)[-1]

    assert result.verdict is Verdict.CONDITIONAL  # the chain has no claims: S1 fires
    assert module.module is ModuleId.INVESTMENT and module.answer is ModuleAnswer.MIXED
    assert module.headline.startswith("Conditional: gates fired: S1")
    assert "KEY" in module.claim_ids and "OTHER" not in module.claim_ids
    assert module.evidence_count == 1


def test_gaps_are_counted_and_named_in_the_headline() -> None:
    gap = claim("G", 0.3, Implication.NEUTRAL, basis=Basis.UNKNOWN, diligence_type="experiment")

    module = answer_of([claim("A", 0.9), gap])

    assert module.unknown_count == 1 and module.headline.endswith("1 open gap")
