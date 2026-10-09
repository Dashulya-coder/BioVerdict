"""Market size from the frozen bundle: patients, price of approved analogs, and their product.

Pure code over the bundle's records: no model, no network. Each number is read from an evidence
excerpt that a connector stored whole, and the estimate lists those evidence ids. What cannot be
computed is named in `missing`; nothing is filled in.

This is a size of the market, not a forecast of sales: it applies no diagnosis, eligibility,
treatment or uptake rate, and the price is what Medicare spent on analogs, before rebates. Every
such simplification is written into `assumptions`. The ranges are bounds multiplied by bounds,
not a simulation (that is the investment model, B7).
"""

from __future__ import annotations

import csv
import json
import re
import statistics
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from bioverdict.connectors.epidemiology import (
    CANCER_FAMILY,
    CDC_FAMILY,
    ORPHANET_FAMILY,
    POPULATION_FAMILY,
)
from bioverdict.connectors.pricing import SPENDING_FAMILY
from bioverdict.store.models import Bundle, Evidence, Range, TamEstimate

# Orphanet's prevalence classes, as cases per 100,000. A class with no upper bound says only
# that the disease is not rare, which is not a number to multiply.
ORPHANET_CLASSES = {
    "<1 / 1 000 000": (0.0, 0.1),
    "1-9 / 1 000 000": (0.1, 0.9),
    "1-9 / 100 000": (1.0, 9.0),
    "1-5 / 10 000": (10.0, 50.0),
    "6-9 / 10 000": (60.0, 90.0),
}
# Whose prevalence may stand for the United States, best first. A single country's figure may not.
ORPHANET_REGIONS = ("United States", "Worldwide", "Europe")
_PER_BENEFICIARY = re.compile(r"^Avg_Spnd(?:ng)?_Per_Bene_\d{4}$")
_BENEFICIARIES = re.compile(r"^Tot_Benes_\d{4}$")


class MarketEstimate(BaseModel):
    """What could be computed. `tam` is set only when both of its factors are."""

    model_config = ConfigDict(extra="forbid")

    patients: Range | None = None
    patients_basis: str | None = None  # what the count is: prevalent patients, or new cases a year
    annual_price_usd: Range | None = None
    tam: TamEstimate | None = None
    evidence_ids: list[str] = []
    assumptions: list[str] = []
    missing: list[str] = []
    warnings: list[str] = []  # why a number should not be read as a market, when that is likely


def _of(evidence: Iterable[Evidence], family: str) -> list[Evidence]:
    return sorted((e for e in evidence if e.source_family == family), key=lambda e: e.id)


def _number(text: object) -> float | None:
    try:
        return float(str(text).replace(",", "").strip())
    except ValueError:
        return None


def _population(evidence: list[Evidence]) -> dict[str, tuple[float, Evidence]]:
    found = {}
    for item in _of(evidence, POPULATION_FAMILY):
        record = json.loads(item.excerpt)
        value = _number(record.get("value"))
        if value is not None:
            found[record["indicator"]["id"]] = (value, item)
    return found


def _cancer(evidence: list[Evidence], out: MarketEstimate) -> bool:
    for item in _of(evidence, CANCER_FAMILY):
        record = json.loads(item.excerpt)
        columns = next(csv.reader([record["columns"]]))
        # The report repeats column names (the rate's interval, then the trend's): keep the first.
        row: dict[str, str] = {}
        for column, value in zip(columns, next(csv.reader([record["row"]])), strict=False):
            row.setdefault(column, value)
        count = _number(row.get("Average Annual Count"))
        rate = _number(next((v for k, v in row.items() if k.startswith("Age-Adjusted")), None))
        low = _number(row.get("Lower 95% Confidence Interval"))
        high = _number(row.get("Upper 95% Confidence Interval"))
        if count is None:
            continue
        spread = (
            (low / rate, high / rate) if rate and low is not None and high is not None else (1, 1)
        )
        out.patients = Range(p10=count * spread[0], p50=count, p90=count * spread[1])
        out.patients_basis = "new cases a year in the United States"
        out.evidence_ids.append(item.id)
        out.assumptions += [
            (
                f"Patients are the average annual new cases of the registry's site: {record['report']}. "
                "The site may be wider than the indication, and no biomarker, stage or line-of-therapy "
                "fraction is applied."
            ),
            (
                "New cases a year stand for the patients treated in a year; patients treated for "
                "longer than a year are not counted again."
            ),
        ]
        return True
    return False


def _cdc(evidence: list[Evidence], out: MarketEstimate) -> bool:
    population = _population(evidence)
    for item in _of(evidence, CDC_FAMILY):
        record = json.loads(item.excerpt)
        share = _number(record.get("datavalue"))
        low = _number(record.get("lowconfidencelimit"))
        high = _number(record.get("highconfidencelimit"))
        bands = [population.get("SP.POP.1564.TO"), population.get("SP.POP.65UP.TO")]
        if share is None or record.get("datavalueunit") != "%" or None in bands:
            continue
        adults = sum(value for value, _ in bands)  # type: ignore[misc]
        low, high = (share if low is None else low), (share if high is None else high)
        out.patients = Range(
            p10=adults * low / 100, p50=adults * share / 100, p90=adults * high / 100
        )
        out.patients_basis = "people in the United States with the condition"
        out.evidence_ids += [item.id, *(source.id for _, source in bands)]  # type: ignore[misc]
        out.assumptions += [
            (
                f"Patients are the CDC's '{record.get('question')}' ({record.get('yearend')}, "
                f"{record.get('datavaluetype')}) applied to the population aged 15 and over; the "
                "survey covers adults from 18, so the count is slightly high."
            ),
            (
                "Everyone with the condition is counted: no diagnosis, eligibility or treatment rate "
                "is applied."
            ),
        ]
        return True
    return False


def _orphanet(evidence: list[Evidence], out: MarketEstimate) -> bool:
    total = _population(evidence).get("SP.POP.TOTL")
    usable = []
    for item in _of(evidence, ORPHANET_FAMILY):
        record = json.loads(item.excerpt)
        bounds = ORPHANET_CLASSES.get(record.get("PrevalenceClass", ""))
        region = record.get("PrevalenceGeographic")
        if (
            bounds is None
            or region not in ORPHANET_REGIONS
            or record.get("PrevalenceType") != "Point prevalence"
            or record.get("PrevalenceValidationStatus") != "Validated"
        ):
            continue
        mean = _number(record.get("ValMoy")) or 0.0
        stated = bounds[0] <= mean <= bounds[1] and mean > 0
        usable.append(
            (ORPHANET_REGIONS.index(region), not stated, item.id, item, record, bounds, mean)
        )
    if not usable or total is None:
        return False
    _, estimated, _, item, record, (low, high), mean = min(usable, key=lambda entry: entry[:3])
    middle = (low + high) / 2 if estimated else mean
    people, source = total
    out.patients = Range(
        p10=people * low / 100_000, p50=people * middle / 100_000, p90=people * high / 100_000
    )
    out.patients_basis = "people in the United States with the disease"
    out.evidence_ids += [item.id, source.id]
    out.assumptions += [
        (
            f"Patients are Orphanet's point prevalence of {record.get('Name')} "
            f"({record.get('PrevalenceClass')}, {record.get('PrevalenceGeographic')}) applied to the "
            "whole US population; the range is the bounds of that prevalence class."
        ),
        (
            "Everyone with the disease is counted: no diagnosis, eligibility or treatment rate is "
            "applied."
        ),
    ]
    return True


def _price(evidence: list[Evidence], out: MarketEstimate) -> None:
    best: dict[tuple[str, str], tuple[float, float, Evidence]] = {}
    for item in _of(evidence, SPENDING_FAMILY):
        record = json.loads(item.excerpt)
        spent = next((_number(v) for k, v in record.items() if _PER_BENEFICIARY.match(k)), None)
        people = next((_number(v) for k, v in record.items() if _BENEFICIARIES.match(k)), None)
        if not spent or spent <= 0:
            continue
        product = (
            str(record.get("Gnrc_Name", "")).casefold(),
            str(record.get("Brnd_Name", "")).casefold(),
        )
        # A product paid for by both programs is one price point: the larger program speaks.
        if product not in best or (people or 0) > best[product][1]:
            best[product] = (spent, people or 0, item)
    if not best:
        out.missing.append(
            "price: no approved drug against the same target has Medicare spending data"
        )
        return
    prices = sorted(spent for spent, _, _ in best.values())
    out.annual_price_usd = Range(p10=prices[0], p50=statistics.median(prices), p90=prices[-1])
    out.evidence_ids += [item.id for _, _, item in best.values()]
    names = sorted({brand or generic for generic, brand in best})
    out.assumptions += [
        (
            f"Price is Medicare's average spending per beneficiary in the latest reported year on "
            f"{len(prices)} approved product(s) against the same target ({', '.join(names)}): lowest, "
            "median and highest. It is before rebates, covers Medicare patients only, and includes "
            "patients treated for part of the year."
        ),
        "The analogs may be approved for other indications and other doses than the candidate's.",
    ]


# More than the world's largest drug class earns a year (GLP-1 agonists, about $50-70 billion).
IMPLAUSIBLE_USD = 100e9
_PREVALENT = "people in the United States with"


def _warnings(out: MarketEstimate) -> list[str]:
    """Plain-language cautions: arithmetic over everyone with a condition is a ceiling."""
    warnings = []
    if out.patients_basis and out.patients_basis.startswith(_PREVALENT):
        warnings.append(
            "The patient count is everyone with the condition. Most are not diagnosed, eligible "
            "or treated with a new drug, so a market size built on it is a ceiling, not a market."
        )
    if out.tam is not None and out.tam.tam_usd.p90 > IMPLAUSIBLE_USD:
        warnings.append(
            f"The upper bound is above ${IMPLAUSIBLE_USD / 1e9:,.0f} billion a year, more than "
            "the largest drug class earns today. Read it as arithmetic, not as a market."
        )
    return warnings


def estimate_market(bundle: Bundle) -> MarketEstimate:
    """Patients, analog price and their product, from the bundle alone."""
    out = MarketEstimate()
    evidence = bundle.evidence
    # A measured national count first, then a measured US rate, then a rare-disease class.
    if not (_cancer(evidence, out) or _cdc(evidence, out) or _orphanet(evidence, out)):
        out.missing.append(
            "patients: the bundle has no usable epidemiology for the indication (covered: cancer "
            "sites of the US registry report, the CDC's chronic disease indicators, Orphanet "
            "point prevalence for the US, the world or Europe)"
        )
    _price(evidence, out)
    out.evidence_ids = sorted(set(out.evidence_ids))
    if out.patients is not None and out.annual_price_usd is not None:
        patients, price = out.patients, out.annual_price_usd
        out.assumptions.append(
            "Market size is patients times price, bound by bound: low with low, middle with "
            "middle, high with high. It is the size of the market at analog prices, not a sales "
            "forecast: no market share or uptake is applied."
        )
        out.tam = TamEstimate(
            addressable_patients=patients,
            annual_price_usd=price,
            tam_usd=Range(
                p10=patients.p10 * price.p10,
                p50=patients.p50 * price.p50,
                p90=patients.p90 * price.p90,
            ),
            evidence_ids=out.evidence_ids,
            assumptions=out.assumptions,
        )
    out.warnings = _warnings(out)
    return out
