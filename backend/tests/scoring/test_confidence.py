from datetime import UTC, date, datetime

import pytest

from bioverdict.scoring.confidence import chain_probability, claim_confidence
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
    ServiceFlag,
    SourceKind,
)

AS_OF = date(2026, 10, 6)
QUOTE = "quote"


def ev(eid: str, level: EvidenceLevel, group: str, **kw) -> Evidence:
    base = {
        "id": eid,
        "source": "PubMed",
        "source_family": "literature",
        "source_kind": SourceKind.PEER_REVIEWED,
        "url": f"https://example.org/{eid}",
        "excerpt": f"{QUOTE} {eid}",
        "published_at": AS_OF,  # recency R = 1
        "retrieved_at": datetime(2026, 10, 6, tzinfo=UTC),
        "level": level,
        "independence_group": group,
        "version": 1,
    }
    return Evidence(**(base | kw))


def link(eid: str, direction: Direction, claim_id: str = "C-1") -> ClaimEvidenceLink:
    return ClaimEvidenceLink(
        claim_id=claim_id, evidence_id=eid, direction=direction, quote=f"{QUOTE} {eid}"
    )


def claim(claim_type: ClaimType = ClaimType.TARGET_CAUSAL) -> Claim:
    return Claim(
        id="C-1",
        run_id="R-1",
        section=Section.MECHANISM,
        text="target is causal",
        claim_type=claim_type,
        basis=Basis.EXTRACTED,
        confidence=0.0,
    )


GENETICS = ev("E1", EvidenceLevel.HUMAN_GENETICS, "lab:a")
OBSERVATIONAL = ev("E2", EvidenceLevel.HUMAN_OBSERVATIONAL, "lab:b")
ANIMAL = ev("E3", EvidenceLevel.ANIMAL_IN_VIVO, "lab:c")
WEAK_CONTRA = ev("E4", EvidenceLevel.IN_VITRO, "lab:d")
STRONG_CONTRA = ev("E5", EvidenceLevel.HUMAN_GENETICS, "biobank:e")

ALL = {e.id: e for e in (GENETICS, OBSERVATIONAL, ANIMAL, WEAK_CONTRA, STRONG_CONTRA)}
SUPPORT = [
    link("E1", Direction.SUPPORTS),
    link("E2", Direction.SUPPORTS),
    link("E3", Direction.SUPPORTS),
]


def conf(links: list[ClaimEvidenceLink], c: Claim | None = None) -> float:
    return claim_confidence(c or claim(), links, ALL, AS_OF).confidence


def test_plan_example_supported_claim_is_90_percent() -> None:
    assert conf(SUPPORT) == pytest.approx(0.90, abs=0.01)  # sum = +1.8


def test_plan_example_weak_contradiction_barely_moves_confidence() -> None:
    c = conf([*SUPPORT, link("E4", Direction.CONTRADICTS)])  # sum = +1.65
    assert c == pytest.approx(0.88, abs=0.01)
    assert conf(SUPPORT) - c < 0.03


def test_plan_example_strong_contradiction_lowers_confidence_clearly() -> None:
    # The plan's table lists sum = +0.8 for this row, which is 1.8 - 1.0 (the weak in vitro
    # contradiction is not included), so it is tested on its own here.
    c = conf([*SUPPORT, link("E5", Direction.CONTRADICTS)])
    assert c == pytest.approx(0.72, abs=0.01)
    assert conf(SUPPORT) - c > 0.15


def test_strong_contradiction_dominates_weak_one() -> None:
    weak = conf([*SUPPORT, link("E4", Direction.CONTRADICTS)])
    both = conf([*SUPPORT, link("E4", Direction.CONTRADICTS), link("E5", Direction.CONTRADICTS)])
    assert both < weak - 0.15


def test_claim_type_changes_level_weights() -> None:
    only_genetics = [link("E1", Direction.SUPPORTS)]
    causal = conf(only_genetics, claim(ClaimType.TARGET_CAUSAL))  # L = 1.0
    drug = conf(only_genetics, claim(ClaimType.DRUG_ACTS_IN_HUMANS))  # L = 0.4
    assert causal > drug


def test_same_lab_repeats_count_less() -> None:
    repeats = {
        f"R{i}": ev(f"R{i}", EvidenceLevel.HUMAN_OBSERVATIONAL, "lab:same") for i in range(5)
    }
    independent = {
        f"I{i}": ev(f"I{i}", EvidenceLevel.HUMAN_OBSERVATIONAL, f"lab:{i}") for i in range(5)
    }
    c = claim()
    rep = claim_confidence(c, [link(k, Direction.SUPPORTS) for k in repeats], repeats, AS_OF)
    ind = claim_confidence(
        c, [link(k, Direction.SUPPORTS) for k in independent], independent, AS_OF
    )
    one = claim_confidence(c, [link("R0", Direction.SUPPORTS)], repeats, AS_OF)
    assert one.support_sum < rep.support_sum < 2 * one.support_sum  # 0.5 * (1 + .5 + .25 ...)
    assert rep.confidence < ind.confidence


def test_ungrounded_quote_is_ignored() -> None:
    bad = ClaimEvidenceLink(
        claim_id="C-1", evidence_id="E1", direction=Direction.SUPPORTS, quote="not in the text"
    )
    r = claim_confidence(claim(), [bad], ALL, AS_OF)
    assert r.confidence == 0.3
    assert ServiceFlag.SPARSE in r.flags


def test_claim_without_evidence_is_low_and_sparse() -> None:
    r = claim_confidence(claim(), [], ALL, AS_OF)
    assert r.confidence <= 0.3
    assert ServiceFlag.SPARSE in r.flags


def test_evidence_after_as_of_is_ignored_for_time_travel() -> None:
    future = {"E1": ev("E1", EvidenceLevel.HUMAN_GENETICS, "lab:a", published_at=date(2027, 1, 1))}
    r = claim_confidence(claim(), [link("E1", Direction.SUPPORTS)], future, AS_OF)
    assert r.confidence == 0.3


def test_old_literature_decays_but_registry_does_not() -> None:
    old = date(2006, 10, 6)  # twenty years old: two half-lives
    lit = {"E1": ev("E1", EvidenceLevel.HUMAN_GENETICS, "lab:a", published_at=old)}
    reg = {
        "E1": ev(
            "E1",
            EvidenceLevel.HUMAN_GENETICS,
            "lab:a",
            published_at=old,
            source_kind=SourceKind.REGISTRY,
        )
    }
    l1 = [link("E1", Direction.SUPPORTS)]
    assert (
        claim_confidence(claim(), l1, lit, AS_OF).confidence
        < claim_confidence(claim(), l1, reg, AS_OF).confidence
    )


def test_contested_flag_when_both_sides_are_strong() -> None:
    both = [
        link("E1", Direction.SUPPORTS),
        link("E5", Direction.CONTRADICTS),
    ]
    r = claim_confidence(claim(), both, ALL, AS_OF)
    assert ServiceFlag.CONTESTED in r.flags
    assert r.confidence == pytest.approx(0.5)  # not averaged away: flagged explicitly


def test_chain_probability_is_a_product_and_finds_missing_links() -> None:
    p, missing = chain_probability([0.9, 0.8, 0.35, 0.9, 0.7])
    assert p == pytest.approx(0.9 * 0.8 * 0.35 * 0.9 * 0.7)
    assert missing == [2]


def test_config_instances_do_not_share_tables() -> None:
    a, b = ConfidenceConfig(), ConfidenceConfig()
    a.level_weight[ClaimType.TARGET_CAUSAL][EvidenceLevel.HUMAN_GENETICS] = 0.1
    a.source_quality[SourceKind.REGISTRY] = 0.1
    assert b.level_weight[ClaimType.TARGET_CAUSAL][EvidenceLevel.HUMAN_GENETICS] == 1.0
    assert b.source_quality[SourceKind.REGISTRY] == 1.0
    assert (
        ConfidenceConfig().level_weight[ClaimType.TARGET_CAUSAL][EvidenceLevel.HUMAN_GENETICS]
        == 1.0
    )


def test_undated_snapshot_is_hidden_before_it_was_fetched() -> None:
    snapshot = {
        "E1": ev(
            "E1",
            EvidenceLevel.HUMAN_GENETICS,
            "db:x",
            published_at=None,
            retrieved_at=datetime(2026, 10, 6, tzinfo=UTC),
        )
    }
    l1 = [link("E1", Direction.SUPPORTS)]
    assert claim_confidence(claim(), l1, snapshot, date(2026, 10, 6)).confidence > 0.5
    # a backtest in the past must not see a database snapshot taken later
    assert claim_confidence(claim(), l1, snapshot, date(2020, 1, 1)).confidence == 0.3
