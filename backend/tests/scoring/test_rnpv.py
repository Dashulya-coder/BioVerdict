import numpy as np
import pytest

from bioverdict.scoring.pos import probability_of_success
from bioverdict.scoring.rnpv import Inputs, RnpvConfig, Tri, npv, run_rnpv
from bioverdict.store.models import Range

PATIENTS = Range(p10=5_000, p50=10_000, p90=20_000)
PRICE = Range(p10=100_000, p50=150_000, p90=200_000)


def _one(**kw) -> Inputs:
    base = {
        "phase_probs": np.array([[0.5]]),
        "modifier": 1.0,
        "pos_cap": 0.95,
        "patients": np.array([1000.0]),
        "price": np.array([100_000.0]),
        "peak_share": np.array([0.1]),
        "net_price_factor": np.array([1.0]),
        "margin": np.array([0.5]),
        "ramp_years": np.array([1.0]),
        "exclusivity_years": np.array([2.0]),
        "discount_rate": np.array([0.0]),
        "durations": np.array([[2.0]]),
        "costs": np.array([[1_000_000.0]]),
    }
    return Inputs(**(base | kw))


def test_npv_matches_a_hand_computed_case() -> None:
    # peak 1000 * 100k * 0.1 = 10M; margin 0.5 -> 5M a year for 2 years = 10M; x 0.5 = 5M; cost 1M
    assert npv(_one())[0] == pytest.approx(4_000_000)


def test_discounting_lowers_value() -> None:
    assert npv(_one(discount_rate=np.array([0.1])))[0] < npv(_one())[0]


def test_certain_failure_costs_only_the_trial() -> None:
    assert npv(_one(phase_probs=np.array([[0.0]])))[0] == pytest.approx(-1_000_000)


def test_the_range_is_ordered_reproducible_and_explained() -> None:
    pos = probability_of_success("phase2", "oncology")
    a = run_rnpv(pos, "phase2", PATIENTS, PRICE)
    b = run_rnpv(pos, "phase2", PATIENTS, PRICE)
    assert a.rnpv == b.rnpv
    assert a.rnpv.p10 <= a.rnpv.p50 <= a.rnpv.p90
    assert a.capital.p50 > 0 and a.months_to_milestone.p50 > 0
    assert any("placeholders" in line for line in a.assumptions)
    assert {name for name, _, _ in a.tornado} >= {"patients", "discount_rate", "peak_share"}


def test_a_bigger_market_gives_a_higher_rnpv() -> None:
    pos = probability_of_success("phase2", "oncology")
    small = run_rnpv(pos, "phase2", PATIENTS, PRICE)
    big = run_rnpv(pos, "phase2", Range(p10=50_000, p50=100_000, p90=200_000), PRICE)
    assert big.rnpv.p50 > small.rnpv.p50


def test_a_tiny_market_is_negative_in_every_scenario() -> None:
    pos = probability_of_success("phase3", "oncology")
    tiny = run_rnpv(pos, "phase3", Range(p10=1, p50=2, p90=3), PRICE)
    assert tiny.rnpv.p90 < 0 and tiny.probability_positive == 0


def test_the_tornado_is_sorted_by_swing() -> None:
    pos = probability_of_success("phase2", "oncology")
    swings = [abs(hi - lo) for _, lo, hi in run_rnpv(pos, "phase2", PATIENTS, PRICE).tornado]
    assert swings == sorted(swings, reverse=True)


def test_a_degenerate_distribution_is_a_point() -> None:
    cfg = RnpvConfig(margin=Tri(low=0.5, mode=0.5, high=0.5))
    pos = probability_of_success("phase1", "oncology")
    assert run_rnpv(pos, "phase1", PATIENTS, PRICE, cfg).rnpv.p10 <= 1e12
