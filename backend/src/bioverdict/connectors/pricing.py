"""Prices of approved analogs: Open Targets names them, CMS says what Medicare spent (A9).

An unapproved drug has no price. What exists is the spending on approved drugs against the same
target, so this connector reads, for every target of the query:

1. the drugs Open Targets lists as approved for that target (the analogs);
2. each analog's row in the CMS "Medicare Part D / Part B Spending by Drug" data.

Every record is a status fact: it is stored whole and no model reads it. The market size is
computed from these records by code (`bioverdict/market/tam.py`).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime

import httpx

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.opentargets import SITE_URL, OpenTargetsApi
from bioverdict.resolver.names import normalize
from bioverdict.store.as_of import filter_as_of
from bioverdict.store.models import Evidence, EvidenceLevel, Locator, ResolverOutput, SourceKind

log = logging.getLogger(__name__)

ANALOG_FAMILY = "approved_analog"
SPENDING_FAMILY = "cms_spending"
APPROVED = "APPROVAL"  # Open Targets' name of the stage of an approved drug
MAX_ANALOGS = 8  # per target; a class rarely has more approved members

ANALOGS_QUERY = """
query ($id: String!) {
  target(ensemblId: $id) {
    id approvedSymbol
    drugAndClinicalCandidates {
      rows { drug { id name drugType maximumClinicalStage tradeNames { label } } }
    }
  }
}
"""

CMS_API = "https://data.cms.gov/data-api/v1/dataset"
# The annual "Spending by Drug" data sets (data.cms.gov, catalog entries of the same names).
PROGRAMS = {
    "Medicare Part D": "7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b",
    "Medicare Part B": "76a714ad-3a2c-43ac-b76d-9dadf8f7d890",
}
_PER_BENEFICIARY = re.compile(r"^Avg_Spnd(?:ng)?_Per_Bene_(\d{4})$")
_SUFFIX = re.compile(r"-[a-z]{4}$")  # the four-letter suffix of a biologic: "lecanemab-irmb"


def analogs_payload(ensembl_id: str) -> dict:
    return {"query": ANALOGS_QUERY, "variables": {"id": ensembl_id}}


def parse_analogs(answer: dict, retrieved_at: datetime) -> list[Evidence]:
    """One record per drug approved against the target, named as the database names it."""
    target = (answer.get("data") or {}).get("target")
    if not target:
        return []
    rows = ((target.get("drugAndClinicalCandidates") or {}).get("rows")) or []
    drugs = {row["drug"]["id"]: row["drug"] for row in rows if row.get("drug")}
    approved = [d for d in drugs.values() if d.get("maximumClinicalStage") == APPROVED]
    evidence = []
    for drug in sorted(approved, key=lambda d: d["id"])[:MAX_ANALOGS]:
        fragment = {"target": target["approvedSymbol"], "drug": drug}
        evidence.append(
            Evidence(
                id=f"analog:{target['id']}:{drug['id']}",  # placeholder until the freeze
                source="Open Targets",
                source_family=ANALOG_FAMILY,
                source_kind=SourceKind.REGISTRY,
                url=f"{SITE_URL}/target/{target['id']}",
                locator=Locator(type="chembl", value=drug["id"]),
                excerpt=json.dumps(fragment, ensure_ascii=False),
                published_at=None,
                retrieved_at=retrieved_at,
                level=EvidenceLevel.REGISTRY_RECORD,
                independence_group="database:opentargets-clinical",
                status_key=f"analog:{target['id']}:{drug['id']}",
                version=1,
            )
        )
    return evidence


def analog_name(evidence: Evidence) -> str:
    return json.loads(evidence.excerpt)["drug"]["name"]


def _same_drug(generic: str, analog: str) -> bool:
    """CMS writes 'Lecanemab-Irmb' and 'Sotorasib'; a combination product is another drug."""
    name = _SUFFIX.sub("", generic.strip().casefold())
    return normalize(name) == normalize(analog)


def latest_year(row: dict) -> int | None:
    """The latest year for which the row reports spending per beneficiary."""
    years = [
        int(match.group(1))
        for key, value in row.items()
        if (match := _PER_BENEFICIARY.match(key)) and str(value).strip()
    ]
    return max(years, default=None)


def parse_spending(
    rows: list[dict], analog: str, program: str, url: str, retrieved_at: datetime
) -> list[Evidence]:
    """The analog's overall row of one program, cut to its latest year. Fields keep CMS's names."""
    evidence = []
    for row in rows:
        year = latest_year(row)
        overall = row.get("Mftr_Name", "Overall") == "Overall"  # Part B has no manufacturer rows
        if year is None or not overall or not _same_drug(row.get("Gnrc_Name", ""), analog):
            continue
        fields = ("Brnd_Name", "Gnrc_Name", "HCPCS_Cd", "HCPCS_Desc")
        fragment = {"program": program, "year": year}
        fragment |= {name: row[name] for name in fields if row.get(name)}
        fragment |= {key: value for key, value in row.items() if key.endswith(f"_{year}") and value}
        key = normalize(f"{row.get('Brnd_Name', '')}{row.get('HCPCS_Cd', '')}")
        evidence.append(
            Evidence(
                id=f"cms:{program}:{analog}:{key}",  # placeholder until the freeze
                source=f"CMS {program} Spending by Drug",
                source_family=SPENDING_FAMILY,
                source_kind=SourceKind.REGULATOR,
                url=url,
                locator=Locator(type="cms_drug", value=row.get("Gnrc_Name", analog)),
                excerpt=json.dumps(fragment, ensure_ascii=False),
                # A snapshot of the current release: visible from the day it was downloaded.
                published_at=None,
                retrieved_at=retrieved_at,
                level=EvidenceLevel.REGISTRY_RECORD,
                independence_group="payer:cms",
                status_key=f"cms:{normalize(program)}:{normalize(analog)}:{key}",
                version=1,
            )
        )
    return evidence


class AnalogPricingConnector:
    """Satisfies `Connector`. Needs an Ensembl id for the target; without one nothing is read.

    A CMS request that fails does not hide the other analogs: it is listed in `problems`.
    """

    name = "analog_pricing"

    def __init__(self, http: CachedHttpClient) -> None:
        self._http = http
        self._api = OpenTargetsApi(http)
        self.problems: list[str] = []

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        self.problems = []
        own = {normalize(name) for name in query.known_assets}
        own |= {normalize(asset.name) for asset in query.assets}
        evidence: list[Evidence] = []
        for target in query.targets:
            if target.ensembl is None:
                continue
            answer, fetched_at = await self._api.query(analogs_payload(target.ensembl))
            # The asset itself is not its own analog (it has no price until it is approved).
            analogs = [
                item
                for item in parse_analogs(answer, fetched_at)
                if normalize(analog_name(item)) not in own
            ]
            evidence += analogs
            for name in dict.fromkeys(analog_name(item) for item in analogs):
                evidence += await self._spending(name)
        return filter_as_of(evidence, as_of)

    async def _spending(self, analog: str) -> list[Evidence]:
        found: list[Evidence] = []
        for program, dataset in PROGRAMS.items():
            url = f"{CMS_API}/{dataset}/data"
            params = {"keyword": analog, "size": "50"}
            try:
                response = await self._http.get(url, params)
                rows = json.loads(response.body)
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("%s spending of %s not read: %s", program, analog, exc)
                self.problems.append(f"{program} spending of {analog} could not be read")
                continue
            source = str(httpx.URL(url, params=params))
            found += parse_spending(rows, analog, program, source, response.fetched_at)
        return found
