"""Probability of success (Layer 3): benchmark phase transitions x bounded modifiers -> a range.

Output is always a P10/P50/P90 range and is `modeled`: its assumptions are returned with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import prod

import numpy as np
from pydantic import BaseModel, ConfigDict

from bioverdict.scoring import benchmarks as bm
from bioverdict.store.models import Range


class PosConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pseudo_n: float = 150.0  # effective sample size behind one phase-transition rate
    sparse_n_divisor: float = 4.0  # fewer effective samples when evidence is sparse: wider range
    draws: int = 10_000
    seed: int = 0  # fixed: the same input always gives the same range
    modifier_min: float = 0.2  # each modifier is bounded
    modifier_max: float = 3.0
    pos_cap: float = 0.95  # a modifier cannot push a probability above this


@dataclass(frozen=True)
class Modifier:
    """A multiplicative adjustment of PoS, always with its cited basis."""

    name: str
    factor: float
    basis: str


def genetic_support_modifier() -> Modifier:
    return Modifier(
        "human genetic support", bm.GENETIC_SUPPORT_RELATIVE_SUCCESS, bm.GENETIC_SUPPORT_SOURCE
    )


@dataclass(frozen=True)
class PosResult:
    pos: Range
    base_probability: float  # product of remaining phase transitions, before modifiers
    transitions: dict[str, float]
    modifiers: list[Modifier]
    assumptions: list[str] = field(default_factory=list)


def phase_transitions(area: str | None = None) -> tuple[dict[str, float], str, list[str]]:
    """Benchmark transitions, their source and any assumption made to obtain them.

    Oncology uses the published phase transitions of the BIO 2021 report. Other areas have only
    a published LOA from Phase I, so the all-disease transitions of the first three phases are
    scaled by one common factor that reproduces that LOA (NDA/BLA stays as reported).
    """
    area = (area or "all").lower()
    if area == "oncology":
        return dict(bm.BIO_2021_ONCOLOGY), bm.BIO_2021_ONCOLOGY_SOURCE, []
    if area not in bm.LOA_BY_AREA:
        raise ValueError(f"unknown therapy area {area!r}; known: {sorted(bm.LOA_BY_AREA)}")
    base = dict(bm.ALL_DISEASES)
    ratio = bm.LOA_BY_AREA[area] / prod(base.values())
    if abs(ratio - 1) < 1e-6:
        return base, bm.CITELINE_2024_SOURCE, []
    scale = ratio ** (1 / 3)
    scaled = {k: (min(v * scale, 0.99) if k != "nda" else v) for k, v in base.items()}
    note = (
        f"{area}: only LOA from Phase I ({bm.LOA_BY_AREA[area]:.1%}) is published, so the first "
        f"three all-disease phase transitions were scaled by {scale:.3f} each (derived)"
    )
    return scaled, bm.CITELINE_2024_SOURCE, [note]


def probability_of_success(
    stage: str = "phase1",
    area: str | None = None,
    modifiers: list[Modifier] | None = None,
    sparse: bool = False,
    cfg: PosConfig | None = None,
) -> PosResult:
    """PoS from `stage` (the phase the asset is entering) to approval, as a P10/P50/P90 range."""
    cfg = cfg or PosConfig()
    if stage not in bm.PHASES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {bm.PHASES}")
    modifiers = modifiers or []
    transitions, source, assumptions = phase_transitions(area)
    remaining = bm.PHASES[bm.PHASES.index(stage) :]
    probs = np.array([transitions[p] for p in remaining])
    base = float(prod(probs))

    factor = 1.0
    for m in modifiers:
        bounded = min(max(m.factor, cfg.modifier_min), cfg.modifier_max)
        if bounded != m.factor:
            assumptions.append(f"modifier '{m.name}' factor {m.factor} bounded to {bounded}")
        factor *= bounded
        assumptions.append(f"modifier '{m.name}' x{bounded}: {m.basis}")
    assumptions.append(f"phase-transition benchmark: {source}")

    n = cfg.pseudo_n / (cfg.sparse_n_divisor if sparse else 1.0)
    if sparse:
        assumptions.append("evidence is sparse: range widened (fewer effective samples)")
    rng = np.random.default_rng(cfg.seed)
    draws = rng.beta(probs * n, (1 - probs) * n, size=(cfg.draws, len(probs)))
    pos = np.minimum(draws.prod(axis=1) * factor, cfg.pos_cap)
    p10, p50, p90 = (float(x) for x in np.percentile(pos, [10, 50, 90]))
    return PosResult(
        pos=Range(p10=p10, p50=p50, p90=p90),
        base_probability=base,
        transitions={p: float(transitions[p]) for p in remaining},
        modifiers=modifiers,
        assumptions=assumptions,
    )
