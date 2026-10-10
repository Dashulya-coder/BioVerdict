"""The value of a diligence question is what its answer would do to the verdict, by code."""

from bioverdict.scoring.verdict import score_verdict
from bioverdict.scoring.voi import value_of_information
from bioverdict.store.models import (
    Basis,
    ChainLink,
    Claim,
    ClaimType,
    ConfidenceParts,
    DiligenceType,
    GateId,
    Range,
    Section,
    Verdict,
)

POSITIVE = Range(p10=10, p50=200, p90=900)


def claim(cid: str, confidence: float = 0.9, **kw) -> Claim:
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


def chain(missing: ChainLink | None = None) -> list[Claim]:
    return [
        claim(f"L-{link.value}", 0.9, chain_link=link) for link in ChainLink if link is not missing
    ]


def test_a_gap_that_alone_holds_the_verdict_back_is_worth_the_step_it_would_lift() -> None:
    gap = claim(
        "C-gap",
        0.1,
        basis=Basis.UNKNOWN,
        chain_link=ChainLink.TARGET_ENGAGEMENT,
        diligence_type=DiligenceType.EXPERIMENT,
    )
    claims = [*chain(ChainLink.TARGET_ENGAGEMENT), gap, claim("K", 0.9, critical=True)]
    assert score_verdict(claims, POSITIVE).verdict is Verdict.CONDITIONAL

    assert value_of_information(claims, "C-gap", POSITIVE) > 0.5


def test_a_gap_beside_another_gap_cannot_move_the_verdict_alone() -> None:
    def gap(link: ChainLink) -> Claim:
        return claim(
            f"C-{link.value}",
            0.1,
            basis=Basis.UNKNOWN,
            chain_link=link,
            diligence_type=DiligenceType.EXPERIMENT,
        )

    two = (ChainLink.HUMAN_EXPOSURE, ChainLink.TARGET_ENGAGEMENT)
    rest = [c for c in chain() if c.chain_link not in two]
    key = claim("K", 0.9, critical=True)
    both_open = [*rest, gap(two[0]), gap(two[1]), key]
    other_closed = [*rest, gap(two[0]), claim("L-closed", 0.9, chain_link=two[1]), key]

    assert value_of_information(both_open, f"C-{two[0].value}", POSITIVE) < 0.1
    assert value_of_information(other_closed, f"C-{two[0].value}", POSITIVE) > 0.5


def test_a_claim_the_gate_rests_on_is_worth_more_than_a_side_claim() -> None:
    stop = claim(
        "C-stop",
        0.5,
        claim_type=ClaimType.STUDY_FACT,
        gate_signals=[GateId.K4],
        confidence_parts=ConfidenceParts(support=0.5, contra=0, freshness=1, independent_groups=1),
    )
    side = claim("C-side", 0.5)
    claims = [*chain(), claim("K", 0.9, critical=True), stop, side]

    assert value_of_information(claims, "C-stop", POSITIVE) > value_of_information(
        claims, "C-side", POSITIVE
    )
    assert value_of_information(claims, "C-side", POSITIVE) == 0


def test_a_claim_that_is_not_in_the_report_is_worth_nothing() -> None:
    assert value_of_information(chain(), "C-none", POSITIVE) == 0.0


def test_a_confident_claim_is_worth_less_than_the_same_claim_in_doubt() -> None:
    def key(confidence: float) -> list[Claim]:
        return [*chain(), claim("K", confidence, critical=True)]

    assert value_of_information(key(0.5), "K", POSITIVE) > value_of_information(
        key(0.95), "K", POSITIVE
    )
