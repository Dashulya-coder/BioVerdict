"""How many people have the disease: Orphanet, CDC and the population they are applied to (A9).

Three open sources, none of which needs a key:

- **Orphanet** (Orphadata, CC BY 4.0): prevalence of rare diseases, found by the Orphanet code
  Open Targets lists for the resolved disease.
- **CDC Chronic Disease Indicators**: measured prevalence among US adults, for the few common
  conditions the data set covers.
- **World Bank**: the US population the rates are multiplied by.

Cancer incidence by site is not covered: no open source without a key was found for it. Every
record is a status fact stored whole; the patient count is computed from them by code
(`bioverdict/market/tam.py`), never by a model.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import date, datetime

import httpx

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.opentargets import OpenTargetsApi
from bioverdict.connectors.validate import contains, json_rows, world_bank_page
from bioverdict.store.as_of import filter_as_of
from bioverdict.store.models import Evidence, EvidenceLevel, Locator, ResolverOutput, SourceKind

# A count of patients says nothing about whether a target is causal or a drug works. Every
# record here carries the level that weighs nothing in those claims, so citing a prevalence can
# never raise scientific confidence.
MARKET_RECORD = EvidenceLevel.REGISTRY_RECORD

ORPHANET_FAMILY = "orphanet_prevalence"
CDC_FAMILY = "cdc_indicator"
POPULATION_FAMILY = "population"

XREFS_QUERY = "query ($id: String!) { disease(efoId: $id) { id name dbXRefs } }"
ORPHANET_URL = "https://www.orphadata.com/data/xml/en_product9_prev.xml"
ORPHANET_PAGE = "https://www.orpha.net/en/disease/detail/"
_PREVALENCE_FIELDS = (
    "PrevalenceType",
    "PrevalenceQualification",
    "PrevalenceClass",
    "PrevalenceGeographic",
    "PrevalenceValidationStatus",
)

CDC_URL = "https://data.cdc.gov/resource/hksd-2xuw.json"
# The indicator that measures each condition, by the disease id the Resolver confirms. Only
# identifiers are written here; the numbers always come from the CDC.
CDC_QUESTIONS = {
    "MONDO_0011122": "Obesity among adults",
    "MONDO_0005044": "High blood pressure among adults",
    "MONDO_0004979": "Current asthma among adults",
}
_CDC_FIELDS = (
    "yearend",
    "locationdesc",
    "datasource",
    "topic",
    "question",
    "datavaluetype",
    "datavalueunit",
    "datavalue",
    "lowconfidencelimit",
    "highconfidencelimit",
)

WORLD_BANK_URL = "https://api.worldbank.org/v2/country/US/indicator/"
POPULATION_INDICATORS = ("SP.POP.TOTL", "SP.POP.1564.TO", "SP.POP.65UP.TO")


def _disease_id(query: ResolverOutput) -> str | None:
    return query.indication.mondo_id or query.indication.efo_id


def xrefs_payload(disease_id: str) -> dict:
    return {"query": XREFS_QUERY, "variables": {"id": disease_id}}


def orphanet_codes(answer: dict) -> list[str]:
    """The Orphanet codes Open Targets cross-references for the disease."""
    disease = (answer.get("data") or {}).get("disease") or {}
    codes = [
        ref.split(":", 1)[1] for ref in disease.get("dbXRefs") or [] if ref.startswith("Orphanet:")
    ]
    return sorted(set(codes))


def parse_orphanet(xml: bytes, codes: list[str], retrieved_at: datetime) -> list[Evidence]:
    """Every prevalence record of the given disorders, with Orphanet's own field names."""
    root = ET.fromstring(xml)
    released = root.attrib.get("date", "")[:10]
    published = date.fromisoformat(released) if released else None
    evidence = []
    for disorder in root.iter("Disorder"):
        code = disorder.findtext("OrphaCode")
        if code not in codes:
            continue
        for record in disorder.iter("Prevalence"):
            fragment = {"OrphaCode": code, "Name": disorder.findtext("Name")}
            fragment |= {
                field: record.findtext(f"{field}/Name")
                for field in _PREVALENCE_FIELDS
                if record.findtext(f"{field}/Name")
            }
            fragment |= {"ValMoy": record.findtext("ValMoy"), "Source": record.findtext("Source")}
            evidence.append(
                Evidence(
                    id=f"orphanet:{code}:{record.attrib['id']}",  # placeholder until the freeze
                    source="Orphanet",
                    source_family=ORPHANET_FAMILY,
                    source_kind=SourceKind.REGISTRY,
                    url=f"{ORPHANET_PAGE}{code}",
                    locator=Locator(type="orphanet", value=code),
                    excerpt=json.dumps(fragment, ensure_ascii=False),
                    published_at=published,
                    retrieved_at=retrieved_at,
                    level=MARKET_RECORD,
                    independence_group="database:orphanet",
                    status_key=f"orphanet:{code}:{record.attrib['id']}",
                    version=1,
                )
            )
    return evidence


_ORPHANET_FILE = contains(b"<JDBOR", b"<DisorderList", b"</JDBOR>")  # whole, not cut short


class OrphanetConnector:
    """Satisfies `Connector`. Prevalence of the resolved disease when Orphanet lists it.

    The disease is identified through Open Targets' cross-reference, never by its name.
    """

    name = "orphanet"

    def __init__(self, http: CachedHttpClient) -> None:
        self._http = http
        self._api = OpenTargetsApi(http)

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        disease_id = _disease_id(query)
        if disease_id is None:
            return []
        answer, _ = await self._api.query(xrefs_payload(disease_id))
        codes = orphanet_codes(answer)
        if not codes:
            return []
        response = await self._http.get(ORPHANET_URL, validate=_ORPHANET_FILE)
        return filter_as_of(parse_orphanet(response.body, codes, response.fetched_at), as_of)


def cdc_params(question: str) -> dict[str, str]:
    where = (
        "locationabbr='US' AND stratificationcategory1='Overall' "
        f"AND datavaluetype='Crude Prevalence' AND question='{question}'"
    )
    return {"$where": where, "$order": "yearend DESC", "$limit": "1"}


def parse_cdc(rows: list[dict], url: str, retrieved_at: datetime) -> list[Evidence]:
    evidence = []
    for row in rows:
        if not row.get("datavalue"):
            continue
        fragment = {field: row[field] for field in _CDC_FIELDS if row.get(field)}
        evidence.append(
            Evidence(
                id=f"cdc:{row.get('questionid')}:{row.get('yearend')}",  # placeholder
                source="CDC Chronic Disease Indicators",
                source_family=CDC_FAMILY,
                source_kind=SourceKind.REGULATOR,
                url=url,
                locator=Locator(type="cdc_indicator", value=str(row.get("questionid"))),
                excerpt=json.dumps(fragment, ensure_ascii=False),
                published_at=None,  # a snapshot of the current release
                retrieved_at=retrieved_at,
                level=MARKET_RECORD,
                independence_group="agency:cdc",
                status_key=f"cdc:{row.get('questionid')}",
                version=1,
            )
        )
    return evidence


class CdcIndicatorsConnector:
    """Satisfies `Connector`. US adult prevalence for the conditions in `CDC_QUESTIONS`."""

    name = "cdc_indicators"

    def __init__(self, http: CachedHttpClient) -> None:
        self._http = http

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        question = CDC_QUESTIONS.get(_disease_id(query) or "")
        if question is None:
            return []
        params = cdc_params(question)
        response = await self._http.get(CDC_URL, params, validate=json_rows)
        source = str(httpx.URL(CDC_URL, params=params))
        rows = json.loads(response.body)
        return filter_as_of(parse_cdc(rows, source, response.fetched_at), as_of)


def parse_population(body: bytes, url: str, retrieved_at: datetime) -> list[Evidence]:
    answer = json.loads(body)
    rows = answer[1] if isinstance(answer, list) and len(answer) > 1 and answer[1] else []
    evidence = []
    for row in rows:
        if row.get("value") is None:
            continue
        indicator = row["indicator"]["id"]
        fragment = {key: row[key] for key in ("indicator", "country", "date", "value")}
        evidence.append(
            Evidence(
                id=f"worldbank:{indicator}",  # placeholder until the freeze
                source="World Bank",
                source_family=POPULATION_FAMILY,
                source_kind=SourceKind.REGULATOR,
                url=url,
                locator=Locator(type="worldbank_indicator", value=indicator),
                excerpt=json.dumps(fragment, ensure_ascii=False),
                published_at=None,  # a snapshot of the current release
                retrieved_at=retrieved_at,
                level=MARKET_RECORD,
                independence_group="agency:worldbank",
                status_key=f"worldbank:US:{indicator}",
                version=1,
            )
        )
    return evidence


class PopulationConnector:
    """Satisfies `Connector`. The US population: total, and the two adult age bands.

    Read only when the indication is identified, since it is used with a prevalence only.
    """

    name = "population"

    def __init__(self, http: CachedHttpClient) -> None:
        self._http = http

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        if _disease_id(query) is None:
            return []
        evidence: list[Evidence] = []
        for indicator in POPULATION_INDICATORS:
            url = WORLD_BANK_URL + indicator
            params = {"format": "json", "mrnev": "1"}
            response = await self._http.get(url, params, validate=world_bank_page)
            source = str(httpx.URL(url, params=params))
            evidence += parse_population(response.body, source, response.fetched_at)
        return filter_as_of(evidence, as_of)


CANCER_FAMILY = "cancer_incidence"
CANCER_URL = "https://statecancerprofiles.cancer.gov/incidencerates/index.php"
# The registry's site code for each resolved disease. A site can be wider than the disease
# (non-small cell lung carcinoma is counted within "Lung & Bronchus"); the estimate says so.
CANCER_SITES = {
    "MONDO_0005233": "047",  # non-small cell lung carcinoma -> Lung & Bronchus
    "MONDO_0005192": "040",  # exocrine pancreatic carcinoma -> Pancreas
    "MONDO_0005184": "040",  # pancreatic ductal adenocarcinoma -> Pancreas
    "MONDO_0005575": "020",  # colorectal cancer -> Colon & Rectum
}
_US_ROW = "US (SEER+NPCR)"


def cancer_params(site: str) -> dict[str, str]:
    """All races, both sexes, all ages, all stages, latest five-year period, as CSV."""
    return {
        "stateFIPS": "00", "areatype": "state", "cancer": site, "race": "00", "sex": "0",
        "age": "001", "stage": "999", "year": "0", "type": "incd",
        "sortVariableName": "rate", "sortOrder": "default", "output": "1",
    }  # fmt: skip


def parse_cancer(body: bytes, site: str, url: str, retrieved_at: datetime) -> list[Evidence]:
    """The national row of the report, verbatim, with the report's title and header line."""
    lines = [line.strip() for line in body.decode("utf-8", "replace").splitlines()]
    title = next((line.strip('"') for line in lines if line.startswith('"') and "," in line), "")
    header = next((line for line in lines if line.startswith("State,FIPS")), None)
    national = next((line for line in lines if line.startswith(f'"{_US_ROW}')), None)
    if header is None or national is None:
        raise ValueError("the cancer incidence report has no national row")
    fragment = {"report": title, "columns": header, "row": national}
    return [
        Evidence(
            id=f"cancer:{site}",  # placeholder until the freeze
            source="NCI State Cancer Profiles",
            source_family=CANCER_FAMILY,
            source_kind=SourceKind.REGULATOR,
            url=url,
            locator=Locator(type="cancer_site", value=site),
            excerpt=json.dumps(fragment, ensure_ascii=False),
            published_at=None,  # a snapshot of the current release
            retrieved_at=retrieved_at,
            level=MARKET_RECORD,
            independence_group="agency:nci-cdc",
            status_key=f"cancer_incidence:US:{site}",
            version=1,
        )
    ]


_CANCER_REPORT = contains(b"State,FIPS", f'"{_US_ROW}'.encode())


class CancerIncidenceConnector:
    """Satisfies `Connector`. New cases a year in the US for the sites in `CANCER_SITES`."""

    name = "cancer_incidence"

    def __init__(self, http: CachedHttpClient) -> None:
        self._http = http

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        site = CANCER_SITES.get(_disease_id(query) or "")
        if site is None:
            return []
        params = cancer_params(site)
        response = await self._http.get(CANCER_URL, params, validate=_CANCER_REPORT)
        source = str(httpx.URL(CANCER_URL, params=params))
        return filter_as_of(parse_cancer(response.body, site, source, response.fetched_at), as_of)
