"""PoS and rNPV of a frozen bundle, for the verdict and for the report.

Stage and therapy area are read from the bundle by fixed rules and the rules are returned as
assumptions. When a stage cannot be read, the market cannot be sized, or its size is a ceiling
rather than a market, no figure is invented: `missing` says what is lacking and the verdict
stays without rNPV (so it cannot be Invest).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from bioverdict.market.tam import IMPLAUSIBLE_USD, estimate_market
from bioverdict.scoring.pos import PosResult, probability_of_success
from bioverdict.scoring.rnpv import RnpvResult, run_rnpv
from bioverdict.store.models import Bundle, VerdictResult

_STAGE = re.compile(r"maximumClinicalStage\W{1,6}PHASE_(\d)", re.IGNORECASE)
_PHASE = re.compile(r"PHASE_(\d)", re.IGNORECASE)
_APPROVED = "APPROVAL"  # Open Targets' name of the stage of an approved drug
IN_INDICATION = "its stage in the run's indication"
ANY_INDICATION = "its highest stage in any indication: the bundle gives none for this one"
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


def _stage_in_indication(excerpt: str) -> str | None:
    """The stage Open Targets gives the asset in the run's indication, when the record has it."""
    try:
        row = json.loads(excerpt).get("indication")
    except ValueError, AttributeError:
        return None
    stage = row.get("maxClinicalStage") if isinstance(row, dict) else None
    known = isinstance(stage, str) and (_PHASE.match(stage) or stage.upper() == _APPROVED)
    return stage if known else None


def _highest(phases: dict[str, int]) -> tuple[str | None, list[str]]:
    best = max(phases.values(), default=0)
    if best == 0:
        return None, []
    return f"phase{min(best, 3)}", [i for i, phase in phases.items() if phase == best]


def read_stage(bundle: Bundle) -> tuple[str | None, list[str], str]:
    """The phase the asset is entering (Phase 1 to 3), the records it was read from, and which
    stage it is: the asset's stage in the run's indication when the bundle reports one (Open
    Targets), otherwise its highest `maximumClinicalStage` in any indication. A drug in Phase 3
    for one disease is not in Phase 3 for another."""
    here = {
        item.id: stage
        for item in bundle.evidence
        if (stage := _stage_in_indication(item.excerpt)) is not None
    }
    if here:  # an asset already approved in the indication has no phase left: nothing to model
        phases = {i: int(m.group(1)) for i, stage in here.items() if (m := _PHASE.match(stage))}
        return (*_highest(phases), IN_INDICATION)
    anywhere = {
        item.id: max(int(digit) for digit in digits)
        for item in bundle.evidence
        if (digits := _STAGE.findall(item.excerpt))
    }
    return (*_highest(anywhere), ANY_INDICATION)


def financial_model(bundle: Bundle, indication: str) -> Financials:
    out = Financials()
    out.stage, out.evidence_ids, which = read_stage(bundle)
    out.area = "oncology" if _CANCER.search(indication) else "all"
    if out.stage is None:
        out.missing.append(
            "stage: the bundle reports no clinical stage (Phase 1 to 3) for the asset, so PoS "
            "and rNPV are not computed"
        )
        return out
    out.assumptions.append(
        f"stage: {out.stage}, read from the bundle as {which} "
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
    if tam.tam_usd.p90 > IMPLAUSIBLE_USD:
        out.missing.append(
            f"rNPV: the market size reaches ${tam.tam_usd.p90 / 1e9:,.0f} billion a year, above "
            f"the ${IMPLAUSIBLE_USD / 1e9:,.0f} billion the largest drug class earns: it counts "
            "everyone with the condition and is a ceiling, not a market a share can be taken of "
            "(see market)"
        )
        return out
    out.evidence_ids = sorted(set(out.evidence_ids) | set(tam.evidence_ids))
    out.rnpv = run_rnpv(out.pos, out.stage, tam.addressable_patients, tam.annual_price_usd)
    out.assumptions += out.rnpv.assumptions
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
