"""PoS and rNPV of a frozen bundle, for the verdict and for the report.

Stage and therapy area are read from the bundle by fixed rules and the rules are returned as
assumptions. When a stage cannot be read or the market cannot be sized, no figure is invented:
`missing` says what is lacking and the verdict stays without rNPV (so it cannot be Invest).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bioverdict.market.tam import estimate_market
from bioverdict.scoring import benchmarks as bm
from bioverdict.scoring.pos import PosResult, probability_of_success
from bioverdict.scoring.rnpv import RnpvResult, run_rnpv
from bioverdict.store.models import Bundle, VerdictResult

_STAGE = re.compile(r"maximumClinicalStage\W{1,6}PHASE_(\d)", re.IGNORECASE)
_CANCER = re.compile(
    r"cancer|carcinoma|tumou?r|neoplasm|lymphoma|leuk(?:a)?emia|melanoma|sarcoma|myeloma|glioma|"
    r"blastoma|nsclc|malignan",
    re.IGNORECASE,
)


@dataclass
class Financials:
    stage: str | None = None
    area: str | None = None
    pos: PosResult | None = None
    rnpv: RnpvResult | None = None
    evidence_ids: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def read_stage(bundle: Bundle) -> tuple[str | None, list[str]]:
    """The phase the asset is entering: the highest `maximumClinicalStage` the bundle reports
    for it (Open Targets), as long as it is Phase 1 to 3."""
    best, ids = 0, []
    for item in bundle.evidence:
        for digit in _STAGE.findall(item.excerpt):
            if int(digit) > best:
                best, ids = int(digit), [item.id]
            elif int(digit) == best and item.id not in ids:
                ids.append(item.id)
    if best == 0:
        return None, []
    return f"phase{min(best, 3)}", ids


def financial_model(bundle: Bundle, indication: str) -> Financials:
    out = Financials()
    out.stage, out.evidence_ids = read_stage(bundle)
    out.area = "oncology" if _CANCER.search(indication) else "all"
    if out.stage is None:
        out.missing.append(
            "stage: the bundle reports no clinical stage (Phase 1 to 3) for the asset, so PoS "
            "and rNPV are not computed"
        )
        return out
    out.assumptions.append(
        f"stage: the highest clinical stage the bundle reports for the asset is {out.stage} "
        f"(PoS counts from that phase to approval)"
    )
    out.assumptions.append(
        f"therapy area for phase-transition benchmarks: {out.area} "
        f"({'indication names a cancer' if out.area == 'oncology' else 'all diseases'})"
    )
    out.pos = probability_of_success(out.stage, out.area)
    out.assumptions += out.pos.assumptions
    tam = estimate_market(bundle).tam
    if tam is None:
        out.missing.append("rNPV: the market could not be sized from the bundle (see market)")
        return out
    out.evidence_ids = sorted(set(out.evidence_ids) | set(tam.evidence_ids))
    out.rnpv = run_rnpv(out.pos, out.stage, tam.addressable_patients, tam.annual_price_usd)
    out.assumptions += out.rnpv.assumptions
    assert out.stage in bm.PHASES
    return out


def with_financials(result: VerdictResult, fin: Financials) -> VerdictResult:
    """The verdict with PoS, rNPV, capital and time to milestone filled in where computed."""
    update: dict[str, object] = {}
    if fin.pos is not None:
        update["pos"] = fin.pos.pos
    if fin.rnpv is not None:
        update |= {
            "rnpv": fin.rnpv.rnpv,
            "capital": fin.rnpv.capital,
            "months_to_milestone": fin.rnpv.months_to_milestone,
        }
    return result.model_copy(update=update)
