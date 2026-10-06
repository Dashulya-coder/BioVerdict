import pytest

from bioverdict.scoring import benchmarks as bm
from bioverdict.scoring.pos import (
    Modifier,
    PosConfig,
    genetic_support_modifier,
    phase_transitions,
    probability_of_success,
)


def test_all_disease_benchmark_reproduces_the_published_loa() -> None:
    loa = 1.0
    for v in bm.ALL_DISEASES.values():
        loa *= v
    assert loa == pytest.approx(0.067, abs=0.001)


def test_oncology_uses_published_transitions() -> None:
    transitions, source, assumptions = phase_transitions("oncology")
    assert transitions == bm.BIO_2021_ONCOLOGY
    assert "BIO" in source and not assumptions


def test_other_areas_are_scaled_to_their_published_loa() -> None:
    transitions, _, assumptions = phase_transitions("hematology")
    loa = 1.0
    for v in transitions.values():
        loa *= v
    assert loa == pytest.approx(bm.LOA_BY_AREA["hematology"], rel=0.01)
    assert transitions["nda"] == bm.ALL_DISEASES["nda"]
    assert assumptions and "derived" in assumptions[0]


def test_unknown_area_and_stage_are_rejected() -> None:
    with pytest.raises(ValueError):
        probability_of_success(area="astrology")
    with pytest.raises(ValueError):
        probability_of_success(stage="phase9")


def test_later_stage_has_higher_pos() -> None:
    early = probability_of_success("phase1", "oncology").pos.p50
    late = probability_of_success("phase3", "oncology").pos.p50
    assert late > early


def test_range_is_ordered_and_centered_near_the_benchmark() -> None:
    r = probability_of_success("phase1")
    assert r.pos.p10 < r.pos.p50 < r.pos.p90
    assert r.pos.p50 == pytest.approx(r.base_probability, rel=0.15)


def test_genetic_support_raises_pos_and_is_documented() -> None:
    plain = probability_of_success("phase2", "metabolic")
    backed = probability_of_success("phase2", "metabolic", [genetic_support_modifier()])
    assert backed.pos.p50 == pytest.approx(plain.pos.p50 * 2.6, rel=0.05)
    assert any("Minikel" in a for a in backed.assumptions)


def test_sparse_evidence_widens_the_range() -> None:
    normal = probability_of_success("phase2", "oncology").pos
    sparse = probability_of_success("phase2", "oncology", sparse=True).pos
    assert (sparse.p90 - sparse.p10) > (normal.p90 - normal.p10)


def test_modifier_is_bounded_and_pos_is_capped() -> None:
    huge = Modifier("optimism", 50.0, "made up")
    r = probability_of_success("nda", "hematology", [huge])
    assert any("bounded" in a for a in r.assumptions)
    assert r.pos.p90 <= PosConfig().pos_cap


def test_same_input_gives_the_same_range() -> None:
    assert probability_of_success("phase2", "oncology") == probability_of_success(
        "phase2", "oncology"
    )
