import pytest

from bioverdict.contracts import Scorer
from bioverdict.scoring.verdict import DeterministicScorer, score_verdict
from bioverdict.store.models import (
    Basis,
    ChainLink,
    Claim,
    ClaimType,
    GateId,
    Range,
    Section,
    ServiceFlag,
    Verdict,
)

POSITIVE = Range(p10=10, p50=200, p90=900)
NEGATIVE_EVEN_OPTIMISTIC = Range(p10=-900, p50=-300, p90=-5)


def claim(cid: str, confidence: float = 0.8, **kw) -> Claim:
    base = {
        "id": cid,
        "run_id": "R-1",
        "section": Section.TRANSLATION,
        "text": f"claim {cid}",
        "claim_type": ClaimType.OTHER,
        "basis": Basis.EXTRACTED,
        "confidence": confidence,
    }
    return Claim(**(base | kw))


def strong_chain(confidence: float = 0.9) -> list[Claim]:
    return [claim(f"L-{link.value}", confidence, chain_link=link) for link in ChainLink]


def gate(result, gate_id: GateId):
    return next(g for g in result.gates if g.gate_id is gate_id)


def test_all_conditions_met_gives_invest() -> None:
    claims = [*strong_chain(), claim("KEY", 0.9, critical=True)]
    r = score_verdict(claims, POSITIVE)
    assert r.verdict is Verdict.INVEST
    assert r.translation_chain_probability == pytest.approx(0.9**5)
    assert not [g for g in r.gates if g.fired]


def test_invest_needs_rnpv() -> None:
    r = score_verdict([*strong_chain(), claim("KEY", 0.9, critical=True)], rnpv=None)
    assert r.verdict is Verdict.CONDITIONAL
    assert any("rNPV" in c for c in r.what_would_change_our_mind)


def test_weak_key_claim_blocks_invest() -> None:
    r = score_verdict([*strong_chain(), claim("KEY", 0.6, critical=True)], POSITIVE)
    assert r.verdict is Verdict.CONDITIONAL
    assert any("KEY" in c for c in r.what_would_change_our_mind)


def test_hard_gate_overrides_everything_else() -> None:
    claims = [*strong_chain(0.95), claim("KEY", 0.95, critical=True)]
    claims.append(claim("FAIL", 0.9, gate_signals=[GateId.K1]))
    r = score_verdict(claims, POSITIVE)
    assert r.verdict is Verdict.DO_NOT_INVEST
    assert gate(r, GateId.K1).claim_ids == ["FAIL"]
    assert r.confidence == pytest.approx(0.9)


def test_gate_does_not_fire_on_low_confidence_claim() -> None:
    claims = [*strong_chain(), claim("KEY", 0.9, critical=True)]
    claims.append(claim("MAYBE", 0.5, gate_signals=[GateId.K2]))
    r = score_verdict(claims, POSITIVE)
    assert r.verdict is Verdict.INVEST
    assert "K2 would fire" in gate(r, GateId.K2).near_miss  # appears in "what would change"
    assert any("K2" in c for c in r.what_would_change_our_mind)


def test_soft_gate_caps_at_conditional() -> None:
    claims = [*strong_chain(), claim("KEY", 0.9, critical=True)]
    claims.append(claim("COMP", 0.7, gate_signals=[GateId.S4]))
    r = score_verdict(claims, POSITIVE)
    assert r.verdict is Verdict.CONDITIONAL
    assert gate(r, GateId.S4).fired


def test_negative_optimistic_rnpv_is_k5() -> None:
    r = score_verdict([*strong_chain(), claim("KEY", 0.9, critical=True)], NEGATIVE_EVEN_OPTIMISTIC)
    assert r.verdict is Verdict.DO_NOT_INVEST
    assert gate(r, GateId.K5).fired


def test_missing_chain_link_fires_s1() -> None:
    chain = [c for c in strong_chain() if c.chain_link is not ChainLink.TARGET_ENGAGEMENT]
    r = score_verdict([*chain, claim("KEY", 0.9, critical=True)], POSITIVE)
    assert r.verdict is Verdict.CONDITIONAL
    assert gate(r, GateId.S1).fired


def test_weak_chain_link_fires_s1_and_lowers_chain_probability() -> None:
    chain = strong_chain()
    chain[2] = chain[2].model_copy(update={"confidence": 0.35})
    r = score_verdict([*chain, claim("KEY", 0.9, critical=True)], POSITIVE)
    assert gate(r, GateId.S1).fired
    assert r.translation_chain_probability == pytest.approx(0.9**4 * 0.35)


def test_sparse_and_contested_key_claims_fire_s2_s3() -> None:
    sparse = claim("A", 0.5, critical=True, flags=[ServiceFlag.SPARSE])
    contested = claim("B", 0.5, critical=True, flags=[ServiceFlag.CONTESTED])
    r = score_verdict([*strong_chain(), sparse, contested], POSITIVE)
    assert gate(r, GateId.S2).claim_ids == ["A"]
    assert gate(r, GateId.S3).claim_ids == ["B"]
    assert r.verdict is Verdict.CONDITIONAL


def test_sparse_flag_on_a_non_critical_claim_is_ignored() -> None:
    other = claim("X", 0.5, flags=[ServiceFlag.SPARSE])
    r = score_verdict([*strong_chain(), claim("KEY", 0.9, critical=True), other], POSITIVE)
    assert not gate(r, GateId.S2).fired


def test_no_evidence_at_all_is_conditional_not_invest() -> None:
    r = score_verdict([], POSITIVE)
    assert r.verdict is Verdict.CONDITIONAL
    assert gate(r, GateId.S1).fired  # every chain link unknown


def test_top_risks_capped_at_three_and_gates_come_first() -> None:
    claims = [claim("COMP", 0.8, gate_signals=[GateId.S4]), claim("K", 0.9, critical=True)]
    r = score_verdict(claims, POSITIVE)
    assert len(r.top_risks) <= 3
    assert r.top_risks[0] == "A link of the human translation chain is missing"


def test_scorer_satisfies_contract_and_is_deterministic() -> None:
    scorer = DeterministicScorer(POSITIVE)
    assert isinstance(scorer, Scorer)
    claims = [*strong_chain(), claim("KEY", 0.9, critical=True)]
    assert scorer.score(claims, []) == scorer.score(claims, [])


def test_chain_of_five_decent_links_is_still_below_the_invest_bar() -> None:
    """0.85 per link looks strong, but 0.85^5 = 0.44 < 0.5: the plan's rule is strict on purpose."""
    r = score_verdict([*strong_chain(0.85), claim("KEY", 0.9, critical=True)], POSITIVE)
    assert r.verdict is Verdict.CONDITIONAL
    assert any("translation chain probability" in c for c in r.what_would_change_our_mind)


def test_rescore_recomputes_confidence_before_the_verdict() -> None:
    from datetime import UTC, date, datetime

    from bioverdict.scoring.verdict import rescore
    from bioverdict.store.models import (
        ClaimEvidenceLink,
        Direction,
        Evidence,
        EvidenceLevel,
        SourceKind,
    )

    evidence = {
        "E1": Evidence(
            id="E1",
            source="PubMed",
            source_family="literature",
            source_kind=SourceKind.PEER_REVIEWED,
            url="https://example.org/1",
            excerpt="strong result",
            published_at=date(2026, 1, 1),
            retrieved_at=datetime(2026, 10, 6, tzinfo=UTC),
            level=EvidenceLevel.HUMAN_GENETICS,
            independence_group="lab:a",
            version=1,
        )
    }
    gate_claim = claim("FAIL", 0.0, gate_signals=[GateId.S4])  # stale confidence 0.0
    links = [
        ClaimEvidenceLink(
            claim_id="FAIL", evidence_id="E1", direction=Direction.SUPPORTS, quote="strong"
        )
    ]
    updated, result = rescore([gate_claim], links, evidence, date(2026, 10, 6))
    assert updated[0].confidence > 0.6  # recomputed from the evidence
    assert gate(result, GateId.S4).fired  # and the gate saw the fresh value


def test_a_weak_hard_signal_is_ignored_below_the_soft_threshold() -> None:
    base = [*strong_chain(), claim("KEY", 0.9, critical=True)]
    weak = score_verdict([*base, claim("STOP", 0.5, gate_signals=[GateId.K1])], POSITIVE)
    assert weak.verdict is Verdict.INVEST  # 0.5 is noise, not an unconfirmed finding


def test_a_hard_gate_needs_more_confidence_than_a_soft_one() -> None:
    """One registry record reaches ~0.77: enough to cap at Conditional, not to say Do Not Invest."""
    base = [*strong_chain(), claim("KEY", 0.9, critical=True)]
    stopped = score_verdict([*base, claim("STOP", 0.77, gate_signals=[GateId.K1])], POSITIVE)
    assert stopped.verdict is Verdict.CONDITIONAL  # not Invest: the signal is serious
    assert not gate(stopped, GateId.K1).fired  # but not Do Not Invest on one source
    assert "K1 would fire" in gate(stopped, GateId.K1).near_miss
    assert any("second independent source" in c for c in stopped.what_would_change_our_mind)
    assert any("not yet confirmed" in r for r in stopped.top_risks)
    competitor = score_verdict([*base, claim("COMP", 0.77, gate_signals=[GateId.S4])], POSITIVE)
    assert competitor.verdict is Verdict.CONDITIONAL and gate(competitor, GateId.S4).fired
    confirmed = score_verdict([*base, claim("STOP", 0.86, gate_signals=[GateId.K1])], POSITIVE)
    assert confirmed.verdict is Verdict.DO_NOT_INVEST
