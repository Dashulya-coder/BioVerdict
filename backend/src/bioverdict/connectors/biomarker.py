"""How common the asset's biomarker is among patients with the cancer (A9).

A drug against a mutated protein treats only the patients whose tumour carries that mutation:
a KRAS G12C inhibitor is for about one lung cancer in eight, not for all of them. The cancer
registry counts every case, so without this fraction the market size is several times too large.

Nothing here is a model's number or a figure from memory:

1. the variant is read by code from the asset's registry records ("KRAS G12C-positive"), and
   only when one variant of a target is named clearly more often than any other;
2. its frequency is counted by code in an open sequencing cohort, the MSK-IMPACT Clinical
   Sequencing Cohort (Zehir et al., Nat Med 2017, about 10,000 patients) served by cBioPortal:
   patients of the cancer type whose tumour has that protein change, out of all patients of
   that type. A patient with several samples is counted once.

The record holds the two counts, not a percentage; `market/tam.py` computes the fraction and
its interval. The cohort is one referral centre's patients with advanced cancer, so it stands
for the newly diagnosed population only roughly, and the market estimate says so. Only point
mutations of a target gene are covered: no fusions, amplifications, expression levels or
signatures such as MSI-high.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import date, datetime

from bioverdict.connectors.clinicaltrials import ClinicalTrialsConnector
from bioverdict.connectors.epidemiology import CANCER_SITES, MARKET_RECORD
from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.validate import json_object, json_rows
from bioverdict.store.as_of import filter_as_of
from bioverdict.store.models import Evidence, Locator, ResolverOutput, SourceKind

log = logging.getLogger(__name__)

API_URL = "https://www.cbioportal.org/api"
STUDY_PAGE = "https://www.cbioportal.org/study/summary?id="
FAMILY = "biomarker_frequency"
STUDY = "msk_impact_2017"
# The cohort's name of the cancer type for each registry site the market size can count.
COHORT_TYPES = {
    "047": "Non-Small Cell Lung Cancer",
    "040": "Pancreatic Cancer",
    "020": "Colorectal Cancer",
}
HEADERS = {"User-Agent": "bioverdict-hackathon", "Accept": "application/json"}
MIN_PATIENTS = 100  # of the cancer type; a fraction of fewer says too little


def named_variant(records: list[Evidence], symbols: list[str]) -> tuple[str, str, int] | None:
    """The gene, the protein change and the number of records that name it, when one variant
    of a target is named in more records than any other ("KRAS G12C", "KRAS p.G12C").

    A drug described with several variants (a pan-KRAS inhibitor) has no single biomarker here.
    """
    counts: Counter[tuple[str, str]] = Counter()
    for symbol in symbols:
        pattern = re.compile(rf"\b{re.escape(symbol)}[\s-]*(?:p\.)?([A-Z]\d{{1,4}}[A-Z])\b")
        for record in records:
            for change in set(pattern.findall(record.excerpt)):
                counts[(symbol, change)] += 1
    ranked = counts.most_common(2)
    if not ranked or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
        return None
    (symbol, change), seen = ranked[0]
    return symbol, change, seen


def count_patients(
    samples: list[dict], mutations: list[dict], cancer_type: str, change: str
) -> tuple[int, int]:
    """Patients of the cancer type with the protein change, and all patients of that type."""
    of_type = {s["sampleId"]: s["patientId"] for s in samples if s.get("value") == cancer_type}
    carriers = {
        of_type[m["sampleId"]]
        for m in mutations
        if m.get("proteinChange") == change and m.get("sampleId") in of_type
    }
    return len(carriers), len(set(of_type.values()))


class BiomarkerFrequencyConnector:
    """Satisfies `Connector`. Reads the registry (from the cache when it ran first) for the
    variant. Gives nothing without an asset, for an indication outside `COHORT_TYPES`, for a
    target without one clear variant, and for a gene the cohort shows no mutation of at all."""

    name = "biomarker_frequency"

    def __init__(self, http: CachedHttpClient, registry: ClinicalTrialsConnector) -> None:
        self._http = http
        self._registry = registry

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        disease = query.indication.mondo_id or query.indication.efo_id
        cancer_type = COHORT_TYPES.get(CANCER_SITES.get(disease or "", ""))
        if cancer_type is None:
            return []
        if not query.known_assets:
            return []  # the variant is the asset's: a class of drugs names several
        symbols = [target.symbol for target in query.targets if target.symbol]
        named = named_variant(await self._registry.fetch(query, as_of), symbols)
        if named is None:
            return []
        symbol, change, seen = named

        gene = await self._json(f"/genes/{symbol}", json_object("entrezGeneId"))
        study = await self._json(f"/studies/{STUDY}", json_object("studyId"))
        samples = await self._json(
            f"/studies/{STUDY}/clinical-data",
            json_rows,
            {
                "clinicalDataType": "SAMPLE",
                "attributeId": "CANCER_TYPE",
                "projection": "SUMMARY",
                "pageSize": "50000",
            },
        )
        response = await self._http.post_json(
            f"{API_URL}/molecular-profiles/{STUDY}_mutations/mutations/fetch?projection=SUMMARY",
            {"entrezGeneIds": [gene["entrezGeneId"]], "sampleListId": f"{STUDY}_all"},
            validate=json_rows,
            headers=HEADERS,
        )
        mutations = json.loads(response.body)
        carriers, patients = count_patients(samples, mutations, cancer_type, change)
        if not mutations or patients < MIN_PATIENTS:
            return []  # the gene is not on the panel, or too few patients to say anything
        return filter_as_of(
            [
                self._record(
                    study,
                    cancer_type,
                    symbol,
                    change,
                    seen,
                    carriers,
                    patients,
                    response.fetched_at,
                )
            ],
            as_of,
        )

    async def _json(self, path: str, validate, params: dict[str, str] | None = None):
        response = await self._http.get(API_URL + path, params, validate=validate, headers=HEADERS)
        return json.loads(response.body)

    @staticmethod
    def _record(
        study: dict,
        cancer_type: str,
        symbol: str,
        change: str,
        seen: int,
        carriers: int,
        patients: int,
        retrieved_at: datetime,
    ) -> Evidence:
        fragment = {
            "study": study["studyId"],
            "study_name": study.get("name"),
            "citation": study.get("citation"),
            "pmid": study.get("pmid"),
            "cancer_type": cancer_type,
            "gene": symbol,
            "protein_change": change,
            "patients_with_variant": carriers,
            "patients_sequenced": patients,
            "counted": "by code from the study's sample and mutation tables; a patient once",
            "variant_named_in_registry_records": seen,
        }
        key = f"biomarker:{study['studyId']}:{cancer_type}:{symbol}:{change}"
        return Evidence(
            id=key,  # placeholder until the freeze
            source=f"cBioPortal: {study.get('name') or study['studyId']}",
            source_family=FAMILY,
            source_kind=SourceKind.PEER_REVIEWED,
            url=STUDY_PAGE + study["studyId"],
            locator=Locator(type="cbioportal_study", value=study["studyId"]),
            excerpt=json.dumps(fragment, ensure_ascii=False),
            published_at=None,  # a snapshot of the portal's current copy of the cohort
            retrieved_at=retrieved_at,
            level=MARKET_RECORD,
            independence_group=f"cohort:{study['studyId']}",
            status_key=key,
            version=1,
        )
