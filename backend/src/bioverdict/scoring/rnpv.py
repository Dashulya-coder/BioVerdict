"""Layers 4 and 5: risk-adjusted NPV by Monte Carlo, capital and time to the next milestone.

Everything here is `modeled`. The model is a plain function of its inputs (`npv`), so the same
function gives the P10/P50/P90 range (inputs sampled), the tornado (one input moved at a time)
and the tests (a hand-computed case). Inputs that no source in the bundle supports are
placeholders in `RnpvConfig`: they are returned with the result as assumptions, never hidden,
and they are the first thing to calibrate (docs/scoring.md, Layer 4).

Money is in US dollars, time in years from today. Phase costs are paid at the start of the phase
and weighted by the probability of reaching it; revenue starts at approval and is weighted by
the probability of approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from bioverdict.scoring import benchmarks as bm
from bioverdict.scoring.pos import PosResult
from bioverdict.store.models import Range


class Tri(BaseModel):
    """A triangular distribution: the cheapest honest way to state a range and a best guess."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    low: float
    mode: float
    high: float

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        if self.low == self.high:
            return np.full(n, self.mode)
        return rng.triangular(self.low, self.mode, self.high, size=n)


# Defaults per remaining phase: duration in years and cost in USD. PLACEHOLDERS, not benchmarks.
_DURATION = {
    "phase1": Tri(low=1.0, mode=1.5, high=2.5),
    "phase2": Tri(low=1.5, mode=2.5, high=3.5),
    "phase3": Tri(low=2.5, mode=3.5, high=5.0),
    "nda": Tri(low=0.8, mode=1.0, high=1.5),
}
_COST = {
    "phase1": Tri(low=3e6, mode=6e6, high=12e6),
    "phase2": Tri(low=10e6, mode=20e6, high=40e6),
    "phase3": Tri(low=40e6, mode=80e6, high=200e6),
    "nda": Tri(low=2e6, mode=3e6, high=5e6),
}


class RnpvConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draws: int = Field(default=10_000, ge=100)
    seed: int = 0
    discount_rate: Tri = Tri(low=0.08, mode=0.10, high=0.12)
    peak_share: Tri = Tri(low=0.05, mode=0.15, high=0.30)  # of the addressable patients treated
    net_price_factor: Tri = Tri(low=0.6, mode=0.75, high=0.9)  # analog price after rebates
    margin: Tri = Tri(low=0.4, mode=0.55, high=0.7)  # contribution margin on net sales
    ramp_years: Tri = Tri(low=3.0, mode=4.0, high=6.0)  # linear climb to peak sales
    exclusivity_years: Tri = Tri(low=8.0, mode=10.0, high=12.0)  # sales years; none after
    durations: dict[str, Tri] = Field(default_factory=lambda: dict(_DURATION))
    costs: dict[str, Tri] = Field(default_factory=lambda: dict(_COST))


@dataclass(frozen=True)
class Inputs:
    """One draw (arrays of length n) or the base case (arrays of length 1) of every input."""

    phase_probs: np.ndarray  # (n, phases): success of each remaining phase
    modifier: float
    pos_cap: float
    patients: np.ndarray
    price: np.ndarray
    peak_share: np.ndarray
    net_price_factor: np.ndarray
    margin: np.ndarray
    ramp_years: np.ndarray
    exclusivity_years: np.ndarray
    discount_rate: np.ndarray
    durations: np.ndarray  # (n, phases) years
    costs: np.ndarray  # (n, phases) USD


def npv(x: Inputs) -> np.ndarray:
    """Risk-adjusted NPV for every row of `x`."""
    n, phases = x.phase_probs.shape
    r = x.discount_rate
    start = np.concatenate([np.zeros((n, 1)), np.cumsum(x.durations, axis=1)], axis=1)
    reach = np.concatenate([np.ones((n, 1)), np.cumprod(x.phase_probs, axis=1)], axis=1)
    cost = (reach[:, :phases] * x.costs / (1 + r[:, None]) ** start[:, :phases]).sum(axis=1)

    approval = np.minimum(reach[:, phases] * x.modifier, x.pos_cap)
    launch = start[:, phases]
    peak = x.patients * x.price * x.net_price_factor * x.peak_share
    years = np.arange(1, 31)[None, :]  # year j of sales is discounted at the end of the year
    ramp = np.minimum(years / np.maximum(x.ramp_years[:, None], 1.0), 1.0)
    alive = years <= x.exclusivity_years[:, None]
    flow = peak[:, None] * x.margin[:, None] * ramp * alive
    value = (flow / (1 + r[:, None]) ** (launch[:, None] + years)).sum(axis=1)
    return approval * value - cost


@dataclass
class RnpvResult:
    rnpv: Range
    capital: Range  # USD to reach approval if every phase is run (not probability-weighted)
    months_to_milestone: Range  # end of the current phase
    tornado: list[tuple[str, float, float]]  # input, rNPV at its low end, rNPV at its high end
    assumptions: list[str] = field(default_factory=list)
    probability_positive: float = 0.0


def _range(values: np.ndarray) -> Range:
    p10, p50, p90 = (float(v) for v in np.percentile(values, [10, 50, 90]))
    return Range(p10=p10, p50=p50, p90=p90)


def _tri_of(r: Range) -> Tri:
    # P10/P50/P90 stand in for the low, middle and high of a triangle: the tails are a little
    # shorter than a true P0/P100, which is the safe side for a market size.
    return Tri(low=r.p10, mode=r.p50, high=r.p90)


def run_rnpv(
    pos: PosResult,
    stage: str,
    patients: Range,
    annual_price_usd: Range,
    cfg: RnpvConfig | None = None,
    pos_cap: float = 0.95,
) -> RnpvResult:
    """The rNPV range, capital, time to milestone and tornado of an asset entering `stage`."""
    cfg = cfg or RnpvConfig()
    if pos.draws is None:
        raise ValueError("the PoS result carries no draws")
    remaining = bm.PHASES[bm.PHASES.index(stage) :]
    rng = np.random.default_rng(cfg.seed)
    n = min(cfg.draws, len(pos.draws))

    def many(tri: Tri) -> np.ndarray:
        return tri.sample(rng, n)

    scalars = {
        "patients": _tri_of(patients),
        "price": _tri_of(annual_price_usd),
        "peak_share": cfg.peak_share,
        "net_price_factor": cfg.net_price_factor,
        "margin": cfg.margin,
        "ramp_years": cfg.ramp_years,
        "exclusivity_years": cfg.exclusivity_years,
        "discount_rate": cfg.discount_rate,
    }
    sampled = {name: many(tri) for name, tri in scalars.items()}
    durations = np.stack([many(cfg.durations[p]) for p in remaining], axis=1)
    costs = np.stack([many(cfg.costs[p]) for p in remaining], axis=1)
    inputs = Inputs(
        phase_probs=pos.draws[:n],
        modifier=pos.factor,
        pos_cap=pos_cap,
        durations=durations,
        costs=costs,
        **sampled,
    )
    values = npv(inputs)

    def at(**override: float) -> float:
        base = {k: np.array([t.mode]) for k, t in scalars.items()} | {
            k: np.array([v]) for k, v in override.items()
        }
        mid = Inputs(
            phase_probs=np.median(pos.draws[:n], axis=0)[None, :],
            modifier=pos.factor,
            pos_cap=pos_cap,
            durations=np.array([[cfg.durations[p].mode for p in remaining]]),
            costs=np.array([[cfg.costs[p].mode for p in remaining]]),
            **base,
        )
        return float(npv(mid)[0])

    tornado = sorted(
        ((name, at(**{name: tri.low}), at(**{name: tri.high})) for name, tri in scalars.items()),
        key=lambda row: -abs(row[2] - row[1]),
    )
    total = costs.sum(axis=1)
    months = durations[:, 0] * 12
    return RnpvResult(
        rnpv=_range(values),
        capital=_range(total),
        months_to_milestone=_range(months),
        tornado=tornado,
        probability_positive=float((values > 0).mean()),
        assumptions=_assumptions(cfg, remaining, patients, annual_price_usd),
    )


def _tri_text(t: Tri) -> str:
    return f"{t.low:g} / {t.mode:g} / {t.high:g}"


def _assumptions(cfg: RnpvConfig, remaining: list[str], patients: Range, price: Range) -> list[str]:
    lines = [
        (
            f"rNPV is modeled: {cfg.draws:,} draws of the inputs, risk-weighted costs and "
            "revenue; the figures below are placeholders to calibrate, not sourced benchmarks"
        ),
        (
            f"addressable patients (P10/P50/P90): {patients.p10:,.0f} / {patients.p50:,.0f} / "
            f"{patients.p90:,.0f}; annual analog price: ${price.p10:,.0f} / "
            f"${price.p50:,.0f} / ${price.p90:,.0f}"
        ),
        f"peak share of patients treated (low/mode/high): {_tri_text(cfg.peak_share)}",
        f"net price after rebates, share of analog price: {_tri_text(cfg.net_price_factor)}",
        f"contribution margin on net sales: {_tri_text(cfg.margin)}",
        f"years from launch to peak sales: {_tri_text(cfg.ramp_years)}",
        f"years of sales before exclusivity ends (none after): {_tri_text(cfg.exclusivity_years)}",
        f"discount rate: {_tri_text(cfg.discount_rate)}",
    ]
    for phase in remaining:
        lines.append(
            f"{phase}: {_tri_text(cfg.durations[phase])} years, ${_tri_text(cfg.costs[phase])} cost"
        )
    return lines
